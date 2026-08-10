import json
import os
import sqlite3
import tempfile
import threading
import unittest
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hysteria2_panel import (
    ConflictError,
    Database,
    LoginRateLimiter,
    HysteriaStatsClient,
    PanelApplication,
    PanelHandler,
    Settings,
    build_connection_uri,
    handle_auth_payload,
    hash_password,
    make_internal_server,
    make_panel_server,
    summarize_dashboard,
    verify_password,
)


class PasswordTests(unittest.TestCase):
    def test_passwords_are_salted_and_verified(self):
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")

        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("correct horse battery staple", first))
        self.assertFalse(verify_password("wrong", first))


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "panel.db"
        self.db = Database(self.db_path, b"a" * 32)
        self.db.initialize()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_admin_login_and_session_lifecycle(self):
        admin_id = self.db.upsert_admin("Elegy", "admin-password")

        self.assertEqual(admin_id, self.db.verify_admin("Elegy", "admin-password"))
        self.assertIsNone(self.db.verify_admin("Elegy", "wrong"))

        raw_token, csrf_token = self.db.create_session(admin_id, ttl_seconds=60)
        session = self.db.get_session(raw_token)
        self.assertEqual(admin_id, session["admin_id"])
        self.assertEqual(csrf_token, session["csrf_token"])

        self.db.revoke_session(raw_token)
        self.assertIsNone(self.db.get_session(raw_token))

    def test_expired_session_is_rejected(self):
        admin_id = self.db.upsert_admin("Elegy", "admin-password")
        raw_token, _ = self.db.create_session(admin_id, ttl_seconds=-1)

        self.assertIsNone(self.db.get_session(raw_token))

    def test_proxy_user_token_is_one_time_and_never_stored_plaintext(self):
        created = self.db.create_proxy_user("alice")

        self.assertEqual("alice", self.db.authenticate_token(created["token"]))
        self.assertEqual(created["token"], self.db.recover_proxy_token(created["id"]))
        with sqlite3.connect(self.db_path) as connection:
            dump = "\n".join(connection.iterdump())
        self.assertNotIn(created["token"], dump)

    def test_proxy_users_have_default_and_custom_limits(self):
        default_user = self.db.create_proxy_user("alice")
        custom_user = self.db.create_proxy_user(
            "bob", device_limit=5, traffic_limit_bytes=500 * 1024**3
        )

        default_record = self.db.get_proxy_user(default_user["id"])
        custom_record = self.db.get_proxy_user(custom_user["id"])
        self.assertEqual(3, default_record["device_limit"])
        self.assertEqual(250 * 1024**3, default_record["traffic_limit_bytes"])
        self.assertEqual(5, custom_record["device_limit"])
        self.assertEqual(500 * 1024**3, custom_record["traffic_limit_bytes"])
        with self.assertRaises(ValueError):
            self.db.create_proxy_user("bad-devices", device_limit=0)
        with self.assertRaises(ValueError):
            self.db.create_proxy_user("bad-traffic", traffic_limit_bytes=0)

    def test_traffic_is_accumulated_and_can_be_reset(self):
        alice = self.db.create_proxy_user("alice")
        bob = self.db.create_proxy_user("bob")

        self.db.add_traffic({"alice": {"tx": 100, "rx": 200}, "bob": {"tx": 9, "rx": 8}})
        self.db.add_traffic({"alice": {"tx": 3, "rx": 4}})
        alice_record = self.db.get_proxy_user(alice["id"])
        self.assertEqual(103, alice_record["tx_bytes"])
        self.assertEqual(204, alice_record["rx_bytes"])

        self.db.reset_proxy_user_traffic(alice["id"], expected_generation=0)
        alice_record = self.db.get_proxy_user(alice["id"])
        self.assertEqual((0, 0), (alice_record["tx_bytes"], alice_record["rx_bytes"]))
        self.assertEqual(1, alice_record["generation"])

        self.db.reset_all_traffic()
        bob_record = self.db.get_proxy_user(bob["id"])
        self.assertEqual((0, 0), (bob_record["tx_bytes"], bob_record["rx_bytes"]))

    def test_initialize_migrates_legacy_users_without_changing_their_token(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        token = "legacy-token"
        with sqlite3.connect(legacy_path) as connection:
            connection.execute(
                """CREATE TABLE proxy_users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                token_fingerprint TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                generation INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
                )"""
            )
            connection.execute(
                "INSERT INTO proxy_users VALUES (1, 'legacy', ?, 1, 0, 1, 1)",
                (self.db._fingerprint(token),),
            )

        legacy_db = Database(legacy_path, b"a" * 32)
        legacy_db.initialize()
        record = legacy_db.get_proxy_user(1)
        self.assertEqual(3, record["device_limit"])
        self.assertEqual(250 * 1024**3, record["traffic_limit_bytes"])
        self.assertEqual("legacy", legacy_db.authenticate_token(token))
        self.assertIsNone(legacy_db.recover_proxy_token(1))

    def test_disable_rotate_and_delete_user(self):
        created = self.db.create_proxy_user("alice", token="first-token")

        self.db.set_proxy_user_enabled(created["id"], False)
        self.assertIsNone(self.db.authenticate_token("first-token"))

        self.db.set_proxy_user_enabled(created["id"], True)
        rotated = self.db.rotate_proxy_token(created["id"], token="second-token")
        self.assertIsNone(self.db.authenticate_token("first-token"))
        self.assertEqual("alice", self.db.authenticate_token(rotated["token"]))

        self.db.delete_proxy_user(created["id"])
        self.assertIsNone(self.db.authenticate_token("second-token"))

    def test_stale_user_generation_cannot_overwrite_a_new_token(self):
        created = self.db.create_proxy_user("alice", token="first-token")

        self.db.rotate_proxy_token(
            created["id"], token="second-token", expected_generation=0
        )
        with self.assertRaises(ConflictError):
            self.db.rotate_proxy_token(
                created["id"], token="third-token", expected_generation=0
            )

        self.assertEqual("alice", self.db.authenticate_token("second-token"))
        self.assertIsNone(self.db.authenticate_token("third-token"))

    def test_names_are_unique_and_control_characters_are_rejected(self):
        self.db.create_proxy_user("alice")

        with self.assertRaises(ValueError):
            self.db.create_proxy_user("alice")
        with self.assertRaises(ValueError):
            self.db.create_proxy_user("bad\nname")

    def test_list_users_is_paginated(self):
        for name in ("alice", "bob", "carol"):
            self.db.create_proxy_user(name)

        first_page = self.db.list_proxy_users(limit=2, offset=0)
        second_page = self.db.list_proxy_users(limit=2, offset=2)

        self.assertEqual(3, first_page["total"])
        self.assertEqual(["alice", "bob"], [user["name"] for user in first_page["users"]])
        self.assertEqual(["carol"], [user["name"] for user in second_page["users"]])

    def test_lists_all_user_names_for_dashboard_summary(self):
        for suffix in range(105):
            self.db.create_proxy_user("user-{:03d}".format(suffix))

        self.assertEqual(105, len(self.db.list_proxy_user_names()))


class AuthContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "panel.db", b"b" * 32)
        self.db.initialize()
        self.user = self.db.create_proxy_user("alice", token="valid-token")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_valid_hysteria_auth_payload_returns_stable_user_id(self):
        status, response = handle_auth_payload(
            self.db,
            json.dumps({"addr": "192.0.2.10:1234", "auth": "valid-token", "tx": 9}).encode(),
        )

        self.assertEqual(200, status)
        self.assertEqual({"ok": True, "id": "alice"}, response)

    def test_invalid_or_oversized_auth_payload_is_rejected(self):
        status, response = handle_auth_payload(
            self.db,
            json.dumps({"addr": "192.0.2.10:1234", "auth": "wrong", "tx": 9}).encode(),
        )
        self.assertEqual(200, status)
        self.assertEqual({"ok": False, "id": ""}, response)

        status, response = handle_auth_payload(self.db, b"not-json")
        self.assertEqual(400, status)
        self.assertEqual("INVALID_REQUEST", response["error"]["code"])

    def test_internal_http_auth_endpoint_matches_hysteria_contract(self):
        server = make_internal_server(("127.0.0.1", 0), self.db)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        request = urllib.request.Request(
            "http://127.0.0.1:{}/auth".format(server.server_address[1]),
            data=json.dumps({"addr": "192.0.2.10:1234", "auth": "valid-token", "tx": 9}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.load(response)

        self.assertEqual({"ok": True, "id": "alice"}, payload)
        self.assertEqual("application/json; charset=utf-8", response.headers["Content-Type"])
        self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])


