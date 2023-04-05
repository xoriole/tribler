import asyncio
import datetime
import logging
import math
import random
import time
from asyncio import Future
from asyncio.exceptions import TimeoutError
from binascii import hexlify
from typing import List, Tuple

import libtorrent as lt
from ipv8.requestcache import RequestCache, NumberCache
from ipv8.taskmanager import TaskManager

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import TrackerResponse, UdpRequest, HealthInfo, \
    UdpRequestType
from tribler.core.components.torrent_checker.torrent_checker.socket_manager import UdpSocketManager
from tribler.core.components.torrent_checker.torrent_checker.trackers import Tracker, dht_utils

MAX_NODES_TO_REQUEST = 1000
MAX_RESPONSES_TO_WAIT = 100
DEFAULT_DHT_ROUTERS = [
    ("dht.libtorrent.org", 25401),
    ("router.bittorrent.com", 6881)
]

MAX_INT32 = 2 ** 16 - 1


class DhtRequestCache(NumberCache):
    """
    Used to track outstanding dht request messages
    """
    def __init__(self, request_cache, infohash, timeout=15):
        super().__init__(request_cache, "DHT", hash(infohash))
        self.infohash = infohash

        self.response = {}
        self.response_future = Future()
        self.register_future(self.response_future)

        self.timeout = timeout

        self.transaction_ids = set()
        self.bf_seeders = bytearray(256)
        self.bf_peers = bytearray(256)

    @property
    def timeout_delay(self):
        return float(self.timeout)

    def register_transaction_id(self, transaction_id):
        print(f"DHT: registering transaction id")
        self.transaction_ids.add(transaction_id)

    def register_dht_response(self, transaction_id, bf_seeds, bf_peers):
        print(f"DHT: registering response")
        if transaction_id not in self.transaction_ids:
            return

        self.transaction_ids.remove(transaction_id)
        self.bf_seeders = dht_utils.combine_bloomfilters(self.bf_seeders, bf_seeds)
        self.bf_peers = dht_utils.combine_bloomfilters(self.bf_peers, bf_peers)

    def on_timeout(self):
        if self.response_future.done():
            return

        seeders = dht_utils.get_size_from_bloomfilter(self.bf_seeders)
        peers = dht_utils.get_size_from_bloomfilter(self.bf_peers)

        health = HealthInfo(self.infohash, last_check=int(time.time()), seeders=seeders, leechers=peers,
                            self_checked=True)

        tracker_response = TrackerResponse('DHT', [health])
        self.response_future.set_result(tracker_response)


