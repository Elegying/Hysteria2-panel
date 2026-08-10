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
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hysteria2_panel import (
    BackupManager,
    BackupValidationError,
    ConflictError,
    Database,
    LoginRateLimiter,
    HysteriaStatsClient,
    PanelApplication,
    PanelHandler,
    RestoreController,
    Settings,
    ServiceController,
    SystemMetrics,
    UpdateChecker,
    UsageManager,
    build_connection_uri,
    handle_auth_payload,
    hash_password,
    make_internal_server,
    make_panel_server,
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

    def collect_and_clear(self):
        return self.snapshot()["traffic"]

    def online(self):
        return self.snapshot()["online"]

    def kick(self, name):
        self.kicked.append(name)


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
        stats = PolicyStatsClient(traffic={"alice": {"tx": 100, "rx": 200}})
        manager = UsageManager(self.db, stats)

        manager.collect_once()

        record = self.db.get_proxy_user(user["id"])
        self.assertEqual((100, 200), (record["tx_bytes"], record["rx_bytes"]))
        self.assertEqual(["alice"], stats.kicked)
        self.assertFalse(manager.authorize("alice"))

    def test_reserves_pending_connections_to_enforce_the_limit(self):
        self.db.create_proxy_user("alice", device_limit=3)
        stats = PolicyStatsClient(online={"alice": 2})
        manager = UsageManager(self.db, stats, pending_ttl=10, clock=lambda: 100.0)

        self.assertTrue(manager.authorize("alice"))
        self.assertFalse(manager.authorize("alice"))

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

    def test_system_metrics_reports_cpu_memory_disk_and_uptime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            proc_root = Path(temp_dir)
            (proc_root / "stat").write_text("cpu  100 0 100 800 0 0 0 0\n")
            (proc_root / "meminfo").write_text(
                "MemTotal: 1000 kB\nMemAvailable: 600 kB\n"
            )
            (proc_root / "uptime").write_text("90061.0 0.0\n")
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

        with self.request("/login") as response:
            body = response.read().decode()
            self.assertIn('type="password"', body)
            self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
            self.assertIn("script-src 'nonce-", response.headers["Content-Security-Policy"])

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
            "总上传",
            "总下载",
            "服务控制",
            "系统资源",
            "高流量用户",
            "当前版本",
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

    def test_dashboard_uses_migration_dialog_and_mobile_user_cards(self):
        self.db.create_proxy_user("alice")
        headers, _ = self.authenticated_headers()

        with self.request("/", headers=headers) as response:
            body = response.read().decode()

        self.assertIn('data-dialog-open="migration-dialog"', body)
        self.assertIn('<dialog id="migration-dialog"', body)
        self.assertIn('aria-labelledby="migration-title"', body)
        self.assertIn('data-dialog-close', body)
        self.assertIn('data-label="名称"', body)
        self.assertIn('data-label="操作"', body)
        self.assertIn('@media(max-width:640px)', body)
        self.assertIn('td::before{content:attr(data-label)', body)

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
        self.assertIn('class="detail version-detail"', dashboard)
        self.assertIn('.dashboard-trio{grid-template-columns:', dashboard)
        self.assertIn('.version-detail{margin-top:12px', dashboard)
        self.assertIn('class="login-form"', login)
        self.assertIn('class="login-actions"', login)
        self.assertIn('.login-form{display:grid;gap:12px}', login)

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

    def test_share_and_traffic_reset_actions_are_csrf_protected(self):
        created = self.db.create_proxy_user("carol")
        self.db.add_traffic({"carol": {"tx": 10, "rx": 20}})
        headers, csrf_token = self.authenticated_headers()

        with self.request(
            "/users/{}/share".format(created["id"]),
            {"csrf": csrf_token, "generation": "0"},
            headers=headers,
        ) as response:
            body = response.read().decode()
        self.assertIn("hysteria2://", body)
        self.assertIn('data-copy-target="uri"', body)

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
        self.assertIn("v0.6.1", body)

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
        self.assertEqual(
            {"alice": {"tx": 100, "rx": 200}}, self.client.collect_and_clear()
        )
        self.assertEqual(1, StatsApiHandler.cleared)


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
