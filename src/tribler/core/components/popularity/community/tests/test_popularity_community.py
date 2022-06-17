import logging
import os
import random
import time
from random import randint
from types import SimpleNamespace
from unittest.mock import Mock

from ipv8.keyvault.crypto import default_eccrypto
from ipv8.test.base import TestBase
from ipv8.test.mocking.ipv8 import MockIPv8

from pony.orm import db_session, count

import pytest

from tribler.core.components.metadata_store.db.store import MetadataStore
from tribler.core.components.metadata_store.remote_query_community.settings import RemoteQueryCommunitySettings
from tribler.core.components.popularity.community.filter import PerPeerTorrentFilter
from tribler.core.components.popularity.community.payload import TorrentsHealthPayload
from tribler.core.components.popularity.community.popularity_community import PopularityCommunity
from tribler.core.components.popularity.community.tests.test_filter import get_random_peers
from tribler.core.tests.tools.base_test import MockObject
from tribler.core.utilities.path_util import Path
from tribler.core.utilities.utilities import random_infohash


class TestPopularityCommunity(TestBase):
    NUM_NODES = 2

    def setUp(self):
        super().setUp()
        self.count = 0
        self.metadata_store_set = set()
        self.initialize(PopularityCommunity, self.NUM_NODES)

    async def tearDown(self):
        for metadata_store in self.metadata_store_set:
            metadata_store.shutdown()
        await super().tearDown()

    def create_node(self, *args, **kwargs):
        mds = MetadataStore(Path(self.temporary_directory()) / f"{self.count}",
                            Path(self.temporary_directory()),
                            default_eccrypto.generate_key("curve25519"))
        self.metadata_store_set.add(mds)
        torrent_checker = MockObject()
        torrent_checker.torrents_checked = set()

        self.count += 1

        rqc_settings = RemoteQueryCommunitySettings()
        return MockIPv8("curve25519", PopularityCommunity, metadata_store=mds,
                        torrent_checker=torrent_checker,
                        rqc_settings=rqc_settings
                        )

    @db_session
    def fill_database(self, metadata_store, last_check_now=False):
        for torrent_ind in range(5):
            last_check = int(time.time()) if last_check_now else 0
            metadata_store.TorrentState(
                infohash=str(torrent_ind).encode() * 20, seeders=torrent_ind + 1, last_check=last_check)

    async def init_first_node_and_gossip(self, checked_torrent_info, deliver_timeout=.1):
        self.nodes[0].overlay.torrent_checker.torrents_checked.add(checked_torrent_info)
        await self.introduce_nodes()

        self.nodes[0].overlay.gossip_random_torrents_health()

        await self.deliver_messages(timeout=deliver_timeout)

    async def test_torrents_health_gossip(self):
        """
        Test whether torrent health information is correctly gossiped around
        """
        checked_torrent_info = (b'a' * 20, 200, 0, int(time.time()))
        node0_db = self.nodes[0].overlay.mds.TorrentState
        node1_db2 = self.nodes[1].overlay.mds.TorrentState

        with db_session:
            assert node0_db.select().count() == 0
            assert node1_db2.select().count() == 0

        await self.init_first_node_and_gossip(checked_torrent_info)

        # Check whether node 1 has new torrent health information
        with db_session:
            torrent = node1_db2.select().first()
            assert torrent.infohash == checked_torrent_info[0]
            assert torrent.seeders == checked_torrent_info[1]
            assert torrent.leechers == checked_torrent_info[2]
            assert torrent.last_check == checked_torrent_info[3]

    async def test_torrents_health_gossip_with_filter(self):
        """
        Test whether new torrent health information is correctly gossiped to the same peer each time and are not
        repeated.
        """
        checked_torrent_info = [(os.urandom(20), random.randint(1, 100), random.randint(0, 100), int(time.time()))
                                for _ in range(10)]

        node0_db = self.nodes[0].overlay.mds.TorrentState
        node1_db2 = self.nodes[1].overlay.mds.TorrentState

        with db_session:
            assert node0_db.select().count() == 0
            assert node1_db2.select().count() == 0

        # Assuming node 0 has 100 checked torrents
        checked_torrents = [(os.urandom(20),
                             random.randint(1, 100),
                             random.randint(0, 100),
                             int(time.time())
                             ) for _ in range(100)]
        self.nodes[0].overlay.torrent_checker.torrents_checked.update(checked_torrents)

        await self.introduce_nodes()

        print(f"torrent info: {checked_torrent_info}")
        results = self.nodes[0].overlay.filter_torrents_already_sent_to_peer(self.nodes[1].my_peer, checked_torrent_info)
        print(f"before sending : {results}")

        self.nodes[0].overlay.gossip_random_torrents_health()

        await self.deliver_messages(timeout=0.1)
        # await self.init_first_node_and_gossip(checked_torrent_info)

        print(f"torrent info: {checked_torrent_info}")
        results = self.nodes[0].overlay.filter_torrents_already_sent_to_peer(self.nodes[1].my_peer, checked_torrent_info)
        print(f"after sending : {results}")

        # Check whether node 1 has new torrent health information
        with db_session:
            counts = count(t for t in node1_db2)
            print(f"count: {counts}")


    async def test_torrents_health_gossip_multiple(self):
        """
        Test whether torrent health information is correctly gossiped around
        """
        # torrent structure is (infohash, seeders, leechers, last_check)
        dead_torrents = {(random_infohash(), 0, randint(1, 10), int(time.time()))
                         for _ in range(10)}
        alive_torrents = {(random_infohash(), randint(1, 10), randint(1, 10), int(time.time()))
                          for _ in range(PopularityCommunity.GOSSIP_RANDOM_TORRENT_COUNT)}
        top_popular_torrents = {(random_infohash(), randint(11, 100), randint(1, 10), int(time.time()))
                                for _ in range(PopularityCommunity.GOSSIP_POPULAR_TORRENT_COUNT)}

        all_checked_torrents = dead_torrents | alive_torrents | top_popular_torrents

        node0_db = self.nodes[0].overlay.mds.TorrentState
        node1_db = self.nodes[1].overlay.mds.TorrentState

        with db_session:
            assert node0_db.select().count() == 0
            assert node1_db.select().count() == 0

        for torrent_info in all_checked_torrents:
            self.nodes[0].overlay.torrent_checker.torrents_checked.add(torrent_info)

        await self.introduce_nodes()

        # Node 0 gossips a message with random torrents health information.
        # Random torrents can include popular torrents as well.
        self.nodes[0].overlay.gossip_random_torrents_health()
        await self.deliver_messages(timeout=0.1)

        # Check whether node 1 has received all random torrent health information
        with db_session:
            assert node1_db.select().count() == PopularityCommunity.GOSSIP_RANDOM_TORRENT_COUNT

        # Node 0 now gossips a message with popular torrents health information
        # This gossipping happens at a different interval than random torrent.
        # That is not checked here.
        self.nodes[0].overlay.gossip_popular_torrents_health()
        await self.deliver_messages(timeout=0.1)

        # Check whether node 1 has received all popular torrent health information.
        # This is checked by checking the existence of all popular torrents infohashes.
        with db_session:
            # Check that gossipped popular torrents exist in the database
            for infohash, _, _, _ in top_popular_torrents:
                assert node1_db.get(infohash=infohash) is not None

            # Since the first message of random torrent health information could
            # include popular torrents, the total number of torrents might not be
            # the sum of all torrents shared.
            count = node1_db.select().count()
            assert count >= max(PopularityCommunity.GOSSIP_RANDOM_TORRENT_COUNT,
                                PopularityCommunity.GOSSIP_POPULAR_TORRENT_COUNT)
            assert count <= PopularityCommunity.GOSSIP_RANDOM_TORRENT_COUNT \
                + PopularityCommunity.GOSSIP_POPULAR_TORRENT_COUNT

    async def test_torrents_health_update(self):
        """
        Test updating the local torrent health information from network
        """
        self.fill_database(self.nodes[1].overlay.mds)

        checked_torrent_info = (b'0' * 20, 200, 0, int(time.time()))
        await self.init_first_node_and_gossip(checked_torrent_info, deliver_timeout=0.5)

        # Check whether node 1 has new torrent health information
        with db_session:
            state = self.nodes[1].overlay.mds.TorrentState.get(infohash=b'0' * 20)
            self.assertIsNot(state.last_check, 0)

    async def test_unknown_torrent_query_back(self):
        """
        Test querying sender for metadata upon receiving an unknown torrent
        """

        infohash = b'1' * 20
        with db_session:
            self.nodes[0].overlay.mds.TorrentMetadata(infohash=infohash)
        await self.init_first_node_and_gossip((infohash, 200, 0, int(time.time())))
        with db_session:
            assert self.nodes[1].overlay.mds.TorrentMetadata.get()

    async def test_skip_torrent_query_back_for_known_torrent(self):
        # Test that we _don't_ send the query if we already know about the infohash
        infohash = b'1' * 20
        with db_session:
            self.nodes[0].overlay.mds.TorrentMetadata(infohash=infohash)
            self.nodes[1].overlay.mds.TorrentMetadata(infohash=infohash)
        self.nodes[1].overlay.send_remote_select = Mock()
        await self.init_first_node_and_gossip((infohash, 200, 0, int(time.time())))
        self.nodes[1].overlay.send_remote_select.assert_not_called()


