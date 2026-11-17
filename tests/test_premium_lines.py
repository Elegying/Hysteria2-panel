import json
import unittest
from unittest import mock
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

    def test_node_reports_cannot_charge_or_count_other_tier(self):
        ordinary, premium = self.prepare()
        for index, node_id in enumerate(self.nodes):
            traffic = {"ordinary": {"tx": 10, "rx": 0},
                       "advanced": {"tx": 100, "rx": 0}}
            domains = [{"user": "ordinary", "domain": "normal.example.test", "tx": 10, "rx": 0},
                       {"user": "advanced", "domain": "premium.example.test", "tx": 100, "rx": 0}]
            result = self.db.apply_node_traffic_batch(
                node_id, format(index + 20, '032x'), traffic, bytes([index + 1]) * 32,
                self.now[0], domain_usage=domains, observed_at=self.now[0])
            self.assertTrue(result['committed'])
            self.assertEqual(1, result['unknownUsers'])
            self.service.accept_online_snapshot(
                self.snapshot(node_id, 70 + index, sequence=2,
                              online={"ordinary": 3, "advanced": 4}),
                remote_ip="203.0.113.{}".format(index + 1))
        self.assertEqual(10, self.db.get_proxy_user(ordinary['id'])['tx_bytes'])
        self.assertEqual(100, self.db.get_proxy_user(premium['id'])['tx_bytes'])
        self.assertEqual({"ordinary": 3}, self.db.node_online_counts(self.nodes[0]))
        self.assertEqual({"advanced": 4}, self.db.node_online_counts(self.nodes[1]))
        self.assertEqual(['normal.example.test'], [x['domain'] for x in self.db.domain_usage_top(ordinary['id'], now=self.now[0])['items']])
        self.assertEqual(['premium.example.test'], [x['domain'] for x in self.db.domain_usage_top(premium['id'], now=self.now[0])['items']])
        with self.db._connect() as c:
            physical = {r['origin_id']: r['total'] for r in c.execute(
                "SELECT origin_id, SUM(tx_bytes+rx_bytes) AS total FROM origin_traffic_daily GROUP BY origin_id")}
        self.assertEqual(110, physical['node:' + self.nodes[0]])
        self.assertEqual(110, physical['node:' + self.nodes[1]])

    def test_local_collection_cannot_charge_premium_user(self):
        ordinary, premium = self.prepare()
        local = 'local:' + 'a' * 32
        self.db.apply_traffic_batch(
            'b' * 32, {'ordinary': {'tx': 10, 'rx': 0}, 'advanced': {'tx': 100, 'rx': 0}},
            origin_id=local, origin_kind='local', origin_name='local',
            domain_usage=[{'user': 'advanced', 'domain': 'premium.example.test', 'tx': 100, 'rx': 0}],
            fresh_local_collection=True)
        self.assertEqual(10, self.db.get_proxy_user(ordinary['id'])['tx_bytes'])
        self.assertEqual(0, self.db.get_proxy_user(premium['id'])['tx_bytes'])
        self.assertEqual([], self.db.domain_usage_top(premium['id'])['items'])

    def test_stale_cross_tier_online_counts_cannot_block_authentication(self):
        ordinary, premium = self.prepare()
        with self.db._connect() as c:
            c.execute("INSERT INTO node_online_counts(node_id,user_name,count) VALUES (?,?,?)",
                      (self.nodes[0], 'advanced', 100))
            c.execute("INSERT INTO node_online_counts(node_id,user_name,count) VALUES (?,?,?)",
                      (self.nodes[1], 'ordinary', 100))
        self.local_online['advanced'] = 100
        self.token = premium['token']
        self.assertTrue(self.service.authorize(self.auth_payload(self.nodes[1], 90), '203.0.113.2')['ok'])
        self.token = ordinary['token']
        self.assertTrue(self.service.authorize(self.auth_payload(self.nodes[0], 91), '203.0.113.1')['ok'])
        states = self.db.list_node_online_states(self.now[0], 60)
        self.assertFalse(any(state['online'] for state in states))

    def test_canary_online_snapshot_does_not_reject_or_count_fake_identity(self):
        self.db.create_proxy_user("ordinary")
        snapshot = self.snapshot(self.nodes[0], 95, sequence=1,
                                 online={"ordinary": 2, "__hy2panel_bootstrap_canary__": 1})
        self.service.accept_online_snapshot(snapshot, '203.0.113.1')
        self.assertEqual({'ordinary': 2}, self.db.node_online_counts(self.nodes[0]))
        snapshot = self.snapshot(self.nodes[0], 96, sequence=2,
                                 online={"unrelated-unknown": 1, "__hy2panel_bootstrap_canary__": 1})
        from hy2panel.distributed import NodeRequestRejected
        with self.assertRaises(NodeRequestRejected):
            self.service.accept_online_snapshot(snapshot, '203.0.113.1')

    def test_canary_identity_cannot_be_created_as_a_user(self):
        with self.assertRaises(ValueError):
            self.db.create_proxy_user("__HY2PANEL_BOOTSTRAP_CANARY__")

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
    def setUp(self):
        fixtures.PanelHttpTests.setUp(self)
        patcher = mock.patch.object(type(self.db), "_certificate_server_name", return_value="cert.example.test")
        patcher.start()
        self.addCleanup(patcher.stop)

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
                (json.dumps({"certificateDerSha256": "ab" * 32, "certificatePem": "fixture"}), node["node_id"]),
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
        self.assertIn("sni=cert.example.test", body)
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

    def test_user_backup_reenrolls_premium_nodes_with_new_certificates(self):
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
                self.assertEqual(0, c.execute("SELECT COUNT(*) FROM premium_node_profiles").fetchone()[0])

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
                self.assertFalse(replacement["restored_profile"])
                with restored._connect() as c:
                    row = c.execute("SELECT name, subscription_host, subscription_port, listen_port, port_hopping FROM nodes WHERE node_id=?", (replacement["node_id"],)).fetchone()
                    self.assertEqual(("replacement", "changed.example.test", 8443, 8443, 0), tuple(row))
                self.assertNotEqual(
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
                    after = response.read()
                    self.assertNotEqual(before, after)
                    self.assertEqual(2, after.count(b"changed.example.test:8443"))
                    self.assertIn(b"sni=cert.example.test", after)
            finally:
                self.application.database = original

    def test_reenrollment_updates_subscription_and_reuses_certificate(self):
        user = self.db.create_proxy_user("rejoin", user_type=1)
        token = self.db.ensure_subscription(user["id"])["token"]
        old_id = self.add_node("us")
        self.db.delete_node_pairing(old_id, "admin", 2)
        replacement = self.db.create_node_enrollment(
            "new line", "1.1.1.1", "admin", "c" * 64, 3, 4,
            tier="premium", region="us", subscription_host="new.example.test",
            subscription_port=8443, port_hopping=True)
        with self.db._connect() as c:
            profile = c.execute("SELECT * FROM premium_node_profiles WHERE node_id=?", (replacement["node_id"],)).fetchone()
            self.assertEqual(("new line", "new.example.test", 443, 8443, 1),
                             (profile["label"], profile["host"], profile["port"], profile["listen_port"], profile["port_hopping"]))
            self.assertEqual("ab" * 32, json.loads(profile["identity_json"])["certificateDerSha256"])
            c.execute("UPDATE nodes SET status='pending_verification', verified_at=1, policy_state='protocol_ready', data_plane_state='dns_admitted' WHERE node_id=?", (replacement["node_id"],))
        with self.request('/sub/' + token, headers={'User-Agent': 'SSRVPN/1.0'}) as response:
            proxies = json.load(response)['proxies']
        self.assertEqual(1, len(proxies))
        self.assertEqual('new.example.test', proxies[0]['server'])
        self.assertEqual(443, proxies[0]['port'])
        self.assertEqual('20000-50000', proxies[0]['ports'])

    def test_live_online_totals_are_isolated_by_user_type(self):
        self.db.create_proxy_user("regular")
        self.db.create_proxy_user("premium", user_type=1)
        headers, _ = self.authenticated_headers()
        live = {"online": {"regular": 2, "premium": 7}, "online_complete": True,
                "observed_at": 1_700_000_200, "machines": []}
        with mock.patch.object(self.application.usage_manager, "online_snapshot", return_value=live):
            for tier, expected in (("standard", 2), ("premium", 7)):
                with self.request('/api/v1/dashboard-online?type=' + tier, headers=headers) as response:
                    payload = json.load(response)
                self.assertEqual(expected, payload['onlineDevices'])

    def test_dashboard_user_counts_follow_the_selected_group(self):
        self.db.create_proxy_user("regular")
        self.db.create_proxy_user("premium", user_type=1)
        self.db.create_proxy_user("premium-two", user_type=1)
        headers, _ = self.authenticated_headers()
        with self.request('/?type=standard', headers=headers) as response:
            normal = response.read().decode()
        with self.request('/?type=premium', headers=headers) as response:
            premium = response.read().decode()
        self.assertIn('共 1 位用户', normal)
        self.assertIn('共 2 位用户', premium)
        self.assertNotIn('显示 1 / 全部 3 位用户', normal)

    def test_online_update_refuses_to_orphan_external_node_data(self):
        with self.db._connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS external_subscription_nodes (id INTEGER, nodes_json TEXT, revision INTEGER)")
            c.execute("INSERT INTO external_subscription_nodes (id, nodes_json, revision) VALUES (1, 'opaque', 1)")
        headers, csrf = self.authenticated_headers()
        self.application.update_result = {"update_available": True, "latest": "v99.0.0"}
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/updates/apply', {'csrf': csrf},
                         headers={**headers, 'Accept': 'application/json'})
        self.assertEqual(409, error.exception.code)
        self.assertIn('外部节点', error.exception.read().decode())
        self.assertEqual(0, self.update_controller.queued)

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
