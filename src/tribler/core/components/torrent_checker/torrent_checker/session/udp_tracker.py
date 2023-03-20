from __future__ import annotations

import logging
import random
import socket
import struct
import sys
import time
from asyncio import get_event_loop, Future, ensure_future, TimeoutError

import async_timeout

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import TrackerResponse, HealthInfo
from tribler.core.components.torrent_checker.torrent_checker.session.tracker import TrackerSession

# Although these are the actions for UDP trackers, they can still be used as
# identifiers.
TRACKER_ACTION_CONNECT = 0
TRACKER_ACTION_ANNOUNCE = 1
TRACKER_ACTION_SCRAPE = 2

MAX_INT32 = 2 ** 16 - 1

UDP_TRACKER_INIT_CONNECTION_ID = 0x41727101980


class UdpTrackerSession(TrackerSession):
    """
    The UDPTrackerSession makes a connection with a UDP tracker and queries
    seeders and leechers for one or more infohashes. It handles the message serialization
    and communication with the torrent checker by making use of Deferred (asynchronously).
    """

    # A list of transaction IDs that have been used in order to avoid conflict.
    _active_session_dict = dict()

    def __init__(self, tracker_url, tracker_address, announce_page, timeout, proxy, socket_mgr):
        super().__init__('udp', tracker_url, tracker_address, announce_page, timeout)

        self._logger.setLevel(logging.INFO)
        self._connection_id = 0
        self.transaction_id = 0
        self.port = tracker_address[1]
        self.ip_address = None
        self.socket_mgr = socket_mgr
        self.proxy = proxy

        # prepare connection message
        self._connection_id = UDP_TRACKER_INIT_CONNECTION_ID
        self.action = TRACKER_ACTION_CONNECT
        self.generate_transaction_id()

    def generate_transaction_id(self):
        """
        Generates a unique transaction id and stores this in the _active_session_dict set.
        """
        while True:
            # make sure there is no duplicated transaction IDs
            transaction_id = random.randint(0, MAX_INT32)
            if transaction_id not in UdpTrackerSession._active_session_dict.items():
                UdpTrackerSession._active_session_dict[self] = transaction_id
                self.transaction_id = transaction_id
                break

    def remove_transaction_id(self):
        """
        Removes an session and its corresponding id from the _active_session_dict set and the socket manager.
        :param session: The session that needs to be removed from the set.
        """
        if self in UdpTrackerSession._active_session_dict:
            del UdpTrackerSession._active_session_dict[self]

        # Checking for socket_mgr is a workaround for race condition
        # in Tribler Session startup/shutdown that sometimes causes
        # unit tests to fail on teardown.
        if self.socket_mgr and self.transaction_id in self.socket_mgr.tracker_sessions:
            self.socket_mgr.tracker_sessions.pop(self.transaction_id)

    async def cleanup(self):
        """
        Cleans the session by cancelling all deferreds and closing sockets.
        :return: A deferred that fires once the cleanup is done.
        """
        await super().cleanup()
        self.remove_transaction_id()

    async def connect_to_tracker(self) -> TrackerResponse:
        """
        Connects to the tracker and starts querying for seed and leech data.
        :return: A dictionary containing seed/leech information per infohash
        """
        # No more requests can be appended to this session
        self.is_initiated = True

        # Clean old tasks if present
        await self.cancel_pending_task("result")
        await self.cancel_pending_task("resolve")

        try:
            async with async_timeout.timeout(self.timeout):
                # We only resolve the hostname if we're not using a proxy.
                # If a proxy is used, the TunnelCommunity will resolve the hostname at the exit nodes.
                if not self.proxy:
                    # Resolve the hostname to an IP address if not done already
                    coro = get_event_loop().getaddrinfo(self.tracker_address[0], 0, family=socket.AF_INET)
                    if isinstance(coro, Future):
                        infos = await coro  # In Python <=3.6 getaddrinfo returns a Future
                    else:
                        infos = await self.register_anonymous_task("resolve", ensure_future(coro))
                    self.ip_address = infos[0][-1][0]
                await self.connect()
                return await self.scrape()
        except TimeoutError:
            self.failed(msg='request timed out')
        except socket.gaierror as e:
            self.failed(msg=str(e))

    async def connect(self):
        """
        Creates a connection message and calls the socket manager to send it.
        """
        if not self.socket_mgr.transport:
            self.failed(msg="UDP socket transport not ready")

        # Initiate the connection
        message = struct.pack('!qii', self._connection_id, self.action, self.transaction_id)
        response = await self.socket_mgr.send_request(message, self)

        # check message size
        if len(response) < 16:
            self._logger.error("%s Invalid response for UDP CONNECT: %s", self, repr(response))
            self.failed(msg="invalid response size")

        # check the response
        action, transaction_id = struct.unpack_from('!ii', response, 0)
        if action != self.action or transaction_id != self.transaction_id:
            # get error message
            errmsg_length = len(response) - 8
            error_message, = struct.unpack_from('!' + str(errmsg_length) + 's', response, 8)

            self._logger.info("%s Error response for UDP CONNECT [%s]: %s",
                              self, repr(response), repr(error_message))
            self.failed(msg=error_message.decode('utf8', errors='ignore'))

        # update action and IDs
        self._connection_id = struct.unpack_from('!q', response, 8)[0]
        self.action = TRACKER_ACTION_SCRAPE
        self.generate_transaction_id()
        self.last_contact = int(time.time())

    async def scrape(self) -> TrackerResponse:
        # pack and send the message
        if sys.version_info.major > 2:
            infohash_list = self.infohash_list
        else:
            infohash_list = [str(infohash) for infohash in self.infohash_list]

        fmt = '!qii' + ('20s' * len(self.infohash_list))
        message = struct.pack(fmt, self._connection_id, self.action, self.transaction_id, *infohash_list)

        # Send the scrape message
        response = await self.socket_mgr.send_request(message, self)

        # check message size
        if len(response) < 8:
            self._logger.info("%s Invalid response for UDP SCRAPE: %s", self, repr(response))
            self.failed("invalid message size")

        # check response
        action, transaction_id = struct.unpack_from('!ii', response, 0)
        if action != self.action or transaction_id != self.transaction_id:
            # get error message
            errmsg_length = len(response) - 8
            error_message, = struct.unpack_from('!' + str(errmsg_length) + 's', response, 8)

            self._logger.info("%s Error response for UDP SCRAPE: [%s] [%s]",
                              self, repr(response), repr(error_message))
            self.failed(msg=error_message.decode('utf8', errors='ignore'))

        # get results
        if len(response) - 8 != len(self.infohash_list) * 12:
            self._logger.info("%s UDP SCRAPE response mismatch: %s", self, len(response))
            self.failed(msg="invalid response size")

        offset = 8

        response_list = []
        now = int(time.time())

        for infohash in self.infohash_list:
            complete, _downloaded, incomplete = struct.unpack_from('!iii', response, offset)
            offset += 12

            # Store the information in the hash dict to be returned.
            # Sow complete as seeders. "complete: number of peers with the entire file, i.e. seeders (integer)"
            #  - https://wiki.theory.org/BitTorrentSpecification#Tracker_.27scrape.27_Convention
            response_list.append(HealthInfo(infohash, seeders=complete, leechers=incomplete,
                                            last_check=now, self_checked=True))

        # close this socket and remove its transaction ID from the list
        self.remove_transaction_id()
        self.last_contact = int(time.time())
        self.is_finished = True

        return TrackerResponse(url=self.tracker_url, torrent_health_list=response_list)