async def test_select_torrents_to_gossip_small_list():
    torrents = [
        # infohash, seeders, leechers, last_check
        (b'0' * 20, 0, 0, None),
        (b'1' * 20, 1, 0, None),
        (b'1' * 20, 2, 0, None),
    ]

    popular, rand = PopularityCommunity.select_torrents_to_gossip(set(torrents))
    assert torrents[1] in popular
    assert torrents[2] in popular
    assert not rand


async def test_select_torrents_to_gossip_big_list():
    # torrent structure is (infohash, seeders, leechers, last_check)
    dead_torrents = {(random_infohash(), 0, randint(1, 10), None)
                     for _ in range(10)}

    alive_torrents = {(random_infohash(), randint(1, 10), randint(1, 10), None)
                      for _ in range(10)}

    top5_popular_torrents = {(random_infohash(), randint(11, 100), randint(1, 10), None)
                             for _ in range(PopularityCommunity.GOSSIP_POPULAR_TORRENT_COUNT)}

    all_torrents = dead_torrents | alive_torrents | top5_popular_torrents

    popular, rand = PopularityCommunity.select_torrents_to_gossip(all_torrents)
    assert len(popular) <= PopularityCommunity.GOSSIP_POPULAR_TORRENT_COUNT
    assert popular == top5_popular_torrents

    assert len(rand) <= PopularityCommunity.GOSSIP_RANDOM_TORRENT_COUNT
    assert rand <= alive_torrents


