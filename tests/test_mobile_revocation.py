"""Revocation credentials remain session-bound across expiry and refresh races."""

import time
import unittest
import urllib.error
from unittest import mock

from tests import test_panel as panel_tests


class MobileRevocationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = panel_tests.PanelHttpTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db

    def issue(self, device="audit-device"):
        return self.db.create_mobile_session(self.fixture.admin_id, device, "Audit")

    def logout(self, tokens, access=True):
        return self.fixture.mobile_json_request(
            "POST", "/api/v1/mobile/auth/logout",
            {key: tokens[key] for key in ("refreshToken", "revocationToken") if key in tokens},
            tokens.get("accessToken", "") if access else "",
        )

    def test_expired_access_logout_revokes_the_refresh_session(self):
        with mock.patch("hysteria2_panel.time.time", return_value=time.time() - 901):
            tokens = self.issue()
        status, result = self.logout(tokens)
        self.assertEqual(200, status)
        self.assertTrue(result["data"]["revoked"])
        self.assertIsNone(self.db.rotate_mobile_session(tokens["refreshToken"]))
        self.assertFalse(self.logout(tokens)[1]["data"]["revoked"])

    def test_restored_inactive_legacy_profile_can_revoke_with_refresh_only(self):
        tokens = self.issue()
        status, result = self.logout({"refreshToken": tokens["refreshToken"]}, access=False)
        self.assertEqual(200, status)
        self.assertTrue(result["data"]["revoked"])
        self.assertIsNone(self.db.get_mobile_session(tokens["accessToken"]))

    def test_multiple_valid_owned_credentials_report_a_successful_revocation(self):
        first, second = self.issue(), self.issue("other-device")
        tokens = {"accessToken": first["accessToken"], "refreshToken": second["refreshToken"]}
        self.assertTrue(self.logout(tokens)[1]["data"]["revoked"])
        self.assertIsNone(self.db.get_mobile_session(first["accessToken"]))
        self.assertIsNone(self.db.get_mobile_session(second["accessToken"]))

    def test_rotation_stable_revocation_cancels_a_concurrent_refresh(self):
        issued = self.issue()
        rotated = self.db.rotate_mobile_session(issued["refreshToken"])
        self.assertEqual(issued["revocationToken"], rotated["revocationToken"])
        self.assertTrue(self.logout(issued)[1]["data"]["revoked"])
        self.assertIsNone(self.db.get_mobile_session(rotated["accessToken"]))
        self.assertIsNone(self.db.rotate_mobile_session(rotated["refreshToken"]))

    def test_old_revocation_cannot_cancel_a_new_login_or_another_device(self):
        old = self.issue()
        replacement = self.issue()
        other = self.issue("other-device")
        self.assertFalse(self.logout(old)[1]["data"]["revoked"])
        self.assertIsNotNone(self.db.get_mobile_session(replacement["accessToken"]))
        self.assertIsNotNone(self.db.get_mobile_session(other["accessToken"]))

    def test_forged_revocation_has_no_effect_and_real_capability_cannot_authenticate(self):
        issued = self.issue()
        forged = issued["revocationToken"][:-1] + ("0" if issued["revocationToken"][-1] != "0" else "1")
        self.assertFalse(self.logout({"revocationToken": forged}, access=False)[1]["data"]["revoked"])
        self.assertIsNotNone(self.db.get_mobile_session(issued["accessToken"]))
        self.assertIsNone(self.db.rotate_mobile_session(issued["revocationToken"]))
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            self.fixture.mobile_json_request(
                "GET", "/api/v1/mobile/auth/session", access_token=issued["revocationToken"],
            )
        self.assertEqual(401, rejected.exception.code)
