import asyncio
import logging
import random

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import TrackerResponse, UdpRequest, HealthInfo
from tribler.core.components.torrent_checker.torrent_checker.socket_manager import UdpSocketManager
from tribler.core.components.torrent_checker.torrent_checker.trackers import Tracker
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.dht_response import DhtResponse
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.request import DhtHealthRequest
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.request_manager import DhtRequestManager

DEFAULT_DHT_ROUTERS = [
    ("dht.libtorrent.org", 25401),
    ("router.bittorrent.com", 6881)
]


class DHTTracker(Tracker):
    """
    This class manages BEP33 health requests to the libtorrent DHT.
    """
    def __init__(self, udp_socket_server: UdpSocketManager, proxy=None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.socket_mgr = udp_socket_server
        self.proxy = proxy

        self.request_manager = DhtRequestManager()

    def is_supported_url(self, tracker_url: str):
        return not tracker_url or tracker_url.lower().startswith("dht")

    async def get_torrent_health(self, infohash, tracker_url, timeout=5) -> HealthInfo:
        if self.request_manager.request_exists(infohash):
            return await self.request_manager.get_request(infohash).response_future

        dht_request = await self.create_health_check_request(infohash, timeout)
        return await dht_request.response_future

    async def get_tracker_response(self, tracker_url, infohashes, timeout=5) -> TrackerResponse:
        # We can only check one infohash at a time so, we collect all co-routines and send the responses
        torrent_health_list = []
        for infohash in infohashes:
            health_info = await self.get_torrent_health(infohash, None, timeout=timeout)
            torrent_health_list.append(health_info)

        return TrackerResponse('DHT', torrent_health_list)

    async def create_health_check_request(self, infohash, timeout) -> DhtHealthRequest:
        health_request = self.request_manager.new_health_request(infohash, timeout)

        await self.request_peers_from_dht_router(infohash)

        return health_request

    async def request_peers_from_dht_router(self, infohash):
        # A random DHT router is selected and request is sent.
        router_host, router_port = random.choice(DEFAULT_DHT_ROUTERS)
        self.logger.info(f"Selected router: ({(router_host, router_port)}) for DHT request [{infohash}]")
        await self.request_peers_from_dht_node(router_host, router_port, infohash)

    async def request_peers_from_dht_node(self, node_ip, node_port, infohash):
        if peer_request := self.request_manager.compose_dht_request(node_ip, node_port, infohash, self.proxy):
            await self.socket_mgr.send(peer_request, response_callback=self.process_dht_response)
            self.request_manager.add_node_request(infohash, node_ip, node_port)

    async def process_dht_response(self, dht_request: UdpRequest, response: bytes):
        dht_response = DhtResponse(response)
        # print(f"processing response")
        if not dht_response.is_valid():
            self.logger.error("Invalid BEP33 response found")
            return

        if not dht_response.is_reply():
            self.logger.error("Skipping non-reply DHT response")
            return

        response_tx_id = dht_response.transaction_id
        request_tx_id = dht_request.transaction_id
        if request_tx_id != response_tx_id:
            self.logger.error(f"Invalid DHT response; Tx ID mismatch [{request_tx_id}=/={response_tx_id}]")
            return

        infohash = self.request_manager.get_infohash(response_tx_id)
        if not infohash:
            self.logger.error(f"No torrent found for tx id: {response_tx_id}")
            return

        if dht_response.has_bloom_filters():
            self.request_manager.process_dht_response(dht_response)

        if dht_response.has_nodes():
            await self.send_dht_get_peers_request_to_closest_nodes(infohash, dht_response.nodes)

        self.request_manager.cleanup_tx(response_tx_id)

    async def send_dht_get_peers_request_to_closest_nodes(self, infohash, decoded_nodes):
        for (_node_id, node_ip, node_port) in decoded_nodes:
            if self.request_manager.max_nodes_requested(infohash):
                return
            if self.request_manager.max_response_received(infohash):
                return

            if not self.request_manager.is_node_requested(infohash, node_ip, node_port):
                await asyncio.sleep(0.01)
                await self.request_peers_from_dht_node(node_ip, node_port, infohash)

    async def shutdown(self):
        await self.request_manager.shutdown()
