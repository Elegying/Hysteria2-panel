"""Nested JSON is invalid input rather than an unhandled request failure."""
import io
import unittest
import urllib.error
import zipfile
from unittest import mock

import hysteria2_panel as panel
import node_agent
from tests import test_panel


def nested_json(depth):
    return ("[" * depth + "0" + "]" * depth).encode()


class JsonDepthBoundaryTests(unittest.TestCase):
    def test_bounded_internal_auth_json_never_dispatches_an_invalid_payload(self):
        database = mock.Mock()
        raw = nested_json(1800)
        self.assertLess(len(raw), 4096)
        self.assertEqual(400, panel.handle_auth_payload(database, raw)[0])
        database.authenticate_token.assert_not_called()
        authorize = mock.Mock()
        self.assertEqual((200, {"ok": False, "id": ""}),
                         node_agent.proxy_auth_payload(raw, authorize))
        authorize.assert_not_called()

    def test_mobile_http_rejects_deep_json_and_remains_available(self):
        fixture = test_panel.PanelHttpTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        raw = nested_json(10000)
        self.assertLess(len(raw), 32768)
        with self.assertRaises(urllib.error.HTTPError) as error:
            fixture.request("/api/v1/mobile/auth/login", raw_data=raw,
                            headers={"Content-Type": "application/json"})
        self.assertEqual(400, error.exception.code)
        error.exception.close()
        with fixture.request("/api/v1/mobile/capabilities") as response:
            self.assertEqual(200, response.status)

    def test_deep_backup_manifest_is_a_validation_error_without_pending_restore(self):
        fixture = test_panel.BackupManagerTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        original = fixture.manager.create_archive()
        candidate = fixture.root / "nested-manifest.zip"
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(
            candidate, "w", compression=zipfile.ZIP_DEFLATED
        ) as output:
            for name in source.namelist():
                output.writestr(name, nested_json(10000) if name == "manifest.json" else source.read(name))
        raw = candidate.read_bytes()
        with self.assertRaisesRegex(panel.BackupValidationError, "备份清单无效"):
            fixture.manager.stage_archive(io.BytesIO(raw), len(raw))
        self.assertFalse(fixture.manager.pending_archive.exists())
        self.assertFalse(list(fixture.manager.work_dir.glob(".upload-*")))
        self.assertEqual(456, fixture.database.get_proxy_user(fixture.user["id"])["rx_bytes"])


if __name__ == "__main__":
    unittest.main()
