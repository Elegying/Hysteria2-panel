import io
from pathlib import Path
import struct
import unittest
import urllib.error
import zipfile

import hysteria2_panel as panel
from tests import test_panel


def lzma_archive(manager, root):
    original = manager.create_archive()
    repacked = root / 'lzma-backup.zip'
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(
        repacked, 'w', compression=zipfile.ZIP_LZMA
    ) as output:
        for name in source.namelist():
            output.writestr(name, source.read(name))
    with zipfile.ZipFile(repacked) as archive:
        entry = archive.infolist()[0]
    valid = repacked.read_bytes()
    corrupt = bytearray(valid)
    name_size, extra_size = struct.unpack_from('<HH', corrupt, entry.header_offset + 26)
    offset = entry.header_offset + 30 + name_size + extra_size
    corrupt[offset + 9:offset + 17] = b'\xff' * 8
    return valid, bytes(corrupt)


@unittest.skipIf(zipfile.lzma is None, 'LZMA decoder is unavailable')
class BackupCodecBoundaryTests(unittest.TestCase):
    def test_corrupt_lzma_is_validation_error_and_valid_lzma_still_stages(self):
        fixture = test_panel.BackupManagerTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        valid, corrupt = lzma_archive(fixture.manager, fixture.root)
        with self.assertRaisesRegex(panel.BackupValidationError, 'ZIP 备份文件无效'):
            fixture.manager.stage_archive(io.BytesIO(corrupt), len(corrupt))
        self.assertFalse(fixture.manager.pending_archive.exists())
        self.assertFalse(list(fixture.manager.work_dir.glob('.upload-*')))
        self.assertEqual(456, fixture.database.get_proxy_user(fixture.user['id'])['rx_bytes'])
        fixture.manager.stage_archive(io.BytesIO(valid), len(valid))
        self.assertTrue(fixture.manager.pending_archive.is_file())

    def test_corrupt_lzma_http_upload_is_400_without_queued_restore(self):
        fixture = test_panel.PanelHttpTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        _valid, corrupt = lzma_archive(fixture.backup_manager, Path(fixture.temp_dir.name))
        headers, csrf = fixture.authenticated_headers()
        headers.update({'Content-Type': 'application/zip', 'X-HY2Panel-CSRF': csrf})
        with self.assertRaises(urllib.error.HTTPError) as error:
            fixture.request('/restore', raw_data=corrupt, headers=headers)
        self.assertEqual(400, error.exception.code)
        error.exception.close()
        self.assertFalse(fixture.backup_manager.pending_archive.exists())
        self.assertFalse(fixture.restore_controller.queued)
