import datetime
import json
import time
import unittest
from unittest import mock

import hysteria2_panel as panel
from tests import test_panel
from tests import test_distributed_control as distributed


class ExpiryTests(unittest.TestCase):
    setUp = test_panel.PanelHttpTests.setUp
    tearDown = test_panel.PanelHttpTests.tearDown
    request = test_panel.PanelHttpTests.request
    authenticated_headers = test_panel.PanelHttpTests.authenticated_headers

    def test_all_types_allow_permanent_or_expiring_and_clear(self):
        headers, csrf = self.authenticated_headers()
        for kind in (0, 1):
            for suffix, date in [("permanent", ""), ("expiring", "2099-12-31")]:
                name = str(kind) + suffix
                with self.request(
                    "/users",
                    {
                        "csrf": csrf,
                        "name": name,
                        "user_type": str(kind),
                        "expires_at": date,
                    },
                    headers=headers,
                ) as response:
                    self.assertEqual(201, response.status)
                user = self.db.get_proxy_user_by_name(name)
                self.assertEqual(
                    None if not date else panel._parse_expires_at(date),
                    user["expires_at"],
                )
        user = self.db.get_proxy_user_by_name("0expiring")
        with self.request(
            "/users/{}/edit".format(user["id"]),
            {
                "csrf": csrf,
                "generation": str(user["generation"]),
                "device_limit": "3",
                "traffic_limit_gb": "250",
                "expires_at": "",
                "inline": "1",
            },
            headers=headers,
        ) as response:
            self.assertEqual(200, response.status)
        self.assertIsNone(self.db.get_proxy_user(user["id"])["expires_at"])

    def test_expiry_boundary_disables_once_and_kicks_existing_connections(self):
        now = int(time.time())
        user = self.db.create_proxy_user("due", expires_at=now)
        other = self.db.create_proxy_user("forever")
        self.db.add_traffic({"due": {"tx": 10, "rx": 20}})
        stats = test_panel.PolicyStatsClient(online={"due": 1, "forever": 1})
        manager = panel.UsageManager(self.db, stats, wall_clock=lambda: now)
        with mock.patch("hysteria2_panel.time.time", return_value=now - 1):
            self.assertEqual("due", self.db.authenticate_token(user["token"]))
        with mock.patch("hysteria2_panel.time.time", return_value=now):
            self.assertIsNone(self.db.authenticate_token(user["token"]))
        manager.collect_once()
        after = self.db.get_proxy_user(user["id"])
        self.assertEqual(0, after["enabled"])
        self.assertEqual(1, after["generation"])
        self.assertEqual(30, after["tx_bytes"] + after["rx_bytes"])
        self.assertEqual(["due"], stats.kicked)
        self.assertEqual(1, self.db.get_proxy_user(other["id"])["enabled"])
        self.assertEqual([], self.db.expire_proxy_users(now + 1))
        self.assertEqual(1, self.db.get_proxy_user(user["id"])["generation"])
        self.db.update_proxy_user_limits(user["id"], 3, 250 * 1024**3, expires_at=None)
        self.db.set_proxy_user_enabled(user["id"], True)
        self.assertEqual("due", self.db.authenticate_token(user["token"]))

    def test_date_uses_beijing_midnight_and_omitted_edit_preserves(self):
        deadline = panel._parse_expires_at("2030-01-02")
        self.assertEqual(
            "2030-01-01T16:00:00+00:00",
            datetime.datetime.fromtimestamp(
                deadline, datetime.timezone.utc
            ).isoformat(),
        )
        user = self.db.create_proxy_user("keep", expires_at=deadline)
        self.db.update_proxy_user_limits(user["id"], 4, 250 * 1024**3)
        self.assertEqual(deadline, self.db.get_proxy_user(user["id"])["expires_at"])

    def test_dashboard_port_tracks_defaults_and_udp_filter_removed(self):
        headers, _ = self.authenticated_headers()
        with self.request("/", headers=headers) as response:
            body = response.read().decode()
        self.assertIn("data-subscription-port>UDP 443</strong>", body)
        self.assertNotIn('id="user-udp443-filter"', body)
        self.assertIn("留空为永久", body)
        self.db.set_subscription_defaults(
            [
                {
                    "label": "custom",
                    "host": "example.com",
                    "port": 8443,
                    "pin_sha256": "ab" * 32,
                }
            ]
        )
        with self.request("/", headers=headers) as response:
            body = response.read().decode()
        self.assertIn("data-subscription-port>UDP 8443</strong>", body)


class RemoteExpiryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = distributed.DistributedAuthorizationTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_expired_remote_auth_denied_and_disconnect_is_persisted(self):
        f = self.fixture
        with f.db._connect() as c:
            c.execute(
                "UPDATE proxy_users SET expires_at=? WHERE name=?", (f.now[0], "alice")
            )
        decision = f.service.authorize(
            f.auth_payload(f.nodes[0], 40), remote_ip="203.0.113.1"
        )
        self.assertFalse(decision["ok"])
        self.assertEqual(["alice"], f.db.expire_proxy_users(f.now[0]))
        with f.db._connect() as c:
            rows = c.execute(
                "SELECT payload FROM node_commands WHERE kind='KICK_USERS'"
            ).fetchall()
        self.assertEqual(2, len(rows))
        self.assertTrue(all("alice" in json.loads(row[0])["users"] for row in rows))