class RateLimiterTests(unittest.TestCase):
    def test_failed_logins_are_limited_per_address_and_success_resets(self):
        now = [1000.0]
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=60, clock=lambda: now[0])

        self.assertTrue(limiter.is_allowed("192.0.2.1"))
        limiter.record_failure("192.0.2.1")
        limiter.record_failure("192.0.2.1")
        self.assertFalse(limiter.is_allowed("192.0.2.1"))
        self.assertTrue(limiter.is_allowed("192.0.2.2"))

        now[0] += 61
        self.assertTrue(limiter.is_allowed("192.0.2.1"))
        limiter.record_failure("192.0.2.1")
        limiter.record_success("192.0.2.1")
        self.assertTrue(limiter.is_allowed("192.0.2.1"))

    def test_address_tracking_is_bounded(self):
        limiter = LoginRateLimiter(max_attempts=2, max_addresses=3, clock=lambda: 1000.0)

        for suffix in range(10):
            limiter.record_failure("192.0.2.{}".format(suffix))

        self.assertLessEqual(len(limiter._attempts), 3)


class FakeStatsClient:
    def __init__(self):
        self.kicked = []

    def snapshot(self):
        return {
            "traffic": {"alice": {"tx": 1024, "rx": 2048}},
            "online": {"alice": 2},
            "available": True,
        }

    def kick(self, name):
        self.kicked.append(name)


