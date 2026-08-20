import gzip
import contextlib
import html
import json
import io
import hashlib
import os
import re
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import textwrap
import unittest
import zipfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import hysteria2_panel
from hy2panel import operations as panel_operations

from hysteria2_panel import (
    BackupManager,
    BackupValidationError,
    BoundedThreadingHTTPServer,
    ConflictError,
    Database,
    LoginRateLimiter,
    HysteriaStatsClient,
    MAX_STATS_RESPONSE_BYTES,
    PanelApplication,
    PanelHandler,
    RebootController,
    RestoreController,
    Settings,
    ServiceController,
    SystemMetrics,
    UpdateChecker,
    UpdateController,
    UpdateInstaller,
    UsageManager,
    build_connection_uri,
    handle_auth_payload,
    hash_password,
    make_internal_server,
    make_panel_server,
    make_stats_client,
    run_supervised_services,
    summarize_dashboard,
    verify_password,
)


def create_test_certificate(directory, common_name="vpn.example.test"):
    certificate = Path(directory) / "server.crt"
    private_key = Path(directory) / "server.key"
    result = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN={}".format(common_name),
            "-days",
            "3650",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return certificate, private_key


class PasswordTests(unittest.TestCase):
    def test_passwords_are_salted_and_verified(self):
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")

        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("correct horse battery staple", first))
        self.assertFalse(verify_password("wrong", first))

    def test_untrusted_hash_parameters_cannot_trigger_expensive_work(self):
        oversized_scrypt = "scrypt$1073741824$8$1$" + "00" * 16 + "$" + "00" * 32
        oversized_pbkdf2 = "pbkdf2_sha256$999999999$" + "00" * 16 + "$" + "00" * 32

        with mock.patch("hysteria2_panel.hashlib.scrypt", create=True) as scrypt:
            self.assertFalse(verify_password("candidate-password", oversized_scrypt))
            scrypt.assert_not_called()
        with mock.patch("hysteria2_panel.hashlib.pbkdf2_hmac") as pbkdf2:
            self.assertFalse(verify_password("candidate-password", oversized_pbkdf2))
            pbkdf2.assert_not_called()


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

    def test_audit_log_drops_records_older_than_the_retention_window(self):
        with mock.patch.object(
            hysteria2_panel, "AUDIT_RETENTION_SECONDS", 100, create=True
        ), mock.patch.object(
            hysteria2_panel, "AUDIT_MAX_ROWS", 100, create=True
        ), mock.patch("hysteria2_panel.time.time", return_value=100):
            self.db.audit("anonymous", "old_failure", "admin", "2001:db8::1")

        with mock.patch.object(
            hysteria2_panel, "AUDIT_RETENTION_SECONDS", 100, create=True
        ), mock.patch.object(
            hysteria2_panel, "AUDIT_MAX_ROWS", 100, create=True
        ), mock.patch("hysteria2_panel.time.time", return_value=201):
            self.db.audit("anonymous", "new_failure", "admin", "2001:db8::2")

        with sqlite3.connect(self.db_path) as connection:
            actions = [row[0] for row in connection.execute("SELECT action FROM audit_log")]
        self.assertEqual(["new_failure"], actions)

    def test_audit_log_keeps_only_the_configured_maximum_rows(self):
        with mock.patch.object(
            hysteria2_panel, "AUDIT_RETENTION_SECONDS", 1000, create=True
        ), mock.patch.object(
            hysteria2_panel, "AUDIT_MAX_ROWS", 3, create=True
        ), mock.patch("hysteria2_panel.time.time", return_value=500):
            for suffix in range(4):
                self.db.audit("anonymous", "failure-{}".format(suffix), "admin", "192.0.2.1")

        with sqlite3.connect(self.db_path) as connection:
            actions = [
                row[0]
                for row in connection.execute("SELECT action FROM audit_log ORDER BY id")
            ]
        self.assertEqual(["failure-1", "failure-2", "failure-3"], actions)

    def test_updating_admin_password_revokes_existing_sessions(self):
        admin_id = self.db.upsert_admin("Elegy", "old-password")
        raw_token, _ = self.db.create_session(admin_id)

        self.db.upsert_admin("Elegy", "new-password")

        self.assertIsNone(self.db.get_session(raw_token))
        self.assertEqual(admin_id, self.db.verify_admin("Elegy", "new-password"))

    def test_changing_admin_username_replaces_the_only_administrator(self):
        admin_id = self.db.upsert_admin("old-admin", "old-password")
        raw_token, _ = self.db.create_session(admin_id)

        replacement_id = self.db.upsert_admin("new-admin", "new-password")

        self.assertEqual(admin_id, replacement_id)
        self.assertIsNone(self.db.verify_admin("old-admin", "old-password"))
        self.assertEqual(admin_id, self.db.verify_admin("new-admin", "new-password"))
        self.assertIsNone(self.db.get_session(raw_token))

    def test_unknown_admin_still_runs_password_verification(self):
        with mock.patch("hysteria2_panel.verify_password", return_value=False) as verifier:
            self.assertIsNone(self.db.verify_admin("missing", "candidate-password"))

        verifier.assert_called_once()

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

    def test_updating_user_limits_preserves_issued_token_and_rejects_stale_edits(self):
        created = self.db.create_proxy_user(
            "alice", device_limit=3, traffic_limit_bytes=250 * 1024**3
        )

        updated = self.db.update_proxy_user_limits(
            created["id"],
            device_limit=5,
            traffic_limit_bytes=500 * 1024**3,
            expected_generation=0,
        )

        self.assertEqual(5, updated["device_limit"])
        self.assertEqual(500 * 1024**3, updated["traffic_limit_bytes"])
        self.assertEqual(1, updated["generation"])
        self.assertEqual(created["token"], self.db.recover_proxy_token(created["id"]))
        self.assertEqual("alice", self.db.authenticate_token(created["token"]))
        with self.assertRaises(ConflictError):
            self.db.update_proxy_user_limits(
                created["id"],
                device_limit=7,
                traffic_limit_bytes=700 * 1024**3,
                expected_generation=0,
            )

    def test_udp_443_access_is_opt_in_and_preserves_the_issued_token(self):
        created = self.db.create_proxy_user("alice")

        self.assertFalse(self.db.get_proxy_user(created["id"])["allow_udp_443"])
        self.assertIsNone(
            self.db.authenticate_token(created["token"], require_udp_443=True)
        )

        updated = self.db.update_proxy_user_limits(
            created["id"],
            device_limit=3,
            traffic_limit_bytes=250 * 1024**3,
            allow_udp_443=True,
            expected_generation=0,
        )

        self.assertTrue(updated["allow_udp_443"])
        self.assertEqual("alice", self.db.authenticate_token(created["token"]))
        self.assertEqual(
            "alice",
            self.db.authenticate_token(created["token"], require_udp_443=True),
        )
        self.assertEqual(created["token"], self.db.recover_proxy_token(created["id"]))

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
        self.assertFalse(record["allow_udp_443"])
        self.assertEqual("legacy", legacy_db.authenticate_token(token))
        self.assertIsNone(legacy_db.authenticate_token(token, require_udp_443=True))
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

    def test_auth_policy_rejects_users_over_connection_or_traffic_limits(self):
        stats = PolicyStatsClient(
            traffic={"alice": {"tx": 0, "rx": 0}}, online={"alice": 2}
        )
        manager = UsageManager(self.db, stats, pending_ttl=10, clock=lambda: 100.0)
        body = json.dumps(
            {"addr": "192.0.2.10:1234", "auth": "valid-token", "tx": 9}
        ).encode()

        self.assertEqual(
            {"ok": True, "id": "alice"}, handle_auth_payload(self.db, body, manager)[1]
        )
        self.assertEqual(
            {"ok": False, "id": ""}, handle_auth_payload(self.db, body, manager)[1]
        )

        self.db.add_traffic({"alice": {"tx": 250 * 1024**3, "rx": 0}})
        stats.online_values = {}
        self.assertEqual(
            {"ok": False, "id": ""}, handle_auth_payload(self.db, body, manager)[1]
        )

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

    def test_udp_443_auth_endpoint_only_allows_opted_in_users(self):
        server = make_internal_server(("127.0.0.1", 0), self.db)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = "http://127.0.0.1:{}/auth/udp-443".format(server.server_address[1])
        body = json.dumps(
            {"addr": "192.0.2.10:1234", "auth": "valid-token", "tx": 9}
        ).encode()

        request = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual({"ok": False, "id": ""}, json.load(response))

        self.db.update_proxy_user_limits(
            self.user["id"],
            device_limit=3,
            traffic_limit_bytes=250 * 1024**3,
            allow_udp_443=True,
            expected_generation=0,
        )
        request = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual({"ok": True, "id": "alice"}, json.load(response))


class RateLimiterTests(unittest.TestCase):
    def test_failed_logins_are_limited_per_address_and_success_resets(self):
        now = [1000.0]
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=60, clock=lambda: now[0])

        self.assertTrue(limiter.is_allowed("192.0.2.1"))
        self.assertEqual(0, limiter.record_failure("192.0.2.1"))
        self.assertEqual(60, limiter.record_failure("192.0.2.1"))
        self.assertFalse(limiter.is_allowed("192.0.2.1"))
        self.assertEqual(60, limiter.retry_after("192.0.2.1"))
        self.assertTrue(limiter.is_allowed("192.0.2.2"))

        now[0] += 61
        self.assertTrue(limiter.is_allowed("192.0.2.1"))
        limiter.record_failure("192.0.2.1")
        limiter.record_success("192.0.2.1")
        self.assertTrue(limiter.is_allowed("192.0.2.1"))

    def test_default_policy_locks_after_five_failures_for_fifteen_minutes(self):
        limiter = LoginRateLimiter()

        self.assertEqual(5, limiter.max_attempts)
        self.assertEqual(15 * 60, limiter.window_seconds)

    def test_address_tracking_is_bounded(self):
        limiter = LoginRateLimiter(max_attempts=2, max_addresses=3, clock=lambda: 1000.0)

        for suffix in range(10):
            limiter.record_failure("192.0.2.{}".format(suffix))

        self.assertLessEqual(len(limiter._attempts), 3)

    def test_ipv6_addresses_in_the_same_64_share_the_login_limit(self):
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=60, clock=lambda: 1000.0)

        self.assertEqual(0, limiter.record_failure("2001:db8:1:2::1"))
        self.assertEqual(60, limiter.record_failure("2001:db8:1:2::ffff"))

        self.assertFalse(limiter.is_allowed("2001:db8:1:2:abcd::1"))
        self.assertTrue(limiter.is_allowed("2001:db8:1:3::1"))

    def test_concurrent_attempts_from_one_address_cannot_bypass_the_limit(self):
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=60, clock=lambda: 1000.0)
        first_started = threading.Event()
        release_first = threading.Event()
        second_verified = threading.Event()
        results = []

        def first_verifier():
            first_started.set()
            self.assertTrue(release_first.wait(1))
            return None

        def second_verifier():
            second_verified.set()
            return 123

        first = threading.Thread(
            target=lambda: results.append(
                limiter.authenticate("192.0.2.1", first_verifier)
            )
        )
        second = threading.Thread(
            target=lambda: results.append(
                limiter.authenticate("192.0.2.1", second_verifier)
            )
        )
        first.start()
        self.assertTrue(first_started.wait(1))
        second.start()
        self.assertFalse(second_verified.wait(0.1))
        release_first.set()
        first.join(1)
        second.join(1)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertFalse(second_verified.is_set())
        self.assertEqual(
            [(None, 60, True), (None, 60, False)],
            results,
        )

    def test_authentication_lock_slot_is_bounded_for_every_address_hash(self):
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=60)
        address = "155.103.116.201"
        self.assertGreaterEqual(
            hashlib.sha256(address.encode("utf-8")).digest()[0],
            len(limiter._authentication_locks),
        )

        self.assertEqual((123, 0, True), limiter.authenticate(address, lambda: 123))


class FakeStatsClient:
    def __init__(self):
        self.kicked = []

    def snapshot(self):
        return {
            "traffic": {"alice": {"tx": 1024, "rx": 2048}},
            "online": {"alice": 2},
            "available": True,
        }

    def collect_and_clear(self):
        return self.snapshot()["traffic"]

    def online(self):
        return self.snapshot()["online"]

    def kick(self, name):
        self.kicked.append(name)

    def kick_many(self, names):
        self.kicked.extend(names)


class PolicyStatsClient(FakeStatsClient):
    def __init__(self, traffic=None, online=None):
        super().__init__()
        self.traffic_values = traffic or {}
        self.online_values = online or {}

    def collect_and_clear(self):
        values = self.traffic_values
        self.traffic_values = {}
        return values

    def online(self):
        return dict(self.online_values)


class UsageManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "panel.db", b"u" * 32)
        self.db.initialize()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_usage_collection_updates_cached_runtime_health(self):
        class FakeHealth:
            def __init__(self):
                self.events = []
                self.database_refreshes = 0

            def refresh_database(self):
                self.database_refreshes += 1

            def record_stats_sync(self, success):
                self.events.append(success)

        health = FakeHealth()
        stats = PolicyStatsClient()
        manager = UsageManager(self.db, stats, health_monitor=health)

        manager.collect_once()
        stats.collect_and_clear = lambda: (_ for _ in ()).throw(
            OSError("stats unavailable")
        )
        with self.assertRaises(OSError):
            manager.collect_once()

        self.assertEqual([True, False], health.events)
        self.assertEqual(2, health.database_refreshes)

    def test_failed_online_snapshot_marks_runtime_not_ready(self):
        class FakeHealth:
            def __init__(self):
                self.events = []

            def refresh_database(self):
                pass

            def record_stats_sync(self, success):
                self.events.append(success)

        health = FakeHealth()
        stats = PolicyStatsClient()
        stats.online = lambda: (_ for _ in ()).throw(OSError("stats unavailable"))
        manager = UsageManager(self.db, stats, health_monitor=health)

        manager.collect_once()

        self.assertEqual([True, False], health.events)

    def test_maintenance_sync_can_target_legacy_primary_stats_only(self):
        settings = mock.Mock(
            stats_url="http://127.0.0.1:19997",
            stats_443_url="http://127.0.0.1:19995",
            stats_secret="stats-secret",
            hysteria_port=19999,
        )

        primary = make_stats_client(settings, primary_only=True)
        combined = make_stats_client(settings, primary_only=False)
        secondary = make_stats_client(settings, secondary_only=True)

        self.assertIsInstance(primary, HysteriaStatsClient)
        self.assertNotIsInstance(primary, hysteria2_panel.CombinedHysteriaStatsClient)
        self.assertIsInstance(combined, hysteria2_panel.CombinedHysteriaStatsClient)
        self.assertIsInstance(secondary, HysteriaStatsClient)
        self.assertEqual("http://127.0.0.1:19995", secondary.base_url)

    def test_maintenance_stats_endpoint_selection_rejects_ambiguous_or_absent_secondary(self):
        settings = mock.Mock(
            stats_url="http://127.0.0.1:19997",
            stats_443_url="http://127.0.0.1:19995",
            stats_secret="stats-secret",
            hysteria_port=19999,
        )
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            make_stats_client(settings, primary_only=True, secondary_only=True)
        settings.hysteria_port = 443
        with self.assertRaisesRegex(ValueError, "not enabled"):
            make_stats_client(settings, secondary_only=True)

    def test_maintenance_quiesce_kicks_clients_before_the_final_collection(self):
        events = []
        stats = mock.Mock()
        stats.online.side_effect = [
            {"alice": 2, "bob": 1},
            {},
            {},
            {},
        ]
        stats.kick_many.side_effect = lambda names: events.append(
            ("kick", list(names))
        )

        hysteria2_panel.quiesce_stats_client(
            stats,
            attempts=4,
            interval=0.01,
            sleeper=lambda delay: events.append(("sleep", delay)),
        )

        self.assertEqual(
            [
                ("kick", ["alice", "bob"]),
                ("sleep", 0.01),
                ("sleep", 0.01),
                ("sleep", 0.01),
            ],
            events,
        )
        self.assertEqual(4, stats.online.call_count)

    def test_maintenance_quiesce_catches_a_late_authenticated_client(self):
        stats = mock.Mock()
        stats.online.side_effect = [
            {},
            {"late-auth": 1},
            {},
            {},
            {},
        ]

        hysteria2_panel.quiesce_stats_client(
            stats,
            attempts=5,
            interval=0,
            sleeper=lambda _delay: None,
        )

        stats.kick_many.assert_called_once_with(["late-auth"])
        self.assertEqual(5, stats.online.call_count)

    def test_maintenance_quiesce_allows_idle_sessions_that_remain_online_after_kick(self):
        stats = mock.Mock()
        stats.online.return_value = {"alice": 1}

        hysteria2_panel.quiesce_stats_client(
            stats,
            attempts=2,
            interval=0,
            sleeper=lambda _delay: None,
        )

        self.assertEqual(
            [mock.call(["alice"]), mock.call(["alice"])],
            stats.kick_many.call_args_list,
        )

    def test_sync_traffic_cli_wires_the_quiesce_flag(self):
        settings = mock.Mock()
        with mock.patch.object(
            hysteria2_panel.Settings, "from_mapping", return_value=settings
        ), mock.patch.object(
            hysteria2_panel.os, "geteuid", return_value=0, create=True
        ), mock.patch.object(hysteria2_panel, "sync_traffic") as sync:
            result = hysteria2_panel.main(
                ["sync-traffic", "--primary-only", "--quiesce"]
            )

        self.assertEqual(0, result)
        sync.assert_called_once_with(
            settings,
            primary_only=True,
            secondary_only=False,
            quiesce=True,
        )

    def test_maintenance_sync_defers_termination_until_the_critical_section_finishes(self):
        installed = {}
        restored = []

        def install_handler(signum, handler):
            previous = installed.get(signum, hysteria2_panel.signal.SIG_DFL)
            installed[signum] = handler
            restored.append((signum, handler))
            return previous

        completed = []
        with mock.patch.object(
            hysteria2_panel.signal, "signal", side_effect=install_handler
        ), mock.patch.object(
            hysteria2_panel.signal,
            "getsignal",
            return_value=hysteria2_panel.signal.SIG_DFL,
        ):
            with self.assertRaises(SystemExit) as raised:
                with hysteria2_panel.defer_termination_signals():
                    installed[hysteria2_panel.signal.SIGTERM](
                        hysteria2_panel.signal.SIGTERM, None
                    )
                    completed.append(True)

        self.assertEqual([True], completed)
        self.assertEqual(128 + hysteria2_panel.signal.SIGTERM, raised.exception.code)
        self.assertGreaterEqual(len(restored), 6)

    def test_deferred_termination_wins_over_a_concurrent_operation_error(self):
        with self.assertRaises(SystemExit) as raised:
            with hysteria2_panel.defer_termination_signals():
                os.kill(os.getpid(), hysteria2_panel.signal.SIGTERM)
                raise RuntimeError("operation also failed")

        self.assertEqual(128 + hysteria2_panel.signal.SIGTERM, raised.exception.code)
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)

    def test_backup_callback_runs_while_traffic_collection_is_locked(self):
        stats = PolicyStatsClient(traffic={})
        manager = UsageManager(self.db, stats)

        result = manager.run_after_collect(lambda: manager.lock.locked())

        self.assertTrue(result)

    def test_collects_durable_traffic_and_kicks_users_at_quota(self):
        user = self.db.create_proxy_user("alice", traffic_limit_bytes=300)
        stats = PolicyStatsClient(
            traffic={"alice": {"tx": 100, "rx": 200}}, online={"alice": 3}
        )
        manager = UsageManager(self.db, stats)

        manager.collect_once()
        manager.collect_once()

        record = self.db.get_proxy_user(user["id"])
        self.assertEqual((100, 200), (record["tx_bytes"], record["rx_bytes"]))
        self.assertEqual(["alice", "alice"], stats.kicked)
        self.assertFalse(manager.authorize("alice"))

    def test_collects_and_kicks_disabled_or_deleted_online_users(self):
        user = self.db.create_proxy_user("disabled")
        self.db.set_proxy_user_enabled(user["id"], False)
        stats = PolicyStatsClient(online={"disabled": 2, "deleted": 1})
        manager = UsageManager(self.db, stats)

        manager.collect_once()

        self.assertEqual(["deleted", "disabled"], sorted(stats.kicked))

    def test_collect_preserves_traffic_when_online_snapshot_fails(self):
        user = self.db.create_proxy_user("alice")
        stats = PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}})
        stats.online = lambda: (_ for _ in ()).throw(OSError("stats unavailable"))
        manager = UsageManager(self.db, stats)

        traffic = manager.collect_once()

        self.assertEqual({"alice": {"tx": 10, "rx": 20}}, traffic)
        record = self.db.get_proxy_user(user["id"])
        self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))
        self.assertEqual([], stats.kicked)

    def test_database_failure_buffers_cleared_traffic_until_the_next_success(self):
        user = self.db.create_proxy_user("alice")
        stats = PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}})
        manager = UsageManager(self.db, stats)
        durable_add = self.db.apply_traffic_batch
        attempts = 0

        def fail_once(batch_id, traffic):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise sqlite3.OperationalError("disk unavailable")
            return durable_add(batch_id, traffic)

        self.db.apply_traffic_batch = fail_once

        with self.assertRaises(sqlite3.OperationalError):
            manager.collect_once()
        self.assertEqual(
            {"alice": {"tx": 10, "rx": 20}}, manager.pending_traffic
        )
        self.assertEqual({}, stats.traffic_values)
        self.assertTrue(manager.pending_traffic_path.is_file())

        manager.collect_once()

        record = self.db.get_proxy_user(user["id"])
        self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))
        self.assertEqual({}, manager.pending_traffic)
        self.assertFalse(manager.pending_traffic_path.exists())
        self.assertEqual(2, attempts)

    def test_pending_traffic_survives_manager_restart(self):
        user = self.db.create_proxy_user("alice")
        stats = PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}})
        durable_apply = self.db.apply_traffic_batch
        manager = UsageManager(self.db, stats)
        self.db.apply_traffic_batch = lambda _batch_id, _traffic: (_ for _ in ()).throw(
            sqlite3.OperationalError("database unavailable")
        )

        with self.assertRaises(sqlite3.OperationalError):
            manager.collect_once()
        journal = manager.pending_traffic_path
        self.assertTrue(journal.is_file())
        self.assertEqual(0o600, journal.stat().st_mode & 0o777)

        self.db.apply_traffic_batch = durable_apply
        restarted = UsageManager(self.db, PolicyStatsClient())
        self.assertEqual({"alice": {"tx": 10, "rx": 20}}, restarted.pending_traffic)
        restarted.collect_once()

        record = self.db.get_proxy_user(user["id"])
        self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))
        self.assertFalse(journal.exists())

    def test_pending_journal_has_a_separate_two_endpoint_size_limit(self):
        manager = UsageManager(self.db, PolicyStatsClient())
        traffic = {"alice": {"tx": 10, "rx": 20}}
        manager._persist_pending_traffic_locked(traffic)
        self.assertGreater(manager.pending_traffic_path.stat().st_size, 1)

        with mock.patch.object(hysteria2_panel, "MAX_STATS_RESPONSE_BYTES", 1):
            restarted = UsageManager(self.db, PolicyStatsClient())

        self.assertEqual(traffic, restarted.pending_traffic)

    def test_pending_journal_size_uses_utf8_instead_of_ascii_escapes(self):
        manager = UsageManager(self.db, PolicyStatsClient())
        traffic = {
            "用户{:03d}".format(index): {"tx": index, "rx": index + 1}
            for index in range(256)
        }
        payload = {"batch_id": "0" * 32, "traffic": traffic}
        utf8_size = len(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        escaped_size = len(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        self.assertLess(utf8_size, escaped_size)

        with mock.patch.object(
            hysteria2_panel,
            "MAX_PENDING_TRAFFIC_BYTES",
            (utf8_size + escaped_size) // 2,
        ):
            manager._persist_pending_traffic_locked(traffic)

        journal = json.loads(manager.pending_traffic_path.read_text())
        self.assertEqual(traffic, journal["traffic"])

    def test_journal_creation_failure_commits_before_manager_is_destroyed(self):
        user = self.db.create_proxy_user("alice")
        stats = PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}})
        manager = UsageManager(self.db, stats)
        durable_apply = self.db.apply_traffic_batch
        applied_batch_ids = []

        def record_apply(batch_id, traffic):
            applied_batch_ids.append(batch_id)
            return durable_apply(batch_id, traffic)

        self.db.apply_traffic_batch = record_apply

        fixed_batch_id = "a" * 32
        with mock.patch(
            "hysteria2_panel.uuid.uuid4",
            return_value=mock.Mock(hex=fixed_batch_id),
        ), mock.patch(
            "hysteria2_panel.tempfile.mkstemp", side_effect=OSError("disk full")
        ):
            manager.collect_once()

        self.assertEqual({}, stats.traffic_values)
        self.assertEqual([fixed_batch_id], applied_batch_ids)
        self.assertEqual({}, manager.pending_traffic)
        self.assertFalse(manager.pending_traffic_path.exists())

        del manager
        reopened_database = Database(self.db.path, self.db.hmac_key)
        reopened_database.initialize()
        restarted = UsageManager(reopened_database, PolicyStatsClient())
        restarted.collect_once()

        record = reopened_database.get_proxy_user(user["id"])
        self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))

    def test_transient_journal_and_database_failures_still_survive_process_restart(self):
        user = self.db.create_proxy_user("alice")
        manager = UsageManager(
            self.db,
            PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}}),
        )
        durable_apply = self.db.apply_traffic_batch
        calls = {"value": 0}

        def fail_database_once(batch_id, traffic):
            calls["value"] += 1
            if calls["value"] == 1:
                raise sqlite3.OperationalError("database temporarily unavailable")
            return durable_apply(batch_id, traffic)

        self.db.apply_traffic_batch = fail_database_once
        try:
            with mock.patch(
                "hysteria2_panel.tempfile.mkstemp", side_effect=OSError("disk temporarily unavailable")
            ):
                manager.collect_once()
        finally:
            self.db.apply_traffic_batch = durable_apply

        del manager
        restarted_database = Database(self.db.path, self.db.hmac_key)
        restarted_database.initialize()
        record = restarted_database.get_proxy_user(user["id"])
        self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))

    def test_journal_and_database_failure_keep_cleared_traffic_for_runtime_retry(self):
        self.db.create_proxy_user("alice")
        stats = PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}})
        manager = UsageManager(self.db, stats)
        durable_apply = self.db.apply_traffic_batch
        self.db.apply_traffic_batch = lambda *_args: (_ for _ in ()).throw(
            sqlite3.OperationalError("database unavailable")
        )

        try:
            with mock.patch(
                "hysteria2_panel.tempfile.mkstemp", side_effect=OSError("disk full")
            ):
                with self.assertRaisesRegex(OSError, "disk full") as raised:
                    manager.collect_once()
        finally:
            self.db.apply_traffic_batch = durable_apply

        self.assertIsInstance(raised.exception.__cause__, sqlite3.OperationalError)
        self.assertEqual({}, stats.traffic_values)
        self.assertEqual({"alice": {"tx": 10, "rx": 20}}, manager.pending_traffic)
        self.assertRegex(manager.pending_traffic_batch_id, r"^[0-9a-f]{32}$")

        manager.collect_once()

        record = self.db.get_proxy_user_by_name("alice")
        self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))

    def test_pending_journal_rename_and_removal_are_directory_fsynced(self):
        self.db.create_proxy_user("alice")
        manager = UsageManager(
            self.db,
            PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}}),
        )
        directory_syncs = []
        real_fsync = os.fsync

        def record_fsync(descriptor):
            if hysteria2_panel.stat.S_ISDIR(os.fstat(descriptor).st_mode):
                directory_syncs.append(descriptor)
            return real_fsync(descriptor)

        with mock.patch.object(hysteria2_panel.os, "fsync", side_effect=record_fsync):
            manager.collect_once()

        self.assertEqual(2, len(directory_syncs))
        self.assertFalse(manager.pending_traffic_path.exists())

    def test_root_maintenance_journal_inherits_the_database_owner(self):
        manager = UsageManager(
            self.db,
            PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}}),
        )
        expected = self.db.path.stat()
        ownership = []

        with mock.patch.object(
            hysteria2_panel.os, "geteuid", return_value=0, create=True
        ), mock.patch.object(
            hysteria2_panel.os,
            "fchown",
            side_effect=lambda _fd, uid, gid: ownership.append((uid, gid)),
        ):
            with self.assertRaises(sqlite3.OperationalError):
                durable_apply = self.db.apply_traffic_batch
                self.db.apply_traffic_batch = lambda *_args: (_ for _ in ()).throw(
                    sqlite3.OperationalError("database unavailable")
                )
                try:
                    manager.collect_once()
                finally:
                    self.db.apply_traffic_batch = durable_apply

        self.assertEqual([(expected.st_uid, expected.st_gid)], ownership)

    def test_pending_traffic_replay_is_idempotent_after_commit_before_cleanup(self):
        user = self.db.create_proxy_user("alice")
        stats = PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}})
        manager = UsageManager(self.db, stats)
        remove = manager._remove_pending_traffic_locked
        manager._remove_pending_traffic_locked = lambda: (_ for _ in ()).throw(
            OSError("simulated crash before journal cleanup")
        )

        with self.assertRaises(OSError):
            manager.collect_once()
        self.assertTrue(manager.pending_traffic_path.is_file())
        manager._remove_pending_traffic_locked = remove

        restarted = UsageManager(self.db, PolicyStatsClient())
        restarted.collect_once()

        record = self.db.get_proxy_user(user["id"])
        self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))
        self.assertFalse(manager.pending_traffic_path.exists())

    def test_reserves_pending_connections_to_enforce_the_limit(self):
        self.db.create_proxy_user("alice", device_limit=3)
        stats = PolicyStatsClient(online={"alice": 2})
        manager = UsageManager(self.db, stats, pending_ttl=10, clock=lambda: 100.0)

        self.assertTrue(manager.authorize("alice"))
        self.assertFalse(manager.authorize("alice"))

    def test_fourth_client_is_rejected_without_kicking_existing_clients(self):
        self.db.create_proxy_user("alice", device_limit=3)
        stats = PolicyStatsClient(online={})
        manager = UsageManager(self.db, stats, pending_ttl=10, clock=lambda: 100.0)

        self.assertEqual(
            [True, True, True, False],
            [manager.authorize("alice") for _ in range(4)],
        )
        self.assertEqual([], stats.kicked)

    def test_rejects_authentication_when_online_limit_cannot_be_checked(self):
        self.db.create_proxy_user("alice", device_limit=3)
        stats = PolicyStatsClient()
        stats.online = lambda: (_ for _ in ()).throw(OSError("stats unavailable"))
        manager = UsageManager(self.db, stats)

        self.assertFalse(manager.authorize("alice"))

    def test_rejects_authentication_when_traffic_limit_cannot_be_checked(self):
        self.db.create_proxy_user("alice", traffic_limit_bytes=300)
        stats = PolicyStatsClient(online={"alice": 0})
        stats.collect_and_clear = lambda: (_ for _ in ()).throw(
            OSError("traffic stats unavailable")
        )
        manager = UsageManager(self.db, stats)

        self.assertFalse(manager.authorize("alice"))

    def test_partial_combined_traffic_is_saved_before_authentication_fails_closed(self):
        user = self.db.create_proxy_user("alice", traffic_limit_bytes=300)
        primary = PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}})
        udp_443 = PolicyStatsClient()
        udp_443.collect_and_clear = lambda: (_ for _ in ()).throw(
            OSError("UDP 443 stats unavailable")
        )
        manager = UsageManager(
            self.db,
            hysteria2_panel.CombinedHysteriaStatsClient(primary, udp_443),
        )

        self.assertFalse(manager.authorize("alice"))
        record = self.db.get_proxy_user(user["id"])
        self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))

    def test_snapshot_and_resets_include_pending_hysteria_traffic(self):
        alice = self.db.create_proxy_user("alice")
        bob = self.db.create_proxy_user("bob")
        stats = PolicyStatsClient(
            traffic={"alice": {"tx": 100, "rx": 200}, "bob": {"tx": 8, "rx": 9}},
            online={"alice": 1},
        )
        manager = UsageManager(self.db, stats)

        snapshot = manager.snapshot()
        self.assertEqual({"tx": 100, "rx": 200}, snapshot["traffic"]["alice"])
        self.assertEqual({"alice": 1}, snapshot["online"])
        self.assertTrue(snapshot["available"])

        stats.traffic_values = {"alice": {"tx": 5, "rx": 6}}
        manager.reset_user(alice["id"], expected_generation=0)
        self.assertEqual((0, 0), tuple(self.db.get_proxy_user(alice["id"])[key] for key in ("tx_bytes", "rx_bytes")))
        self.assertEqual(["alice"], stats.kicked)

        manager.reset_all()
        self.assertEqual((0, 0), tuple(self.db.get_proxy_user(bob["id"])[key] for key in ("tx_bytes", "rx_bytes")))


