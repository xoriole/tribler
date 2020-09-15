import os
import time
from asyncio import ensure_future, get_event_loop
from random import randint

# Check if we are running from the root directory
# If not, modify our path so that we can import IPv8
try:
    import ipv8
    del ipv8
except ImportError:
    import __scriptpath__  # noqa: F401

from cuckoopy import CuckooFilter

from ipv8.configuration import get_default_configuration
from ipv8.lazy_community import lazy_wrapper

from ipv8_service import IPv8, _COMMUNITIES

from tribler_core.modules.popularity.payload import TorrentsHealthPayload
from tribler_core.modules.popularity.popularity_community import PopularityCommunity


INSTANCES = []
START_TIME = time.time()
RESULTS = []
LIFETIME = int(os.environ.get('EXP_LIFETIME', '60'))  # How long to run this experiment?


class MyCommunity(PopularityCommunity):

    def __init__(self, *args, **kwargs):
        super(MyCommunity, self).__init__(*args, **kwargs)

        self.peers_filter = CuckooFilter(capacity=10000, bucket_size=4, fingerprint_size=1)
        self.torrents_filter = CuckooFilter(capacity=10000, bucket_size=4, fingerprint_size=1)

        self.unique_peers = 0
        self.all_torrents = 0
        self.unique_torrents = 0
        self.duplicate_torrents = 0
        self.message_count = 0

        self.max_seeders = 0
        self.max_leechers = 0
        self.sum_seeders = 0
        self.sum_leechers = 0
        self.avg_seeders = 0
        self.avg_leechers = 0
        self.zero_seeders = 0

    def started(self):
        def check_peers():
            global INSTANCES, START_TIME, RESULTS

            diff = time.time() - START_TIME
            RESULTS.append([int(diff), len(self.get_peers()), self.unique_peers, self.message_count,
                            self.all_torrents, self.unique_torrents, self.duplicate_torrents,
                            self.max_seeders, self.avg_seeders, self.zero_seeders])

            if self.get_peers():
                for peer in self.get_peers():
                    if not self.peers_filter.contains(str(peer.mid)):
                        self.unique_peers += 1
                        self.peers_filter.insert(str(peer.mid))

                if diff > LIFETIME:
                    async def shutdown():
                        for instance in INSTANCES:
                            await instance.stop(False)
                        get_event_loop().stop()
                    ensure_future(shutdown())

                print(f"time: {int(diff)}, "
                      f"peers (connected): {len(self.get_peers())}, "
                      f"peers (unique): {self.unique_peers}, "
                      f"messages: {self.message_count}, "
                      f"torrents (all): {self.all_torrents}, "
                      f"torrents (unique): {self.unique_torrents}, "
                      f"torrents (dup): {self.duplicate_torrents}, "
                      f"seeders (max): {self.max_seeders}, "
                      f"seeders (avg): {self.avg_seeders}, "
                      f"seeders (zero): {self.zero_seeders}")

        self.register_task("check_peers", check_peers, interval=5, delay=0)

    @lazy_wrapper(TorrentsHealthPayload)
    async def on_torrents_health(self, _, payload):
        all_torrents = payload.random_torrents + payload.torrents_checked
        self.message_count += 1
        self.all_torrents += len(all_torrents)

        for infohash, seeders, leechers, last_check in all_torrents:
            infohash_str = str(infohash)

            if self.torrents_filter.contains(infohash_str):
                self.duplicate_torrents += 1
            else:
                self.unique_torrents += 1

                if self.torrents_filter.insert(infohash_str):
                    if seeders > self.max_seeders:
                        self.max_seeders = seeders
                    if leechers > self.max_leechers:
                        self.max_leechers = leechers
                    if seeders == 0:
                        self.zero_seeders += 1

                    self.sum_seeders += seeders
                    self.sum_leechers += leechers

                    self.avg_seeders = self.sum_seeders / self.unique_torrents
                    self.avg_leechers = self.sum_leechers / self.unique_torrents


_COMMUNITIES['MyCommunity'] = MyCommunity


async def start_communities():
    configuration = get_default_configuration()
    configuration['keys'] = [{
        'alias': "my peer",
        'generation': u"medium",
        'file': u"ec.pem"
    }]
    configuration['port'] = 12000 + randint(0, 10000)
    configuration['overlays'] = [{
        'class': 'MyCommunity',
        'key': "my peer",
        'walkers': [{
            'strategy': "RandomWalk",
            'peers': 1000,
            'init': {
                'timeout': 3.0
            }
        }],
        'initialize': {'metadata_store': None, 'torrent_checker': None},
        'on_start': [('started', )]
    }]

    ipv8 = IPv8(configuration)
    await ipv8.start()
    INSTANCES.append(ipv8)


ensure_future(start_communities())
get_event_loop().run_forever()

with open('popularity.txt', 'w') as f:
    f.write('TIME, PEERS_CONNECTED, PEERS_UNIQUE, MESSAGES, TORRENTS_ALL, TORRENTS_UNIQUE, TORRENTS_DUPLICATES, SEEDEERS_MAX, SEEDERS_AVG, SEEDERS_ZERO')
    for (diff, peers_connected, peers_unique, message, torrents_all, torrents_unique, torrents_duplicate, seeders_max, seeders_avg, seeders_zero) in RESULTS:
        f.write('\n%.2f, %d, %d, %d, %d, %d, %d, %d, %.2f, %d' % (diff, peers_connected, peers_unique, message, torrents_all, torrents_unique, torrents_duplicate, seeders_max, seeders_avg, seeders_zero))
