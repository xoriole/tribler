"""
Supported credit mining policy.
Author(s): Egbert Bouman, Mihai Capota, Elric Milon, Ardhi Putra
"""
from __future__ import absolute_import
import logging
import random
import time

from Tribler.Core.simpledefs import DLSTATUS_STOPPED, DLSTATUS_STOPPED_ON_ERROR, UPLOAD, DOWNLOAD, DLSTATUS_SEEDING, \
    DLSTATUS_DOWNLOADING

MB = 1024 * 1024
HOUR = 3600
DAY = 86400
WEEK = 7 * DAY
DOWNLOAD_MODE = 0
UPLOAD_MODE = 1


class BasePolicy(object):
    """
    Base class for determining what swarm selection policy will be applied
    """

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.torrents = {}

    def get_default_state(self):
        return {
            'policy': self.__class__.__name__,
            'status': -1,
            'start_time': 0,
            'stop_time': 0
        }

    def sort(self, torrents):
        raise NotImplementedError()

    def schedule_start(self, torrent):
        torrent.to_start = True
        self.torrents[torrent.infohash] = torrent

    def run(self):
        started = stopped = 0
        for torrent in self.torrents.values():
            if not torrent.download:
                continue

            status = torrent.download.get_state().get_status()
            if torrent.to_start and status == DLSTATUS_STOPPED:
                torrent.download.restart()
                started += 1
            elif not torrent.to_start and status not in [DLSTATUS_STOPPED, DLSTATUS_STOPPED_ON_ERROR]:
                torrent.download.stop()
                stopped += 1
            torrent.to_start = False

            self._logger.info('Started %d torrent(s), stopped %d torrent(s)', started, stopped)

    def get_reserved_bytes(self, torrent):
        length = torrent.download.get_def().get_length()
        progress = torrent.download.get_state().get_progress()
        return length * (1.0 - progress)


class RandomPolicy(BasePolicy):
    """
    A credit mining policy that chooses a swarm randomly
    """

    def sort(self, torrents):
        result = torrents[:]
        random.shuffle(result)
        return result


class SeederRatioPolicy(BasePolicy):
    """
    Find the most underseeded swarm to boost.
    """

    def sort(self, torrents):
        def sort_key(torrent):
            ds = torrent.state
            seeds, peers = ds.get_num_seeds_peers() if ds else (0, 1)
            return seeds / float(seeds + peers)

        return sorted(torrents, key=sort_key, reverse=True)


class UploadPolicy(BasePolicy):
    """
    Choose swarm such that we maximize the total upload.
    """

    def sort(self, torrents):
        def sort_key(torrent):
            if torrent.download and torrent.download.handle:
                status = torrent.download.handle.status()
                return status.total_upload / float(status.active_time) if status.active_time else 0.0
            return 0.0

        return sorted(torrents, key=sort_key, reverse=True)


class InvestmentState(object):
    """
    Represents the credit mining state for the torrent.
    """
    def __init__(self, state_id, upload_mode, bandwidth_limit, promotion_ratio=1, promotion_interval=5 * 60):
        self.state_id = state_id
        self.bandwidth_limit = bandwidth_limit
        self.upload_mode = upload_mode
        self.promotion_ratio = promotion_ratio
        self.promotion_interval = promotion_interval

    def is_promotion_ready(self, download, upload):
        if self.upload_mode:
            return upload > self.bandwidth_limit * self.promotion_ratio
        return download > self.bandwidth_limit

    def __str__(self):
        return 'InvestmentState {'\
               + '\n\tid:' + str(self.state_id)\
               + '\n\tbandwidth_limit:' + str(self.bandwidth_limit)\
               + '\n\tupload_mode:' + str(self.upload_mode)\
               + '\n\tpromotion_ratio:' + str(self.promotion_ratio)\
               + '\n\tpromotion_interval:' + str(self.promotion_interval)\
               + '\n}'