class OperationsTests(unittest.TestCase):
    @staticmethod
    def restore_settings(directory):
        return mock.Mock(
            database_path=Path(directory) / "panel.db",
            hmac_key=b"r" * 32,
            tls_cert=Path(directory) / "server.crt",
            tls_key=Path(directory) / "server.key",
            public_host="vpn.example.test",
            hysteria_port=19999,
            node_name="test-node",
            panel_scheme="http",
            panel_port=19998,
            auth_port=19996,
            stats_url="http://127.0.0.1:19997",
            stats_443_url="http://127.0.0.1:19995",
            stats_secret="stats-secret",
        )

    def test_restore_marker_is_persistent_root_configuration_state(self):
        self.assertEqual(
            Path("/etc/hysteria2-panel/.restore-active"),
            hysteria2_panel.RESTORE_ACTIVE_MARKER,
        )

    @staticmethod
    def write_egress_fixture(directory, policy="web"):
        root = Path(directory)
        env_path = root / "panel.env"
        primary = root / "hysteria.yaml"
        secondary = root / "hysteria-443.yaml"
        env_path.write_text(
            "HY2PANEL_PANEL_PORT=19998\nHY2PANEL_EGRESS_POLICY={}\n".format(policy)
        )
        config = """listen: :19999
{}masquerade:
  type: string
""".format(panel_operations.EgressPolicyManager._acl_block(policy, 19998))
        primary.write_text(config)
        secondary.write_text(config.replace("listen: :19999", "listen: :443"))
        for path in (env_path, primary, secondary):
            path.chmod(0o640)
        return env_path, primary, secondary

    @staticmethod
    def write_egress_state(state_path, policy, paths):
        state_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "policy": policy,
                    "files": {
                        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in paths
                    },
                }
            )
        )
        state_path.chmod(0o644)

    def test_egress_policy_controller_reads_state_and_starts_only_fixed_units(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path, primary, secondary = self.write_egress_fixture(directory)
            state_path = Path(directory) / "egress-state.json"
            self.write_egress_state(
                state_path, "web", (env_path, primary, secondary)
            )
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                if command[:2] == ["/bin/systemctl", "show"]:
                    return mock.Mock(
                        returncode=0,
                        stdout="LoadState=loaded\nActiveState=active\n",
                        stderr="",
                    )
                env_path.write_text(
                    env_path.read_text().replace("=web", "=full")
                )
                for path in (primary, secondary):
                    path.write_bytes(
                        panel_operations.EgressPolicyManager._replace_acl(
                            path.read_bytes(), "full", 19998
                        )
                    )
                self.write_egress_state(
                    state_path, "full", (env_path, primary, secondary)
                )
                return mock.Mock(returncode=0, stdout="", stderr="")

            controller = panel_operations.EgressPolicyController(
                runner=runner,
                env_path=env_path,
                config_paths=(primary, secondary),
                state_path=state_path,
                expected_uid=os.geteuid(),
            )

            self.assertEqual("web", controller.status())
            self.assertEqual("full", controller.switch("full"))
            with self.assertRaises(ValueError):
                controller.switch("full;id")
            self.assertEqual(
                [[
                    "/usr/bin/sudo",
                    "-n",
                    "/bin/systemctl",
                    "start",
                    "hysteria2-panel-egress-full.service",
                ]],
                [
                    command
                    for command, _kwargs in calls
                    if command[:2] == ["/usr/bin/sudo", "-n"]
                ],
            )
            self.assertTrue(all("shell" not in kwargs for _command, kwargs in calls))

    def test_egress_policy_controller_reports_drift_and_reconciles_same_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path, primary, secondary = self.write_egress_fixture(directory)
            state_path = Path(directory) / "egress-state.json"
            self.write_egress_state(
                state_path, "web", (env_path, primary, secondary)
            )
            primary.write_bytes(
                panel_operations.EgressPolicyManager._replace_acl(
                    primary.read_bytes(), "full", 19998
                )
            )
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                if command[:2] == ["/bin/systemctl", "show"]:
                    return mock.Mock(
                        returncode=0,
                        stdout="LoadState=loaded\nActiveState=active\n",
                        stderr="",
                    )
                primary.write_bytes(
                    panel_operations.EgressPolicyManager._replace_acl(
                        primary.read_bytes(), "web", 19998
                    )
                )
                self.write_egress_state(
                    state_path, "web", (env_path, primary, secondary)
                )
                return mock.Mock(returncode=0, stdout="", stderr="")

            controller = panel_operations.EgressPolicyController(
                runner=runner,
                env_path=env_path,
                config_paths=(primary, secondary),
                state_path=state_path,
                expected_uid=os.geteuid(),
            )

            self.assertEqual("inconsistent", controller.status())
            self.assertEqual("web", controller.switch("web"))
            self.assertIn(
                [
                    "/usr/bin/sudo",
                    "-n",
                    "/bin/systemctl",
                    "start",
                    "hysteria2-panel-egress-web.service",
                ],
                [command for command, _kwargs in calls],
            )

    def test_egress_policy_manager_switches_both_configs_and_persists_state(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path, primary, secondary = self.write_egress_fixture(directory)
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                return mock.Mock(returncode=0, stdout="active\n", stderr="")

            manager = panel_operations.EgressPolicyManager(
                runner=runner,
                env_path=env_path,
                config_paths=(primary, secondary),
                state_path=Path(directory) / "egress-state.json",
                transaction_path=Path(directory) / "egress-transaction.json",
                expected_uid=os.geteuid(),
            )
            manager.apply("full", panel_port=19998)

            self.assertIn("HY2PANEL_EGRESS_POLICY=full", env_path.read_text())
            for path in (primary, secondary):
                source = path.read_text()
                self.assertIn('- "reject(127.0.0.0/8)"', source)
                self.assertIn('- "reject(100.64.0.0/10)"', source)
                self.assertIn('- "reject(fc00::/7)"', source)
                self.assertIn('- "direct(all)"', source)
                self.assertNotIn('- "reject(all)"', source)

            manager.apply("web", panel_port=19998)
            self.assertIn("HY2PANEL_EGRESS_POLICY=web", env_path.read_text())
            for path in (primary, secondary):
                source = path.read_text()
                self.assertIn('- "direct(all, tcp/19998)"', source)
                self.assertIn('- "reject(all)"', source)
                self.assertNotIn('- "direct(all)"', source)

            commands = [command for command, _kwargs in calls]
            self.assertEqual(2, commands.count([
                "/bin/systemctl", "restart", "hysteria2-panel-server.service"
            ]))
            self.assertTrue(all("shell" not in kwargs for _command, kwargs in calls))

    def test_egress_policy_manager_rolls_back_every_file_when_restart_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path, primary, secondary = self.write_egress_fixture(directory)
            originals = {path: path.read_bytes() for path in (env_path, primary, secondary)}
            restart_attempts = 0

            def runner(command, **_kwargs):
                nonlocal restart_attempts
                if command[:2] == ["/bin/systemctl", "restart"]:
                    restart_attempts += 1
                    return mock.Mock(
                        returncode=1 if restart_attempts == 1 else 0,
                        stdout="",
                        stderr="failed",
                    )
                return mock.Mock(returncode=0, stdout="active\n", stderr="")

            manager = panel_operations.EgressPolicyManager(
                runner=runner,
                env_path=env_path,
                config_paths=(primary, secondary),
                state_path=Path(directory) / "egress-state.json",
                transaction_path=Path(directory) / "egress-transaction.json",
                expected_uid=os.geteuid(),
            )

            with self.assertRaises(RuntimeError):
                manager.apply("full", panel_port=19998)

            self.assertEqual(2, restart_attempts)
            self.assertEqual(
                originals,
                {path: path.read_bytes() for path in (env_path, primary, secondary)},
            )

    def test_egress_policy_manager_does_not_start_a_stopped_server(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path, primary, secondary = self.write_egress_fixture(directory)
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                if command == [
                    "/bin/systemctl",
                    "is-active",
                    "hysteria2-panel-server.service",
                ]:
                    return mock.Mock(returncode=3, stdout="inactive\n", stderr="")
                return mock.Mock(returncode=0, stdout="active\n", stderr="")

            manager = panel_operations.EgressPolicyManager(
                runner=runner,
                env_path=env_path,
                config_paths=(primary, secondary),
                state_path=Path(directory) / "egress-state.json",
                transaction_path=Path(directory) / "egress-transaction.json",
                expected_uid=os.geteuid(),
            )

            manager.apply("full", panel_port=19998)

            self.assertIn("HY2PANEL_EGRESS_POLICY=full", env_path.read_text())
            commands = [command for command, _kwargs in calls]
            self.assertNotIn(
                ["/bin/systemctl", "restart", "hysteria2-panel-server.service"],
                commands,
            )

    def test_egress_policy_manager_restarts_an_active_secondary_only(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path, primary, secondary = self.write_egress_fixture(directory)
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                if command[:3] == ["/bin/systemctl", "is-active", "hysteria2-panel-server.service"]:
                    return mock.Mock(returncode=3, stdout="inactive\n", stderr="")
                return mock.Mock(returncode=0, stdout="active\n", stderr="")

            manager = panel_operations.EgressPolicyManager(
                runner=runner,
                env_path=env_path,
                config_paths=(primary, secondary),
                state_path=Path(directory) / "egress-state.json",
                transaction_path=Path(directory) / "egress-transaction.json",
                expected_uid=os.geteuid(),
            )

            manager.apply("full", panel_port=19998)

            restart_commands = [
                command for command, _kwargs in calls
                if command[:2] == ["/bin/systemctl", "restart"]
            ]
            self.assertEqual(
                [["/bin/systemctl", "restart", "hysteria2-panel-server-443.service"]],
                restart_commands,
            )

    def test_egress_policy_manager_preserves_an_inactive_secondary(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path, primary, secondary = self.write_egress_fixture(directory)
            active = {
                "hysteria2-panel-server.service": True,
                "hysteria2-panel-server-443.service": False,
            }

            def runner(command, **_kwargs):
                if command[:2] == ["/bin/systemctl", "restart"]:
                    active["hysteria2-panel-server.service"] = True
                    active["hysteria2-panel-server-443.service"] = True
                    return mock.Mock(returncode=0, stdout="", stderr="")
                if command[:2] == ["/bin/systemctl", "stop"]:
                    active[command[2]] = False
                    return mock.Mock(returncode=0, stdout="", stderr="")
                if command[:2] == ["/bin/systemctl", "is-active"]:
                    state = active[command[2]]
                    return mock.Mock(
                        returncode=0 if state else 3,
                        stdout="active\n" if state else "inactive\n",
                        stderr="",
                    )
                raise AssertionError(command)

            manager = panel_operations.EgressPolicyManager(
                runner=runner,
                env_path=env_path,
                config_paths=(primary, secondary),
                state_path=Path(directory) / "egress-state.json",
                transaction_path=Path(directory) / "egress-transaction.json",
                expected_uid=os.geteuid(),
            )

            manager.apply("full", panel_port=19998)

            self.assertTrue(active["hysteria2-panel-server.service"])
            self.assertFalse(active["hysteria2-panel-server-443.service"])

    def test_egress_policy_manager_recovers_a_power_loss_before_env_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path, primary, secondary = self.write_egress_fixture(directory)
            originals = {
                path: path.read_bytes() for path in (env_path, primary, secondary)
            }
            state_path = Path(directory) / "egress-state.json"
            transaction_path = Path(directory) / "egress-transaction.json"
            self.write_egress_state(
                state_path, "web", (env_path, primary, secondary)
            )
            manager = panel_operations.EgressPolicyManager(
                runner=lambda _command, **_kwargs: mock.Mock(
                    returncode=0, stdout="active\n", stderr=""
                ),
                env_path=env_path,
                config_paths=(primary, secondary),
                state_path=state_path,
                transaction_path=transaction_path,
                expected_uid=os.geteuid(),
            )
            real_replace = panel_operations._atomic_replace_managed_file
            replacements = 0

            def interrupted_replace(path, payload, metadata):
                nonlocal replacements
                real_replace(path, payload, metadata)
                replacements += 1
                if replacements == 2:
                    raise BaseException("simulated power loss")

            with mock.patch.object(
                panel_operations,
                "_atomic_replace_managed_file",
                side_effect=interrupted_replace,
            ), self.assertRaises(BaseException):
                manager.apply("full", panel_port=19998)

            self.assertTrue(transaction_path.exists())
            manager.recover()
            self.assertFalse(transaction_path.exists())
            self.assertEqual(
                originals,
                {path: path.read_bytes() for path in (env_path, primary, secondary)},
            )

    def test_egress_policy_manager_rejects_symlinked_managed_config(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path, primary, secondary = self.write_egress_fixture(directory)
            real_primary = Path(directory) / "real-primary.yaml"
            primary.replace(real_primary)
            primary.symlink_to(real_primary)
            manager = panel_operations.EgressPolicyManager(
                env_path=env_path,
                config_paths=(primary, secondary),
                expected_uid=os.geteuid(),
            )

            with self.assertRaises(RuntimeError):
                manager.apply("full", panel_port=19998)

    def test_apply_egress_policy_cli_requires_root_and_uses_the_shared_lock(self):
        settings = mock.Mock(panel_port=19998)
        manager = mock.Mock()
        with mock.patch.object(
            hysteria2_panel.Settings, "from_mapping", return_value=settings
        ), mock.patch.object(
            hysteria2_panel, "EgressPolicyManager", return_value=manager
        ), mock.patch.object(
            hysteria2_panel.os, "geteuid", return_value=0
        ), mock.patch.object(
            hysteria2_panel,
            "exclusive_maintenance_lock",
            return_value=contextlib.nullcontext(),
        ) as maintenance_lock, mock.patch.object(
            hysteria2_panel,
            "defer_termination_signals",
            return_value=contextlib.nullcontext(),
        ), mock.patch("builtins.print"):
            self.assertEqual(0, hysteria2_panel.main(["apply-egress-policy", "full"]))

        maintenance_lock.assert_called_once_with(blocking=False)
        manager.apply.assert_called_once_with("full", 19998)

        with mock.patch.object(
            hysteria2_panel.Settings, "from_mapping", return_value=settings
        ), mock.patch.object(
            hysteria2_panel, "EgressPolicyManager"
        ) as manager_type, mock.patch.object(
            hysteria2_panel.os, "geteuid", return_value=1000
        ), mock.patch("builtins.print"):
            self.assertEqual(1, hysteria2_panel.main(["apply-egress-policy", "web"]))
        manager_type.assert_not_called()

    def test_egress_recovery_cli_runs_before_environment_loading(self):
        manager = mock.Mock()
        with mock.patch.object(
            hysteria2_panel, "EgressPolicyManager", return_value=manager
        ), mock.patch.object(
            hysteria2_panel.os, "geteuid", return_value=0
        ), mock.patch.object(
            hysteria2_panel.Settings, "from_mapping"
        ) as load_settings, mock.patch.object(
            hysteria2_panel,
            "exclusive_maintenance_lock",
            return_value=contextlib.nullcontext(),
        ) as maintenance_lock, mock.patch.object(
            hysteria2_panel,
            "defer_termination_signals",
            return_value=contextlib.nullcontext(),
        ):
            self.assertEqual(0, hysteria2_panel.main(["recover-egress-policy"]))

        load_settings.assert_not_called()
        maintenance_lock.assert_called_once_with(blocking=True)
        manager.recover.assert_called_once_with()

    def test_installer_can_record_the_verified_current_egress_state(self):
        settings = mock.Mock(panel_port=19998)
        manager = mock.Mock()
        with mock.patch.object(
            hysteria2_panel.Settings, "from_mapping", return_value=settings
        ), mock.patch.object(
            hysteria2_panel, "EgressPolicyManager", return_value=manager
        ), mock.patch.object(
            hysteria2_panel.os, "geteuid", return_value=0
        ):
            self.assertEqual(
                0,
                hysteria2_panel.main(
                    ["record-egress-policy-state", "full"]
                ),
            )

        manager.record_current_state.assert_called_once_with("full", 19998)

    def test_resume_after_restore_cli_loads_and_passes_environment_settings(self):
        settings = mock.Mock()
        with mock.patch.object(
            hysteria2_panel.Settings, "from_mapping", return_value=settings
        ) as load_settings, mock.patch.object(
            hysteria2_panel, "resume_after_restore"
        ) as resume, mock.patch.object(
            hysteria2_panel.os, "geteuid", return_value=0
        ):
            result = hysteria2_panel.main(["resume-after-restore"])

        self.assertEqual(0, result)
        load_settings.assert_called_once_with(os.environ)
        resume.assert_called_once_with(settings, strict_paths=False)

    def test_restore_and_resume_reject_a_symlink_marker_without_starting_services(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "restore-active"
            marker.symlink_to(Path(directory) / "missing-target")
            settings = self.restore_settings(directory)
            with mock.patch.object(
                hysteria2_panel, "start_restore_services"
            ) as start_services:
                with self.assertRaisesRegex(RuntimeError, "marker is invalid"):
                    hysteria2_panel.resume_after_restore(
                        settings,
                        lock_path=Path(directory) / "resume.lock",
                        marker_path=marker,
                    )
                with self.assertRaisesRegex(RuntimeError, "marker is invalid"):
                    hysteria2_panel.restore_pending(
                        settings,
                        lock_path=Path(directory) / "restore.lock",
                        marker_path=marker,
                    )

            start_services.assert_not_called()

    def test_recover_restore_files_cli_runs_before_environment_settings_load(self):
        with mock.patch.object(
            hysteria2_panel.Settings, "from_mapping"
        ) as load_settings, mock.patch.object(
            hysteria2_panel, "recover_restore_files"
        ) as recover, mock.patch.object(hysteria2_panel.os, "geteuid", return_value=0):
            result = hysteria2_panel.main(["recover-restore-files"])

        self.assertEqual(0, result)
        recover.assert_called_once_with(strict_paths=False)
        load_settings.assert_not_called()

    def test_maintenance_lock_is_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "maintenance.lock"
            with hysteria2_panel.exclusive_maintenance_lock(lock_path):
                with self.assertRaisesRegex(RuntimeError, "维护任务正在运行"):
                    with hysteria2_panel.exclusive_maintenance_lock(lock_path):
                        self.fail("the second maintenance lock must not be acquired")

            with hysteria2_panel.exclusive_maintenance_lock(lock_path):
                self.assertTrue(lock_path.is_file())
                self.assertEqual(0o600, lock_path.stat().st_mode & 0o777)

    def test_maintenance_lock_can_wait_until_the_owner_releases_it(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "maintenance.lock"
            attempting = threading.Event()
            acquired = threading.Event()

            def wait_for_lock():
                attempting.set()
                with hysteria2_panel.exclusive_maintenance_lock(
                    lock_path, blocking=True
                ):
                    acquired.set()

            with hysteria2_panel.exclusive_maintenance_lock(lock_path):
                waiter = threading.Thread(target=wait_for_lock)
                waiter.start()
                self.assertTrue(attempting.wait(1))
                self.assertFalse(acquired.wait(0.1))

            waiter.join(1)
            self.assertFalse(waiter.is_alive())
            self.assertTrue(acquired.is_set())

    def test_recover_without_marker_never_waits_for_an_installer_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "maintenance.lock"
            marker = Path(directory) / "restore-active"
            with hysteria2_panel.exclusive_maintenance_lock(lock_path), mock.patch.object(
                hysteria2_panel, "_read_restore_transaction"
            ) as read_transaction:
                started = time.monotonic()
                hysteria2_panel.recover_restore_files(
                    lock_path=lock_path,
                    marker_path=marker,
                    expected_uid=os.geteuid(),
                    strict_paths=False,
                )
                self.assertLess(time.monotonic() - started, 0.1)
            read_transaction.assert_not_called()

    def test_boot_recover_quarantines_an_orphan_pending_upload_without_a_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work_dir = root / "work"
            work_dir.mkdir(mode=0o700)
            work_dir.chmod(0o700)
            pending = work_dir / "pending-restore.zip"
            pending.write_bytes(b"orphan upload")
            pending.chmod(0o600)
            pending_uid = pending.stat().st_uid

            hysteria2_panel.recover_restore_files(
                lock_path=root / "maintenance.lock",
                marker_path=root / "restore-active",
                pending_path=pending,
                work_dir=work_dir,
                pending_uid=pending_uid,
                expected_uid=0,
                strict_paths=False,
            )

            self.assertFalse(pending.exists())
            quarantined = list(work_dir.glob("failed-restore-orphan-*.zip"))
            self.assertEqual(1, len(quarantined))
            self.assertEqual(b"orphan upload", quarantined[0].read_bytes())

    def test_boot_recover_quarantines_a_captured_orphan_without_a_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work_dir = root / "work"
            work_dir.mkdir(mode=0o700)
            work_dir.chmod(0o700)
            captured = root / "restore-active.archive"
            captured.write_bytes(b"captured orphan")
            captured.chmod(0o600)

            hysteria2_panel.recover_restore_files(
                lock_path=root / "maintenance.lock",
                marker_path=root / "restore-active",
                pending_path=work_dir / "pending-restore.zip",
                captured_path=captured,
                work_dir=work_dir,
                pending_uid=os.geteuid(),
                expected_uid=os.geteuid(),
                strict_paths=False,
            )

            self.assertFalse(captured.exists())
            quarantined = list(work_dir.glob("failed-restore-orphan-captured-*.zip"))
            self.assertEqual(1, len(quarantined))
            self.assertEqual(b"captured orphan", quarantined[0].read_bytes())

    def test_recover_rechecks_marker_after_waiting_for_the_maintenance_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work_dir = root / "work"
            work_dir.mkdir(mode=0o700)
            work_dir.chmod(0o700)
            marker = root / "restore-active"
            pending = work_dir / "pending-restore.zip"
            pending.write_bytes(b"pending")
            pending.chmod(0o600)
            entered = threading.Event()
            completed = threading.Event()
            record = {"phase": "disk-consistent", "outcome": "rolled-back"}

            def recover():
                entered.set()
                hysteria2_panel.recover_restore_files(
                    lock_path=root / "maintenance.lock",
                    marker_path=marker,
                    pending_path=pending,
                    work_dir=work_dir,
                    pending_uid=os.geteuid(),
                    expected_uid=os.geteuid(),
                    strict_paths=False,
                )
                completed.set()

            with mock.patch.object(
                hysteria2_panel,
                "_read_restore_transaction",
                return_value=record,
            ), mock.patch.object(
                hysteria2_panel,
                "_reconcile_to_services_pending",
                return_value={"phase": "services-pending"},
            ) as reconcile:
                with hysteria2_panel.exclusive_maintenance_lock(
                    root / "maintenance.lock"
                ):
                    worker = threading.Thread(target=recover)
                    worker.start()
                    self.assertTrue(entered.wait(1))
                    self.assertFalse(completed.wait(0.1))
                    marker.write_text("{}", encoding="utf-8")
                    marker.chmod(0o600)
                    pending.unlink()

                worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertTrue(completed.is_set())
            reconcile.assert_called_once()

    def test_durable_move_handles_cross_filesystem_restore_quarantine(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.zip"
            target_dir = Path(directory) / "target"
            target_dir.mkdir()
            destination = target_dir / "failed.zip"
            source.write_bytes(b"restore archive")
            real_replace = os.replace
            first = {"value": True}

            def replace_with_cross_device(source_path, destination_path):
                if first["value"]:
                    first["value"] = False
                    raise OSError(hysteria2_panel.errno.EXDEV, "cross-device")
                return real_replace(source_path, destination_path)

            with mock.patch.object(
                hysteria2_panel.os, "replace", side_effect=replace_with_cross_device
            ):
                hysteria2_panel._durable_move(source, destination)

            self.assertFalse(source.exists())
            self.assertEqual(b"restore archive", destination.read_bytes())

    def test_secure_restore_copy_handles_short_writes_and_preserves_source_on_stall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "pending-restore.zip"
            captured = root / "captured.zip"
            source.write_bytes(b"complete restore payload")
            source.chmod(0o600)
            database = Database(root / "panel.db", b"r" * 32)
            database.initialize()
            manager = BackupManager(
                database=database,
                hmac_key=b"r" * 32,
                tls_cert=root / "server.crt",
                tls_key=root / "server.key",
                public_host="vpn.example.test",
                hysteria_port=19999,
                work_dir=root,
            )
            real_write = os.write

            def short_write(descriptor, value):
                return real_write(descriptor, value[: max(1, len(value) // 2)])

            with mock.patch.object(hysteria2_panel.os, "write", side_effect=short_write):
                manager._secure_pending_archive(captured)
            self.assertEqual(source.read_bytes(), captured.read_bytes())

            captured.unlink()
            with mock.patch.object(hysteria2_panel.os, "write", return_value=0):
                with self.assertRaisesRegex(OSError, "short write"):
                    manager._secure_pending_archive(captured)
            self.assertEqual(b"complete restore payload", source.read_bytes())
            self.assertFalse(captured.exists())

    def test_orphan_quarantine_handles_short_writes_and_preserves_source_on_stall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "orphan.zip"
            destination = root / "quarantined.zip"
            payload = b"complete orphan restore payload"
            source.write_bytes(payload)
            source.chmod(0o600)
            real_write = os.write

            def short_write(descriptor, value):
                return real_write(descriptor, value[: max(1, len(value) // 2)])

            with mock.patch.object(hysteria2_panel.os, "write", side_effect=short_write):
                hysteria2_panel._quarantine_secure_orphan(
                    source,
                    destination,
                    hysteria2_panel.MAX_BACKUP_ARCHIVE_BYTES,
                    os.geteuid(),
                )
            self.assertFalse(source.exists())
            self.assertEqual(payload, destination.read_bytes())

            destination.unlink()
            source.write_bytes(payload)
            source.chmod(0o600)
            with mock.patch.object(hysteria2_panel.os, "write", return_value=0):
                with self.assertRaisesRegex(OSError, "short write"):
                    hysteria2_panel._quarantine_secure_orphan(
                        source,
                        destination,
                        hysteria2_panel.MAX_BACKUP_ARCHIVE_BYTES,
                        os.geteuid(),
                    )
            self.assertEqual(payload, source.read_bytes())
            self.assertFalse(destination.exists())

    def test_restore_transaction_persistence_retries_transient_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "restore-active"
            real_replace = os.replace
            calls = {"value": 0}

            def fail_once(source, destination):
                calls["value"] += 1
                if calls["value"] == 1:
                    raise OSError("transient rename failure")
                return real_replace(source, destination)

            with mock.patch.object(
                hysteria2_panel.os, "replace", side_effect=fail_once
            ):
                hysteria2_panel._atomic_write_json(
                    marker, {"version": 1, "phase": "queued"}
                )

            self.assertEqual(
                {"phase": "queued", "version": 1},
                json.loads(marker.read_text(encoding="utf-8")),
            )

    def test_queue_marker_is_durable_before_the_only_pending_archive_is_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = Database(root / "panel.db", b"r" * 32)
            database.initialize()
            certificate, private_key = create_test_certificate(root)
            certificate.chmod(0o640)
            private_key.chmod(0o640)
            manager = BackupManager(
                database=database,
                hmac_key=b"r" * 32,
                tls_cert=certificate,
                tls_key=private_key,
                public_host="vpn.example.test",
                hysteria_port=19999,
                work_dir=root / "work",
                maintenance_lock_path=root / "maintenance.lock",
                maintenance_lock_owner=os.geteuid(),
                maintenance_lock_mode=0o600,
                restore_marker_path=root / "restore-active",
            )
            (root / "maintenance.lock").touch(mode=0o600)
            archive = manager.create_archive()
            manager.stage_archive(
                io.BytesIO(archive.read_bytes()), archive.stat().st_size
            )
            marker = root / "restore-active"
            original_consume = manager._consume_captured_pending

            def crash_after_marker(metadata):
                self.assertTrue(marker.is_file())
                record = json.loads(marker.read_text(encoding="utf-8"))
                self.assertEqual("queued", record["phase"])
                self.assertTrue(Path(record["queuedArchive"]).is_file())
                raise RuntimeError("simulated power loss before pending cleanup")

            manager._consume_captured_pending = crash_after_marker
            with self.assertRaisesRegex(RuntimeError, "simulated power loss"):
                manager.queue_restore_transaction(
                    marker, root / "panel.env", root / "backups"
                )
            manager._consume_captured_pending = original_consume

            self.assertTrue(manager.pending_archive.is_file())
            self.assertEqual(
                hashlib.sha256(manager.pending_archive.read_bytes()).hexdigest(),
                json.loads(marker.read_text(encoding="utf-8"))["pendingSha256"],
            )

            record = hysteria2_panel._read_restore_transaction(
                marker, expected_uid=os.geteuid(), strict_paths=False
            )
            with mock.patch.object(
                hysteria2_panel,
                "_validate_current_restore_identity",
                return_value={
                    "panel.db": "1" * 64,
                    "server.crt": "2" * 64,
                    "server.key": "3" * 64,
                    "panel.env": "4" * 64,
                },
            ):
                hysteria2_panel._reconcile_restore_transaction(
                    record, marker, identity_uid=os.geteuid()
                )

            self.assertFalse(manager.pending_archive.exists())
            hysteria2_panel._remove_restore_marker(marker)
            manager.stage_archive(
                io.BytesIO(archive.read_bytes()), archive.stat().st_size
            )
            self.assertTrue(manager.pending_archive.is_file())

    def test_root_revalidation_failure_does_not_block_the_next_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = Database(root / "panel.db", b"r" * 32)
            database.initialize()
            certificate, private_key = create_test_certificate(root)
            manager = BackupManager(
                database=database,
                hmac_key=b"r" * 32,
                tls_cert=certificate,
                tls_key=private_key,
                public_host="vpn.example.test",
                hysteria_port=19999,
                work_dir=root / "work",
                maintenance_lock_path=root / "maintenance.lock",
                maintenance_lock_owner=os.geteuid(),
                maintenance_lock_mode=0o600,
                restore_marker_path=root / "restore-active",
            )
            (root / "maintenance.lock").touch(mode=0o600)
            archive = manager.create_archive()
            archive_bytes = archive.read_bytes()
            manager.stage_archive(io.BytesIO(archive_bytes), len(archive_bytes))

            with mock.patch.object(
                manager,
                "validate_archive",
                side_effect=BackupValidationError("root revalidation failed"),
            ):
                with self.assertRaisesRegex(
                    BackupValidationError, "root revalidation failed"
                ):
                    manager.queue_restore_transaction(
                        root / "restore-active", root / "panel.env", root / "backups"
                    )

            self.assertFalse(manager.pending_archive.exists())
            manager.stage_archive(io.BytesIO(archive_bytes), len(archive_bytes))
            self.assertTrue(manager.pending_archive.is_file())

    def test_queue_crash_recovery_writes_a_readable_disk_consistent_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "restore-active"
            queued_archive = Path(directory) / "restore-active.archive"
            (Path(directory) / "work").mkdir()
            queued_archive.write_bytes(b"valid captured archive")
            queued_archive.chmod(0o600)
            current_files = {
                "panel.db": "1" * 64,
                "server.crt": "2" * 64,
                "server.key": "3" * 64,
                "panel.env": "4" * 64,
            }
            record = {
                "version": hysteria2_panel.RESTORE_TRANSACTION_VERSION,
                "phase": "queued",
                "pendingArchive": str(Path(directory) / "pending-restore.zip"),
                "queuedArchive": str(queued_archive),
                "pendingSha256": hashlib.sha256(queued_archive.read_bytes()).hexdigest(),
                "pendingSize": queued_archive.stat().st_size,
                "databasePath": str(Path(directory) / "panel.db"),
                "tlsCert": str(Path(directory) / "server.crt"),
                "tlsKey": str(Path(directory) / "server.key"),
                "envFile": str(Path(directory) / "panel.env"),
                "workDir": str(Path(directory) / "work"),
                "backupRoot": str(Path(directory) / "backups"),
                "publicHost": "vpn.example.test",
                "hysteriaPort": 19999,
                "nodeName": "test-node",
            }
            marker.write_text(json.dumps(record), encoding="utf-8")
            marker.chmod(0o600)

            with mock.patch.object(
                hysteria2_panel,
                "_validate_current_restore_identity",
                return_value=current_files,
            ):
                hysteria2_panel._reconcile_restore_transaction(
                    record, marker, identity_uid=os.geteuid()
                )

            reread = hysteria2_panel._read_restore_transaction(
                marker, expected_uid=os.geteuid(), strict_paths=False
            )
            self.assertEqual("disk-consistent", reread["phase"])
            self.assertEqual("rolled-back", reread["outcome"])
            self.assertEqual(current_files, reread["oldFiles"])
            self.assertFalse(queued_archive.exists())

    def test_restore_defers_termination_until_all_identity_files_are_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = mock.Mock(
                database_path=Path(directory) / "panel.db",
                hmac_key=b"r" * 32,
                tls_cert=Path(directory) / "server.crt",
                tls_key=Path(directory) / "server.key",
                public_host="vpn.example.test",
                hysteria_port=19999,
                node_name="test-node",
            )
            applied = []
            manager = mock.Mock()

            def apply_archive(**_kwargs):
                os.kill(os.getpid(), hysteria2_panel.signal.SIGTERM)
                applied.append("database")
                applied.append("certificate")
                applied.append("private-key")
                applied.append("environment")
                return {"proxyUserCount": 1, "automaticBackup": "backup.zip"}

            manager.apply_pending_archive.side_effect = apply_archive
            systemd = mock.Mock(return_value=mock.Mock(returncode=0, stdout=""))
            applied_record = {"phase": "disk-consistent", "outcome": "applied"}
            with mock.patch.object(
                hysteria2_panel, "BackupManager", return_value=manager
            ), mock.patch.object(
                hysteria2_panel, "settle_restore_traffic"
            ), mock.patch.object(
                hysteria2_panel, "stop_restore_services"
            ), mock.patch.object(
                hysteria2_panel, "start_restore_services"
            ), mock.patch.object(
                hysteria2_panel,
                "_read_restore_transaction",
                side_effect=[None, applied_record],
            ), mock.patch.object(
                hysteria2_panel,
                "_reconcile_to_services_pending",
                return_value={"phase": "services-pending", "outcome": "applied"},
            ), mock.patch("builtins.print"):
                with self.assertRaises(SystemExit) as raised:
                    hysteria2_panel.restore_pending(
                        settings,
                        lock_path=Path(directory) / "maintenance.lock",
                        marker_path=Path(directory) / "restore-active",
                        runner=systemd,
                    )

            self.assertEqual(128 + hysteria2_panel.signal.SIGTERM, raised.exception.code)
            self.assertEqual(
                ["database", "certificate", "private-key", "environment"],
                applied,
            )

    def test_restore_requests_a_blocking_lock_before_stopping_services(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "maintenance.lock"
            settings = self.restore_settings(directory)
            events = []
            manager = mock.Mock()
            manager.apply_pending_archive.return_value = {
                "proxyUserCount": 1,
                "automaticBackup": "backup.zip",
            }
            applied_record = {"phase": "disk-consistent", "outcome": "applied"}

            @hysteria2_panel.contextlib.contextmanager
            def lock_context(path, blocking=False):
                events.append(("lock", path, blocking))
                yield

            @hysteria2_panel.contextlib.contextmanager
            def signal_context():
                events.append(("signals",))
                yield

            with mock.patch.object(
                hysteria2_panel,
                "exclusive_maintenance_lock",
                side_effect=lock_context,
            ) as maintenance_lock, mock.patch.object(
                hysteria2_panel,
                "defer_termination_signals",
                side_effect=signal_context,
            ), mock.patch.object(
                hysteria2_panel, "BackupManager", return_value=manager
            ), mock.patch.object(
                hysteria2_panel,
                "settle_restore_traffic",
                side_effect=lambda *_args, **_kwargs: events.append(("settle",)),
            ), mock.patch.object(
                hysteria2_panel, "stop_restore_services"
            ) as stop_services, mock.patch.object(
                hysteria2_panel, "start_restore_services"
            ), mock.patch.object(
                hysteria2_panel,
                "_read_restore_transaction",
                side_effect=[None, applied_record],
            ), mock.patch.object(
                hysteria2_panel,
                "_reconcile_to_services_pending",
                return_value={"phase": "services-pending", "outcome": "applied"},
            ), mock.patch("builtins.print"):
                hysteria2_panel.restore_pending(
                    settings,
                    lock_path=lock_path,
                    marker_path=Path(directory) / "restore-active",
                )

            maintenance_lock.assert_called_once_with(lock_path, blocking=True)
            self.assertEqual(
                [("lock", lock_path, True), ("signals",), ("settle",)],
                events[:3],
            )
            stop_services.assert_called_once_with(runner=subprocess.run)

    def test_restore_failure_leaves_recovery_marker_and_defers_service_start(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = mock.Mock(
                database_path=Path(directory) / "panel.db",
                hmac_key=b"r" * 32,
                tls_cert=Path(directory) / "server.crt",
                tls_key=Path(directory) / "server.key",
                public_host="vpn.example.test",
                hysteria_port=19999,
                node_name="test-node",
            )
            manager = mock.Mock()
            manager.apply_pending_archive.side_effect = RuntimeError("restore failed")
            marker = Path(directory) / "restore-active"
            with mock.patch.object(
                hysteria2_panel, "BackupManager", return_value=manager
            ), mock.patch.object(
                hysteria2_panel, "settle_restore_traffic"
            ), mock.patch.object(
                hysteria2_panel, "stop_restore_services"
            ) as stop_services, mock.patch.object(
                hysteria2_panel, "start_restore_services"
            ) as start_services:
                with self.assertRaisesRegex(RuntimeError, "restore failed"):
                    hysteria2_panel.restore_pending(
                        settings,
                        lock_path=Path(directory) / "maintenance.lock",
                        marker_path=marker,
                    )

            stop_services.assert_called_once_with(runner=subprocess.run)
            start_services.assert_not_called()
            manager.queue_restore_transaction.assert_called_once()

    def test_resume_accepts_normal_traffic_changes_after_files_are_preflight_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work_dir = root / "work"
            backup_root = root / "backups"
            work_dir.mkdir()
            backup_root.mkdir()
            database_path = root / "panel.db"
            hmac_key = b"r" * 32
            database = Database(database_path, hmac_key)
            database.initialize()
            database_path.chmod(0o600)
            user = database.create_proxy_user("alice")
            # This marker represents the post-stop, disk-consistent phase. Keep
            # the schema out of WAL so the fixture matches that production state.
            with sqlite3.connect(database_path) as connection:
                self.assertEqual(
                    (0, 0, 0),
                    tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()),
                )
            certificate, private_key = create_test_certificate(root)
            certificate.chmod(0o640)
            private_key.chmod(0o640)
            manager = BackupManager(
                database=database,
                hmac_key=hmac_key,
                tls_cert=certificate,
                tls_key=private_key,
                public_host="vpn.example.test",
                hysteria_port=19999,
                node_name="test-node",
                work_dir=work_dir,
            )
            env_file = root / "panel.env"
            env_file.write_text(
                "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN={}\n".format(
                    hmac_key.hex(),
                    manager._certificate_pin(certificate.read_bytes()),
                ),
                encoding="utf-8",
            )
            env_file.chmod(0o640)
            marker = root / "restore-active"
            record = {
                "version": hysteria2_panel.RESTORE_TRANSACTION_VERSION,
                "phase": "disk-consistent",
                "outcome": "rolled-back",
                "pendingArchive": str(work_dir / "pending-restore.zip"),
                "queuedArchive": str(root / "restore-active.archive"),
                "pendingSha256": "0" * 64,
                "pendingSize": 1,
                "databasePath": str(database_path),
                "tlsCert": str(certificate),
                "tlsKey": str(private_key),
                "envFile": str(env_file),
                "workDir": str(work_dir),
                "backupRoot": str(backup_root),
                "publicHost": "vpn.example.test",
                "hysteriaPort": 19999,
                "nodeName": "test-node",
            }
            record["oldFiles"] = hysteria2_panel._validate_current_restore_identity(
                record, root_uid=os.geteuid()
            )
            hysteria2_panel._atomic_write_json(marker, record)

            hysteria2_panel.recover_restore_files(
                lock_path=root / "maintenance.lock",
                marker_path=marker,
                expected_uid=os.geteuid(),
                strict_paths=False,
            )
            self.assertEqual(
                "services-pending",
                json.loads(marker.read_text(encoding="utf-8"))["phase"],
            )

            database.apply_traffic_batch(
                "f" * 32, {"alice": {"tx": 10, "rx": 20}}
            )
            self.assertEqual(
                (10, 20),
                tuple(
                    database.get_proxy_user(user["id"])[name]
                    for name in ("tx_bytes", "rx_bytes")
                ),
            )

            settings = self.restore_settings(directory)
            settings.hmac_key = hmac_key

            def runner(command, **_kwargs):
                self.assertEqual("show", command[1])
                return mock.Mock(
                    returncode=0,
                    stdout="LoadState=loaded\nActiveState=active\n",
                    stderr="",
                )

            hysteria2_panel.resume_after_restore(
                settings,
                lock_path=root / "maintenance.lock",
                marker_path=marker,
                runner=runner,
                expected_uid=os.geteuid(),
                strict_paths=False,
                health_probe=lambda *_args: None,
                stats_probe=lambda *_args: None,
                tcp_probe=lambda *_args: None,
                attempts=2,
                sleeper=lambda _seconds: None,
            )

            self.assertFalse(marker.exists())

    def test_restore_preflight_rejects_a_symlinked_current_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work_dir = root / "work"
            work_dir.mkdir()
            real_database_path = root / "real.db"
            hmac_key = b"r" * 32
            database = Database(real_database_path, hmac_key)
            database.initialize()
            real_database_path.chmod(0o600)
            database.create_proxy_user("alice")
            database_path = root / "panel.db"
            database_path.symlink_to(real_database_path)
            certificate, private_key = create_test_certificate(root)
            certificate.chmod(0o640)
            private_key.chmod(0o640)
            manager = BackupManager(
                database=database,
                hmac_key=hmac_key,
                tls_cert=certificate,
                tls_key=private_key,
                public_host="vpn.example.test",
                hysteria_port=19999,
                work_dir=work_dir,
            )
            env_file = root / "panel.env"
            env_file.write_text(
                "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN={}\n".format(
                    hmac_key.hex(),
                    manager._certificate_pin(certificate.read_bytes()),
                ),
                encoding="utf-8",
            )
            env_file.chmod(0o640)
            record = {
                "databasePath": str(database_path),
                "tlsCert": str(certificate),
                "tlsKey": str(private_key),
                "envFile": str(env_file),
                "workDir": str(work_dir),
                "publicHost": "vpn.example.test",
                "hysteriaPort": 19999,
                "nodeName": "test-node",
            }

            with self.assertRaisesRegex(RuntimeError, "unsafe restore file"):
                hysteria2_panel._validate_current_restore_identity(record)

    def test_restore_marker_creation_fsyncs_the_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "restore-active"
            synced_types = []
            real_fsync = os.fsync

            def record_fsync(descriptor):
                metadata = os.fstat(descriptor)
                synced_types.append(
                    "directory"
                    if hysteria2_panel.stat.S_ISDIR(metadata.st_mode)
                    else "file"
                )
                return real_fsync(descriptor)

            with mock.patch.object(
                hysteria2_panel.os, "fsync", side_effect=record_fsync
            ):
                hysteria2_panel._atomic_write_json(marker, {"phase": "queued"})

            self.assertEqual(["file", "directory"], synced_types)

    def test_restore_keeps_marker_when_loaded_secondary_service_is_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "restore-active"
            settings = mock.Mock(
                database_path=Path(directory) / "panel.db",
                hmac_key=b"r" * 32,
                tls_cert=Path(directory) / "server.crt",
                tls_key=Path(directory) / "server.key",
                public_host="vpn.example.test",
                hysteria_port=19999,
                node_name="test-node",
            )
            manager = mock.Mock()
            manager.apply_pending_archive.return_value = {
                "proxyUserCount": 1,
                "automaticBackup": "backup.zip",
            }
            states = {
                "hysteria2-panel-tcp-probe-443.service": ("loaded", "active"),
                "hysteria2-panel-server-443.service": ("loaded", "failed"),
                "hysteria2-panel-tcp-probe.service": ("loaded", "active"),
                "hysteria2-panel-server.service": ("loaded", "active"),
                "hysteria2-panel.service": ("loaded", "active"),
            }
            inspected = []

            def runner(command, **_kwargs):
                if command[1] == "start":
                    return mock.Mock(returncode=0, stdout="", stderr="")
                if command[1] == "show":
                    unit = command[-1]
                    inspected.append(unit)
                    load_state, active_state = states[unit]
                    return mock.Mock(
                        returncode=0,
                        stdout="LoadState={}\nActiveState={}\n".format(
                            load_state, active_state
                        ),
                        stderr="",
                    )
                self.fail("unexpected systemctl command: {}".format(command))

            record = {"phase": "services-pending", "outcome": "rolled-back"}
            marker.write_text("{}", encoding="utf-8")
            marker.chmod(0o600)
            with mock.patch.object(
                hysteria2_panel,
                "_read_restore_transaction",
                return_value=record,
            ), mock.patch.object(
                hysteria2_panel,
                "_reconcile_restore_transaction",
                return_value=record,
            ):
                with self.assertRaisesRegex(RuntimeError, "not healthy"):
                    hysteria2_panel.resume_after_restore(
                        settings,
                        lock_path=Path(directory) / "maintenance.lock",
                        marker_path=marker,
                        runner=runner,
                        health_probe=lambda *_args: None,
                        stats_probe=lambda *_args: None,
                        tcp_probe=lambda *_args: None,
                        attempts=2,
                        sleeper=lambda _seconds: None,
                        marker_reader=lambda *_args, **_kwargs: record,
                    )

            self.assertIn("hysteria2-panel-server-443.service", inspected)
            self.assertTrue(marker.is_file())

    def test_restore_service_start_allows_only_absent_optional_units(self):
        inspected = []
        required_units = {
            "hysteria2-panel.service",
            "hysteria2-panel-server.service",
            "hysteria2-panel-tcp-probe.service",
        }

        def runner(command, **_kwargs):
            if command[1] == "start":
                return mock.Mock(returncode=0, stdout="", stderr="")
            if command[1] == "show":
                unit = command[-1]
                inspected.append(unit)
                if unit in required_units:
                    load_state, active_state = "loaded", "active"
                else:
                    load_state, active_state = "not-found", "inactive"
                return mock.Mock(
                    returncode=0,
                    stdout="LoadState={}\nActiveState={}\n".format(
                        load_state, active_state
                    ),
                    stderr="",
                )
            self.fail("unexpected systemctl command: {}".format(command))

        settings = self.restore_settings(tempfile.gettempdir())
        settings.hysteria_port = 443
        health_checks = []
        stats_checks = []
        tcp_checks = []
        hysteria2_panel.start_restore_services(
            settings,
            runner=runner,
            health_probe=lambda url, _settings: health_checks.append(url),
            stats_probe=lambda url, secret: stats_checks.append((url, secret)),
            tcp_probe=lambda port: tcp_checks.append(port),
            attempts=1,
            sleeper=lambda _seconds: None,
        )

        self.assertEqual(list(hysteria2_panel.RESTORE_STOP_UNITS) * 2, inspected)
        self.assertEqual(
            [
                "http://127.0.0.1:19998/readyz",
                "http://127.0.0.1:19996/healthz",
                "http://127.0.0.1:19998/readyz",
                "http://127.0.0.1:19996/healthz",
            ],
            health_checks,
        )
        self.assertEqual(
            [
                ("http://127.0.0.1:19997", "stats-secret"),
                ("http://127.0.0.1:19997", "stats-secret"),
            ],
            stats_checks,
        )
        self.assertEqual([443, 443], tcp_checks)

    def test_restore_health_checks_loaded_secondary_stats_and_tcp_probe(self):
        def runner(command, **_kwargs):
            if command[1] == "start":
                return mock.Mock(returncode=0, stdout="", stderr="")
            if command[1] == "show":
                return mock.Mock(
                    returncode=0,
                    stdout="LoadState=loaded\nActiveState=active\n",
                    stderr="",
                )
            self.fail("unexpected systemctl command: {}".format(command))

        settings = self.restore_settings(tempfile.gettempdir())
        stats_checks = []
        tcp_checks = []
        hysteria2_panel.start_restore_services(
            settings,
            runner=runner,
            health_probe=lambda *_args: None,
            stats_probe=lambda url, secret: stats_checks.append((url, secret)),
            tcp_probe=lambda port: tcp_checks.append(port),
            attempts=2,
            sleeper=lambda _seconds: None,
        )

        self.assertEqual(
            [
                (settings.stats_url, settings.stats_secret),
                (settings.stats_443_url, settings.stats_secret),
            ]
            * 2,
            stats_checks,
        )
        self.assertEqual([settings.hysteria_port, 443] * 2, tcp_checks)

    def test_restore_health_probe_rejects_non_loopback_urls_before_network_io(self):
        settings = self.restore_settings(tempfile.gettempdir())
        with mock.patch(
            "hysteria2_panel.urllib.request.urlopen"
        ) as opener, self.assertRaises(RuntimeError):
            hysteria2_panel._default_restore_health_probe(
                "https://attacker.example/healthz", settings
            )
        opener.assert_not_called()

    def test_restore_health_rechecks_units_and_keeps_marker_after_transient_active(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "restore-active"
            marker.write_text("", encoding="utf-8")
            settings = self.restore_settings(directory)
            calls = 0

            def runner(command, **_kwargs):
                nonlocal calls
                if command[1] == "start":
                    return mock.Mock(returncode=0, stdout="", stderr="")
                unit = command[-1]
                if command[1] == "show":
                    calls += 1
                    active_state = (
                        "failed"
                        if unit == "hysteria2-panel-server.service"
                        and calls > len(hysteria2_panel.RESTORE_STOP_UNITS)
                        else "active"
                    )
                    return mock.Mock(
                        returncode=0,
                        stdout="LoadState=loaded\nActiveState={}\n".format(active_state),
                        stderr="",
                    )
                self.fail("unexpected command: {}".format(command))

            record = {"phase": "services-pending", "outcome": "rolled-back"}
            with mock.patch.object(
                hysteria2_panel,
                "_reconcile_restore_transaction",
                return_value=record,
            ):
                with self.assertRaisesRegex(RuntimeError, "healthy"):
                    hysteria2_panel.resume_after_restore(
                        settings,
                        lock_path=Path(directory) / "maintenance.lock",
                        marker_path=marker,
                        runner=runner,
                        health_probe=lambda *_args: None,
                        stats_probe=lambda *_args: None,
                        tcp_probe=lambda *_args: None,
                        attempts=2,
                        sleeper=lambda _seconds: None,
                        marker_reader=lambda *_args, **_kwargs: record,
                    )

            self.assertTrue(marker.is_file())

    def test_restore_stats_selection_fails_closed_on_secondary_transitions(self):
        settings = self.restore_settings(tempfile.gettempdir())

        for secondary_state in ("activating", "deactivating", "unknown"):
            with self.subTest(secondary_state=secondary_state):
                def runner(command, **_kwargs):
                    state = (
                        "active"
                        if command[-1] == "hysteria2-panel-server.service"
                        else secondary_state
                    )
                    return mock.Mock(
                        returncode=0,
                        stdout="LoadState=loaded\nActiveState={}\n".format(state),
                        stderr="",
                    )

                with mock.patch.object(
                    hysteria2_panel, "make_stats_client"
                ) as make_client, self.assertRaisesRegex(
                    RuntimeError, "state is invalid"
                ):
                    hysteria2_panel.make_restore_stats_client(
                        settings, runner=runner
                    )
                make_client.assert_not_called()

    def test_restore_stats_selection_requires_the_configured_endpoint_topology(self):
        settings = self.restore_settings(tempfile.gettempdir())

        def runner(command, **_kwargs):
            if command[-1] == "hysteria2-panel-server.service":
                load_state, active_state = "loaded", "active"
            else:
                load_state, active_state = "not-found", "inactive"
            return mock.Mock(
                returncode=0,
                stdout="LoadState={}\nActiveState={}\n".format(
                    load_state, active_state
                ),
                stderr="",
            )

        with self.assertRaisesRegex(RuntimeError, "secondary.*missing"):
            hysteria2_panel.make_restore_stats_client(settings, runner=runner)

        settings.hysteria_port = 443
        primary_client = mock.Mock()
        with mock.patch.object(
            hysteria2_panel, "make_stats_client", return_value=primary_client
        ) as make_client:
            self.assertIs(
                primary_client,
                hysteria2_panel.make_restore_stats_client(settings, runner=runner),
            )
        make_client.assert_called_once_with(settings, primary_only=True)

    def test_restore_settles_traffic_before_archive_apply_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.restore_settings(directory)
            database = Database(settings.database_path, settings.hmac_key)
            database.initialize()
            user = database.create_proxy_user("alice")
            stats = PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}})
            manager = mock.Mock()
            manager.apply_pending_archive.side_effect = RuntimeError("restore failed")
            marker = Path(directory) / "restore-active"
            stopped = []

            def runner(command, **_kwargs):
                action = command[1]
                unit = command[-1]
                if action == "kill":
                    stopped.append("panel")
                    return mock.Mock(returncode=0, stdout="", stderr="")
                if action == "show":
                    if unit == "hysteria2-panel.service":
                        state = "inactive" if stopped else "active"
                    elif unit == "hysteria2-panel-server.service":
                        state = (
                            "inactive"
                            if unit in stopped
                            else "active"
                        )
                    else:
                        state = "inactive"
                    load = "not-found" if state == "inactive" and unit not in {
                        "hysteria2-panel.service",
                        "hysteria2-panel-server.service",
                    } else "loaded"
                    return mock.Mock(
                        returncode=0,
                        stdout="LoadState={}\nActiveState={}\n".format(load, state),
                        stderr="",
                    )
                if action == "stop":
                    stopped.append(unit)
                    return mock.Mock(returncode=0, stdout="", stderr="")
                if action == "start":
                    return mock.Mock(returncode=0, stdout="", stderr="")
                self.fail("unexpected command: {}".format(command))

            with mock.patch.object(
                hysteria2_panel, "BackupManager", return_value=manager
            ), mock.patch.object(
                hysteria2_panel,
                "make_restore_stats_client",
                return_value=stats,
            ), mock.patch.object(
                hysteria2_panel, "start_restore_services"
            ):
                with self.assertRaisesRegex(RuntimeError, "restore failed"):
                    hysteria2_panel.restore_pending(
                        settings,
                        lock_path=Path(directory) / "maintenance.lock",
                        marker_path=marker,
                        runner=runner,
                        quiesce=lambda _client: None,
                    )

            record = database.get_proxy_user(user["id"])
            self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))
            manager.queue_restore_transaction.assert_called_once()
            manager.apply_pending_archive.assert_called_once()

    def test_sigterm_waits_for_inflight_traffic_collection_before_service_exit(self):
        class BlockingServer:
            def __init__(self):
                self.started = threading.Event()
                self.stopped = threading.Event()
                self.closed = False

            def serve_forever(self):
                self.started.set()
                self.stopped.wait(2)

            def shutdown(self):
                self.stopped.set()

            def server_close(self):
                self.closed = True

        class InflightUsage:
            def __init__(self):
                self.started = threading.Event()
                self.release = threading.Event()
                self.persisted = False
                self.final_collections = 0

            def run_collector(self, stop_event):
                self.started.set()
                self.release.wait(2)
                self.persisted = True
                stop_event.wait(2)

            def collect_once(self):
                self.final_collections += 1

        panel_server = BlockingServer()
        auth_server = BlockingServer()
        usage = InflightUsage()
        installed = {}
        handler_ready = threading.Event()

        def install_handler(signum, handler):
            installed[signum] = handler
            if signum == hysteria2_panel.signal.SIGTERM and callable(handler):
                handler_ready.set()
            return hysteria2_panel.signal.SIG_DFL

        def terminate_after_collection_starts():
            self.assertTrue(handler_ready.wait(1))
            self.assertTrue(usage.started.wait(1))
            installed[hysteria2_panel.signal.SIGTERM](
                hysteria2_panel.signal.SIGTERM, None
            )
            time.sleep(0.05)
            self.assertFalse(usage.persisted)
            usage.release.set()

        terminator = threading.Thread(target=terminate_after_collection_starts)
        terminator.start()
        with mock.patch.object(
            hysteria2_panel.signal, "signal", side_effect=install_handler
        ), mock.patch.object(
            hysteria2_panel.signal,
            "getsignal",
            return_value=hysteria2_panel.signal.SIG_DFL,
        ):
            hysteria2_panel.run_supervised_services(
                panel_server,
                auth_server,
                usage,
                panel_scheme="http",
            )
        terminator.join(2)

        self.assertFalse(terminator.is_alive())
        self.assertTrue(usage.persisted)
        self.assertEqual(1, usage.final_collections)
        self.assertTrue(panel_server.closed)
        self.assertTrue(auth_server.closed)

    def test_second_sigterm_during_final_collection_is_deferred_until_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            ready = Path(directory) / "collector-ready"
            final_started = Path(directory) / "final-started"
            persisted = Path(directory) / "persisted"
            script = textwrap.dedent(
                """
                import threading
                import time
                from pathlib import Path

                from hysteria2_panel import run_supervised_services

                ready = Path({ready!r})
                final_started = Path({final_started!r})
                persisted = Path({persisted!r})

                class Server:
                    def __init__(self):
                        self.stopped = threading.Event()

                    def serve_forever(self):
                        self.stopped.wait(5)

                    def shutdown(self):
                        self.stopped.set()

                    def server_close(self):
                        return

                class Usage:
                    def run_collector(self, stop_event):
                        ready.write_text("ready", encoding="utf-8")
                        stop_event.wait(5)

                    def collect_once(self):
                        final_started.write_text("started", encoding="utf-8")
                        time.sleep(0.5)
                        persisted.write_text("persisted", encoding="utf-8")

                run_supervised_services(Server(), Server(), Usage(), "http")
                """
            ).format(
                ready=str(ready),
                final_started=str(final_started),
                persisted=str(persisted),
            )
            project_root = str(Path(hysteria2_panel.__file__).resolve().parent)
            process = subprocess.Popen(
                [sys.executable, "-c", script],
                cwd=project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            def wait_for(path):
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if path.exists():
                        return True
                    if process.poll() is not None:
                        return False
                    time.sleep(0.01)
                return False

            stderr = ""
            try:
                self.assertTrue(wait_for(ready), "collector worker did not start")
                process.send_signal(hysteria2_panel.signal.SIGTERM)
                self.assertTrue(wait_for(final_started), "final collection did not start")
                process.send_signal(hysteria2_panel.signal.SIGTERM)
                _stdout, stderr = process.communicate(timeout=5)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)

            self.assertEqual(0, process.returncode, stderr)
            self.assertTrue(persisted.is_file())

    def test_server_close_waits_for_an_inflight_http_request(self):
        request_started = threading.Event()
        release_request = threading.Event()
        close_finished = threading.Event()

        class BlockingHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                request_started.set()
                release_request.wait(2)
                self.send_response(204)
                self.end_headers()

            def log_message(self, _format, *_args):
                return

        server = BoundedThreadingHTTPServer(
            ("127.0.0.1", 0), BlockingHandler, max_workers=1
        )
        serving = threading.Thread(target=server.serve_forever)
        serving.start()
        request = threading.Thread(
            target=lambda: urllib.request.urlopen(
                "http://127.0.0.1:{}/".format(server.server_address[1]),
                timeout=2,
            ).close()
        )
        request.start()
        self.assertTrue(request_started.wait(1))

        server.shutdown()
        closing = threading.Thread(
            target=lambda: (server.server_close(), close_finished.set())
        )
        closing.start()
        self.assertFalse(close_finished.wait(0.05))
        release_request.set()

        self.assertTrue(close_finished.wait(1))
        request.join(1)
        serving.join(1)
        closing.join(1)
        self.assertFalse(request.is_alive())
        self.assertFalse(serving.is_alive())
        self.assertFalse(closing.is_alive())

    def test_shutdown_interrupts_a_slow_request_before_waiting_for_threads(self):
        request_started = threading.Event()

        class SlowBodyHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                request_started.set()
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(204)
                self.end_headers()

            def log_message(self, _format, *_args):
                return

        server = BoundedThreadingHTTPServer(
            ("127.0.0.1", 0), SlowBodyHandler, max_workers=1, request_timeout=1
        )
        serving = threading.Thread(target=server.serve_forever)
        serving.start()
        client = socket.create_connection(server.server_address, timeout=1)
        client.sendall(
            b"POST / HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1000\r\n\r\nx"
        )
        self.assertTrue(request_started.wait(1))

        server.shutdown()
        server.shutdown_active_requests()
        closing = threading.Thread(target=server.server_close)
        closing.start()
        closing.join(1)

        client.close()
        serving.join(1)
        self.assertFalse(closing.is_alive())
        self.assertFalse(serving.is_alive())

    def test_request_deadline_evicts_a_slow_drip_client_and_frees_the_worker(self):
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(204)
                self.end_headers()

            def log_message(self, _format, *_args):
                return

        server = BoundedThreadingHTTPServer(
            ("127.0.0.1", 0), HealthHandler, max_workers=1, request_timeout=1
        )
        server.request_deadline = 1
        serving = threading.Thread(target=server.serve_forever)
        serving.start()
        slow_client = socket.create_connection(server.server_address, timeout=1)
        slow_client.sendall(b"G")
        stop_drip = threading.Event()

        def drip_bytes():
            while not stop_drip.wait(0.1):
                try:
                    slow_client.sendall(b"E")
                except OSError:
                    return

        dripping = threading.Thread(target=drip_bytes)
        dripping.start()
        try:
            time.sleep(1.2)
            with urllib.request.urlopen(
                "http://127.0.0.1:{}/healthz".format(server.server_address[1]),
                timeout=1,
            ) as response:
                self.assertEqual(204, response.status)
        finally:
            stop_drip.set()
            slow_client.close()
            dripping.join(1)
            server.shutdown()
            server.shutdown_active_requests()
            server.server_close()
            serving.join(1)

        self.assertFalse(dripping.is_alive())
        self.assertFalse(serving.is_alive())

    def test_tls_socket_registered_after_shutdown_is_closed_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            certificate, private_key = create_test_certificate(directory)
            wrapped_ready = threading.Event()
            release_wrapped_socket = threading.Event()
            close_finished = threading.Event()

            class IdleHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(204)
                    self.end_headers()

                def log_message(self, _format, *_args):
                    return

            real_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            real_context.load_cert_chain(str(certificate), str(private_key))

            class BarrierTlsContext:
                def wrap_socket(self, *args, **kwargs):
                    wrapped = real_context.wrap_socket(*args, **kwargs)
                    wrapped_ready.set()
                    release_wrapped_socket.wait(5)
                    return wrapped

            server = BoundedThreadingHTTPServer(
                ("127.0.0.1", 0),
                IdleHandler,
                max_workers=1,
                request_timeout=30,
            )
            server.tls_context = BarrierTlsContext()
            serving = threading.Thread(target=server.serve_forever)
            serving.start()
            client_context = ssl._create_unverified_context()
            client = client_context.wrap_socket(
                socket.create_connection(server.server_address, timeout=2),
                server_hostname="vpn.example.test",
            )
            closing = None
            try:
                self.assertTrue(wrapped_ready.wait(2))
                server.shutdown()
                server.shutdown_active_requests()
                closing = threading.Thread(
                    target=lambda: (server.server_close(), close_finished.set())
                )
                closing.start()
                self.assertFalse(close_finished.wait(0.05))

                release_wrapped_socket.set()

                self.assertTrue(close_finished.wait(1))
            finally:
                release_wrapped_socket.set()
                client.close()
                if closing is None:
                    server.server_close()
                else:
                    closing.join(2)
                serving.join(2)

            self.assertFalse(serving.is_alive())
            self.assertFalse(closing.is_alive())

    def test_partial_worker_start_failure_does_not_shutdown_an_unstarted_server(self):
        class FakeServer:
            def __init__(self):
                self.stopped = threading.Event()
                self.shutdown_calls = 0

            def serve_forever(self):
                self.stopped.wait(1)

            def shutdown(self):
                self.shutdown_calls += 1
                self.stopped.set()

            def server_close(self):
                return

        panel_server = FakeServer()
        auth_server = FakeServer()
        usage = mock.Mock()
        real_start = threading.Thread.start
        starts = 0

        def fail_second_start(thread):
            nonlocal starts
            starts += 1
            if starts == 2:
                raise RuntimeError("thread unavailable")
            return real_start(thread)

        with mock.patch.object(threading.Thread, "start", new=fail_second_start):
            with self.assertRaisesRegex(RuntimeError, "thread unavailable"):
                hysteria2_panel.run_supervised_services(
                    panel_server,
                    auth_server,
                    usage,
                    panel_scheme="http",
                )

        self.assertEqual(1, panel_server.shutdown_calls)
        self.assertEqual(0, auth_server.shutdown_calls)

    def test_worker_exit_fails_the_process_and_closes_every_local_service(self):
        class FakeServer:
            def __init__(self, exits=False):
                self.exits = exits
                self.stopped = threading.Event()
                self.closed = False

            def serve_forever(self):
                if self.exits:
                    return
                self.stopped.wait(2)

            def shutdown(self):
                self.stopped.set()

            def server_close(self):
                self.closed = True

        class FakeUsageManager:
            def __init__(self):
                self.stopped = threading.Event()

            def run_collector(self, stop_event):
                stop_event.wait(2)
                self.stopped.set()

            def collect_once(self):
                raise RuntimeError("final traffic sync unavailable")

        panel_server = FakeServer(exits=True)
        auth_server = FakeServer()
        usage_manager = FakeUsageManager()

        with self.assertRaisesRegex(RuntimeError, "panel-http"):
            run_supervised_services(
                panel_server,
                auth_server,
                usage_manager,
                panel_scheme="http",
            )

        self.assertTrue(panel_server.closed)
        self.assertTrue(auth_server.closed)
        self.assertTrue(usage_manager.stopped.wait(1))

    def test_worker_exit_final_collection_persists_real_usage(self):
        class Server:
            def __init__(self, exits=False):
                self.exits = exits
                self.stopped = threading.Event()

            def serve_forever(self):
                if self.exits:
                    return
                self.stopped.wait(2)

            def shutdown(self):
                self.stopped.set()

            def server_close(self):
                return

        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "panel.db", b"w" * 32)
            database.initialize()
            user = database.create_proxy_user("alice")
            usage = UsageManager(
                database,
                PolicyStatsClient(traffic={"alice": {"tx": 10, "rx": 20}}),
            )

            with self.assertRaisesRegex(RuntimeError, "panel-http"):
                run_supervised_services(
                    Server(exits=True),
                    Server(),
                    usage,
                    panel_scheme="http",
                )

            record = database.get_proxy_user(user["id"])
            self.assertEqual((10, 20), (record["tx_bytes"], record["rx_bytes"]))

    def test_service_controller_uses_only_fixed_systemctl_commands(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return type("Result", (), {"returncode": 0, "stdout": "active\n", "stderr": ""})()

        controller = ServiceController(runner=runner)
        self.assertEqual("active", controller.status())
        self.assertEqual("active", controller.action("restart"))
        with self.assertRaises(ValueError):
            controller.action("restart;id")
        self.assertEqual(
            [
                ["/bin/systemctl", "is-active", "hysteria2-panel-server.service"],
                ["/usr/bin/sudo", "-n", "/bin/systemctl", "restart", "hysteria2-panel-server.service"],
                ["/bin/systemctl", "is-active", "hysteria2-panel-server.service"],
            ],
            [command for command, _ in calls],
        )
        self.assertTrue(all("shell" not in kwargs for _, kwargs in calls))

    def test_restore_controller_can_only_start_the_fixed_restore_unit(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return type("Result", (), {"returncode": 0, "stdout": ""})()

        RestoreController(runner=runner).queue()

        self.assertEqual(
            [
                "/usr/bin/sudo",
                "-n",
                "/bin/systemctl",
                "--no-block",
                "start",
                "hysteria2-panel-restore.service",
            ],
            calls[0][0],
        )
        self.assertNotIn("shell", calls[0][1])

    def test_update_controller_persists_target_and_reports_the_real_unit_state(self):
        calls = []
        unit_active = [True]

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            if command[1] == "show":
                return type(
                    "Result",
                    (),
                    {
                        "returncode": 0,
                        "stdout": (
                            "ActiveState={}\nSubState={}\n".format(
                                "active" if unit_active[0] else "inactive",
                                "running" if unit_active[0] else "dead",
                            )
                            + "Result=success\nExecMainStatus=0\n"
                        ),
                        "stderr": "",
                    },
                )()
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / "update-status.json"
            controller = UpdateController(
                runner=runner,
                status_path=status_path,
                current_version="0.13.0",
                clock=lambda: 1000,
            )
            controller.queue("v0.14.0")
            status = controller.status()
            with self.assertRaises(ValueError):
                controller.queue("v0.15.0;reboot")
            restarted_controller = UpdateController(
                runner=runner,
                status_path=status_path,
                current_version="0.14.0",
                clock=lambda: 1001,
            )
            still_installing = restarted_controller.status()
            unit_active[0] = False
            completed = restarted_controller.status()

        self.assertEqual(
            [
                "/usr/bin/sudo",
                "-n",
                "/bin/systemctl",
                "--no-block",
                "start",
                "hysteria2-panel-update.service",
            ],
            calls[0][0],
        )
        self.assertEqual(
            [
                "/bin/systemctl",
                "show",
                "hysteria2-panel-update.service",
                "--property=ActiveState",
                "--property=SubState",
                "--property=Result",
                "--property=ExecMainStatus",
                "--no-pager",
            ],
            calls[1][0],
        )
        self.assertEqual("running", status["state"])
        self.assertEqual("v0.14.0", status["target"])
        self.assertEqual("running", still_installing["state"])
        self.assertEqual("success", completed["state"])
        self.assertTrue(all("shell" not in kwargs for _, kwargs in calls))

    def test_update_controller_records_queue_failure_and_stale_success(self):
        def failed_start(command, **_kwargs):
            return type(
                "Result", (), {"returncode": 1, "stdout": "", "stderr": "denied"}
            )()

        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / "update-status.json"
            controller = UpdateController(
                runner=failed_start,
                status_path=status_path,
                current_version="0.13.0",
                clock=lambda: 1000,
            )
            with self.assertRaises(RuntimeError):
                controller.queue("v0.14.0")
            self.assertEqual("failed", controller.status()["state"])

        def inactive_unit(_command, **_kwargs):
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": (
                        "ActiveState=inactive\nSubState=dead\n"
                        "Result=success\nExecMainStatus=0\n"
                    ),
                    "stderr": "",
                },
            )()

        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / "update-status.json"
            controller = UpdateController(
                runner=inactive_unit,
                status_path=status_path,
                current_version="0.13.0",
                clock=lambda: 1000,
            )
            controller.queue("v0.14.0")
            controller.clock = lambda: 1031
            status = controller.status()
            self.assertEqual("failed", status["state"])
            self.assertIn("版本未改变", status["message"])

    def test_reboot_controller_uses_only_the_fixed_nonblocking_command(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        RebootController(runner=runner).queue()

        self.assertEqual(
            ["/usr/bin/sudo", "-n", "/bin/systemctl", "--no-block", "reboot"],
            calls[0][0],
        )
        self.assertNotIn("shell", calls[0][1])

    def test_update_checker_uses_the_fixed_repository_and_compares_versions(self):
        requests = []

        class Response(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        def opener(request, timeout):
            requests.append((request.full_url, timeout, request.headers))
            return Response(json.dumps({"tag_name": "v0.4.0"}).encode())

        result = UpdateChecker("0.3.0", opener=opener).check()
        self.assertEqual("v0.4.0", result["latest"])
        self.assertTrue(result["update_available"])
        self.assertEqual(
            "https://api.github.com/repos/Elegying/Hysteria2-panel/releases/latest",
            requests[0][0],
        )
        self.assertEqual(3, requests[0][1])

    def test_update_installer_downloads_only_the_fixed_release_and_runs_noninteractively(self):
        requests = []
        calls = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        def opener(request, timeout):
            requests.append((request.full_url, timeout))
            if request.full_url.endswith("/releases/latest"):
                return Response(json.dumps({"tag_name": "v0.12.0"}).encode())
            if request.full_url.endswith("/install.sh.sigstore.json"):
                return Response(b'{"mediaType":"application/vnd.dev.sigstore.bundle.v0.3+json"}')
            return Response(b'#!/usr/bin/env bash\nPANEL_VERSION="0.12.0"\n')

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return type("Result", (), {"returncode": 0})()

        result = UpdateInstaller(
            current_version="0.11.2", opener=opener, runner=runner
        ).apply()

        self.assertEqual(
            [
                "https://api.github.com/repos/Elegying/Hysteria2-panel/releases/latest",
                "https://raw.githubusercontent.com/Elegying/Hysteria2-panel/v0.12.0/install.sh",
                "https://github.com/Elegying/Hysteria2-panel/releases/download/v0.12.0/install.sh.sigstore.json",
            ],
            [url for url, _ in requests],
        )
        self.assertEqual(
            ["/opt/hysteria2-panel/bin/cosign", "verify-blob"],
            calls[0][0][:2],
        )
        self.assertIn(
            "https://github.com/Elegying/Hysteria2-panel/.github/workflows/release-signature.yml@refs/tags/v0.12.0",
            calls[0][0],
        )
        self.assertIn("https://token.actions.githubusercontent.com", calls[0][0])
        self.assertEqual(60, calls[0][1]["timeout"])
        self.assertEqual(["/bin/bash", "-n"], calls[1][0][:2])
        self.assertEqual(["/bin/bash"], calls[2][0][:1])
        self.assertNotIn("shell", calls[0][1])
        self.assertNotIn("shell", calls[1][1])
        self.assertNotIn("shell", calls[2][1])
        self.assertEqual("1", calls[2][1]["env"]["HY2PANEL_AUTO_UPDATE"])
        self.assertEqual("v0.12.0", calls[2][1]["env"]["PANEL_REF"])
        self.assertNotIn("timeout", calls[2][1])
        self.assertNotIn("ADMIN_PASSWORD", calls[2][1]["env"])
        self.assertEqual(
            {"current": "v0.11.2", "latest": "v0.12.0", "updated": True},
            result,
        )

    def test_update_installer_rejects_an_invalid_signature_before_bash(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        responses = iter(
            [
                Response(json.dumps({"tag_name": "v0.12.0"}).encode()),
                Response(b'#!/usr/bin/env bash\nPANEL_VERSION="0.12.0"\n'),
                Response(b"invalid-signature-bundle"),
            ]
        )
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})()

        with self.assertRaisesRegex(ValueError, "signature"):
            UpdateInstaller(
                current_version="0.11.2",
                opener=lambda *_args, **_kwargs: next(responses),
                runner=runner,
            ).apply()

        self.assertEqual("/opt/hysteria2-panel/bin/cosign", calls[0][0])
        self.assertFalse(any(command[0] == "/bin/bash" for command in calls))

    def test_update_installer_rejects_mismatched_installer_version(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        responses = iter(
            [
                Response(json.dumps({"tag_name": "v0.12.0"}).encode()),
                Response(b'#!/usr/bin/env bash\nPANEL_VERSION="9.9.9"\n'),
            ]
        )
        with self.assertRaises(ValueError):
            UpdateInstaller(
                current_version="0.11.2",
                opener=lambda *_args, **_kwargs: next(responses),
                runner=mock.Mock(),
            ).apply()

    def test_update_installer_rejects_non_semver_tags_before_downloading_code(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        runner = mock.Mock()
        with self.assertRaises(ValueError):
            UpdateInstaller(
                current_version="0.11.2",
                opener=lambda *_args, **_kwargs: Response(
                    json.dumps({"tag_name": "v0.12.0/../../main"}).encode()
                ),
                runner=runner,
            ).apply()
        runner.assert_not_called()

    def test_update_installer_rejects_prerelease_metadata_before_downloading_code(self):
        requests = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        def opener(request, timeout):
            self.assertEqual(3, timeout)
            requests.append(request.full_url)
            return Response(
                json.dumps(
                    {"tag_name": "v0.12.0", "draft": False, "prerelease": True}
                ).encode()
            )

        with self.assertRaises(ValueError):
            UpdateInstaller(
                current_version="0.11.2", opener=opener, runner=mock.Mock()
            ).apply()
        self.assertEqual(1, len(requests))

    def test_update_installer_does_not_execute_when_already_current(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        runner = mock.Mock()
        result = UpdateInstaller(
            current_version="0.12.0",
            opener=lambda *_args, **_kwargs: Response(
                json.dumps({"tag_name": "v0.12.0"}).encode()
            ),
            runner=runner,
        ).apply()

        self.assertEqual(
            {"current": "v0.12.0", "latest": "v0.12.0", "updated": False},
            result,
        )
        runner.assert_not_called()

    def test_system_metrics_reports_cpu_memory_disk_and_uptime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            proc_root = Path(temp_dir)
            (proc_root / "stat").write_text("cpu  100 0 100 800 0 0 0 0\n")
            (proc_root / "meminfo").write_text(
                "MemTotal: 1000 kB\nMemAvailable: 600 kB\n"
            )
            (proc_root / "uptime").write_text("90061.0 0.0\n")
            (proc_root / "sys/net/ipv4").mkdir(parents=True)
            (proc_root / "sys/net/ipv4/tcp_congestion_control").write_text("bbr\n")
            (proc_root / "sys/net/core").mkdir(parents=True)
            (proc_root / "sys/net/core/default_qdisc").write_text("fq\n")
            disk = type("Disk", (), {"total": 1000, "used": 250, "free": 750})()
            metrics = SystemMetrics(
                proc_root=proc_root,
                disk_usage=lambda _: disk,
                cpu_count=lambda: 1,
                loadavg=lambda: (0.5, 0.0, 0.0),
            )

            first = metrics.snapshot()
            (proc_root / "stat").write_text("cpu  150 0 150 900 0 0 0 0\n")
            second = metrics.snapshot()

        self.assertEqual(50.0, first["cpu_percent"])
        self.assertEqual(50.0, second["cpu_percent"])
        self.assertEqual(40.0, second["memory_percent"])
        self.assertEqual(25.0, second["disk_percent"])
        self.assertEqual("1天 1小时", second["uptime"])
        self.assertEqual("bbr", second["tcp_congestion_control"])
        self.assertEqual("fq", second["default_qdisc"])


class FakeServiceController:
    def __init__(self):
        self.actions = []
        self.state = "active"

    def status(self):
        return self.state

    def action(self, action):
        self.actions.append(action)
        self.state = "active" if action in {"start", "restart"} else "inactive"
        return self.state


class FakeEgressPolicyController:
    def __init__(self):
        self.actions = []
        self.state = "web"

    def status(self):
        return self.state

    def switch(self, policy):
        self.actions.append(policy)
        self.state = policy
        return self.state


class FakeRestoreController:
    def __init__(self):
        self.queued = 0

    def queue(self):
        self.queued += 1


class FakeUpdateController:
    def __init__(self):
        self.queued = 0
        self.target = None

    def queue(self, target):
        self.queued += 1
        self.target = target

    def status(self):
        return {
            "state": "queued" if self.queued else "idle",
            "target": self.target,
            "current": "v0.13.0",
            "message": "更新任务已排队" if self.queued else "尚未启动更新",
        }


class FakeRebootController:
    def __init__(self):
        self.queued = 0

    def queue(self):
        self.queued += 1

class FakeSystemMetrics:
    def snapshot(self):
        return {
            "cpu_percent": 12.5,
            "memory_percent": 40.0,
            "memory_used": 400,
            "memory_total": 1000,
            "disk_percent": 25.0,
            "disk_used": 250,
            "disk_total": 1000,
            "uptime": "1天 1小时",
            "tcp_congestion_control": "bbr",
            "default_qdisc": "fq",
        }


class FakeUpdateChecker:
    def check(self):
        return {
            "current": "v0.3.0",
            "latest": "v0.4.0",
            "update_available": True,
            "url": "https://github.com/Elegying/Hysteria2-panel/releases/latest",
        }


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


class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.hmac_key = b"m" * 32
        self.database = Database(self.root / "source.db", self.hmac_key)
        self.database.initialize()
        source_admin = self.database.upsert_admin("source-admin", "source-password")
        self.database.create_session(source_admin)
        self.database.audit("source-admin", "test", "alice", "127.0.0.1")
        self.user = self.database.create_proxy_user("alice")
        self.database.add_traffic({"alice": {"tx": 123, "rx": 456}})
        self.certificate, self.private_key = create_test_certificate(self.root)
        self.manager = BackupManager(
            database=self.database,
            hmac_key=self.hmac_key,
            tls_cert=self.certificate,
            tls_key=self.private_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            node_name="私家车-2026",
            work_dir=self.root / "work",
            maintenance_lock_path=self.root / "maintenance.lock",
            maintenance_lock_owner=os.geteuid(),
            maintenance_lock_mode=0o600,
            restore_marker_path=self.root / "restore-active",
        )
        (self.root / "maintenance.lock").touch(mode=0o600)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_backup_contains_migratable_state_and_validates_credentials(self):
        archive = self.manager.create_archive()

        with zipfile.ZipFile(archive) as package:
            self.assertEqual(
                {
                    "manifest.json",
                    "data/panel.db",
                    "secrets/hmac-key.hex",
                    "tls/server.crt",
                    "tls/server.key",
                },
                set(package.namelist()),
            )
            manifest = json.loads(package.read("manifest.json"))
            packaged_database = self.root / "packaged.db"
            packaged_database.write_bytes(package.read("data/panel.db"))

        self.assertEqual(1, manifest["formatVersion"])
        self.assertEqual("vpn.example.test", manifest["source"]["publicHost"])
        self.assertEqual(19999, manifest["source"]["hysteriaPort"])
        self.assertEqual("私家车-2026", manifest["source"]["nodeName"])
        self.assertEqual(1, manifest["proxyUserCount"])
        with sqlite3.connect(packaged_database) as connection:
            for table in ("admins", "sessions", "audit_log"):
                self.assertEqual(
                    0,
                    connection.execute("SELECT COUNT(*) FROM {}".format(table)).fetchone()[0],
                    table,
                )
        inspected = self.manager.validate_archive(archive)
        self.assertEqual(manifest["certificate"]["pinSHA256"], inspected["certificate"]["pinSHA256"])

    def test_archive_limit_can_hold_the_largest_valid_uncompressed_backup(self):
        self.assertGreaterEqual(
            hysteria2_panel.MAX_BACKUP_ARCHIVE_BYTES,
            hysteria2_panel.MAX_BACKUP_CONTENT_BYTES + 3 * 1024**2,
        )

    def test_restore_rejects_non_blob_proxy_token_seeds_as_validation_errors(self):
        invalid_database = self.root / "invalid-seed.db"
        with sqlite3.connect(self.database.path) as source, sqlite3.connect(
            invalid_database
        ) as destination:
            source.backup(destination)
            destination.execute("PRAGMA journal_mode = DELETE")
            destination.execute(
                "UPDATE proxy_users SET token_seed = 'not-a-blob' WHERE name = 'alice'"
            )

        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            with self.assertRaisesRegex(BackupValidationError, "用户数据库"):
                self.manager._validate_database(
                    invalid_database.read_bytes(), self.hmac_key, directory
                )

    def test_restore_replacement_fsyncs_owner_and_mode_before_rename(self):
        destination = self.root / "replace-me"
        destination.write_bytes(b"old")
        destination.chmod(0o640)
        events = []
        real_fchown = os.fchown
        real_fchmod = os.fchmod
        real_fsync = os.fsync
        real_replace = os.replace

        def track_fchown(descriptor, uid, gid):
            events.append("fchown")
            return real_fchown(descriptor, uid, gid)

        def track_fchmod(descriptor, mode):
            events.append("fchmod")
            return real_fchmod(descriptor, mode)

        def track_fsync(descriptor):
            events.append("fsync")
            return real_fsync(descriptor)

        def track_replace(source, target):
            events.append("replace")
            return real_replace(source, target)

        with mock.patch.object(
            hysteria2_panel.os, "fchown", side_effect=track_fchown
        ), mock.patch.object(
            hysteria2_panel.os, "fchmod", side_effect=track_fchmod
        ), mock.patch.object(
            hysteria2_panel.os, "fsync", side_effect=track_fsync
        ), mock.patch.object(
            hysteria2_panel.os, "replace", side_effect=track_replace
        ):
            self.manager._replace_bytes(destination, b"new")

        self.assertEqual(b"new", destination.read_bytes())
        self.assertEqual(0o640, destination.stat().st_mode & 0o777)
        self.assertLess(events.index("fchown"), events.index("fchmod"))
        self.assertLess(events.index("fchmod"), events.index("fsync"))
        self.assertLess(events.index("fsync"), events.index("replace"))

    def test_restore_migrates_backups_created_before_udp_443_support(self):
        current_archive = self.manager.create_archive()
        with zipfile.ZipFile(current_archive) as package:
            payloads = {name: package.read(name) for name in package.namelist()}
        legacy_database = self.root / "legacy-backup.db"
        legacy_database.write_bytes(payloads["data/panel.db"])
        legacy_columns = ",".join(BackupManager.REQUIRED_PROXY_COLUMNS)
        with sqlite3.connect(legacy_database) as connection:
            connection.execute(
                "CREATE TABLE proxy_users_legacy AS SELECT {} FROM proxy_users".format(
                    legacy_columns
                )
            )
            connection.execute("DROP TABLE proxy_users")
            connection.execute("ALTER TABLE proxy_users_legacy RENAME TO proxy_users")
        payloads["data/panel.db"] = legacy_database.read_bytes()
        manifest = json.loads(payloads["manifest.json"])
        manifest["files"]["data/panel.db"] = {
            "sha256": hashlib.sha256(payloads["data/panel.db"]).hexdigest(),
            "size": len(payloads["data/panel.db"]),
        }
        payloads["manifest.json"] = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        legacy_archive = self.root / "legacy-backup.zip"
        with zipfile.ZipFile(legacy_archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for name, value in payloads.items():
                package.writestr(name, value)

        destination_root = self.root / "legacy-destination"
        destination_root.mkdir()
        destination_hmac = b"d" * 32
        destination_database = Database(destination_root / "panel.db", destination_hmac)
        destination_database.initialize()
        destination_certificate, destination_key = create_test_certificate(
            destination_root, "vpn.example.test"
        )
        env_file = destination_root / "panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=destination-pin\n".format(
                destination_hmac.hex()
            )
        )
        destination = BackupManager(
            database=destination_database,
            hmac_key=destination_hmac,
            tls_cert=destination_certificate,
            tls_key=destination_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            work_dir=destination_root / "work",
        )

        destination.apply_archive(
            legacy_archive,
            env_file=env_file,
            backup_root=destination_root / "automatic-backups",
        )

        restored = Database(destination_database.path, self.hmac_key)
        record = restored.get_proxy_user(self.user["id"])
        self.assertFalse(record["allow_udp_443"])
        self.assertIsNone(
            restored.authenticate_token(self.user["token"], require_udp_443=True)
        )

    def test_restore_rejects_path_traversal_and_mismatched_endpoint(self):
        malicious = self.root / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as package:
            package.writestr("../panel.db", b"not allowed")

        with self.assertRaises(BackupValidationError):
            self.manager.validate_archive(malicious)

        archive = self.manager.create_archive()
        other_endpoint = BackupManager(
            database=self.database,
            hmac_key=self.hmac_key,
            tls_cert=self.certificate,
            tls_key=self.private_key,
            public_host="other.example.test",
            hysteria_port=19999,
            work_dir=self.root / "other-work",
        )
        with self.assertRaisesRegex(BackupValidationError, "域名"):
            other_endpoint.validate_archive(archive, require_compatible_endpoint=True)

    def test_only_one_restore_archive_can_be_staged_at_a_time(self):
        archive_bytes = self.manager.create_archive().read_bytes()

        self.manager.stage_archive(io.BytesIO(archive_bytes), len(archive_bytes))
        original_digest = hashlib.sha256(self.manager.pending_archive.read_bytes()).digest()

        with self.assertRaisesRegex(BackupValidationError, "已有恢复任务"):
            self.manager.stage_archive(io.BytesIO(archive_bytes), len(archive_bytes))
        self.assertEqual(
            original_digest,
            hashlib.sha256(self.manager.pending_archive.read_bytes()).digest(),
        )

    def test_restore_upload_is_rejected_while_installer_holds_maintenance_lock(self):
        archive = self.manager.create_archive()
        archive_bytes = archive.read_bytes()

        with hysteria2_panel.exclusive_maintenance_lock(
            self.root / "maintenance.lock"
        ):
            with self.assertRaisesRegex(BackupValidationError, "维护任务"):
                self.manager.stage_archive(
                    io.BytesIO(archive_bytes), len(archive_bytes)
                )

        self.assertFalse(self.manager.pending_archive.exists())

    def test_restore_upload_is_rejected_until_the_previous_health_marker_is_cleared(self):
        archive = self.manager.create_archive()
        archive_bytes = archive.read_bytes()
        self.manager.restore_marker_path.write_text(
            json.dumps({"phase": "services-pending"}), encoding="utf-8"
        )
        self.manager.restore_marker_path.chmod(0o600)

        with self.assertRaisesRegex(BackupValidationError, "健康检查"):
            self.manager.stage_archive(
                io.BytesIO(archive_bytes), len(archive_bytes)
            )

        self.assertFalse(self.manager.pending_archive.exists())

        self.manager.restore_marker_path.unlink()
        self.manager.restore_marker_path.symlink_to(self.root / "missing-marker-target")
        with self.assertRaisesRegex(BackupValidationError, "健康检查"):
            self.manager.stage_archive(
                io.BytesIO(archive_bytes), len(archive_bytes)
            )
        self.assertFalse(self.manager.pending_archive.exists())

    def test_failed_pending_restore_is_quarantined_and_does_not_block_retry(self):
        payload = b"failed restore archive"
        self.manager.work_dir.mkdir(parents=True, mode=0o700)
        self.manager.pending_archive.write_bytes(payload)
        self.manager.pending_archive.chmod(0o600)
        self.manager.apply_archive = mock.Mock(side_effect=RuntimeError("simulated failure"))

        with self.assertRaisesRegex(RuntimeError, "simulated failure"):
            self.manager.apply_pending_archive(
                env_file=self.root / "panel.env",
                backup_root=self.root / "automatic-backups",
            )

        self.assertFalse(self.manager.pending_archive.exists())
        quarantined = list(self.manager.work_dir.glob("failed-restore-*.zip"))
        self.assertEqual(1, len(quarantined))
        self.assertEqual(payload, quarantined[0].read_bytes())
        self.assertEqual(0o600, quarantined[0].stat().st_mode & 0o777)

    def test_restore_preserves_destination_admin_and_restores_old_node_credentials(self):
        archive = self.manager.create_archive()
        destination_root = self.root / "destination"
        destination_root.mkdir()
        destination_hmac = b"d" * 32
        destination_db = Database(destination_root / "panel.db", destination_hmac)
        destination_db.initialize()
        destination_admin = destination_db.upsert_admin("destination-admin", "destination-password")
        destination_db.create_proxy_user("will-be-replaced")
        destination_db.create_session(destination_admin)
        destination_cert, destination_key = create_test_certificate(
            destination_root, "vpn.example.test"
        )
        env_file = destination_root / "panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=old\nHY2PANEL_PUBLIC_HOST=vpn.example.test\nHY2PANEL_HYSTERIA_PORT=19999\n".format(
                destination_hmac.hex()
            )
        )
        destination = BackupManager(
            database=destination_db,
            hmac_key=destination_hmac,
            tls_cert=destination_cert,
            tls_key=destination_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            work_dir=destination_root / "work",
        )

        result = destination.apply_archive(
            archive,
            env_file=env_file,
            backup_root=destination_root / "automatic-backups",
        )

        restored = Database(destination_db.path, self.hmac_key)
        self.assertEqual(destination_admin, restored.verify_admin("destination-admin", "destination-password"))
        self.assertIsNone(restored.verify_admin("source-admin", "source-password"))
        self.assertEqual("alice", restored.authenticate_token(self.user["token"]))
        self.assertEqual(["alice"], [row["name"] for row in restored.list_proxy_users()["users"]])
        with sqlite3.connect(destination_db.path) as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
        self.assertEqual(self.certificate.read_bytes(), destination_cert.read_bytes())
        self.assertEqual(self.private_key.read_bytes(), destination_key.read_bytes())
        self.assertIn("HY2PANEL_HMAC_KEY={}".format(self.hmac_key.hex()), env_file.read_text())
        self.assertIn("HY2PANEL_CERT_PIN={}".format(result["certificate"]["pinSHA256"]), env_file.read_text())
        self.assertTrue((Path(result["automaticBackup"]) / "panel.db").is_file())

    def test_restore_preserves_every_issued_link_identity_across_server_replacement(self):
        created_second = self.database.create_proxy_user(
            "bob", device_limit=7, traffic_limit_bytes=900 * 1024**3
        )
        second_token = created_second["token"]
        second_current = self.database.get_proxy_user(created_second["id"])
        self.database.update_proxy_user_limits(
            created_second["id"],
            device_limit=7,
            traffic_limit_bytes=900 * 1024**3,
            allow_udp_443=True,
            expected_generation=second_current["generation"],
        )
        legacy = self.database.create_proxy_user("legacy", token="legacy-issued-token")
        self.database.add_traffic({"bob": {"tx": 789, "rx": 987}})
        issued_tokens = {
            "alice": self.user["token"],
            "bob": second_token,
            "legacy": legacy["token"],
        }
        source_pin = self.manager._certificate_pin(self.certificate.read_bytes())
        issued_uris = {
            name: build_connection_uri(
                "vpn.example.test", 19999, token, source_pin, "私家车-2026"
            )
            for name, token in issued_tokens.items()
        }
        archive = self.manager.create_archive()
        destination_root = self.root / "replacement-server"
        destination_root.mkdir()
        destination_hmac = b"z" * 32
        destination_db = Database(destination_root / "panel.db", destination_hmac)
        destination_db.initialize()
        destination_db.upsert_admin("replacement-admin", "replacement-password")
        destination_cert, destination_key = create_test_certificate(
            destination_root, "vpn.example.test"
        )
        env_file = destination_root / "panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=destination-pin\n"
            "HY2PANEL_PUBLIC_HOST=vpn.example.test\nHY2PANEL_HYSTERIA_PORT=19999\n".format(
                destination_hmac.hex()
            )
        )
        destination = BackupManager(
            database=destination_db,
            hmac_key=destination_hmac,
            tls_cert=destination_cert,
            tls_key=destination_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            node_name="私家车-2026",
            work_dir=destination_root / "work",
        )

        destination.apply_archive(
            archive,
            env_file=env_file,
            backup_root=destination_root / "automatic-backups",
        )

        restored = Database(destination_db.path, self.hmac_key)
        restored_users = {user["name"]: user for user in restored.list_proxy_users_for_usage()}
        self.assertEqual(set(issued_tokens), set(restored_users))
        for name, token in issued_tokens.items():
            with self.subTest(name=name):
                self.assertEqual(name, restored.authenticate_token(token))
                recovered = restored.recover_proxy_token(restored_users[name]["id"])
                if name == "legacy":
                    self.assertIsNone(recovered)
                else:
                    self.assertEqual(token, recovered)
                    self.assertEqual(
                        issued_uris[name],
                        build_connection_uri(
                            "vpn.example.test",
                            19999,
                            recovered,
                            destination._certificate_pin(destination_cert.read_bytes()),
                            "私家车-2026",
                        ),
                    )
        self.assertEqual(7, restored_users["bob"]["device_limit"])
        self.assertEqual(900 * 1024**3, restored_users["bob"]["traffic_limit_bytes"])
        self.assertTrue(restored_users["bob"]["allow_udp_443"])
        self.assertEqual((789, 987), (restored_users["bob"]["tx_bytes"], restored_users["bob"]["rx_bytes"]))
        self.assertEqual(self.certificate.read_bytes(), destination_cert.read_bytes())
        self.assertEqual(self.private_key.read_bytes(), destination_key.read_bytes())

    def test_restore_rolls_back_if_post_write_identity_verification_fails(self):
        archive = self.manager.create_archive()
        destination_root = self.root / "post-write-corruption"
        destination_root.mkdir()
        destination_hmac = b"q" * 32
        destination_db = Database(destination_root / "panel.db", destination_hmac)
        destination_db.initialize()
        original_user = destination_db.create_proxy_user("original")
        destination_cert, destination_key = create_test_certificate(
            destination_root, "vpn.example.test"
        )
        env_file = destination_root / "panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=original-pin\n".format(
                destination_hmac.hex()
            )
        )
        original_cert = destination_cert.read_bytes()
        original_key = destination_key.read_bytes()
        original_env = env_file.read_bytes()
        destination = BackupManager(
            database=destination_db,
            hmac_key=destination_hmac,
            tls_cert=destination_cert,
            tls_key=destination_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            work_dir=destination_root / "work",
        )
        replace_bytes = destination._replace_bytes
        corrupted = {"value": False}

        def corrupt_new_environment(path, value):
            replace_bytes(path, value)
            if Path(path) == env_file and not corrupted["value"]:
                corrupted["value"] = True
                env_file.write_bytes(value.replace(b"HY2PANEL_CERT_PIN=", b"HY2PANEL_CERT_PIN=corrupt-"))

        destination._replace_bytes = corrupt_new_environment

        with self.assertRaises(BackupValidationError):
            destination.apply_archive(
                archive,
                env_file=env_file,
                backup_root=destination_root / "automatic-backups",
            )

        restored_current = Database(destination_db.path, destination_hmac)
        self.assertEqual("original", restored_current.authenticate_token(original_user["token"]))
        self.assertEqual(original_cert, destination_cert.read_bytes())
        self.assertEqual(original_key, destination_key.read_bytes())
        self.assertEqual(original_env, env_file.read_bytes())

    def test_restore_rolls_back_if_post_write_user_data_differs(self):
        archive = self.manager.create_archive()
        destination_root = self.root / "post-write-user-corruption"
        destination_root.mkdir()
        destination_hmac = b"r" * 32
        destination_db = Database(destination_root / "panel.db", destination_hmac)
        destination_db.initialize()
        original_user = destination_db.create_proxy_user("original")
        destination_cert, destination_key = create_test_certificate(
            destination_root, "vpn.example.test"
        )
        env_file = destination_root / "panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=original-pin\n".format(
                destination_hmac.hex()
            )
        )
        original_cert = destination_cert.read_bytes()
        original_key = destination_key.read_bytes()
        original_env = env_file.read_bytes()
        destination = BackupManager(
            database=destination_db,
            hmac_key=destination_hmac,
            tls_cert=destination_cert,
            tls_key=destination_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            work_dir=destination_root / "work",
        )
        validate_applied_restore = destination._validate_applied_restore

        def corrupt_then_validate(*args, **kwargs):
            with sqlite3.connect(str(destination_db.path)) as connection:
                connection.execute(
                    "UPDATE proxy_users SET traffic_limit_bytes = traffic_limit_bytes + 1"
                )
            return validate_applied_restore(*args, **kwargs)

        destination._validate_applied_restore = corrupt_then_validate

        with self.assertRaises(BackupValidationError):
            destination.apply_archive(
                archive,
                env_file=env_file,
                backup_root=destination_root / "automatic-backups",
            )

        restored_current = Database(destination_db.path, destination_hmac)
        self.assertEqual("original", restored_current.authenticate_token(original_user["token"]))
        self.assertEqual(original_cert, destination_cert.read_bytes())
        self.assertEqual(original_key, destination_key.read_bytes())
        self.assertEqual(original_env, env_file.read_bytes())

    def test_restore_rolls_back_all_files_if_replacement_fails(self):
        archive = self.manager.create_archive()
        destination_root = self.root / "rollback-destination"
        destination_root.mkdir()
        destination_hmac = b"r" * 32
        destination_db = Database(destination_root / "panel.db", destination_hmac)
        destination_db.initialize()
        original_user = destination_db.create_proxy_user("original")
        destination_cert, destination_key = create_test_certificate(
            destination_root, "vpn.example.test"
        )
        env_file = destination_root / "panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=original-pin\n".format(
                destination_hmac.hex()
            )
        )
        original_cert = destination_cert.read_bytes()
        original_key = destination_key.read_bytes()
        original_env = env_file.read_bytes()
        destination = BackupManager(
            database=destination_db,
            hmac_key=destination_hmac,
            tls_cert=destination_cert,
            tls_key=destination_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            work_dir=destination_root / "work",
        )
        replace_bytes = destination._replace_bytes
        failed = {"value": False}

        def fail_once(path, value):
            if Path(path) == destination_cert and not failed["value"]:
                failed["value"] = True
                raise OSError("simulated disk failure")
            return replace_bytes(path, value)

        destination._replace_bytes = fail_once

        with self.assertRaises(OSError):
            destination.apply_archive(
                archive,
                env_file=env_file,
                backup_root=destination_root / "automatic-backups",
            )

        restored_current = Database(destination_db.path, destination_hmac)
        self.assertEqual("original", restored_current.authenticate_token(original_user["token"]))
        self.assertEqual(original_cert, destination_cert.read_bytes())
        self.assertEqual(original_key, destination_key.read_bytes())
        self.assertEqual(original_env, env_file.read_bytes())

    def test_prepared_transaction_recovers_from_power_loss_using_durable_backups(self):
        archive = self.manager.create_archive()
        destination_root = self.root / "prepared-power-loss"
        destination_root.mkdir()
        destination_hmac = b"p" * 32
        destination_db = Database(destination_root / "panel.db", destination_hmac)
        destination_db.initialize()
        original = destination_db.create_proxy_user("original")
        destination_db.path.chmod(0o600)
        destination_cert, destination_key = create_test_certificate(
            destination_root, "vpn.example.test"
        )
        destination_cert.chmod(0o640)
        destination_key.chmod(0o640)
        destination_work = destination_root / "work"
        maintenance_lock = destination_root / "maintenance.lock"
        maintenance_lock.touch(mode=0o600)
        marker = destination_root / "restore-active"
        env_file = destination_root / "panel.env"
        destination = BackupManager(
            database=destination_db,
            hmac_key=destination_hmac,
            tls_cert=destination_cert,
            tls_key=destination_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            work_dir=destination_work,
            maintenance_lock_path=maintenance_lock,
            maintenance_lock_owner=os.geteuid(),
            maintenance_lock_mode=0o600,
            restore_marker_path=marker,
        )
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN={}\n".format(
                destination_hmac.hex(),
                destination._certificate_pin(destination_cert.read_bytes()),
            ),
            encoding="utf-8",
        )
        env_file.chmod(0o640)
        archive_bytes = archive.read_bytes()
        destination.stage_archive(io.BytesIO(archive_bytes), len(archive_bytes))
        destination.queue_restore_transaction(
            marker, env_file, destination_root / "automatic-backups"
        )
        real_replace = destination._replace_bytes
        destination._replace_bytes = lambda *_args: (_ for _ in ()).throw(
            KeyboardInterrupt("simulated power loss")
        )
        try:
            with self.assertRaisesRegex(KeyboardInterrupt, "power loss"):
                destination.apply_pending_archive(
                    env_file=env_file,
                    backup_root=destination_root / "automatic-backups",
                    transaction_path=marker,
                    archive_path=Path(str(marker) + ".archive"),
                )
        finally:
            destination._replace_bytes = real_replace

        prepared = hysteria2_panel._read_restore_transaction(
            marker, expected_uid=os.geteuid(), strict_paths=False
        )
        self.assertEqual("prepared", prepared["phase"])
        for name in ("panel.db", "server.crt", "server.key", "panel.env"):
            self.assertEqual(
                0o600, (Path(prepared["backupDir"]) / name).stat().st_mode & 0o777
            )

        hysteria2_panel._reconcile_to_services_pending(
            prepared, marker, identity_uid=os.geteuid()
        )
        recovered = hysteria2_panel._read_restore_transaction(
            marker, expected_uid=os.geteuid(), strict_paths=False
        )
        self.assertEqual("services-pending", recovered["phase"])
        self.assertEqual("rolled-back", recovered["outcome"])
        self.assertEqual(
            "original", Database(destination_db.path, destination_hmac).authenticate_token(
                original["token"]
            )
        )

    def test_explicit_restore_advances_to_health_phase_and_resume_clears_marker(self):
        archive = self.manager.create_archive()
        destination_root = self.root / "explicit-transaction"
        destination_root.mkdir()
        database_path = destination_root / "panel.db"
        destination_hmac = b"e" * 32
        destination_db = Database(database_path, destination_hmac)
        destination_db.initialize()
        destination_db.create_proxy_user("old-user")
        database_path.chmod(0o600)
        certificate, private_key = create_test_certificate(
            destination_root, "vpn.example.test"
        )
        certificate.chmod(0o640)
        private_key.chmod(0o640)
        env_file = destination_root / "panel.env"
        staging = BackupManager(
            database=destination_db,
            hmac_key=destination_hmac,
            tls_cert=certificate,
            tls_key=private_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            node_name="test-node",
            work_dir=destination_root / "backup-restore",
            maintenance_lock_path=destination_root / "maintenance.lock",
            maintenance_lock_owner=os.geteuid(),
            maintenance_lock_mode=0o600,
            restore_marker_path=destination_root / "restore-active",
        )
        (destination_root / "maintenance.lock").touch(mode=0o600)
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN={}\n".format(
                destination_hmac.hex(),
                staging._certificate_pin(certificate.read_bytes()),
            ),
            encoding="utf-8",
        )
        env_file.chmod(0o640)
        archive_bytes = archive.read_bytes()
        staging.stage_archive(io.BytesIO(archive_bytes), len(archive_bytes))
        marker = destination_root / "restore-active"
        backup_root = destination_root / "automatic-backups"
        settings = mock.Mock(
            database_path=database_path,
            hmac_key=destination_hmac,
            tls_cert=certificate,
            tls_key=private_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            node_name="test-node",
            panel_scheme="http",
            panel_port=19998,
            auth_port=19996,
            stats_url="http://127.0.0.1:19997",
            stats_443_url="http://127.0.0.1:19995",
            stats_secret="stats-secret",
        )

        with mock.patch.object(
            hysteria2_panel, "RESTORE_ENV_FILE", env_file
        ), mock.patch.object(
            hysteria2_panel, "RESTORE_BACKUP_ROOT", backup_root
        ), mock.patch.object(
            hysteria2_panel, "settle_restore_traffic"
        ), mock.patch.object(
            hysteria2_panel, "stop_restore_services"
        ), mock.patch("builtins.print"):
            hysteria2_panel.restore_pending(
                settings,
                lock_path=destination_root / "maintenance.lock",
                marker_path=marker,
            )

        transaction = hysteria2_panel._read_restore_transaction(
            marker, expected_uid=os.geteuid(), strict_paths=False
        )
        self.assertEqual("services-pending", transaction["phase"])
        self.assertEqual("applied", transaction["outcome"])
        restored = Database(database_path, self.hmac_key)
        self.assertEqual("alice", restored.authenticate_token(self.user["token"]))

        def runner(command, **_kwargs):
            self.assertEqual("show", command[1])
            return mock.Mock(
                returncode=0,
                stdout="LoadState=loaded\nActiveState=active\n",
                stderr="",
            )

        hysteria2_panel.resume_after_restore(
            settings,
            lock_path=destination_root / "maintenance.lock",
            marker_path=marker,
            runner=runner,
            expected_uid=os.geteuid(),
            strict_paths=False,
            health_probe=lambda *_args: None,
            stats_probe=lambda *_args: None,
            tcp_probe=lambda *_args: None,
            attempts=2,
            sleeper=lambda _seconds: None,
        )
        self.assertFalse(marker.exists())


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
        self.service_controller = FakeServiceController()
        self.egress_policy_controller = FakeEgressPolicyController()
        self.restore_controller = FakeRestoreController()
        self.update_controller = FakeUpdateController()
        self.reboot_controller = FakeRebootController()
        certificate, private_key = create_test_certificate(self.temp_dir.name)
        maintenance_lock = Path(self.temp_dir.name) / "maintenance.lock"
        maintenance_lock.touch(mode=0o600)
        self.backup_manager = BackupManager(
            database=self.db,
            hmac_key=b"c" * 32,
            tls_cert=certificate,
            tls_key=private_key,
            public_host="154.9.234.210",
            hysteria_port=19999,
            node_name="私家车-2026",
            work_dir=Path(self.temp_dir.name) / "backup-restore",
            maintenance_lock_path=maintenance_lock,
            maintenance_lock_owner=os.geteuid(),
            maintenance_lock_mode=0o600,
            restore_marker_path=Path(self.temp_dir.name) / "restore-active",
        )
        self.application = PanelApplication(
            database=self.db,
            public_host="154.9.234.210",
            hysteria_port=19999,
            pin_sha256="AA:BB:CC",
            stats_client=self.stats,
            node_name="私家车-2026",
            service_controller=self.service_controller,
            egress_policy_controller=self.egress_policy_controller,
            system_metrics=FakeSystemMetrics(),
            update_checker=FakeUpdateChecker(),
            backup_manager=self.backup_manager,
            restore_controller=self.restore_controller,
            update_controller=self.update_controller,
            reboot_controller=self.reboot_controller,
        )
        self.server = make_panel_server(("127.0.0.1", 0), self.application)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{}".format(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def request(self, path, data=None, headers=None, follow_redirects=True, raw_data=None):
        body = raw_data
        if body is None and data is not None:
            body = urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers or {},
            method="POST" if body is not None else "GET",
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
            self.assertEqual("no-store", response.headers["Cache-Control"])
            self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
            self.assertEqual("no-referrer", response.headers["Referrer-Policy"])

        with self.request("/login") as response:
            body = response.read().decode()
            self.assertIn('type="password"', body)
            self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
            self.assertIn("script-src 'nonce-", response.headers["Content-Security-Policy"])

    def test_liveness_readiness_and_loopback_metrics_are_distinct(self):
        class FakeHealth:
            ready = False

            def readiness(self):
                return self.ready, {"database": self.ready}

            def prometheus_metrics(self):
                return "hy2panel_ready {}\n".format(1 if self.ready else 0)

        health = FakeHealth()
        self.application.health_monitor = health

        with self.request("/healthz") as response:
            self.assertEqual(200, response.status)
        with self.assertRaises(urllib.error.HTTPError) as unavailable:
            self.request("/readyz")
        self.assertEqual(503, unavailable.exception.code)
        self.assertEqual({"status": "not-ready"}, json.load(unavailable.exception))

        health.ready = True
        with self.request("/readyz") as response:
            self.assertEqual(200, response.status)
            self.assertEqual({"status": "ready"}, json.load(response))
        with self.request("/metrics") as response:
            metrics = response.read().decode()
            self.assertEqual("text/plain; version=0.0.4; charset=utf-8", response.headers["Content-Type"])
            self.assertEqual("hy2panel_ready 1\n", metrics)

        with mock.patch.object(PanelHandler, "_is_loopback_client", return_value=False):
            with self.assertRaises(urllib.error.HTTPError) as external:
                self.request("/metrics")
        self.assertEqual(404, external.exception.code)

    def test_large_dashboard_uses_negotiated_gzip_without_caching_sensitive_html(self):
        for index in range(356):
            self.db.create_proxy_user("gzip-{:04d}".format(index))
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            identity = response.read()
        compressed_headers = dict(headers)
        compressed_headers["Accept-Encoding"] = "br, gzip, deflate"
        with self.request("/", headers=compressed_headers) as response:
            compressed = response.read()
            content_encoding = response.headers.get("Content-Encoding")
            vary = response.headers.get("Vary")
            cache_control = response.headers.get("Cache-Control")

        self.assertEqual("gzip", content_encoding)
        self.assertEqual("Accept-Encoding", vary)
        self.assertEqual("no-store", cache_control)
        self.assertLess(len(compressed), len(identity) // 4)
        self.assertIn("Hysteria 2 用户管理面板", gzip.decompress(compressed).decode())

    def test_gzip_quality_zero_is_respected(self):
        headers, _ = self.authenticated_headers()
        headers["Accept-Encoding"] = "gzip;q=0"

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        self.assertIsNone(response.headers.get("Content-Encoding"))
        self.assertIn("Hysteria 2 用户管理面板", body)

    def test_login_page_exposes_svg_favicon(self):
        with self.request("/login") as response:
            body = response.read().decode()
            self.assertIn(
                '<link rel="icon" type="image/svg+xml" href="/favicon.svg">',
                body,
            )
            self.assertIn("img-src 'self'", response.headers["Content-Security-Policy"])

        with self.request("/favicon.svg") as response:
            icon = response.read().decode()
            self.assertEqual("image/svg+xml", response.headers["Content-Type"])
            self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"', icon)
            self.assertIn('viewBox="0 0 64 64"', icon)

    def test_fifth_bad_login_immediately_locks_source_and_returns_retry_after(self):
        now = [1000.0]
        self.application.rate_limiter = LoginRateLimiter(
            max_attempts=2, window_seconds=60, clock=lambda: now[0]
        )

        with self.assertRaises(urllib.error.HTTPError) as first:
            self.request("/login", {"username": "Elegy", "password": "wrong"})
        self.assertEqual(401, first.exception.code)

        with self.assertRaises(urllib.error.HTTPError) as locked:
            self.request("/login", {"username": "Elegy", "password": "wrong"})
        self.assertEqual(429, locked.exception.code)
        self.assertEqual("60", locked.exception.headers["Retry-After"])
        self.assertIn("尝试次数过多", locked.exception.read().decode())

        with self.assertRaises(urllib.error.HTTPError) as still_locked:
            self.request(
                "/login", {"username": "Elegy", "password": "admin-password"}
            )
        self.assertEqual(429, still_locked.exception.code)

        now[0] += 61
        with self.assertRaises(urllib.error.HTTPError) as success:
            self.request(
                "/login",
                {"username": "Elegy", "password": "admin-password"},
                follow_redirects=False,
            )
        self.assertEqual(303, success.exception.code)

    def test_locked_source_is_audited_only_on_the_lock_transition(self):
        actions = []
        self.db.audit = lambda _actor, action, _target, _address: actions.append(action)
        self.application.rate_limiter = LoginRateLimiter(max_attempts=1, window_seconds=60)

        for password in ("wrong-password", "admin-password"):
            with self.assertRaises(urllib.error.HTTPError) as response:
                self.request("/login", {"username": "Elegy", "password": password})
            self.assertEqual(429, response.exception.code)

        self.assertEqual(1, actions.count("login_failed"))
        self.assertEqual(1, actions.count("login_locked"))

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
        user = self.db.list_proxy_users()["users"][0]
        self.assertEqual("alice", user["name"])
        self.assertEqual(3, user["device_limit"])
        self.assertEqual(250 * 1024**3, user["traffic_limit_bytes"])

    def test_user_creation_accepts_device_and_traffic_limits(self):
        headers, csrf_token = self.authenticated_headers()

        with self.request(
            "/users",
            {
                "name": "custom",
                "device_limit": "7",
                "traffic_limit_gb": "500",
                "csrf": csrf_token,
            },
            headers=headers,
        ) as response:
            self.assertEqual(201, response.status)

        user = self.db.list_proxy_users()["users"][0]
        self.assertEqual(7, user["device_limit"])
        self.assertEqual(500 * 1024**3, user["traffic_limit_bytes"])

    def test_inline_user_creation_returns_connection_json_for_the_dashboard_dialog(self):
        headers, csrf_token = self.authenticated_headers()

        with self.request(
            "/users",
            {
                "name": "dialog-user",
                "device_limit": "3",
                "traffic_limit_gb": "250",
                "csrf": csrf_token,
                "inline": "1",
            },
            headers=headers,
        ) as response:
            payload = json.loads(response.read().decode())

        self.assertEqual(201, response.status)
        self.assertEqual("application/json; charset=utf-8", response.headers["Content-Type"])
        self.assertEqual("dialog-user", payload["name"])
        self.assertTrue(payload["uri"].startswith("hysteria2://"))
        self.assertNotIn("token", payload)

    def test_dashboard_shows_service_and_global_summary_cards(self):
        self.db.create_proxy_user("alice")
        self.db.create_proxy_user("bob")
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        for label in (
            "服务状态",
            "当前用户",
            "不活跃用户",
            "在线设备",
            "按 Hysteria 客户端实例统计",
            "总上传",
            "总下载",
            "服务控制",
            "系统资源",
            "高流量用户",
            "当前版本",
            "BBR 状态",
            "Hysteria BBR",
            "内核 bbr / fq",
            "检查更新",
            "重置全部流量",
            "总流量",
            "分享",
            "重置流量",
            "一键备份",
            "一键恢复",
        ):
            self.assertIn(label, body)
        self.assertIn('value="3"', body)
        self.assertIn('value="250"', body)

    def test_dashboard_uses_dialogs_and_compact_mobile_user_rows(self):
        created = self.db.create_proxy_user("alice")
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        self.assertIn('data-dialog-open="migration-dialog"', body)
        self.assertIn('<dialog id="migration-dialog"', body)
        self.assertIn('aria-labelledby="migration-title"', body)
        self.assertIn('data-dialog-close', body)
        self.assertIn('data-create-user-form', body)
        self.assertIn('data-dialog-open="edit-user-dialog"', body)
        self.assertIn('<dialog id="edit-user-dialog"', body)
        self.assertIn('data-edit-user-form', body)
        self.assertIn('<dialog id="credentials-dialog"', body)
        self.assertIn('data-share-form', body)
        self.assertIn('data-qr-form', body)
        self.assertIn('name="qr" value="1"', body)
        self.assertIn('id="credentials-qr"', body)
        self.assertIn('data-save-qr', body)
        self.assertNotIn(created["token"], body)
        self.assertIn('data-label="名称"', body)
        self.assertIn('data-label="操作"', body)
        self.assertIn('@media(max-width:640px)', body)
        self.assertIn('.user-heading{flex-basis:auto}', body)
        self.assertIn('.user-table tr{display:grid;', body)
        self.assertIn('grid-template-columns:repeat(3,minmax(0,1fr))', body)
        self.assertIn('.user-table th{position:sticky;', body)
        self.assertIn('@media(prefers-reduced-motion:reduce)', body)
        self.assertIn('先通过服务器 IP 登录新面板完成恢复并验证，再切换 DNS', body)
        self.assertNotIn('td::before{content:attr(data-label)', body)
        self.assertNotIn('限 3 个并发连接', body)

    def test_dashboard_marks_users_over_the_client_instance_limit(self):
        self.db.create_proxy_user("alice", device_limit=1)
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        self.assertIn('class="over-limit-name">alice</strong>', body)
        self.assertIn('客户端实例超限', body)
        self.assertIn('data-over-device-limit="1"', body)

    def test_user_limits_can_be_edited_without_changing_the_issued_link(self):
        created = self.db.create_proxy_user("editable")
        original_token = self.db.recover_proxy_token(created["id"])
        headers, csrf_token = self.authenticated_headers()

        with self.request(
            "/users/{}/edit".format(created["id"]),
            {
                "csrf": csrf_token,
                "generation": "0",
                "device_limit": "6",
                "traffic_limit_gb": "750",
                "allow_udp_443": "1",
                "inline": "1",
            },
            headers={**headers, "Accept": "application/json"},
        ) as response:
            payload = json.loads(response.read().decode())

        self.assertEqual(200, response.status)
        self.assertEqual("editable", payload["name"])
        self.assertEqual(6, payload["device_limit"])
        self.assertEqual(750, payload["traffic_limit_gb"])
        self.assertTrue(payload["allow_udp_443"])
        record = self.db.get_proxy_user(created["id"])
        self.assertEqual(6, record["device_limit"])
        self.assertEqual(750 * 1024**3, record["traffic_limit_bytes"])
        self.assertTrue(record["allow_udp_443"])
        self.assertEqual(original_token, self.db.recover_proxy_token(created["id"]))

        with self.request("/", headers=headers) as response:
            dashboard = response.read().decode()
        self.assertIn('name="allow_udp_443"', dashboard)
        self.assertIn('data-allow-udp443="1"', dashboard)
        self.assertIn("允许该账号使用 UDP 443", dashboard)

    def test_user_limit_edit_requires_csrf_and_detects_stale_generation(self):
        created = self.db.create_proxy_user("editable")
        headers, csrf_token = self.authenticated_headers()

        with self.assertRaises(urllib.error.HTTPError) as missing_csrf:
            self.request(
                "/users/{}/edit".format(created["id"]),
                {"generation": "0", "device_limit": "4", "traffic_limit_gb": "300"},
                headers=headers,
            )
        self.assertEqual(403, missing_csrf.exception.code)

        self.db.set_proxy_user_enabled(created["id"], False, expected_generation=0)
        with self.assertRaises(urllib.error.HTTPError) as stale:
            self.request(
                "/users/{}/edit".format(created["id"]),
                {
                    "csrf": csrf_token,
                    "generation": "0",
                    "device_limit": "4",
                    "traffic_limit_gb": "300",
                },
                headers=headers,
            )
        self.assertEqual(409, stale.exception.code)

    def test_dashboard_compacts_operations_and_keeps_login_actions_separate(self):
        self.db.create_proxy_user("alice")
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            dashboard = response.read().decode()
        with self.request("/login") as response:
            login = response.read().decode()

        self.assertIn('class="operations dashboard-trio"', dashboard)
        self.assertIn('class="card traffic-card"', dashboard)
        self.assertIn('class="detail compact-detail"', dashboard)
        self.assertIn('class="service-details version-details"', dashboard)
        self.assertIn('class="detail compact-detail bbr-detail"', dashboard)
        self.assertIn('class="detail compact-detail version-panel"', dashboard)
        self.assertIn('.dashboard-trio{align-items:stretch;grid-template-columns:', dashboard)
        self.assertNotIn('class="detail version-detail"', dashboard)
        self.assertNotIn('.version-panel{border-left:', dashboard)
        self.assertIn('class="login-form"', login)
        self.assertIn('class="login-actions"', login)
        self.assertIn('.login-form{display:grid;gap:12px}', login)

    def test_dashboard_lists_newest_users_first_by_default(self):
        for name in ("oldest", "middle", "newest"):
            self.db.create_proxy_user(name)
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        newest = 'data-user-name="newest"'
        middle = 'data-user-name="middle"'
        oldest = 'data-user-name="oldest"'
        self.assertLess(body.index(newest), body.index(middle))
        self.assertLess(body.index(middle), body.index(oldest))

    def test_dashboard_lists_all_users_with_search_and_create_dialog(self):
        for index in range(55):
            self.db.create_proxy_user("user{:03d}".format(index))
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        self.assertEqual(55, body.count('data-user-name="'))
        self.assertIn("<strong>user000</strong>", body)
        self.assertNotIn("第 1 /", body)
        self.assertIn('type="search"', body)
        self.assertIn('data-user-search', body)
        self.assertIn('class="section-head user-section-head"', body)
        self.assertIn('class="user-heading"', body)
        self.assertIn('for="user-search">用户名', body)
        self.assertLess(body.index('class="user-heading"'), body.index('class="user-search"'))
        self.assertIn('data-search-status', body)
        self.assertIn('window.requestAnimationFrame(filterUsers)', body)
        self.assertIn('data-dialog-open="create-user-dialog"', body)
        self.assertIn('<dialog id="create-user-dialog"', body)
        self.assertIn('aria-labelledby="create-user-title"', body)
        self.assertIn('class="section-actions"', body)
        self.assertIn('placeholder="例如：Alice 手机" autofocus', body)

    def test_dashboard_combines_search_status_online_and_udp443_filters(self):
        allowed = self.db.create_proxy_user("Alice & Co")
        disabled = self.db.create_proxy_user("disabled-user")
        self.db.update_proxy_user_limits(
            allowed["id"],
            3,
            250 * 1024**3,
            allow_udp_443=True,
            expected_generation=0,
        )
        self.db.set_proxy_user_enabled(
            disabled["id"], False, expected_generation=0
        )
        self.stats.snapshot = lambda: {
            "traffic": {},
            "online": {"Alice & Co": 2},
            "available": True,
        }
        headers, _ = self.authenticated_headers()

        with self.request(
            "/?q=Alice%20%26%20Co&status=enabled&online=active&udp443=allowed",
            headers=headers,
        ) as response:
            body = response.read().decode()

        self.assertIn('class="user-filters"', body)
        self.assertIn('name="q" type="search" value="Alice &amp; Co"', body)
        self.assertIn('<option value="enabled" selected>启用</option>', body)
        self.assertIn('<option value="active" selected>在线</option>', body)
        self.assertIn('<option value="allowed" selected>已开放</option>', body)
        self.assertIn('data-enabled="1"', body)
        self.assertIn('data-online="2"', body)
        self.assertIn('data-allow-udp443="1"', body)
        self.assertIn('data-filter-empty', body)
        self.assertIn('data-clear-user-filters', body)
        self.assertIn("new URLSearchParams(new FormData(filterForm))", body)
        self.assertIn("row.dataset.enabled === (statusFilter.value === 'enabled' ? '1' : '0')", body)
        self.assertIn("row.dataset.allowUdp443 === (udp443Filter.value === 'allowed' ? '1' : '0')", body)
        self.assertIn("history.replaceState", body)
        self.assertIn("userSearch.value = '';", body)
        self.assertNotIn("filterForm.reset();", body)

    def test_dashboard_rejects_unknown_filter_values_and_bounds_search_text(self):
        self.db.create_proxy_user("safe-user")
        headers, _ = self.authenticated_headers()
        query = urllib.parse.urlencode(
            {
                "q": '<script>alert("x")</script>' + "x" * 100,
                "status": "unknown",
                "online": "unknown",
                "udp443": "unknown",
            }
        )

        with self.request("/?" + query, headers=headers) as response:
            body = response.read().decode()

        self.assertNotIn('<script>alert("x")</script>', body)
        self.assertIn('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;', body)
        self.assertNotIn('value="unknown" selected', body)
        search_value = re.search(
            r'name="q" type="search" value="([^"]*)"', body
        ).group(1)
        self.assertLessEqual(len(html.unescape(search_value)), 96)

    def test_backup_download_and_restore_upload_are_authenticated_and_csrf_protected(self):
        self.db.create_proxy_user("migrating-user")
        headers, csrf_token = self.authenticated_headers()

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/backup",
                {"csrf": "wrong"},
                headers=headers,
                follow_redirects=False,
            )
        self.assertEqual(403, raised.exception.code)

        with self.request(
            "/backup", {"csrf": csrf_token}, headers=headers
        ) as response:
            backup_bytes = response.read()
            self.assertEqual("application/zip", response.headers["Content-Type"])
            self.assertIn("attachment;", response.headers["Content-Disposition"])
            self.assertEqual("no-store", response.headers["Cache-Control"])
        with zipfile.ZipFile(io.BytesIO(backup_bytes)) as package:
            self.assertIn("manifest.json", package.namelist())

        restore_headers = dict(headers)
        restore_headers.update(
            {
                "Content-Type": "application/zip",
                "X-HY2Panel-CSRF": csrf_token,
            }
        )
        with self.request(
            "/restore",
            headers=restore_headers,
            raw_data=backup_bytes,
            follow_redirects=False,
        ) as response:
            body = response.read().decode()
            self.assertEqual(202, response.status)
        self.assertIn("恢复任务已启动", body)
        self.assertEqual(1, self.restore_controller.queued)
        self.assertTrue(self.backup_manager.pending_archive.is_file())

    def test_backup_fails_closed_when_pending_traffic_cannot_be_flushed(self):
        headers, csrf_token = self.authenticated_headers()
        original_run = self.application.usage_manager.run_after_collect

        def fail_collect(_action):
            raise RuntimeError("traffic database unavailable")

        self.application.usage_manager.run_after_collect = fail_collect
        try:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                self.request(
                    "/backup",
                    {"csrf": csrf_token},
                    headers=headers,
                    follow_redirects=False,
                )
            self.assertEqual(500, raised.exception.code)
            self.assertEqual([], list(self.backup_manager.work_dir.glob("*.zip")))
        finally:
            self.application.usage_manager.run_after_collect = original_run

    def test_restore_rejects_wrong_content_type_and_csrf(self):
        archive = self.backup_manager.create_archive().read_bytes()
        headers, csrf_token = self.authenticated_headers()

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/restore",
                headers={**headers, "Content-Type": "application/zip", "X-HY2Panel-CSRF": "wrong"},
                raw_data=archive,
                follow_redirects=False,
            )
        self.assertEqual(403, raised.exception.code)

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/restore",
                headers={**headers, "Content-Type": "application/octet-stream", "X-HY2Panel-CSRF": csrf_token},
                raw_data=archive,
                follow_redirects=False,
            )
        self.assertEqual(400, raised.exception.code)

    def test_restore_removes_staged_archive_when_root_service_cannot_start(self):
        class FailingRestoreController:
            def queue(self):
                raise RuntimeError("sudo unavailable")

        self.application.restore_controller = FailingRestoreController()
        archive = self.backup_manager.create_archive().read_bytes()
        headers, csrf_token = self.authenticated_headers()

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/restore",
                headers={
                    **headers,
                    "Content-Type": "application/zip",
                    "X-HY2Panel-CSRF": csrf_token,
                },
                raw_data=archive,
                follow_redirects=False,
            )

        self.assertEqual(500, raised.exception.code)
        self.assertFalse(self.backup_manager.pending_archive.exists())

    def test_dashboard_shows_only_top_five_traffic_users(self):
        for index in range(6):
            self.db.create_proxy_user("user{}".format(index))
            self.db.add_traffic(
                {"user{}".format(index): {"tx": index + 1, "rx": index + 1}}
            )
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        self.assertEqual(5, body.count('class="rank-row"'))
        self.assertNotIn('<span class="rank-name">user0</span>', body)
        self.assertIn('class="rank-main"><span class="rank-name">', body)
        self.assertIn('.dashboard-trio{align-items:stretch;', body)

    def test_total_traffic_header_sorts_users_in_both_directions(self):
        for name, total in (("alpha", 20), ("beta", 60), ("gamma", 40)):
            self.db.create_proxy_user(name)
            self.db.add_traffic({name: {"tx": total // 2, "rx": total // 2}})
        headers, _ = self.authenticated_headers()

        with self.request("/?sort=traffic&order=desc", headers=headers) as response:
            descending = response.read().decode()
        with self.request("/?sort=traffic&order=asc", headers=headers) as response:
            ascending = response.read().decode()

        beta_row = 'data-user-name="beta"'
        gamma_row = 'data-user-name="gamma"'
        alpha_row = 'data-user-name="alpha"'
        self.assertLess(descending.index(beta_row), descending.index(gamma_row))
        self.assertLess(descending.index(gamma_row), descending.index(alpha_row))
        self.assertLess(ascending.index(alpha_row), ascending.index(gamma_row))
        self.assertLess(ascending.index(gamma_row), ascending.index(beta_row))
        self.assertIn('href="/?sort=traffic&amp;order=asc"', descending)

    def test_online_device_header_sorts_users_in_both_directions(self):
        for name in ("alpha", "beta", "gamma"):
            self.db.create_proxy_user(name)
        self.stats.snapshot = lambda: {
            "traffic": {},
            "online": {"alpha": 1, "beta": 3, "gamma": 2},
            "available": True,
        }
        headers, _ = self.authenticated_headers()

        with self.request("/?sort=online&order=desc", headers=headers) as response:
            descending = response.read().decode()
        with self.request("/?sort=online&order=asc", headers=headers) as response:
            ascending = response.read().decode()

        beta_row = 'data-user-name="beta"'
        gamma_row = 'data-user-name="gamma"'
        alpha_row = 'data-user-name="alpha"'
        self.assertLess(descending.index(beta_row), descending.index(gamma_row))
        self.assertLess(descending.index(gamma_row), descending.index(alpha_row))
        self.assertLess(ascending.index(alpha_row), ascending.index(gamma_row))
        self.assertLess(ascending.index(gamma_row), ascending.index(beta_row))
        self.assertIn('href="/?sort=online&amp;order=asc"', descending)
        self.assertIn('<th aria-sort="descending"><a class="sort-link" href="/?sort=online', descending)
        self.assertIn(
            '<th aria-sort="none"><a class="sort-link" href="/?sort=traffic&amp;order=desc">总流量 ⇅</a>',
            descending,
        )

    def test_share_and_traffic_reset_actions_are_csrf_protected(self):
        created = self.db.create_proxy_user("carol")
        self.db.add_traffic({"carol": {"tx": 10, "rx": 20}})
        headers, csrf_token = self.authenticated_headers()

        with self.request(
            "/users/{}/share".format(created["id"]),
            {"csrf": csrf_token, "generation": "0", "inline": "1"},
            headers=headers,
        ) as response:
            payload = json.loads(response.read().decode())
        self.assertTrue(payload["uri"].startswith("hysteria2://"))
        self.assertEqual("carol", payload["name"])

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/users/{}/reset".format(created["id"]),
                {"csrf": "wrong", "generation": "0"},
                headers=headers,
                follow_redirects=False,
            )
        self.assertEqual(403, raised.exception.code)

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/users/{}/reset".format(created["id"]),
                {"csrf": csrf_token, "generation": "0"},
                headers=headers,
                follow_redirects=False,
            )
        self.assertEqual(303, raised.exception.code)
        user = self.db.get_proxy_user(created["id"])
        self.assertEqual((0, 0), (user["tx_bytes"], user["rx_bytes"]))

    def test_qr_share_is_opt_in_and_returns_a_bounded_binary_matrix(self):
        created = self.db.create_proxy_user("qr-user")
        headers, csrf_token = self.authenticated_headers()
        path = "/users/{}/share".format(created["id"])

        with self.request(
            path,
            {"csrf": csrf_token, "generation": "0", "inline": "1"},
            headers=headers,
        ) as response:
            ordinary = json.loads(response.read().decode())
        self.assertNotIn("qr", ordinary)

        with self.request(
            path,
            {
                "csrf": csrf_token,
                "generation": "0",
                "inline": "1",
                "qr": "1",
            },
            headers=headers,
        ) as response:
            payload = json.loads(response.read().decode())

        self.assertEqual(ordinary["uri"], payload["uri"])
        self.assertEqual("qr-user", payload["name"])
        matrix = payload["qr"]
        self.assertGreaterEqual(len(matrix), 21)
        self.assertLessEqual(len(matrix), 177)
        self.assertTrue(all(len(row) == len(matrix) for row in matrix))
        self.assertTrue(all(set(row) <= {"0", "1"} for row in matrix))

    def test_legacy_user_share_requires_an_explicit_rotation(self):
        legacy = self.db.create_proxy_user("legacy", token="legacy-token")
        headers, csrf_token = self.authenticated_headers()

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/users/{}/share".format(legacy["id"]),
                {"csrf": csrf_token, "generation": "0"},
                headers=headers,
            )

        self.assertEqual(409, raised.exception.code)
        self.assertIn("轮换密钥", raised.exception.read().decode())

    def test_global_reset_service_control_and_update_check(self):
        user = self.db.create_proxy_user("carol")
        self.db.add_traffic({"carol": {"tx": 10, "rx": 20}})
        headers, csrf_token = self.authenticated_headers()

        for path in ("/users/reset-traffic", "/service/stop", "/updates/check"):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                self.request(
                    path,
                    {"csrf": csrf_token},
                    headers=headers,
                    follow_redirects=False,
                )
            self.assertEqual(303, raised.exception.code)

        self.assertEqual((0, 0), tuple(self.db.get_proxy_user(user["id"])[key] for key in ("tx_bytes", "rx_bytes")))
        self.assertEqual(["stop"], self.service_controller.actions)
        with self.request("/", headers=headers) as response:
            body = response.read().decode()
        self.assertIn("v0.21.0", body)

    def test_disruptive_actions_fail_closed_when_traffic_settlement_fails(self):
        headers, csrf_token = self.authenticated_headers()
        self.application.usage_manager.run_after_collect = mock.Mock(
            side_effect=RuntimeError("stats unavailable")
        )

        for path in ("/service/restart", "/egress/full", "/system/reboot"):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                self.request(path, {"csrf": csrf_token}, headers=headers)
            self.assertEqual(500, raised.exception.code)

        self.assertEqual([], self.service_controller.actions)
        self.assertEqual([], self.egress_policy_controller.actions)
        self.assertEqual(0, self.reboot_controller.queued)

    def test_dashboard_shows_full_state_and_node_wide_switch_in_service_port_card(self):
        headers, _csrf_token = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        self.assertIn('class="detail compact-detail port-detail"', body)
        self.assertIn('action="/egress/full"', body)
        self.assertIn('data-egress-form', body)
        self.assertIn('aria-pressed="false"', body)
        self.assertIn('FULL 已关闭', body)
        self.assertLess(body.index("UDP 19999"), body.index('action="/egress/full"'))

        self.egress_policy_controller.state = "full"
        with self.request("/", headers=headers) as response:
            body = response.read().decode()
        self.assertIn('action="/egress/web"', body)
        self.assertIn('aria-pressed="true"', body)
        self.assertIn('FULL 已开启', body)

    def test_egress_policy_switch_requires_csrf_and_accepts_only_fixed_policies(self):
        headers, csrf_token = self.authenticated_headers()

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/egress/full",
                {"csrf": "wrong"},
                headers=headers,
                follow_redirects=False,
            )
        self.assertEqual(403, raised.exception.code)
        self.assertEqual([], self.egress_policy_controller.actions)

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/egress/full;id",
                {"csrf": csrf_token},
                headers=headers,
                follow_redirects=False,
            )
        self.assertEqual(404, raised.exception.code)
        self.assertEqual([], self.egress_policy_controller.actions)

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(
                "/egress/full",
                {"csrf": csrf_token},
                headers=headers,
                follow_redirects=False,
            )
        self.assertEqual(303, raised.exception.code)
        self.assertEqual(["full"], self.egress_policy_controller.actions)

    def test_online_update_requires_csrf_and_queues_the_fixed_task(self):
        headers, csrf_token = self.authenticated_headers()

        with self.assertRaises(urllib.error.HTTPError) as missing_csrf:
            self.request("/updates/apply", {}, headers=headers)
        self.assertEqual(403, missing_csrf.exception.code)
        self.assertEqual(0, self.update_controller.queued)

        with self.request(
            "/updates/check",
            {"csrf": csrf_token},
            headers=headers,
        ):
            pass
        with self.request("/", headers=headers) as response:
            body = response.read().decode()
        self.assertIn('action="/updates/apply"', body)
        self.assertIn('data-update-form', body)
        self.assertIn('data-update-status', body)
        self.assertIn("立即更新", body)

        with self.request(
            "/updates/apply",
            {"csrf": csrf_token},
            headers={**headers, "Accept": "application/json"},
        ) as response:
            payload = json.loads(response.read().decode())
            self.assertEqual(202, response.status)
            self.assertEqual("queued", payload["state"])
            self.assertEqual("v0.4.0", payload["target"])
        self.assertEqual(1, self.update_controller.queued)
        self.assertEqual("v0.4.0", self.update_controller.target)

        with self.request("/updates/status", headers=headers) as response:
            status = json.loads(response.read().decode())
        self.assertEqual("queued", status["state"])
        with self.assertRaises(urllib.error.HTTPError) as unauthenticated:
            self.request("/updates/status", follow_redirects=False)
        self.assertEqual(303, unauthenticated.exception.code)

    def test_update_check_waits_until_an_apply_has_captured_its_target(self):
        apply_started = threading.Event()
        release_apply = threading.Event()
        check_called = threading.Event()

        class BlockingUpdateController(FakeUpdateController):
            def queue(inner_self, target):
                apply_started.set()
                if not release_apply.wait(1):
                    raise RuntimeError("test did not release update apply")
                super().queue(target)

        class ObservedUpdateChecker(FakeUpdateChecker):
            def check(inner_self):
                check_called.set()
                return super().check()

        controller = BlockingUpdateController()
        self.application.update_controller = controller
        self.application.update_checker = ObservedUpdateChecker()
        self.application.update_result = FakeUpdateChecker().check()
        headers, csrf_token = self.authenticated_headers()
        failures = []

        def apply_update():
            try:
                with self.request(
                    "/updates/apply",
                    {"csrf": csrf_token},
                    headers={**headers, "Accept": "application/json"},
                ):
                    pass
            except Exception as exc:
                failures.append(exc)

        def check_update():
            try:
                with self.request(
                    "/updates/check",
                    {"csrf": csrf_token},
                    headers=headers,
                    follow_redirects=False,
                ):
                    pass
            except urllib.error.HTTPError as exc:
                if exc.code != 303:
                    failures.append(exc)
            except Exception as exc:
                failures.append(exc)

        apply_thread = threading.Thread(target=apply_update)
        check_thread = threading.Thread(target=check_update)
        apply_thread.start()
        self.assertTrue(apply_started.wait(1))
        check_thread.start()
        try:
            self.assertFalse(check_called.wait(0.1))
        finally:
            release_apply.set()
            apply_thread.join(1)
            check_thread.join(1)

        self.assertFalse(apply_thread.is_alive())
        self.assertFalse(check_thread.is_alive())
        self.assertEqual([], failures)
        self.assertTrue(check_called.is_set())
        self.assertEqual("v0.4.0", controller.target)

    def test_deleting_a_user_forgets_transient_connection_state(self):
        created = self.db.create_proxy_user("transient-user")
        self.application.usage_manager.pending["transient-user"] = [1000.0]
        self.application.usage_manager.last_online["transient-user"] = 2
        headers, csrf_token = self.authenticated_headers()

        with self.assertRaises(urllib.error.HTTPError) as deleted:
            self.request(
                "/users/{}/delete".format(created["id"]),
                {"csrf": csrf_token, "generation": "0"},
                headers=headers,
                follow_redirects=False,
            )

        self.assertEqual(303, deleted.exception.code)
        self.assertNotIn("transient-user", self.application.usage_manager.pending)
        self.assertNotIn("transient-user", self.application.usage_manager.last_online)

    def test_server_reboot_requires_csrf_and_queues_the_fixed_action(self):
        headers, csrf_token = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()
        self.assertIn('action="/system/reboot"', body)
        self.assertIn("重启服务器", body)
        self.assertIn("所有节点连接会暂时中断", body)

        with self.assertRaises(urllib.error.HTTPError) as missing_csrf:
            self.request("/system/reboot", {}, headers=headers)
        self.assertEqual(403, missing_csrf.exception.code)
        self.assertEqual(0, self.reboot_controller.queued)

        with self.request(
            "/system/reboot", {"csrf": csrf_token}, headers=headers
        ) as response:
            self.assertEqual(202, response.status)
            self.assertIn("服务器正在重启", response.read().decode())
        self.assertEqual(1, self.reboot_controller.queued)

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
        self.assertEqual(30, self.server.request_deadline)
        self.assertEqual(64, self.server.max_workers)
        self.assertIsNone(self.server.tls_context)

    def test_slow_tls_handshake_does_not_block_later_https_request(self):
        server = make_panel_server(("127.0.0.1", 0), self.application)
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.load_cert_chain(
            str(self.backup_manager.tls_cert), str(self.backup_manager.tls_key)
        )
        server.tls_context = tls_context
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        slow_client = socket.create_connection(("127.0.0.1", port), timeout=1)
        try:
            time.sleep(0.1)
            started = time.monotonic()
            with urllib.request.urlopen(
                "https://127.0.0.1:{}/healthz".format(port),
                context=ssl._create_unverified_context(),
                timeout=1,
            ) as response:
                self.assertEqual({"status": "ok"}, json.load(response))
            self.assertLess(time.monotonic() - started, 1)
        finally:
            slow_client.close()
            server.shutdown()
            server.server_close()

    def test_expected_client_disconnect_does_not_emit_server_traceback(self):
        server = object.__new__(BoundedThreadingHTTPServer)
        for error in (
            BrokenPipeError("closed"),
            ConnectionAbortedError("aborted"),
            ConnectionResetError("reset"),
        ):
            with self.subTest(error=type(error).__name__), mock.patch.object(
                ThreadingHTTPServer, "handle_error"
            ) as parent_handler:
                try:
                    raise error
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    server.handle_error(None, ("127.0.0.1", 12345))

                parent_handler.assert_not_called()

    def test_unexpected_server_error_uses_default_error_handler(self):
        server = object.__new__(BoundedThreadingHTTPServer)
        for error in (ValueError("unexpected"), TimeoutError("timed out")):
            with self.subTest(error=type(error).__name__), mock.patch.object(
                ThreadingHTTPServer, "handle_error"
            ) as parent_handler:
                try:
                    raise error
                except (ValueError, TimeoutError):
                    server.handle_error(None, ("127.0.0.1", 12345))

                parent_handler.assert_called_once_with(None, ("127.0.0.1", 12345))


