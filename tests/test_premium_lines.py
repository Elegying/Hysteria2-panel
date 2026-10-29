import json
import unittest
import urllib.error

from tests import test_panel as fixtures
from tests.test_distributed_control import (
    DistributedControlCase,
    DistributedAuthorizationTests,
)


class PremiumAuthorizationTests(DistributedControlCase):
    auth_payload = DistributedAuthorizationTests.auth_payload

    def prepare(self):
        self.accept_empty_snapshots()
        with self.db._connect() as connection:
            connection.execute(
                "UPDATE nodes SET tier='premium' WHERE node_id=?", (self.nodes[1],)
            )
        standard = self.db.create_proxy_user("ordinary")
        advanced = self.db.create_proxy_user("advanced", user_type=1, device_limit=100)
        return standard, advanced

    def test_cross_tier_denial_and_group_failure_isolation(self):
        ordinary, advanced = self.prepare()
        for user, node, expected, nonce in [
            (ordinary, 0, True, 31),
            (ordinary, 1, False, 32),
            (advanced, 0, False, 33),
            (advanced, 1, True, 34),
        ]:
            self.token = user["token"]
            decision = self.service.authorize(
                self.auth_payload(self.nodes[node], nonce), "203.0.113." + str(node + 1)
            )
            self.assertEqual(expected, decision["ok"])
        # stale ordinary node and local collector must not block the premium group
        self.local_available = False
        with self.db._connect() as connection:
            connection.execute(
                "DELETE FROM node_online_snapshots WHERE node_id=?", (self.nodes[0],)
            )
        self.token = advanced["token"]
        self.assertTrue(
            self.service.authorize(self.auth_payload(self.nodes[1], 35), "203.0.113.2")[
                "ok"
            ]
        )
        self.assertIsNone(self.db.authenticate_token(advanced["token"]))
        self.assertFalse(
            self.db.authorize_local_participant("advanced", {}, self.now[0])
        )

    def test_shared_one_hundred_slots_across_regions(self):
        _, advanced = self.prepare()
        with self.db._connect() as connection:
            connection.execute("UPDATE nodes SET tier='premium'")
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[0], 60, sequence=2, online={"advanced": 60}),
            "203.0.113.1",
        )
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[1], 61, sequence=2, online={"advanced": 39}),
            "203.0.113.2",
        )
        self.token = advanced["token"]
        self.assertTrue(
            self.service.authorize(self.auth_payload(self.nodes[0], 62), "203.0.113.1")[
                "ok"
            ]
        )
        self.assertFalse(
            self.service.authorize(self.auth_payload(self.nodes[1], 63), "203.0.113.2")[
                "ok"
            ]
        )

    def test_start_expiry_and_shared_quota(self):
        _, advanced = self.prepare()
        self.token = advanced["token"]
        with self.db._connect() as connection:
            connection.execute(
                "UPDATE proxy_users SET starts_at=? WHERE id=?",
                (self.now[0] + 1, advanced["id"]),
            )
        self.assertFalse(
            self.service.authorize(self.auth_payload(self.nodes[1], 40), "203.0.113.2")[
                "ok"
            ]
        )
        with self.db._connect() as connection:
            connection.execute(
                "UPDATE proxy_users SET starts_at=?,tx_bytes=traffic_limit_bytes WHERE id=?",
                (self.now[0] - 1, advanced["id"]),
            )
        self.assertFalse(
            self.service.authorize(self.auth_payload(self.nodes[1], 41), "203.0.113.2")[
                "ok"
            ]
        )
        with self.db._connect() as connection:
            connection.execute(
                "UPDATE proxy_users SET tx_bytes=0,expires_at=? WHERE id=?",
                (self.now[0], advanced["id"]),
            )
        self.assertFalse(
            self.service.authorize(self.auth_payload(self.nodes[1], 42), "203.0.113.2")[
                "ok"
            ]
        )


