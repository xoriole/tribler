import time
from asyncio import Future

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import HealthInfo
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht import dht_utils
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.dht_response import DhtResponse
from tribler.core.utilities.async_group.async_group import AsyncGroup

MAX_NODES_TO_REQUEST = 1000
MAX_RESPONSES_TO_WAIT = 100


class DhtRequestSession:
    def __init__(self, infohash):
        self.infohash = infohash

        self.requested_nodes = set()

        self.bf_seeders = bytearray(256)
        self.bf_peers = bytearray(256)
        self.num_responses = 0

        self.future = Future()

        self.requests = AsyncGroup()

    def add_request_to_session(self, request):
        self.requests.add_task(request)

    def add_response(self, dht_response: DhtResponse):
        bf_seeders, bf_leechers = dht_response.bloom_filters
        self.bf_seeders = dht_utils.combine_bloomfilters(self.bf_seeders, bf_seeders)
        self.bf_peers = dht_utils.combine_bloomfilters(self.bf_peers, bf_leechers)
        self.num_responses += 1
        print(f"num responses: {self.num_responses}, is zero: {bf_seeders == bytearray(256)}")

    def get_health_info(self):
        seeders = dht_utils.get_size_from_bloomfilter(self.bf_seeders)
        peers = dht_utils.get_size_from_bloomfilter(self.bf_peers)

        health = HealthInfo(
            infohash=self.infohash,
            last_check=int(time.time()),
            seeders=seeders,
            leechers=peers,
            self_checked=True
        )

        print(f"num responses: {self.num_responses}, num nodes: {len(self.requested_nodes)}")
        return health

    def max_nodes_requested(self):
        return len(self.requested_nodes) >= MAX_NODES_TO_REQUEST

    def max_responses_received(self):
        return self.num_responses >= MAX_RESPONSES_TO_WAIT

    async def send_response(self):
        await self.requests.cancel()

        if not self.future.done():
            self.future.set_result(self.get_health_info())
