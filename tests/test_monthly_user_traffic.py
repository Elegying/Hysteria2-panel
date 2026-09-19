"""Monthly quota reset preserves machine billing and is crash/idempotency safe."""
import concurrent.futures
import datetime
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import urllib.error

from hysteria2_panel import Database, UsageManager, seconds_to_user_traffic_month, user_traffic_month
from tests import test_panel


def epoch(value):
    return datetime.datetime.fromisoformat(value).timestamp()


class MonthlyTrafficTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Database(Path(self.tmp.name) / 'panel.db', b'm' * 32)
        self.start = epoch('2026-09-19T12:00:00+08:00')
        self.boundary = epoch('2026-10-01T00:00:00+08:00')
        with mock.patch('hysteria2_panel.time.time', return_value=self.start):
            self.db.initialize()
        self.user = self.db.create_proxy_user('monthly-user', traffic_limit_bytes=100000)
        self.db.apply_traffic_batch('a' * 32, {'monthly-user': {'tx': 100, 'rx': 200}}, observed_at=int(self.start))

    def traffic(self):
        row = self.db.get_proxy_user(self.user['id'])
        return row['tx_bytes'] + row['rx_bytes']

    def test_timezone_first_enable_boundary_and_clock_rollback(self):
        self.assertEqual('2026-10', user_traffic_month(self.boundary))
        self.assertEqual(1, seconds_to_user_traffic_month(self.boundary - 1))
        self.assertFalse(self.db.reset_monthly_traffic_if_due(self.start))
        self.assertFalse(self.db.reset_monthly_traffic_if_due(self.boundary - 1))
        self.assertEqual(300, self.traffic())
        self.assertTrue(self.db.reset_monthly_traffic_if_due(self.boundary))
        self.assertEqual(0, self.traffic())
        self.db.add_traffic({'monthly-user': {'tx': 50, 'rx': 0}})
        self.assertFalse(self.db.reset_monthly_traffic_if_due(self.boundary + 1))
        self.assertFalse(self.db.reset_monthly_traffic_if_due(self.start))
        self.assertEqual(50, self.traffic())

    def test_concurrent_restart_and_missed_months(self):
        late = epoch('2027-01-04T01:00:00+08:00')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.db.reset_monthly_traffic_if_due, [late, late]))
        self.assertEqual(1, results.count(True))
        self.db.add_traffic({'monthly-user': {'tx': 12, 'rx': 0}})
        other = Database(self.db.path, b'm' * 32)
        other.initialize()
        self.assertFalse(other.reset_monthly_traffic_if_due(late + 1))
        self.assertEqual(12, self.traffic())

    def test_failure_rolls_back_marker_and_retries(self):
        with self.db._connect() as c:
            c.execute("CREATE TRIGGER fail_reset BEFORE UPDATE ON proxy_users BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.reset_monthly_traffic_if_due(self.boundary)
        self.assertEqual(300, self.traffic())
        with self.db._connect() as c:
            self.assertEqual('2026-09', c.execute('SELECT period FROM user_traffic_reset_state').fetchone()[0])
            c.execute('DROP TRIGGER fail_reset')
        self.assertTrue(self.db.reset_monthly_traffic_if_due(self.boundary))

    def test_old_remote_batch_does_not_restore_user_usage_or_erase_machine_ledger(self):
        with self.db._connect() as c:
            billing = list(c.execute('SELECT * FROM origin_traffic_daily'))
        self.db.reset_monthly_traffic_if_due(self.boundary)
        with self.db._connect() as c:
            self.assertEqual(billing, list(c.execute('SELECT * FROM origin_traffic_daily')))
        self.db.apply_traffic_batch('b' * 32, {'monthly-user': {'tx': 20, 'rx': 30}},
                                   origin_id='node:' + 'a' * 32, origin_kind='remote',
                                   observed_at=int(self.boundary) - 1)
        self.assertEqual(0, self.traffic())
        self.db.apply_traffic_batch('c' * 32, {'monthly-user': {'tx': 3, 'rx': 4}},
                                   origin_id='node:' + 'a' * 32, origin_kind='remote',
                                   observed_at=int(self.boundary) + 1)
        self.assertEqual(7, self.traffic())

    def test_collector_settles_before_reset_and_failed_settlement_does_not_commit(self):
        stats = test_panel.PolicyStatsClient(online={'monthly-user': 1})
        manager = UsageManager(self.db, stats, wall_clock=lambda: self.boundary)
        with mock.patch.object(stats, 'collect_and_clear', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                manager.collect_once()
        self.assertEqual(300, self.traffic())
        manager.collect_once()
        self.assertEqual(0, self.traffic())
        self.assertEqual([], stats.kicked)
        # Fresh samples in the reset second still count; replayed old batches do not.
        stats.traffic_values = {'monthly-user': {'tx': 7, 'rx': 11}}
        manager.collect_once()
        self.assertEqual(18, self.traffic())


class UserLookupTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_panel.PanelHttpTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_lookup_requires_login_and_returns_only_edit_fields(self):
        f = self.fixture
        f.db.create_proxy_user('Lookup-User', allow_udp_443=True)
        with f.request('/users/lookup?name=Lookup-User') as response:
            self.assertNotIn(b'"device_limit"', response.read())
        headers, _ = f.authenticated_headers()
        with f.request('/users/lookup?name=lookup-user', headers=headers) as response:
            payload = json.load(response)
        self.assertEqual('Lookup-User', payload['name'])
        self.assertTrue(payload['allow_udp_443'])
        self.assertEqual({'id', 'name', 'generation', 'device_limit', 'traffic_limit_gb', 'used_traffic_gib', 'allow_udp_443'}, set(payload))
        with self.assertRaises(urllib.error.HTTPError) as error:
            f.request('/users/lookup?name=missing', headers=headers)
        self.assertEqual(404, error.exception.code)
        error.exception.close()
