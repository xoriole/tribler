import logging
import struct
import time
from asyncio import Future

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import UdpRequestType, UdpRequest, HealthInfo
from tribler.core.components.torrent_checker.torrent_checker.trackers import TrackerException

TRACKER_ACTION_CONNECT = 0
TRACKER_ACTION_ANNOUNCE = 1
TRACKER_ACTION_SCRAPE = 2

MAX_INT32 = 2 ** 16 - 1

UDP_TRACKER_INIT_CONNECTION_ID = 0x41727101980


class UdpTrackerProtocol:

    def __init__(self, socket_manager, socks_proxy=None):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.transaction_id = 0
        self.socket_manager = socket_manager
        self.socks_proxy = socks_proxy

    def get_next_transaction_id(self):
        transaction_id = self.transaction_id
        self.transaction_id += 1
        return transaction_id

    def compose_connect_request(self, host, port):
        transaction_id = self.get_next_transaction_id()

        connection_id = UDP_TRACKER_INIT_CONNECTION_ID
        action = TRACKER_ACTION_CONNECT

        message = struct.pack('!qii', connection_id, action, transaction_id)
        receiver = (host, port)

        udp_request = UdpRequest(
            request_type=UdpRequestType.CONNECTION_REQUEST,
            transaction_id=transaction_id,
            receiver=receiver,
            data=message,
            socks_proxy=self.socks_proxy,
            response=Future()
        )
        return udp_request

    async def send_connection_request(self, ip_address, port):
        connection_request = self.compose_connect_request(ip_address, port)
        await self.socket_manager.send(connection_request, response_callback=self.process_connection_response)
        return await connection_request.response

    def process_connection_response(self, connection_request: UdpRequest, response):
        if len(response) < 16:
            self._logger.error("%s Invalid response for UDP CONNECT: %s", self, repr(response))
            raise TrackerException("Invalid response size")

        action, transaction_id = struct.unpack_from('!ii', response, 0)
        if action != TRACKER_ACTION_CONNECT or transaction_id != connection_request.transaction_id:
            errmsg_length = len(response) - 8
            error_message, = struct.unpack_from('!' + str(errmsg_length) + 's', response, 8)

            self._logger.info("%s Error response for UDP CONNECT [%s]: %s",
                              self, repr(response), repr(error_message))
            raise TrackerException(error_message.decode('utf8', errors='ignore'))

        connection_id = struct.unpack_from('!q', response, 8)[0]

        response_future = connection_request.response
        if not response_future.done():
            connection_request.response.set_result(connection_id)

    def compose_scrape_request(self, host, port, connection_id, infohash_list):
        transaction_id = self.get_next_transaction_id()
        action = TRACKER_ACTION_SCRAPE
        fmt = '!qii' + ('20s' * len(infohash_list))
        message = struct.pack(fmt, connection_id, action, transaction_id, *infohash_list)
        receiver = (host, port)

        udp_request = UdpRequest(
            request_type=UdpRequestType.SCRAPE_REQUEST,
            transaction_id=transaction_id,
            receiver=receiver,
            data=message,
            connection_id=connection_id,
            socks_proxy=self.socks_proxy,
            infohashes=infohash_list,
            response=Future()
        )
        return udp_request

    async def send_scrape_request(self, ip_address, port, connection_id, infohash_list):
        scrape_request = self.compose_scrape_request(ip_address, port, connection_id, infohash_list)
        await self.socket_manager.send(scrape_request, response_callback=self.process_scrape_response)
        return await scrape_request.response

    def process_scrape_response(self, scrape_request: UdpRequest, response):
        if len(response) < 8:
            self._logger.info("%s Invalid response for UDP SCRAPE: %s", self, repr(response))
            raise TrackerException("Invalid message size of scrape response")

        action, transaction_id = struct.unpack_from('!ii', response, 0)
        if action != TRACKER_ACTION_SCRAPE or transaction_id != scrape_request.transaction_id:
            errmsg_length = len(response) - 8
            error_message, = struct.unpack_from('!' + str(errmsg_length) + 's', response, 8)

            self._logger.info("%s Error response for UDP SCRAPE: [%s] [%s]",
                              self, repr(response), repr(error_message))
            raise TrackerException(error_message.decode('utf8', errors='ignore'))

        scrape_response_initial_offset = 8
        infohash_list = scrape_request.infohashes

        # Response should be a multiple of 12 bytes which includes the health info for each infohash.
        if len(response) - scrape_response_initial_offset != len(infohash_list) * 12:
            self._logger.info("%s UDP SCRAPE response mismatch: %s", self, len(response))
            raise TrackerException("Invalid UDP tracker response size")

        offset = scrape_response_initial_offset
        now = int(time.time())
        response_list = []

        for infohash in infohash_list:
            complete, _downloaded, incomplete = struct.unpack_from('!iii', response, offset)
            response_list.append(HealthInfo(infohash, last_check=now, seeders=complete, leechers=incomplete))
            offset += 12

        response_future = scrape_request.response
        if not response_future.done():
            scrape_request.response.set_result(response_list)
