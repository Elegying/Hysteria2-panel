"""Web user actions share the mobile API's bounded ID validation."""
import unittest
import urllib.error

from tests import test_panel


class WebUserIdBoundaryTests(unittest.TestCase):
    def test_invalid_ids_are_rejected_before_every_action_and_valid_edit_still_works(self):
        fixture = test_panel.PanelHttpTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        headers, csrf = fixture.authenticated_headers()
        user = fixture.db.create_proxy_user("web-boundary-kept")
        original = fixture.db.get_proxy_user(user["id"])
        form = {"csrf": csrf, "generation": "0", "device_limit": "3",
                "traffic_limit_gb": "1", "inline": "1"}
        for identifier in ("0", "9223372036854775808", "9" * 5000):
            for action in ("edit", "toggle", "rotate", "delete", "share", "reset"):
                with self.subTest(action=action, id_length=len(identifier)):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        fixture.request("/users/{}/{}".format(identifier, action),
                                        data=form, headers=headers)
                    self.assertEqual(404, error.exception.code)
                    error.exception.close()
                    self.assertEqual(original, fixture.db.get_proxy_user(user["id"]))
        with fixture.request("/users/{}/edit".format(user["id"]),
                             data=form, headers=headers) as response:
            self.assertEqual(200, response.status)
        self.assertEqual(1024**3, fixture.db.get_proxy_user(user["id"])["traffic_limit_bytes"])


if __name__ == "__main__":
    unittest.main()
