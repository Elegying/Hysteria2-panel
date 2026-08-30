import base64
import json
import os
import socket
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import node_agent
from hy2panel.distributed import (
    DistributedControlService,
    MAX_STATE_AGE_SECONDS,
    NodeRequestRejected,
    canonical_node_request,
)
from hy2panel.nodes import OpenSSLSignatureVerifier
from hysteria2_panel import Database, UsageManager


def public_key(value):
    der = bytes.fromhex("302a300506032b6570032100") + bytes([value]) * 32
    return base64.b64encode(der).decode("ascii")


def nonce(value):
    return base64.urlsafe_b64encode(bytes([value]) * 32).rstrip(b"=").decode("ascii")


class DistributedControlCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "panel.db"
        self.db = Database(self.db_path, b"d" * 32)
        self.db.initialize()
        self.now = [2_000_000_000]
        self.local_online = {}
        self.local_available = True
        self.service = DistributedControlService(
            self.db,
            clock=lambda: self.now[0],
            signature_verifier=lambda _key, _message, _signature: True,
            local_state_provider=self.local_state,
        )
        self.nodes = [self.create_ready_node(index) for index in (1, 2)]

    def tearDown(self):
        self.temp_dir.cleanup()

    def local_state(self):
        if not self.local_available:
            raise OSError("local stats unavailable")
        return {
            "online": dict(self.local_online),
            "observedAt": self.now[0],
            "trafficAckedAt": self.now[0],
        }

    def create_ready_node(self, value):
        node_id = "{:032x}".format(value)
        current = self.now[0]
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """INSERT INTO nodes(
                    node_id, name, expected_ip, observed_ip, status, public_key,
                    hostname, platform, architecture, agent_version, created_at,
                    registered_at, last_seen_at, verified_at, verified_by,
                    last_heartbeat_at, last_heartbeat_ip, policy_state,
                    policy_enabled_at, policy_enabled_by
                ) VALUES (?, ?, ?, ?, 'pending_verification', ?, ?, 'linux',
                    'amd64', '0.26.0', ?, ?, ?, ?, 'admin', ?, ?,
                    'protocol_ready', ?, 'admin')""",
                (
                    node_id,
                    "node-{}".format(value),
                    "203.0.113.{}".format(value),
                    "203.0.113.{}".format(value),
                    public_key(value),
                    "node-{}.example.test".format(value),
                    current,
                    current,
                    current,
                    current,
                    current,
                    "203.0.113.{}".format(value),
                    current,
                ),
            )
        return node_id

    def common(self, node_id, value):
        return {
            "nodeId": node_id,
            "sentAt": self.now[0],
            "nonce": nonce(value),
            "signature": base64.b64encode(b"s" * 64).decode("ascii"),
        }

    def snapshot(self, node_id, value, sequence=1, online=None, **changes):
        payload = self.common(node_id, value)
        payload.update(
            {
                "snapshotId": "{:032x}".format(value),
                "sequence": sequence,
                "observedAt": self.now[0],
                "trafficAckedAt": self.now[0],
                "online": online or {},
            }
        )
        payload.update(changes)
        return payload

    def accept_empty_snapshots(self):
        for index, node_id in enumerate(self.nodes, 10):
            self.service.accept_online_snapshot(
                self.snapshot(node_id, index),
                remote_ip="203.0.113.{}".format(int(node_id, 16)),
            )


class SignedNodeRequestTests(DistributedControlCase):
    def test_canonical_request_is_domain_separated_sorted_and_excludes_signature(self):
        payload = self.snapshot(self.nodes[0], 7)
        message = canonical_node_request("online", payload)
        self.assertTrue(message.startswith(b"hy2panel-node-online-v1\n{"))
        self.assertNotIn(b"signature", message)
        self.assertIn(b'"nodeId":"00000000000000000000000000000001"', message)

    def test_standby_wrong_ip_bad_signature_and_replay_fail_closed(self):
        payload = self.snapshot(self.nodes[0], 8)
        self.service.accept_online_snapshot(payload, remote_ip="203.0.113.1")
        with self.assertRaises(NodeRequestRejected):
            self.service.accept_online_snapshot(payload, remote_ip="203.0.113.1")
        with self.assertRaises(NodeRequestRejected):
            self.service.accept_online_snapshot(
                self.snapshot(self.nodes[1], 9), remote_ip="203.0.113.99"
            )
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE nodes SET policy_state = 'standby' WHERE node_id = ?",
                (self.nodes[1],),
            )
        with self.assertRaises(NodeRequestRejected):
            self.service.accept_online_snapshot(
                self.snapshot(self.nodes[1], 10), remote_ip="203.0.113.2"
            )

    def test_control_cycle_batches_accounting_snapshot_and_command_poll(self):
        self.db.create_proxy_user("alice")
        command = self.db.queue_node_command(
            self.nodes[0], "REFRESH_SNAPSHOT", {}, self.now[0]
        )
        payload = self.common(self.nodes[0], 91)
        payload.update(
            {
                "cycleId": "9" * 32,
                "trafficBatches": [
                    {
                        "batchId": "8" * 32,
                        "observedAt": self.now[0],
                        "traffic": {"alice": {"tx": 10, "rx": 20}},
                    }
                ],
                "onlineSnapshot": {
                    "snapshotId": "7" * 32,
                    "sequence": 1,
                    "observedAt": self.now[0],
                    "trafficAckedAt": self.now[0] - MAX_STATE_AGE_SECONDS - 1,
                    "online": {"alice": 1},
                },
                "commandPoll": {"requestId": "6" * 32},
            }
        )

        result = self.service.control_cycle(payload, remote_ip="203.0.113.1")

        self.assertEqual("9" * 32, result["cycleId"])
        self.assertEqual("8" * 32, result["traffic"][0]["batchId"])
        self.assertTrue(result["traffic"][0]["committed"])
        self.assertEqual(1, result["online"]["sequence"])
        self.assertEqual(command["commandId"], result["commands"][0]["commandId"])
        with sqlite3.connect(str(self.db_path)) as connection:
            counters = connection.execute(
                "SELECT tx_bytes, rx_bytes FROM proxy_users WHERE name = 'alice'"
            ).fetchone()
        self.assertEqual((10, 20), counters)
        self.assertEqual({"alice": 1}, self.db.node_online_counts(self.nodes[0]))
        with self.assertRaises(NodeRequestRejected):
            self.service.control_cycle(payload, remote_ip="203.0.113.1")


