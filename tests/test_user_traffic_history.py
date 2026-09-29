"""User history is a bounded, idempotent observation ledger, not a quota counter."""
import datetime
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import urllib.error

from hysteria2_panel import Database
from hy2panel.mobile_api import match_mobile_route
from tests import test_panel


def stamp(value):
    return int(datetime.datetime.fromisoformat(value).timestamp())


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = stamp('2026-09-29T12:00:00+08:00')
        self.db = Database(Path(self.temp.name) / 'panel.db', b'h' * 32)
        with mock.patch('hysteria2_panel.time.time', return_value=self.now):
            self.db.initialize()
            self.user = self.db.create_proxy_user('history-user')

    def add(self, batch, amount, observed=None, now=None, origin='local'):
        with mock.patch('hysteria2_panel.time.time', return_value=now or self.now):
            return self.db.apply_traffic_batch(batch, {'history-user': {'tx': amount, 'rx': amount * 2}},
                observed_at=observed or self.now, origin_id=origin + ':' + 'a' * 32,
                origin_kind='remote' if origin == 'node' else 'local')

    def test_aggregates_sources_and_hours_without_replay_or_quota_edits(self):
        self.add('a' * 32, 10)
        self.assertFalse(self.add('a' * 32, 10))
        self.add('b' * 32, 30, self.now - 3600, origin='node')
        data = self.db.user_traffic_history(self.user['id'], self.now)
        self.assertEqual(120, data['totalBytes'])
        self.assertEqual(29, len(data['days']))
        day = data['days'][0]
        self.assertEqual(24, len(day['hours']))
        self.assertEqual(75, day['hours'][11]['percent'])
        self.assertEqual(25, day['hours'][12]['percent'])
        self.assertEqual(100, day['percent'])
        self.db.reset_proxy_user_traffic(self.user['id'])
        self.assertEqual(120, self.db.user_traffic_history(self.user['id'], self.now)['totalBytes'])

    def test_month_reset_drops_old_details_preserves_new_arrivals_and_dedup(self):
        self.add('a' * 32, 10)
        boundary = stamp('2026-10-01T00:00:00+08:00')
        self.add('b' * 32, 7, boundary, boundary)
        with self.db._connect() as c:
            c.executemany('INSERT INTO audit_log(created_at,actor,action,target,remote_ip) VALUES (?,?,?,?,?)',
                [(boundary - 1, 'test', 'old', '', ''), (boundary, 'test', 'new', '', '')])
        self.assertTrue(self.db.reset_monthly_traffic_if_due(boundary + 10))
        self.add('c' * 32, 30, boundary - 1, boundary + 20)
        self.assertFalse(self.add('a' * 32, 10, self.now, boundary + 20))
        data = self.db.user_traffic_history(self.user['id'], boundary + 20)
        self.assertEqual(21, data['totalBytes'])
        self.assertEqual('2026-10-01', data['days'][0]['date'])
        with self.db._connect() as c:
            self.assertEqual(1, c.execute('SELECT COUNT(*) FROM user_traffic_hourly').fetchone()[0])
            self.assertEqual(['new'], [r[0] for r in c.execute('SELECT action FROM audit_log')])

    def test_deleted_identity_cannot_leak_history_to_reused_numeric_id(self):
        self.add('a' * 32, 10)
        self.db.delete_proxy_user(self.user['id'])
        user = self.db.create_proxy_user('new-history-user')
        self.assertEqual(0, self.db.user_traffic_history(user['id'], self.now)['totalBytes'])
        with self.assertRaises(KeyError):
            self.db.user_traffic_history(99999, self.now)

    def test_month_cleanup_failure_is_atomic_and_old_domains_cannot_reappear(self):
        self.add('a' * 32, 10)
        boundary = stamp('2026-10-01T00:00:00+08:00')
        with self.db._connect() as c:
            c.execute("CREATE TRIGGER fail_history_delete BEFORE DELETE ON user_traffic_hourly BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.reset_monthly_traffic_if_due(boundary)
        self.assertEqual(10, self.db.get_proxy_user(self.user['id'])['tx_bytes'])
        with self.db._connect() as c:
            self.assertEqual('2026-09', c.execute('SELECT period FROM user_traffic_reset_state').fetchone()[0])
            c.execute('DROP TRIGGER fail_history_delete')
        self.db.reset_monthly_traffic_if_due(boundary)
        with mock.patch('hysteria2_panel.time.time', return_value=boundary + 2):
            self.db.apply_traffic_batch('e' * 32, {}, observed_at=boundary - 1,
                domain_usage=[{'user': 'history-user', 'domain': 'example.test', 'tx': 1, 'rx': 2}])
        with self.db._connect() as c:
            self.assertEqual(0, c.execute('SELECT COUNT(*) FROM domain_usage_monthly').fetchone()[0])

    def test_hour_counter_overflow_rolls_back_instead_of_silently_becoming_float(self):
        self.add('a' * 32, 1)
        with self.db._connect() as c:
            c.execute('UPDATE user_traffic_hourly SET tx_bytes = ?', (2**63 - 1,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.add('b' * 32, 1)
        self.assertEqual(1, self.db.get_proxy_user(self.user['id'])['tx_bytes'])

    def test_failed_history_write_rolls_back_user_and_dedup_ledger(self):
        with self.db._connect() as c:
            c.execute("CREATE TRIGGER fail_history BEFORE INSERT ON user_traffic_hourly BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.add('a' * 32, 10)
        self.assertEqual(0, self.db.get_proxy_user(self.user['id'])['tx_bytes'])
        with self.db._connect() as c:
            self.assertEqual(0, c.execute('SELECT COUNT(*) FROM applied_traffic_batches').fetchone()[0])


class HistoryHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_panel.PanelHttpTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_actual_two_node_protocol_updates_the_shared_user_history(self):
        self.fixture.test_two_node_control_e2e_replays_durable_traffic_after_outage()
        user = self.fixture.db.get_proxy_user_by_name('distributed-e2e')
        self.assertEqual(37, self.fixture.db.user_traffic_history(user['id'])['totalBytes'])

    def test_mobile_history_requires_bearer_and_returns_the_same_safe_payload(self):
        f = self.fixture
        user = f.db.create_proxy_user('history-mobile')
        path = '/api/v1/mobile/users/{}/traffic-history'.format(user['id'])
        with self.assertRaises(urllib.error.HTTPError) as exc:
            f.request(path)
        self.assertEqual(401, exc.exception.code)
        exc.exception.close()
        session = f.db.create_mobile_session(f.admin_id, 'history-fixture-device', 'Fixture')
        with f.request(path, headers={'Authorization': 'Bearer ' + session['accessToken']}) as response:
            data = json.load(response)['data']
        self.assertEqual(f.db.user_traffic_history(user['id']), data)

    def test_web_requires_auth_and_mobile_route_is_reserved(self):
        f = self.fixture
        user = f.db.create_proxy_user('history-http')
        path = '/api/v1/users/{}/traffic-history'.format(user['id'])
        with f.request(path) as r:
            self.assertNotIn(b'"days"', r.read())
        headers, _ = f.authenticated_headers()
        with f.request(path, headers=headers) as r:
            data = json.load(r)
        self.assertEqual('history-http', data['name'])
        self.assertEqual(24, len(data['days'][0]['hours']))
        self.assertNotIn('token', json.dumps(data))
        with self.assertRaises(urllib.error.HTTPError) as exc:
            f.request('/api/v1/users/999999/traffic-history', headers=headers)
        self.assertEqual(404, exc.exception.code)
        exc.exception.close()
        self.assertEqual(('user-traffic-history', ('1',)), match_mobile_route('GET', '/api/v1/mobile/users/1/traffic-history'))
