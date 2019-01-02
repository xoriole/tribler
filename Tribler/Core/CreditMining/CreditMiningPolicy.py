from __future__ import absolute_import

import time

"""
Supported credit mining policy.
Author(s): Egbert Bouman, Mihai Capota, Elric Milon, Ardhi Putra, Sandip Pandey
"""
import random

HOUR = 3600
MB = 1204 * 1024


class BasePolicy(object):
    """
    Base class for determining what swarm selection policy will be applied
    """

    def get_name(self):
        raise NotImplementedError()

    def sort(self, torrents):
        raise NotImplementedError()

    def should_remove(self, torrent):
        raise NotImplementedError()

    def get_download_size(self, torrent):
        length = torrent.download.get_def().get_length()
        progress = torrent.download.get_state().get_progress()
        return length * (1.0 - progress)


class RandomPolicy(BasePolicy):
    """
    A credit mining policy that chooses a swarm randomly
    """

    def get_name(self):
        return 'RandomPolicy'

    def sort(self, torrents):
        result = torrents[:]
        random.shuffle(result)
        return result

    def should_remove(self, torrent):
        raise False


class SeederRatioPolicy(BasePolicy):
    """
    Find the most underseeded swarm to boost.
    """

    def get_name(self):
        return 'SeederRatioPolicy'

    def sort(self, torrents):
        def sort_key(torrent):
            ds = torrent.state
            seeds, peers = ds.get_num_seeds_peers() if ds else (0, 1)
            return seeds / float(seeds + peers)

        return sorted(torrents, key=sort_key, reverse=True)

    def should_remove(self, torrent):
        raise False


class UploadPolicy(BasePolicy):
    """
    Choose swarm such that we maximize the total upload.
    """

    def get_name(self):
        return 'UploadPolicy'

    def sort(self, torrents):
        def sort_key(torrent):
            if torrent.download and torrent.download.handle:
                status = torrent.download.handle.status()
                return status.total_upload / float(status.active_time) if status.active_time else 0.0
            return 0.0

        return sorted(torrents, key=sort_key, reverse=True)

    def should_remove(self, torrent):
        raise False


class InvestmentPolicy(BasePolicy):
    """
    Choose swarm based on investment and return on investment.
    """

    def __init__(self, levels=[]):
        super(InvestmentPolicy, self).__init__()
        self.levels = levels

    def get_name(self):
        return 'InvestmentPolicy'

    def sort(self, torrents):
        def sort_key(torrent):
            if torrent.download and torrent.download.handle:
                status = torrent.download.handle.status()
                return status.total_upload / float(status.active_time) if status.active_time else 0.0
            return 0.0

        return sorted(torrents, key=sort_key, reverse=True)

    def should_remove(self, torrentdl):
        diff_time = time.time() - torrentdl.add_time
        lt_status = torrentdl.get_state().lt_status
        uploaded = lt_status.total_payload_upload if lt_status else 0

        return diff_time > HOUR and uploaded < 5 * MB \
               or diff_time > 12 * HOUR and uploaded < 50 * MB \
               or diff_time > 24 * HOUR and uploaded < 100 * MB \
               or diff_time > 48 * HOUR and uploaded < 250 * MB \
               or diff_time > 72 * HOUR

    def get_download_size(self, torrent):
        lt_status = torrent.download.get_state().lt_status
        downloaded = lt_status.total_payload_download if lt_status else 0
        return self.levels[torrent.level].download_limit - downloaded

    def promote_torrent(self, torrent):
        mining_level = self.levels[torrent.level]
        lt_status = torrent.download.get_state().lt_status
        if mining_level.upload_mode:
            uploaded = lt_status.total_payload_upload if lt_status else 0
            if uploaded > mining_level.promotion_ratio * mining_level.download_limit:
                torrent.download.set_upload_mode(False)
                torrent.level += 1
        else:
            downloaded = lt_status.total_payload_download if lt_status else 0
            diff = downloaded - mining_level.download_limit
            if diff > 0:
                torrent.download.set_upload_mode(True)
                torrent.level += 1

    def promote(self, torrent):
        mining_level = self.levels[torrent.level]
        lt_status = torrent.download.get_state().lt_status
        if mining_level.upload_mode:
            uploaded = lt_status.total_payload_upload if lt_status else 0
            return uploaded > mining_level.promotion_ratio * mining_level.download_limit
        else:
            downloaded = lt_status.total_payload_download if lt_status else 0
            return downloaded > mining_level.download_limit

    def is_final_level(self, level):
        return len(self.levels) == level


