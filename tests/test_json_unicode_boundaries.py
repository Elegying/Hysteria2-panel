"""JSON Unicode escapes cannot break credentials or signing boundaries."""
import json
import unittest
import urllib.error
from unittest import mock

import hysteria2_panel as panel
from tests import test_panel


class JsonUnicodeBoundaryTests(unittest.TestCase):
    def test_internal_auth_rejects_lone_surrogates_without_auth_dispatch(self):
        database = mock.Mock()
        for token in ("\ud800", "\udfff", "prefix\ud800"):
            with self.subTest(position=len(token)):
                raw = json.dumps({"auth": token}).encode()
                self.assertEqual(400, panel.handle_auth_payload(database, raw)[0])
        database.authenticate_token.assert_not_called()

    def test_mobile_invalid_unicode_is_400_and_valid_unicode_login_refresh_work(self):
        fixture = test_panel.PanelHttpTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        username, password = "中文管理员", "fixture-password"
        fixture.db.upsert_admin(username, password)
        with fixture.db._connect() as connection:
            before = connection.execute("SELECT COUNT(*) FROM mobile_sessions").fetchone()[0]
        for path, payload in (
            ("/api/v1/mobile/auth/login", {"username": "\ud800", "password": "invalid"}),
            ("/api/v1/mobile/auth/refresh", {"refreshToken": "hy2r_\ud800"}),
            ("/api/v1/mobile/auth/login", {"username": username, "password": password,
                                          "deviceId": "unicode-fixture", "deviceName": "\udfff"}),
            ("/api/v1/mobile/auth/login", {"username": username, "password": password,
                                          "deviceId": "unicode-fixture", "deviceName": {"\ud800": 1}}),
        ):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    fixture.mobile_json_request("POST", path, payload)
                self.assertEqual(400, error.exception.code)
                error.exception.close()
        with fixture.db._connect() as connection:
            self.assertEqual(before, connection.execute("SELECT COUNT(*) FROM mobile_sessions").fetchone()[0])
        status, login = fixture.mobile_json_request("POST", "/api/v1/mobile/auth/login", {
            "username": username, "password": password,
            "deviceId": "unicode-fixture", "deviceName": "测试设备🌸",
        })
        self.assertEqual(200, status)
        status, refreshed = fixture.mobile_json_request("POST", "/api/v1/mobile/auth/refresh",
            {"refreshToken": login["data"]["refreshToken"]})
        self.assertEqual(200, status)
        self.assertNotEqual(login["data"]["accessToken"], refreshed["data"]["accessToken"])


if __name__ == "__main__":
    unittest.main()