class FailingStatsClient(FakeStatsClient):
    def kick(self, name):
        raise OSError("stats unavailable")


class DashboardSummaryTests(unittest.TestCase):
    def test_summary_matches_ssr_panel_metrics(self):
        summary = summarize_dashboard(
            ["alice", "bob"],
            {
                "traffic": {
                    "alice": {"tx": 1024, "rx": 2048},
                    "deleted-user": {"tx": 9999, "rx": 9999},
                },
                "online": {"alice": 2, "deleted-user": 5},
                "available": True,
            },
        )

        self.assertEqual(
            {
                "service_available": True,
                "total_users": 2,
                "inactive_users": 1,
                "online_devices": 2,
                "total_tx": 1024,
                "total_rx": 2048,
            },
            summary,
        )

    def test_unavailable_stats_are_reported_without_inventing_activity(self):
        summary = summarize_dashboard(
            ["alice"], {"traffic": {}, "online": {}, "available": False}
        )

        self.assertFalse(summary["service_available"])
        self.assertEqual(1, summary["inactive_users"])
        self.assertEqual(0, summary["online_devices"])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PanelHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "panel.db", b"c" * 32)
        self.db.initialize()
        self.admin_id = self.db.upsert_admin("Elegy", "admin-password")
        self.stats = FakeStatsClient()
        self.application = PanelApplication(
            database=self.db,
            public_host="154.9.234.210",
            hysteria_port=19999,
            pin_sha256="AA:BB:CC",
            stats_client=self.stats,
            node_name="私家车-2026",
        )
        self.server = make_panel_server(("127.0.0.1", 0), self.application)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{}".format(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def request(self, path, data=None, headers=None, follow_redirects=True):
        request = urllib.request.Request(
            self.base_url + path,
            data=urllib.parse.urlencode(data).encode() if data is not None else None,
            headers=headers or {},
            method="POST" if data is not None else "GET",
        )
        opener = urllib.request.build_opener() if follow_redirects else urllib.request.build_opener(NoRedirect())
        return opener.open(request, timeout=2)

    def authenticated_headers(self):
        raw_token, csrf_token = self.db.create_session(self.admin_id)
        return {"Cookie": "hy2panel_session={}".format(raw_token)}, csrf_token

    def test_login_page_and_health_have_security_headers(self):
        with self.request("/healthz") as response:
            self.assertEqual({"status": "ok"}, json.load(response))
            self.assertEqual("DENY", response.headers["X-Frame-Options"])

        with self.request("/login") as response:
            body = response.read().decode()
            self.assertIn('type="password"', body)
            self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])

    def test_root_requires_authentication(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request("/", follow_redirects=False)
        self.assertEqual(303, raised.exception.code)
        self.assertEqual("/login", raised.exception.headers["Location"])

    def test_login_sets_a_secure_session_cookie(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/login",
                {"username": "Elegy", "password": "admin-password"},
                follow_redirects=False,
            )
        self.assertEqual(303, raised.exception.code)
        cookie = raised.exception.headers["Set-Cookie"]
        self.assertTrue(cookie.startswith("hy2panel_session="))
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

    def test_user_creation_requires_csrf_and_returns_credentials_once(self):
        headers, csrf_token = self.authenticated_headers()
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request("/users", {"name": "alice", "csrf": "wrong"}, headers=headers)
        self.assertEqual(403, raised.exception.code)

        with self.request("/users", {"name": "alice", "csrf": csrf_token}, headers=headers) as response:
            body = response.read().decode()
        self.assertEqual(201, response.status)
        self.assertIn("hysteria2://", body)
        self.assertIn("154.9.234.210:19999", body)
        self.assertIn("%E7%A7%81%E5%AE%B6%E8%BD%A6-2026", body)
        self.assertEqual("alice", self.db.list_proxy_users()["users"][0]["name"])

    def test_dashboard_shows_service_and_global_summary_cards(self):
        self.db.create_proxy_user("alice")
        self.db.create_proxy_user("bob")
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        for label in ("服务状态", "当前用户", "不活跃用户", "在线设备", "总上传", "总下载"):
            self.assertIn(label, body)

    def test_http_mode_omits_secure_cookie_and_hsts(self):
        self.application.secure_cookies = False
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/login",
                {"username": "Elegy", "password": "admin-password"},
                follow_redirects=False,
            )

        self.assertNotIn("Secure", raised.exception.headers["Set-Cookie"])
        self.assertTrue(
            raised.exception.headers["Set-Cookie"].startswith("hy2panel_http_session=")
        )
        self.assertNotIn("Strict-Transport-Security", raised.exception.headers)
        self.assertIn("HttpOnly", raised.exception.headers["Set-Cookie"])

    def test_malformed_request_logging_does_not_require_a_parsed_path(self):
        handler = PanelHandler.__new__(PanelHandler)
        handler.client_address = ("127.0.0.1", 12345)
        handler.command = ""

        handler.log_message("bad request")

    def test_dashboard_escapes_names_and_disabling_kicks_user(self):
        created = self.db.create_proxy_user("<script>alert(1)</script>")
        headers, csrf_token = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/users/{}/toggle".format(created["id"]),
                {"csrf": csrf_token, "generation": "0"},
                headers=headers,
                follow_redirects=False,
            )
        self.assertEqual(303, raised.exception.code)
        self.assertEqual(["<script>alert(1)</script>"], self.stats.kicked)
        self.assertIsNone(self.db.authenticate_token(created["token"]))

    def test_audit_failure_does_not_hide_new_credentials(self):
        headers, csrf_token = self.authenticated_headers()
        self.db.audit = lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("disk full"))

        with self.request(
            "/users", {"name": "alice", "csrf": csrf_token}, headers=headers
        ) as response:
            body = response.read().decode()

        self.assertEqual(201, response.status)
        self.assertIn("hysteria2://", body)
        self.assertEqual("alice", self.db.list_proxy_users()["users"][0]["name"])

    def test_kick_failure_does_not_hide_rotated_credentials(self):
        created = self.db.create_proxy_user("alice", token="first-token")
        self.application.stats_client = FailingStatsClient()
        headers, csrf_token = self.authenticated_headers()

        with self.request(
            "/users/{}/rotate".format(created["id"]),
            {"csrf": csrf_token, "generation": "0"},
            headers=headers,
        ) as response:
            body = response.read().decode()

        self.assertEqual(200, response.status)
        self.assertIn("hysteria2://", body)
        self.assertIsNone(self.db.authenticate_token("first-token"))

    def test_panel_server_sets_timeout_and_worker_limit(self):
        self.assertEqual(10, self.server.request_timeout)
        self.assertEqual(64, self.server.max_workers)
        self.assertIsNone(self.server.tls_context)


