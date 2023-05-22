import asyncio
import logging
import random
from asyncio import Future

import libtorrent as lt

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import UdpRequestType, DhtTrackerRequest
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.dht_response import DhtResponse
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.session import DhtRequestSession
from tribler.core.components.torrent_checker.torrent_checker.trackers.exceptions import TooManyDHTRequestsError

MAX_INT32 = 2 ** 16 - 1
MAX_NODES_TO_REQUEST = 1000
MAX_RESPONSES_TO_WAIT = 100

DEFAULT_DHT_ROUTERS = [
    ("dht.libtorrent.org", 25401),
    ("router.bittorrent.com", 6881)
]


class DhtProtocol:
    """
    DHT Protocol implements BEP33 Protocol.

    Message flow:
    1. We send DHT Request to the router.
    2. The router returns a DHT response with list of nodes.
    3. We send DHT Request to those nodes.
    4. Nodes returns DHT response.
    5. We process each received DHT Response:
        a) If the response contains bloom filter, then combine the bloom filters.
        b) If the response contains other nodes, we send DHT request to those nodes and wait for response.
        c) If enough response is received or max number of nodes are contacted, we finalize the health response from
           bloom filters and return the response.
    """

    def __init__(self, socket_manager, socks_proxy=None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.socket_mgr = socket_manager
        self.socks_proxy = socks_proxy

        self.max_nodes_to_request = MAX_NODES_TO_REQUEST
        self.max_responses_to_wait = MAX_RESPONSES_TO_WAIT

        self.dht_sessions = dict()
        self.transaction_ids = set()

    async def do_health_request(self, infohash):
        if infohash in self.dht_sessions:
            return self.dht_sessions[infohash]

        request = self.create_new_session(infohash)
        await self.send_dht_request_to_router(infohash)
        return request

    def create_new_session(self, infohash):
        self.dht_sessions[infohash] = DhtRequestSession(infohash)
        return self.dht_sessions[infohash]

    async def send_dht_request_to_router(self, infohash):
        router_host, router_port = random.choice(DEFAULT_DHT_ROUTERS)
        self.logger.info(f"Selected router: ({(router_host, router_port)}) for DHT request [{infohash}]")
        await self.send_dht_request(router_host, router_port, infohash)

    async def send_dht_request(self, node_ip, node_port, infohash):
        peer_request = self.compose_dht_request(node_ip, node_port, infohash)
        await self.socket_mgr.send(peer_request, response_callback=self.process_dht_response)
        await asyncio.sleep(0.1)

    def compose_dht_request(self, host, port, infohash):
        tx_id = self._reserve_tx_id()
        payload = self._compose_dht_request_payload(infohash, tx_id)
        udp_request = self._compose_dht_request(infohash, tx_id, payload, host, port)
        return udp_request

    def _reserve_tx_id(self):
        for _ in range(MAX_INT32):
            tx_id = random.randint(1, MAX_INT32).to_bytes(2, 'big')
            if tx_id not in self.transaction_ids:
                self.transaction_ids.add(tx_id)
                return tx_id

        raise TooManyDHTRequestsError()

    def _compose_dht_request(self, infohash, tx_id, payload, host, port):
        return DhtTrackerRequest(
            request_type=UdpRequestType.DHT_REQUEST,
            transaction_id=tx_id,
            receiver=(host, port),
            data=payload,
            socks_proxy=self.socks_proxy,
            response=Future(),
            infohash=infohash
        )

    def _compose_dht_request_payload(self, infohash, tx_id):
        request = {
            't': tx_id,
            'y': b'q',
            'q': b'get_peers',
            'a': {
                'id': infohash,
                'info_hash': infohash,
                'noseed': 1,
                'scrape': 1
            }
        }
        payload = lt.bencode(request)
        return payload

    async def process_dht_response(self, dht_request: DhtTrackerRequest, response: bytes):
        dht_response = DhtResponse(response)

        self.transaction_ids.remove(dht_response.transaction_id)

        if not dht_response.is_valid():
            self.logger.error("Invalid BEP33 response found")
            return

        if not dht_response.is_reply():
            self.logger.error("Skipping non-reply DHT response")
            return

        session: DhtRequestSession = self.dht_sessions[dht_request.infohash]
        if dht_response.has_bloom_filters():
            session.add_response(dht_response)

        if dht_response.has_nodes():
            await self.process_node_request(session, dht_response)

        if session.max_responses_received():
            await session.send_response()

    async def process_node_request(self, health_request, dht_response: DhtResponse):
        for (_node_id, node_ip, node_port) in dht_response.nodes:
            if health_request.max_nodes_requested():
                return

            health_request.add_request_to_session(self.send_dht_request(node_ip, node_port, health_request.infohash))
            health_request.requested_nodes.add((node_ip, node_port))
