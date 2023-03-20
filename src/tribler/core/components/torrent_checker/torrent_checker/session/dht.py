from __future__ import annotations

import time

from tribler.core.components.libtorrent.download_manager.download_manager import DownloadManager
from tribler.core.components.torrent_checker.torrent_checker import DHT
from tribler.core.components.torrent_checker.torrent_checker.dataclasses import TrackerResponse, HealthInfo
from tribler.core.components.torrent_checker.torrent_checker.session.tracker import TrackerSession
from tribler.core.components.torrent_checker.torrent_checker.utils import gather_coros, filter_non_exceptions


class FakeDHTSession(TrackerSession):
    """
    Fake TrackerSession that manages DHT requests
    """

    def __init__(self, download_manager: DownloadManager, timeout: float):
        super().__init__(DHT, DHT, DHT, DHT, timeout)

        self.download_manager = download_manager

    async def connect_to_tracker(self) -> TrackerResponse:
        health_list = []
        now = int(time.time())
        for infohash in self.infohash_list:
            metainfo = await self.download_manager.get_metainfo(infohash, timeout=self.timeout, raise_errors=True)
            health = HealthInfo(infohash, seeders=metainfo[b'seeders'], leechers=metainfo[b'leechers'],
                                last_check=now, self_checked=True)
            health_list.append(health)

        return TrackerResponse(url=DHT, torrent_health_list=health_list)


class FakeBep33DHTSession(FakeDHTSession):
    """
    Fake session for a BEP33 lookup.
    """

    async def connect_to_tracker(self) -> TrackerResponse:
        coros = [self.download_manager.dht_health_manager.get_health(infohash, timeout=self.timeout)
                 for infohash in self.infohash_list]
        results = await gather_coros(coros)
        return TrackerResponse(url=DHT, torrent_health_list=filter_non_exceptions(results))