class StatsApiHandler(BaseHTTPRequestHandler):
    kicked = []

    def log_message(self, *args):
        pass

    def _json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _empty(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.headers.get("Authorization") != "stats-secret":
            self.send_error(401)
            return
        if self.path == "/traffic":
            self._json({"alice": {"tx": 100, "rx": 200}})
            return
        if self.path == "/online":
            self._json({"alice": 2})
            return
        self.send_error(404)

    def do_POST(self):
        if self.headers.get("Authorization") != "stats-secret" or self.path != "/kick":
            self.send_error(401)
            return
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).kicked.extend(json.loads(body))
        self._empty()


class StatsClientTests(unittest.TestCase):
    def setUp(self):
        StatsApiHandler.kicked = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), StatsApiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = HysteriaStatsClient(
            "http://127.0.0.1:{}".format(self.server.server_address[1]), "stats-secret"
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_snapshot_and_kick_use_hysteria_stats_contract(self):
        self.assertEqual(
            {
                "traffic": {"alice": {"tx": 100, "rx": 200}},
                "online": {"alice": 2},
                "available": True,
            },
            self.client.snapshot(),
        )

        self.client.kick("alice")
        self.assertEqual(["alice"], StatsApiHandler.kicked)


class SettingsTests(unittest.TestCase):
    def test_environment_contract_is_validated(self):
        settings = Settings.from_mapping(
            {
                "HY2PANEL_DB": "/tmp/panel.db",
                "HY2PANEL_HMAC_KEY": "ab" * 32,
                "HY2PANEL_PUBLIC_HOST": "154.9.234.210",
                "HY2PANEL_HYSTERIA_PORT": "19999",
                "HY2PANEL_PANEL_PORT": "19998",
                "HY2PANEL_AUTH_PORT": "19996",
                "HY2PANEL_STATS_PORT": "19997",
                "HY2PANEL_STATS_SECRET": "stats-secret",
                "HY2PANEL_TLS_CERT": "/tmp/server.crt",
                "HY2PANEL_TLS_KEY": "/tmp/server.key",
                "HY2PANEL_CERT_PIN": "AA:BB:CC",
            }
        )

        self.assertEqual(19999, settings.hysteria_port)
        self.assertEqual(b"\xab" * 32, settings.hmac_key)
        self.assertEqual("http://127.0.0.1:19997", settings.stats_url)
        self.assertEqual("Hysteria 2", settings.node_name)
        self.assertEqual("https", settings.panel_scheme)

        invalid = dict(os.environ)
        invalid["HY2PANEL_HMAC_KEY"] = "too-short"
        with self.assertRaises(ValueError):
            Settings.from_mapping(invalid)

    def test_custom_node_name_and_http_panel_scheme(self):
        values = {
            "HY2PANEL_HMAC_KEY": "ab" * 32,
            "HY2PANEL_PUBLIC_HOST": "vpn.ssrvpn.vip",
            "HY2PANEL_STATS_SECRET": "stats-secret",
            "HY2PANEL_CERT_PIN": "AA:BB:CC",
            "HY2PANEL_NODE_NAME": "私家车-2026",
            "HY2PANEL_PANEL_SCHEME": "http",
        }

        settings = Settings.from_mapping(values)

        self.assertEqual("私家车-2026", settings.node_name)
        self.assertEqual("http", settings.panel_scheme)

    def test_invalid_node_name_or_panel_scheme_is_rejected(self):
        base = {
            "HY2PANEL_HMAC_KEY": "ab" * 32,
            "HY2PANEL_PUBLIC_HOST": "vpn.ssrvpn.vip",
            "HY2PANEL_STATS_SECRET": "stats-secret",
            "HY2PANEL_CERT_PIN": "AA:BB:CC",
        }
        with self.assertRaises(ValueError):
            Settings.from_mapping({**base, "HY2PANEL_NODE_NAME": "bad\nname"})
        with self.assertRaises(ValueError):
            Settings.from_mapping({**base, "HY2PANEL_PANEL_SCHEME": "ftp"})


class ConnectionUriTests(unittest.TestCase):
    def test_connection_uri_encodes_auth_label_and_certificate_pin(self):
        uri = build_connection_uri(
            host="154.9.234.210",
            port=19999,
            auth="a token/with:specials",
            pin_sha256="AA:BB:CC",
            label="Alice 手机",
        )
        parsed = urllib.parse.urlsplit(uri)

        self.assertEqual("hysteria2", parsed.scheme)
        self.assertEqual("154.9.234.210:19999", parsed.netloc.split("@", 1)[1])
        self.assertEqual("a token/with:specials", urllib.parse.unquote(parsed.netloc.split("@", 1)[0]))
        self.assertEqual("1", urllib.parse.parse_qs(parsed.query)["insecure"][0])
        self.assertEqual("AA:BB:CC", urllib.parse.parse_qs(parsed.query)["pinSHA256"][0])
        self.assertEqual("Alice 手机", urllib.parse.unquote(parsed.fragment))


if __name__ == "__main__":
    unittest.main()
