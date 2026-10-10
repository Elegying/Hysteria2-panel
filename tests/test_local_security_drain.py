"""Local credential rotation drains every old connection across panel restarts."""

import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest import mock

import hysteria2_panel as panel
from tests import test_panel as panel_tests


class LocalStats:
    def __init__(self):
        self.connected = 3
        self.marked = False
        self.used = 0
        self.kicks = 0
        self.fail = False

    def online(self):
        return {"rotation-probe": self.connected}

    def dump_streams(self):
        return []

    def kick(self, name):
        self.kick_many([name])

    def kick_many(self, names):
        if "rotation-probe" in names and self.connected:
            if self.fail:
                raise OSError("stats unavailable")
            self.marked = True
            self.kicks += 1

    def transfer(self):
        if self.marked:
            self.connected -= 1
            self.marked = False
        self.used += self.connected * 100

    def collect_and_clear(self):
        amount, self.used = self.used, 0
        return {"rotation-probe": {"tx": amount, "rx": 0}}


class LocalSecurityDrainTests(unittest.TestCase):
    def setUp(self):
        self.fixture = panel_tests.PanelHttpTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        self.now = [int(time.time())]
        self.stats = LocalStats()
        self.fixture.application.stats_client = self.stats
        self.user = self.db.create_proxy_user("rotation-probe", device_limit=10)
        self.manager = self.restart_manager()

    def restart_manager(self):
        database = panel.Database(self.db.path, self.db.hmac_key)
        database.initialize()
        manager = panel.UsageManager(database, self.stats, wall_clock=lambda: self.now[0])
        self.fixture.application.usage_manager = manager
        return manager

    def drain(self):
        return next(row for row in self.db.list_proxy_users_for_usage()
                    if row["id"] == self.user["id"])["local_drain_started_at"]

    def rotate_mobile(self):
        session = self.db.create_mobile_session(self.fixture.admin_id, "rotation-device", "Audit")
        with mock.patch("hysteria2_panel.time.time", return_value=self.now[0]):
            status, _ = self.fixture.mobile_json_request(
                "POST", "/api/v1/mobile/users/{}/rotate-secret".format(self.user["id"]),
                {"generation": 0}, session["accessToken"],
            )
        self.assertEqual(200, status)

    def test_mobile_rotation_drains_three_connections_and_resumes_after_restart(self):
        self.rotate_mobile()
        new_token = self.db.recover_proxy_token(self.user["id"])
        body = json.dumps({"auth": new_token}).encode()
        self.assertIsNone(self.db.authenticate_token(self.user["token"]))
        self.assertFalse(panel.handle_auth_payload(self.db, body, self.manager)[1]["ok"])
        other = self.db.create_proxy_user("other")
        self.assertTrue(self.db.authorize_local_participant(other["name"], {}, self.now[0]))
        for remaining in (2, 1, 0):
            self.stats.transfer()
            self.manager.collect_once()
            self.assertEqual(remaining, self.stats.connected)
        self.assertEqual(3, self.stats.kicks)
        self.assertIsNotNone(self.drain())
        self.manager = self.restart_manager()
        self.now[0] += 10
        self.manager.collect_once()
        self.assertFalse(panel.handle_auth_payload(self.db, body, self.manager)[1]["ok"])
        self.now[0] += 1
        self.manager.collect_once()
        self.assertIsNone(self.drain())
        self.assertTrue(panel.handle_auth_payload(self.db, body, self.manager)[1]["ok"])

    def test_web_rotation_retains_recovery_when_the_initial_kick_fails(self):
        self.stats.fail = True
        headers, csrf = self.fixture.authenticated_headers()
        with mock.patch("hysteria2_panel.time.time", return_value=self.now[0]):
            with self.fixture.request(
                "/users/{}/rotate".format(self.user["id"]),
                {"csrf": csrf, "generation": "0"}, headers=headers,
            ) as response:
                self.assertEqual(200, response.status)
                self.assertIn("hysteria2://", response.read().decode())
        self.assertIsNotNone(self.drain())
        self.manager = self.restart_manager()
        self.stats.fail = False
        self.now[0] += 11
        for _ in range(3):
            self.manager.collect_once()
            self.assertIsNotNone(self.drain())
            self.stats.transfer()
        self.manager.collect_once()
        self.assertEqual(0, self.stats.connected)
        self.assertIsNone(self.drain())

    def test_old_completion_cannot_clear_a_second_rotation_in_the_same_second(self):
        self.rotate_mobile()
        started = self.drain()
        with mock.patch("hysteria2_panel.time.time", return_value=self.now[0]):
            self.db.rotate_proxy_token(self.user["id"], expected_generation=1, drain_local=True)
        self.db.finish_local_user_drain(self.user["id"], 1, started)
        self.assertEqual(started, self.drain())
        with self.assertRaises(panel.ConflictError):
            self.db.rotate_proxy_token(self.user["id"], expected_generation=1, drain_local=True)
        self.assertEqual(2, self.db.get_proxy_user(self.user["id"])["generation"])
        self.assertEqual(started, self.drain())

    def test_legacy_schema_migration_preserves_the_existing_identity(self):
        path = Path(self.fixture.temp_dir.name) / "legacy-drain.db"
        with sqlite3.connect(str(path)) as connection:
            connection.execute("""CREATE TABLE proxy_users (
                id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE,
                token_fingerprint TEXT UNIQUE, enabled INTEGER,
                created_at INTEGER, updated_at INTEGER)""")
            connection.execute("INSERT INTO proxy_users VALUES (1, ?, ?, 1, 1, 1)",
                               ("legacy", self.db._fingerprint("synthetic-legacy-token")))
        migrated = panel.Database(path, self.db.hmac_key)
        migrated.initialize()
        self.assertEqual("legacy", migrated.authenticate_token("synthetic-legacy-token"))
        self.assertIsNone(migrated.list_proxy_users_for_usage()[0]["local_drain_started_at"])
