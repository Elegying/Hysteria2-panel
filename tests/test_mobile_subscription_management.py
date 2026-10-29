"""Mobile mutations use the same identities and validity rules as the web panel."""
import time
import unittest
import urllib.error

from hy2panel.nodes import NodeEnrollmentService
from tests import test_panel


class MobileSubscriptionManagementTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_panel.PanelHttpTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.token = self.fixture.db.create_mobile_session(
            self.fixture.admin_id, 'mobile-management-test', 'Android')['accessToken']

    def request(self, method, path, payload=None):
        return self.fixture.mobile_json_request(method, '/api/v1/mobile/' + path,
                                               payload, access_token=self.token)

    def create(self, **values):
        status, result = self.request('POST', 'users', dict(name='premium-test', userType=1, **values))
        self.assertEqual(201, status)
        _, users = self.request('GET', 'users')
        self.assertTrue(users['data']['subscriptionManagement'])
        user = next(x for x in users['data']['items'] if x['name'] == 'premium-test')
        return user, result['data']['uri']

    def test_premium_defaults_and_rotation_preserve_subscription(self):
        user, url = self.create()
        self.assertEqual((1, 100, 250 * 1024**3, None),
                         (user['userType'], user['deviceLimit'], user['trafficLimitBytes'], user['expiresAt']))
        password = self.fixture.db.recover_proxy_token(user['id'])
        _, shared = self.request('POST', 'users/{}/share'.format(user['id']), {'generation': user['generation']})
        self.assertEqual(url, shared['data']['uri'])
        _, rotated = self.request('POST', 'users/{}/rotate-secret'.format(user['id']), {'generation': user['generation']})
        self.assertEqual(url, rotated['data']['uri'])
        self.assertNotEqual(password, self.fixture.db.recover_proxy_token(user['id']))

    def test_dates_are_preserved_when_omitted_and_cleared_only_explicitly(self):
        now = int(time.time())
        user, url = self.create(startsAt=now - 30, expiresAt=now + 3600)
        path = 'users/{}'.format(user['id'])
        limits = {'deviceLimit': 100, 'trafficLimitGb': 250}
        self.request('PATCH', path, dict(limits, generation=0))
        saved = self.fixture.db.get_proxy_user(user['id'])
        self.assertEqual(now + 3600, saved['expires_at'])
        self.request('PATCH', path, dict(limits, generation=1, expiresAt=None, startsAt=None))
        saved = self.fixture.db.get_proxy_user(user['id'])
        self.assertIsNone(saved['expires_at'])
        self.assertIsNone(saved['starts_at'])
        _, shared = self.request('POST', path + '/share', {'generation': 2})
        self.assertEqual(url, shared['data']['uri'])
        for invalid in (True, '123', -1, 253402272000):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('PATCH', path, dict(limits, generation=2, expiresAt=invalid))
            self.assertEqual(400, error.exception.code)
            error.exception.close()
            self.assertEqual(2, self.fixture.db.get_proxy_user(user['id'])['generation'])

    def test_node_enrollment_preserves_tier_region_and_hopping(self):
        app = self.fixture.application
        app.secure_cookies = True
        app.node_enrollment_service = NodeEnrollmentService(self.fixture.db, 'https://panel.example.com:19999', '0.39.48')
        for index, hopping in enumerate((True, False)):
            _, result = self.request('POST', 'node-enrollments', {
                'name': 'Japan {}'.format(index), 'expectedIp': '8.8.8.8',
                'tier': 'premium', 'region': 'jp' if hopping else 'sg',
                'subscriptionHost': 'jp.example.com' if hopping else 'sg.example.com', 'portHopping': hopping,
            })
            node = next(n for n in self.fixture.db.list_nodes() if n['node_id'] == result['data']['nodeId'])
            self.assertEqual('premium', node['tier'])
            self.assertEqual(hopping, bool(node['port_hopping']))
            self.assertEqual(19999, node['listen_port'])
            self.assertEqual(443 if hopping else 19999, node['subscription_port'])
