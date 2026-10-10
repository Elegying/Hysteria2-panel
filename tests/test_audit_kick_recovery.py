"""Real central leases combined with Hysteria's one-consumer kick semantics."""

from pathlib import Path
from unittest import mock

import node_agent
from tests.test_distributed_control import DistributedControlCase


class KickRecoveryTests(DistributedControlCase):
    def test_multiple_connections_retry_across_restart_then_ack_once_empty(self):
        user = self.db.create_proxy_user("audit-user", traffic_limit_bytes=10)
        self.db.apply_node_traffic_batch(
            self.nodes[0], "1" * 32, {user["name"]: {"tx": 11, "rx": 0}},
            "1" * 64, self.now[0], observed_at=self.now[0],
        )
        root = Path(self.temp_dir.name)
        state = node_agent.ProtocolState(root / "kick-state.json")

        class Stats:
            connected = 3
            marker = False

            def online(self):
                return {"audit-user": self.connected}

            def kick(self, users):
                self.marker = "audit-user" in users and self.connected > 0

            def traffic_event(self):
                if self.marker:
                    self.marker = False
                    self.connected -= 1

        stats = Stats()
        command_id = None
        for cycle in range(4):
            now = self.now[0] + cycle * 2
            commands = self.db.poll_node_commands(self.nodes[0], format(cycle + 2, "064x"), now)
            self.assertEqual(1, len(commands))
            command = commands[0]
            command_id = command["commandId"]
            self.assertFalse(state.command_completed(command_id))
            outcome = node_agent.execute_control_command(command, stats)
            if cycle < 3:
                self.assertEqual("deferred-ack", outcome)
                # A delayed event consumes only one marker, as in the real core.
                stats.traffic_event()
                state = node_agent.ProtocolState(root / "kick-state.json")
            else:
                self.assertIsNone(outcome)
                state.record_command_completed(command_id, now)
                self.assertTrue(self.db.ack_node_command(
                    self.nodes[0], command_id, True, "", "f" * 64, now,
                ))
        self.assertEqual(0, stats.connected)
        self.assertTrue(state.command_completed(command_id))
        self.assertEqual([], self.db.poll_node_commands(self.nodes[0], "e" * 64, now + 2))

    def test_pending_quota_kick_is_cancelled_after_allowance_is_restored(self):
        user = self.db.create_proxy_user("restored", traffic_limit_bytes=10)
        self.db.apply_node_traffic_batch(
            self.nodes[0], "1" * 32, {"restored": {"tx": 11, "rx": 0}},
            "1" * 64, self.now[0], observed_at=self.now[0],
        )
        self.assertEqual(1, len(self.db.poll_node_commands(self.nodes[0], "2" * 64, self.now[0])))
        self.db.update_proxy_user_limits(user["id"], 3, 100)
        self.assertEqual([], self.db.poll_node_commands(self.nodes[0], "3" * 64, self.now[0] + 2))

    def test_pending_kicks_do_not_starve_later_control_commands(self):
        for index in range(32):
            self.db.queue_node_command(
                self.nodes[0], "KICK_USERS", {"users": ["user-{}".format(index)]}, self.now[0]
            )
        first = self.db.poll_node_commands(self.nodes[0], "a" * 64, self.now[0])
        self.assertEqual(32, len(first))
        next_command = self.db.queue_node_command(
            self.nodes[0], "REFRESH_SNAPSHOT", {}, self.now[0] + 1
        )
        second = self.db.poll_node_commands(self.nodes[0], "b" * 64, self.now[0] + 2)
        self.assertEqual(next_command["commandId"], second[0]["commandId"])

    def test_security_drain_pauses_only_target_node_and_cannot_reuse_cached_allow(self):
        user = self.db.create_proxy_user("rotating", device_limit=100)
        self.accept_empty_snapshots()

        def authorize(node, request, nonce):
            return self.db.authorize_distributed_node(
                node, format(request, "032x"), user["token"], False, {},
                format(nonce, "064x"), self.now[0], 30,
            )["ok"]

        self.assertTrue(authorize(self.nodes[0], 20, 20))
        command = self.db.queue_node_command(
            self.nodes[0], "KICK_USERS", {"users": [user["name"]]}, self.now[0]
        )
        self.assertFalse(authorize(self.nodes[0], 20, 21))  # Retry of the cached allow.
        self.assertFalse(authorize(self.nodes[0], 22, 22))
        self.assertTrue(authorize(self.nodes[1], 23, 23))
        self.db.ack_node_command(self.nodes[0], command["commandId"], True, "", "f" * 64, self.now[0])
        self.assertTrue(authorize(self.nodes[0], 24, 24))

    def test_late_connection_restarts_the_quiet_window_and_restart_cannot_skip_it(self):
        root = Path(self.temp_dir.name)
        command = {"commandId": "a" * 32, "kind": "KICK_USERS", "payload": {"users": ["alice"]}}
        protocol = mock.Mock()
        protocol.send_control_cycle.return_value = {"commands": [command], "traffic": [], "acceptedAt": self.now[0]}
        stats = mock.Mock()
        stats.online.return_value = {}
        state = node_agent.ProtocolState(root / "quiet-state.json")
        state.set_data_plane_stopped(True)  # Isolate command processing from sampling.

        def create_cycle():
            return node_agent.NodeControlCycle(
                protocol, stats, node_agent.DurableTrafficSpool(root / "quiet-spool"), state,
                clock=lambda: self.now[0],
            )

        cycle = create_cycle()
        cycle.run_once()
        protocol.ack_command.assert_not_called()
        self.now[0] += 9
        stats.online.return_value = {"alice": 1}  # Previously issued auth arrives late.
        cycle.run_once()
        stats.online.return_value = {}
        cycle.run_once()
        self.now[0] += 5
        cycle = create_cycle()
        cycle.run_once()
        self.now[0] += 9
        cycle.run_once()
        protocol.ack_command.assert_not_called()
        self.now[0] += 1
        cycle.run_once()
        protocol.ack_command.assert_called_once_with(command["commandId"], True, "")
        self.assertTrue(state.command_completed(command["commandId"]))
