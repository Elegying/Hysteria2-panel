import base64
import contextlib
import datetime
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import node_agent
from hy2panel.budgets import budget_period
from hysteria2_panel import Database, sqlite_connection


def public_key(value):
    der = bytes.fromhex("302a300506032b6570032100") + bytes([value]) * 32
    return base64.b64encode(der).decode("ascii")


class NodeOperationsCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "panel.db"
        self.db = Database(self.db_path, b"o" * 32)
        self.db.initialize()
        self.now = 2_000_000_000
        self.node_id = "1" * 32
        with sqlite_connection(str(self.db_path)) as connection:
            connection.execute(
                """INSERT INTO nodes(
                    node_id, name, expected_ip, observed_ip, status, public_key,
                    hostname, platform, architecture, agent_version, created_at,
                    registered_at, last_seen_at, verified_at, verified_by,
                    last_heartbeat_at, last_heartbeat_ip, policy_state,
                    policy_enabled_at, policy_enabled_by, data_plane_state
                ) VALUES (?, '数据节点一', '203.0.113.10', '203.0.113.10',
                    'pending_verification', ?, 'node.example.test', 'linux',
                    'amd64', '0.32.0', ?, ?, ?, ?, 'admin', ?, '203.0.113.10',
                    'protocol_ready', ?, 'admin', 'dns_admitted')""",
                (
                    self.node_id,
                    public_key(1),
                    self.now,
                    self.now,
                    self.now,
                    self.now,
                    self.now,
                    self.now,
                ),
            )

    def tearDown(self):
        self.temp_dir.cleanup()


