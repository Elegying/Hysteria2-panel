"""Local stats larger than node-command inputs settle atomically and recover."""
import json
import sqlite3
import unittest
from unittest import mock

import hysteria2_panel as panel
from tests.test_distributed_control import DistributedControlCase


class LocalQuotaBatchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = DistributedControlCase('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        self.names = ['limit-{:04}'.format(index) for index in range(1001)]
        for name in self.names:
            self.db.create_proxy_user(name, traffic_limit_bytes=1)
        self.requests = []

    def client(self, names, port):
        traffic = {name: {'tx': 1, 'rx': 1} for name in names}
        self.assertLess(len(json.dumps(traffic).encode()), panel.MAX_STATS_RESPONSE_BYTES)
        client = panel.HysteriaStatsClient('http://127.0.0.1:{}'.format(port), 'fixture-only')
        remaining = [traffic]

        def request(path, data=None):
            self.requests.append((port, path, data))
            if path == '/traffic?clear=1':
                return remaining.pop() if remaining else {}
            if path == '/online':
                return {name: 1 for name in names}
            return {'streams': []} if path == '/dump/streams' else {}

        patch = mock.patch.object(client, '_request', side_effect=request)
        patch.start()
        self.addCleanup(patch.stop)
        return client

    def assert_settled(self, manager):
        self.assertFalse(manager.pending_traffic_path.exists())
        with self.db._connect() as connection:
            self.assertEqual(2002, connection.execute('SELECT SUM(tx_bytes+rx_bytes) FROM proxy_users').fetchone()[0])
            self.assertEqual(1, connection.execute('SELECT COUNT(*) FROM applied_traffic_batches').fetchone()[0])
            self.assertEqual(2002, connection.execute('SELECT SUM(tx_bytes+rx_bytes) FROM origin_traffic_daily').fetchone()[0])
            commands = connection.execute('SELECT node_id,payload,quota_generations FROM node_commands').fetchall()
        self.assertEqual(22, len(commands))
        for node_id in self.fixture.nodes:
            chunks = [json.loads(row['payload'])['users'] for row in commands if row['node_id'] == node_id]
            self.assertEqual(self.names, sorted(name for chunk in chunks for name in chunk))
            self.assertTrue(all(1 <= len(chunk) <= 100 for chunk in chunks))
        for row in commands:
            self.assertEqual(set(json.loads(row['payload'])['users']), set(json.loads(row['quota_generations'])))

    def test_combined_local_response_over_one_thousand_users_settles_and_kicks(self):
        clients = [self.client(self.names[:501], 19997), self.client(self.names[501:], 19995)]
        manager = panel.UsageManager(self.db, panel.CombinedHysteriaStatsClient(*clients))
        manager.collect_once()
        self.assert_settled(manager)
        kicks = [name for _port, path, data in self.requests if path == '/kick' for name in data]
        self.assertEqual(self.names, sorted(kicks))
        manager.collect_once()
        self.assert_settled(manager)
        # Public broadcasts and individual wire commands retain their bounds.
        with self.assertRaises(ValueError):
            self.db.queue_kick_users_on_ready_nodes(self.names)
        user = self.db.get_proxy_user_by_name(self.names[0])
        self.db.update_proxy_user_limits(user['id'], user['device_limit'], 10)
        payload = self.fixture.common(self.fixture.nodes[0], 61)
        payload['requestId'] = 'a' * 32
        polled = self.fixture.service.poll_commands(payload, '203.0.113.1')['commands']
        self.assertEqual(self.names[1:], sorted(name for command in polled for name in command['payload']['users']))

    def test_local_only_deployment_does_not_require_remote_command_targets(self):
        for node_id in self.fixture.nodes:
            self.db.delete_node_pairing(node_id, 'fixture-admin')
        manager = panel.UsageManager(self.db, self.client(self.names, 19997))
        manager.collect_once()
        self.assertFalse(manager.pending_traffic_path.exists())
        with self.db._connect() as connection:
            self.assertEqual(2002, connection.execute('SELECT SUM(tx_bytes+rx_bytes) FROM proxy_users').fetchone()[0])
            self.assertEqual(0, connection.execute('SELECT COUNT(*) FROM node_commands').fetchone()[0])

    def test_later_command_chunk_failure_rolls_back_and_journal_recovers_after_restart(self):
        client = self.client(self.names, 19997)
        manager = panel.UsageManager(self.db, client)
        with self.db._connect() as connection:
            connection.execute("""CREATE TRIGGER fail_tail_command BEFORE INSERT ON node_commands
                WHEN NEW.payload LIKE '%limit-1000%'
                BEGIN SELECT RAISE(ABORT, 'command write unavailable'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            manager.collect_once()
        self.assertTrue(manager.pending_traffic_path.is_file())
        with self.db._connect() as connection:
            self.assertEqual(0, connection.execute('SELECT SUM(tx_bytes+rx_bytes) FROM proxy_users').fetchone()[0])
            self.assertEqual(0, connection.execute('SELECT COUNT(*) FROM node_commands').fetchone()[0])
            self.assertEqual(0, connection.execute('SELECT COUNT(*) FROM applied_traffic_batches').fetchone()[0])
            self.assertEqual(0, connection.execute('SELECT COUNT(*) FROM origin_traffic_daily').fetchone()[0])
            connection.execute('DROP TRIGGER fail_tail_command')
        self.assertEqual(1, sum(path == '/traffic?clear=1' for _port, path, _data in self.requests))
        recovered = panel.UsageManager(self.db, client)
        recovered.collect_once()
        self.assert_settled(recovered)
        recovered.collect_once()
        self.assert_settled(recovered)


if __name__ == '__main__':
    unittest.main()
