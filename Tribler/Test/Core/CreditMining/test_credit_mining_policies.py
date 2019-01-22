"""
Module of Credit mining function testing.

Author(s): Mihai Capota, Ardhi Putra
"""
from __future__ import absolute_import

import time

from six.moves import xrange
from twisted.internet.defer import inlineCallbacks
from Tribler.Core.CreditMining.CreditMiningPolicy import RandomPolicy, SeederRatioPolicy, UploadPolicy, \
    InvestmentPolicy, MB, InvestmentState
from Tribler.Core.CreditMining.CreditMiningManager import CreditMiningTorrent
from Tribler.Core.simpledefs import DLSTATUS_STOPPED, DLSTATUS_DOWNLOADING
from Tribler.Test.Core.base_test import TriblerCoreTest, MockObject


class TestCreditMiningPolicies(TriblerCoreTest):
    """
    Class to test the credit mining policies
    """

    @inlineCallbacks
    def setUp(self):
        yield super(TestCreditMiningPolicies, self).setUp()
        self.torrents = [CreditMiningTorrent(i, 'test torrent %d' % i) for i in range(10)]

    def test_random_policy(self):
        policy = RandomPolicy()

        sorted_torrents = policy.sort(self.torrents)
        self.assertItemsEqual(self.torrents, sorted_torrents, 'Arrays contains different torrents')

    def test_seederratio_policy(self):
        for i, torrent in enumerate(self.torrents):
            mock_ds = MockObject()
            mock_ds.get_num_seeds_peers = lambda index=i: (index, 1)
            torrent.state = mock_ds

        policy = SeederRatioPolicy()
        sorted_torrents = policy.sort(self.torrents)
        expected_torrents = list(reversed(self.torrents))

        self.assertItemsEqual(sorted_torrents, expected_torrents, 'Arrays contains different torrents')
        self.assertListEqual(sorted_torrents, expected_torrents, 'Array is not sorted properly')

    def test_upload_policy(self):
        for i, torrent in enumerate(self.torrents):
            mock_status = MockObject()
            mock_status.total_upload = i * i
            mock_status.active_time = i

            mock_handle = MockObject()
            mock_handle.status = lambda status=mock_status: status

            mock_dl = MockObject()
            mock_dl.handle = mock_handle

            torrent.download = mock_dl

        policy = UploadPolicy()
        sorted_torrents = policy.sort(self.torrents)
        expected_torrents = list(reversed(self.torrents))

        self.assertItemsEqual(sorted_torrents, expected_torrents, 'Arrays contains different torrents')
        self.assertListEqual(sorted_torrents, expected_torrents, 'Array is not sorted properly')

    def test_schedule_start(self):
        policy = UploadPolicy()
        policy.schedule(self.torrents[0])
        self.assertTrue(self.torrents[0].to_start)
        policy.schedule(self.torrents[1], to_start=False)
        self.assertFalse(self.torrents[1].to_start)

    def test_basic_policy_run(self):
        """
        Test running an iteration of basic policy.

        Scenario: There are 10 torrents with infohashes ordered as 0-9 and the torrents with odd infohashes
        are downloading while the rest are stopped. In the next iteration, we assume that all the
        torrents with infohashes as multiple of 3 are scheduled to start and the rest to be stopped.

        The scenario is represented in the table below:
        Infohash    Status         To Start     ->  Result
            0       STOPPED         True            Started
            1       DOWNLOADING     False           Stopped
            2       STOPPED         False           Do Nothing
            3       DOWNLOADING     True            Do Nothing
            4       STOPPED         False           Do Nothing
            5       DOWNLOADING     False           Stopped
            6       STOPPED         True            Started
            7       DOWNLOADING     False           Stopped
            8       STOPPED         False           Do Nothing
            9       DOWNLOADING     True            Do Nothing

        At the end of the iteration, the following result is expected:
        Started = 2
        Stopped = 3
        """

        # Any BasicPolicy implementation is fine.
        policy = UploadPolicy()

        def get_status(torrent):
            return DLSTATUS_STOPPED if torrent.infohash % 2 == 0 else DLSTATUS_DOWNLOADING

        for torrent in self.torrents:
            torrent.download = MockObject()
            torrent.download.state = MockObject()
            torrent.download.state.get_status = lambda _torrent=torrent: get_status(_torrent)
            torrent.download.get_state = lambda _state=torrent.download.state: _state
            torrent.download.restart = lambda: None
            torrent.download.stop = lambda: None

            # Schedule torrent to start or stop
            if torrent.infohash % 3 == 0:
                policy.schedule(torrent)
            else:
                policy.schedule(torrent, to_start=False)

        (started, stopped) = policy.run()
        self.assertEqual(started, 2)
        self.assertEqual(stopped, 3)

    def test_basic_policy_run_with_no_downloads(self):
        """
        Test running an iteration of basic policy without any downloads.
        Policy should just skip those torrents.
        """
        policy = UploadPolicy()
        for torrent in self.torrents:
            policy.schedule(torrent)

        (started, stopped) = policy.run()
        self.assertEqual(started, 0)
        self.assertEqual(stopped, 0)


