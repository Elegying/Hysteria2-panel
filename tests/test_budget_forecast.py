"""Single-count projections, membership changes and interface address display."""
import datetime
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hy2panel.budgets import budget_forecast
from hy2panel.dashboard import machine_forecasts
from hy2panel.operations import SystemMetrics
from hysteria2_panel import Database


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(Path(self.temp.name) / 'test.db', b'a' * 32)
        self.db.initialize()
        self.now = int(datetime.datetime(2033, 5, 18, tzinfo=datetime.timezone.utc).timestamp())
        self.local = 'local:' + 'a' * 32
        self.remote = 'node:' + 'b' * 32
        for origin, kind in ((self.local, 'local'), (self.remote, 'remote')):
            self.db.register_usage_origin(origin, kind, kind, created_at=self.now - 8 * 86400)
        with self.db._connect() as connection:
            for origin in (self.local, self.remote):
                connection.execute('INSERT INTO origin_traffic_daily VALUES (?, ?, ?, ?, ?)',
                                   (origin, '2033-05-17', 500, 200, self.now - 1))
            # Today must not dilute or inflate the completed-day average.
            connection.execute('INSERT INTO origin_traffic_daily VALUES (?, ?, ?, ?, ?)',
                               (self.local, '2033-05-18', 999999, 0, self.now))
        self.db.set_origin_budget(self.local, 1000, 80, 'admin', self.now,
                                  manual_used_bytes=0)

    def test_average_includes_zero_days_and_ignores_partial_today(self):
        self.assertEqual({'daily_bytes': 200, 'sample_days': 7},
                         self.db.recent_daily_traffic_average(self.now))
        with self.db._connect() as connection:
            connection.execute('UPDATE usage_origins SET created_at = ?', (self.now,))
        self.assertEqual({'daily_bytes': None, 'sample_days': 0},
                         self.db.recent_daily_traffic_average(self.now))

    def test_removal_recalculates_immediately_and_preserves_historical_average(self):
        app = SimpleNamespace(database=self.db,
                              usage_manager=SimpleNamespace(local_origin_id=self.local),
                              service_controller=SimpleNamespace(status=lambda: 'active'))
        with self.db._connect() as connection:
            connection.execute("""INSERT INTO nodes(node_id, name, status, policy_state,
                lifecycle_state, data_plane_state, created_at)
                VALUES (?, 'forecast-edge', 'pending_verification', 'protocol_ready',
                'active', 'dns_admitted', ?)""", ('b' * 32, self.now - 86400))
        first = machine_forecasts(app, self.db.list_nodes(), now=self.now)
        self.assertIn('5月28日', first[self.local]['text'])
        self.assertIn('2 台', first[self.local]['basis'])
        with mock.patch.object(self.db, 'recent_daily_traffic_average', wraps=self.db.recent_daily_traffic_average) as average:
            self.assertEqual(first, machine_forecasts(app, self.db.list_nodes(), now=self.now + 1))
            average.assert_not_called()
            self.db.delete_node_pairing('b' * 32, 'admin', self.now + 1)
            second = machine_forecasts(app, self.db.list_nodes(), now=self.now + 1)
            average.assert_called_once()
        self.assertIn('5月23日', second[self.local]['text'])
        self.assertIn('1 台', second[self.local]['basis'])
        self.assertEqual(200, self.db.recent_daily_traffic_average(self.now)['daily_bytes'])

    def test_reset_horizon_unlimited_zero_and_exhausted_states(self):
        budget = self.db.get_origin_budget(self.local, self.now)
        self.assertEqual('预计重置前够用', budget_forecast(budget, 1, 2, self.now))
        self.assertEqual('预计重置前够用', budget_forecast(budget, 1000 / 14, 1, self.now))
        self.assertIn('数据不足', budget_forecast(budget, None, 2, self.now))
        self.assertIn('近期无流量', budget_forecast(budget, 0, 2, self.now))
        self.assertIn('未参与供流', budget_forecast(budget, 200, 0, self.now))
        self.assertEqual('流量已用尽', budget_forecast(dict(budget, remaining_bytes=0), 200, 2, self.now))
        self.assertIn('未设置预算', budget_forecast(dict(budget, limit_bytes=0), 200, 2, self.now))

    def test_mobile_uses_the_same_forecast_and_server_ip(self):
        from hy2panel.mobile_api import _traffic_budgets
        app = SimpleNamespace(database=self.db,
                              usage_manager=SimpleNamespace(local_origin_id=self.local),
                              service_controller=SimpleNamespace(status=lambda: 'active'),
                              system_metrics=SimpleNamespace(server_ips=lambda: ('203.0.113.5',)))
        snapshot = {'machine_stats': {'origins': [
            {'origin_id': self.local, 'kind': 'local', 'display_name': 'panel',
             'tx_bytes': 600, 'rx_bytes': 300},
        ]}}
        with mock.patch('hy2panel.mobile_api.time.time', return_value=self.now):
            item = _traffic_budgets(app, snapshot)[0]
        self.assertEqual('203.0.113.5', item['serverIp'])
        self.assertEqual((600, 300), (item['txBytes'], item['rxBytes']))
        self.assertIn('5月23日', item['budget']['forecastText'])
        self.assertEqual('2033-06-01', item['budget']['nextResetDate'])

    def test_ip_addresses_are_local_deduplicated_and_cached(self):
        proc = Path(self.temp.name) / 'proc'
        (proc / 'net').mkdir(parents=True)
        (proc / 'net/fib_trie').write_text('''Local:
           |-- 127.0.0.1
              /32 host LOCAL
           |-- 8.8.8.8
              /32 host LOCAL
           |-- 8.8.8.8
              /32 host LOCAL
           |-- 10.0.0.2
              /32 host LOCAL
''')
        (proc / 'net/if_inet6').write_text('26064700470000000000000000001111 02 40 00 80 eth0\nfe800000000000000000000000000001 02 40 20 80 eth0\n')
        metrics = SystemMetrics(proc_root=proc)
        self.assertEqual(('8.8.8.8', '2606:4700:4700::1111'), metrics.server_ips())
        (proc / 'net/fib_trie').unlink()
        self.assertEqual(('8.8.8.8', '2606:4700:4700::1111'), metrics.server_ips())
        self.assertEqual((), SystemMetrics(proc_root=proc / 'missing').server_ips())