class StatsApiHandler(BaseHTTPRequestHandler):
    kicked = []
    cleared = 0

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
        if self.path == "/traffic?clear=1":
            type(self).cleared += 1
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
        StatsApiHandler.cleared = 0
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
        self.client.kick_many(["bob", "carol"])
        self.assertEqual(["alice", "bob", "carol"], StatsApiHandler.kicked)
        self.assertEqual(
            {"alice": {"tx": 100, "rx": 200}}, self.client.collect_and_clear()
        )
        self.assertEqual(1, StatsApiHandler.cleared)

    def test_stats_response_body_is_bounded(self):
        response = mock.MagicMock()
        response.status = 200
        response.read.return_value = b"x" * (MAX_STATS_RESPONSE_BYTES + 1)
        response.__enter__.return_value = response

        with mock.patch("hysteria2_panel.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "too large"):
                self.client._request("/traffic")

        response.read.assert_called_once_with(MAX_STATS_RESPONSE_BYTES + 1)

    def test_stats_api_must_remain_on_plaintext_loopback(self):
        for url in (
            "http://example.com:19997",
            "https://127.0.0.1:19997",
            "http://localhost:19997",
            "http://127.0.0.1:19997/base",
            "http://127.0.0.1:not-a-port",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    HysteriaStatsClient(url, "stats-secret")

    def test_combined_stats_merge_both_hysteria_entrypoints(self):
        primary = PolicyStatsClient(
            traffic={"alice": {"tx": 100, "rx": 200}},
            online={"alice": 1},
        )
        udp_443 = PolicyStatsClient(
            traffic={
                "alice": {"tx": 7, "rx": 9},
                "bob": {"tx": 3, "rx": 4},
            },
            online={"alice": 2, "bob": 1},
        )
        client = hysteria2_panel.CombinedHysteriaStatsClient(primary, udp_443)

        self.assertEqual(
            {
                "alice": {"tx": 107, "rx": 209},
                "bob": {"tx": 3, "rx": 4},
            },
            client.collect_and_clear(),
        )
        self.assertEqual({"alice": 3, "bob": 1}, client.online())
        client.kick_many(["alice", "bob"])
        self.assertEqual(["alice", "bob"], primary.kicked)
        self.assertEqual(["alice", "bob"], udp_443.kicked)

    def test_combined_stats_kicks_every_entrypoint_when_one_is_unavailable(self):
        primary = PolicyStatsClient()
        udp_443 = PolicyStatsClient()
        primary.kick_many = lambda names: (_ for _ in ()).throw(
            OSError("primary stats unavailable")
        )
        client = hysteria2_panel.CombinedHysteriaStatsClient(primary, udp_443)

        with self.assertRaises(OSError):
            client.kick_many(["alice"])

        self.assertEqual(["alice"], udp_443.kicked)


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
        self.assertEqual("http://127.0.0.1:19995", settings.stats_443_url)
        self.assertEqual("Hysteria 2", settings.node_name)
        self.assertEqual("http", settings.panel_scheme)

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

    def test_internal_auth_listener_must_remain_on_ipv4_loopback(self):
        base = {
            "HY2PANEL_HMAC_KEY": "ab" * 32,
            "HY2PANEL_PUBLIC_HOST": "vpn.ssrvpn.vip",
            "HY2PANEL_STATS_SECRET": "stats-secret",
            "HY2PANEL_CERT_PIN": "AA:BB:CC",
        }

        settings = Settings.from_mapping(
            {**base, "HY2PANEL_AUTH_HOST": "127.0.0.1"}
        )
        self.assertEqual("127.0.0.1", settings.auth_host)
        for address in ("0.0.0.0", "192.0.2.10", "::1"):
            with self.subTest(address=address):
                with self.assertRaisesRegex(ValueError, "AUTH_HOST"):
                    Settings.from_mapping(
                        {**base, "HY2PANEL_AUTH_HOST": address}
                    )

    def test_configured_ports_preserve_privileged_endpoints_but_reserve_secondary_443(self):
        base = {
            "HY2PANEL_HMAC_KEY": "ab" * 32,
            "HY2PANEL_PUBLIC_HOST": "vpn.ssrvpn.vip",
            "HY2PANEL_STATS_SECRET": "stats-secret",
            "HY2PANEL_CERT_PIN": "AA:BB:CC",
        }
        settings = Settings.from_mapping({**base, "HY2PANEL_HYSTERIA_PORT": "443"})
        self.assertEqual(443, settings.hysteria_port)

        for variable in (
            "HY2PANEL_PANEL_PORT",
            "HY2PANEL_AUTH_PORT",
            "HY2PANEL_STATS_PORT",
            "HY2PANEL_STATS_443_PORT",
        ):
            with self.subTest(variable=variable):
                with self.assertRaisesRegex(ValueError, "must be different"):
                    Settings.from_mapping({**base, variable: "443"})


class ConnectionUriTests(unittest.TestCase):
    def test_qr_matrix_has_standard_finder_patterns_and_no_embedded_quiet_zone(self):
        matrix = hysteria2_panel.build_qr_matrix(
            "hysteria2://token@example.test:19999/?insecure=1#node"
        )

        finder = [
            "1111111",
            "1000001",
            "1011101",
            "1011101",
            "1011101",
            "1000001",
            "1111111",
        ]
        self.assertGreaterEqual(len(matrix), 21)
        self.assertLessEqual(len(matrix), 177)
        self.assertEqual(finder, [row[:7] for row in matrix[:7]])
        self.assertEqual(finder, [row[-7:] for row in matrix[:7]])
        self.assertEqual(finder, [row[:7] for row in matrix[-7:]])
        self.assertTrue(all(len(row) == len(matrix) for row in matrix))
        self.assertTrue(all(set(row) <= {"0", "1"} for row in matrix))

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
