import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import node_agent
from hysteria2_panel import Database


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
        with sqlite3.connect(str(self.db_path)) as connection:
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
        with sqlite3.connect(str(self.db_path)) as connection:
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

    def test_user_counter_reset_does_not_erase_machine_bandwidth_budget_usage(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """INSERT INTO origin_traffic_daily(
                    origin_id, usage_date, tx_bytes, rx_bytes, updated_at
                ) VALUES (?, '2033-05-18', 1, 2, ?)""",
                ("node:" + self.node_id, self.now),
            )

        self.db.reset_all_traffic()

        with sqlite3.connect(str(self.db_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM origin_traffic_daily"
            ).fetchone()[0]
        self.assertEqual(1, count)

    def test_budget_status_counts_are_bounded_and_include_local_and_remote(self):
        local_origin_id = "local:" + "a" * 32
        with sqlite3.connect(str(self.db_path)) as connection:
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
        with sqlite3.connect(str(self.db_path)) as connection:
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
        with sqlite3.connect(str(self.db_path)) as connection:
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
