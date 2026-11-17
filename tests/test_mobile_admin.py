"""Real HTTP contracts for the additive Android administration surface."""
import io
import hashlib
import base64
import json
import time
import unittest
import urllib.error
import zipfile
from unittest import mock

from hy2panel.admin_api import EXACT_ROUTES, PATTERN_ROUTES, match_admin_route
from tests import test_panel


class MobileAdminHttpTests(unittest.TestCase):
    def setUp(self):
        self.f = test_panel.PanelHttpTests('runTest')
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        _, login = self.f.mobile_json_request('POST', '/api/v1/mobile/auth/login', {
            'username': 'Elegy', 'password': 'admin-password',
            'deviceId': 'admin-parity-tests', 'deviceName': 'Test device',
        })
        self.token = login['data']['accessToken']
        self.api = '/api/v1/mobile'

    def request(self, method, path, data=None, token=True):
        try:
            return self.f.mobile_json_request(method, self.api + path, data,
                                              access_token=self.token if token else '')
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_all_exact_routes_require_bearer_and_no_browser_cookie_is_issued(self):
        for (method, path), _route in EXACT_ROUTES.items():
            with self.subTest(path=path):
                status, body = self.request(method, path[len(self.api):], {} if method == 'POST' else None, token=False)
                self.assertEqual(401, status)
                self.assertEqual('SESSION_EXPIRED', body['error']['code'])
        headers, _ = self.f.authenticated_headers()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.f.request(self.api + '/settings', headers=headers)
        with caught.exception as response:
            self.assertEqual(401, response.code)
            self.assertNotIn('Set-Cookie', response.headers)

    def test_settings_and_budgets_reads_are_json_and_do_not_expose_credentials(self):
        for path in ('/settings', '/budgets', '/subscriptions', '/subscriptions/defaults', '/subscriptions/external'):
            status, body = self.request('GET', path)
            self.assertEqual(200, status, path)
            self.assertIsNone(body['error'])
            self.assertNotIn('privateKey', json.dumps(body))
        state = self.request('GET', '/settings')[1]['data']
        self.assertIn('certificate', state)
        self.assertIn('hopping', state)
        self.assertEqual('not_configured', state['offsiteBackup']['state'])

    def test_budget_validation_and_readback(self):
        origin = self.f.application.usage_manager.local_origin_id
        path = '/usage-origins/' + origin + '/budget'
        valid = {'limitGiB': 300, 'warningPercent': 80, 'usedGiB': '1.5', 'resetDay': 15}
        self.assertEqual(200, self.request('POST', path, valid)[0])
        items = self.request('GET', '/budgets')[1]['data']['items']
        self.assertEqual(300 * 1024**3, next(b for b in items if b['origin_id'] == origin)['limit_bytes'])
        for invalid in ({**valid, 'limitGiB': True}, {**valid, 'usedGiB': 1.5}, {**valid, 'unexpected': 1}):
            self.assertEqual(400, self.request('POST', path, invalid)[0])

    def test_subscription_defaults_and_per_user_nodes(self):
        user = self.f.db.create_proxy_user('api-user')
        sub = self.f.db.ensure_subscription(user['id'])
        original = self.f.db.recover_subscription_token(sub['id'])
        node = {'label': 'API test', 'host': 'node.example.com', 'port': 443,
                'pin_sha256': 'a' * 64, 'enabled': True}
        self.assertEqual(200, self.request('POST', '/subscriptions/defaults', {'nodes': [node]})[0])
        self.assertEqual(200, self.request('POST', '/subscriptions/%s/nodes' % sub['id'], {'nodes': [node]})[0])
        self.assertEqual(original, self.f.db.recover_subscription_token(sub['id']))
        self.assertEqual(400, self.request('POST', '/subscriptions/defaults', {'nodes': [{**node, 'port': True}]})[0])
        self.assertEqual(400, self.request('POST', '/subscriptions/%s/delete' % sub['id'], {'confirm': 'wrong'})[0])
        self.assertEqual(200, self.request('POST', '/subscriptions/%s/disable' % sub['id'], {'confirm': str(sub['id'])})[0])
        self.assertFalse(self.f.db.get_subscription(subscription_id=sub['id'])['enabled'])
        self.assertEqual(200, self.request('POST', '/subscriptions/%s/enable' % sub['id'], {'confirm': str(sub['id'])})[0])

    def test_external_preview_redaction_revision_and_validation(self):
        payload = {'revision': 0, 'nodes': [{'label': 'external', 'enabled': True,
                    'uri': 'anytls://private-password@node.example.com:443?insecure=0'}]}
        status, result = self.request('POST', '/subscriptions/external/preview', payload)
        self.assertEqual(200, status)
        self.assertNotIn('private-password', json.dumps(result))
        status, result = self.request('POST', '/subscriptions/external', payload)
        self.assertEqual(200, status)
        revision = result['data']['revision']
        self.assertEqual(409, self.request('POST', '/subscriptions/external', payload)[0])
        public = self.request('GET', '/subscriptions/external')[1]['data']
        self.assertNotIn('private-password', json.dumps(public))
        self.assertEqual(200, self.request('POST', '/subscriptions/external', {
            'revision': revision, 'nodes': [{'id': 0, 'label': 'renamed', 'enabled': True}],
        })[0])
        bad = self.request('POST', '/subscriptions/external/preview', {
            'revision': revision + 1, 'nodes': [{'label': 'bad', 'enabled': True, 'uri': 'not-a-uri-private-password'}],
        })
        self.assertEqual(400, bad[0])
        self.assertNotIn('private-password', json.dumps(bad))

    def test_diagnostics_and_remote_operations_use_existing_guards(self):
        f = self.f
        issued = f.application.node_enrollment_service.create('remote', '8.8.4.9', 10, 'Elegy')
        node = issued['nodeId']
        with f.db._connect() as connection:
            connection.execute("UPDATE nodes SET policy_state='protocol_ready',status='pending_verification',verified_at=1 WHERE node_id=?", (node,))
        path = '/nodes/' + node + '/operations/restart'
        self.assertEqual(409, self.request('POST', path, {'confirm': node})[0])
        f.db.server_monitor.accept(node, dict(cpu=1, memory=2, disk=3, uptime=10, observedAt=int(time.time())))
        self.assertEqual(400, self.request('POST', path, {'confirm': 'wrong'})[0])
        status, body = self.request('POST', path, {'confirm': node})
        self.assertEqual(202, status)
        self.assertIn('commandId', body['data'])
        self.assertEqual(409, self.request('POST', path, {'confirm': node})[0])
        with mock.patch.object(f.application.line_monitor, 'request', return_value=(True, 'started')) as request:
            self.assertEqual(202, self.request('POST', '/usage-origins/node:' + node + '/diagnostics', {})[0])
            request.assert_called_once_with('node:' + node)
        self.assertEqual(404, self.request('POST', '/usage-origins/node:' + 'f' * 32 + '/diagnostics', {})[0])

    def test_update_check_and_apply_are_bound_to_checked_target(self):
        self.assertEqual(409, self.request('POST', '/updates/apply', {'confirm': 'UPDATE_PANEL', 'target': 'v9.0.0'})[0])
        status, body = self.request('POST', '/updates/check', {})
        self.assertEqual(200, status)
        target = body['data']['latest']
        self.assertEqual(400, self.request('POST', '/updates/apply', {'target': target})[0])
        self.assertEqual(409, self.request('POST', '/updates/apply', {'confirm': 'UPDATE_PANEL', 'target': 'v9.0.0'})[0])
        self.assertEqual(202, self.request('POST', '/updates/apply', {'confirm': 'UPDATE_PANEL', 'target': target})[0])

    def test_hopping_egress_and_global_reset_require_confirmation(self):
        for path in ('/port-hopping/enable', '/egress/full', '/users/reset-traffic', '/usage-origins/legacy-unattributed/delete'):
            self.assertEqual(400, self.request('POST', path, {})[0], path)
        with mock.patch.object(self.f.application.port_hopping_controller, 'set_enabled', return_value={'enabled': True}) as setter:
            self.assertEqual(200, self.request('POST', '/port-hopping/enable', {'confirm': 'LOCAL_NODE'})[0])
            setter.assert_called_once_with(True)
        self.assertEqual(200, self.request('POST', '/egress/full', {'confirm': 'LOCAL_NODE'})[0])
        self.assertEqual(200, self.request('POST', '/users/reset-traffic', {'confirm': 'RESET_TRAFFIC', 'group': 'standard'})[0])
        self.assertEqual(200, self.request('POST', '/usage-origins/legacy-unattributed/delete', {'confirm': 'DELETE_UNATTRIBUTED'})[0])

    def test_backup_binary_and_restore_stream_share_validation(self):
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
        with self.f.request(self.api + '/backup', raw_data=b'{}', headers=headers) as response:
            self.assertEqual(200, response.status)
            self.assertIn('application/zip', response.headers['Content-Type'])
            body = response.read()
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertIn('manifest.json', archive.namelist())
        headers['Content-Type'] = 'application/zip'
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.f.request(self.api + '/restore', raw_data=body, headers=headers)
        with caught.exception as response:
            self.assertEqual(400, response.code)
        headers['X-HY2Panel-Confirm'] = 'RESTORE'
        with self.f.request(self.api + '/restore', raw_data=body, headers=headers) as response:
            self.assertEqual(202, response.status)
            self.assertEqual('queued', json.load(response)['data']['status'])

    def test_maintenance_blocks_writes_but_not_reads(self):
        self.assertTrue(self.f.application.begin_maintenance())
        try:
            self.assertEqual(503, self.request('POST', '/updates/check', {})[0])
            self.assertEqual(200, self.request('GET', '/subscriptions/defaults')[0])
        finally:
            self.f.application.finish_maintenance()

    def test_node_administration_routes_are_closed_and_typed(self):
        node = 'a' * 32
        for suffix in ('verify', 'revoke', 'protocol/enable', 'lifecycle/drain', 'data-plane/bootstrap', 'data-plane/canary/pass', 'data-plane/dns/admit'):
            self.assertEqual(401, self.request('POST', '/nodes/' + node + '/' + suffix, {}, token=False)[0])
        self.assertIsNone(match_admin_route('POST', self.api + '/nodes/' + node + '/operations/exec')[0])
        self.assertIsNone(match_admin_route('POST', self.api + '/subscriptions/' + '9' * 19 + '/delete')[0])
        self.assertTrue(PATTERN_ROUTES)

    def test_node_verification_protocol_and_revocation_persist_state(self):
        node = self.f.application.node_enrollment_service.create('remote', '8.8.4.9', 10, 'Elegy')['nodeId']
        key = bytes.fromhex('302a300506032b6570032100') + b'x' * 32
        with self.f.db._connect() as connection:
            connection.execute("UPDATE nodes SET status='pending_verification', public_key=?, last_heartbeat_at=? WHERE node_id=?",
                               (base64.b64encode(key).decode(), int(time.time()), node))
        prefix = '/nodes/' + node
        self.assertEqual(409, self.request('POST', prefix + '/protocol/enable', {'confirm': node})[0])
        self.assertEqual(409, self.request('POST', prefix + '/verify', {'fingerprint': '0' * 64})[0])
        self.assertEqual(200, self.request('POST', prefix + '/verify', {'fingerprint': hashlib.sha256(key).hexdigest()})[0])
        self.assertEqual(200, self.request('POST', prefix + '/protocol/enable', {'confirm': node})[0])
        self.assertEqual('protocol_ready', self.f.db.get_node_for_heartbeat(node)['policy_state'])
        self.assertEqual(409, self.request('POST', prefix + '/data-plane/bootstrap', {'confirm': node})[0])
        self.assertEqual(200, self.request('POST', prefix + '/protocol/disable', {'confirm': node})[0])
        self.assertEqual(200, self.request('POST', prefix + '/revoke', {'confirm': node})[0])
        self.assertEqual('revoked', self.f.db.get_node_for_heartbeat(node)['status'])
        self.assertEqual(409, self.request('POST', prefix + '/protocol/enable', {'confirm': node})[0])

    def test_restore_rejects_invalid_zip_without_queueing(self):
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/zip',
                   'X-HY2Panel-Confirm': 'RESTORE'}
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.f.request(self.api + '/restore', raw_data=b'not-a-backup', headers=headers)
        with caught.exception as response:
            self.assertEqual(400, response.code)
            self.assertEqual('RESTORE_FAILED', json.load(response)['error']['code'])
        self.assertEqual(0, self.f.application.restore_controller.queued)
        self.assertEqual(200, self.request('POST', '/updates/check', {})[0])
