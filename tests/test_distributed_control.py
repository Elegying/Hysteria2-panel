import base64
import json
import sqlite3
import stat
import tempfile
import threading
import unittest
from pathlib import Path

import node_agent
from hy2panel.distributed import (
    DistributedControlService,
    NodeRequestRejected,
    canonical_node_request,
)
from hysteria2_panel import Database


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
            self.snapshot(self.nodes[0], 14, observedAt=self.now[0] - 6),
            self.snapshot(self.nodes[0], 15, trafficAckedAt=self.now[0] - 6),
            self.snapshot(self.nodes[0], 16, online={"unknown": 1}),
            self.snapshot(self.nodes[0], 17, online={"bad": -1}),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(NodeRequestRejected):
                    self.service.accept_online_snapshot(
                        payload, remote_ip="203.0.113.1"
                    )


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
        self.now[0] += 6
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


class NodeCommandTests(DistributedControlCase):
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


class NodeAgentProtocolTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