class OnlineSnapshotTests(DistributedControlCase):
    def test_snapshot_replaces_counts_monotonically_and_exposes_freshness(self):
        user = self.db.create_proxy_user("alice")
        first = self.snapshot(self.nodes[0], 11, online={"alice": 2})
        result = self.service.accept_online_snapshot(first, remote_ip="203.0.113.1")
        self.assertEqual(1, result["sequence"])
        second = self.snapshot(
            self.nodes[0], 12, sequence=2, online={"alice": 1}
        )
        self.service.accept_online_snapshot(second, remote_ip="203.0.113.1")
        self.assertEqual({"alice": 1}, self.db.node_online_counts(self.nodes[0]))
        self.assertEqual("alice", user["name"])
        with self.assertRaises(NodeRequestRejected):
            self.service.accept_online_snapshot(
                self.snapshot(self.nodes[0], 13, sequence=2),
                remote_ip="203.0.113.1",
            )

    def test_stale_checkpoint_unknown_user_and_invalid_counts_are_rejected(self):
        cases = (
            self.snapshot(
                self.nodes[0],
                14,
                observedAt=self.now[0] - MAX_STATE_AGE_SECONDS - 1,
            ),
            self.snapshot(
                self.nodes[0],
                15,
                trafficAckedAt=self.now[0] - MAX_STATE_AGE_SECONDS - 1,
            ),
            self.snapshot(self.nodes[0], 16, online={"unknown": 1}),
            self.snapshot(self.nodes[0], 17, online={"bad": -1}),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(NodeRequestRejected):
                    self.service.accept_online_snapshot(
                        payload, remote_ip="203.0.113.1"
                    )

    def test_snapshot_within_bounded_control_retry_budget_is_accepted(self):
        delayed = self.snapshot(
            self.nodes[0],
            18,
            observedAt=self.now[0] - 40,
            trafficAckedAt=self.now[0] - 40,
        )

        result = self.service.accept_online_snapshot(
            delayed, remote_ip="203.0.113.1"
        )

        self.assertEqual(1, result["sequence"])

    def test_dashboard_snapshot_combines_fresh_machine_online_counts_and_labels_stale(self):
        self.db.create_proxy_user("alice")
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[0], 19, online={"alice": 2}),
            remote_ip="203.0.113.1",
        )
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[1], 20, online={"alice": 3}),
            remote_ip="203.0.113.2",
        )

        class LocalStats:
            def collect_and_clear(self):
                return {}

            def online(self):
                return {"alice": 1}

        manager = UsageManager(
            self.db,
            LocalStats(),
            local_origin_id="local:" + "9" * 32,
            local_origin_name="面板本机",
            wall_clock=lambda: self.now[0],
        )
        fresh = manager.snapshot()
        origins = {row["origin_id"]: row for row in fresh["machine_stats"]["origins"]}

        self.assertEqual({"alice": 6}, fresh["online"])
        self.assertTrue(fresh["online_complete"])
        self.assertEqual(1, origins["local:" + "9" * 32]["online_devices"])
        self.assertEqual(2, origins["node:" + self.nodes[0]]["online_devices"])
        self.assertEqual("fresh", origins["node:" + self.nodes[0]]["online_state"])

        self.now[0] += MAX_STATE_AGE_SECONDS + 1
        stale = manager.snapshot()
        origins = {row["origin_id"]: row for row in stale["machine_stats"]["origins"]}
        self.assertEqual({"alice": 1}, stale["online"])
        self.assertFalse(stale["online_complete"])
        self.assertTrue(stale["machine_stats"]["has_stale_online"])
        self.assertIsNone(origins["node:" + self.nodes[0]]["online_devices"])
        self.assertEqual(2, origins["node:" + self.nodes[0]]["last_known_online_devices"])
        self.assertEqual("stale", origins["node:" + self.nodes[0]]["online_state"])


class DistributedAuthorizationTests(DistributedControlCase):
    def setUp(self):
        super().setUp()
        created = self.db.create_proxy_user("alice", device_limit=3)
        self.token = created["token"]
        self.accept_empty_snapshots()

    def auth_payload(self, node_id, value, request_id=None):
        payload = self.common(node_id, value)
        payload.update(
            {
                "requestId": request_id or "{:032x}".format(value),
                "entrypoint": "main",
                "auth": self.token,
                "tx": 1024,
            }
        )
        return payload

    def test_two_nodes_concurrently_allow_exactly_the_remaining_device_limit(self):
        barrier = threading.Barrier(5)
        results = []

        def authorize(index):
            node_id = self.nodes[index % 2]
            barrier.wait()
            result = self.service.authorize(
                self.auth_payload(node_id, 30 + index),
                remote_ip="203.0.113.{}".format((index % 2) + 1),
            )
            results.append(result["ok"])

        workers = [threading.Thread(target=authorize, args=(index,)) for index in range(4)]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertEqual([False, True, True, True], sorted(results))

    def test_request_id_is_idempotent_and_stale_state_or_local_failure_denies(self):
        request_id = "f" * 32
        first = self.service.authorize(
            self.auth_payload(self.nodes[0], 40, request_id=request_id),
            remote_ip="203.0.113.1",
        )
        second = self.service.authorize(
            self.auth_payload(self.nodes[0], 41, request_id=request_id),
            remote_ip="203.0.113.1",
        )
        self.assertEqual(first, second)
        self.now[0] += MAX_STATE_AGE_SECONDS + 1
        with self.assertRaises(NodeRequestRejected):
            self.service.authorize(
                self.auth_payload(self.nodes[1], 42), remote_ip="203.0.113.2"
            )
        self.now[0] -= 6
        self.local_available = False
        with self.assertRaises(NodeRequestRejected):
            self.service.authorize(
                self.auth_payload(self.nodes[1], 43), remote_ip="203.0.113.2"
            )

    def test_auth_accepts_snapshots_within_bounded_control_retry_budget(self):
        self.now[0] += 40

        result = self.service.authorize(
            self.auth_payload(self.nodes[0], 44), remote_ip="203.0.113.1"
        )

        self.assertTrue(result["ok"])

    def test_new_panel_runtime_epoch_invalidates_persisted_auth_and_snapshot_leases(self):
        request_id = "e" * 32
        allowed = self.service.authorize(
            self.auth_payload(self.nodes[0], 45, request_id=request_id),
            remote_ip="203.0.113.1",
        )
        self.assertTrue(allowed["ok"])
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE proxy_users SET tx_bytes = 123, rx_bytes = 456 WHERE name = 'alice'"
            )
            connection.execute(
                """INSERT INTO local_auth_leases(
                    decision_id, user_name, created_at, expires_at
                ) VALUES (?, 'alice', ?, ?)""",
                ("d" * 32, self.now[0], self.now[0] + 5),
            )

        self.db.begin_runtime_epoch()

        with sqlite3.connect(str(self.db_path)) as connection:
            self.assertEqual(
                (0, 0, 0, 0),
                tuple(
                    connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                    for table in (
                        "node_online_snapshots",
                        "node_online_counts",
                        "node_auth_decisions",
                        "local_auth_leases",
                    )
                ),
            )
            timestamps = connection.execute(
                """SELECT COUNT(*) FROM nodes
                WHERE policy_state = 'protocol_ready'
                    AND (last_snapshot_at IS NOT NULL
                        OR last_traffic_ack_at IS NOT NULL)"""
            ).fetchone()[0]
        self.assertEqual(0, timestamps)
        user = self.db.get_proxy_user_by_name("alice")
        self.assertEqual((123, 456), (user["tx_bytes"], user["rx_bytes"]))

        with self.assertRaises(NodeRequestRejected):
            self.service.authorize(
                self.auth_payload(self.nodes[0], 46, request_id=request_id),
                remote_ip="203.0.113.1",
            )

        for index, node_id in enumerate(self.nodes, 47):
            self.service.accept_online_snapshot(
                self.snapshot(node_id, index, sequence=2),
                remote_ip="203.0.113.{}".format(int(node_id, 16)),
            )
        refreshed = self.service.authorize(
            self.auth_payload(self.nodes[0], 49), remote_ip="203.0.113.1"
        )
        self.assertTrue(refreshed["ok"])

    def test_local_auth_accepts_remote_snapshots_within_control_retry_budget(self):
        class Stats:
            def collect_and_clear(self):
                return {}

            def online(self):
                return {}

        manager = UsageManager(
            self.db,
            Stats(),
            clock=lambda: 123.0,
            wall_clock=lambda: self.now[0],
        )
        self.now[0] += 40

        self.assertTrue(manager.authorize("alice"))

    def test_pending_remote_auth_covers_the_full_snapshot_freshness_window(self):
        for index in range(3):
            result = self.service.authorize(
                self.auth_payload(self.nodes[index % 2], 90 + index),
                remote_ip="203.0.113.{}".format((index % 2) + 1),
            )
            self.assertTrue(result["ok"])
        self.now[0] += 40

        fourth = self.service.authorize(
            self.auth_payload(self.nodes[0], 93), remote_ip="203.0.113.1"
        )

        self.assertFalse(fourth["ok"])

    def test_local_and_remote_auth_share_one_global_device_limit(self):
        class Stats:
            def collect_and_clear(self):
                return {}

            def online(self):
                return {}

        manager = UsageManager(
            self.db,
            Stats(),
            clock=lambda: self.now[0],
            wall_clock=lambda: self.now[0],
        )
        service = DistributedControlService(
            self.db,
            clock=lambda: self.now[0],
            signature_verifier=lambda _key, _message, _signature: True,
            local_state_provider=manager.distributed_local_state,
        )
        start = threading.Barrier(5)
        results = []

        def local_authorize():
            start.wait(1)
            results.append(manager.authorize("alice"))

        def remote_authorize(index):
            start.wait(1)
            try:
                result = service.authorize(
                    self.auth_payload(self.nodes[index % 2], 70 + index),
                    remote_ip="203.0.113.{}".format((index % 2) + 1),
                )
            except NodeRequestRejected:
                results.append(False)
            else:
                results.append(result["ok"])

        workers = [threading.Thread(target=local_authorize)] + [
            threading.Thread(target=remote_authorize, args=(index,))
            for index in range(3)
        ]
        for worker in workers:
            worker.start()
        start.wait(1)
        for worker in workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())

        self.assertEqual(3, results.count(True))
        self.assertEqual(1, results.count(False))
        self.now[0] += MAX_STATE_AGE_SECONDS + 1
        self.assertFalse(manager.authorize("alice"))

    def test_distributed_local_state_uses_wall_clock_for_protocol_timestamps(self):
        class Stats:
            def collect_and_clear(self):
                return {}

            def online(self):
                return {}

        manager = UsageManager(
            self.db,
            Stats(),
            clock=lambda: 123.0,
            wall_clock=lambda: self.now[0],
        )

        self.assertEqual(
            {
                "online": {},
                "observedAt": self.now[0],
                "trafficAckedAt": self.now[0],
            },
            manager.distributed_local_state(),
        )

    def test_auth_secrets_and_signed_envelopes_are_not_persisted(self):
        payload = self.auth_payload(self.nodes[0], 80)
        self.assertTrue(
            self.service.authorize(payload, remote_ip="203.0.113.1")["ok"]
        )
        database_bytes = b"".join(
            path.read_bytes()
            for path in self.db_path.parent.glob(self.db_path.name + "*")
            if path.is_file()
        )
        for secret in (
            self.token,
            payload["nonce"],
            payload["signature"],
            json.dumps(payload, separators=(",", ":")),
        ):
            self.assertNotIn(secret.encode("utf-8"), database_bytes)


