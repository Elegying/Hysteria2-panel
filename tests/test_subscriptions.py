import base64
import json
import time
import unittest
from unittest import mock
import urllib.error
import urllib.parse

import hysteria2_panel as panel
from tests import test_panel as fixtures


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        fixtures.PanelHttpTests.setUp(self)
        # Subscription defaults must not depend on the host systemd state.
        self.application.port_hopping_controller = mock.Mock()
        self.application.port_hopping_controller.status.return_value = {
            "enabled": False, "ports": "20000-50000", "target": 443
        }

    tearDown = fixtures.PanelHttpTests.tearDown
    request = fixtures.PanelHttpTests.request
    authenticated_headers = fixtures.PanelHttpTests.authenticated_headers

    def issue(self, name="subscriber"):
        user = self.db.create_proxy_user(name, allow_udp_443=True)
        headers, csrf = self.authenticated_headers()
        with self.request(
            "/users/{}/share".format(user["id"]),
            {"csrf": csrf, "generation": "0", "inline": "1"},
            headers=headers,
        ) as response:
            payload = json.load(response)
        return user, urllib.parse.urlsplit(payload["uri"]).path, headers, csrf

    def test_default_port_and_live_global_update_keep_identity_and_usage(self):
        user, path, headers, csrf = self.issue()
        self.db.add_traffic({"subscriber": {"tx": 100, "rx": 200}})
        with self.request(path) as response:
            first = base64.b64decode(response.read()).decode()
            self.assertIn(":443/", first)
            self.assertIn(user["token"], first)
            self.assertEqual(
                "upload=100; download=200; total=268435456000",
                response.headers["Subscription-Userinfo"],
            )
            self.assertEqual("no-store", response.headers["Cache-Control"])
        nodes = [
            {
                "label": "changed",
                "host": "new.example.com",
                "port": 8443,
                "pin_sha256": "ab" * 32,
            }
        ]
        with self.request(
            "/subscriptions/defaults",
            {"csrf": csrf, "nodes": json.dumps(nodes)},
            headers=headers,
        ) as response:
            self.assertEqual(200, response.status)
        with self.request(path) as response:
            second = base64.b64decode(response.read()).decode()
        self.assertIn("new.example.com:8443/", second)
        self.assertIn(user["token"], second)
        self.assertNotEqual(first, second)
        self.assertEqual("subscriber", self.db.authenticate_token(user["token"]))
        self.db.initialize()
        self.assertEqual(8443, self.db.get_subscription_defaults()[0]["port"])
        token = self.db.ensure_subscription(user["id"])["token"]
        self.assertEqual(path, "/sub/" + token)

    def test_rotation_retains_subscription_but_changes_proxy_auth(self):
        user, path, _, _ = self.issue()
        rotated = self.db.rotate_proxy_token(user["id"])
        with self.request(path) as response:
            body = base64.b64decode(response.read()).decode()
        self.assertIn(rotated["token"], body)
        self.assertNotIn(user["token"], body)
        self.assertIsNone(self.db.authenticate_token(user["token"]))

    def test_ssrvpn_subscription_carries_fixed_usage_origin_after_node_changes(self):
        self.application.subscription_base_url = "https://panel.example.test:19998"
        user, path, _, _ = self.issue()
        for host, port in [("hk.example.test", 19999), ("changed.example.test", 8443)]:
            self.db.set_subscription_defaults([{"label": "custom", "host": host,
                "port": port, "pin_sha256": "ab" * 32, "enabled": True}])
            with self.request(path, headers={"User-Agent": "SSRVPN/1.0"}) as response:
                node = json.load(response)["proxies"][0]
            self.assertEqual(host, node["server"])
            self.assertEqual(port, node["port"])
            self.assertEqual(user["token"], node["password"])
            self.assertEqual({"version": 1, "origin": "https://panel.example.test:19998"},
                             node["ssrvpn-account-usage"])
        with self.request(path, headers={"User-Agent": "clash.meta"}) as response:
            self.assertNotIn("ssrvpn-account-usage", json.load(response)["proxies"][0])

    def test_formats_and_exhausted_usage(self):
        user, path, _, _ = self.issue()
        with self.db._connect() as connection:
            connection.execute(
                "UPDATE proxy_users SET tx_bytes=traffic_limit_bytes, expires_at=? WHERE id=?",
                (int(time.time()) + 3600, user["id"]),
            )
        with self.request(path, headers={"User-Agent": "clash.meta"}) as response:
            payload = json.load(response)
            self.assertEqual(443, payload["proxies"][0]["port"])
            self.assertEqual(user["token"], payload["proxies"][0]["password"])
            self.assertIn("expire=", response.headers["Subscription-Userinfo"])
            self.assertIn(
                "upload=268435456000", response.headers["Subscription-Userinfo"]
            )
        with self.request(path + "?format=raw") as response:
            self.assertTrue(response.read().startswith(b"hysteria2://"))
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request(path + "?format=unknown")
        self.assertEqual(400, err.exception.code)

    def test_revocation_expiration_permissions_and_csrf(self):
        user, path, headers, _ = self.issue()
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request(
                "/subscriptions/defaults",
                {"csrf": "bad", "nodes": "[]"},
                headers=headers,
            )
        self.assertEqual(403, err.exception.code)
        self.db.set_proxy_user_enabled(user["id"], False)
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request(path)
        self.assertEqual(403, err.exception.code)
        self.db.set_proxy_user_enabled(user["id"], True)
        with self.db._connect() as connection:
            connection.execute(
                "UPDATE proxy_users SET expires_at=? WHERE id=?",
                (int(time.time()) - 1, user["id"]),
            )
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request(path)
        self.assertEqual(410, err.exception.code)
        with self.db._connect() as connection:
            connection.execute(
                "UPDATE proxy_users SET expires_at=NULL,allow_udp_443=0 WHERE id=?",
                (user["id"],),
            )
        with self.request(path) as response:
            self.assertEqual(200, response.status)

    def test_subscription_secrets_are_redacted_from_logs(self):
        _, path, _, _ = self.issue()
        with self.assertLogs(panel.LOGGER, level="INFO") as logs:
            with self.request(path) as response:
                response.read()
        self.assertNotIn(path, "\n".join(logs.output))
        self.assertIn("/sub/[redacted]", "\n".join(logs.output))

    def test_override_and_return_to_global_without_url_change(self):
        user, path, headers, csrf = self.issue()
        sub = self.db.get_subscription(user_id=user["id"])
        self.db.set_subscription_nodes(
            sub["id"],
            [
                {
                    "label": "custom",
                    "host": "custom.example",
                    "port": 9999,
                    "pin_sha256": "ab" * 32,
                }
            ],
        )
        with self.request(path + "?format=raw") as response:
            self.assertIn(b":9999/", response.read())
        with self.request(
            "/subscriptions/{}/nodes".format(sub["id"]),
            {"csrf": csrf, "nodes": "[]"},
            headers=headers,
        ):
            pass
        with self.request(path + "?format=raw") as response:
            self.assertIn(b":443/", response.read())

    def test_subscription_title_is_independent_of_node_name(self):
        _, path, _, _ = self.issue()
        with self.request(path) as response:
            self.assertEqual(
                "私家车",
                base64.b64decode(response.headers["Profile-Title"][7:]).decode(),
            )
            self.assertIn(
                urllib.parse.quote("私家车.txt"),
                response.headers["Content-Disposition"],
            )
            uri = base64.b64decode(response.read()).decode()
        self.assertEqual(
            "edge-fixture-02", urllib.parse.unquote(urllib.parse.urlsplit(uri).fragment)
        )
        self.application.subscription_name = "自定义订阅"
        with self.request(path) as response:
            self.assertEqual(
                "自定义订阅",
                base64.b64decode(response.headers["Profile-Title"][7:]).decode(),
            )

    def test_reset_revokes_both_credentials_only_for_selected_user(self):
        user, path, headers, csrf = self.issue()
        other = self.db.create_proxy_user("unaffected", allow_udp_443=True)
        other_subscription = self.db.ensure_subscription(other["id"])
        self.db.add_traffic({"subscriber": {"tx": 123, "rx": 456}})
        before = self.db.get_proxy_user(user["id"])
        sub = self.db.get_subscription(user_id=user["id"])
        with self.request(
            "/subscriptions/{}/regenerate".format(sub["id"]),
            {"csrf": csrf},
            headers=headers,
        ) as response:
            self.assertEqual(200, response.status)
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request(path)
        self.assertEqual(404, err.exception.code)
        self.assertIsNone(self.db.authenticate_token(user["token"]))
        self.assertIn("subscriber", self.stats.kicked)
        after = self.db.get_proxy_user(user["id"])
        self.assertEqual(before["generation"] + 1, after["generation"])
        self.assertIsNotNone(
            next(
                u for u in self.db.list_proxy_users_for_usage() if u["id"] == user["id"]
            )["local_drain_started_at"]
        )
        for field in (
            "tx_bytes",
            "rx_bytes",
            "device_limit",
            "traffic_limit_bytes",
            "enabled",
            "expires_at",
        ):
            self.assertEqual(before[field], after[field])
        replacement = self.db.recover_subscription_token(sub["id"])
        with self.request("/sub/" + replacement) as response:
            uri = base64.b64decode(response.read()).decode()
        new_password = urllib.parse.unquote(urllib.parse.urlsplit(uri).username)
        self.assertNotEqual(user["token"], new_password)
        self.assertEqual("subscriber", self.db.authenticate_token(new_password))
        self.assertEqual("unaffected", self.db.authenticate_token(other["token"]))
        self.assertEqual(
            other_subscription["token"],
            self.db.ensure_subscription(other["id"])["token"],
        )

    def test_reset_is_atomic_if_password_write_fails(self):
        user, path, _, _ = self.issue()
        sub = self.db.get_subscription(user_id=user["id"])
        with self.db._connect() as connection:
            connection.execute(
                "CREATE TRIGGER reject_rotation BEFORE UPDATE OF token_fingerprint ON proxy_users BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
        import sqlite3

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.regenerate_subscription_token(sub["id"])
        self.assertEqual("subscriber", self.db.authenticate_token(user["token"]))
        self.assertEqual(path, "/sub/" + self.db.recover_subscription_token(sub["id"]))
        self.assertEqual(0, self.db.get_proxy_user(user["id"])["generation"])

    def test_validation_is_atomic(self):
        good = [
            {
                "label": "valid",
                "host": "example.com",
                "port": 443,
                "pin_sha256": "ab" * 32,
            }
        ]
        self.db.set_subscription_defaults(good)
        for changes in (
            {"port": 65536},
            {"host": "example.com/?injected=1"},
            {"pin_sha256": "bad"},
            {"enabled": "false"},
        ):
            with self.assertRaises(ValueError):
                self.db.set_subscription_defaults([{**good[0], **changes}])
        self.assertEqual(443, self.db.get_subscription_defaults()[0]["port"])


if __name__ == "__main__":
    unittest.main()
