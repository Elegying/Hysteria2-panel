import base64
import json
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch
from pathlib import Path

import hysteria2_panel as panel
from tests import test_panel as fixtures


class SubscriptionBackupTests(unittest.TestCase):
    setUp = fixtures.PanelHttpTests.setUp
    tearDown = fixtures.PanelHttpTests.tearDown
    request = fixtures.PanelHttpTests.request

    def test_hostname_collision_blocks_restore_but_allows_backup(self):
        user = self.db.create_proxy_user("hostname-guard")
        subscription = self.db.ensure_subscription(user["id"])
        manager = self.backup_manager
        with patch.object(panel.socket, "gethostname", return_value=manager.public_host):
            archive = manager.create_archive()
            with self.assertRaisesRegex(panel.BackupValidationError, "主机名"):
                manager.validate_archive(archive, require_compatible_endpoint=True)
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                env = root / "panel.env"
                env.write_text("unchanged")
                with self.assertRaisesRegex(panel.BackupValidationError, "主机名"):
                    manager.apply_archive(archive, env_file=env, backup_root=root / "backup")
                self.assertEqual(env.read_text(), "unchanged")
            self.assertEqual(self.db.ensure_subscription(user["id"]), subscription)
            self.assertEqual(self.db.authenticate_token(user["token"]), "hostname-guard")
        manager.validate_archive(archive, require_compatible_endpoint=True)

    def test_restore_to_new_hmac_keeps_original_subscription_and_proxy_credentials(
        self,
    ):
        user = self.db.create_proxy_user(
            "migrated", allow_udp_443=True, expires_at=4102444800
        )
        sub = self.db.ensure_subscription(user["id"])
        self.db.add_traffic({"migrated": {"tx": 123, "rx": 456}})
        nodes = [
            {
                "label": "私家车",
                "host": "vpn.example.test",
                "port": 443,
                "pin_sha256": "ab" * 32,
            }
        ]
        self.db.set_subscription_defaults(nodes)
        custom = self.db.create_proxy_user("custom", allow_udp_443=True)
        custom_sub = self.db.ensure_subscription(custom["id"])
        self.db.set_subscription_nodes(custom_sub["id"], nodes)
        path = "/sub/" + sub["token"]
        with self.request(path) as response:
            before = response.read()
            usage = response.headers["Subscription-Userinfo"]
        advanced = self.db.create_proxy_user("advanced-backup", user_type=1, device_limit=100,
            starts_at=1893456000, expires_at=4102444800)
        advanced_sub = self.db.ensure_subscription(advanced["id"])
        with self.db._connect() as connection:
            connection.execute("INSERT INTO premium_node_profiles(node_id,region,label,host,port,identity_json) VALUES (?,?,?,?,?,?)",
                ("ab"*16,"hk","私家车-香港-专线","hk.example.test",19999,None))
        archive = self.backup_manager.create_archive()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = b"x" * 32
            target = panel.Database(root / "panel.db", key)
            target.initialize()
            cert, private = fixtures.create_test_certificate(root)
            lock = root / "lock"
            lock.touch(mode=0o600)
            manager = panel.BackupManager(
                database=target,
                hmac_key=key,
                tls_cert=cert,
                tls_key=private,
                public_host="8.8.8.8",
                hysteria_port=19999,
                node_name="new node",
                work_dir=root / "work",
                maintenance_lock_path=lock,
                maintenance_lock_owner=__import__("os").geteuid(),
                maintenance_lock_mode=0o600,
            )
            env = root / "panel.env"
            env.write_text(
                "HY2PANEL_HMAC_KEY=" + key.hex() + "\nHY2PANEL_CERT_PIN=old\n"
            )
            env.chmod(0o600)
            original_cert, original_key = self.backup_manager.tls_cert.read_bytes(), self.backup_manager.tls_key.read_bytes()
            manager.apply_archive(archive, env_file=env, backup_root=root / "backups")
            self.assertEqual(original_cert, cert.read_bytes())
            self.assertEqual(original_key, private.read_bytes())
            restored = panel.Database(target.path, self.db.hmac_key)
            restored.initialize()
            self.assertIn(self.db.hmac_key.hex(), env.read_text())
            self.assertEqual(advanced_sub, restored.ensure_subscription(advanced["id"]))
            self.assertEqual(1893456000, restored.get_proxy_user(advanced["id"])["starts_at"])
            self.assertEqual(1, restored.get_proxy_user(advanced["id"])["user_type"])
            with restored._connect() as connection:
                self.assertEqual(0, connection.execute("SELECT count(*) FROM premium_node_profiles").fetchone()[0])
            self.assertEqual(sub, restored.ensure_subscription(user["id"]))
            self.assertEqual(custom_sub, restored.ensure_subscription(custom["id"]))
            self.assertEqual("migrated", restored.authenticate_token(user["token"]))
            self.assertEqual([], restored.list_subscription_nodes(custom_sub["id"]))
            self.assertIsNone(restored.get_subscription_defaults())
            self.assertEqual(100, restored.get_proxy_user(advanced["id"])["device_limit"])
            self.assertEqual(123, restored.get_proxy_user(user["id"])["tx_bytes"])
            self.assertEqual(456, restored.get_proxy_user(user["id"])["rx_bytes"])
            restored.set_subscription_defaults(nodes)
            original = self.application.database
            self.application.database = restored
            try:
                with self.request(path) as response:
                    self.assertEqual(before, response.read())
                    self.assertEqual(usage, response.headers["Subscription-Userinfo"])
                # Renewed certificate changes only the node pin, never the subscription identity.
                (root / "renewed").mkdir()
                fresh_cert, _ = fixtures.create_test_certificate(root / "renewed")
                pin = manager._certificate_pin(Path(fresh_cert).read_bytes())
                nodes[0]["pin_sha256"] = pin
                restored.set_subscription_defaults(nodes)
                with self.request(path) as response:
                    uri = base64.b64decode(response.read()).decode()
                self.assertEqual(
                    pin,
                    urllib.parse.parse_qs(urllib.parse.urlsplit(uri).query)[
                        "pinSHA256"
                    ][0],
                )
                with self.request(path + "?format=clash") as response:
                    self.assertEqual(
                        pin, json.load(response)["proxies"][0]["fingerprint"]
                    )
                self.assertEqual(sub, restored.ensure_subscription(user["id"]))
            finally:
                self.application.database = original

    def test_backup_preserves_local_identity_and_requires_original_endpoints(self):
        import zipfile
        manager = self.backup_manager
        manager.subscription_base_url = "https://subscriptions.example.test:19999"
        with patch.object(panel.PortHoppingController, "status", return_value={"enabled": True}):
            archive = manager.create_archive()
        with zipfile.ZipFile(archive) as package:
            self.assertEqual({"manifest.json", "data/panel.db", "secrets/hmac-key.hex", "tls/server.crt", "tls/server.key"}, set(package.namelist()))
            manifest = json.loads(package.read("manifest.json"))
            self.assertEqual(3, manifest["formatVersion"])
            self.assertTrue(manifest["source"]["portHoppingEnabled"])
            self.assertEqual(manager.subscription_base_url, manifest["source"]["subscriptionBaseUrl"])
            self.assertEqual(manager.tls_cert.read_bytes(), package.read("tls/server.crt"))
            self.assertEqual(manager.tls_key.read_bytes(), package.read("tls/server.key"))
        original_host, original_port = manager.public_host, manager.hysteria_port
        manager.public_host = "replacement.example.test"
        with self.assertRaisesRegex(panel.BackupValidationError, "域名"):
            manager.validate_archive(archive, require_compatible_endpoint=True)
        manager.public_host = original_host
        manager.hysteria_port = 24443
        with self.assertRaisesRegex(panel.BackupValidationError, "端口"):
            manager.validate_archive(archive, require_compatible_endpoint=True)
        manager.hysteria_port = original_port
        manager.validate_archive(archive, require_compatible_endpoint=True)
        for address in ("", "http://subscriptions.example.test:19999", "https://subscriptions.example.test:24443"):
            manager.subscription_base_url = address
            with self.subTest(address=address), self.assertRaisesRegex(panel.BackupValidationError, "订阅"):
                manager.validate_archive(archive, require_compatible_endpoint=True)

    def test_invalid_subscription_identity_rejected_before_restore(self):
        user = self.db.create_proxy_user("broken")
        self.db.ensure_subscription(user["id"])
        with self.db._connect() as connection:
            connection.execute("UPDATE subscriptions SET token_seed=?", (b"z" * 32,))
        with self.assertRaisesRegex(panel.BackupValidationError, "订阅签名"):
            self.backup_manager._validate_database_path(self.db.path, self.db.hmac_key)
