import heapq
import random
import time
from binascii import unhexlify
from pathlib import Path

from dotenv import load_dotenv
from pony import orm
from pydantic import BaseSettings, Field

from ipv8.lazy_community import lazy_wrapper

from pony.orm import db_session, Database

from tribler.core.components.metadata_store.remote_query_community.remote_query_community import RemoteQueryCommunity
from tribler.core.components.popularity.community.payload import TorrentsHealthPayload
from tribler.core.components.popularity.community.popularity_community import PopularityCommunity
from tribler.core.components.popularity.community.version_community_mixin import VersionCommunityMixin, VersionRequest
from tribler.core.utilities.unicode import hexlify

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(ENV_FILE)


def define_torrent_health_binding(db):
    class TorrentHealthEntity(db.Entity):
        rowid = orm.PrimaryKey(int, auto=True)

        peer_pk = orm.Required(bytes, index=True)
        peer_ip = orm.Required(str, index=True)
        peer_port = orm.Required(int, index=True)
        received_at = orm.Optional(int, size=64, default=0, index=True)

        infohash = orm.Required(str, index=True)
        seeders = orm.Optional(int, default=0)
        leechers = orm.Optional(int, default=0)
        last_check = orm.Optional(int, size=64, default=0, index=True)
    return TorrentHealthEntity

def define_peer_binding(db):
    class PeerEntity(db.Entity):
        rowid = orm.PrimaryKey(int, auto=True)
        pk = orm.Required(bytes, unique=True, index=True)
        ip = orm.Required(str, index=True)
        port = orm.Required(int, index=True)

        version = orm.Optional(str, index=True)
        platform = orm.Optional(str, index=True)

        first_known = orm.Required(int, size=64, default=0)
        last_known = orm.Required(int, size=64, default=0)
    return PeerEntity


class DatabaseSettings(BaseSettings):
    provider: str = 'sqlite'
    host: str = 'localhost'
    user: str = 'user'
    password: str = None
    database: str = 'popular_torrents'
    filename: str = 'database.sqlite'

    class Config:
        env_prefix = 'EXP_DB_'

    def get_connection(self):
        if self.provider == 'sqlite':
            return self.dict(include={'provider', 'filename'})
        else:
            return self.dict(include={'provider', 'host', 'user', 'password', 'database'})


class CustomPopularityCommunity(PopularityCommunity):
    """
    Custom PopularityCommunity created to run experiments.
    """
    # GOSSIP_INTERVAL_FOR_POPULAR_TORRENTS = 120  # seconds
    # GOSSIP_INTERVAL_FOR_RANDOM_TORRENTS = 5  # seconds
    # GOSSIP_POPULAR_TORRENT_COUNT = 10
    # GOSSIP_RANDOM_TORRENT_COUNT = 10

    def __init__(self, *args, **kwargs):
        # Creating a separate instance of Network for this community to find more peers
        super().__init__(*args, **kwargs)

        # Connection info for database database
        connection = DatabaseSettings().get_connection()
        self.logger.info(f"DB connection config: {connection}")

        self.db = Database()
        self.db.bind(**connection)

        # define bindings for tables and generate the mappings for the tables
        self.TorrentHealthEntity = define_torrent_health_binding(self.db)
        self.PeerEntity = define_peer_binding(self.db)
        self.db.generate_mapping(create_tables=True)

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
        self.TorrentHealthEntity(peer_pk=peer.public_key.key_to_bin(),
                                 peer_ip=peer.address.ip,
                                 peer_port=peer.address.port,
                                 received_at=received_at,
                                 infohash=hex_infohash,
                                 seeders=seeders,
                                 leechers=leechers,
                                 last_check=last_check)

    @lazy_wrapper(TorrentsHealthPayload)
    async def on_torrents_health(self, peer, payload):
        self.send_version_request(peer)
        self.logger.info(f"Received torrent health information for "
                          f"{len(payload.torrents_checked)} popular torrents and"
                          f" {len(payload.random_torrents)} random torrents")

        torrents = payload.random_torrents + payload.torrents_checked
        await self.mds.run_threaded(self.process_torrents_health, peer, torrents)

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
        if not existing_peer or not existing_peer.version or time_now - existing_peer.last_known > refresh_interval:
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
