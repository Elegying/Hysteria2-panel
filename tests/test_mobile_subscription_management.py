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
        status, result = self.request('POST', 'users', dict({'name': 'premium-test', 'userType': 1}, **values))
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

    def test_subscription_management_preserves_links_except_explicit_reset(self):
        user, url = self.create()
        path = 'users/{}'.format(user['id'])
        _, view = self.request('GET', path + '/subscription')
        data = view['data']
        password = self.fixture.db.recover_proxy_token(user['id'])
        self.assertEqual(url, data['url'])
        for action, enabled in [('disable', False), ('enable', True), ('inherit', True)]:
            _, result = self.request('POST', path + '/subscription-' + action,
                {'generation': data['generation'], 'revision': data['revision']})
            data = result['data']
            self.assertEqual(enabled, data['enabled'])
            self.assertEqual(url, data['url'])
            self.assertEqual(password, self.fixture.db.recover_proxy_token(user['id']))
        stale = dict(generation=data['generation'], revision=data['revision'])
        _, result = self.request('POST', path + '/subscription-regenerate', stale)
        self.assertNotEqual(url, result['data']['url'])
        self.assertNotEqual(password, self.fixture.db.recover_proxy_token(user['id']))
        self.assertIsNone(self.fixture.db.get_subscription_by_token(url.rsplit('/', 1)[-1]))
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('POST', path + '/subscription-regenerate', stale)
        self.assertEqual(409, error.exception.code)
        error.exception.close()

    def test_subscription_revision_rejects_stale_toggle_and_missing_auth(self):
        user, url = self.create()
        path = 'users/{}/subscription'.format(user['id'])
        _, view = self.request('GET', path)
        data = view['data']
        payload = {'generation': data['generation'], 'revision': data['revision']}
        self.request('POST', path + '-disable', payload)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('POST', path + '-enable', payload)
        self.assertEqual(409, error.exception.code)
        error.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.fixture.mobile_json_request('GET', '/api/v1/mobile/' + path)
        self.assertEqual(401, error.exception.code)
        error.exception.close()

    def test_create_missing_subscription_and_restore_inherited_nodes(self):
        user, _ = self.create(userType=0)
        path = 'users/{}'.format(user['id'])
        sub = self.fixture.db.get_subscription(user_id=user['id'])
        self.fixture.db.delete_subscription(sub['id'])
        password = self.fixture.db.recover_proxy_token(user['id'])
        _, view = self.request('GET', path + '/subscription')
        self.assertFalse(view['data']['exists'])
        self.assertIsNone(self.fixture.db.get_subscription(user_id=user['id']))
        _, created = self.request('POST', path + '/subscription-create', {
            'generation': view['data']['generation'], 'revision': view['data']['revision']})
        self.assertEqual(password, self.fixture.db.recover_proxy_token(user['id']))
        sub = self.fixture.db.get_subscription(user_id=user['id'])
        self.fixture.db.set_subscription_nodes(sub['id'], [{'label': 'Custom',
            'host': 'example.com', 'port': 443, 'pin_sha256': 'a' * 64, 'enabled': True}])
        _, view = self.request('GET', path + '/subscription')
        self.assertFalse(view['data']['usesDefaults'])
        _, inherited = self.request('POST', path + '/subscription-inherit', {
            'generation': view['data']['generation'], 'revision': view['data']['revision']})
        self.assertTrue(inherited['data']['usesDefaults'])
        self.assertEqual(created['data']['url'], inherited['data']['url'])

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
