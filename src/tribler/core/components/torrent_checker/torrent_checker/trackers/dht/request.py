import logging
import time
from asyncio import Future
from binascii import hexlify

from ipv8.requestcache import NumberCache

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import HealthInfo, TrackerResponse
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht import dht_utils

MAX_NODES_TO_REQUEST = 1000
MAX_RESPONSES_TO_WAIT = 100


class DhtHealthRequest(NumberCache):
    """
    Used to track outstanding dht request messages
    """
    CACHE_PREFIX = "DHT"

    def __init__(self, request_cache, infohash, timeout):
        super().__init__(request_cache, DhtHealthRequest.CACHE_PREFIX, DhtHealthRequest.infohash_to_number(infohash))
        self.logger = logging.getLogger(self.__class__.__name__)

        self.infohash = infohash
        self.timeout = timeout

        self.bf_seeders = bytearray(256)
        self.bf_peers = bytearray(256)

        self.transaction_ids = set()
        self.num_responses_collected = 0

        self.response_future = Future()
        self.register_future(self.response_future)

    @classmethod
    def infohash_to_number(cls, infohash):
        return hash(infohash)

    @property
    def timeout_delay(self):
        return float(self.timeout)

    @property
    def num_responses(self):
        return self.num_responses_collected

    def register_transaction_id(self, transaction_id):
        self.transaction_ids.add(transaction_id)

    def register_bloom_filters(self, transaction_id, bf_seeds, bf_peers):
        if transaction_id not in self.transaction_ids:
            self.logger.error(f"Invalid DHT response; Unexpected TX ID: {hexlify(transaction_id)}")
            return

        self.transaction_ids.remove(transaction_id)
        self.bf_seeders = dht_utils.combine_bloomfilters(self.bf_seeders, bf_seeds)
        self.bf_peers = dht_utils.combine_bloomfilters(self.bf_peers, bf_peers)
        self.num_responses_collected += 1

    def get_health_info(self):
        seeders = dht_utils.get_size_from_bloomfilter(self.bf_seeders)
        peers = dht_utils.get_size_from_bloomfilter(self.bf_peers)

        health = HealthInfo(self.infohash,
                            last_check=int(time.time()),
                            seeders=seeders,
                            leechers=peers,
                            self_checked=True)
        return health

    def on_timeout(self):
        if self.response_future.done():
            return

        health = self.get_health_info()
        tracker_response = TrackerResponse('DHT', [health])
        self.response_future.set_result(tracker_response)
