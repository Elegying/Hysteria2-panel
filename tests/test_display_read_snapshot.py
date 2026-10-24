"""Display polling must not serialize authentication behind stats I/O."""
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from hysteria2_panel import Database, UsageManager, MAX_STATE_AGE_SECONDS
from hy2panel.mobile_api import users_payload
from test_panel import PolicyStatsClient


class DisplayReadSnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Database(Path(temporary.name) / 'panel.db', b'd' * 32)
        self.db.initialize()
        self.user = self.db.create_proxy_user('alice')
        self.stats = PolicyStatsClient(traffic={'alice': {'tx': 10, 'rx': 20}}, online={'alice': 1})
        self.now = [1800000000]
        self.manager = UsageManager(self.db, self.stats, wall_clock=lambda: self.now[0])

    def test_cold_display_does_not_collect_or_claim_zero_is_fresh(self):
        with mock.patch.object(self.stats, 'collect_and_clear', side_effect=AssertionError('read collected')), \
                mock.patch.object(self.stats, 'online', side_effect=AssertionError('read sampled')):
            snapshot = self.manager.read_snapshot()
        self.assertFalse(snapshot['available'])
        self.assertFalse(snapshot['online_complete'])
        origin = snapshot['machine_stats']['origins'][0]
        self.assertIsNone(origin['online_devices'])
        self.assertIsNone(origin['observed_at'])
        self.assertEqual(0, self.db.get_proxy_user(self.user['id'])['tx_bytes'])

    def test_display_finishes_while_collector_lock_is_held(self):
        self.manager.collect_once()
        result = []
        completed = threading.Event()

        def read():
            try:
                result.append(self.manager.read_snapshot())
            finally:
                completed.set()

        with self.manager.lock, \
                mock.patch.object(self.stats, 'collect_and_clear', side_effect=AssertionError('read collected')), \
                mock.patch.object(self.stats, 'online', side_effect=AssertionError('read sampled')):
            thread = threading.Thread(target=read)
            thread.start()
            finished_under_lock = completed.wait(2)
        thread.join(3)
        self.assertTrue(finished_under_lock, 'display waited for the authentication/collector mutex')
        self.assertEqual({'tx': 10, 'rx': 20}, result[0]['traffic']['alice'])
        self.assertEqual({'alice': 1}, result[0]['online'])

    def test_freshness_uses_sample_time_and_failure_invalidates_it(self):
        self.manager.collect_once()
        self.now[0] += 3
        snapshot = self.manager.read_snapshot()
        self.assertTrue(snapshot['available'])
        self.assertEqual(self.now[0] - 3, snapshot['machine_stats']['origins'][0]['observed_at'])
        self.now[0] += MAX_STATE_AGE_SECONDS
        self.assertFalse(self.manager.read_snapshot()['available'])
        self.manager.collect_once()
        self.manager._record_health(False)
        self.assertFalse(self.manager.read_snapshot()['available'])
        self.assertFalse(self.manager.read_snapshot()['online_complete'])

    def test_mobile_reads_current_committed_rows_without_replaying_pending_source(self):
        self.manager.collect_once()
        self.stats.traffic_values = {'alice': {'tx': 100, 'rx': 200}}
        self.db.add_traffic({'alice': {'tx': 7, 'rx': 9}})
        application = SimpleNamespace(database=self.db, usage_manager=self.manager)
        with mock.patch.object(self.db, 'list_proxy_users_for_usage',
                               wraps=self.db.list_proxy_users_for_usage) as read_users:
            result = users_payload(application)
        self.assertEqual(1, read_users.call_count)
        self.assertEqual(46, result['items'][0]['usedBytes'])
        self.assertEqual({'alice': {'tx': 100, 'rx': 200}}, self.stats.traffic_values)
        self.db.delete_proxy_user(self.user['id'])
        self.assertEqual([], users_payload(application)['items'])

    def test_read_snapshot_cannot_authorize_a_revoked_user(self):
        self.manager.collect_once()
        self.assertTrue(self.manager.read_snapshot()['available'])
        self.db.set_proxy_user_enabled(self.user['id'], False)
        self.assertFalse(self.manager.authorize('alice'))
        application = SimpleNamespace(database=self.db, usage_manager=self.manager)
        self.assertFalse(users_payload(application)['items'][0]['enabled'])


if __name__ == '__main__':
    unittest.main()