class DHTTracker(TaskManager, Tracker):
    """
    This class manages BEP33 health requests to the libtorrent DHT.
    """
    def __init__(self, udp_socket_server: UdpSocketManager, proxy=None):
        TaskManager.__init__(self)
        self._logger = logging.getLogger(self.__class__.__name__)
        self.socket_mgr = udp_socket_server
        self.proxy = proxy

        self.lookup_futures = {}  # Map from binary infohash to future
        self.bf_seeders = {}  # Map from infohash to (final) seeders bloomfilter
        self.bf_peers = {}  # Map from infohash to (final) peers bloomfilter
        self.outstanding = {}  # Map from transaction_id to infohash

        self.health_result = {}

        self.tid_to_infohash = dict()
        self.infohash_to_nodes = dict()
        self.infohash_to_responses = dict()

        self.request_cache = RequestCache()
        self.tx_id_to_cache = {}

    def is_outstanding(self, infohash):
        print(f"{datetime.datetime.now()}: checking outstanding....")
        exists = self.request_cache.has("DHT", hash(infohash))
        print(f"{datetime.datetime.now()}: exists: {exists}")
        return exists

    def get_outstanding_request(self, infohash) -> DhtRequestCache:
        return self.request_cache.get("DHT", hash(infohash))

    def get_outstanding_request_by_tx_id(self, infohash) -> DhtRequestCache:
        return self.request_cache.get("DHT", hash(infohash))

    async def get_health(self, infohash, timeout=15) -> TrackerResponse:
        """
        Lookup the health of a given infohash.
        :param infohash: The 20-byte infohash to lookup.
        :param timeout: The timeout of the lookup.
        """
        # if infohash in self.lookup_futures:
        #     return await self.lookup_futures[infohash]
        #
        # lookup_future = Future()
        # self.lookup_futures[infohash] = lookup_future
        # self.bf_seeders[infohash] = bytearray(256)
        # self.bf_peers[infohash] = bytearray(256)

        if self.is_outstanding(infohash):
            return await self.get_outstanding_request(infohash).response_future

        dht_request = DhtRequestCache(self.request_cache, infohash)
        cache = self.request_cache.add(dht_request)
        # print(f"returned cache: {cache}")

        # Initially send request to one of the default DHT router and get the closest nodes.
        # Then query those nodes and process the Bloom filters from the response.
        await self.send_request_to_dht_router_and_continue(infohash)

        # self.register_task(f"lookup_{hexlify(infohash)}", self.finalize_lookup, infohash, delay=timeout)
        #
        # return await lookup_future
        print(f"Waiting for DHT response")
        response = await dht_request.response_future
        print(f"DHT response: {response}")

        return response

    async def send_request_to_dht_router_and_continue(self, infohash):
        # Select one of the default router and send the peer request.
        # Routers send nodes in the DHT response.
        # Those nodes will be queried while processing the response.
        router_host, router_port = random.choice(DEFAULT_DHT_ROUTERS)
        print(f"router: ({(router_host, router_port)}")
        await self.send_dht_get_peers_request(router_host, router_port, infohash)

    async def send_dht_get_peers_request(self, node_ip, node_port, infohash):
        dht_request = self.compose_dht_get_peers_request(node_ip, node_port, infohash)
        await self.socket_mgr.send(dht_request, response_callback=self.process_udp_raw_response)

    def compose_dht_get_peers_request(self, host, port, infohash):
        # DHT requests require a unique transaction ID. This transaction ID
        # is returned on the response but not the infohash. So, we have to maintain a
        # map to transaction ID to infohash for associating response to infohash.
        transaction_id = self.generate_unique_transaction_id()
        self.tid_to_infohash[transaction_id] = infohash
        self.register_transaction_id(infohash, transaction_id)

        payload = dht_utils.compose_dht_get_peers_payload(transaction_id, infohash)
        self.requesting_bloomfilters(transaction_id, infohash)

        udp_request = UdpRequest(
            request_type=UdpRequestType.DHT_REQUEST,
            transaction_id=transaction_id,
            receiver=(host, port),
            data=payload,
            socks_proxy=self.proxy,
            response=Future()
        )
        return udp_request

    def register_transaction_id(self, infohash, tx_id):
        cache = self.get_outstanding_request(infohash)
        if not cache:
            print(f"Cache not found for infohash: {infohash}")
            return
        cache.register_transaction_id(tx_id)
        self.tx_id_to_cache[tx_id] = cache

    def generate_unique_transaction_id(self):
        while True:
            tx_id = random.randint(1, MAX_INT32).to_bytes(2, 'big')
            if tx_id not in self.tid_to_infohash:
                return tx_id

    async def process_udp_raw_response(self, dht_request: UdpRequest, response: bytes):
        decoded = lt.bdecode(response)
        if not decoded:
            return

        await self.proccess_dht_response(decoded)

    def finalize_lookup(self, infohash):
        """
        Finalize the lookup of the provided infohash and invoke the appropriate deferred.
        :param infohash: The infohash of the lookup we finalize.
        """
        for transaction_id in [key for key, value in self.outstanding.items() if value == infohash]:
            self.outstanding.pop(transaction_id, None)

        if infohash not in self.lookup_futures:
            return

        if self.lookup_futures[infohash].done():
            return

        # Determine the seeders/peers
        bf_seeders = self.bf_seeders.pop(infohash)
        bf_peers = self.bf_peers.pop(infohash)

        seeders = dht_utils.get_size_from_bloomfilter(bf_seeders)
        peers = dht_utils.get_size_from_bloomfilter(bf_peers)

        health = HealthInfo(infohash, last_check=int(time.time()), seeders=seeders, leechers=peers, self_checked=True)
        self.health_result[infohash] = health

        tracker_response = TrackerResponse('DHT', [health])
        self.lookup_futures[infohash].set_result(tracker_response)

    async def proccess_dht_response(self, decoded):
        if b'r' in decoded:
            transaction_id = decoded[b't']
            infohash = self.tid_to_infohash.pop(transaction_id, None)
            if not infohash:
                return

            dht_response = decoded[b'r']
            if b'nodes' in dht_response:
                b_nodes = dht_response[b'nodes']
                decoded_nodes = dht_utils.decode_nodes(b_nodes)
                await self.send_dht_get_peers_request_to_closest_nodes(infohash, decoded_nodes)

            # We received a raw DHT message - decode it and check whether it is a BEP33 message.
            if b'BFsd' in dht_response and b'BFpe' in dht_response:
                received_responses = self.infohash_to_responses.get(infohash, 0)
                self.infohash_to_responses[infohash] = received_responses + 1

                seeders_bloom_filter = dht_response[b'BFsd']
                peers_bloom_filter = dht_response[b'BFpe']
                self.received_bloomfilters(transaction_id,
                                           bytearray(seeders_bloom_filter),
                                           bytearray(peers_bloom_filter))
                self.register_dht_response(transaction_id, seeders_bloom_filter, peers_bloom_filter)

    def register_dht_response(self, transaction_id, bf_seeds, bf_peers):
        cache: DhtRequestCache = self.tx_id_to_cache.get(transaction_id, None)
        if cache:
            cache.register_dht_response(transaction_id, bf_seeds, bf_peers)

    async def send_dht_get_peers_request_to_closest_nodes(self, infohash, decoded_nodes):
        sent_nodes = self.infohash_to_nodes.get(infohash, [])
        diff = MAX_NODES_TO_REQUEST - len(sent_nodes)

        if diff <= 0 or self.infohash_to_responses.get(infohash, 0) > MAX_RESPONSES_TO_WAIT:
            return

        requests = []
        for (_node_id, node_ip, node_port) in decoded_nodes[:diff]:
            ip_port_str = f'{node_ip}:{node_port}'
            if ip_port_str not in sent_nodes:
                await asyncio.sleep(0.01)
                await self.send_dht_get_peers_request(node_ip, node_port, infohash)
                sent_nodes.append(ip_port_str)
                self.infohash_to_nodes[infohash] = sent_nodes

    def requesting_bloomfilters(self, transaction_id, infohash):
        """
        Tne libtorrent DHT has sent a get_peers query for an infohash we may be interested in.
        If so, keep track of the transaction and node IDs.
        :param transaction_id: The ID of the query
        :param infohash: The infohash for which the query was sent.
        """
        if infohash in self.lookup_futures:
            self.outstanding[transaction_id] = infohash
        elif transaction_id in self.outstanding:
            # Libtorrent is reusing the transaction_id, and is now using it for a infohash that we're not interested in.
            self.outstanding.pop(transaction_id, None)

    def received_bloomfilters(self, transaction_id, bf_seeds=bytearray(256), bf_peers=bytearray(256)):
        """
        We have received bloom filters from the libtorrent DHT. Register the bloom filters and process them.
        :param transaction_id: The ID of the query for which we are receiving the bloom filter.
        :param bf_seeds: The bloom filter indicating the IP addresses of the seeders.
        :param bf_peers: The bloom filter indicating the IP addresses of the peers (leechers).
        """
        infohash = self.outstanding.get(transaction_id)
        if not infohash:
            self._logger.info("Could not find lookup infohash for incoming BEP33 bloomfilters")
            return

        if infohash not in self.bf_seeders or infohash not in self.bf_peers:
            self._logger.info("Could not find lookup infohash for incoming BEP33 bloomfilters")
            return

        self.bf_seeders[infohash] = dht_utils.combine_bloomfilters(self.bf_seeders[infohash], bf_seeds)
        self.bf_peers[infohash] = dht_utils.combine_bloomfilters(self.bf_peers[infohash], bf_peers)

    async def shutdown(self):
        await self.request_cache.shutdown()
        await self.shutdown_task_manager()