class TestInvestmentPolicy(TriblerCoreTest):
    """
    Class to test investment policy.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(TestInvestmentPolicy, self).setUp()
        self.torrents = [CreditMiningTorrent(i, 'test torrent %d' % i) for i in range(10)]
        self.policy = InvestmentPolicy()

    def test_default_states(self):
        default_states = self.policy.get_default_investment_states()
        self.assertEqual(len(default_states), 20)

        self.assertEqual(default_states[0].state_id, 0)
        self.assertEqual(default_states[0].upload_mode, False)
        self.assertEqual(default_states[0].bandwidth_limit, 5 * MB)

        self.assertEqual(default_states[19].state_id, 19)
        self.assertEqual(default_states[19].upload_mode, True)
        self.assertEqual(default_states[19].bandwidth_limit, 163 * MB)

    def test_state_is_promotion_ready(self):
        download_state1 = InvestmentState(1, False, 5*MB, promotion_ratio=1)
        self.assertFalse(download_state1.is_promotion_ready(4 * MB, 3 * MB))
        self.assertTrue(download_state1.is_promotion_ready(5.1 * MB, 3 * MB))
        self.assertFalse(download_state1.is_promotion_ready(3 * MB, 6 * MB))

        upload_state1 = InvestmentState(1, True, 5 * MB, promotion_ratio=1)
        self.assertFalse(upload_state1.is_promotion_ready(5 * MB, 3 * MB))
        self.assertTrue(upload_state1.is_promotion_ready(5 * MB, 6 * MB))

        upload_state2 = InvestmentState(1, True, 5 * MB, promotion_ratio=2)
        self.assertFalse(upload_state2.is_promotion_ready(5 * MB, 6 * MB))
        self.assertTrue(upload_state2.is_promotion_ready(5 * MB, 10 * MB))

    def test_compute_investment_state(self):
        downloads = [1, 4, 5, 8, 10, 110, 150, 1000]
        uploads = [0, 2, 3, 7, 15, 90, 180, 1000]
        expected_states = [0, 0, 1, 4, 6, 17, 18, 19]

        for i in xrange(len(downloads)):
            computed_state = self.policy.compute_state(downloads[i] * MB, uploads[i] * MB)
            self.assertEqual(expected_states[i], computed_state)

    def test_get_reserved_bytes(self):
        policy = InvestmentPolicy()
        self.torrents[0].get_storage = lambda: (10 * MB, 4 * MB)

        # For state 0 with 5MB bandwidth limit
        self.torrents[0].mining_state['state_id'] = 0
        self.assertTrue(policy.investment_states[0].bandwidth_limit, 5 * MB)
        self.assertEqual(policy.get_reserved_bytes(self.torrents[0]), 1 * MB)

        # For state 1 with 5MB bandwidth limit
        self.torrents[0].mining_state['state_id'] = 1
        self.assertTrue(policy.investment_states[0].bandwidth_limit, 5 * MB)
        self.assertEqual(policy.get_reserved_bytes(self.torrents[0]), 1 * MB)

        # For state 2 with 7MB bandwidth limit
        self.torrents[0].mining_state['state_id'] = 2
        self.assertTrue(policy.investment_states[1].bandwidth_limit, 7 * MB)
        self.assertEqual(policy.get_reserved_bytes(self.torrents[0]), 3 * MB)

    def test_schedule_start(self):
        policy = InvestmentPolicy()

        self.torrents[0].download = MockObject()
        self.torrents[0].state = MockObject()
        self.torrents[0].state.get_total_transferred = lambda _: 0

        time_before = time.time()
        policy.schedule_start(self.torrents[0])
        self.assertTrue(self.torrents[0].to_start)
        added_time = self.torrents[0].mining_state['start_time']
        self.assertTrue(added_time >= time_before)

        # Check adding torrent is done only once on subsequent start
        start_time = self.torrents[0].mining_state['start_time']
        self.torrents[0].to_start = False
        policy.schedule_start(self.torrents[0])
        self.assertTrue(self.torrents[0].to_start)
        self.assertEqual(start_time, self.torrents[0].mining_state['start_time'])

    def test_promote_torrent(self):

        def mock_restart_download(upload_mode, torrent):
            torrent.upload_mode = upload_mode

        policy = InvestmentPolicy()

        torrent = self.torrents[0]
        torrent.download = MockObject()
        torrent.download.restart = lambda upload_mode, _torrent=torrent: mock_restart_download(upload_mode, _torrent)

        # Promote from state 0
        torrent.upload_mode = False
        torrent.mining_state['state_id'] = 0
        policy.promote_torrent(torrent)
        self.assertEqual(torrent.mining_state['state_id'], 1)
        self.assertTrue(torrent.upload_mode)

        # Promote from state 1
        torrent.upload_mode = True
        torrent.mining_state['state_id'] = 1
        policy.promote_torrent(torrent)
        self.assertEqual(torrent.mining_state['state_id'], 2)
        self.assertFalse(torrent.upload_mode)

        # Promote from last state
        last_state = len(policy.investment_states) - 1
        torrent.upload_mode = True  # Last state is always in upload mode
        torrent.mining_state['state_id'] = last_state
        policy.promote_torrent(torrent)
        self.assertEqual(torrent.mining_state['state_id'], last_state)
        self.assertTrue(torrent.upload_mode)
