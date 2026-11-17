"""Bearer monitoring must match the web read model without triggering probes."""
import json
import time
import unittest
import urllib.error
from unittest import mock

from tests import test_panel


class MobileMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.f = test_panel.PanelHttpTests('runTest')
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        status, login = self.f.mobile_json_request('POST', '/api/v1/mobile/auth/login', {
            'username': 'Elegy', 'password': 'admin-password',
            'deviceId': 'monitor-test', 'deviceName': 'Monitoring test',
        })
        self.assertEqual(200, status)
        self.token = login['data']['accessToken']

    def test_bearer_required(self):
        for route in ('server-monitor', 'line-monitor'):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.f.mobile_json_request('GET', '/api/v1/mobile/' + route)
            with caught.exception as response:
                self.assertEqual(401, response.code)
                self.assertEqual('SESSION_EXPIRED', json.load(response)['error']['code'])

    def test_resources_match_web_and_exclude_revoked_nodes(self):
        f = self.f
        issued = f.application.node_enrollment_service.create('remote', '8.8.4.9', 10, 'Elegy')
        node_id = issued['nodeId']
        f.db.server_monitor.accept(node_id, dict(cpu=1, memory=2, disk=3, uptime=10, observedAt=int(time.time())))
        headers, _ = f.authenticated_headers()
        with f.request('/api/v1/server-monitor', headers=headers) as response:
            web = json.load(response)
        status, mobile = f.mobile_json_request('GET', '/api/v1/mobile/server-monitor', access_token=self.token)
        self.assertEqual(200, status)
        self.assertEqual(web['servers'], mobile['data']['servers'])
        self.assertEqual(web['operations'], mobile['data']['operations'])
        with f.db._connect() as connection:
            connection.execute("UPDATE nodes SET status='revoked' WHERE node_id=?", (node_id,))
        _, mobile = f.mobile_json_request('GET', '/api/v1/mobile/server-monitor', access_token=self.token)
        self.assertNotIn(node_id, mobile['data']['servers'])

    def test_history_ranges_and_no_automatic_probe(self):
        monitor = mock.Mock()
        monitor.snapshot.return_value = {'network': {}, 'checks': {}, 'today': {}}
        with mock.patch.object(self.f.application, 'line_monitor', monitor):
            for suffix, today in [('', False), ('?range=5m', False), ('?range=today', True)]:
                status, result = self.f.mobile_json_request('GET', '/api/v1/mobile/line-monitor' + suffix, access_token=self.token)
                self.assertEqual(200, status)
                self.assertEqual(monitor.snapshot.return_value, result['data'])
                self.assertEqual({'today': True} if today else {}, monitor.snapshot.call_args.kwargs)
            monitor.request.assert_not_called()
            calls = monitor.snapshot.call_count
            for suffix in ('?range=year', '?range=today&range=5m'):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.f.mobile_json_request('GET', '/api/v1/mobile/line-monitor' + suffix, access_token=self.token)
                with caught.exception as response:
                    self.assertEqual(400, response.code)
                    self.assertEqual('RANGE_INVALID', json.load(response)['error']['code'])
            self.assertEqual(calls, monitor.snapshot.call_count)

    def test_capabilities_advertise_reads_only(self):
        _, result = self.f.mobile_json_request('GET', '/api/v1/mobile/capabilities')
        features = result['data']['features']
        for feature in ('server-resource-monitor', 'network-history-today', 'line-diagnostics-read'):
            self.assertIn(feature, features)
        self.assertNotIn('remote-server-reboot', features)