class DistributedTrafficTests(DistributedControlCase):
    def setUp(self):
        super().setUp()
        self.db.create_proxy_user("alice")

    def traffic_payload(self, node_id, value, batch_id=None, traffic=None):
        payload = self.common(node_id, value)
        payload.update(
            {
                "batchId": batch_id or "{:032x}".format(value),
                "observedAt": self.now[0],
                "traffic": traffic or {"alice": {"tx": 10, "rx": 20}},
            }
        )
        return payload

    def test_two_nodes_sum_and_retry_of_one_batch_has_effect_once(self):
        batch_id = "a" * 32
        first = self.service.apply_traffic_batch(
            self.traffic_payload(self.nodes[0], 50, batch_id=batch_id),
            remote_ip="203.0.113.1",
        )
        duplicate = self.service.apply_traffic_batch(
            self.traffic_payload(self.nodes[0], 51, batch_id=batch_id),
            remote_ip="203.0.113.1",
        )
        self.service.apply_traffic_batch(
            self.traffic_payload(self.nodes[1], 52), remote_ip="203.0.113.2"
        )
        user = self.db.get_proxy_user_by_name("alice")
        self.assertTrue(first["committed"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual((20, 40), (user["tx_bytes"], user["rx_bytes"]))
        origins = {row["origin_id"]: row for row in self.db.list_usage_origins()}
        self.assertEqual(
            (10, 20),
            (origins["node:" + self.nodes[0]]["tx_bytes"], origins["node:" + self.nodes[0]]["rx_bytes"]),
        )
        self.assertEqual(
            (10, 20),
            (origins["node:" + self.nodes[1]]["tx_bytes"], origins["node:" + self.nodes[1]]["rx_bytes"]),
        )
        self.assertEqual("node-1", origins["node:" + self.nodes[0]]["display_name"])
        self.assertEqual("node-2", origins["node:" + self.nodes[1]]["display_name"])

    def test_unknown_user_is_counted_without_blocking_known_traffic(self):
        result = self.service.apply_traffic_batch(
            self.traffic_payload(
                self.nodes[0],
                53,
                traffic={"alice": {"tx": 1, "rx": 2}, "deleted": {"tx": 3, "rx": 4}},
            ),
            remote_ip="203.0.113.1",
        )
        self.assertEqual(1, result["unknownUsers"])
        user = self.db.get_proxy_user_by_name("alice")
        self.assertEqual((1, 2), (user["tx_bytes"], user["rx_bytes"]))

    def test_quota_crossing_queues_one_fixed_kick_for_every_ready_node(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE proxy_users SET traffic_limit_bytes = 25 WHERE name = 'alice'"
            )
        batch_id = "c" * 32

        self.service.apply_traffic_batch(
            self.traffic_payload(self.nodes[0], 55, batch_id=batch_id),
            remote_ip="203.0.113.1",
        )
        self.service.apply_traffic_batch(
            self.traffic_payload(self.nodes[0], 56, batch_id=batch_id),
            remote_ip="203.0.113.1",
        )

        with sqlite3.connect(str(self.db_path)) as connection:
            commands = connection.execute(
                """SELECT node_id, kind, payload FROM node_commands
                ORDER BY node_id"""
            ).fetchall()
        self.assertEqual(
            [
                (self.nodes[0], "KICK_USERS", '{"users":["alice"]}'),
                (self.nodes[1], "KICK_USERS", '{"users":["alice"]}'),
            ],
            commands,
        )

    def test_local_traffic_quota_crossing_also_kicks_every_ready_node(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE proxy_users SET traffic_limit_bytes = 25 WHERE name = 'alice'"
            )

        self.assertTrue(
            self.db.apply_traffic_batch(
                "d" * 32, {"alice": {"tx": 10, "rx": 20}}
            )
        )

        with sqlite3.connect(str(self.db_path)) as connection:
            commands = connection.execute(
                "SELECT node_id, kind, payload FROM node_commands ORDER BY node_id"
            ).fetchall()
        self.assertEqual(
            [
                (self.nodes[0], "KICK_USERS", '{"users":["alice"]}'),
                (self.nodes[1], "KICK_USERS", '{"users":["alice"]}'),
            ],
            commands,
        )

    def test_large_quota_crossing_batch_commits_and_chunks_kick_commands(self):
        names = ["user-{:03d}".format(index) for index in range(101)]
        for name in names:
            self.db.create_proxy_user(name)
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.executemany(
                "UPDATE proxy_users SET traffic_limit_bytes = 1 WHERE name = ?",
                ((name,) for name in names),
            )

        batch_id = "e" * 32
        result = self.db.apply_node_traffic_batch(
            self.nodes[0],
            batch_id,
            {name: {"tx": 1, "rx": 1} for name in names},
            "f" * 64,
            accepted_at=self.now[0],
        )

        self.assertTrue(result["committed"])
        duplicate = self.db.apply_node_traffic_batch(
            self.nodes[0],
            batch_id,
            {name: {"tx": 1, "rx": 1} for name in names},
            "e" * 64,
            accepted_at=self.now[0] + 1,
        )
        self.assertTrue(duplicate["duplicate"])
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            self.assertIsNotNone(
                connection.execute(
                    """SELECT 1 FROM node_traffic_batches
                    WHERE node_id = ? AND batch_id = ?""",
                    (self.nodes[0], batch_id),
                ).fetchone()
            )
            commands = connection.execute(
                """SELECT node_id, payload FROM node_commands
                WHERE kind = 'KICK_USERS' ORDER BY node_id, payload"""
            ).fetchall()
        self.assertEqual(4, len(commands))
        for node_id in self.nodes:
            chunks = [
                json.loads(row["payload"])["users"]
                for row in commands
                if row["node_id"] == node_id
            ]
            self.assertEqual(names, sorted(name for chunk in chunks for name in chunk))
            self.assertTrue(all(1 <= len(chunk) <= 100 for chunk in chunks))
        for name in names:
            user = self.db.get_proxy_user_by_name(name)
            self.assertEqual((1, 1), (user["tx_bytes"], user["rx_bytes"]))

    def test_large_quota_kick_failure_rolls_back_the_entire_traffic_batch(self):
        names = ["rollback-{:03d}".format(index) for index in range(101)]
        for name in names:
            self.db.create_proxy_user(name)
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.executemany(
                "UPDATE proxy_users SET traffic_limit_bytes = 1 WHERE name = ?",
                ((name,) for name in names),
            )
            connection.execute(
                """CREATE TRIGGER reject_second_kick_chunk
                BEFORE INSERT ON node_commands
                WHEN NEW.kind = 'KICK_USERS' AND NEW.payload LIKE '%rollback-100%'
                BEGIN
                    SELECT RAISE(ABORT, 'injected command failure');
                END"""
            )

        batch_id = "6" * 32
        result = self.db.apply_node_traffic_batch(
            self.nodes[0],
            batch_id,
            {name: {"tx": 1, "rx": 1} for name in names},
            "6" * 64,
            accepted_at=self.now[0],
        )

        self.assertIsNone(result)
        with sqlite3.connect(str(self.db_path)) as connection:
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM node_commands WHERE kind = 'KICK_USERS'"
                ).fetchone()[0],
            )
            self.assertIsNone(
                connection.execute(
                    """SELECT 1 FROM node_traffic_batches
                    WHERE node_id = ? AND batch_id = ?""",
                    (self.nodes[0], batch_id),
                ).fetchone()
            )
        for name in names:
            user = self.db.get_proxy_user_by_name(name)
            self.assertEqual((0, 0), (user["tx_bytes"], user["rx_bytes"]))
        self.assertEqual([], self.db.list_usage_origins())

    def test_one_nodes_full_ledger_does_not_block_another_node(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.executemany(
                """INSERT INTO node_traffic_batches(
                    node_id, batch_id, unknown_users, applied_at
                ) VALUES (?, ?, 0, ?)""",
                (
                    (self.nodes[1], "{:032x}".format(index), self.now[0])
                    for index in range(250000)
                ),
            )

        result = self.db.apply_node_traffic_batch(
            self.nodes[0],
            "9" * 32,
            {"alice": {"tx": 1, "rx": 1}},
            "8" * 64,
            accepted_at=self.now[0],
        )

        self.assertTrue(result["committed"])
        self.assertEqual((1, 1), tuple(
            self.db.get_proxy_user_by_name("alice")[key]
            for key in ("tx_bytes", "rx_bytes")
        ))

    def test_node_traffic_ledger_evicts_oldest_row_instead_of_rejecting_batch(self):
        with mock.patch.object(
            Database, "NODE_TRAFFIC_LEDGER_MAX_ROWS", 3, create=True
        ):
            with sqlite3.connect(str(self.db_path)) as connection:
                connection.executemany(
                    """INSERT INTO node_traffic_batches(
                        node_id, batch_id, unknown_users, applied_at
                    ) VALUES (?, ?, 0, ?)""",
                    (
                        (self.nodes[0], "{:032x}".format(index), self.now[0] + index)
                        for index in range(3)
                    ),
                )

            result = self.db.apply_node_traffic_batch(
                self.nodes[0],
                "a" * 32,
                {"alice": {"tx": 1, "rx": 1}},
                "7" * 64,
                accepted_at=self.now[0] + 3,
            )

        self.assertTrue(result["committed"])
        with sqlite3.connect(str(self.db_path)) as connection:
            batches = connection.execute(
                """SELECT batch_id FROM node_traffic_batches
                WHERE node_id = ? ORDER BY applied_at, batch_id""",
                (self.nodes[0],),
            ).fetchall()
        self.assertEqual(3, len(batches))
        self.assertNotIn(("0" * 32,), batches)
        self.assertIn(("a" * 32,), batches)

    def test_spooled_batch_survives_a_control_plane_outage(self):
        observed_at = self.now[0]
        self.now[0] += 600
        payload = self.traffic_payload(self.nodes[0], 54, batch_id="b" * 32)
        payload["observedAt"] = observed_at
        result = self.service.apply_traffic_batch(
            payload, remote_ip="203.0.113.1"
        )
        self.assertTrue(result["committed"])
        self.assertEqual((10, 20), tuple(self.db.get_proxy_user_by_name("alice")[key] for key in ("tx_bytes", "rx_bytes")))


class NodeCommandTests(DistributedControlCase):
    def test_broadcast_kick_rejects_invalid_names_without_partial_commands(self):
        for names in (None, [object()], ["user-{:04d}".format(i) for i in range(1001)]):
            with self.subTest(names=names):
                with self.assertRaises(ValueError):
                    self.db.queue_kick_users_on_ready_nodes(names, self.now[0])
        with sqlite3.connect(str(self.db_path)) as connection:
            self.assertEqual(
                0, connection.execute("SELECT COUNT(*) FROM node_commands").fetchone()[0]
            )

    def test_broadcast_kick_chunks_large_valid_name_sets(self):
        names = ["user-{:03d}".format(index) for index in range(101)]

        self.assertEqual(
            4, self.db.queue_kick_users_on_ready_nodes(names, self.now[0])
        )

        with sqlite3.connect(str(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            commands = connection.execute(
                """SELECT node_id, payload FROM node_commands
                WHERE kind = 'KICK_USERS' ORDER BY node_id, payload"""
            ).fetchall()
        self.assertEqual(4, len(commands))
        for node_id in self.nodes:
            chunks = [
                json.loads(row["payload"])["users"]
                for row in commands
                if row["node_id"] == node_id
            ]
            self.assertEqual(names, sorted(name for chunk in chunks for name in chunk))
            self.assertTrue(all(1 <= len(chunk) <= 100 for chunk in chunks))

    def test_only_fixed_commands_can_be_polled_and_acknowledged_idempotently(self):
        command = self.db.queue_node_command(
            self.nodes[0], "KICK_USERS", {"users": ["alice"]}, self.now[0]
        )
        poll = self.common(self.nodes[0], 60)
        poll["requestId"] = "b" * 32
        commands = self.service.poll_commands(poll, remote_ip="203.0.113.1")
        self.assertEqual(command["commandId"], commands["commands"][0]["commandId"])
        ack = self.common(self.nodes[0], 61)
        ack.update({"commandId": command["commandId"], "ok": True, "errorCode": ""})
        self.assertTrue(self.service.ack_command(ack, remote_ip="203.0.113.1")["acked"])
        retry = self.common(self.nodes[0], 62)
        retry.update({"commandId": command["commandId"], "ok": True, "errorCode": ""})
        self.assertTrue(self.service.ack_command(retry, remote_ip="203.0.113.1")["acked"])
        with self.assertRaises(ValueError):
            self.db.queue_node_command(
                self.nodes[0], "RUN_SHELL", {"command": "id"}, self.now[0]
            )

    def test_failed_or_unacked_commands_retry_with_bounded_backoff(self):
        command = self.db.queue_node_command(
            self.nodes[0], "REFRESH_SNAPSHOT", {}, self.now[0]
        )
        first = self.common(self.nodes[0], 63)
        first["requestId"] = "c" * 32
        self.assertEqual(
            [command],
            self.service.poll_commands(first, remote_ip="203.0.113.1")["commands"],
        )

        immediate = self.common(self.nodes[0], 64)
        immediate["requestId"] = "d" * 32
        self.assertEqual(
            [],
            self.service.poll_commands(immediate, remote_ip="203.0.113.1")["commands"],
        )

        self.now[0] += 2
        retry = self.common(self.nodes[0], 65)
        retry["requestId"] = "e" * 32
        self.assertEqual(
            command["commandId"],
            self.service.poll_commands(retry, remote_ip="203.0.113.1")["commands"][0][
                "commandId"
            ],
        )

    def test_unacked_commands_continue_retrying_after_attempt_cap(self):
        command = self.db.queue_node_command(
            self.nodes[0], "REFRESH_SNAPSHOT", {}, self.now[0]
        )
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """UPDATE node_commands SET attempts = 10, next_attempt_at = ?
                WHERE command_id = ?""",
                (self.now[0], command["commandId"]),
            )

        capped = self.common(self.nodes[0], 66)
        capped["requestId"] = "f" * 32
        delivered = self.service.poll_commands(capped, remote_ip="203.0.113.1")
        self.assertEqual(command["commandId"], delivered["commands"][0]["commandId"])
        with sqlite3.connect(str(self.db_path)) as connection:
            attempts, next_attempt_at = connection.execute(
                """SELECT attempts, next_attempt_at FROM node_commands
                WHERE command_id = ?""",
                (command["commandId"],),
            ).fetchone()
        self.assertEqual(10, attempts)
        self.assertGreater(next_attempt_at, self.now[0])

        self.now[0] = next_attempt_at
        again = self.common(self.nodes[0], 67)
        again["requestId"] = "1" * 32
        redelivered = self.service.poll_commands(again, remote_ip="203.0.113.1")
        self.assertEqual(
            command["commandId"], redelivered["commands"][0]["commandId"]
        )


class NodeAgentProtocolTests(unittest.TestCase):
    class Response:
        def __init__(self, payload, status=200):
            self.payload = payload
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, maximum):
            return self.payload[:maximum]

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_auth_proxy_strips_address_and_maps_every_control_failure_to_denial(self):
        captured = {}

        def authorize(payload):
            captured.update(payload)
            return {"ok": True, "id": "alice"}

        status, response = node_agent.proxy_auth_payload(
            json.dumps({"addr": "198.51.100.4:1234", "auth": "secret", "tx": 10}).encode(),
            authorize,
            entrypoint="main",
        )
        self.assertEqual((200, {"ok": True, "id": "alice"}), (status, response))
        self.assertNotIn("addr", captured)
        self.assertEqual("secret", captured["auth"])
        for failure in (OSError("offline"), ValueError("bad response")):
            with self.subTest(failure=failure):
                status, response = node_agent.proxy_auth_payload(
                    json.dumps({"addr": "198.51.100.4:1234", "auth": "secret", "tx": 10}).encode(),
                    lambda _payload, failure=failure: (_ for _ in ()).throw(failure),
                    entrypoint="main",
                )
                self.assertEqual((200, {"ok": False, "id": ""}), (status, response))

    def test_durable_spool_keeps_batches_until_ack_and_uses_root_only_files(self):
        spool = node_agent.DurableTrafficSpool(self.root / "spool", max_bytes=1024 * 1024)
        batch = spool.enqueue({"alice": {"tx": 10, "rx": 20}}, observed_at=2_000_000_000)
        path = self.root / "spool" / (batch["batchId"] + ".json")
        self.assertTrue(path.exists())
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        self.assertEqual([batch], spool.pending())
        spool.ack(batch["batchId"])
        self.assertFalse(path.exists())

    def test_spool_preflight_reserves_envelope_and_rejects_unsafe_entries(self):
        spool = node_agent.DurableTrafficSpool(
            self.root / "bounded-spool",
            max_bytes=256 * 1024,
            reserve_bytes=0,
        )
        with mock.patch.object(
            node_agent.shutil,
            "disk_usage",
            return_value=mock.Mock(free=10 * 1024 * 1024),
        ):
            self.assertFalse(spool.can_collect(256 * 1024))

        batch = spool.enqueue({"alice": {"tx": 1, "rx": 2}}, 2_000_000_000)
        entry = spool.path / (batch["batchId"] + ".json")
        entry.chmod(0o644)
        with self.assertRaises(node_agent.ProtocolError):
            spool.pending()

        count_limited = node_agent.DurableTrafficSpool(
            self.root / "count-spool",
            max_bytes=1024 * 1024,
            reserve_bytes=0,
            max_entries=1,
        )
        count_limited.enqueue({}, 2_000_000_000)
        with mock.patch.object(
            node_agent.shutil,
            "disk_usage",
            return_value=mock.Mock(free=10 * 1024 * 1024),
        ):
            self.assertFalse(count_limited.can_collect())
        with self.assertRaises(node_agent.ProtocolError):
            count_limited.enqueue({}, 2_000_000_001)

    def test_protocol_client_signs_domain_separated_https_requests(self):
        state = self.root / "registration.json"
        state.write_text(
            json.dumps(
                {
                    "nodeId": "d" * 32,
                    "panelUrl": "https://panel.example.com:19998",
                    "registeredAt": 1,
                    "status": "PENDING_VERIFICATION",
                }
            )
        )
        state.chmod(0o600)
        private_key = self.root / "private.pem"
        private_key.write_text("not-read-by-test-signer")
        private_key.chmod(0o600)
        captured = {}

        def signer(path, message):
            captured["privateKey"] = path
            captured["message"] = message
            return b"s" * 64

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return self.Response(
                json.dumps(
                    {
                        "ok": True,
                        "id": "alice",
                        "decisionId": "e" * 32,
                        "expiresAt": 2_000_000_005,
                    }
                ).encode()
            )

        client = node_agent.NodeProtocolClient(
            state,
            private_key,
            opener=opener,
            signer=signer,
            clock=lambda: 2_000_000_000,
            nonce_factory=lambda _size: nonce(90),
        )
        result = client.authorize({"entrypoint": "main", "auth": "secret", "tx": 10})
        self.assertTrue(result["ok"])
        self.assertEqual(
            "https://panel.example.com:19998/api/v1/node-auth-decisions",
            captured["url"],
        )
        self.assertEqual(8, captured["timeout"])
        self.assertTrue(captured["message"].startswith(b"hy2panel-node-auth-v1\n"))
        self.assertNotIn(b"signature", captured["message"])
        self.assertEqual(base64.b64encode(b"s" * 64).decode(), captured["body"]["signature"])

    def test_protocol_client_sends_one_bounded_control_cycle_request(self):
        state = self.root / "registration.json"
        state.write_text(
            json.dumps(
                {
                    "nodeId": "d" * 32,
                    "panelUrl": "https://panel.example.com:19998",
                    "registeredAt": 1,
                    "status": "PENDING_VERIFICATION",
                }
            )
        )
        state.chmod(0o600)
        private_key = self.root / "private.pem"
        private_key.write_text("not-read-by-test-signer")
        private_key.chmod(0o600)
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return self.Response(
                json.dumps(
                    {
                        "cycleId": captured["body"]["cycleId"],
                        "acceptedAt": 2_000_000_000,
                        "traffic": [
                            {
                                "batchId": "a" * 32,
                                "committed": True,
                                "duplicate": False,
                                "unknownUsers": 0,
                            }
                        ],
                        "online": {
                            "snapshotId": "b" * 32,
                            "sequence": 1,
                            "acceptedAt": 2_000_000_000,
                        },
                        "commands": [],
                        "polledAt": 2_000_000_000,
                    }
                ).encode()
            )

        messages = []
        client = node_agent.NodeProtocolClient(
            state,
            private_key,
            opener=opener,
            signer=lambda _path, message: messages.append(message) or b"s" * 64,
            clock=lambda: 2_000_000_000,
            nonce_factory=lambda _size: nonce(92),
        )
        result = client.send_control_cycle(
            [{"batchId": "a" * 32, "observedAt": 2_000_000_000, "traffic": {}}],
            {
                "snapshotId": "b" * 32,
                "sequence": 1,
                "observedAt": 2_000_000_000,
                "trafficAckedAt": 2_000_000_000,
                "online": {},
            },
        )

        self.assertEqual(
            "https://panel.example.com:19998/api/v1/node-control-cycles",
            captured["url"],
        )
        self.assertEqual(8, captured["timeout"])
        self.assertTrue(messages[0].startswith(b"hy2panel-node-control-cycle-v1\n"))
        self.assertEqual("a" * 32, result["traffic"][0]["batchId"])

    def test_signer_streams_secret_bearing_requests_without_a_temp_file(self):
        message = b'hy2panel-node-auth-v1\n{"auth":"secret"}'
        private_key = Path(self.temp_dir.name) / "node.key"
        private_key.write_bytes(b"private")
        private_key.chmod(0o600)
        completed = mock.Mock(returncode=0, stdout=b"s" * 64)
        with mock.patch.object(
            node_agent.os, "memfd_create", None, create=True
        ), mock.patch.object(
            node_agent.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(
                b"s" * 64,
                node_agent._openssl_sign(private_key, message, executable="/usr/bin/openssl"),
            )
        arguments = run.call_args.args[0]
        self.assertEqual("/dev/stdin", arguments[arguments.index("-in") + 1])
        self.assertEqual(message, run.call_args.kwargs["input"])
        self.assertNotIn("stdin", run.call_args.kwargs)

    def test_signer_uses_anonymous_memory_on_openssl_3_linux(self):
        message = b'hy2panel-node-auth-v1\n{"auth":"secret"}'
        private_key = Path(self.temp_dir.name) / "node.key"
        private_key.write_bytes(b"private")
        private_key.chmod(0o600)
        completed = mock.Mock(returncode=0, stdout=b"s" * 64)
        with mock.patch.object(
            node_agent.os, "memfd_create", return_value=41, create=True
        ) as create, mock.patch.object(
            node_agent.os.path, "isdir", return_value=True
        ), mock.patch.object(
            node_agent.os, "write", return_value=len(message)
        ) as write, mock.patch.object(
            node_agent.os, "lseek"
        ) as seek, mock.patch.object(
            node_agent.os, "close"
        ) as close, mock.patch.object(
            node_agent.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(
                b"s" * 64,
                node_agent._openssl_sign(private_key, message, executable="/usr/bin/openssl"),
            )
        create.assert_called_once()
        write.assert_called_once_with(41, mock.ANY)
        seek.assert_called_once_with(41, 0, node_agent.os.SEEK_SET)
        close.assert_called_once_with(41)
        arguments = run.call_args.args[0]
        self.assertEqual("/proc/self/fd/41", arguments[arguments.index("-in") + 1])
        self.assertEqual((41,), run.call_args.kwargs["pass_fds"])
        self.assertNotIn("input", run.call_args.kwargs)

    def test_verifier_streams_secret_bearing_requests_without_a_message_file(self):
        public_der = bytes.fromhex("302a300506032b6570032100") + b"p" * 32
        message = b'hy2panel-node-auth-v1\n{"auth":"secret"}'
        completed = mock.Mock(returncode=0)
        with mock.patch(
            "hy2panel.nodes.os.memfd_create", None, create=True
        ), mock.patch("hy2panel.nodes.subprocess.run", return_value=completed) as run:
            self.assertTrue(
                OpenSSLSignatureVerifier()(
                    base64.b64encode(public_der).decode("ascii"),
                    message,
                    b"s" * 64,
                )
            )
        arguments = run.call_args.args[0]
        self.assertEqual("/dev/stdin", arguments[arguments.index("-in") + 1])
        self.assertEqual(message, run.call_args.kwargs["input"])

    def test_verifier_uses_anonymous_memory_on_openssl_3_linux(self):
        public_der = bytes.fromhex("302a300506032b6570032100") + b"p" * 32
        message = b'hy2panel-node-auth-v1\n{"auth":"secret"}'
        completed = mock.Mock(returncode=0)
        with mock.patch(
            "hy2panel.nodes.os.memfd_create", return_value=42, create=True
        ), mock.patch(
            "hy2panel.nodes.os.path.isdir", return_value=True
        ), mock.patch(
            "hy2panel.nodes.os.write", return_value=len(message)
        ), mock.patch(
            "hy2panel.nodes.os.lseek"
        ), mock.patch(
            "hy2panel.nodes.os.close"
        ) as close, mock.patch(
            "hy2panel.nodes.subprocess.run", return_value=completed
        ) as run:
            self.assertTrue(
                OpenSSLSignatureVerifier()(
                    base64.b64encode(public_der).decode("ascii"),
                    message,
                    b"s" * 64,
                )
            )
        close.assert_any_call(42)
        arguments = run.call_args.args[0]
        self.assertEqual("/proc/self/fd/42", arguments[arguments.index("-in") + 1])
        self.assertEqual((42,), run.call_args.kwargs["pass_fds"])
        self.assertNotIn("input", run.call_args.kwargs)

    def test_streaming_signer_and_verifier_interoperate_with_real_ed25519(self):
        homebrew_openssl = Path("/opt/homebrew/opt/openssl@3/bin/openssl")
        openssl = (
            str(homebrew_openssl)
            if homebrew_openssl.exists()
            else node_agent.shutil.which("openssl")
        )
        self.assertIsNotNone(openssl)
        private_key = self.root / "real-private.pem"
        public_der = self.root / "real-public.der"
        node_agent.subprocess.run(
            [openssl, "genpkey", "-algorithm", "ED25519", "-out", private_key],
            check=True,
            capture_output=True,
        )
        private_key.chmod(0o600)
        node_agent.subprocess.run(
            [
                openssl,
                "pkey",
                "-in",
                private_key,
                "-pubout",
                "-outform",
                "DER",
                "-out",
                public_der,
            ],
            check=True,
            capture_output=True,
        )
        message = b'hy2panel-node-auth-v1\n{"auth":"secret"}'
        signature = node_agent._openssl_sign(
            private_key, message, executable=openssl
        )
        self.assertTrue(
            OpenSSLSignatureVerifier(executable=openssl)(
                base64.b64encode(public_der.read_bytes()).decode("ascii"),
                message,
                signature,
            )
        )

    def test_command_executor_has_no_generic_command_surface(self):
        calls = []

        class Stats:
            def kick(self, users):
                calls.append(("kick", users))

            def online(self):
                calls.append(("online",))
                return {}

            def collect_and_clear(self):
                calls.append(("traffic",))
                return {}

        stats = Stats()
        node_agent.execute_control_command(
            {"commandId": "a" * 32, "kind": "KICK_USERS", "payload": {"users": ["alice"]}},
            stats,
        )
        node_agent.execute_control_command(
            {"commandId": "b" * 32, "kind": "REFRESH_SNAPSHOT", "payload": {}},
            stats,
            refresh_snapshot=lambda: calls.append(("snapshot",)),
        )
        node_agent.execute_control_command(
            {"commandId": "c" * 32, "kind": "FLUSH_TRAFFIC", "payload": {}},
            stats,
            flush_traffic=lambda: calls.append(("durable-flush",)),
        )
        self.assertEqual(
            [("kick", ["alice"]), ("snapshot",), ("durable-flush",)], calls
        )
        with self.assertRaises(node_agent.ProtocolError):
            node_agent.execute_control_command(
                {"commandId": "e" * 32, "kind": "FLUSH_TRAFFIC", "payload": {}},
                stats,
            )
        with self.assertRaises(node_agent.ProtocolError):
            node_agent.execute_control_command(
                {"commandId": "d" * 32, "kind": "RUN_SHELL", "payload": {"command": "id"}},
                stats,
            )

    def test_control_cycle_replays_durable_traffic_after_failed_ack(self):
        calls = []
        now = [2_000_000_000]

        class Stats:
            def collect_and_clear(self):
                calls.append(("collect",))
                if len([call for call in calls if call == ("collect",)]) == 1:
                    return {"alice": {"tx": 10, "rx": 20}}
                return {}

            def online(self):
                return {"alice": 1}

            def kick(self, users):
                calls.append(("kick", users))

        class Protocol:
            fail_once = True

            def send_traffic(self, batch):
                calls.append(("send", batch["batchId"], dict(batch["traffic"])))
                if self.fail_once:
                    self.fail_once = False
                    raise OSError("central unavailable")
                return {"batchId": batch["batchId"], "committed": True}

            def send_online(self, sequence, online, traffic_acked_at):
                calls.append(("snapshot", sequence, online, traffic_acked_at))
                return {"sequence": sequence}

            def poll_commands(self):
                return []

            def ack_command(self, command_id, ok, error_code):
                calls.append(("command-ack", command_id, ok, error_code))

        root = Path(self.temp_dir.name)
        spool = node_agent.DurableTrafficSpool(root / "traffic-spool")
        state = node_agent.ProtocolState(root / "protocol-state.json")
        cycle = node_agent.NodeControlCycle(
            Protocol(), Stats(), spool, state, clock=lambda: now[0]
        )

        batch_ids = [mock.Mock(hex="f" * 32), mock.Mock(hex="0" * 32)]
        with mock.patch.object(node_agent.uuid, "uuid4", side_effect=batch_ids):
            with self.assertRaises(OSError):
                cycle.flush_traffic()
            pending = spool.pending()
            self.assertEqual(1, len(pending))
            self.assertEqual(
                {"alice": {"tx": 10, "rx": 20}}, pending[0]["traffic"]
            )

            now[0] += 1
            cycle.run_once()
        self.assertEqual([], spool.pending())
        self.assertEqual(now[0], state.traffic_acked_at())
        sent = [call for call in calls if call[0] == "send"]
        self.assertEqual(sent[0][1], sent[1][1])
        self.assertEqual({}, sent[2][2])
        snapshots = [call for call in calls if call[0] == "snapshot"]
        self.assertEqual(1, len(snapshots))
        self.assertEqual({"alice": 1}, snapshots[0][2])

    def test_control_cycle_collects_new_traffic_while_an_older_batch_cannot_upload(self):
        calls = []

        class Stats:
            def collect_and_clear(self):
                calls.append("collect")
                return {"alice": {"tx": 30, "rx": 40}}

            def online(self):
                return {"alice": 1}

        class Protocol:
            def send_traffic(self, _batch):
                calls.append("send")
                raise OSError("central unavailable")

            def send_online(self, _sequence, _online, _traffic_acked_at):
                calls.append("snapshot")
                return {"sequence": 1}

            def poll_commands(self):
                calls.append("poll")
                return []

        root = Path(self.temp_dir.name)
        spool = node_agent.DurableTrafficSpool(root / "outage-spool")
        spool.enqueue({"alice": {"tx": 10, "rx": 20}}, 2_000_000_000)
        cycle = node_agent.NodeControlCycle(
            Protocol(),
            Stats(),
            spool,
            node_agent.ProtocolState(root / "outage-state.json"),
            clock=lambda: 2_000_000_001,
        )

        with self.assertRaises(OSError):
            cycle.run_once()

        self.assertIn("collect", calls)
        self.assertIn("poll", calls)
        self.assertEqual(2, len(spool.pending()))
        self.assertIn(
            {"alice": {"tx": 30, "rx": 40}},
            [batch["traffic"] for batch in spool.pending()],
        )

    def test_control_cycle_combines_upload_snapshot_and_command_poll(self):
        calls = []

        class Stats:
            def collect_and_clear(self):
                calls.append("collect")
                return {"alice": {"tx": 10, "rx": 20}}

            def online(self):
                calls.append("online")
                return {"alice": 1}

        class Protocol:
            def send_control_cycle(self, batches, snapshot):
                calls.append(("combined", len(batches), snapshot["online"]))
                return {
                    "acceptedAt": 2_000_000_000,
                    "traffic": [
                        {"batchId": batch["batchId"], "committed": True}
                        for batch in batches
                    ],
                    "online": {
                        "snapshotId": snapshot["snapshotId"],
                        "sequence": snapshot["sequence"],
                    },
                    "commands": [],
                }

            def poll_commands(self):
                calls.append("legacy-poll")
                return []

        root = Path(self.temp_dir.name)
        spool = node_agent.DurableTrafficSpool(root / "combined-spool")
        state = node_agent.ProtocolState(root / "combined-state.json")
        node_agent.NodeControlCycle(
            Protocol(), Stats(), spool, state, clock=lambda: 2_000_000_000
        ).run_once()

        self.assertEqual([], spool.pending())
        self.assertEqual(2_000_000_000, state.traffic_acked_at())
        self.assertIn(("combined", 1, {"alice": 1}), calls)
        self.assertNotIn("legacy-poll", calls)

    def test_control_cycle_falls_back_only_once_when_old_panel_returns_404(self):
        calls = []

        class Stats:
            def collect_and_clear(self):
                return {}

            def online(self):
                return {}

        class Protocol:
            def send_control_cycle(self, _batches, _snapshot):
                calls.append("combined")
                raise node_agent.ProtocolNotSupported("old panel")

            def send_traffic(self, batch):
                calls.append("traffic")
                return {"batchId": batch["batchId"], "committed": True}

            def send_online(self, sequence, _online, _traffic_acked_at):
                calls.append("snapshot")
                return {"sequence": sequence}

            def poll_commands(self):
                calls.append("poll")
                return []

        root = Path(self.temp_dir.name)
        cycle = node_agent.NodeControlCycle(
            Protocol(),
            Stats(),
            node_agent.DurableTrafficSpool(root / "fallback-spool"),
            node_agent.ProtocolState(root / "fallback-state.json"),
            clock=lambda: 2_000_000_000,
        )
        cycle.run_once()
        cycle.run_once()

        self.assertEqual(1, calls.count("combined"))
        self.assertEqual(2, calls.count("poll"))
        self.assertEqual(2, calls.count("traffic"))

    def test_combined_cycle_keeps_the_serialized_request_below_the_http_limit(self):
        captured = {}

        class Stats:
            def collect_and_clear(self):
                raise AssertionError("full spool must be drained before collecting")

            def online(self):
                return {}

        class Protocol:
            def send_control_cycle(self, batches, snapshot):
                captured["count"] = len(batches)
                captured["size"] = len(
                    json.dumps(
                        {"trafficBatches": batches, "onlineSnapshot": snapshot},
                        separators=(",", ":"),
                    ).encode()
                )
                return {
                    "acceptedAt": 2_000_000_000,
                    "traffic": [
                        {"batchId": batch["batchId"], "committed": True}
                        for batch in batches
                    ],
                    "online": (
                        None
                        if snapshot is None
                        else {
                            "snapshotId": snapshot["snapshotId"],
                            "sequence": snapshot["sequence"],
                        }
                    ),
                    "commands": [],
                }

        root = Path(self.temp_dir.name)
        spool = node_agent.DurableTrafficSpool(
            root / "bounded-combined-spool", max_entries=8
        )
        traffic = {
            "user-{:055d}".format(index): {"tx": 1, "rx": 1}
            for index in range(1000)
        }
        for observed_at in range(2_000_000_000, 2_000_000_008):
            spool.enqueue(traffic, observed_at)
        cycle = node_agent.NodeControlCycle(
            Protocol(),
            Stats(),
            spool,
            node_agent.ProtocolState(root / "bounded-combined-state.json"),
            clock=lambda: 2_000_000_010,
        )
        cycle.run_once()

        self.assertLess(captured["count"], 8)
        self.assertLessEqual(captured["size"], 480 * 1024)
        self.assertGreater(len(spool.pending()), 0)

    def test_control_cycle_persists_success_before_command_ack(self):
        calls = []
        command = {
            "commandId": "f" * 32,
            "kind": "KICK_USERS",
            "payload": {"users": ["alice"]},
        }

        class Stats:
            def collect_and_clear(self):
                return {}

            def online(self):
                return {}

            def kick(self, users):
                calls.append(("kick", list(users)))

        class Protocol:
            def send_traffic(self, batch):
                return {"batchId": batch["batchId"], "committed": True}

            def send_online(self, sequence, _online, _traffic_acked_at):
                return {"sequence": sequence}

            def poll_commands(self):
                return [command]

            def ack_command(self, command_id, ok, error_code):
                calls.append(("ack", command_id, ok, error_code))

        root = Path(self.temp_dir.name)
        state_path = root / "command-state.json"
        cycle = node_agent.NodeControlCycle(
            Protocol(),
            Stats(),
            node_agent.DurableTrafficSpool(root / "command-spool"),
            node_agent.ProtocolState(state_path),
            clock=lambda: 2_000_000_000,
        )
        cycle.run_once()
        restarted = node_agent.NodeControlCycle(
            Protocol(),
            Stats(),
            node_agent.DurableTrafficSpool(root / "command-spool"),
            node_agent.ProtocolState(state_path),
            clock=lambda: 2_000_000_001,
        )
        restarted.run_once()

        self.assertEqual([("kick", ["alice"])], [call for call in calls if call[0] == "kick"])
        self.assertEqual(2, len([call for call in calls if call[0] == "ack"]))

    def test_stats_client_rejects_non_loopback_and_short_secrets(self):
        with self.assertRaises(ValueError):
            node_agent.LocalStatsClient("http://203.0.113.1:19997", "s" * 32)
        with self.assertRaises(ValueError):
            node_agent.LocalStatsClient("http://127.0.0.1:19997", "short")

    def test_combined_stats_merges_both_entrypoints_and_kicks_both(self):
        calls = []

        class Stats:
            def __init__(self, name, online, traffic):
                self.name = name
                self._online = online
                self._traffic = traffic

            def online(self):
                calls.append((self.name, "online"))
                return dict(self._online)

            def collect_and_clear(self):
                calls.append((self.name, "traffic"))
                return dict(self._traffic)

            def kick(self, users):
                calls.append((self.name, "kick", list(users)))

        combined = node_agent.CombinedLocalStatsClient(
            Stats("main", {"alice": 2}, {"alice": {"tx": 10, "rx": 20}}),
            Stats(
                "udp443",
                {"alice": 1, "bob": 1},
                {"alice": {"tx": 3, "rx": 4}, "bob": {"tx": 5, "rx": 6}},
            ),
        )

        self.assertEqual({"alice": 3, "bob": 1}, combined.online())
        self.assertEqual(
            {
                "alice": {"tx": 13, "rx": 24},
                "bob": {"tx": 5, "rx": 6},
            },
            combined.collect_and_clear(),
        )
        combined.kick(["alice"])
        self.assertIn(("main", "kick", ["alice"]), calls)
        self.assertIn(("udp443", "kick", ["alice"]), calls)

    def test_combined_stats_fails_closed_when_either_entrypoint_fails(self):
        class Good:
            def online(self):
                return {}

            def collect_and_clear(self):
                return {}

            def kick(self, _users):
                return None

        class Bad(Good):
            def online(self):
                raise node_agent.ProtocolError("unavailable")

        combined = node_agent.CombinedLocalStatsClient(Good(), Bad())
        with self.assertRaises(node_agent.ProtocolError):
            combined.online()

    def test_loopback_auth_server_maps_main_and_udp443_without_logging_secrets(self):
        captured = []

        class Client:
            def authorize(self, payload):
                captured.append(payload)
                return {
                    "ok": True,
                    "id": "alice",
                    "decisionId": "a" * 32,
                    "expiresAt": 2_000_000_005,
                }

        server = node_agent.make_node_auth_proxy_server(("127.0.0.1", 0), Client())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:{}/auth/udp-443".format(server.server_address[1]),
                data=json.dumps(
                    {"addr": "198.51.100.4:1234", "auth": "secret", "tx": 10}
                ).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                self.assertEqual({"ok": True, "id": "alice"}, json.loads(response.read()))
            self.assertEqual("udp443", captured[0]["entrypoint"])
            self.assertNotIn("addr", captured[0])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
        with self.assertRaises(ValueError):
            node_agent.make_node_auth_proxy_server(("0.0.0.0", 19996), Client())

    def test_auth_server_evicts_slow_clients_and_bounds_workers(self):
        class Client:
            def authorize(self, _payload):
                return {"ok": False, "id": "", "decisionId": "a" * 32, "expiresAt": 0}

        server = node_agent.make_node_auth_proxy_server(
            ("127.0.0.1", 0), Client(), max_workers=1, request_timeout=0.2
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        slow = socket.create_connection(server.server_address, timeout=1)
        try:
            slow.sendall(b"POST /auth HTTP/1.1\r\nHost: localhost\r\n")
            time.sleep(0.35)
            with urllib.request.urlopen(
                "http://127.0.0.1:{}/healthz".format(server.server_address[1]),
                timeout=1,
            ) as response:
                self.assertEqual(200, response.status)
            self.assertEqual(1, server.max_workers)
        finally:
            slow.close()
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_auth_server_can_rebind_immediately_after_a_served_connection(self):
        class Client:
            def authorize(self, _payload):
                return {
                    "ok": False,
                    "id": "",
                    "decisionId": "a" * 32,
                    "expiresAt": 0,
                }

        first = node_agent.make_node_auth_proxy_server(
            ("127.0.0.1", 0), Client()
        )
        address = first.server_address
        thread = threading.Thread(target=first.serve_forever, daemon=True)
        thread.start()
        with urllib.request.urlopen(
            "http://127.0.0.1:{}/healthz".format(address[1]), timeout=1
        ) as response:
            self.assertEqual(200, response.status)
        first.shutdown()
        first.server_close()
        thread.join(2)

        second = node_agent.make_node_auth_proxy_server(address, Client())
        try:
            self.assertTrue(second.allow_reuse_address)
        finally:
            second.server_close()

    def test_control_loop_uses_jittered_polling_and_bounded_failure_backoff(self):
        calls = []
        stopped = threading.Event()

        class Cycle:
            def run_once(self):
                calls.append(("cycle",))
                if len(calls) == 1:
                    raise node_agent.ProtocolError("central unavailable")

        delays = []

        def sleeper(delay):
            delays.append(delay)
            if len(delays) == 2:
                stopped.set()

        node_agent.run_control_loop(
            Cycle(), stopped, sleeper=sleeper, jitter_source=lambda: 1.0
        )
        self.assertEqual([("cycle",), ("cycle",)], calls)
        self.assertEqual(2, len(delays))
        self.assertAlmostEqual(2.4, delays[0])
        self.assertAlmostEqual(2.4, delays[1])

    def test_snapshot_refresh_allows_the_bounded_control_retry_budget(self):
        now = 2_000_000_000

        class State:
            def traffic_acked_at(self):
                return now - 40

            def next_sequence(self):
                return 1

        class Protocol:
            def send_online(self, sequence, online, traffic_acked_at):
                self.sent = (sequence, online, traffic_acked_at)
                return {"sequence": sequence}

        class Stats:
            def online(self):
                return {"alice": 1}

        protocol = Protocol()
        cycle = node_agent.NodeControlCycle(
            protocol,
            Stats(),
            spool=None,
            state=State(),
            clock=lambda: now,
        )

        self.assertEqual({"sequence": 1}, cycle.refresh_snapshot())
        self.assertEqual((1, {"alice": 1}, now - 40), protocol.sent)
        self.assertEqual(MAX_STATE_AGE_SECONDS, node_agent.MAX_STATE_AGE_SECONDS)

    def test_control_once_reads_local_stats_secret_only_from_environment(self):
        cycle = mock.Mock()
        arguments = [
            "control-once",
            "--private-key",
            "/root/node.key",
            "--state-file",
            "/root/registration.json",
            "--protocol-state",
            "/root/protocol.json",
            "--spool-dir",
            "/root/spool",
            "--stats-url",
            "http://127.0.0.1:19997",
        ]
        with mock.patch.object(node_agent, "NodeProtocolClient") as protocol_client:
            with mock.patch.object(node_agent, "LocalStatsClient") as stats_client:
                with mock.patch.object(node_agent, "DurableTrafficSpool") as spool:
                    with mock.patch.object(node_agent, "ProtocolState") as state:
                        with mock.patch.object(
                            node_agent, "NodeControlCycle", return_value=cycle
                        ):
                            with mock.patch.dict(
                                os.environ,
                                {"HY2PANEL_STATS_SECRET": "s" * 32},
                                clear=False,
                            ):
                                self.assertEqual(0, node_agent.main(arguments))
                                self.assertNotIn("HY2PANEL_STATS_SECRET", os.environ)
        stats_client.assert_called_once_with(
            "http://127.0.0.1:19997", "s" * 32
        )
        protocol_client.assert_called_once()
        spool.assert_called_once_with(Path("/root/spool"))
        state.assert_called_once_with(Path("/root/protocol.json"))
        cycle.run_once.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
