import logging
import random
from asyncio import Future
from binascii import hexlify

from ipv8.requestcache import RequestCache

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import UdpRequest, UdpRequestType
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht import dht_utils
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.dht_response import DhtResponse
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.request import DhtHealthRequest

MAX_INT32 = 2 ** 16 - 1
MAX_NODES_TO_REQUEST = 1000
MAX_RESPONSES_TO_WAIT = 100


class DhtRequestManager(RequestCache):

    def __init__(self):
        super(DhtRequestManager, self).__init__()
        self.logger = logging.getLogger(self.__class__.__name__)

        self.tx_id_to_cache = dict()
        self.tx_id_to_infohash = dict()

        self.infohash_to_nodes = dict()
        self.infohash_to_responses = dict()

    def request_exists(self, infohash):
        exists = self.has(DhtHealthRequest.CACHE_PREFIX, DhtHealthRequest.infohash_to_number(infohash))
        return exists

    def get_request(self, infohash) -> DhtHealthRequest:
        return self.get(DhtHealthRequest.CACHE_PREFIX, DhtHealthRequest.infohash_to_number(infohash))

    def pop_infohash(self, tx_id):
        return self.tx_id_to_infohash.pop(tx_id, None)

    def get_infohash(self, tx_id):
        return self.tx_id_to_infohash.get(tx_id, None)

    def new_health_request(self, infohash, timeout):
        dht_request = DhtHealthRequest(self, infohash, timeout)
        self.add(dht_request)
        return dht_request

    def reserve_tx_id(self, infohash):
        for _ in range(MAX_INT32):
            tx_id = random.randint(1, MAX_INT32).to_bytes(2, 'big')
            if tx_id not in self.tx_id_to_infohash:
                self.tx_id_to_infohash[tx_id] = infohash
                return tx_id
        return None

    def register_tx_id_to_health_request(self, tx_id, infohash):
        cache = self.get_request(infohash)
        if not cache:
            self.logger.info(f"Cache not found for infohash: {infohash}")
            return None

        cache.register_transaction_id(tx_id)

    def compose_dht_request(self, host, port, infohash, proxy):
        # DHT requests require a unique transaction ID. This transaction ID
        # is returned on the response but not the infohash. So, we have to maintain a
        # map to transaction ID to infohash for associating response to infohash.
        tx_id = self.reserve_tx_id(infohash)
        if not tx_id:
            self.logger.error(f"Too many DHT requests already; Skipping peer request")
            return None

        self.register_tx_id_to_health_request(tx_id, infohash)

        payload = dht_utils.compose_dht_get_peers_payload(tx_id, infohash)
        udp_request = UdpRequest(
            request_type=UdpRequestType.DHT_REQUEST,
            transaction_id=tx_id,
            receiver=(host, port),
            data=payload,
            socks_proxy=proxy,
            response=Future()
        )
        return udp_request

    def process_dht_response(self, dht_response: DhtResponse):
        tx_id = dht_response.transaction_id

        infohash = self.get_infohash(tx_id)
        if not infohash:
            self.logger.error(f"No torrent found for tx id: {tx_id}")
            return

        cache = self.get_request(infohash)
        if not cache:
            self.logger.error(f"No request found for infohash: {hexlify(infohash)}")
            return

        bf_seeds, bf_peers = dht_response.bloom_filters
        cache.register_bloom_filters(tx_id, bf_seeds, bf_peers)

        self.increment_response_count(infohash)

    def increment_response_count(self, infohash):
        received_responses = self.infohash_to_responses.get(infohash, 0)
        self.infohash_to_responses[infohash] = received_responses + 1

    def max_nodes_requested(self, infohash):
        sent_nodes = self.infohash_to_nodes.get(infohash, [])
        return len(sent_nodes) >= MAX_NODES_TO_REQUEST

    def max_response_received(self, infohash):
        request = self.get_request(infohash)
        if request:
            return request.num_responses > MAX_RESPONSES_TO_WAIT
        return False

    def is_node_requested(self, infohash, node_ip, node_port):
        ip_port_str = f'{node_ip}:{node_port}'
        return ip_port_str in self.infohash_to_nodes.get(infohash, [])

    def add_node_request(self, infohash, node_ip, node_port):
        ip_port_str = f'{node_ip}:{node_port}'
        requested_nodes = self.infohash_to_nodes.get(infohash, [])
        requested_nodes.append(ip_port_str)
        self.infohash_to_nodes[infohash] = requested_nodes

    def cleanup_tx(self, tx_id):
        self.tx_id_to_infohash.pop(tx_id, None)
        self.tx_id_to_cache.pop(tx_id, None)
