import logging
from asyncio.exceptions import TimeoutError

import async_timeout

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import TrackerResponse
from tribler.core.components.torrent_checker.torrent_checker.socket_manager import UdpTrackerDataProtocol
from tribler.core.components.torrent_checker.torrent_checker.trackers import Tracker, TrackerException, tracker_utils
from tribler.core.components.torrent_checker.torrent_checker.trackers.udp.protocol import UdpTrackerProtocol
from tribler.core.utilities.tracker_utils import parse_tracker_url


class UdpTracker(Tracker):
    """
        The UDPTrackerSession makes a connection with a UDP tracker and queries
        seeders and leechers for one or more infohashes. It handles the message serialization
        and communication with the torrent checker by making use of Deferred (asynchronously).
        """

    def __init__(self, udp_socket_server: UdpTrackerDataProtocol, proxy=None):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.socket_mgr = udp_socket_server
        self.proxy = proxy

        self.protocol = UdpTrackerProtocol(self.socket_mgr, self.proxy)

    def is_supported_url(self, tracker_url: str):
        return tracker_url.lower().startswith("udp://")

    async def get_torrent_health(self, infohash, tracker_url, timeout=5):
        tracker_response: TrackerResponse = await self.get_tracker_response(tracker_url, [infohash], timeout=timeout)
        if tracker_response and tracker_response.torrent_health_list:
            return tracker_response.torrent_health_list[0]
        return None

    async def get_tracker_response(self, tracker_url, infohashes, timeout=5, proxy=None) -> TrackerResponse:
        if not self.socket_mgr.transport:
            raise TrackerException("UDP socket transport is not ready yet")

        tracker_type, tracker_address, announce_page = parse_tracker_url(tracker_url)

        try:
            async with async_timeout.timeout(timeout):
                ip_address = await self.resolve_ip(tracker_address)
                port = int(tracker_address[1])

                connection_id = await self.protocol.send_connection_request(ip_address, port)
                response_list = await self.protocol.send_scrape_request(ip_address, port, connection_id, infohashes)
                return TrackerResponse(url=tracker_url, torrent_health_list=response_list)

        except TimeoutError as e:
            raise TrackerException("Request timeout resolving tracker ip") from e

    async def resolve_ip(self, tracker_address):
        """
        We only resolve the hostname if we're not using a proxy.
        If a proxy is used, the TunnelCommunity will resolve the hostname at the exit nodes.
        """
        if self.proxy:
            return tracker_address[0]

        return await tracker_utils.resolve_ip(tracker_address)
