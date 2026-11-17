"""Maintenance refusal is actionable without disclosing exception details."""
import unittest
from unittest import mock

import node_agent


class OperationErrorCodeTests(unittest.TestCase):
    def test_drain_refusal_is_distinct_from_other_failures_and_never_completed(self):
        for error, code in [
            (node_agent.SessionsNotDrainedError('live sessions'), 'SESSIONS_NOT_DRAINED'),
            (OSError('private details'), 'EXECUTION_FAILED'),
        ]:
            with self.subTest(code=code):
                client, state = mock.Mock(), mock.Mock()
                state.command_completed.return_value = False
                cycle = node_agent.NodeControlCycle(client, mock.Mock(), mock.Mock(), state)
                command = {'commandId': 'a' * 32, 'kind': 'RESTART_SERVICE'}
                with mock.patch.object(cycle, '_run_combined', return_value=([command], None)), mock.patch.object(
                    node_agent, 'execute_control_command', side_effect=error
                ):
                    cycle.run_once()
                client.ack_command.assert_called_once_with('a' * 32, False, code)
                state.record_command_completed.assert_not_called()