class PremiumSubscriptionTests(unittest.TestCase):
    setUp = fixtures.PanelHttpTests.setUp
    tearDown = fixtures.PanelHttpTests.tearDown
    request = fixtures.PanelHttpTests.request
    authenticated_headers = fixtures.PanelHttpTests.authenticated_headers

    def add_node(self, region):
        node = self.db.create_node_enrollment(
            "私家车-" + region + "-专线",
            "8.8.8.8",
            "admin",
            region * 32,
            1,
            2,
            tier="premium",
            region=region,
            subscription_host=region + ".example.test",
        )
        with self.db._connect() as c:
            c.execute(
                "UPDATE nodes SET status='pending_verification',verified_at=1,policy_state='protocol_ready',data_plane_state='dns_admitted' WHERE node_id=?",
                (node["node_id"],),
            )
            c.execute(
                "UPDATE premium_node_profiles SET identity_json=? WHERE node_id=?",
                (json.dumps({"certificateDerSha256": "ab" * 32}), node["node_id"]),
            )
        return node["node_id"]

    def test_four_nodes_dynamic_update_and_no_ordinary_fallback(self):
        advanced = self.db.create_proxy_user("advanced", user_type=1, device_limit=100)
        sub = self.db.ensure_subscription(advanced["id"])
        path = "/sub/" + sub["token"]
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request(path)
        self.assertEqual(404, err.exception.code)
        nodes = [self.add_node(r) for r in ("hk", "us", "jp", "sg")]
        with self.request(path + "?format=raw") as response:
            body = response.read().decode()
            self.assertEqual(4, len(body.splitlines()))
            self.assertIn(
                "total=268435456000", response.headers["Subscription-Userinfo"]
            )
        for region in ("hk", "us", "jp", "sg"):
            self.assertIn(region + ".example.test:19999", body)
        self.db.update_premium_node_profile(
            nodes[0], "香港新名字", "new-hk.example.com", 443
        )
        with self.request(path + "?format=raw") as response:
            self.assertIn("new-hk.example.com:443", response.read().decode())
        self.assertEqual(sub, self.db.ensure_subscription(advanced["id"]))
        ordinary = self.db.create_proxy_user("ordinary")
        ordinary_sub = self.db.ensure_subscription(ordinary["id"])
        with self.request("/sub/" + ordinary_sub["token"] + "?format=raw") as response:
            body = response.read().decode()
            self.assertNotIn("example.test", body)
            self.assertNotIn("new-hk", body)

    def test_independent_persistent_certificates_and_backup_profiles(self):
        nodes = []
        for region in ("hk", "us"):
            node = self.db.create_node_enrollment(
                region,
                "8.8.8.8",
                "admin",
                region * 32,
                1,
                2,
                tier="premium",
                region=region,
                subscription_host=region + ".example.test",
                port_hopping=region == "hk",
            )
            nodes.append(node["node_id"])

        def policy():
            return {"egressPolicy": "full"}

        first = self.db.get_or_create_node_identity(nodes[0], policy)
        second = self.db.get_or_create_node_identity(nodes[1], policy)
        self.assertNotEqual(
            first["certificateDerSha256"], second["certificateDerSha256"]
        )
        self.assertNotEqual(first["privateKeyPem"], second["privateKeyPem"])
        self.assertEqual(first, self.db.get_or_create_node_identity(nodes[0], policy))
        user = self.db.create_proxy_user(
            "migration-user", user_type=1, device_limit=100
        )
        subscription = self.db.ensure_subscription(user["id"])
        with self.db._connect() as c:
            c.execute(
                "UPDATE nodes SET status='pending_verification',verified_at=1,policy_state='protocol_ready',data_plane_state='dns_admitted'"
            )
        with self.request("/sub/" + subscription["token"] + "?format=raw") as response:
            before = response.read()
        archive = self.backup_manager.create_archive()
        import zipfile
        import sqlite3
        import tempfile

        with zipfile.ZipFile(archive) as z, tempfile.NamedTemporaryFile() as f:
            f.write(z.read("data/panel.db"))
            f.flush()
            with sqlite3.connect(f.name) as c:
                self.assertEqual(
                    2,
                    c.execute("SELECT COUNT(*) FROM premium_node_profiles").fetchone()[
                        0
                    ],
                )
                self.assertEqual(
                    first,
                    json.loads(
                        c.execute(
                            "SELECT identity_json FROM premium_node_profiles WHERE node_id=?",
                            (nodes[0],),
                        ).fetchone()[0]
                    ),
                )

            import hysteria2_panel as panel

            restored = panel.Database(f.name, self.db.hmac_key)
            restored.initialize()
            self.assertEqual([], restored.list_nodes())
            for region, identity in (("hk", first), ("us", second)):
                replacement = restored.create_node_enrollment(
                    "replacement",
                    "1.1.1.1",
                    "admin",
                    region * 32,
                    3,
                    4,
                    tier="premium",
                    region=region,
                    subscription_host="changed.example.test",
                    subscription_port=8443,
                )
                self.assertTrue(replacement["restored_profile"])
                self.assertEqual(
                    identity,
                    restored.get_or_create_node_identity(
                        replacement["node_id"], policy
                    ),
                )
                with restored._connect() as c:
                    c.execute(
                        "UPDATE nodes SET status='pending_verification',verified_at=1,policy_state='protocol_ready',data_plane_state='dns_admitted' WHERE node_id=?",
                        (replacement["node_id"],),
                    )
            self.assertEqual(subscription, restored.ensure_subscription(user["id"]))
            self.assertEqual(user["token"], restored.recover_proxy_token(user["id"]))
            original = self.application.database
            self.application.database = restored
            try:
                with self.request(
                    "/sub/" + subscription["token"] + "?format=raw"
                ) as response:
                    self.assertEqual(before, response.read())
            finally:
                self.application.database = original

    def test_group_reset_never_changes_other_users(self):
        normal = self.db.create_proxy_user("normal")
        premium = self.db.create_proxy_user("premium", user_type=1)
        self.db.add_traffic(
            {"normal": {"tx": 10, "rx": 20}, "premium": {"tx": 30, "rx": 40}}
        )
        self.db.reset_group_traffic(1)
        self.assertEqual(0, self.db.get_proxy_user(premium["id"])["tx_bytes"])
        self.assertEqual(10, self.db.get_proxy_user(normal["id"])["tx_bytes"])

    def test_web_advanced_defaults_start_and_separate_navigation(self):
        headers, csrf = self.authenticated_headers()
        with self.request(
            "/users",
            {
                "csrf": csrf,
                "name": "newadvanced",
                "user_type": "1",
                "inline": "1",
                "starts_at": "2099-01-01",
                "expires_at": "2100-01-01",
            },
            headers=headers,
        ) as response:
            payload = json.load(response)
        user = self.db.get_proxy_user_by_name("newadvanced")
        self.assertEqual(100, user["device_limit"])
        self.assertIsNotNone(user["starts_at"])
        import urllib.parse

        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request(urllib.parse.urlsplit(payload["uri"]).path)
        self.assertEqual(403, err.exception.code)
        with self.request("/?type=premium", headers=headers) as response:
            body = response.read().decode()
            self.assertIn("专线用户", body)
            self.assertIn("待开通", body)


