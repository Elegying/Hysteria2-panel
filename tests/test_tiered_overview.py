"""Account group totals remain distinct in the mobile overview."""
import unittest
from types import SimpleNamespace
from unittest import mock

from hy2panel import mobile_api


class TieredOverviewTests(unittest.TestCase):
    def test_mobile_overview_separates_traffic_by_account_type(self):
        users = [
            {'userType': 0, 'txBytes': 10, 'rxBytes': 20, 'usedBytes': 30,
             'onlineDevices': 1},
            {'userType': 1, 'txBytes': 100, 'rxBytes': 200, 'usedBytes': 300,
             'onlineDevices': 2},
        ]
        app = SimpleNamespace(node_name='test', public_host='example.test',
                              hysteria_port=443,
                              service_controller=SimpleNamespace(status=lambda: 'active'),
                              system_metrics=SimpleNamespace(snapshot=lambda: {}))
        with mock.patch.object(mobile_api, '_safe_snapshot', return_value={}), \
             mock.patch.object(mobile_api, '_user_items', return_value=users), \
             mock.patch.object(mobile_api, 'nodes_payload', return_value={
                 'total': 0, 'online': 0, 'statusCounts': {}}), \
             mock.patch.object(mobile_api, '_traffic_budgets', return_value=[]):
            data = mobile_api.overview_payload(app, 'test')
        self.assertEqual({'txBytes': 10, 'rxBytes': 20, 'totalBytes': 30},
                         data['trafficByTier']['standard'])
        self.assertEqual({'txBytes': 100, 'rxBytes': 200, 'totalBytes': 300},
                         data['trafficByTier']['premium'])
        self.assertEqual(330, data['traffic']['totalBytes'])


if __name__ == '__main__':
    unittest.main()
