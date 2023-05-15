import asyncio

from ipv8.taskmanager import TaskManager

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import HealthInfo, TrackerResponse
from tribler.core.components.torrent_checker.torrent_checker.socket_manager import UdpSocketManager
from tribler.core.components.torrent_checker.torrent_checker.trackers import TrackerException
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.dht import DHTTracker
from tribler.core.components.torrent_checker.torrent_checker.trackers.http import HttpTracker
from tribler.core.components.torrent_checker.torrent_checker.trackers.udp import UdpTracker
from tribler.core.components.torrent_checker.torrent_checker.utils import filter_non_exceptions, \
    gather_coros, aggregate_health_info


class ICheckerService:

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def get_health_info(self, infohash, tracker_urls=None, timeout=5) -> HealthInfo:
        pass

    async def get_tracker_response(self, tracker_url, infohashes=None, timeout=5) -> TrackerResponse:
        pass


class CheckerService(ICheckerService, TaskManager):

    def __init__(self, proxy=None):
        super().__init__()
        self.proxy = proxy
        self.socket_mgr = UdpSocketManager()
        self.udp_transport = None
        self.trackers = []

    async def initialize(self):
        await self._create_socket_or_schedule()
        udp_tracker = UdpTracker(self.socket_mgr, proxy=self.proxy)
        dht_tracker = DHTTracker(self.socket_mgr, proxy=self.proxy)
        http_tracker = HttpTracker(self.proxy)

        self.trackers = [dht_tracker, udp_tracker, http_tracker]

    async def _create_socket_or_schedule(self):
        """
        This method attempts to bind to a UDP port. If it fails for some reason (i.e. no network connection), we try
        again later.
        """
        try:
            self.udp_transport = await self._create_udp_socket()
        except OSError as e:
            retry_seconds = 10
            self._logger.error("Error when creating UDP socket: %s; Will retry in %d seconds", e, retry_seconds)
            self.register_task("listen_udp_port", self._create_socket_or_schedule, delay=retry_seconds)

    async def _create_udp_socket(self):
        loop = asyncio.get_event_loop()
        transport, _ = await loop.create_datagram_endpoint(lambda: self.socket_mgr, local_addr=('0.0.0.0', 0))
        return transport

    async def shutdown(self):
        """
        Shutdown the torrent health checker.

        Once shut down it can't be started again.
        :returns A deferred that will fire once the shutdown has completed.
        """
        for tracker in self.trackers:
            tracker.shutdown()

        if self.udp_transport:
            self.udp_transport.close()
            self.udp_transport = None

        await self.shutdown_task_manager()

    async def get_health_info(self, infohash, tracker_urls=None, timeout=5) -> HealthInfo:
        if not tracker_urls:
            tracker_urls = ['DHT']

        health_response_coros = []
        for tracker in self.trackers:
            for tracker_url in tracker_urls:
                if tracker.is_supported_url(tracker_url):
                    health_response_coro = tracker.get_torrent_health(infohash, tracker_url, timeout=timeout)
                    health_response_coros.append(health_response_coro)

        responses = await gather_coros(health_response_coros)
        self._logger.info(f'{len(responses)} responses have been received: {responses}')

        successful_responses = filter_non_exceptions(responses)
        health = aggregate_health_info(infohash, successful_responses)
        return health

    async def get_tracker_response(self, tracker_url, infohashes=None, timeout=20) -> TrackerResponse:
        for tracker in self.trackers:
            if tracker.is_supported_url(tracker_url):
                return await tracker.get_tracker_response(tracker_url, infohashes, timeout=timeout)

        raise TrackerException(f"Unknown tracker: {tracker_url}")
