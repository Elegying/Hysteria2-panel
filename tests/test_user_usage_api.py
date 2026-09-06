"""Account usage contract over real local TLS, with synthetic Hysteria sources."""
import concurrent.futures
import hashlib
import http.client
import json
import secrets
import socket
import sqlite3
import ssl
import tempfile
import threading
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import hysteria2_panel as panel
from tests.test_panel import PolicyStatsClient, create_test_certificate
from tests.test_distributed_control import DistributedControlCase


class UserUsageRateLimiterTests(unittest.TestCase):
    def test_limits_are_atomic_bounded_and_expire(self):
        now = [0]
        limiter = panel.UserUsageRateLimiter(clock=lambda: now[0])
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda _: limiter.consume('same', 12), range(100)))
        self.assertEqual(12, results.count(0))
        for i in range(4095):
            self.assertEqual(0, limiter.consume(str(i), 1))
        self.assertGreater(limiter.consume('overflow', 1), 0)
        self.assertEqual(4096, len(limiter.windows))
        now[0] = 60
        self.assertEqual(0, limiter.consume('same', 12))
        self.assertEqual(1, len(limiter.windows))


class UserUsageApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = panel.Database(Path(self.temp.name) / 'panel.db', secrets.token_bytes(32))
        self.db.initialize()
        # Runtime-generated legacy password: never a fixture credential/snapshot.
        self.token = secrets.token_urlsafe(24)
        self.user = self.db.create_proxy_user('alice', token=self.token)
        self.other = self.db.create_proxy_user('bob')
        self.stats = PolicyStatsClient()
        self.manager = panel.UsageManager(self.db, self.stats)
        self.manager.collect_once()
        self.app = panel.PanelApplication(
            self.db, 'node.example.test', 443, 'a' * 64, self.stats,
            usage_manager=self.manager,
        )
        self.server = panel.make_panel_server(('127.0.0.1', 0), self.app)
        cert, key = create_test_certificate(self.temp.name)
        self.server.tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.server.tls_context.load_cert_chain(cert, key)
        self.context = ssl.create_default_context(cafile=str(cert))
        self.context.check_hostname = False  # fixture CN differs from loopback IP
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def request(self, token=None, path='/api/v1/user/usage', method='GET', headers=None):
        request_headers = {'Authorization': 'Bearer ' + (self.token if token is None else token)}
        request_headers.update(headers or {})
        connection = http.client.HTTPSConnection(
            '127.0.0.1', self.server.server_port, context=self.context, timeout=4
        )
        try:
            connection.request(method, path, headers=request_headers)
            response = connection.getresponse()
            body = response.read()
            return response.status, dict(response.getheaders()), json.loads(body)
        finally:
            connection.close()

    def assert_error(self, result, status, code):
        self.assertEqual(status, result[0])
        self.assertEqual({'apiVersion': 1, 'error': {'code': code}}, result[2])
        self.assertEqual('no-store', result[1]['Cache-Control'])
        self.assertNotIn(self.token, json.dumps(result))

    def state_digest(self):
        with self.db._connect() as connection:
            # Includes ledger, leases, commands, configuration, audit and identities.
            raw = '\n'.join(connection.iterdump()).encode()
        return hashlib.sha256(raw).hexdigest()

    def test_old_uri_password_and_zero_account_are_compatible_and_read_only(self):
        uri = panel.build_connection_uri('node.example.test', 443, self.token, 'a'*64, 'node')
        password = urllib.parse.unquote(urllib.parse.urlsplit(uri).username)
        self.assertEqual(self.token, password)
        self.assertIsNone(self.db.recover_proxy_token(self.user['id']))
        before = self.state_digest()
        with mock.patch.object(self.stats, 'collect_and_clear', side_effect=AssertionError('query collected')), \
             mock.patch.object(self.stats, 'online', side_effect=AssertionError('query sampled')), \
             mock.patch.object(self.stats, 'kick_many', side_effect=AssertionError('query kicked')):
            status, headers, payload = self.request(password)
        self.assertEqual(200, status)
        self.assertEqual({'scope': 'account', 'usedBytes': 0,
                          'trafficLimitBytes': 268435456000,
                          'onlineDevices': 0, 'deviceLimit': 3}, payload['data'])
        self.assertEqual({'apiVersion', 'data', 'meta'}, set(payload))
        self.assertTrue(payload['meta']['complete'])
        self.assertEqual('no-store', headers['Cache-Control'])
        self.assertEqual(before, self.state_digest())
        self.assertEqual('alice', self.db.authenticate_token(password))
        self.assertTrue(self.manager.authorize('alice'))

    def test_over_limit_disabled_and_full_devices_keep_identity_access(self):
        self.db.add_traffic({'alice': {'tx': 300000000000, 'rx': 9},
                             'bob': {'tx': 700, 'rx': 800}})
        self.stats.online_values = {'alice': 8, 'bob': 2}
        self.manager.collect_once()
        self.db.set_proxy_user_enabled(self.user['id'], False)
        before = self.state_digest()
        result = self.request()
        self.assertEqual(200, result[0])
        self.assertEqual(300000000009, result[2]['data']['usedBytes'])
        self.assertEqual(8, result[2]['data']['onlineDevices'])
        self.assertEqual(before, self.state_digest())
        self.assertIsNone(self.db.authenticate_token(self.token))
        self.assertFalse(self.manager.authorize('alice'))

    def test_wrong_deleted_and_rotated_passwords_fail_immediately(self):
        self.assert_error(self.request(secrets.token_urlsafe(24)), 401, 'INVALID_CREDENTIALS')
        rotated = self.db.rotate_proxy_token(self.user['id'])
        self.assert_error(self.request(), 401, 'INVALID_CREDENTIALS')
        self.assertEqual(200, self.request(rotated['token'])[0])
        self.db.delete_proxy_user(self.user['id'])
        self.assert_error(self.request(rotated['token']), 401, 'INVALID_CREDENTIALS')

    def test_account_selectors_and_url_credentials_are_rejected_without_logging(self):
        with self.assertLogs(panel.LOGGER, level='INFO') as logs:
            for suffix in ('?user_id=' + str(self.other['id']), '?username=bob',
                           '?token=' + self.token, '/' + self.token):
                self.assert_error(self.request(path='/api/v1/user/usage' + suffix),
                                  400, 'INVALID_REQUEST')
        self.assertNotIn(self.token, '\n'.join(logs.output))
        self.assertNotIn('username=bob', '\n'.join(logs.output))
        self.assertNotIn('bob', json.dumps(self.request()[2]))

    def test_failures_and_stale_data_never_turn_into_zero_or_extend_expiry(self):
        first = self.request()[2]['meta']
        future = first['serverTime'] + 5
        with mock.patch('hysteria2_panel.time.time', return_value=future):
            second = self.request()[2]['meta']
        self.assertEqual(first['trafficObservedAt'], second['trafficObservedAt'])
        self.assertEqual(first['onlineObservedAt'], second['onlineObservedAt'])
        self.assertEqual(first['expiresAt'], second['expiresAt'])
        with mock.patch('hysteria2_panel.time.time', return_value=first['expiresAt']):
            self.assert_error(self.request(), 503, 'STATS_STALE')
        with mock.patch.object(self.stats, 'collect_and_clear', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):
                self.manager.collect_once()
        self.assert_error(self.request(), 503, 'STATS_UNAVAILABLE')
        self.manager.collect_once()
        with mock.patch.object(self.stats, 'online', side_effect=OSError('unavailable')):
            self.manager.collect_once()
        self.assert_error(self.request(), 503, 'STATS_UNAVAILABLE')

    def test_idle_account_uses_collection_clock_and_restart_requires_new_sample(self):
        with self.db._connect() as connection:
            connection.execute('UPDATE proxy_users SET updated_at = 1')
        self.assertEqual(200, self.request()[0])
        self.app.usage_manager = panel.UsageManager(self.db, self.stats)
        self.assert_error(self.request(), 503, 'STATS_UNAVAILABLE')
        self.app.usage_manager.collect_once()
        self.assertEqual(200, self.request()[0])

    def test_partial_local_sources_and_invalid_online_counts_are_unavailable(self):
        other_stats = PolicyStatsClient()
        combined = panel.CombinedHysteriaStatsClient(self.stats, other_stats)
        manager = panel.UsageManager(self.db, combined)
        self.app.usage_manager = manager
        self.stats.traffic_values = {'alice': {'tx': 11, 'rx': 13}}
        with mock.patch.object(other_stats, 'collect_and_clear', side_effect=OSError('down')):
            with self.assertRaises(panel.PartialTrafficCollectionError):
                manager.collect_once()
        self.assert_error(self.request(), 503, 'STATS_UNAVAILABLE')
        manager.collect_once()
        self.assertEqual(24, self.request()[2]['data']['usedBytes'])
        self.stats.online_values = {'alice': True}
        self.manager.collect_once()
        self.app.usage_manager = self.manager
        self.assert_error(self.request(), 503, 'STATS_UNAVAILABLE')

    def test_rate_limit_and_concurrency_do_not_mutate_business_state(self):
        before = self.state_digest()
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda _: self.request(), range(40)))
        successful = [r for r in results if r[0] == 200]
        limited = [r for r in results if r[0] == 429]
        self.assertTrue(successful)
        self.assertLessEqual(len(successful), 12)
        self.assertEqual(40, len(successful) + len(limited))
        for result in limited:
            self.assertGreaterEqual(int(result[1]['Retry-After']), 1)
        self.assertEqual(before, self.state_digest())
        self.assertTrue(self.manager.authorize('alice'))
        self.manager.collect_once()

    def test_full_http_slots_return_redacted_429_without_business_mutation(self):
        before = self.state_digest()
        for _ in range(8):
            self.app.user_usage_http_slots.acquire()
        try:
            with self.assertLogs(panel.LOGGER, level='INFO') as logs:
                result = self.request(path='/api/v1/user/usage?token=' + self.token)
            self.assert_error(result, 429, 'RATE_LIMITED')
            self.assertEqual('1', result[1]['Retry-After'])
            self.assertNotIn(self.token, '\n'.join(logs.output))
            self.assertEqual(before, self.state_digest())
        finally:
            for _ in range(8):
                self.app.user_usage_http_slots.release()
        self.assertEqual(200, self.request()[0])

    def test_busy_query_slots_do_not_wait_on_auth_or_collector_lock(self):
        self.manager.lock.acquire()
        try:
            start = time.monotonic()
            self.assertEqual(200, self.request()[0])
            self.assertLess(time.monotonic() - start, 1)
        finally:
            self.manager.lock.release()
        for _ in range(4):
            self.app.user_usage_slots.acquire()
        try:
            self.assert_error(self.request(), 429, 'RATE_LIMITED')
            self.assertTrue(self.manager.authorize('alice'))
        finally:
            for _ in range(4):
                self.app.user_usage_slots.release()

    def test_database_contention_and_expensive_read_are_bounded(self):
        with self.db._connect() as writer:
            writer.execute('BEGIN IMMEDIATE')
            writer.execute('UPDATE proxy_users SET tx_bytes = tx_bytes + 1')
            start = time.monotonic()
            self.assertEqual(200, self.request()[0])  # WAL reader never waits for writer
            self.assertLess(time.monotonic() - start, 1)
            writer.rollback()
        # Exercise sqlite VM deadline without sleeping inside the query path.
        with self.db._connect() as connection:
            connection.executescript('''
                ALTER TABLE proxy_users RENAME TO saved_users;
                CREATE VIEW proxy_users AS
                WITH RECURSIVE slow(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM slow WHERE x<100000000)
                SELECT saved_users.*, (SELECT SUM(x) FROM slow) AS work FROM saved_users
                WHERE work > 0;
            ''')
        start = time.monotonic()
        self.assert_error(self.request(), 503, 'STATS_UNAVAILABLE')
        self.assertLess(time.monotonic() - start, 1.5)

    def test_size_methods_headers_and_errors_do_not_leak(self):
        self.assert_error(self.request(headers={'Content-Length': '1'}), 400, 'INVALID_REQUEST')
        self.assert_error(self.request(headers={'X-Padding': 'x' * 8200}), 413, 'REQUEST_TOO_LARGE')
        self.assert_error(self.request(method='POST'), 405, 'METHOD_NOT_ALLOWED')
        self.assert_error(self.request(method='PUT'), 405, 'METHOD_NOT_ALLOWED')
        self.assert_error(self.request(headers={'Authorization': 'Bearer short'}), 401, 'INVALID_CREDENTIALS')
        with mock.patch.object(self.db, 'user_usage', side_effect=sqlite3.OperationalError(self.token)):
            with self.assertLogs(panel.LOGGER, level='INFO') as logs:
                self.assert_error(self.request(), 503, 'STATS_UNAVAILABLE')
        self.assertNotIn(self.token, '\n'.join(logs.output))

    def test_plain_http_rejects_and_admin_and_machine_routes_stay_private(self):
        plain = panel.make_panel_server(('127.0.0.1', 0), self.app)
        thread = threading.Thread(target=plain.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection('127.0.0.1', plain.server_port, timeout=2)
            conn.request('GET', '/api/v1/user/usage', headers={'Authorization': 'Bearer ' + self.token})
            response = conn.getresponse()
            self.assertEqual(403, response.status)
            self.assertEqual('HTTPS_REQUIRED', json.loads(response.read())['error']['code'])
            conn.close()
        finally:
            plain.shutdown()
            plain.server_close()
            thread.join(3)
        self.assertEqual(401, self.request(path='/api/v1/mobile/users')[0])
        self.assertNotEqual(200, self.request(path='/api/v1/node-traffic-batches', method='POST')[0])

    def test_duplicate_auth_and_malformed_request_line_never_echo_password(self):
        for raw in (
            ('GET /api/v1/user/usage?token=' + self.token + ' HTTP/invalid\r\n\r\n'),
            ('GET /api/v1/user/usage HTTP/1.1\r\nHost: localhost\r\n'
             'Authorization: Bearer ' + self.token + '\r\n'
             'Authorization: Bearer ' + self.other['token'] + '\r\n\r\n'),
        ):
            sock = self.context.wrap_socket(socket.socket(), server_hostname='vpn.example.test')
            sock.settimeout(4)
            sock.connect(('127.0.0.1', self.server.server_port))
            try:
                with self.assertLogs(panel.LOGGER, level='INFO') as logs:
                    sock.sendall(raw.encode())
                    received = b''
                    while True:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        received += chunk
                self.assertNotIn(self.token, '\n'.join(logs.output))
                self.assertNotIn(self.token.encode(), received)
                self.assertIn(b'"error"', received)
                self.assertNotIn(b'"data"', received)
            finally:
                sock.close()

    def test_client_response_examples_match_exact_wire_contract(self):
        examples = json.loads((Path(__file__).parents[1] /
                               'docs/examples/client-usage-v1.json').read_text())
        actual = self.request()[2]
        for example in examples:
            body = example['body']
            self.assertEqual(1, body['apiVersion'])
            if example['status'] == 200:
                self.assertEqual(set(actual), set(body))
                self.assertEqual(set(actual['data']), set(body['data']))
                self.assertEqual(set(actual['meta']), set(body['meta']))
                for key, value in body['data'].items():
                    if key != 'scope':
                        self.assertIs(type(value), int)
                        self.assertGreaterEqual(value, 0)
                self.assertTrue(body['meta']['complete'])
                self.assertEqual(min(body['meta']['trafficObservedAt'],
                                     body['meta']['onlineObservedAt']) + 30,
                                 body['meta']['expiresAt'])
            else:
                self.assertEqual({'apiVersion', 'error'}, set(body))
                self.assertEqual({'code'}, set(body['error']))

    def test_normalized_request_targets_cannot_bypass_usage_deadline(self):
        for target in ('  /api/v1/user/usage', '//api/v1/user/usage',
                       'https://localhost/api/v1/user/usage'):
            sock = self.context.wrap_socket(socket.socket(), server_hostname='vpn.example.test')
            sock.settimeout(4)
            sock.connect(('127.0.0.1', self.server.server_port))
            try:
                with mock.patch.object(self.server, '_arm_request_deadline',
                                       wraps=self.server._arm_request_deadline) as arm:
                    sock.sendall(('GET ' + target + ' HTTP/1.1\r\nHost: localhost\r\n'
                                  'Authorization: Bearer ' + self.token + '\r\n\r\n').encode())
                    response = http.client.HTTPResponse(sock)
                    response.begin()
                    response.read()
                    self.assertIn(response.status, (200, 400))
                    self.assertTrue(any(call.args[1] == 3 for call in arm.call_args_list))
            finally:
                sock.close()

    def test_slow_headers_have_deadline_and_leave_capacity_for_control(self):
        sock = self.context.wrap_socket(socket.socket(), server_hostname='vpn.example.test')
        sock.settimeout(5)
        sock.connect(('127.0.0.1', self.server.server_port))
        start = time.monotonic()
        try:
            sock.sendall(b'GET /api/v1/user/usage HTTP/1.1\r\nHost: localhost\r\n')
            self.assertEqual(200, self.request()[0])
            self.assertTrue(self.manager.authorize('alice'))
            self.assertEqual(b'', sock.recv(1024))
            self.assertLess(time.monotonic() - start, 4)
        finally:
            sock.close()


class UserUsageDistributedTests(DistributedControlCase):
    def setUp(self):
        super().setUp()
        self.token = secrets.token_urlsafe(24)
        self.user = self.db.create_proxy_user('alice', token=self.token)
        self.local = (self.now[0], self.now[0], {'alice': 1})

    def checkpoint(self, node_id, sequence=1, observed=None, online=2, traffic=None):
        observed = self.now[0] if observed is None else observed
        result = self.db.apply_node_traffic_batch(
            node_id, secrets.token_hex(16), traffic or {}, secrets.token_hex(32),
            accepted_at=self.now[0], observed_at=observed,
        )
        self.assertTrue(result['committed'])
        self.assertTrue(self.db.accept_node_online_snapshot(
            node_id, secrets.token_hex(16), sequence, observed, self.now[0],
            {'alice': online} if online else {}, secrets.token_hex(32), self.now[0],
        ))

    def query(self):
        return self.db.user_usage(self.db._fingerprint(self.token), self.local, self.now[0])

    def test_account_ledger_matches_origins_including_historical_nodes(self):
        self.db.apply_traffic_batch(secrets.token_hex(16), {'alice': {'tx': 7, 'rx': 11}})
        self.checkpoint(self.nodes[0], traffic={'alice': {'tx': 13, 'rx': 17}})
        self.checkpoint(self.nodes[1], online=3, traffic={'alice': {'tx': 19, 'rx': 23}})
        result = self.query()
        self.assertEqual(90, result['data']['usedBytes'])
        self.assertEqual(6, result['data']['onlineDevices'])
        with self.db._connect() as connection:
            self.assertEqual(90, connection.execute(
                "SELECT SUM(tx_bytes+rx_bytes) FROM usage_origin_users WHERE user_name='alice'"
            ).fetchone()[0])
            connection.execute("UPDATE nodes SET status='revoked' WHERE node_id=?", (self.nodes[1],))
        result = self.query()
        self.assertEqual(90, result['data']['usedBytes'])
        self.assertEqual(3, result['data']['onlineDevices'])
        self.db.reset_proxy_user_traffic(self.user['id'])
        self.assertEqual(0, self.query()['data']['usedBytes'])

    def test_missing_stale_standby_future_and_partial_sources_fail(self):
        self.checkpoint(self.nodes[0])
        with self.assertRaises(panel.UserUsageError):
            self.query()
        self.checkpoint(self.nodes[1], observed=self.now[0] - 31)
        with self.assertRaisesRegex(panel.UserUsageError, 'STATS_STALE'):
            self.query()
        self.checkpoint(self.nodes[1], sequence=2)
        self.assertTrue(self.query()['meta']['complete'])
        with self.db._connect() as connection:
            connection.execute('UPDATE node_usage_checkpoints SET traffic_observed_at=? WHERE node_id=?',
                               (self.now[0]+1, self.nodes[1]))
        with self.assertRaises(panel.UserUsageError):
            self.query()
        self.checkpoint(self.nodes[1], sequence=3)
        with self.db._connect() as connection:
            connection.execute("UPDATE nodes SET policy_state='standby' WHERE node_id=?", (self.nodes[1],))
        with self.assertRaisesRegex(panel.UserUsageError, 'STATS_INCOMPLETE'):
            self.query()

    def test_zero_collection_counts_and_batch_receive_time_does_not_refresh_old_data(self):
        self.local = (self.now[0], self.now[0], {})
        for node in self.nodes:
            self.checkpoint(node, online=0)
        self.assertEqual(0, self.query()['data']['usedBytes'])
        self.assertEqual(0, self.query()['data']['onlineDevices'])
        self.now[0] += 5
        self.assertEqual(self.now[0] + 25, self.query()['meta']['expiresAt'])
        self.checkpoint(self.nodes[0], sequence=2, observed=self.now[0]-40, online=0)
        with self.assertRaisesRegex(panel.UserUsageError, 'STATS_STALE'):
            self.query()

    def test_duplicate_batch_does_not_extend_collection_lifetime(self):
        for node in self.nodes:
            self.checkpoint(node)
        batch_id = secrets.token_hex(16)
        observed = self.now[0]
        traffic = {'alice': {'tx': 5, 'rx': 7}}
        first = self.db.apply_node_traffic_batch(
            self.nodes[0], batch_id, traffic, secrets.token_hex(32), observed,
            observed_at=observed,
        )
        self.assertFalse(first['duplicate'])
        self.assertTrue(self.db.accept_node_online_snapshot(
            self.nodes[0], secrets.token_hex(16), 2, observed, observed,
            {'alice': 2}, secrets.token_hex(32), observed,
        ))
        expires = self.query()['meta']['expiresAt']
        self.now[0] += 5
        duplicate = self.db.apply_node_traffic_batch(
            self.nodes[0], batch_id, traffic, secrets.token_hex(32), self.now[0],
            observed_at=self.now[0],
        )
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(expires, self.query()['meta']['expiresAt'])
        self.assertEqual(12, self.query()['data']['usedBytes'])

    def test_committed_batch_requires_following_online_snapshot_and_restart_invalidates(self):
        for node in self.nodes:
            self.checkpoint(node)
        self.db.apply_node_traffic_batch(self.nodes[0], secrets.token_hex(16), {},
                                        secrets.token_hex(32), self.now[0], observed_at=self.now[0])
        with self.assertRaisesRegex(panel.UserUsageError, 'STATS_INCOMPLETE'):
            self.query()
        self.checkpoint(self.nodes[0], sequence=2)
        self.assertTrue(self.query()['meta']['complete'])
        self.db.begin_runtime_epoch()
        with self.assertRaisesRegex(panel.UserUsageError, 'STATS_INCOMPLETE'):
            self.query()


if __name__ == '__main__':
    unittest.main()