async def test_no_alive_torrents():
    torrents = {(random_infohash(), 0, randint(1, 10), None)
                for _ in range(10)}

    popular, rand = PopularityCommunity.select_torrents_to_gossip(torrents)
    assert not popular
    assert not rand


# pylint: disable=super-init-not-called
async def test_gossip_torrents_health_returns():
    peers = get_random_peers(1)

    class MockPopularityCommunity(PopularityCommunity):
        def __init__(self):
            self.is_ez_send_has_been_called = False
            self.is_ez_send_has_been_called_with_payload = False
            self.torrent_checker = None
            self.logger = logging.getLogger()
            self.per_peer_torrent_filter = PerPeerTorrentFilter()

        def ez_send(self, peer, *payloads, **kwargs):
            self.is_ez_send_has_been_called = True
            for payload in payloads:
                if isinstance(payload, TorrentsHealthPayload):
                    print(payload)
            print(payloads)

        def get_peers(self):
            return peers

    community = MockPopularityCommunity()

    community.gossip_random_torrents_health()
    assert not community.torrent_checker
    assert not community.is_ez_send_has_been_called

    community.torrent_checker = SimpleNamespace()
    community.torrent_checker.torrents_checked = None
    community.gossip_random_torrents_health()
    assert not community.is_ez_send_has_been_called

    community.torrent_checker.torrents_checked = {(b'0' * 20, 0, 0, None),
                                                  (b'1' * 20, 0, 0, None)}

    community.gossip_random_torrents_health()
    assert not community.is_ez_send_has_been_called

    community.torrent_checker.torrents_checked = {(b'0' * 20, 1, 0, None),
                                                  (b'1' * 20, 1, 0, None)}
    community.gossip_random_torrents_health()
    assert community.is_ez_send_has_been_called

    community.gossip_random_torrents_health()
    assert community.is_ez_send_has_been_called
