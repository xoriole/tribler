import heapq
import random
from binascii import unhexlify

from cuckoo.filter import ScalableCuckooFilter

from ipv8.lazy_community import lazy_wrapper

from pony.orm import db_session

from tribler.core.components.metadata_store.remote_query_community.remote_query_community import RemoteQueryCommunity
from tribler.core.components.popularity.community.filter_community_mixin import FilterCommunityMixin
from tribler.core.components.popularity.community.payload import TorrentsHealthPayload
from tribler.core.components.popularity.community.version_community_mixin import VersionCommunityMixin
from tribler.core.utilities.unicode import hexlify


class PopularityCommunity(RemoteQueryCommunity, VersionCommunityMixin, FilterCommunityMixin):
    """
    Community for disseminating the content across the network.

    Every 2 minutes it gossips 10 popular torrents and
    every 5 seconds it gossips 10 random torrents to
    a random peer.

    Gossiping is for checked torrents only.
    """
    GOSSIP_INTERVAL_FOR_POPULAR_TORRENTS = 120  # seconds
    GOSSIP_INTERVAL_FOR_RANDOM_TORRENTS = 5  # seconds
    GOSSIP_POPULAR_TORRENT_COUNT = 10
    GOSSIP_RANDOM_TORRENT_COUNT = 10

    # Filter parameters
    # FILTER_CAPACITY = 1000
    # FILTER_ERROR_RATE = 0.1

    community_id = unhexlify('9aca62f878969c437da9844cba29a134917e1648')

    def __init__(self, *args, torrent_checker=None, **kwargs):
        # Creating a separate instance of Network for this community to find more peers
        super().__init__(*args, **kwargs)
        FilterCommunityMixin.__init__(self)

        self.torrent_checker = torrent_checker

        self.add_message_handler(TorrentsHealthPayload, self.on_torrents_health)

        self.logger.info('Popularity Community initialized (peer mid %s)',
                         hexlify(self.my_peer.mid))
        self.register_task("gossip_popular_torrents", self.gossip_popular_torrents_health,
                           interval=PopularityCommunity.GOSSIP_INTERVAL_FOR_POPULAR_TORRENTS)
        self.register_task("gossip_random_torrents", self.gossip_random_torrents_health,
                           interval=PopularityCommunity.GOSSIP_INTERVAL_FOR_RANDOM_TORRENTS)
        # self.register_task("update_filter", self.update_filter, interval=5)

        # Init version community message handlers
        self.init_version_community()

        # # Init filters
        # self.peer_torrents_filters = {}

    def init_filters(self):
        pass

    # def update_filter(self):
    #     pass

    @staticmethod
    def select_torrents_to_gossip(torrents, include_popular=True, include_random=True) -> (set, set):
        """ Select torrents to gossip.

        Select top 5 popular torrents, and 5 random torrents.

        Args:
            torrents: set of tuples (infohash, seeders, leechers, last_check)
            include_popular: If True, popular torrents based on seeder count are selected
            include_random: If True, torrents are randomly selected

        Returns:
            tuple (set(popular), set(random))

        """
        # select the torrents that have seeders
        alive = {(_, seeders, *rest) for (_, seeders, *rest) in torrents
                 if seeders > 0}
        if not alive:
            return {}, {}

        print(f"alive torrents: {len(alive)}")

        popular, rand = set(), set()

        # select most popular from alive torrents, using `seeders` as a key
        if include_popular:
            count = PopularityCommunity.GOSSIP_POPULAR_TORRENT_COUNT
            popular = set(heapq.nlargest(count, alive, key=lambda t: t[1]))

        # select random torrents from the rest of the list
        if include_random:
            rest = alive - popular
            count = min(PopularityCommunity.GOSSIP_RANDOM_TORRENT_COUNT, len(rest))
            rand = set(random.sample(list(rest), count))

        return popular, rand

    def _gossip_torrents_health(self, include_popular=True, include_random=True):
        """
        Gossip torrent health information to another peer.
        """
        if not self.get_peers() or not self.torrent_checker:
            return

        checked = self.torrent_checker.torrents_checked
        if not checked:
            return

        random_peer = random.choice(self.get_peers())
        filtered_checked = self.filter_torrents_for_peer(random_peer, checked)

        popular, rand = PopularityCommunity.select_torrents_to_gossip(checked,
                                                                      include_popular=include_popular,
                                                                      include_random=include_random)
        if not popular and not rand:
            self.logger.debug(f'No torrents to gossip. Checked torrents count: '
                             f'{len(checked)}')
            return

        self.logger.info(
            f'Gossip torrent health information for {len(rand)}'
            f' random torrents and {len(popular)} popular torrents')

        self.ez_send(random_peer, TorrentsHealthPayload.create(rand, popular))
        self.update_filter(random_peer, rand, popular)

    def filter_torrents_for_peer(self, peer, torrents):
        print(f"--- filter torrents per peer[{peer.address.ip}:{peer.address.port}] ----")
        print(f" total torrents checked: {len(torrents)}")
        filter = self.get_filter(peer)
        output = []
        count = 0
        for torrent in torrents:
            infohash, seeders, leechers, last_check = torrent
            count += 1
            if seeders < 1:
                continue
            if seeders > 0 and not filter.contains(infohash):
                output.append(torrent)
            else:
                print(f"[{count}] torrent already exists or dead: {hexlify(infohash)}")
        print(f" filtered torrents: {len(output)}")
        return set(output)

    def update_filter(self, peer, random_torrents, popular_torrents):
        peer_mid = str(peer.mid)
        infohashes = [infohash for infohash, seeders, leechers, last_check in random_torrents | popular_torrents]
        self.add_to_filter(peer, infohashes)

    def prune_filter(self):
        pass

    def gossip_random_torrents_health(self):
        """
        Gossip random torrent health information to another peer.
        """
        self._gossip_torrents_health(include_popular=False, include_random=True)

    def gossip_popular_torrents_health(self):
        """
        Gossip popular torrent health information to another peer.
        """
        self._gossip_torrents_health(include_popular=True, include_random=False)

    @lazy_wrapper(TorrentsHealthPayload)
    async def on_torrents_health(self, peer, payload):
        self.logger.debug(f"Received torrent health information for "
                         f"{len(payload.torrents_checked)} popular torrents and"
                         f" {len(payload.random_torrents)} random torrents")

        torrents = payload.random_torrents + payload.torrents_checked

        for infohash in await self.mds.run_threaded(self.process_torrents_health, torrents):
            # Get a single result per infohash to avoid duplicates
            self.send_remote_select(peer=peer, infohash=infohash, last=1)

    @db_session
    def process_torrents_health(self, torrent_healths):
        infohashes_to_resolve = set()
        for infohash, seeders, leechers, last_check in torrent_healths:
            added = self.mds.process_torrent_health(infohash, seeders, leechers, last_check)
            if added:
                infohashes_to_resolve.add(infohash)
        return infohashes_to_resolve
