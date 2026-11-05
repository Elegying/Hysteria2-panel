"""External upstream parity, credential isolation and user-only restore."""
import json
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import hysteria2_panel as panel
from tests import test_panel as fixtures

NODES = [{"label": "Fixture upstream", "uri": "anytls://fixture-secret@upstream.example.test:443?peer=tls.example.test#Fixture", "enabled": True}]


class ExternalHttpTests(unittest.TestCase):
    setUp = fixtures.PanelHttpTests.setUp
    tearDown = fixtures.PanelHttpTests.tearDown
    request = fixtures.PanelHttpTests.request
    authenticated_headers = fixtures.PanelHttpTests.authenticated_headers

    def test_admin_preview_publish_redaction_and_revision(self):
        headers, csrf = self.authenticated_headers()
        body = {"csrf": csrf, "revision": 0, "nodes": json.dumps(NODES)}
        with self.request('/subscriptions/external/preview', body, headers) as response:
            self.assertNotIn(b'fixture-secret', response.read())
        self.assertEqual(0, self.db.get_external_nodes()['revision'])
        with self.request('/subscriptions/external', body, headers) as response:
            self.assertEqual(1, json.load(response)['revision'])
        with self.request('/subscriptions/external', headers=headers) as response:
            data = json.load(response)
        self.assertNotIn('uri', data['nodes'][0])
        self.assertNotIn('fixture-secret', json.dumps(data))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/subscriptions/external', body, headers)
        self.assertEqual(400, caught.exception.code)
        caught.exception.close()
        node = dict(data['nodes'][0], label='Renamed', uri='')
        with self.request('/subscriptions/external', {"csrf": csrf, "revision": 1, "nodes": json.dumps([node])}, headers):
            pass
        self.assertIn('fixture-secret', self.db.get_external_nodes()['nodes'][0]['uri'])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/subscriptions/external', dict(body, csrf='bad'), headers)
        self.assertEqual(403, caught.exception.code)
        caught.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/subscriptions/external', follow_redirects=False)
        self.assertIn(caught.exception.code, (302, 303))
        caught.exception.close()

    def test_standard_unchanged_premium_formats_and_disabled_subscription(self):
        standard = self.db.create_proxy_user('standard')
        premium = self.db.create_proxy_user('premium', user_type=1, device_limit=7)
        standard_sub = self.db.ensure_subscription(standard['id'])
        premium_sub = self.db.ensure_subscription(premium['id'])
        path = '/sub/' + standard_sub['token'] + '?format=clash'
        with self.request(path) as response:
            before = response.read()
        self.db.publish_external_nodes(NODES, 0)
        with self.request(path) as response:
            self.assertEqual(before, response.read())
        for output in ('raw', 'clash', 'base64'):
            with self.request('/sub/' + premium_sub['token'] + '?format=' + output) as response:
                body = response.read()
                self.assertIn('external-usage=unknown', response.headers['X-Traffic-Scope'])
                if output == 'clash':
                    self.assertEqual('anytls', json.loads(body)['proxies'][0]['type'])
                elif output == 'raw':
                    self.assertIn(b'anytls://fixture-secret@', body)
                else:
                    self.assertIn(b'anytls://fixture-secret@', panel.base64.b64decode(body))
        self.assertEqual(7, self.db.get_proxy_user(premium['id'])['device_limit'])
        with self.db._connect() as connection:
            connection.execute('UPDATE subscriptions SET enabled=0 WHERE id=?', (premium_sub['id'],))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/sub/' + premium_sub['token'])
        self.assertEqual(403, caught.exception.code)
        caught.exception.close()

    def test_cipher_tampering_and_wrong_key_rejected(self):
        encoded = panel.encode_external_nodes(NODES, self.db.hmac_key)
        self.assertNotIn('fixture-secret', encoded)
        self.assertEqual(panel.validate_external_nodes(NODES), panel.decode_external_nodes(encoded, self.db.hmac_key))
        with self.assertRaises(ValueError):
            panel.decode_external_nodes(encoded, b'z' * 32)
        envelope = json.loads(encoded)
        payload = bytearray(panel.base64.b64decode(envelope['payload']))
        payload[-1] ^= 1
        envelope['payload'] = panel.base64.b64encode(payload).decode()
        with self.assertRaises(ValueError):
            panel.decode_external_nodes(json.dumps(envelope), self.db.hmac_key)

    def test_user_backup_omits_upstreams_and_restore_rekeys_target(self):
        user = self.db.create_proxy_user('migrate', user_type=1, device_limit=9, traffic_limit_bytes=123456)
        sub = self.db.ensure_subscription(user['id'])
        self.db.add_traffic({'migrate': {'tx': 123, 'rx': 456}})
        self.db.publish_external_nodes(NODES, 0)
        archive = self.backup_manager.create_archive()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, paths = self.backup_manager._extract_archive(archive, root / 'incoming')
            with sqlite3.connect(paths['data/panel.db']) as connection:
                self.assertEqual(0, connection.execute('SELECT COUNT(*) FROM external_subscription_nodes').fetchone()[0])
            key = b'z' * 32
            target = panel.Database(root / 'target.db', key)
            target.initialize()
            target_nodes = [dict(NODES[0], label='Target configuration')]
            target.publish_external_nodes(target_nodes, 0)
            cert, private = fixtures.create_test_certificate(root)
            env = root / 'panel.env'
            env.write_text('HY2PANEL_HMAC_KEY=' + key.hex() + '\nHY2PANEL_CERT_PIN=old\n')
            env.chmod(0o600)
            manager = panel.BackupManager(target, key, cert, private, '8.8.8.8', 19999, work_dir=root / 'work')
            manager.apply_archive(archive, env, root / 'rollback')
            restored = panel.Database(target.path, self.db.hmac_key)
            self.assertEqual(panel.validate_external_nodes(target_nodes), restored.get_external_nodes()['nodes'])
            self.assertEqual(1, restored.get_external_nodes()['revision'])
            self.assertEqual(sub['token'], restored.ensure_subscription(user['id'])['token'])
            result = restored.get_proxy_user(user['id'])
            self.assertEqual((123, 456, 9, 123456), tuple(result[k] for k in ('tx_bytes', 'rx_bytes', 'device_limit', 'traffic_limit_bytes')))
            with self.assertRaises(ValueError):
                target.get_external_nodes()

    def test_bad_target_credentials_abort_without_replacing_users(self):
        user = self.db.create_proxy_user('keep')
        archive = self.backup_manager.create_archive()
        with self.db._connect() as connection:
            connection.execute("INSERT INTO external_subscription_nodes VALUES (1, 'broken', 1)")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, paths = self.backup_manager._extract_archive(archive, root / 'incoming')
            with self.assertRaises(panel.BackupValidationError):
                self.backup_manager._stage_user_restore(paths['data/panel.db'], self.db.path, b'z' * 32)
        self.assertEqual('keep', self.db.authenticate_token(user['token']))

    def test_corrupt_external_config_does_not_break_standard_subscription(self):
        user = self.db.create_proxy_user('normal')
        sub = self.db.ensure_subscription(user['id'])
        with patch.object(self.db, 'get_external_nodes', side_effect=ValueError('invalid')):
            with self.request('/sub/' + sub['token'] + '?format=clash') as response:
                self.assertTrue(json.load(response)['proxies'])
