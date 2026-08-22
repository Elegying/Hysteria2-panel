import hashlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import hysteria2_panel
from hysteria2_panel import Database
from test_panel import create_test_certificate


class RestoreRecoveryStreamingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work_dir = self.root / "work"
        self.work_dir.mkdir()
        self.hmac_key = b"r" * 32
        self.database_path = self.root / "panel.db"
        database = Database(self.database_path, self.hmac_key)
        database.initialize()
        database.create_proxy_user("alice")
        self.certificate, self.private_key = create_test_certificate(self.root)
        certificate_bytes = self.certificate.read_bytes()
        pin = hysteria2_panel.BackupManager._certificate_pin(certificate_bytes)
        self.env_file = self.root / "panel.env"
        self.env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN={}\n".format(
                self.hmac_key.hex(), pin
            ),
            encoding="utf-8",
        )
        os.chmod(self.database_path, 0o600)
        os.chmod(self.certificate, 0o640)
        os.chmod(self.private_key, 0o640)
        os.chmod(self.env_file, 0o640)
        self.record = {
            "databasePath": str(self.database_path),
            "tlsCert": str(self.certificate),
            "tlsKey": str(self.private_key),
            "envFile": str(self.env_file),
            "workDir": str(self.work_dir),
            "publicHost": "vpn.example.test",
            "hysteriaPort": 19999,
            "nodeName": "test-node",
        }

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def _reject_large_reads(original):
        def guarded(path, maximum, *args, **kwargs):
            if Path(path).name in {"panel.db", "incoming.zip"}:
                raise AssertionError("large recovery files must be streamed")
            return original(path, maximum, *args, **kwargs)

        return guarded

    def test_current_identity_hashes_database_without_materializing_it(self):
        original = hysteria2_panel._read_secure_regular
        with mock.patch(
            "hysteria2_panel._read_secure_regular",
            side_effect=self._reject_large_reads(original),
        ):
            identity = hysteria2_panel._validate_current_restore_identity(
                self.record, root_uid=os.getuid()
            )

        self.assertEqual(
            hashlib.sha256(self.database_path.read_bytes()).hexdigest(),
            identity["panel.db"],
        )

    def test_rollback_restores_database_without_materializing_it(self):
        backup_dir = self.root / "restore-20260822T000000Z-1234abcd"
        backup_dir.mkdir(mode=0o700)
        database_backup = backup_dir / "panel.db"
        hysteria2_panel.BackupManager._copy_database(
            self.database_path, database_backup
        )
        os.chmod(database_backup, 0o600)
        for source, name in (
            (self.certificate, "server.crt"),
            (self.private_key, "server.key"),
            (self.env_file, "panel.env"),
        ):
            shutil.copyfile(source, backup_dir / name)
            os.chmod(backup_dir / name, 0o600)
        self.record["backupDir"] = str(backup_dir)
        self.record["oldFiles"] = {
            name: hashlib.sha256((backup_dir / name).read_bytes()).hexdigest()
            for name in ("panel.db", "server.crt", "server.key", "panel.env")
        }

        original = hysteria2_panel._read_secure_regular
        with mock.patch(
            "hysteria2_panel._read_secure_regular",
            side_effect=self._reject_large_reads(original),
        ):
            hysteria2_panel._restore_old_files(self.record, root_uid=os.getuid())

        self.assertEqual(
            self.record["oldFiles"]["panel.db"],
            hashlib.sha256(self.database_path.read_bytes()).hexdigest(),
        )

    def test_rollback_checks_peak_capacity_before_replacing_any_file(self):
        backup_dir = self.root / "restore-20260822T000000Z-8765abcd"
        backup_dir.mkdir(mode=0o700)
        database_backup = backup_dir / "panel.db"
        hysteria2_panel.BackupManager._copy_database(
            self.database_path, database_backup
        )
        os.chmod(database_backup, 0o600)
        for source, name in (
            (self.certificate, "server.crt"),
            (self.private_key, "server.key"),
            (self.env_file, "panel.env"),
        ):
            shutil.copyfile(source, backup_dir / name)
            os.chmod(backup_dir / name, 0o600)
        self.record["backupDir"] = str(backup_dir)
        self.record["oldFiles"] = {
            name: hashlib.sha256((backup_dir / name).read_bytes()).hexdigest()
            for name in ("panel.db", "server.crt", "server.key", "panel.env")
        }
        no_space = type("DiskUsage", (), {"total": 1, "used": 1, "free": 0})()

        with mock.patch(
            "hysteria2_panel.shutil.disk_usage", return_value=no_space
        ), mock.patch.object(
            hysteria2_panel.BackupManager, "_replace_file"
        ) as replace_file:
            with self.assertRaisesRegex(hysteria2_panel.BackupValidationError, "空间"):
                hysteria2_panel._restore_old_files(
                    self.record, root_uid=os.getuid()
                )

        replace_file.assert_not_called()

    def test_orphan_quarantine_is_bounded_across_repeated_recovery(self):
        orphan_work = self.root / "orphan-work"
        orphan_work.mkdir(mode=0o700)
        pending = orphan_work / "pending-restore.zip"
        manual = orphan_work / "failed-restore-manual.zip"
        manual.write_bytes(b"operator-owned")
        os.chmod(manual, 0o600)
        for index in range(hysteria2_panel.FAILED_RESTORE_MAX_ENTRIES + 2):
            pending.write_bytes("orphan-{}".format(index).encode("ascii"))
            os.chmod(pending, 0o600)
            hysteria2_panel.recover_restore_files(
                lock_path=self.root / "orphan.lock",
                marker_path=self.root / "orphan-marker",
                pending_path=pending,
                captured_path=self.root / "orphan-captured",
                work_dir=orphan_work,
                pending_uid=os.getuid(),
                expected_uid=os.getuid(),
                strict_paths=False,
            )

        self.assertEqual(
            hysteria2_panel.FAILED_RESTORE_MAX_ENTRIES,
            len(
                [
                    path
                    for path in orphan_work.iterdir()
                    if hysteria2_panel.FAILED_RESTORE_NAME_PATTERN.fullmatch(
                        path.name
                    )
                ]
            ),
        )
        self.assertEqual(b"operator-owned", manual.read_bytes())

    def test_boot_recovery_handles_upload_hardlink_crash_window(self):
        orphan_work = self.root / "hardlink-work"
        orphan_work.mkdir(mode=0o700)
        temporary_upload = orphan_work / ".upload-abcdefgh.zip"
        temporary_upload.write_bytes(b"captured before temporary unlink")
        os.chmod(temporary_upload, 0o600)
        pending = orphan_work / "pending-restore.zip"
        os.link(temporary_upload, pending)

        hysteria2_panel.recover_restore_files(
            lock_path=self.root / "hardlink.lock",
            marker_path=self.root / "hardlink-marker",
            pending_path=pending,
            captured_path=self.root / "hardlink-captured",
            work_dir=orphan_work,
            pending_uid=os.getuid(),
            expected_uid=os.getuid(),
            strict_paths=False,
        )

        self.assertFalse(temporary_upload.exists())
        self.assertFalse(pending.exists())
        self.assertEqual(1, len(list(orphan_work.glob("failed-restore-*.zip"))))

    def test_boot_recovery_cleans_only_strict_known_temporary_names(self):
        cleanup_work = self.root / "cleanup-work"
        cleanup_work.mkdir(mode=0o700)
        marker = self.root / "cleanup-marker"
        marker.touch(mode=0o600)
        target_root = self.root / "targets"
        target_root.mkdir()
        known = [
            cleanup_work / ".backup-abcdefgh.zip",
            cleanup_work / ".upload-abcdefgh.zip",
            cleanup_work / ".consumed-restore-0123456789abcdef.zip",
            cleanup_work / ".restore-orphan.abcdefgh",
            cleanup_work / ".restore-move.abcdefgh",
            cleanup_work / ".consumed-orphan-0123456789abcdef",
            self.root / ".restore-capture.abcdefgh",
            self.root / ".restore-transaction.abcdefgh",
            self.root / ".consumed-orphan-fedcba9876543210",
            target_root / ".restore-abcdefgh",
        ]
        for path in known:
            path.write_bytes(b"temporary")
            os.chmod(path, 0o600)
        temporary_directory = cleanup_work / "tmpabcdefgh"
        temporary_directory.mkdir(mode=0o700)
        unsafe = cleanup_work / ".backup-ijklmnop.zip"
        unsafe.write_bytes(b"must stay")
        os.chmod(unsafe, 0o644)
        unrelated = cleanup_work / "operator-file.zip"
        unrelated.write_bytes(b"must stay")
        record = dict(self.record)
        record.update(
            {
                "databasePath": str(target_root / "panel.db"),
                "tlsCert": str(target_root / "server.crt"),
                "tlsKey": str(target_root / "server.key"),
                "envFile": str(target_root / "panel.env"),
            }
        )

        with mock.patch.object(
            hysteria2_panel, "_read_restore_transaction", return_value=record
        ), mock.patch.object(
            hysteria2_panel, "_reconcile_to_services_pending"
        ) as reconcile:
            hysteria2_panel.recover_restore_files(
                lock_path=self.root / "cleanup.lock",
                marker_path=marker,
                pending_path=cleanup_work / "pending-restore.zip",
                captured_path=self.root / "cleanup-marker.archive",
                work_dir=cleanup_work,
                pending_uid=os.getuid(),
                expected_uid=os.getuid(),
                strict_paths=False,
            )

        reconcile.assert_called_once()
        self.assertTrue(all(not path.exists() for path in known))
        self.assertFalse(temporary_directory.exists())
        self.assertTrue(unsafe.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
