import json
import os
import shutil
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import hysteria2_panel
from hy2panel.certificate import certificate_validity_timestamps
from hysteria2_panel import (
    RESTORE_DISK_SAFETY_BYTES,
    BackupManager,
    BackupValidationError,
    Database,
    sqlite_connection,
)
from test_panel import create_test_certificate


class BackupStreamingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.hmac_key = b"s" * 32
        self.database = Database(self.root / "source.db", self.hmac_key)
        self.database.initialize()
        self.user = self.database.create_proxy_user("alice")
        self.database.apply_traffic_batch(
            "a" * 32, {"alice": {"tx": 1, "rx": 2}}
        )
        self.certificate, self.private_key = create_test_certificate(self.root)
        self.manager = self._manager(
            self.database,
            self.hmac_key,
            self.certificate,
            self.private_key,
            self.root / "source-work",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _manager(self, database, hmac_key, certificate, private_key, work_dir):
        lock_path = work_dir.parent / (work_dir.name + "-maintenance.lock")
        lock_path.touch(mode=0o600)
        return BackupManager(
            database=database,
            hmac_key=hmac_key,
            tls_cert=certificate,
            tls_key=private_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            work_dir=work_dir,
            maintenance_lock_path=lock_path,
            maintenance_lock_owner=None,
            maintenance_lock_mode=0o600,
            restore_marker_path=work_dir.parent / (work_dir.name + "-restore-active"),
        )

    @staticmethod
    def _reject_database_reads(manager):
        original = manager._read_bounded

        def read_bounded(path, maximum):
            if Path(path).suffix == ".db":
                raise AssertionError("database files must be streamed")
            return original(path, maximum)

        manager._read_bounded = read_bounded

    def test_archive_creation_and_validation_stream_the_database(self):
        self._reject_database_reads(self.manager)

        archive = self.manager.create_archive()
        manifest = self.manager.validate_archive(archive)

        self.assertEqual(1, manifest["proxyUserCount"])
        packaged_database = self.root / "packaged.db"
        with zipfile.ZipFile(archive) as package, package.open(
            "data/panel.db"
        ) as source, packaged_database.open("wb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
        with sqlite_connection(packaged_database) as connection:
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM applied_traffic_batches"
                ).fetchone()[0],
            )

    def test_archive_is_self_validated_before_it_becomes_downloadable(self):
        with mock.patch.object(
            self.manager,
            "validate_archive",
            side_effect=BackupValidationError("invalid archive"),
        ):
            with self.assertRaisesRegex(BackupValidationError, "invalid archive"):
                self.manager.create_archive()

        self.assertEqual([], list(self.manager.work_dir.iterdir()))

    def test_archive_capacity_uses_logical_database_size_including_wal(self):
        required = []
        with sqlite_connection(str(self.database.path)) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA wal_autocheckpoint = 0")
            connection.execute(
                """INSERT INTO audit_log(
                    created_at, actor, action, target, remote_ip
                ) VALUES (1, 'fixture', 'wal-capacity', 'runtime', zeroblob(?))""",
                (8 * 1024**2,),
            )
            connection.commit()
            logical_size = (
                connection.execute("PRAGMA page_count").fetchone()[0]
                * connection.execute("PRAGMA page_size").fetchone()[0]
            )
            with mock.patch.object(
                self.manager,
                "_require_free_space",
                side_effect=lambda _path, size: required.append(size),
            ):
                self.manager.create_archive()
            self.assertGreater(logical_size, self.database.path.stat().st_size)
            self.assertGreaterEqual(
                required[0], 3 * logical_size + RESTORE_DISK_SAFETY_BYTES
            )

    def test_restore_streams_database_replacement_and_checks_free_space(self):
        archive = self.manager.create_archive()
        destination_hmac = b"d" * 32
        destination_database = Database(self.root / "destination.db", destination_hmac)
        destination_database.initialize()
        destination_database.create_proxy_user("old-user")
        certificate_root = self.root / "destination-certificate"
        certificate_root.mkdir()
        destination_certificate, destination_key = create_test_certificate(certificate_root)
        env_file = self.root / "panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=old\n".format(
                destination_hmac.hex()
            ),
            encoding="utf-8",
        )
        destination = self._manager(
            destination_database,
            destination_hmac,
            destination_certificate,
            destination_key,
            self.root / "destination-work",
        )
        self._reject_database_reads(destination)

        result = destination.apply_archive(
            archive, env_file=env_file, backup_root=self.root / "restore-backups"
        )

        self.assertEqual(1, result["proxyUserCount"])
        restored_database = Database(destination_database.path, self.hmac_key)
        self.assertIsNotNone(restored_database.authenticate_token(self.user["token"]))

    def test_restore_capacity_includes_atomic_database_replacement_copy(self):
        archive = self.manager.create_archive()
        env_file = self.root / "capacity-estimate-panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=old\n".format(
                self.hmac_key.hex()
            ),
            encoding="utf-8",
        )
        logical_size = 64 * 1024**2
        required = []
        with mock.patch.object(
            self.manager,
            "_database_logical_size",
            return_value=logical_size,
            create=True,
        ), mock.patch.object(
            self.manager,
            "_require_free_space",
            side_effect=lambda _path, size: required.append(size),
        ):
            self.manager.apply_archive(
                archive,
                env_file=env_file,
                backup_root=self.root / "capacity-estimate-backups",
            )

        self.assertTrue(required)
        self.assertGreaterEqual(
            max(required), 3 * logical_size + RESTORE_DISK_SAFETY_BYTES
        )

    def test_restore_capacity_uses_larger_incoming_database_for_staging(self):
        archive = self.manager.create_archive()
        env_file = self.root / "incoming-capacity-panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=old\n".format(
                self.hmac_key.hex()
            ),
            encoding="utf-8",
        )
        incoming_size = 96 * 1024**2
        required = []
        extract_archive = self.manager._extract_archive

        def report_large_incoming(*args, **kwargs):
            manifest, paths = extract_archive(*args, **kwargs)
            manifest["files"]["data/panel.db"]["size"] = incoming_size
            return manifest, paths

        with mock.patch.object(
            self.manager, "_extract_archive", side_effect=report_large_incoming
        ), mock.patch.object(
            self.manager,
            "_require_free_space",
            side_effect=lambda _path, size: required.append(size),
        ):
            self.manager.apply_archive(
                archive,
                env_file=env_file,
                backup_root=self.root / "incoming-capacity-backups",
            )

        old_size = self.manager._database_logical_size(self.database.path)
        self.assertGreater(
            incoming_size, old_size, "fixture must model a large backup into a small node"
        )
        self.assertGreaterEqual(
            max(required),
            3 * old_size + 2 * incoming_size + RESTORE_DISK_SAFETY_BYTES,
        )

    def test_restore_fails_before_mutation_when_capacity_is_insufficient(self):
        archive = self.manager.create_archive()
        env_file = self.root / "capacity-panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=old\n".format(
                self.hmac_key.hex()
            ),
            encoding="utf-8",
        )
        def logical_database_digest():
            with sqlite_connection(str(self.database.path)) as connection:
                dump = "\n".join(connection.iterdump()).encode("utf-8")
            return self.manager._sha256(dump)

        original_database_digest = logical_database_digest()
        no_space = type("DiskUsage", (), {"total": 1, "used": 1, "free": 0})()

        with mock.patch("hysteria2_panel.shutil.disk_usage", return_value=no_space):
            with self.assertRaisesRegex(BackupValidationError, "空间"):
                self.manager.apply_archive(
                    archive,
                    env_file=env_file,
                    backup_root=self.root / "capacity-backups",
                )

        self.assertEqual(
            original_database_digest,
            logical_database_digest(),
        )

    def test_restore_artifact_retention_is_bounded_by_age_and_count(self):
        retention_root = self.root / "retention"
        retention_root.mkdir()
        now = time.time()
        entries = []
        for index in range(12):
            entry = retention_root / (
                "restore-20260822T1200{:02d}Z-{:08x}".format(index, index)
            )
            entry.mkdir()
            modified = now - index
            os.utime(entry, (modified, modified))
            entries.append(entry)
        manual = retention_root / "restore-manual-do-not-delete"
        manual.mkdir()
        os.utime(manual, (now - 86400, now - 86400))
        protected = entries[-1]

        self.manager._prune_entries(
            retention_root,
            hysteria2_panel.RESTORE_BACKUP_NAME_PATTERN,
            retention_seconds=5,
            maximum=3,
            keep=(protected,),
        )

        self.assertEqual(
            {entries[0].name, entries[1].name, protected.name, manual.name},
            {path.name for path in retention_root.iterdir()},
        )

    def test_expired_certificate_archive_is_rejected(self):
        archive = self.manager.create_archive()
        _not_before, expires_at = certificate_validity_timestamps(self.certificate)

        with mock.patch.object(
            hysteria2_panel.time, "time", return_value=expires_at + 1
        ):
            with self.assertRaisesRegex(BackupValidationError, "证书.*过期"):
                self.manager.validate_archive(archive)

    def test_not_yet_valid_certificate_archive_is_rejected(self):
        archive = self.manager.create_archive()
        not_before, _expires_at = certificate_validity_timestamps(self.certificate)

        with mock.patch.object(
            hysteria2_panel.time, "time", return_value=not_before - 1
        ):
            with self.assertRaisesRegex(BackupValidationError, "证书尚未生效"):
                self.manager.validate_archive(archive)

    def test_archive_rejects_missing_or_malformed_audit_metadata(self):
        archive = self.manager.create_archive()
        with zipfile.ZipFile(archive) as package:
            payloads = {
                name: package.read(name) for name in package.namelist()
            }

        def without_created_at(manifest):
            manifest.pop("createdAt")

        def invalid_created_at(manifest):
            manifest["createdAt"] = "not-a-timestamp"

        def invalid_panel_version(manifest):
            manifest["panelVersion"] = {"unexpected": "object"}

        for label, mutate in (
            ("missing-created-at", without_created_at),
            ("invalid-created-at", invalid_created_at),
            ("invalid-panel-version", invalid_panel_version),
        ):
            with self.subTest(label=label):
                manifest = json.loads(payloads["manifest.json"])
                mutate(manifest)
                modified = dict(payloads)
                modified["manifest.json"] = json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                candidate = self.root / (label + ".zip")
                with zipfile.ZipFile(
                    candidate, "w", compression=zipfile.ZIP_DEFLATED
                ) as package:
                    for name, value in modified.items():
                        package.writestr(name, value)

                with self.assertRaisesRegex(
                    BackupValidationError, "备份清单元数据无效"
                ):
                    self.manager.validate_archive(candidate)


if __name__ == "__main__":
    unittest.main()
