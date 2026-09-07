"""Accounting boundaries across delayed local journals and signed node batches."""
import datetime
import json
from unittest import mock

from tests import test_distributed_control as distributed_tests
from hysteria2_panel import Database, UsageManager


class LedgerBoundaryTests(distributed_tests.DistributedControlCase):
    def setUp(self):
        super().setUp()
        self.serial = 100
        self.local_origin = 'local:' + 'a' * 32

    def origin(self, source):
        return self.local_origin if source == 'local' else 'node:' + self.nodes[0]

    def settle(self, source, name, amount, observed_at, batch_id=None):
        self.serial += 1
        batch_id = batch_id or '{:032x}'.format(self.serial)
        traffic = {name: {'tx': 0, 'rx': amount}}
        if source == 'local':
            with mock.patch('hysteria2_panel.time.time', return_value=self.now[0]):
                applied = self.db.apply_traffic_batch(
                    batch_id, traffic, origin_id=self.local_origin,
                    origin_kind='local', origin_name='本机', observed_at=observed_at,
                )
            return {'committed': True, 'duplicate': not applied, 'batchId': batch_id}
        payload = self.common(self.nodes[0], self.serial)
        payload.update(batchId=batch_id, observedAt=observed_at, traffic=traffic)
        return self.service.apply_traffic_batch(payload, remote_ip='203.0.113.1')

    def machine_total(self, source):
        with self.db._connect() as connection:
            return connection.execute(
                'SELECT COALESCE(SUM(tx_bytes + rx_bytes), 0) '
                'FROM origin_traffic_daily WHERE origin_id = ?', (self.origin(source),),
            ).fetchone()[0]

    def check_reset_boundary(self, all_users):
        for source in ('local', 'remote'):
            with self.subTest(source=source):
                user = self.db.create_proxy_user(source)
                self.settle(source, source, 100, self.now[0])
                observed_at = self.now[0] + 1
                self.now[0] += 5
                reset_at = self.now[0]
                with mock.patch('hysteria2_panel.time.time', return_value=reset_at):
                    if all_users:
                        self.db.reset_all_traffic()
                    else:
                        self.db.reset_proxy_user_traffic(user['id'], expected_generation=0)
                # A fresh connection/manager must retain the adjustment boundary.
                self.db = Database(self.db_path, b'd' * 32)
                self.service.database = self.db
                self.now[0] += 1
                late = self.settle(source, source, 30, observed_at)
                self.assertTrue(late['committed'])
                self.assertTrue(self.settle(source, source, 30, observed_at,
                                            late['batchId'])['duplicate'])
                record = self.db.get_proxy_user(user['id'])
                self.assertEqual((0, 0), (record['tx_bytes'], record['rx_bytes']))
                self.assertEqual(130, self.machine_total(source))
                self.now[0] += 1
                self.settle(source, source, 20, self.now[0])
                record = self.db.get_proxy_user(user['id'])
                self.assertEqual(20, record['tx_bytes'] + record['rx_bytes'])
                self.assertEqual(150, self.machine_total(source))

    def test_single_user_reset_does_not_recharge_pending_history(self):
        self.check_reset_boundary(False)

    def test_all_users_reset_does_not_recharge_pending_history(self):
        self.check_reset_boundary(True)

    def test_deleted_users_still_settle_machine_usage_exactly_once(self):
        for source in ('local', 'remote'):
            with self.subTest(source=source):
                user = self.db.create_proxy_user(source)
                self.settle(source, source, 100, self.now[0])
                observed_at = self.now[0] + 1
                self.db.delete_proxy_user(user['id'])
                self.now[0] += 5
                late = self.settle(source, source, 30, observed_at)
                self.assertTrue(late['committed'])
                if source == 'remote':
                    self.assertEqual(1, late['unknownUsers'])
                self.assertTrue(self.settle(source, source, 30, observed_at,
                                            late['batchId'])['duplicate'])
                self.assertEqual(130, self.machine_total(source))
                with self.db._connect() as connection:
                    self.assertEqual(0, connection.execute(
                        'SELECT COUNT(*) FROM usage_origin_users WHERE user_name = ?',
                        (source,),
                    ).fetchone()[0])
                    self.assertEqual(0, connection.execute(
                        'SELECT COUNT(*) FROM proxy_users WHERE name = ?', (source,),
                    ).fetchone()[0])

    def test_late_batches_stay_in_observed_provider_cycle(self):
        for reset_day in (1, 15):
            for source in ('local', 'remote'):
                with self.subTest(reset_day=reset_day, source=source):
                    name = '{}-{}'.format(source, reset_day)
                    self.db.create_proxy_user(name)
                    boundary = int(datetime.datetime(
                        2033, 6, reset_day, tzinfo=datetime.timezone.utc,
                    ).timestamp())
                    self.now[0] = boundary + 1
                    self.db.set_origin_budget(self.origin(source), 10000, 80, 'admin',
                                              self.now[0], reset_day=reset_day)
                    self.settle(source, name, 30, boundary - 1)
                    budget = self.db.get_origin_budget(self.origin(source), self.now[0])
                    self.assertEqual(0, budget['used_bytes'])
                    self.settle(source, name, 20, boundary + 1)
                    self.assertEqual(40, self.db.get_origin_budget(
                        self.origin(source), self.now[0])['used_bytes'])

    def test_manual_provider_baseline_excludes_late_history_and_rolls_over(self):
        for source in ('local', 'remote'):
            with self.subTest(source=source):
                self.db.create_proxy_user(source)
                saved_at = int(datetime.datetime(
                    2033, 5, 18, 12, tzinfo=datetime.timezone.utc,
                ).timestamp())
                self.now[0] = saved_at - 5
                self.settle(source, source, 100, self.now[0])
                self.db.set_origin_budget(self.origin(source), 10000, 80, 'admin',
                                          saved_at, manual_used_bytes=5000, reset_day=15)
                self.now[0] = saved_at + 5
                for observed_at in (saved_at - 1, saved_at):
                    late = self.settle(source, source, 30, observed_at)
                    self.assertTrue(self.settle(source, source, 30, observed_at,
                                                late['batchId'])['duplicate'])
                self.assertEqual(5000, self.db.get_origin_budget(
                    self.origin(source), self.now[0])['used_bytes'])
                self.settle(source, source, 20, saved_at + 1)
                self.assertEqual(5040, self.db.get_origin_budget(
                    self.origin(source), self.now[0])['used_bytes'])
                self.assertEqual(180, self.machine_total(source))
                self.now[0] = int(datetime.datetime(
                    2033, 6, 15, tzinfo=datetime.timezone.utc,
                ).timestamp()) + 1
                # A previous-cycle batch must not enter the reset cycle, even
                # when it was sampled after the previous manual baseline.
                self.settle(source, source, 50, self.now[0] - 2)
                self.assertEqual(0, self.db.get_origin_budget(
                    self.origin(source), self.now[0])['used_bytes'])
                self.settle(source, source, 10, self.now[0])
                self.assertEqual(20, self.db.get_origin_budget(
                    self.origin(source), self.now[0])['used_bytes'])

    def test_local_pending_journal_replays_original_observation_after_restart(self):
        user = self.db.create_proxy_user('alice')
        original = self.now[0]
        self.now[0] += 5
        with mock.patch('hysteria2_panel.time.time', return_value=self.now[0]):
            self.db.reset_proxy_user_traffic(user['id'])
        journal = self.db_path.with_name('pending-traffic.json')
        journal.write_text(json.dumps({
            'batch_id': 'c' * 32, 'traffic': {'alice': {'tx': 10, 'rx': 20}},
            'domains': [], 'observed_at': original,
        }))
        manager = UsageManager(self.db, object(), wall_clock=lambda: self.now[0],
                               local_origin_id=self.local_origin)
        manager._flush_pending_traffic_locked()
        self.assertFalse(journal.exists())
        self.assertEqual(0, self.db.get_proxy_user(user['id'])['rx_bytes'])
        self.assertEqual(30, self.machine_total('local'))
        # Legacy journals without a timestamp remain readable; settlement time
        # is the only available observation, rather than inventing old dates.
        self.now[0] += 1
        journal.write_text(json.dumps({
            'batch_id': 'd' * 32, 'traffic': {'alice': {'tx': 1, 'rx': 2}},
        }))
        manager = UsageManager(self.db, object(), wall_clock=lambda: self.now[0],
                               local_origin_id=self.local_origin)
        with mock.patch('hysteria2_panel.time.time', return_value=self.now[0]):
            manager._flush_pending_traffic_locked()
        self.assertEqual(2, self.db.get_proxy_user(user['id'])['rx_bytes'])
        self.assertEqual(33, self.machine_total('local'))