class BackupTransportRestoreTests(unittest.TestCase):
    def test_saved_hopping_is_restored_only_after_successful_identity_restore(self):
        import contextlib
        from types import SimpleNamespace
        from unittest import mock
        import hysteria2_panel as panel

        for outcome, enabled in (
            ("applied", True),
            ("applied", False),
            ("rolled-back", True),
        ):
            with self.subTest(outcome=outcome, enabled=enabled):
                record = {
                    "phase": "services-pending",
                    "outcome": outcome,
                    "portHoppingEnabled": enabled,
                }
                runner = mock.Mock()
                with mock.patch.object(panel, 'exclusive_maintenance_lock', return_value=contextlib.nullcontext()), \
                     mock.patch.object(panel, 'verify_restore_services'), \
                     mock.patch.object(panel, '_remove_restore_marker'):
                    panel.resume_after_restore(
                        SimpleNamespace(panel_port=19998),
                        runner=runner,
                        marker_reader=lambda *args, **kwargs: record,
                        egress_manager=mock.Mock(),
                    )
                if outcome == "applied":
                    self.assertEqual(
                        [
                            "/bin/systemctl",
                            "enable" if enabled else "disable",
                            "--now",
                            panel.PortHoppingController.UNIT,
                        ],
                        runner.call_args.args[0],
                    )
                else:
                    runner.assert_not_called()
