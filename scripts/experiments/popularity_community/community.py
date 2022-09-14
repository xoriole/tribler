import time
from binascii import unhexlify
from pathlib import Path

from dotenv import load_dotenv
from pony.orm import db_session, desc

from ipv8.lazy_community import lazy_wrapper, lazy_wrapper_wd
from scripts.experiments.common.database import get_database
from scripts.experiments.popularity_community.entities import define_torrent_health_binding, define_peer_binding, \
    define_checked_torrents_binding, define_message_record_binding
from tribler.core.components.popularity.community.payload import TorrentsHealthPayload
from tribler.core.components.popularity.community.popularity_community import PopularityCommunity
from tribler.core.components.popularity.community.version_community_mixin import VersionRequest
from tribler.core.utilities.unicode import hexlify


class CustomPopularityCommunity(PopularityCommunity):
    """
    Custom PopularityCommunity created to run experiments.
    """
    INTERVAL_TO_CHECK_TORRENTS_HEALTH = 5  # seconds

    def __init__(self, *args, **kwargs):
        # Creating a separate instance of Network for this community to find more peers
        super().__init__(*args, **kwargs)

        # define bindings for tables and generate the mappings for the tables
        self.db = get_database()
        self.TorrentHealthEntity = define_torrent_health_binding(self.db)
        self.PeerEntity = define_peer_binding(self.db)
        self.CheckedTorrentsEntity = define_checked_torrents_binding(self.db)
        self.MessageRecordEntity = define_message_record_binding(self.db)
        self.db.generate_mapping(create_tables=True)

        self.register_task("check_one_received_torrent_health", self.check_one_received_torrent_health_from_db,
                           interval=CustomPopularityCommunity.INTERVAL_TO_CHECK_TORRENTS_HEALTH)

    def gossip_random_torrents_health(self):
        """
        No gossipping done on by this node. It is only a community observer.
        """
        pass

    def gossip_popular_torrents_health(self):
        """
        No gossipping done on by this node. It is only a community observer.
        """
        pass

    def add_received_torrent_to_database(self, peer, infohash, seeders, leechers, last_check, received_at):
        hex_infohash = hexlify(infohash)
        self.create_or_update_checked_torrent_entity(hex_infohash, seeders, leechers, last_check)
        self.create_torrent_entity(peer, hex_infohash, seeders, leechers, last_check, received_at)

    def create_or_update_checked_torrent_entity(self, hex_infohash, seeders, leechers, last_check):
        existing_torrent = self.CheckedTorrentsEntity.select(lambda c: c.infohash == hex_infohash).first()
        if not existing_torrent:
            self.CheckedTorrentsEntity(
                infohash=hex_infohash,
                seeders=seeders,
                leechers=leechers,
                last_checked=last_check,
                num_received=1,
                seeders_by_crawler=-1,
                leechers_by_crawler=-1,
                last_checked_by_crawler=-1
            )
        else:
            existing_torrent.seeders = seeders
            existing_torrent.leechers = leechers
            existing_torrent.last_check = last_check
            existing_torrent.num_received += 1

    def create_torrent_entity(self, peer, hex_infohash, seeders, leechers, last_check, received_at):
        self.TorrentHealthEntity(peer_pk=peer.public_key.key_to_bin(),
                                 peer_ip=peer.address.ip,
                                 peer_port=peer.address.port,
                                 received_at=received_at,
                                 infohash=hex_infohash,
                                 seeders=seeders,
                                 leechers=leechers,
                                 last_check=last_check)

    @lazy_wrapper_wd(TorrentsHealthPayload)
    async def on_torrents_health(self, peer, payload, data):
        self.send_version_request(peer)
        self.logger.info(f"Received torrent health information for "
                          f"{len(payload.torrents_checked)} popular torrents and"
                          f" {len(payload.random_torrents)} random torrents")

        self.record_torrent_health_message(peer, data)

        torrents = payload.random_torrents + payload.torrents_checked
        with db_session:
            self.process_torrents_health(peer, torrents)
        # await self.mds.run_threaded(self.process_torrents_health, peer, torrents)

    @db_session
    def record_message(self, peer_pk, message_type, message_len):
        self.MessageRecordEntity(
            peer_pk=peer_pk,
            received_ts=int(time.time()),
            type=message_type,
            size=message_len
        )

    def record_torrent_health_message(self, peer, message_data):
        self.record_message(peer.public_key.key_to_bin(), 'TORRENT_HEALTH', len(message_data))

    @db_session
    def process_torrents_health(self, peer, torrent_healths):
        received_at = int(time.time())
        for infohash, seeders, leechers, last_check in torrent_healths:
            self.add_received_torrent_to_database(peer, infohash, seeders, leechers, last_check, received_at)

    @db_session
    def peer_version_exists(self, peer):
        time_now = int(time.time())
        refresh_interval = 86400  # 1 day

        existing_peer = self.PeerEntity.select(lambda p: p.pk == peer.public_key.key_to_bin()).first()
        if not existing_peer:
            # Create an entry for the peer with null version and platform
            self.PeerEntity(pk=peer.public_key.key_to_bin(),
                            ip=peer.address.ip,
                            port=peer.address.port,
                            version='N/A',
                            platform='N/A',
                            first_known=time_now,
                            last_known=time_now)
            return False
        elif existing_peer.version == 'N/A' or time_now - existing_peer.last_known > refresh_interval:
            return False
        return True

    def send_version_request(self, peer):
        if not self.peer_version_exists(peer):
            self.logger.info(f"Sending version request to {peer.address}")
            self.ez_send(peer, VersionRequest())

    @db_session
    def process_version_response(self, peer, version, platform):
        ip = peer.address.ip
        port = peer.address.port
        time_now = int(time.time())
        self.logger.info(f"Version response -> pk: {hexlify(peer.public_key.key_to_bin())[:16]}, "
                         f"ip: [{ip}:{port}], version: {version}, platform: {platform}")
        existing_peer = self.PeerEntity.select(lambda p: p.pk == peer.public_key.key_to_bin()).first()
        if existing_peer:
            existing_peer.ip = ip
            existing_peer.port = port
            existing_peer.version = version
            existing_peer.platform = platform
            existing_peer.last_known = time_now
        else:
            self.PeerEntity(pk=peer.public_key.key_to_bin(),
                            ip=ip,
                            port=port,
                            version=version,
                            platform=platform,
                            first_known=time_now,
                            last_known=time_now)

    def is_dht_ready(self):
        return self.torrent_checker.dlmgr.is_dht_ready()
    async def check_and_get_torrent_health(self, hex_infohash):
        hex_infohash = "7949ef20a89feb1a2838e5b1ef42676a2ae602cc"
        print(f"Checking health:{hex_infohash}")
        bin_infohash = unhexlify(hex_infohash)
        torrent_health = await self.torrent_checker.check_torrent_health(bin_infohash, scrape_now=True) or {}
        print(f"Health response: {torrent_health}")

        seeders = torrent_health.get('DHT', {}).get('seeders', -1)
        leechers = torrent_health.get('DHT', {}).get('leechers', -1)

        print(f"Health [{hex_infohash}]: seeders: {seeders}; leechers: {leechers}")
        return seeders, leechers

    async def check_one_received_torrent_health_from_db(self):
        print("Doing regular torrent check")
        if not self.is_dht_ready():
            print(f"DHT is not ready...")
            return
        print("DHT is ready")

        with db_session:
            selected_torrent = self.CheckedTorrentsEntity\
                                    .select(lambda c: c.last_checked_by_crawler < 0)\
                                    .order_by(lambda c: desc(c.seeders))\
                                    .first()
            if selected_torrent:
                checked_seeders, checked_leechers = await self.check_and_get_torrent_health(selected_torrent.infohash)
                selected_torrent.seeders_by_crawler = checked_seeders
                selected_torrent.leechers_by_crawler = checked_leechers
                selected_torrent.last_checked_by_crawler = int(time.time())

