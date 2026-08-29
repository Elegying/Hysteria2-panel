import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path

from offsite_backup import (
    HttpsWebDavClient,
    OffsiteBackupConfig,
    OffsiteBackupRunner,
    WebDavBackupStore,
)


class FakeWebDavClient:
    def __init__(self, names=None):
        self.names = list(names or [])
        self.calls = []
        self.sizes = {}

    def put(self, name, path, sha256):
        self.calls.append(("put", name, sha256))
        self.sizes[name] = Path(path).stat().st_size

    def move(self, source, destination):
        self.calls.append(("move", source, destination))
        self.sizes[destination] = self.sizes.pop(source)
        self.names.append(destination)

    def size(self, name):
        self.calls.append(("size", name))
        return self.sizes[name]

    def list_names(self):
        self.calls.append(("list",))
        return list(self.names)

    def delete(self, name):
        self.calls.append(("delete", name))


class OffsiteBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_config_requires_root_only_https_without_url_credentials(self):
        path = self.root / "offsite.json"
        path.write_text(
            json.dumps(
                {
                    "endpoint": "https://backup.example.test/hy2panel/",
                    "username": "backup-user",
                    "password": "secret-value",
                }
            ),
            encoding="utf-8",
        )
        path.chmod(0o600)

        config = OffsiteBackupConfig.load(path, expected_uid=os.geteuid())

        self.assertEqual("https://backup.example.test/hy2panel/", config.endpoint)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            OffsiteBackupConfig.load(path, expected_uid=os.geteuid())
        path.chmod(0o600)
        path.write_text(
            json.dumps(
                {
                    "endpoint": "http://backup.example.test/",
                    "username": "u",
                    "password": "p",
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            OffsiteBackupConfig.load(path, expected_uid=os.geteuid())

    def test_upload_is_temporary_then_atomic_and_retention_is_exact(self):
        archive = self.root / "backup.zip"
        archive.write_bytes(b"verified-backup")
        old = "hysteria2-panel-offsite-20330401T000000Z-aaaaaaaa.zip"
        recent = "hysteria2-panel-offsite-20330517T000000Z-bbbbbbbb.zip"
        unrelated = "other-20300101T000000Z.zip"
        client = FakeWebDavClient([old, recent, unrelated])
        store = WebDavBackupStore(client, retention_days=30)
        now = datetime.datetime(2033, 5, 18, 0, 0, tzinfo=datetime.timezone.utc)

        result = store.upload(archive, now=now)

        self.assertTrue(result["name"].startswith("hysteria2-panel-offsite-20330518T000000Z-"))
        self.assertEqual("put", client.calls[0][0])
        self.assertTrue(client.calls[0][1].startswith(".upload-"))
        self.assertEqual("move", client.calls[1][0])
        self.assertIn(("delete", old), client.calls)
        self.assertNotIn(("delete", recent), client.calls)
        self.assertNotIn(("delete", unrelated), client.calls)

    def test_unconfigured_runner_writes_sanitized_status_without_creating_backup(self):
        status = self.root / "status.json"
        created = []
        runner = OffsiteBackupRunner(
            config_path=self.root / "missing.json",
            status_path=status,
            archive_factory=lambda: created.append(True),
            expected_uid=os.geteuid(),
            status_gid=os.getegid(),
        )

        result = runner.run()

        self.assertEqual("not_configured", result["state"])
        self.assertEqual([], created)
        persisted = json.loads(status.read_text(encoding="utf-8"))
        self.assertEqual({"state", "checkedAt", "lastSuccessAt", "errorCode"}, set(persisted))
        self.assertNotIn("endpoint", status.read_text(encoding="utf-8"))

    def test_configured_runner_removes_the_temporary_local_archive(self):
        config_path = self.root / "offsite.json"
        config_path.write_text(
            json.dumps(
                {
                    "endpoint": "https://backup.example.test/hy2panel/",
                    "username": "backup-user",
                    "password": "secret-value",
                }
            ),
            encoding="utf-8",
        )
        config_path.chmod(0o600)
        archive = self.root / "daily.zip"
        archive.write_bytes(b"verified-backup")
        client = FakeWebDavClient()
        now = datetime.datetime(2033, 5, 18, 0, 0, tzinfo=datetime.timezone.utc)
        runner = OffsiteBackupRunner(
            config_path=config_path,
            status_path=self.root / "status.json",
            archive_factory=lambda: archive,
            expected_uid=os.geteuid(),
            status_gid=os.getegid(),
            client_factory=lambda _config: client,
            clock=lambda: now,
        )

        result = runner.run()

        self.assertEqual("success", result["state"])
        self.assertFalse(archive.exists())

    def test_webdav_listing_accepts_namespaced_href_and_decodes_names(self):
        client = HttpsWebDavClient.__new__(HttpsWebDavClient)
        client._request = lambda *args, **kwargs: (
            207,
            {},
            b"""<?xml version=\"1.0\"?>
            <d:multistatus xmlns:d=\"DAV:\">
              <d:response><d:href>/hy2panel/</d:href></d:response>
              <d:response><d:href>/hy2panel/backup%20one.zip</d:href></d:response>
            </d:multistatus>""",
        )

        self.assertEqual(["hy2panel", "backup one.zip"], client.list_names())

    def test_webdav_listing_rejects_document_type_and_entity_declarations(self):
        client = HttpsWebDavClient.__new__(HttpsWebDavClient)
        client._request = lambda *args, **kwargs: (
            207,
            {},
            b"<!DOCTYPE x [<!ENTITY y SYSTEM 'file:///etc/passwd'>]>"
            b"<d:multistatus xmlns:d='DAV:'><d:href>&y;</d:href></d:multistatus>",
        )

        with self.assertRaises(RuntimeError):
            client.list_names()
