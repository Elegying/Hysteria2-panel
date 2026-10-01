"""Damaged deflate payloads remain validation failures, with no queued restore."""
import io
import struct
import unittest
import urllib.error
import zipfile

import hysteria2_panel as panel
from tests import test_panel


def corrupt_deflate(path):
    with zipfile.ZipFile(path) as archive:
        entry = archive.infolist()[0]
        assert entry.compress_type == zipfile.ZIP_DEFLATED
    raw = bytearray(path.read_bytes())
    name_size, extra_size = struct.unpack_from("<HH", raw, entry.header_offset + 26)
    # Reserved deflate block type: corrupt data while preserving ZIP structure.
    raw[entry.header_offset + 30 + name_size + extra_size] = 0xff
    return bytes(raw)


class CorruptBackupUploadTests(unittest.TestCase):
    def test_corrupt_payload_is_rejected_and_valid_upload_still_stages(self):
        fixture = test_panel.BackupManagerTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        archive = fixture.manager.create_archive()
        original = archive.read_bytes()
        corrupted = corrupt_deflate(archive)
        with self.assertRaisesRegex(panel.BackupValidationError, "ZIP 备份文件无效"):
            fixture.manager.stage_archive(io.BytesIO(corrupted), len(corrupted))
        self.assertFalse(fixture.manager.pending_archive.exists())
        self.assertFalse(list(fixture.manager.work_dir.glob(".upload-*")))
        self.assertEqual(456, fixture.database.get_proxy_user(fixture.user["id"])["rx_bytes"])
        fixture.manager.stage_archive(io.BytesIO(original), len(original))
        self.assertTrue(fixture.manager.pending_archive.is_file())

    def test_http_corrupt_archive_returns_400_without_queuing_restore(self):
        fixture = test_panel.PanelHttpTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        archive = fixture.backup_manager.create_archive()
        headers, csrf = fixture.authenticated_headers()
        headers.update({"Content-Type": "application/zip", "X-HY2Panel-CSRF": csrf})
        with self.assertRaises(urllib.error.HTTPError) as error:
            fixture.request("/restore", raw_data=corrupt_deflate(archive), headers=headers)
        self.assertEqual(400, error.exception.code)
        self.assertIn("ZIP 备份文件无效", error.exception.read().decode())
        error.exception.close()
        self.assertFalse(fixture.backup_manager.pending_archive.exists())
        self.assertFalse(fixture.restore_controller.queued)


if __name__ == "__main__":
    unittest.main()
