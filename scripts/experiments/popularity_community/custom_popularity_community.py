import time
from pathlib import Path

from dotenv import load_dotenv
from pony.orm import db_session

from ipv8.lazy_community import lazy_wrapper
from scripts.experiments.common.database import get_database
from scripts.experiments.popularity_community.custom_entities import define_torrent_health_binding, define_peer_binding
from tribler.core.components.popularity.community.payload import TorrentsHealthPayload
from tribler.core.components.popularity.community.popularity_community import PopularityCommunity
from tribler.core.components.popularity.community.version_community_mixin import VersionRequest
from tribler.core.utilities.unicode import hexlify


class CustomPopularityCommunity(PopularityCommunity):
    """
    Custom PopularityCommunity created to run experiments.
    """

    def __init__(self, *args, **kwargs):
        # Creating a separate instance of Network for this community to find more peers
        super().__init__(*args, **kwargs)

        # define bindings for tables and generate the mappings for the tables
        self.db = get_database()
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
