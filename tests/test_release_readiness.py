"""Cross-node availability, bounded online state and stale quota commands."""

import json
from pathlib import Path
from unittest import mock

import node_agent
from hy2panel.distributed import MAX_STATE_AGE_SECONDS, NodeRequestRejected, _online_mapping
from hysteria2_panel import Database, seconds_to_user_traffic_month, user_traffic_month
from tests.test_distributed_control import DistributedControlCase


class ReleaseReadinessTests(DistributedControlCase):
    def auth(self, node, nonce, token):
        payload = self.common(node, nonce)
        payload.update(requestId=format(nonce, "032x"), entrypoint="main", auth=token, tx=0)
        return self.service.authorize(payload, remote_ip="203.0.113.2")["ok"]

    def test_deleted_idle_session_does_not_block_other_nodes_or_restore_identity(self):
        retired = self.db.create_proxy_user("retired-idle")
        survivor = self.db.create_proxy_user("survivor")
        self.accept_empty_snapshots()
        self.assertTrue(self.auth(self.nodes[1], 30, survivor["token"]))
        self.db.delete_proxy_user(retired["id"])
        self.now[0] += MAX_STATE_AGE_SECONDS + 1
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[0], 31, sequence=2, online={"retired-idle": 2, "survivor": 1}),
            remote_ip="203.0.113.1",
        )
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[1], 32, sequence=2), remote_ip="203.0.113.2"
        )
        self.assertEqual({"survivor": 1}, self.db.node_online_counts(self.nodes[0]))
        self.assertTrue(self.auth(self.nodes[1], 33, survivor["token"]))
        self.assertFalse(self.auth(self.nodes[1], 34, retired["token"]))
        with self.assertRaises(NodeRequestRejected):
            self.service.accept_online_snapshot(
                self.snapshot(self.nodes[0], 35, sequence=3,
                              online={"retired-idle": 1, "never-created": 1}),
                remote_ip="203.0.113.1",
            )
        self.assertEqual({"survivor": 1}, self.db.node_online_counts(self.nodes[0]))

    def test_1001_online_accounts_settle_traffic_and_preserve_every_device_count(self):
        names = ["用户" * 29 + "{:06d}".format(i) for i in range(1001)]
        for name in names:
            self.db.create_proxy_user(name)
        payload = self.common(self.nodes[0], 91)
        payload.update(
            cycleId="9" * 32,
            trafficBatches=[{"batchId": "8" * 32, "observedAt": self.now[0],
                             "traffic": {names[-1]: {"tx": 10, "rx": 20}}}],
            onlineSnapshot={"snapshotId": "7" * 32, "sequence": 1,
                            "observedAt": self.now[0], "trafficAckedAt": self.now[0],
                            "online": {name: 2 for name in names}},
            commandPoll={"requestId": "6" * 32},
        )
        command = self.db.queue_node_command(self.nodes[0], "REFRESH_SNAPSHOT", {}, self.now[0])
        result = self.service.control_cycle(payload, remote_ip="203.0.113.1")
        self.assertTrue(result["traffic"][0]["committed"])
        self.assertEqual(command["commandId"], result["commands"][0]["commandId"])
        counts = self.db.node_online_counts(self.nodes[0])
        self.assertEqual({name: 2 for name in names}, counts)
        user = self.db.get_proxy_user_by_name(names[-1])
        self.assertEqual(30, user["tx_bytes"] + user["rx_bytes"])
        # The standalone endpoint uses the same byte bound and full-state semantics.
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[0], 92, sequence=2, online=counts),
            remote_ip="203.0.113.1",
        )
        self.assertEqual(counts, self.db.node_online_counts(self.nodes[0]))

    def test_online_byte_bound_and_invalid_counts_remain_fail_closed(self):
        self.assertFalse(_online_mapping({"a": True}))
        self.assertFalse(_online_mapping({"a": 101}))
        self.assertFalse(_online_mapping({"a": -1}))
        self.assertFalse(_online_mapping({"bad\ud800": 1}))
        oversized = {"用户" * 29 + "{:06d}".format(i): 1 for i in range(4000)}
        self.assertFalse(_online_mapping(oversized))

    def exhaust(self, names):
        for name in names:
            self.db.create_proxy_user(name, traffic_limit_bytes=10)
        result = self.db.apply_node_traffic_batch(
            self.nodes[0], "a" * 32, {name: {"tx": 5, "rx": 5} for name in names},
            "b" * 64, self.now[0],
        )
        self.assertTrue(result["committed"])

    def test_monthly_reset_cancels_old_quota_kicks_but_keeps_security_kicks(self):
        self.exhaust(["monthly"])
        self.db.queue_kick_users_on_ready_nodes(["monthly"], self.now[0])
        with self.db._connect() as connection:
            connection.execute("UPDATE user_traffic_reset_state SET period = ?",
                               (user_traffic_month(self.now[0]),))
        boundary = int(self.now[0] + seconds_to_user_traffic_month(self.now[0]))
        self.assertTrue(self.db.reset_monthly_traffic_if_due(boundary))
        for index, node in enumerate(self.nodes):
            commands = self.db.poll_node_commands(node, str(index) * 64, boundary + 1)
            self.assertEqual([{"users": ["monthly"]}], [c["payload"] for c in commands])
        with self.db._connect() as connection:
            cancelled = connection.execute(
                "SELECT COUNT(*) FROM node_commands WHERE last_error = 'QUOTA_SUPERSEDED'"
            ).fetchone()[0]
        self.assertEqual(2, cancelled)
        user = self.db.get_proxy_user_by_name("monthly")
        self.assertEqual(0, user["tx_bytes"] + user["rx_bytes"])
        self.assertTrue(user["enabled"])

    def test_quota_command_filters_only_restored_members_after_restart(self):
        self.exhaust(["restored", "still-exhausted"])
        restored = self.db.get_proxy_user_by_name("restored")
        self.db.update_proxy_user_limits(restored["id"], 3, 100)
        db = Database(self.db_path, b"d" * 32)
        db.initialize()
        commands = db.poll_node_commands(self.nodes[0], "c" * 64, self.now[0] + 1)
        self.assertEqual([{"users": ["still-exhausted"]}], [c["payload"] for c in commands])

    def test_new_exhaustion_after_reset_gets_a_new_command(self):
        self.exhaust(["again"])
        first = self.db.poll_node_commands(self.nodes[0], "c" * 64, self.now[0])
        self.db.reset_all_traffic()
        current = self.db.get_proxy_user_by_name("again")
        with mock.patch("hysteria2_panel.time.time", return_value=self.now[0] + 1):
            self.db.update_proxy_user_limits(current["id"], 3, 10, used_traffic_bytes=10)
        commands = self.db.poll_node_commands(self.nodes[0], "d" * 64, self.now[0] + 10)
        self.assertEqual(1, len(commands))
        self.assertNotEqual(first[0]["commandId"], commands[0]["commandId"])
        self.assertEqual({"users": ["again"]}, commands[0]["payload"])

    def test_large_snapshot_is_sent_after_traffic_instead_of_starving(self):
        root = Path(self.temp_dir.name)
        spool = node_agent.DurableTrafficSpool(root / "spool", max_entries=4)
        state = node_agent.ProtocolState(root / "state.json")
        traffic = {"u{:063d}".format(i): {"tx": 2**63 - 1, "rx": 2**63 - 1}
                   for i in range(900)}
        for observed_at in range(self.now[0] - 4, self.now[0]):
            spool.enqueue(traffic, observed_at)
        online = {"u{:063d}".format(i): 1 for i in range(1001)}
        stats = mock.Mock(spec=node_agent.LocalStatsClient)
        stats.online.return_value = online
        calls = []
        protocol = mock.Mock()

        def send_cycle(batches, snapshot):
            self.assertIsNone(snapshot)
            self.assertEqual(4, len(batches))
            size = len(json.dumps({"trafficBatches": batches, "onlineSnapshot": snapshot},
                                  separators=(",", ":")).encode())
            self.assertLessEqual(size, node_agent.CONTROL_CYCLE_PAYLOAD_BUDGET_BYTES)
            calls.append("traffic")
            return {"traffic": [{"batchId": b["batchId"], "committed": True} for b in batches],
                    "acceptedAt": self.now[0], "online": None, "commands": []}

        def send_online(sequence, counts, ack):
            self.assertEqual([], spool.pending())
            self.assertEqual(online, counts)
            self.assertEqual(self.now[0], ack)
            calls.append("online")
            return {"sequence": sequence}

        protocol.send_control_cycle.side_effect = send_cycle
        protocol.send_online.side_effect = send_online
        cycle = node_agent.NodeControlCycle(protocol, stats, spool, state, clock=lambda: self.now[0])
        cycle.run_once()
        self.assertEqual(["traffic", "online"], calls)
        stats.collect_and_clear.assert_not_called()
