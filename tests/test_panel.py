import gzip
import json
import io
import hashlib
import os
import sqlite3
import subprocess
import tempfile
import threading
import unittest
import zipfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

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
            ],
            [url for url, _ in requests],
        )
        self.assertEqual(["/bin/bash", "-n"], calls[0][0][:2])
        self.assertEqual(["/bin/bash"], calls[1][0][:1])
        self.assertNotIn("shell", calls[0][1])
        self.assertNotIn("shell", calls[1][1])
        self.assertEqual("1", calls[1][1]["env"]["HY2PANEL_AUTO_UPDATE"])
        self.assertEqual("v0.12.0", calls[1][1]["env"]["PANEL_REF"])
        self.assertNotIn("ADMIN_PASSWORD", calls[1][1]["env"])
        self.assertEqual(
            {"current": "v0.11.2", "latest": "v0.12.0", "updated": True},
            result,
        )

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
        )

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

    def test_failed_pending_restore_is_quarantined_and_does_not_block_retry(self):
        payload = b"failed restore archive"
        self.manager.work_dir.mkdir(parents=True, mode=0o700)
        self.manager.pending_archive.write_bytes(payload)
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
        second = self.database.create_proxy_user(
            "bob", device_limit=7, traffic_limit_bytes=900 * 1024**3
        )
        legacy = self.database.create_proxy_user("legacy", token="legacy-issued-token")
        self.database.add_traffic({"bob": {"tx": 789, "rx": 987}})
        issued_tokens = {
            "alice": self.user["token"],
            "bob": second["token"],
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
        self.restore_controller = FakeRestoreController()
        self.update_controller = FakeUpdateController()
        self.reboot_controller = FakeRebootController()
        certificate, private_key = create_test_certificate(self.temp_dir.name)
        self.backup_manager = BackupManager(
            database=self.db,
            hmac_key=b"c" * 32,
            tls_cert=certificate,
            tls_key=private_key,
            public_host="154.9.234.210",
            hysteria_port=19999,
            node_name="私家车-2026",
            work_dir=Path(self.temp_dir.name) / "backup-restore",
        )
        self.application = PanelApplication(
            database=self.db,
            public_host="154.9.234.210",
            hysteria_port=19999,
            pin_sha256="AA:BB:CC",
            stats_client=self.stats,
            node_name="私家车-2026",
            service_controller=self.service_controller,
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
        self.db.create_proxy_user("alice")
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
        self.assertIn('data-label="名称"', body)
        self.assertIn('data-label="操作"', body)
        self.assertIn('@media(max-width:640px)', body)
        self.assertIn('.user-table tr{display:grid;', body)
        self.assertIn('grid-template-columns:repeat(5,minmax(0,1fr))', body)
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
                "inline": "1",
            },
            headers={**headers, "Accept": "application/json"},
        ) as response:
            payload = json.loads(response.read().decode())

        self.assertEqual(200, response.status)
        self.assertEqual("editable", payload["name"])
        self.assertEqual(6, payload["device_limit"])
        self.assertEqual(750, payload["traffic_limit_gb"])
        record = self.db.get_proxy_user(created["id"])
        self.assertEqual(6, record["device_limit"])
        self.assertEqual(750 * 1024**3, record["traffic_limit_bytes"])
        self.assertEqual(original_token, self.db.recover_proxy_token(created["id"]))

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

        newest = '<tr data-user-name="newest" data-over-device-limit="0"><td data-label="名称"><strong>newest</strong>'
        middle = '<tr data-user-name="middle" data-over-device-limit="0"><td data-label="名称"><strong>middle</strong>'
        oldest = '<tr data-user-name="oldest" data-over-device-limit="0"><td data-label="名称"><strong>oldest</strong>'
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
        self.assertIn('aria-label="搜索用户"', body)
        self.assertNotIn('for="user-search">搜索用户', body)
        self.assertLess(body.index('class="user-heading"'), body.index('class="user-search"'))
        self.assertLess(body.index('class="user-search"'), body.index('class="section-actions"'))
        self.assertIn('data-search-status', body)
        self.assertIn('window.requestAnimationFrame(filterUsers)', body)
        self.assertIn('data-dialog-open="create-user-dialog"', body)
        self.assertIn('<dialog id="create-user-dialog"', body)
        self.assertIn('aria-labelledby="create-user-title"', body)
        self.assertIn('class="section-actions"', body)
        self.assertIn('placeholder="例如：Alice 手机" autofocus', body)

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

        beta_row = '<tr data-user-name="beta" data-over-device-limit="0"><td data-label="名称"><strong>beta</strong>'
        gamma_row = '<tr data-user-name="gamma" data-over-device-limit="0"><td data-label="名称"><strong>gamma</strong>'
        alpha_row = '<tr data-user-name="alpha" data-over-device-limit="0"><td data-label="名称"><strong>alpha</strong>'
        self.assertLess(descending.index(beta_row), descending.index(gamma_row))
        self.assertLess(descending.index(gamma_row), descending.index(alpha_row))
        self.assertLess(ascending.index(alpha_row), ascending.index(gamma_row))
        self.assertLess(ascending.index(gamma_row), ascending.index(beta_row))
        self.assertIn('href="/?sort=traffic&amp;order=asc"', descending)

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
        self.assertIn("v0.14.2", body)

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
        self.assertEqual(64, self.server.max_workers)
        self.assertIsNone(self.server.tls_context)

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
        if self.path == "/traffic?clear=true":
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
