"""Exercise the raw ZIP upload boundary through the real HTTP handler."""
import http.client
import io
import socket
import stat
import unittest
import urllib.error
import zipfile

import hysteria2_panel as panel
from tests import test_panel


class BackupUploadContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_panel.PanelHttpTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.user = self.fixture.db.create_proxy_user("upload-contract")
        self.original = self.fixture.backup_manager.create_archive().read_bytes()
        self.headers, csrf = self.fixture.authenticated_headers()
        self.headers.update({"Content-Type": "application/zip", "X-HY2Panel-CSRF": csrf})

    def assert_rejected(self, body, message, **headers):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.fixture.request("/restore", raw_data=body, headers={**self.headers, **headers})
        with raised.exception as response:
            self.assertEqual(400, response.code)
            self.assertIn(message, response.read().decode())
        self.assert_clean()

    def assert_clean(self):
        manager = self.fixture.backup_manager
        self.assertFalse(manager.pending_archive.exists())
        self.assertFalse(list(manager.work_dir.glob(".upload-*")))
        self.assertFalse(self.fixture.restore_controller.queued)
        self.assertIsNotNone(self.fixture.db.authenticate_token(self.user["token"]))

    def assert_valid_upload_recovers(self):
        with self.fixture.request(
            "/restore", raw_data=self.original,
            headers={**self.headers, "Accept": "application/json"},
        ) as response:
            self.assertEqual(202, response.status)
            response.read()
        self.assertTrue(self.fixture.restore_controller.queued)
        self.assertEqual(self.original, self.fixture.backup_manager.pending_archive.read_bytes())

    def test_extra_duplicate_directory_symlink_and_traversal_entries_are_rejected(self):
        with zipfile.ZipFile(io.BytesIO(self.original)) as source:
            members = {name: source.read(name) for name in source.namelist()}
        for case in ("extra", "duplicate", "directory", "symlink", "traversal", "absolute"):
            with self.subTest(case=case):
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, payload in members.items():
                        if name == "tls/server.key":
                            if case == "directory":
                                name += "/"
                            elif case == "traversal":
                                name = "../server.key"
                            elif case == "absolute":
                                name = "/tls/server.key"
                            elif case == "symlink":
                                name = zipfile.ZipInfo(name)
                                name.create_system = 3
                                name.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(name, payload)
                    if case == "extra":
                        archive.writestr("unlisted.txt", b"unlisted")
                    elif case == "duplicate":
                        with self.assertWarnsRegex(UserWarning, "Duplicate name"):
                            archive.writestr("manifest.json", members["manifest.json"])
                self.assert_rejected(output.getvalue(), "备份文件结构无效")
        self.assert_valid_upload_recovers()

    def test_compressed_database_over_the_real_limit_is_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.original)) as source, zipfile.ZipFile(
            output, "w", compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for name in source.namelist():
                if name != "data/panel.db":
                    archive.writestr(name, source.read(name))
            # Use the real 128 MiB limit, streaming a highly compressible payload.
            chunk = b"\0" * (1024 * 1024)
            with archive.open("data/panel.db", "w") as database:
                for _ in range(128):
                    database.write(chunk)
                database.write(b"\0")
        body = output.getvalue()
        self.assertLess(len(body), 1024 * 1024)
        self.assert_rejected(body, "备份文件结构无效")
        self.assert_valid_upload_recovers()

    def test_raw_body_type_and_length_boundaries_release_the_upload_slot(self):
        for length in ("0", "-1", str(131 * 1024**2 + 1), "invalid"):
            with self.subTest(length=length):
                self.assert_rejected(b"", "备份文件大小无效", **{"Content-Length": length})
        self.assert_rejected(b"x", "ZIP 备份文件无效")
        self.assert_rejected(
            self.original, "仅支持本面板生成的 ZIP",
            **{"Content-Type": "multipart/form-data; boundary=upload-fixture"},
        )
        # Exactly 131 MiB is within the size limit, but an EOF must reject a
        # truncated body immediately without staging it or retaining the lock.
        connection = http.client.HTTPConnection(*self.fixture.server.server_address, timeout=2)
        self.addCleanup(connection.close)
        connection.request(
            "POST", "/restore", body=b"x",
            headers={**self.headers, "Content-Length": str(131 * 1024**2)},
        )
        connection.sock.shutdown(socket.SHUT_WR)
        with connection.getresponse() as response:
            self.assertEqual(400, response.status)
            self.assertIn("备份文件上传不完整", response.read().decode())
        self.assert_clean()
        self.assertEqual(131 * 1024**2, panel.MAX_BACKUP_ARCHIVE_BYTES)
        self.assert_valid_upload_recovers()


if __name__ == "__main__":
    unittest.main()
