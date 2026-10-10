"""A lost ACK cannot strand independent commands leased in the same response."""
import unittest
from unittest import mock

import node_agent
from tests import test_expired_node_traffic


class CommandAckIsolationTests(unittest.TestCase):
    def check_batch(self, legacy, first_state):
        fixture = test_expired_node_traffic.ExpiredNodeTrafficTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.spool.ack(fixture.expired["batchId"])
        fixture.stats.collect_and_clear.return_value = {}
        fixture.connect_commands()
        fixture.protocol.send_online.side_effect = lambda sequence, online, ack: (
            fixture.fixture.service.accept_online_snapshot(fixture.envelope({
                "snapshotId": "a" * 32, "sequence": sequence,
                "observedAt": fixture.fixture.now[0], "trafficAckedAt": ack,
                "online": online,
            }), "203.0.113.1"))
        fixture.cycle._combined_supported = not legacy
        commands = [fixture.fixture.db.queue_node_command(
            fixture.fixture.nodes[0], "KICK_USERS", {"users": [name]},
            fixture.fixture.now[0] + index) for index, name in enumerate(("alice", "bob"))]
        fixture.fixture.now[0] += 2
        fixture.cycle.run_once()
        self.assertTrue(all(not fixture.state.command_completed(c["commandId"]) for c in commands))
        fixture.protocol.ack_command.assert_not_called()
        fixture.fixture.now[0] += 10
        fixture.stats.kick.reset_mock()
        if first_state == "completed":
            fixture.state.record_command_completed(commands[0]["commandId"], fixture.fixture.now[0])
        elif first_state == "execution-failed":
            fixture.stats.kick.side_effect = [node_agent.ProtocolError("local kick failed"), None]
        acknowledge = fixture.protocol.ack_command.side_effect

        def lost_first_ack(command_id, ok, error):
            if command_id == commands[0]["commandId"]:
                raise OSError("first ACK unavailable")
            return acknowledge(command_id, ok, error)

        fixture.protocol.ack_command.side_effect = lost_first_ack
        with self.assertRaisesRegex(OSError, "first ACK unavailable"):
            fixture.cycle.run_once()
        expected = [mock.call(["bob"])] if first_state == "completed" else [
            mock.call(["alice"]), mock.call(["bob"])]
        self.assertEqual(expected, fixture.stats.kick.call_args_list)
        self.assertTrue(fixture.state.command_completed(commands[1]["commandId"]))
        self.assertEqual(first_state != "execution-failed",
                         fixture.state.command_completed(commands[0]["commandId"]))
        fixture.protocol.ack_command.assert_any_call(commands[0]["commandId"],
            first_state != "execution-failed",
            "EXECUTION_FAILED" if first_state == "execution-failed" else "")
        fixture.fixture.now[0] += 31
        fixture.protocol.ack_command.side_effect = acknowledge
        fixture.stats.kick.side_effect = None
        fixture.cycle.state = node_agent.ProtocolState(fixture.state.path)
        fixture.cycle.run_once()
        # Successful effects are never repeated after restarting before re-ACK.
        if first_state == "execution-failed":
            expected.append(mock.call(["alice"]))
            self.assertFalse(fixture.state.command_completed(commands[0]["commandId"]))
            fixture.fixture.now[0] += 10
            fixture.cycle.run_once()
            expected.append(mock.call(["alice"]))
        self.assertEqual(expected, fixture.stats.kick.call_args_list)
        with fixture.fixture.db._connect() as connection:
            rows = connection.execute("SELECT acked_at FROM node_commands").fetchall()
        self.assertEqual(2, len(rows))
        self.assertTrue(all(row["acked_at"] is not None for row in rows))

    def test_executed_command_ack_failure_does_not_block_later_commands(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.check_batch(legacy, "executed")

    def test_cached_command_ack_failure_does_not_block_later_commands(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.check_batch(legacy, "completed")

    def test_failed_execution_ack_failure_does_not_block_later_commands(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.check_batch(legacy, "execution-failed")


if __name__ == "__main__":
    unittest.main()
