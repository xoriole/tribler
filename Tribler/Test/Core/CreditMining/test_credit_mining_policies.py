"""
Module of Credit mining function testing.

Author(s): Mihai Capota, Ardhi Putra
"""
from __future__ import absolute_import
from six.moves import xrange
from twisted.internet.defer import inlineCallbacks

from Tribler.Core.CreditMining.CreditMiningPolicy import RandomPolicy, SeederRatioPolicy, UploadPolicy, \
    InvestmentPolicy, MB
from Tribler.Core.CreditMining.CreditMiningManager import CreditMiningTorrent
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

    def test_compute_investment_state(self):
        downloads = [1, 4, 5, 8, 10, 110, 150]
        uploads = [0, 2, 3, 7, 15, 90, 180]
        expected_states = [0, 0, 1, 4, 6, 17, 18]

        for i in xrange(len(downloads)):
            computed_state = self.policy.compute_state(downloads[i] * MB, uploads[i] * MB)
            self.assertEqual(expected_states[i], computed_state)