class NodeBudgetTests(NodeOperationsCase):
    @staticmethod
    def utc_timestamp(year, month, day, hour=0):
        return int(
            datetime.datetime(
                year, month, day, hour, tzinfo=datetime.timezone.utc
            ).timestamp()
        )

    def test_initialize_migrates_existing_budgets_with_compatible_cycle_defaults(self):
        legacy_path = Path(self.temp_dir.name) / "legacy-budget.db"
        with sqlite_connection(str(legacy_path)) as connection:
            connection.execute(
                """CREATE TABLE origin_traffic_budgets (
                    origin_id TEXT PRIMARY KEY,
                    limit_bytes INTEGER NOT NULL,
                    warning_percent INTEGER NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )"""
            )
            connection.execute(
                "INSERT INTO origin_traffic_budgets VALUES (?, 1000, 80, 'admin', ?)",
                ("local:" + "b" * 32, self.now),
            )

        legacy_db = Database(legacy_path, b"p" * 32)
        legacy_db.initialize()

        with sqlite_connection(str(legacy_path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM origin_traffic_budgets"
            ).fetchone()
        self.assertEqual(1, row["reset_day"])
        self.assertEqual(0, row["manual_used_bytes"])
        self.assertEqual(0, row["baseline_total_bytes"])
        self.assertIsNone(row["baseline_at"])

    def test_local_budget_uses_only_new_idempotent_monthly_deltas(self):
        self.db.create_proxy_user("alice", token="t" * 32)
        origin_id = "local:" + "a" * 32
        with mock.patch("hysteria2_panel.time.time", return_value=self.now):
            self.assertTrue(
                self.db.apply_traffic_batch(
                    "a" * 32,
                    {"alice": {"tx": 600, "rx": 300}},
                    origin_id=origin_id,
                    origin_kind="local",
                    origin_name="面板本机",
                )
            )
            self.assertFalse(
                self.db.apply_traffic_batch(
                    "a" * 32,
                    {"alice": {"tx": 600, "rx": 300}},
                    origin_id=origin_id,
                    origin_kind="local",
                    origin_name="面板本机",
                )
            )
        self.db.set_origin_budget(origin_id, 1000, 80, "admin", self.now)

        budget = self.db.get_origin_budget(origin_id, self.now)

        self.assertEqual(900, budget["used_bytes"])
        self.assertEqual("warning", budget["status"])
        self.assertEqual(90.0, budget["percent"])
        self.assertEqual("2033-05", budget["period"])

    def test_remote_budget_is_idempotent_and_next_month_starts_at_zero(self):
        self.db.create_proxy_user("alice", token="u" * 32)
        with sqlite_connection(str(self.db_path)) as connection:
            connection.execute(
                """INSERT INTO usage_origins(
                    origin_id, kind, node_id, display_name, created_at, last_traffic_at
                ) VALUES (?, 'remote', ?, '数据节点一', ?, ?)""",
                ("node:" + self.node_id, self.node_id, self.now, self.now),
            )
            connection.execute(
                """INSERT INTO origin_traffic_daily(
                    origin_id, usage_date, tx_bytes, rx_bytes, updated_at
                ) VALUES (?, '2033-05-18', 400, 600, ?)""",
                ("node:" + self.node_id, self.now),
            )
        self.db.set_origin_budget(
            "node:" + self.node_id, 1000, 80, "admin", self.now
        )

        current = self.db.get_origin_budget("node:" + self.node_id, self.now)
        following = self.db.get_origin_budget(
            "node:" + self.node_id, 2_002_665_600
        )

        self.assertEqual("exhausted", current["status"])
        self.assertEqual(1000, current["used_bytes"])
        self.assertEqual(0, following["used_bytes"])
        self.assertEqual("normal", following["status"])

    def test_manual_used_baseline_adds_only_traffic_recorded_after_save(self):
        self.db.create_proxy_user("baseline", token="b" * 32)
        origin_id = "local:" + "c" * 32
        saved_at = self.utc_timestamp(2033, 5, 18, 12)
        with mock.patch("hysteria2_panel.time.time", return_value=saved_at - 60):
            self.db.apply_traffic_batch(
                "c" * 32,
                {"baseline": {"tx": 700, "rx": 300}},
                origin_id=origin_id,
                origin_kind="local",
                origin_name="面板本机",
            )
        self.db.set_origin_budget(
            origin_id,
            20_000,
            80,
            "admin",
            saved_at,
            manual_used_bytes=5_000,
            reset_day=15,
        )
        with mock.patch("hysteria2_panel.time.time", return_value=saved_at + 60):
            self.db.apply_traffic_batch(
                "d" * 32,
                {"baseline": {"tx": 200, "rx": 100}},
                origin_id=origin_id,
                origin_kind="local",
                origin_name="面板本机",
            )

        budget = self.db.get_origin_budget(origin_id, saved_at + 120)

        self.assertEqual(5_300, budget["used_bytes"])
        self.assertEqual(5_000, budget["manual_used_bytes"])
        self.assertEqual(15, budget["reset_day"])
        self.assertEqual("2033-05-15", budget["period_start"])
        self.assertEqual("2033-06-15", budget["next_reset_date"])

    def test_manual_baseline_waterline_is_atomic_with_concurrent_traffic(self):
        self.db.create_proxy_user("atomic", token="a" * 32)
        origin_id = "local:" + "9" * 32
        saved_at = self.utc_timestamp(2033, 5, 18, 12)
        baseline_read = threading.Event()
        traffic_started = threading.Event()
        failures = []
        original_connect = self.db._connect

        @contextlib.contextmanager
        def gated_connect():
            with original_connect() as connection:
                class ConnectionProxy:
                    def execute(self, statement, parameters=()):
                        if "SELECT COALESCE(SUM(tx_bytes + rx_bytes), 0)" in statement:
                            baseline_read.set()
                            if not traffic_started.wait(2):
                                raise AssertionError("concurrent traffic did not start")
                            time.sleep(0.1)
                        return connection.execute(statement, parameters)

                    def __getattr__(self, name):
                        return getattr(connection, name)

                yield ConnectionProxy()

        def save_budget():
            try:
                self.db.set_origin_budget(
                    origin_id,
                    20_000,
                    80,
                    "admin",
                    saved_at,
                    manual_used_bytes=5_000,
                    reset_day=15,
                )
            except Exception as exc:  # pragma: no cover - surfaced below
                failures.append(exc)

        def add_concurrent_traffic():
            try:
                if not baseline_read.wait(2):
                    raise AssertionError("baseline read did not start")
                traffic_started.set()
                with mock.patch("hysteria2_panel.time.time", return_value=saved_at + 1):
                    self.db.apply_traffic_batch(
                        "9" * 32,
                        {"atomic": {"tx": 200, "rx": 100}},
                        origin_id=origin_id,
                        origin_kind="local",
                        origin_name="面板本机",
                    )
            except Exception as exc:  # pragma: no cover - surfaced below
                failures.append(exc)

        with mock.patch.object(self.db, "_connect", gated_connect):
            saver = threading.Thread(target=save_budget)
            traffic = threading.Thread(target=add_concurrent_traffic)
            saver.start()
            traffic.start()
            saver.join(5)
            traffic.join(5)

        self.assertFalse(saver.is_alive())
        self.assertFalse(traffic.is_alive())
        self.assertEqual([], failures)
        self.assertEqual(
            5_300,
            self.db.get_origin_budget(origin_id, saved_at + 60)["used_bytes"],
        )

    def test_editing_manual_used_reanchors_without_counting_old_delta_twice(self):
        self.db.create_proxy_user("reanchor", token="r" * 32)
        origin_id = "node:" + self.node_id
        first_save = self.utc_timestamp(2033, 5, 18, 10)
        with mock.patch("hysteria2_panel.time.time", return_value=first_save - 60):
            self.db.apply_traffic_batch(
                "e" * 32,
                {"reanchor": {"tx": 1_000, "rx": 0}},
                origin_id=origin_id,
                origin_kind="remote",
                origin_name="数据节点一",
            )
        self.db.set_origin_budget(
            origin_id, 20_000, 80, "admin", first_save,
            manual_used_bytes=5_000, reset_day=1,
        )
        with mock.patch("hysteria2_panel.time.time", return_value=first_save + 60):
            self.db.apply_traffic_batch(
                "f" * 32,
                {"reanchor": {"tx": 300, "rx": 0}},
                origin_id=origin_id,
                origin_kind="remote",
                origin_name="数据节点一",
            )
        self.db.set_origin_budget(
            origin_id, 20_000, 80, "admin", first_save + 120,
            manual_used_bytes=7_000, reset_day=1,
        )
        with mock.patch("hysteria2_panel.time.time", return_value=first_save + 180):
            self.db.apply_traffic_batch(
                "1" * 32,
                {"reanchor": {"tx": 200, "rx": 0}},
                origin_id=origin_id,
                origin_kind="remote",
                origin_name="数据节点一",
            )

        budget = self.db.get_origin_budget(origin_id, first_save + 240)

        self.assertEqual(7_200, budget["used_bytes"])

    def test_manual_baseline_expires_at_custom_reset_and_new_cycle_uses_ledger(self):
        self.db.create_proxy_user("cycle", token="y" * 32)
        origin_id = "local:" + "d" * 32
        saved_at = self.utc_timestamp(2033, 5, 18, 12)
        self.db.set_origin_budget(
            origin_id, 20_000, 80, "admin", saved_at,
            manual_used_bytes=9_000, reset_day=19,
        )
        after_reset = self.utc_timestamp(2033, 5, 19, 1)
        with mock.patch("hysteria2_panel.time.time", return_value=after_reset):
            self.db.apply_traffic_batch(
                "2" * 32,
                {"cycle": {"tx": 250, "rx": 50}},
                origin_id=origin_id,
                origin_kind="local",
                origin_name="面板本机",
            )

        budget = self.db.get_origin_budget(origin_id, after_reset + 60)

        self.assertEqual(300, budget["used_bytes"])
        self.assertEqual("2033-05-19", budget["period_start"])
        self.assertEqual("2033-06-19", budget["period_end"])

    def test_reset_day_31_clamps_to_month_end_without_drifting(self):
        origin_id = "local:" + "e" * 32
        february = self.utc_timestamp(2024, 2, 28, 12)
        self.db.set_origin_budget(
            origin_id, 20_000, 80, "admin", february,
            manual_used_bytes=400, reset_day=31,
        )

        before_reset = self.db.get_origin_budget(origin_id, february)
        after_reset = self.db.get_origin_budget(
            origin_id, self.utc_timestamp(2024, 2, 29, 1)
        )

        self.assertEqual("2024-01-31", before_reset["period_start"])
        self.assertEqual("2024-02-29", before_reset["next_reset_date"])
        self.assertEqual(400, before_reset["used_bytes"])
        self.assertEqual("2024-02-29", after_reset["period_start"])
        self.assertEqual("2024-03-31", after_reset["next_reset_date"])
        self.assertEqual(0, after_reset["used_bytes"])

    def test_reset_days_29_30_and_31_each_clamp_against_the_current_month(self):
        cases = (
            ((2023, 2, 28, 12), 31, "2023-02-28", "2023-03-31"),
            ((2024, 2, 29, 12), 30, "2024-02-29", "2024-03-30"),
            ((2024, 4, 30, 12), 31, "2024-04-30", "2024-05-31"),
        )
        for timestamp_parts, reset_day, expected_start, expected_end in cases:
            with self.subTest(reset_day=reset_day, timestamp=timestamp_parts):
                start, end = budget_period(
                    self.utc_timestamp(*timestamp_parts), reset_day
                )
                self.assertEqual(expected_start, start.strftime("%Y-%m-%d"))
                self.assertEqual(expected_end, end.strftime("%Y-%m-%d"))

    def test_unattributed_history_cleanup_does_not_touch_users_or_assigned_origins(self):
        created = self.db.create_proxy_user("cleanup", token="z" * 32)
        local_origin = "local:" + "f" * 32
        with mock.patch("hysteria2_panel.time.time", return_value=self.now):
            self.db.apply_traffic_batch(
                "3" * 32, {"cleanup": {"tx": 100, "rx": 50}}
            )
            self.db.apply_traffic_batch(
                "4" * 32,
                {"cleanup": {"tx": 30, "rx": 20}},
                origin_id=local_origin,
                origin_kind="local",
                origin_name="面板本机",
            )
        before_user = self.db.get_proxy_user(created["id"])

        deleted = self.db.delete_unattributed_history()
        repeated = self.db.delete_unattributed_history()

        after_user = self.db.get_proxy_user(created["id"])
        origins = {row["origin_id"]: row for row in self.db.list_usage_origins()}
        self.assertEqual({"origins": 1, "users": 1, "daily": 1}, deleted)
        self.assertEqual({"origins": 0, "users": 0, "daily": 0}, repeated)
        self.assertEqual(
            (before_user["tx_bytes"], before_user["rx_bytes"]),
            (after_user["tx_bytes"], after_user["rx_bytes"]),
        )
        self.assertNotIn("legacy-unattributed", origins)
        self.assertEqual((30, 20), (origins[local_origin]["tx_bytes"], origins[local_origin]["rx_bytes"]))
        with sqlite_connection(str(self.db_path)) as connection:
            assigned_daily = connection.execute(
                "SELECT tx_bytes, rx_bytes FROM origin_traffic_daily WHERE origin_id = ?",
                (local_origin,),
            ).fetchone()
        self.assertEqual((30, 20), assigned_daily)

    def test_user_counter_reset_does_not_erase_machine_bandwidth_budget_usage(self):
        with sqlite_connection(str(self.db_path)) as connection:
            connection.execute(
                """INSERT INTO origin_traffic_daily(
                    origin_id, usage_date, tx_bytes, rx_bytes, updated_at
                ) VALUES (?, '2033-05-18', 1, 2, ?)""",
                ("node:" + self.node_id, self.now),
            )

        self.db.reset_all_traffic()

        with sqlite_connection(str(self.db_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM origin_traffic_daily"
            ).fetchone()[0]
        self.assertEqual(1, count)

    def test_budget_status_counts_are_bounded_and_include_local_and_remote(self):
        local_origin_id = "local:" + "a" * 32
        with sqlite_connection(str(self.db_path)) as connection:
            connection.executemany(
                """INSERT INTO origin_traffic_daily(
                    origin_id, usage_date, tx_bytes, rx_bytes, updated_at
                ) VALUES (?, '2033-05-18', ?, 0, ?)""",
                (
                    (local_origin_id, 850, self.now),
                    ("node:" + self.node_id, 1000, self.now),
                ),
            )
        self.db.set_origin_budget(local_origin_id, 1000, 80, "admin", self.now)
        self.db.set_origin_budget(
            "node:" + self.node_id, 1000, 80, "admin", self.now
        )

        counts = self.db.origin_budget_status_counts(self.now)

        self.assertEqual(
            {"disabled": 0, "normal": 0, "warning": 1, "exhausted": 1},
            counts,
        )


class NodeLifecycleTests(NodeOperationsCase):
    def make_zero_fresh_snapshot(self):
        with sqlite_connection(str(self.db_path)) as connection:
            connection.execute(
                """INSERT INTO node_online_snapshots(
                    node_id, snapshot_id, sequence, observed_at,
                    traffic_acked_at, accepted_at
                ) VALUES (?, ?, 1, ?, ?, ?)""",
                (self.node_id, "2" * 32, self.now, self.now, self.now),
            )

    def test_safe_stop_requires_drain_dns_removal_and_fresh_zero_online(self):
        with self.assertRaises(ValueError):
            self.db.request_node_stop(
                self.node_id, "admin", self.now, dns_removed_verified=False
            )
        self.assertTrue(self.db.begin_node_drain(self.node_id, "admin", self.now))
        with self.assertRaises(ValueError):
            self.db.request_node_stop(
                self.node_id, "admin", self.now, dns_removed_verified=False
            )
        self.make_zero_fresh_snapshot()

        command = self.db.request_node_stop(
            self.node_id, "admin", self.now, dns_removed_verified=True
        )

        self.assertEqual("STOP_DATA_PLANE", command["kind"])
        node = self.db.list_nodes()[0]
        self.assertEqual("stopping", node["lifecycle_state"])

    def test_stop_ack_and_resume_ack_advance_lifecycle_without_deleting_identity(self):
        self.db.begin_node_drain(self.node_id, "admin", self.now)
        self.make_zero_fresh_snapshot()
        stop = self.db.request_node_stop(
            self.node_id, "admin", self.now, dns_removed_verified=True
        )
        self.assertTrue(
            self.db.ack_node_command(
                self.node_id, stop["commandId"], True, "", "3" * 64, self.now
            )
        )
        stopped = self.db.list_nodes()[0]
        self.assertEqual("stopped", stopped["lifecycle_state"])
        self.assertEqual(public_key(1), stopped["public_key"])

        resume = self.db.request_node_resume(self.node_id, "admin", self.now + 1)
        self.assertEqual("START_DATA_PLANE", resume["kind"])
        self.assertTrue(
            self.db.ack_node_command(
                self.node_id,
                resume["commandId"],
                True,
                "",
                "4" * 64,
                self.now + 1,
            )
        )
        active = self.db.list_nodes()[0]
        self.assertEqual("active", active["lifecycle_state"])
        self.assertEqual("direct_canary_passed", active["data_plane_state"])

    def test_control_executor_uses_only_fixed_callbacks(self):
        stop = mock.Mock()
        start = mock.Mock()
        flush = mock.Mock()
        state = mock.Mock()
        state.data_plane_stopped.return_value = False

        node_agent.execute_control_command(
            {"commandId": "5" * 32, "kind": "STOP_DATA_PLANE", "payload": {}},
            mock.Mock(),
            flush_traffic=flush,
            protocol_state=state,
            stop_data_plane=stop,
            start_data_plane=start,
        )

        flush.assert_called_once_with()
        state.set_data_plane_stopped.assert_called_once_with(True)
        stop.assert_called_once_with()
        start.assert_not_called()

    def test_stop_retry_skips_unavailable_stats_after_the_stop_marker(self):
        stop = mock.Mock()
        flush = mock.Mock()
        state = mock.Mock()
        state.data_plane_stopped.return_value = True

        node_agent.execute_control_command(
            {"commandId": "6" * 32, "kind": "STOP_DATA_PLANE", "payload": {}},
            mock.Mock(),
            flush_traffic=flush,
            protocol_state=state,
            stop_data_plane=stop,
        )

        flush.assert_not_called()
        state.set_data_plane_stopped.assert_not_called()
        stop.assert_called_once_with()

    def test_stopping_node_cannot_start_a_new_authentication(self):
        user = self.db.create_proxy_user("alice", token="v" * 32)
        with sqlite_connection(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE nodes SET lifecycle_state = 'stopping' WHERE node_id = ?",
                (self.node_id,),
            )

        decision = self.db.authorize_distributed_node(
            self.node_id,
            "7" * 32,
            user["token"],
            False,
            {},
            "8" * 64,
            self.now,
            5,
        )

        self.assertIsNone(decision)