class InvestmentPolicy(BasePolicy):
    """
    Policy to select and promote torrents based on the (upload) yield on the investment download.
    Higher the yield, higher will be the allowance to do investment download.
    """

    def __init__(self, states=None):
        super(InvestmentPolicy, self).__init__()
        self.investment_states = states if states else self.get_default_investment_states()
        self.mining_level = {}

    @staticmethod
    def get_default_investment_states():
        """
        Default investment state has the following parameters:
            - Starting investment value, say a
            - Alternating Download (0) and Upload mode (1)
            - Promotion ratio = Upload/Download = 1

            The value of investment in each state follows the following half series:
                a, a + a/2, ...
            The inital values of a = 5 MB
            Then the sequence becomes 5, 7, 10, 15, 22, 33, 49, 73, 109, 163, ...
        :return: Dict of investment states
        """
        investment = 5
        states = {}
        for level in xrange(10):
            download_state = 2 * level
            upload_state = download_state + 1
            states[download_state] = InvestmentState(download_state, download_state % 2, investment * MB)
            states[upload_state] = InvestmentState(upload_state, upload_state % 2, investment * MB)
            investment = investment + investment/2
        return states

    def schedule_start(self, torrent):
        if torrent.infohash not in self.torrents:
            up = torrent.state.get_total_transferred(UPLOAD)
            down = torrent.state.get_total_transferred(DOWNLOAD)
            torrent.mining_state['start_time'] = time.time()
            torrent.mining_state['initial_upload'] = up
            torrent.mining_state['initial_download'] = down
            torrent.mining_state['state_id'] = self.compute_state(down, up)
        torrent.to_start = True
        self.torrents[torrent.infohash] = torrent

    def compute_state(self, download, upload):
        for state in self.investment_states.values():
            if (state.upload_mode and upload < state.bandwidth_limit * state.promotion_ratio) \
                    or (not state.upload_mode and download < state.bandwidth_limit):
                return state.state_id
        return 0

    def sort(self, torrents):
        def sort_key(torrent):
            if torrent.download and torrent.download.handle:
                status = torrent.download.handle.status()
                return status.total_upload / float(status.active_time) if status.active_time else 0.0
            return 0.0

        return sorted(torrents, key=sort_key, reverse=True)

    def promote_torrent(self, torrent):
        current_state_id = torrent.mining_state.get('state_id', 0)
        if len(self.investment_states) == current_state_id + 1:
            return
        next_state = self.investment_states[current_state_id + 1]
        torrent.mining_state['state_id'] = current_state_id + 1
        if next_state.upload_mode:
            torrent.download.restart(upload_mode=True)
        else:
            torrent.download.restart(upload_mode=False)

    def run(self):
        """
        Run an iteration of the policy.

        If torrent has no yield for a week, stop it.
        If torrent is scheduled to be started,
            - promote torrent if it is ready for promotion
            - otherwise ensure the torrent is correct mode
        Else
            - stop the torrent
        """
        started = stopped = 0
        num_uploading = num_downloading = 0
        for torrent in self.torrents.values():
            if not torrent.download:
                continue

            torrent_state = torrent.download.get_state()
            eta = torrent_state.get_eta()
            if eta == 0:
                torrent.download.restart(upload_mode=True)
                num_uploading += 1

            upload = torrent_state.get_total_transferred(UPLOAD)
            download = torrent_state.get_total_transferred(DOWNLOAD)

            # Remove the torrent if upload is too low in a week's time
            diff_time = time.time() - torrent.start_time
            diff_upload = upload - torrent.mining_state.get('initial_upload', 0)
            if diff_time > WEEK and diff_upload < 5 * MB:
                torrent.download.stop()

            investment_state = self.investment_states[torrent.mining_state.get('state_id', 0)]
            if torrent.to_start:
                if investment_state.is_promotion_ready(download, upload):
                    self.promote_torrent(torrent)
                else:
                    status = torrent_state.get_status()
                    if investment_state.upload_mode and status is not DLSTATUS_SEEDING:
                        torrent.download.restart(upload_mode=True)
                        num_uploading += 1
                    elif not investment_state.upload_mode and status is not DLSTATUS_DOWNLOADING:
                        torrent.download.restart(upload_mode=False)
                        num_downloading += 1
                started += 1
                torrent.to_start = False
            else:
                torrent.download.stop()
                stopped += 1

        self._logger.info('Started %d torrent(s), stopped %d torrent(s)', started, stopped)
        self._logger.info('Torrents in upload mode: %d, download mode: %d', num_uploading, num_downloading)

    def get_reserved_bytes(self, torrent):
        length = torrent.download.get_def().get_length()
        progress = torrent.download.get_state().get_progress()
        return length * (1.0 - progress)
