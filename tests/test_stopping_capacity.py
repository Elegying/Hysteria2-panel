"""Stopping nodes keep their live device reservations until stop is confirmed."""
from tests import test_distributed_control as distributed_tests
from hy2panel.distributed import MAX_STATE_AGE_SECONDS, NodeRequestRejected
from hysteria2_panel import NODE_HEARTBEAT_FRESHNESS_SECONDS


class StoppingCapacityTests(distributed_tests.DistributedControlCase):
    def setUp(self):
        super().setUp()
        self.user = self.db.create_proxy_user('alice', device_limit=1)
        self.serial = 100
        self.sequences = {node: 0 for node in self.nodes}
        with self.db._connect() as connection:
            connection.execute("UPDATE nodes SET data_plane_state = 'dns_admitted'")
        self.refresh(self.nodes[0], {'alice': 1})
        self.refresh(self.nodes[1], {})

    def next_nonce(self):
        self.serial += 1
        return self.serial

    def refresh(self, node, online):
        self.sequences[node] += 1
        return self.service.accept_online_snapshot(
            self.snapshot(node, self.next_nonce(), sequence=self.sequences[node], online=online),
            remote_ip='203.0.113.{}'.format(int(node, 16)),
        )

    def auth(self, node):
        payload = self.common(node, self.next_nonce())
        payload.update(requestId='{:032x}'.format(self.serial), entrypoint='main',
                       auth=self.user['token'], tx=0)
        return self.service.authorize(payload, remote_ip='203.0.113.{}'.format(int(node, 16)))

    def begin_stop(self, kind):
        if kind == 'disconnect':
            return self.db.request_node_disconnect(self.nodes[0], 'admin', self.now[0])
        return self.db.request_node_stop(self.nodes[0], 'admin', self.now[0], emergency=True)

    def ack(self, command, ok):
        return self.db.ack_node_command(
            self.nodes[0], command['commandId'], ok, '' if ok else 'FAILED',
            '{:064x}'.format(self.next_nonce()), self.now[0],
        )

    def check_stop_until_ack(self, kind):
        self.assertFalse(self.auth(self.nodes[1])['ok'])
        command = self.begin_stop(kind)
        with self.db._connect() as connection:
            row = connection.execute(
                'SELECT delivered_at, acked_at FROM node_commands WHERE command_id = ?',
                (command['commandId'],),
            ).fetchone()
            self.assertEqual((None, None), tuple(row))
        self.assertFalse(self.auth(self.nodes[1])['ok'])
        self.assertFalse(self.db.authorize_local_participant('alice', {}, self.now[0]))
        with self.assertRaises(NodeRequestRejected):
            self.auth(self.nodes[0])
        # Stopping does not block its last settlement or online observations.
        self.now[0] += 1
        self.refresh(self.nodes[0], {'alice': 1})
        payload = self.common(self.nodes[0], self.next_nonce())
        payload.update(batchId='{:032x}'.format(self.serial), observedAt=self.now[0],
                       traffic={'alice': {'tx': 10, 'rx': 20}})
        self.assertTrue(self.service.apply_traffic_batch(
            payload, remote_ip='203.0.113.1')['committed'])
        self.assertFalse(self.ack(command, False))
        self.assertFalse(self.auth(self.nodes[1])['ok'])
        self.assertFalse(self.db.authorize_local_participant('alice', {}, self.now[0]))
        self.assertTrue(self.ack(command, True))
        self.assertTrue(self.auth(self.nodes[1])['ok'])
        with self.assertRaises(NodeRequestRejected):
            self.auth(self.nodes[0])

    def test_disconnect_keeps_devices_until_successful_uninstall_ack(self):
        self.check_stop_until_ack('disconnect')

    def test_emergency_stop_keeps_devices_until_successful_stop_ack(self):
        self.check_stop_until_ack('stop')

    def test_stale_stopping_node_fails_closed_and_offline_revocation_unblocks(self):
        self.begin_stop('disconnect')
        self.now[0] += MAX_STATE_AGE_SECONDS + 1
        self.refresh(self.nodes[1], {})
        with self.assertRaises(NodeRequestRejected):
            self.auth(self.nodes[1])
        self.assertFalse(self.db.authorize_local_participant('alice', {}, self.now[0]))
        # Expiration is not evidence that old QUIC connections stopped. The
        # existing explicit offline revocation remains the recovery path.
        self.now[0] += NODE_HEARTBEAT_FRESHNESS_SECONDS + 1
        self.assertTrue(self.db.delete_node_pairing(self.nodes[0], 'admin', self.now[0]))
        self.refresh(self.nodes[1], {})
        self.assertTrue(self.auth(self.nodes[1])['ok'])

    def test_local_capacity_is_released_after_confirmed_stop(self):
        command = self.begin_stop('stop')
        self.assertFalse(self.db.authorize_local_participant('alice', {}, self.now[0]))
        self.assertTrue(self.ack(command, True))
        self.assertTrue(self.db.authorize_local_participant('alice', {}, self.now[0]))
