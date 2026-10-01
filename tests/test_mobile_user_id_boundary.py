"""Out-of-range user IDs cannot escape the mobile HTTP response contract."""
import unittest
import urllib.error

from hy2panel.mobile_api import match_mobile_route
from tests import test_panel


class MobileUserIdBoundaryTests(unittest.TestCase):
    def test_shared_routes_bound_ids_before_integer_conversion(self):
        for method, suffix in (("GET", "/domain-usage"), ("GET", "/traffic-history"),
                               ("POST", "/disable"), ("PATCH", ""), ("DELETE", "")):
            for identifier in ("0", "9223372036854775808", "9" * 5000):
                with self.subTest(method=method, identifier_length=len(identifier)):
                    self.assertEqual((None, ()), match_mobile_route(
                        method, "/api/v1/mobile/users/" + identifier + suffix))
            self.assertIsNotNone(match_mobile_route(
                method, "/api/v1/mobile/users/42" + suffix)[0])
        self.assertEqual(("update-user", ("9223372036854775807",)),
                         match_mobile_route("PATCH", "/api/v1/mobile/users/9223372036854775807"))

    def test_http_rejects_invalid_ids_without_mutating_or_breaking_valid_requests(self):
        fixture = test_panel.PanelHttpTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        token = fixture.db.create_mobile_session(
            fixture.admin_id, "review-id-boundary", "Fixture")["accessToken"]
        user = fixture.db.create_proxy_user("boundary-kept")
        original = fixture.db.get_proxy_user(user["id"])
        for method, suffix, payload in (
            ("GET", "/domain-usage", None),
            ("GET", "/traffic-history", None),
            ("POST", "/disable", {"generation": 0}),
            ("PATCH", "", {"generation": 0, "usedTrafficGiB": "1"}),
            ("DELETE", "", {"generation": 0}),
        ):
            with self.subTest(method=method, suffix=suffix):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    fixture.mobile_json_request(method,
                        "/api/v1/mobile/users/9223372036854775808" + suffix,
                        payload, access_token=token)
                self.assertEqual(404, error.exception.code)
                error.exception.close()
                self.assertEqual(original, fixture.db.get_proxy_user(user["id"]))
        status, _ = fixture.mobile_json_request("POST",
            "/api/v1/mobile/users/{}/disable".format(user["id"]),
            {"generation": 0}, access_token=token)
        self.assertEqual(200, status)
        self.assertFalse(fixture.db.get_proxy_user(user["id"])["enabled"])


if __name__ == "__main__":
    unittest.main()
