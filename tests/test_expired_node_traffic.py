"""Expired records retain evidence without starving valid accounting batches."""
import hashlib
from pathlib import Path
import unittest
from unittest import mock

import node_agent
from hy2panel.distributed import MAX_TRAFFIC_BATCH_AGE_SECONDS, NodeRequestRejected
from tests.test_distributed_control import DistributedControlCase


class ExpiredNodeTrafficTests(unittest.TestCase):
    def setUp(self):
        self.fixture = DistributedControlCase('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = Path(self.fixture.temp_dir.name)
        self.spool = node_agent.DurableTrafficSpool(self.root / 'spool')
        self.state = node_agent.ProtocolState(self.root / 'state.json')
        self.user = self.fixture.db.create_proxy_user('alice')
        self.nonce = 20
        self.snapshots = []
        self.stats = mock.Mock(spec=node_agent.LocalStatsClient)
        self.stats.dump_streams.return_value = []
        self.stats.collect_and_clear.return_value = {'alice': {'tx': 1, 'rx': 2}}
        self.stats.online.return_value = {}
        self.protocol = mock.Mock(spec=node_agent.NodeProtocolClient)
        self.protocol.send_control_cycle.side_effect = self.send_cycle
        self.protocol.send_traffic.side_effect = self.send_traffic
        self.protocol.poll_commands.return_value = []
        self.cycle = node_agent.NodeControlCycle(
            self.protocol, self.stats, self.spool, self.state,
            clock=lambda: self.fixture.now[0],
        )
        self.expired = self.spool.enqueue({'alice': {'tx': 5, 'rx': 6}},
            self.fixture.now[0] - MAX_TRAFFIC_BATCH_AGE_SECONDS - 1)

    def envelope(self, extra):
        self.nonce += 1
        payload = self.fixture.common(self.fixture.nodes[0], self.nonce)
        payload.update(extra)
        return payload

    def send_cycle(self, batches, snapshot):
        self.snapshots.append(snapshot)
        try:
            return self.fixture.service.control_cycle(self.envelope({
                'cycleId': 'c' * 32, 'trafficBatches': batches, 'onlineSnapshot': snapshot,
                'commandPoll': {'requestId': 'd' * 32},
            }), '203.0.113.1')
        except NodeRequestRejected as error:
            raise node_agent.ProtocolError('central rejected batch') from error

    def send_traffic(self, batch):
        return self.fixture.service.apply_traffic_batch(self.envelope(batch), '203.0.113.1')

    def digest(self):
        return hashlib.sha256((self.spool.path / (self.expired['batchId'] + '.json')).read_bytes()).hexdigest()

    def connect_commands(self):
        self.protocol.poll_commands.side_effect = lambda: self.fixture.service.poll_commands(
            self.envelope({'requestId': 'f' * 32}), '203.0.113.1')['commands']
        self.protocol.ack_command.side_effect = lambda command_id, ok, error: self.fixture.service.ack_command(
            self.envelope({'commandId': command_id, 'ok': ok, 'errorCode': error}), '203.0.113.1')

    def test_expired_cycles_execute_leased_commands_and_keep_stop_protection(self):
        self.connect_commands()
        for legacy in (False, True):
            self.cycle._combined_supported = not legacy
            command = self.fixture.db.queue_node_command(
                self.fixture.nodes[0], 'KICK_USERS', {'users': ['alice']}, self.fixture.now[0])
            with self.assertRaises(node_agent.ExpiredTrafficError):
                self.cycle.run_once()
            self.assertFalse(self.state.command_completed(command['commandId']))
            self.fixture.now[0] += 10
            with self.assertRaises(node_agent.ExpiredTrafficError):
                self.cycle.run_once()
            self.assertTrue(self.state.command_completed(command['commandId']))
            with self.fixture.db._connect() as db:
                self.assertIsNotNone(db.execute('SELECT acked_at FROM node_commands WHERE command_id=?',
                    (command['commandId'],)).fetchone()[0])
            self.fixture.now[0] += 31
        self.assertEqual(4, self.stats.kick.call_count)
        self.protocol.send_online.assert_not_called()
        self.assertEqual([self.expired], self.spool.pending())
        self.cycle.stop_data_plane = mock.Mock()
        self.cycle.quiesce_traffic = mock.Mock()
        stop = self.fixture.db.queue_node_command(
            self.fixture.nodes[0], 'STOP_DATA_PLANE', {}, self.fixture.now[0])
        with self.assertRaises(node_agent.ExpiredTrafficError):
            self.cycle.run_once()
        self.cycle.stop_data_plane.assert_not_called()
        self.assertFalse(self.state.command_completed(stop['commandId']))
        self.assertFalse(self.state.data_plane_stopped())

    def test_local_ack_failure_does_not_discard_commands_from_combined_response(self):
        self.spool.ack(self.expired['batchId'])
        self.connect_commands()
        command = self.fixture.db.queue_node_command(
            self.fixture.nodes[0], 'KICK_USERS', {'users': ['alice']}, self.fixture.now[0])
        with mock.patch.object(self.spool, 'ack', side_effect=OSError('unlink unavailable')):
            with self.assertRaises(OSError):
                self.cycle.run_once()
            self.assertFalse(self.state.command_completed(command['commandId']))
            self.assertEqual(1, len(self.spool.pending()))
            self.spool.max_entries = 1
            self.fixture.now[0] += 10
            with self.assertRaises(OSError):
                self.cycle.run_once()
        self.assertEqual([mock.call(['alice'])] * 2, self.stats.kick.call_args_list)
        self.assertTrue(self.state.command_completed(command['commandId']))
        self.assertEqual(1, len(self.spool.pending()))
        self.protocol.poll_commands.assert_not_called()

    def test_lost_command_ack_retries_confirmation_without_reexecuting(self):
        self.connect_commands()
        command = self.fixture.db.queue_node_command(
            self.fixture.nodes[0], 'KICK_USERS', {'users': ['alice']}, self.fixture.now[0])
        with self.assertRaises(node_agent.ExpiredTrafficError):
            self.cycle.run_once()
        self.assertFalse(self.state.command_completed(command['commandId']))
        self.fixture.now[0] += 10
        acknowledge = self.protocol.ack_command.side_effect
        self.protocol.ack_command.side_effect = OSError('lost command acknowledgement')
        with self.assertRaises(OSError):
            self.cycle.run_once()
        self.assertTrue(self.state.command_completed(command['commandId']))
        self.fixture.now[0] += 31
        self.protocol.ack_command.side_effect = acknowledge
        self.cycle.state = node_agent.ProtocolState(self.state.path)
        with self.assertRaises(node_agent.ExpiredTrafficError):
            self.cycle.run_once()
        self.assertEqual([mock.call(['alice'])] * 2, self.stats.kick.call_args_list)
        with self.fixture.db._connect() as db:
            self.assertIsNotNone(db.execute('SELECT acked_at FROM node_commands WHERE command_id=?',
                (command['commandId'],)).fetchone()[0])

    def test_deferred_snapshot_failure_still_executes_combined_commands(self):
        self.spool.ack(self.expired['batchId'])
        self.connect_commands()
        command = self.fixture.db.queue_node_command(
            self.fixture.nodes[0], 'KICK_USERS', {'users': ['alice']}, self.fixture.now[0])
        with mock.patch('node_agent.CONTROL_CYCLE_PAYLOAD_BUDGET_BYTES', 220), \
             mock.patch.object(self.cycle, 'refresh_snapshot', side_effect=OSError('snapshot unavailable')) as refresh:
            with self.assertRaises(OSError):
                self.cycle.run_once()
            self.assertFalse(self.state.command_completed(command['commandId']))
            self.fixture.now[0] += 10
            with self.assertRaises(OSError):
                self.cycle.run_once()
        self.assertEqual(2, refresh.call_count)
        self.assertEqual([mock.call(['alice'])] * 2, self.stats.kick.call_args_list)
        self.assertTrue(self.state.command_completed(command['commandId']))
        self.assertEqual([], self.spool.pending())
        self.protocol.poll_commands.assert_not_called()

    def test_combined_and_legacy_upload_valid_batches_while_retaining_expired(self):
        self.assertEqual(MAX_TRAFFIC_BATCH_AGE_SECONDS, node_agent.MAX_TRAFFIC_BATCH_AGE_SECONDS)
        for legacy in (False, True):
            self.cycle._combined_supported = not legacy
            for _ in range(3):
                with self.assertRaises(node_agent.ExpiredTrafficError):
                    self.cycle.run_once()
                self.fixture.now[0] += 1
            self.assertEqual([self.expired], self.spool.pending())
        account = self.fixture.db.get_proxy_user(self.user['id'])
        self.assertEqual((6, 12), (account['tx_bytes'], account['rx_bytes']))
        self.assertTrue(all(snapshot is None for snapshot in self.snapshots))
        self.protocol.send_online.assert_not_called()
        with self.assertRaises(node_agent.ExpiredTrafficError):
            self.cycle.refresh_snapshot()
        with self.assertRaises(NodeRequestRejected):
            self.send_traffic(self.expired)  # The central replay age gate still applies.

    def test_reconciliation_requires_expiry_and_exact_digest_and_keeps_archive(self):
        with self.assertRaisesRegex(node_agent.ProtocolError, 'digest'):
            self.spool.reconcile(self.expired['batchId'], '0' * 64, self.fixture.now[0])
        current = self.spool.enqueue({}, self.fixture.now[0])
        with self.assertRaisesRegex(node_agent.ProtocolError, 'expired'):
            self.spool.reconcile(current['batchId'], '0' * 64, self.fixture.now[0])
        self.spool.ack(current['batchId'])
        original = (self.spool.path / (self.expired['batchId'] + '.json')).read_bytes()
        self.spool.reconcile(self.expired['batchId'], self.digest(), self.fixture.now[0])
        archive = self.root / 'spool.reconciled' / (self.expired['batchId'] + '.json')
        self.assertEqual(original, archive.read_bytes())
        self.assertEqual(0o600, archive.stat().st_mode & 0o777)
        self.assertEqual([], self.spool.pending())
        self.cycle.run_once()
        self.assertIsNotNone(self.snapshots[-1])

    def test_archive_failure_retains_original_and_retry_survives_restart(self):
        digest = self.digest()
        ack = self.spool.ack
        with mock.patch.object(node_agent.DurableTrafficSpool, 'persist_collections',
                               side_effect=OSError('archive storage unavailable')):
            with self.assertRaises(OSError):
                self.spool.reconcile(self.expired['batchId'], digest, self.fixture.now[0])
        self.assertEqual([self.expired], self.spool.pending())
        with mock.patch.object(self.spool, 'ack', side_effect=OSError('interrupted after archive')):
            with self.assertRaises(OSError):
                self.spool.reconcile(self.expired['batchId'], digest, self.fixture.now[0])
        self.assertEqual([self.expired], self.spool.pending())
        self.spool = node_agent.DurableTrafficSpool(self.spool.path)
        self.spool.reconcile(self.expired['batchId'], digest, self.fixture.now[0])
        self.assertEqual([], self.spool.pending())
        self.assertFalse(ack(self.expired['batchId']))

    def test_archive_symlink_is_rejected_and_cli_requires_confirmation(self):
        (self.root / 'spool.reconciled').symlink_to(self.spool.path, target_is_directory=True)
        with self.assertRaisesRegex(node_agent.ProtocolError, 'unsafe'):
            self.spool.reconcile(self.expired['batchId'], self.digest(), self.fixture.now[0])
        with mock.patch('sys.stderr'):
            self.assertEqual(2, node_agent.main(['reconcile-traffic', '--spool-dir', str(self.spool.path),
                '--batch-id', self.expired['batchId'], '--sha256', self.digest()]))
        self.assertEqual([self.expired], self.spool.pending())

    def test_full_spool_can_drain_valid_entries_without_publishing_online(self):
        # No capacity for another collection: valid backlog must still drain.
        self.spool.enqueue({'alice': {'tx': 3, 'rx': 4}}, self.fixture.now[0])
        self.spool.max_entries = 2
        with self.assertRaises(node_agent.ExpiredTrafficError):
            self.cycle.run_once()
        self.stats.collect_and_clear.assert_not_called()
        self.assertEqual([self.expired], self.spool.pending())
        self.assertEqual(3, self.fixture.db.get_proxy_user(self.user['id'])['tx_bytes'])

    def test_refresh_command_cannot_publish_fresh_snapshot_over_unsettled_traffic(self):
        self.spool.ack(self.expired['batchId'])
        self.state.set_traffic_ack(self.fixture.now[0])
        self.cycle._combined_supported = False
        self.protocol.send_traffic.side_effect = OSError('central traffic upload unavailable')
        command = {'commandId': 'e' * 32, 'kind': 'REFRESH_SNAPSHOT', 'payload': {}}
        self.protocol.poll_commands.return_value = [command]
        with self.assertRaises(OSError):
            self.cycle.run_once()
        self.assertEqual(1, len(self.spool.pending()))
        self.protocol.send_online.assert_not_called()
        self.protocol.ack_command.assert_called_once_with('e' * 32, False, 'EXECUTION_FAILED')
        self.assertFalse(self.state.command_completed('e' * 32))
        self.protocol.send_traffic.side_effect = self.send_traffic
        self.cycle._upload_pending()
        self.protocol.send_online.return_value = {'sequence': 1}
        self.cycle.refresh_snapshot()
        self.protocol.send_online.assert_called_once()


if __name__ == '__main__':
    unittest.main()
