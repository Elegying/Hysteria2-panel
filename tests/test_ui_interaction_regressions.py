import json
import unittest
import urllib.error

from tests import test_panel


class UIInteractionRegressions(unittest.TestCase):
    def setUp(self):
        self.fixture = test_panel.PanelHttpTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_duplicate_user_has_actionable_chinese_feedback_on_web_and_mobile(self):
        f = self.fixture
        f.db.create_proxy_user("duplicate-user")
        headers, csrf = f.authenticated_headers()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            f.request(
                "/users",
                {"name": "duplicate-user", "inline": "1", "csrf": csrf},
                headers,
            )
        self.assertEqual(400, caught.exception.code)
        web_error = json.loads(caught.exception.read())["error"]
        tokens = f.db.create_mobile_session(f.admin_id, "ui-review-test", "Test")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            f.mobile_json_request(
                "POST",
                "/api/v1/mobile/users",
                {"name": "duplicate-user"},
                access_token=tokens["accessToken"],
            )
        self.assertEqual(400, caught.exception.code)
        payload = json.loads(caught.exception.read())
        self.assertEqual(web_error, payload["error"]["message"])
        self.assertIn("已存在", web_error)
        self.assertIn("重试", web_error)
        self.assertEqual(1, len(f.db.list_proxy_users_for_usage()))

    def test_browser_edit_lookup_preserves_the_full_sqlite_id_as_text(self):
        f = self.fixture
        user = f.db.create_proxy_user("precision-user")
        user_id = 9223372036854775807
        with f.db._connect() as connection:
            connection.execute(
                "UPDATE proxy_users SET id=? WHERE id=?", (user_id, user["id"])
            )
        headers, csrf = f.authenticated_headers()
        with f.request(
            "/users/lookup?name=precision-user", headers=headers
        ) as response:
            payload = json.loads(response.read())
        self.assertEqual(str(user_id), payload["id"])
        with f.request(
            "/users/" + payload["id"] + "/edit",
            {
                "csrf": csrf,
                "inline": "1",
                "generation": payload["generation"],
                "device_limit": "7",
                "traffic_limit_gb": "250",
            },
            headers,
        ) as response:
            self.assertEqual(200, response.status)
        self.assertEqual(7, f.db.get_proxy_user(user_id)["device_limit"])
