import argparse
import asyncio
import csv
import logging
import os
import random
import socket
import time
from asyncio import Future
from binascii import hexlify, unhexlify
from pathlib import Path

from ipv8 import community

from ipv8.peer import Peer
from ipv8.peerdiscovery.discovery import RandomWalk

from pony.orm import count, db_session

import sentry_sdk

from experiment.tool.tiny_tribler_service import TinyTriblerService
from ipv8.taskmanager import TaskManager
from tribler_core.modules.metadata_store.orm_bindings.channel_node import NEW

from tribler_core.modules.popularity.popularity_community import PopularityCommunity
from tribler_core.utilities.osutils import get_root_state_directory

_logger = logging.getLogger(__name__)

TARGET_PEERS_COUNT = 20  # Tribler uses this number for walking strategy

sentry_sdk.init(
    os.environ.get('SENTRY_URL'),
    traces_sample_rate=1.0
)
DEAD_TORRENT_RATE = 0.01
NUM_INITIAL_TORRENTS = 100


class FakeDHTHealthManager(TaskManager):
    """
    This is a fake DHT health manager which gets its file information from a local source.
    """

    def __init__(self):
        TaskManager.__init__(self)
        self._logger = logging.getLogger(self.__class__.__name__)
        self.torrent_healths = {}  # Dictionary from infohash -> (seeders, leechers)

    def get_health(self, infohash, **_):
        self._logger.info("Getting health info for infohash %s", hexlify(infohash))
        print(f"Getting health info for infohash {hexlify(infohash)}")
        future = Future()

        seeders, peers = 0, 0
        if infohash in self.torrent_healths:
            seeders, peers = self.torrent_healths[infohash]

        health_response = {
            "DHT": [{
                "infohash": hexlify(infohash),
                "seeders": seeders,
                "leechers": peers
            }]
        }

        self.register_task("lookup_%s" % hexlify(infohash), future.set_result,
                           health_response, delay=random.randint(1, 7))
        return future



class ObservablePopularityCommunity(PopularityCommunity):

    community_id = unhexlify('9aca62f878969c437da9844cba29a134917e1649')

    def __init__(self, interval_in_sec, output_file_path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._logger = logging.getLogger(self.__class__.__name__)

        self._start_time = time.time()

        self._interval_in_sec = interval_in_sec
        self._output_file_path = output_file_path

        self.dht_health_manager = FakeDHTHealthManager()

        self._csv_file, self._csv_writer = self.init_csv_writer()

        self.register_task("check", self.check, interval=self._interval_in_sec)
        # self.register_task("init_random_torrents", self.init_random_torrents, interval=self._interval_in_sec, delay=5)

        print(f"*** Initializing popularity community ***")
        # self.init_random_torrents()
        # print(f"*** Finished inserting {NUM_INITIAL_TORRENTS} torrents to the local database")

    def __del__(self):
        if self._csv_file:
            self._csv_file.close()

    def init_csv_writer(self):
        csv_file = open(self._output_file_path, 'w')
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['time_in_sec', 'total', 'alive'])
        return csv_file, csv_writer

    @db_session
    def get_torrents_info_tuple(self):
        return count(ts for ts in self.metadata_store.TorrentState), \
               count(ts for ts in self.metadata_store.TorrentState if ts.seeders > 0)

    def check(self):
        num_peers = len(self.get_peers())
        time_since_start = time.time() - self._start_time
        torrents_total, torrents_with_seeders = self.get_torrents_info_tuple()

        print(f"Time: {time_since_start:.0f}s, peers: {num_peers}, total: {torrents_total}, live: {torrents_with_seeders}")
        # print(f"default trackers: {community._DNS_ADDRESSES}, {community._DEFAULT_ADDRESSES}")
        self._logger.info(f"Time: {time_since_start:.0f}s, peers: {num_peers}, total: {torrents_total}, live: {torrents_with_seeders}")
        self._csv_writer.writerow([f"{time_since_start:.0f}", torrents_total, torrents_with_seeders])
        self._csv_file.flush()
        # print(f"default dns: {community._DNS_ADDRESSES}, address: {community._DEFAULT_ADDRESSES}")
        # for peer in self.get_peers():
        #     print(f"peer: {peer}")


