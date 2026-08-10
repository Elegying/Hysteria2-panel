import json
import sqlite3
import tempfile
import threading
import unittest
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from hysteria2_panel import (
    Database,
    LoginRateLimiter,
    PanelApplication,
    build_connection_uri,
    handle_auth_payload,
    hash_password,
    make_internal_server,
    make_panel_server,
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
        with sqlite3.connect(self.db_path) as connection:
            dump = "\n".join(connection.iterdump())
        self.assertNotIn(created["token"], dump)

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
        self.assertEqual("alice", self.db.list_proxy_users()["users"][0]["name"])

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
                {"csrf": csrf_token},
                headers=headers,
                follow_redirects=False,
            )
        self.assertEqual(303, raised.exception.code)
        self.assertEqual(["<script>alert(1)</script>"], self.stats.kicked)
        self.assertIsNone(self.db.authenticate_token(created["token"]))


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
