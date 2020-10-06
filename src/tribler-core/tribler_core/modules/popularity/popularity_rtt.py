import math
import os
import random
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

from ipv8.lazy_community import lazy_wrapper_wd

from tribler_core.modules.popularity.payload import TorrentsHealthPayload
from tribler_core.modules.popularity.popularity_community import PopularityCommunity


START_TIME = time.time()
RESULTS = []
LIFETIME = int(os.environ.get('EXP_LIFETIME', '60'))  # How long to run this experiment?
HEALTH_CHECK_PERCENTAGE = float(os.environ.get('HEALTH_CHECK_PERCENTAGE', '0.5'))
HEALTH_CHECK_THRESHOLD = int(os.environ.get('HEALTH_CHECK_THRESHOLD', '10'))


class PopularityCommunityObserver(PopularityCommunity):

    def __init__(self, *args, **kwargs):
        super(PopularityCommunityObserver, self).__init__(*args, **kwargs)

        self.peers_filter = CuckooFilter(capacity=10000, bucket_size=4, fingerprint_size=1)
        self.torrents_filter = CuckooFilter(capacity=10000, bucket_size=4, fingerprint_size=1)

        self.unique_peers = 0
        self.num_torrents = 0
        self.unique_torrents = 0
        self.duplicate_torrents = 0
        self.message_count = 0
        self.bandwidth_received = 0

        self.max_seeders = 0
        self.max_leechers = 0
        self.sum_seeders = 0
        self.sum_leechers = 0
        self.avg_seeders = 0
        self.avg_leechers = 0
        self.zero_seeders = 0

        self.total_dht_checks = 0
        self.failed_dht_checks = 0
        self.success_dht_checks = 0
        self.dht_dead_torrents = 0
        self.dht_alive_torrents = 0
        self.dht_fresh_torrents = 0
        self.dht_health_diff = 0


        self.on_start()

    def on_start(self):
        def check_peers():
            global START_TIME, RESULTS

            diff = time.time() - START_TIME
            RESULTS.append([int(diff), len(self.get_peers()), self.unique_peers, self.message_count,
                            self.num_torrents, self.unique_torrents, self.duplicate_torrents,
                            self.max_seeders, self.avg_seeders, self.zero_seeders, self.bandwidth_received,
                            self.total_dht_checks, self.failed_dht_checks, self.success_dht_checks,
                            self.dht_dead_torrents, self.dht_alive_torrents, self.dht_fresh_torrents,
                            self.dht_health_diff])

            if self.get_peers():
                for peer in self.get_peers():
                    if not self.peers_filter.contains(str(peer.mid)):
                        self.unique_peers += 1
                        self.peers_filter.insert(str(peer.mid))

                if diff > LIFETIME:
                    async def shutdown():
                        self.on_stop()
                        get_event_loop().stop()
                    ensure_future(shutdown())

                print(f"time: {int(diff)}, "
                      f"peers (connected): {len(self.get_peers())}, "
                      f"peers (unique): {self.unique_peers}, "
                      f"messages: {self.message_count}, "
                      f"bandwidth: {self.bandwidth_received}, \n  "
                      f"torrents (all): {self.num_torrents}, "
                      f"torrents (unique): {self.unique_torrents}, "
                      f"torrents (dup): {self.duplicate_torrents}, \n  "
                      f"seeders (max): {self.max_seeders}, "
                      f"seeders (avg): {self.avg_seeders}, "
                      f"seeders (zero): {self.zero_seeders}, \n  "
                      f"dht (total): {self.total_dht_checks}, "
                      f"dht (failed): {self.failed_dht_checks}, "
                      f"dht (success): {self.success_dht_checks}, "
                      f"dht (dead): {self.dht_dead_torrents}, "
                      f"dht (alive): {self.dht_alive_torrents}, "
                      f"dht (fresh): {self.dht_fresh_torrents}, "
                      f"dht (fresh): {self.dht_health_diff}")

        self.register_task("check_peers", check_peers, interval=5, delay=0)

    def on_stop(self):
        with open('popularity.txt', 'w') as f:
            f.write('TIME, PEERS_CONNECTED, PEERS_UNIQUE, MESSAGES, TORRENTS_ALL, TORRENTS_UNIQUE, TORRENTS_DUPLICATES,'
                    ' SEEDEERS_MAX, SEEDERS_AVG, SEEDERS_ZERO, BANDWIDTH, DHT_TOTAL, DHT_FAILED, DHT_SUCCESS,'
                    ' DHT_DEAD, DHT_ALIVE, DHT_FRESH, DHT_DIFF')
            for (diff, peers_connected, peers_unique, message, torrents_all, torrents_unique, torrents_duplicate,
                 seeders_max, seeders_avg, seeders_zero, bandwidth, dht_total, dht_failed, dht_success,
                 dht_dead, dht_alive, dht_fresh, dht_diff) in RESULTS:
                f.write('\n%.2f, %d, %d, %d, %d, %d, %d, %d, %.2f, %d, %.2f, %d, %d, %d, %d, %d, %d, %d'
                        % (diff, peers_connected, peers_unique, message, torrents_all, torrents_unique,
                           torrents_duplicate, seeders_max, seeders_avg, seeders_zero, bandwidth,
                           dht_total, dht_failed, dht_success, dht_dead, dht_alive, dht_fresh, dht_diff))

    @lazy_wrapper_wd(TorrentsHealthPayload)
    async def on_torrents_health(self, _, payload, data):
        all_torrents = payload.random_torrents + payload.torrents_checked
        self.num_torrents += len(all_torrents)
        self.message_count += 1
        self.bandwidth_received += len(data)

        chosen_index = -1
        if random.random() < HEALTH_CHECK_PERCENTAGE:
            chosen_index = random.randint(0, len(all_torrents))

        for idx, (infohash, seeders, leechers, last_check) in enumerate(all_torrents):
            infohash_str = str(infohash)

            if idx == chosen_index:
                if seeders == 0:
                    chosen_index += 1
                else:
                    await self.verify_health(infohash, seeders, leechers)

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

    async def verify_health(self, infohash, seeders, leechers):
        self.total_dht_checks += 1
        health_data = await self.torrent_checker.check_torrent_health(infohash, scrape_now=False)
        print(f"health_data received: {health_data}")

        if not health_data or ('DHT' in health_data and 'error' in health_data['DHT']):
            self.failed_dht_checks += 1
            return

        self.success_dht_checks += 1

        actual_seeders = health_data['DHT']['seeders']
        actual_leechers = health_data['DHT']['leechers']

        if actual_seeders == 0 and actual_leechers == 0:
            self.dht_dead_torrents += 1
            return
        self.dht_alive_torrents += 1

        if seeders - actual_seeders <= HEALTH_CHECK_THRESHOLD:
            self.dht_fresh_torrents += 1

        self.dht_health_diff += seeders - actual_seeders