class Service(TinyTriblerService):
    def __init__(self, interval_in_sec, output_file_path, timeout_in_sec, working_dir, config_path):
        super().__init__(Service.create_config(working_dir, config_path), timeout_in_sec,
                         working_dir, config_path)

        self._interval_in_sec = interval_in_sec
        self._output_file_path = output_file_path
        # self.setup_env_tracker()

    # def setup_env_tracker(self):
    #     # env_tracker = os.environ.get('TRACKERS', None)
    #     # if env_tracker:
    #     community._DEFAULT_ADDRESSES = []
    #     community._DNS_ADDRESSES = [("tracker", 6527)]
    #     pass

    @staticmethod
    def create_config(working_dir, config_path):
        config = TinyTriblerService.create_default_config(working_dir, config_path)

        config.set_libtorrent_enabled(True)
        config.set_ipv8_enabled(True)
        config.set_chant_enabled(True)

        return config

    async def before_tribler_starts(self):
        community._DEFAULT_ADDRESSES = []
        community._DNS_ADDRESSES = [("tracker", 6527)]

    async def on_tribler_started(self):
        await super().on_tribler_started()
        self.logger.info("Tribler started successfully")

        session = self.session
        peer = Peer(session.trustchain_keypair)

        session.dlmgr.dht_health_manager = FakeDHTHealthManager()
        self.init_random_torrents()

        # Create a channel
        # self.session.mds.ChannelMetadata.create_channel('test' + ''.join(str(i) for i in range(100)), 'test')

        session.popularity_community = ObservablePopularityCommunity(self._interval_in_sec,
                                                                     self._output_file_path,
                                                                     peer, session.ipv8.endpoint,
                                                                     session.ipv8.network,
                                                                     metadata_store=session.mds,
                                                                     torrent_checker=session.torrent_checker)

        session.ipv8.overlays.append(session.popularity_community)
        session.ipv8.strategies.append((RandomWalk(session.popularity_community),
                                        TARGET_PEERS_COUNT))

        # Setup a fake DHT checker
        # session.dlmgr.dht_health_manager = session.popularity_community.dht_health_manager

    def init_random_torrents(self):
        print(f"initializing {NUM_INITIAL_TORRENTS} torrents")
        torrent_healths = {}
        with db_session:
            # my_channel = self.metadata_store.ChannelMetadata.get_my_channel()
            for _ in range(NUM_INITIAL_TORRENTS):
                infohash_hex = ''.join(random.choice('0123456789abcdef') for _ in range(40))
                infohash = unhexlify(infohash_hex)
                seeders = 0 if random.random() < DEAD_TORRENT_RATE else random.randint(1, 10000)
                leechers = random.randint(0, 10000)

                new_entry_dict = {
                    "infohash": infohash,
                    "title": infohash_hex,
                    "size": 1024,
                    "status": NEW
                }
                # print(f"inserting torrent {new_entry_dict}")
                metadata = self.session.mds.TorrentMetadata.from_dict(new_entry_dict)
                metadata.health.seeders = seeders
                metadata.health.leechers = leechers
                metadata.health.last_check = int(time.time())

                # Update torrent health
                torrent_healths[infohash] = (seeders, leechers)

            # my_channel.commit_channel_torrent()
            self.session.dlmgr.dht_health_manager.torrent_healths.update(torrent_healths)

        print(f"initialization of {NUM_INITIAL_TORRENTS} torrents completed")

def _parse_argv():
    parser = argparse.ArgumentParser(description='Calculate velocity of initial torrents list filling')

    parser.add_argument('-i', '--interval', type=int, help='how frequently (in sec) the torrent list has been checked',
                        default=10)
    parser.add_argument('-t', '--timeout', type=int, help='a time in sec that the experiment will last',
                        default=1*60)
    parser.add_argument('-f', '--file', type=str, help='result file path (csv)', default='result.csv')
    parser.add_argument('-v', '--verbosity', help='increase output verbosity', action='store_true')

    return parser.parse_args()


def _run_tribler(arguments):

    # state_directory = os.environ.get('STATE_DIR', get_root_state_directory())
    ip_address = socket.gethostbyname(socket.gethostname())
    working_dir = get_root_state_directory(home_dir_postfix=f"tribler-{ip_address}")
    result_file = Path(working_dir, arguments.file)
    print(f"working directory: {working_dir}")

    service = Service(arguments.interval,
                      result_file,
                      arguments.timeout,
                      working_dir=working_dir,
                      config_path=Path('./tribler.conf'))

    loop = asyncio.get_event_loop()
    loop.create_task(service.start_tribler())
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


if __name__ == "__main__":
    _arguments = _parse_argv()
    print(f"Arguments: {_arguments}")

    logging_level = logging.DEBUG if _arguments.verbosity else logging.CRITICAL
    logging.basicConfig(level=logging_level)

    _run_tribler(_arguments)
