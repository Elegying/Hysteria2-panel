import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from hysteria2_panel import (
    BackupManager,
    BackupValidationError,
    Database,
    sqlite_connection,
)
from offsite_backup import OffsiteBackupRunner
from test_offsite_backup import FakeWebDavClient
from test_panel import create_test_certificate


class PortableBackupCompactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.hmac_key = b"portable-backup-fixture-key-value"
        self.database = Database(self.root / "source.db", self.hmac_key)
        self.database.initialize()
        self.admin_id = self.database.upsert_admin(
            "source-admin", "source-password-for-fixture"
        )
        self.database.create_session(self.admin_id)
        self.database.create_mobile_session(
            self.admin_id, "fixture-device", "Fixture phone"
        )
        self.database.audit(
            "source-admin", "fixture", "portable-backup", "192.0.2.10"
        )
        self.user = self.database.create_proxy_user(
            "alice",
            device_limit=7,
            traffic_limit_bytes=987654321,
            allow_udp_443=True,
        )
        self.database.update_proxy_user_limits(
            self.user["id"],
            device_limit=9,
            traffic_limit_bytes=1234567890,
            allow_udp_443=True,
            expected_generation=0,
        )
        self.database.set_proxy_user_enabled(
            self.user["id"], False, expected_generation=1
        )
        self.origin_id = "local:" + "1" * 32
        self.database.apply_traffic_batch(
            "1" * 32,
            {"alice": {"tx": 123456, "rx": 654321}},
            origin_id=self.origin_id,
            origin_kind="local",
            origin_name="Fixture local origin",
        )
        self.database.set_origin_budget(
            self.origin_id,
            limit_bytes=5 * 1024**4,
            warning_percent=73,
            reset_day=12,
            manual_used_bytes=456789,
            actor="source-admin",
            updated_at=2_000_000_000,
        )
        self.certificate, self.private_key = create_test_certificate(self.root)
        self.work_dir = self.root / "work"
        self.lock_path = self.root / "maintenance.lock"
        self.lock_path.touch(mode=0o600)
        self.manager = self._manager(
            self.database,
            self.hmac_key,
            self.certificate,
            self.private_key,
            self.work_dir,
            self.lock_path,
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def _manager(database, hmac_key, certificate, private_key, work_dir, lock_path):
        return BackupManager(
            database=database,
            hmac_key=hmac_key,
            tls_cert=certificate,
            tls_key=private_key,
            public_host="vpn.example.test",
            hysteria_port=19999,
            node_name="Fixture node",
            work_dir=work_dir,
            maintenance_lock_path=lock_path,
            maintenance_lock_owner=os.geteuid(),
            maintenance_lock_mode=0o600,
            restore_marker_path=work_dir.parent / "restore-active",
        )

    def _populate_node_runtime(self, traffic_batch_count):
        now = 2_000_000_000
        node_id = "a" * 32
        with sqlite_connection(self.database.path, timeout=30) as connection:
            connection.execute(
                """INSERT INTO nodes(
                    node_id, name, status, created_at, policy_state,
                    data_plane_state, lifecycle_state
                ) VALUES (?, 'Fixture remote', 'pending_verification', ?,
                    'protocol_ready', 'installed', 'active')""",
                (node_id, now),
            )
            connection.execute(
                """INSERT INTO node_enrollments(
                    enrollment_id, node_id, token_digest, created_by,
                    created_at, expires_at
                ) VALUES ('enrollment', ?, 'enrollment-digest', 'source-admin', ?, ?)""",
                (node_id, now, now + 3600),
            )
            connection.execute(
                "INSERT INTO node_heartbeat_nonces VALUES (?, 'heartbeat-nonce', ?)",
                (node_id, now),
            )
            connection.execute(
                "INSERT INTO node_request_nonces VALUES (?, 'fixture', 'request-nonce', ?)",
                (node_id, now),
            )
            connection.execute(
                """INSERT INTO node_online_snapshots(
                    node_id, snapshot_id, sequence, observed_at,
                    traffic_acked_at, accepted_at
                ) VALUES (?, 'snapshot', 1, ?, ?, ?)""",
                (node_id, now, now, now),
            )
            connection.execute(
                "INSERT INTO node_online_counts VALUES (?, 'alice', 2)",
                (node_id,),
            )
            connection.execute(
                """INSERT INTO node_auth_decisions(
                    node_id, request_id, decision_id, allowed, user_name,
                    created_at, expires_at, absorbed_at
                ) VALUES (?, 'request', 'decision', 1, 'alice', ?, ?, NULL)""",
                (node_id, now, now + 60),
            )
            connection.execute(
                "INSERT INTO local_auth_leases VALUES ('lease', 'alice', ?, ?)",
                (now, now + 60),
            )
            connection.execute(
                """INSERT INTO node_commands(
                    command_id, node_id, kind, payload, created_at,
                    next_attempt_at
                ) VALUES ('command', ?, 'fixture', '{}', ?, ?)""",
                (node_id, now, now),
            )
            connection.execute(
                """INSERT INTO node_data_plane_bootstrap_grants(
                    grant_id, node_id, token_digest, bound_ip, created_by,
                    created_at, expires_at
                ) VALUES ('grant', ?, 'grant-digest', '192.0.2.20',
                    'source-admin', ?, ?)""",
                (node_id, now, now + 60),
            )
            connection.executemany(
                """INSERT INTO node_traffic_batches(
                    node_id, batch_id, unknown_users, applied_at
                ) VALUES (?, ?, 0, ?)""",
                (
                    (
                        node_id,
                        hashlib.sha256(
                            "fixture-batch-{}".format(index).encode("ascii")
                        ).hexdigest(),
                        now + index,
                    )
                    for index in range(traffic_batch_count)
                ),
            )

    def _extract_database(self, archive, name="portable.db"):
        destination = self.root / name
        with zipfile.ZipFile(archive) as package, package.open(
            "data/panel.db"
        ) as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        return destination

    @staticmethod
    def _logical_digest(database_path):
        with sqlite_connection(database_path) as connection:
            return hashlib.sha256(
                "\n".join(connection.iterdump()).encode("utf-8")
            ).hexdigest()

    def test_all_application_tables_have_an_explicit_portable_classification(self):
        with sqlite_connection(self.database.path) as connection:
            actual = BackupManager._application_tables(connection)
        restored = set(BackupManager.RESTORED_TABLE_COLUMNS)
        runtime = set(BackupManager.RUNTIME_TABLES)

        self.assertFalse(restored & runtime)
        self.assertEqual(actual, restored | runtime)

    def test_unknown_table_stops_backup_instead_of_copying_or_deleting_it(self):
        with sqlite_connection(self.database.path) as connection:
            connection.execute(
                "CREATE TABLE future_unclassified_state(value TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO future_unclassified_state VALUES ('fixture-value')"
            )

        with self.assertRaisesRegex(BackupValidationError, "未分类"):
            self.manager.create_archive()

        with sqlite_connection(self.database.path) as connection:
            self.assertEqual(
                [("fixture-value",)],
                connection.execute(
                    "SELECT value FROM future_unclassified_state"
                ).fetchall(),
            )
        self.assertEqual([], list(self.work_dir.iterdir()))

    def test_large_runtime_ledger_is_removed_compacted_and_restores_exact_business_data(self):
        self._populate_node_runtime(100_001)
        source_inode = self.database.path.stat().st_ino
        source_digest = self._logical_digest(self.database.path)
        source_size = self.database.path.stat().st_size
        started = time.monotonic()

        archive = self.manager.create_archive()
        elapsed = time.monotonic() - started
        portable_database = self._extract_database(archive)

        with zipfile.ZipFile(archive) as package:
            self.assertEqual(
                {
                    "manifest.json",
                    "data/panel.db",
                    "secrets/hmac-key.hex",
                    "tls/server.crt",
                    "tls/server.key",
                },
                set(package.namelist()),
            )
            self.assertEqual(
                self.hmac_key,
                bytes.fromhex(
                    package.read("secrets/hmac-key.hex").decode("ascii").strip()
                ),
            )
            self.assertEqual(
                self.certificate.read_bytes(), package.read("tls/server.crt")
            )
            self.assertEqual(
                self.private_key.read_bytes(), package.read("tls/server.key")
            )
            manifest = json.loads(package.read("manifest.json"))
            self.assertEqual(1, manifest["formatVersion"])

        with sqlite_connection(portable_database) as connection:
            self.assertEqual([("ok",)], connection.execute("PRAGMA quick_check").fetchall())
            self.assertEqual([], connection.execute("PRAGMA foreign_key_check").fetchall())
            BackupManager._assert_portable_table_contract(connection)
            for table in BackupManager.RUNTIME_TABLES:
                self.assertEqual(
                    0,
                    connection.execute(
                        "SELECT COUNT(*) FROM {}".format(table)  # nosec B608
                    ).fetchone()[0],
                    table,
                )

        self.assertTrue(
            self.manager._restored_rows_equal(self.database.path, portable_database)
        )
        self.assertEqual(source_inode, self.database.path.stat().st_ino)
        self.assertEqual(source_digest, self._logical_digest(self.database.path))
        with sqlite_connection(self.database.path) as connection:
            self.assertEqual(
                100_001,
                connection.execute(
                    "SELECT COUNT(*) FROM node_traffic_batches"
                ).fetchone()[0],
            )

        raw_snapshot = self.root / "untrimmed.db"
        BackupManager._copy_database(self.database.path, raw_snapshot)
        raw_archive = self.root / "untrimmed.zip"
        with zipfile.ZipFile(
            raw_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as package:
            package.write(raw_snapshot, "data/panel.db")
        self.assertLess(archive.stat().st_size, raw_archive.stat().st_size * 0.10)
        self.assertLess(archive.stat().st_size, 1024**2)
        self.assertLess(portable_database.stat().st_size, source_size * 0.10)
        self.assertLess(elapsed, 60)

        target_root = self.root / "target"
        target_root.mkdir()
        target_hmac = b"target-server-current-hmac-value"
        target_database = Database(target_root / "panel.db", target_hmac)
        target_database.initialize()
        target_admin_id = target_database.upsert_admin(
            "target-admin", "target-admin-password"
        )
        old_user = target_database.create_proxy_user("old-target-user")
        target_certificate, target_key = create_test_certificate(
            target_root, "vpn.example.test"
        )
        target_lock = target_root / "maintenance.lock"
        target_lock.touch(mode=0o600)
        target_manager = self._manager(
            target_database,
            target_hmac,
            target_certificate,
            target_key,
            target_root / "work",
            target_lock,
        )
        env_file = target_root / "panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=fixture-old-pin\n".format(
                target_hmac.hex()
            ),
            encoding="utf-8",
        )
        env_file.chmod(0o600)

        target_manager.apply_archive(
            archive,
            env_file=env_file,
            backup_root=target_root / "automatic-backups",
        )

        restored = Database(target_database.path, self.hmac_key)
        self.assertEqual(self.user["token"], restored.recover_proxy_token(self.user["id"]))
        self.assertIsNone(restored.authenticate_token(self.user["token"]))
        self.assertIsNone(restored.authenticate_token(old_user["token"]))
        restored_user = restored.get_proxy_user(self.user["id"])
        self.assertEqual(
            {
                "enabled": 0,
                "generation": 2,
                "device_limit": 9,
                "traffic_limit_bytes": 1234567890,
                "tx_bytes": 123456,
                "rx_bytes": 654321,
                "allow_udp_443": 1,
            },
            {
                key: restored_user[key]
                for key in (
                    "enabled",
                    "generation",
                    "device_limit",
                    "traffic_limit_bytes",
                    "tx_bytes",
                    "rx_bytes",
                    "allow_udp_443",
                )
            },
        )
        with sqlite_connection(target_database.path) as connection:
            self.assertEqual(
                [(target_admin_id, "target-admin")],
                connection.execute(
                    "SELECT id, username FROM admins ORDER BY id"
                ).fetchall(),
            )
        self.assertTrue(
            target_manager._restored_rows_equal(target_database.path, portable_database)
        )
        self.assertEqual(self.certificate.read_bytes(), target_certificate.read_bytes())
        self.assertEqual(self.private_key.read_bytes(), target_key.read_bytes())

    def test_vacuum_failure_does_not_publish_or_mutate_the_online_database(self):
        self._populate_node_runtime(10)
        source_inode = self.database.path.stat().st_ino
        source_digest = self._logical_digest(self.database.path)

        with mock.patch.object(
            self.manager,
            "_vacuum_into",
            side_effect=BackupValidationError("fixture compaction failure"),
        ):
            with self.assertRaisesRegex(BackupValidationError, "compaction failure"):
                self.manager.create_archive()

        self.assertEqual(source_inode, self.database.path.stat().st_ino)
        self.assertEqual(source_digest, self._logical_digest(self.database.path))
        self.assertEqual([], list(self.work_dir.iterdir()))

    def test_legacy_format_one_full_database_remains_compatible_without_runtime_import(self):
        self._populate_node_runtime(25)
        compact_archive = self.manager.create_archive()
        with zipfile.ZipFile(compact_archive) as package:
            payloads = {name: package.read(name) for name in package.namelist()}
        full_snapshot = self.root / "legacy-full.db"
        BackupManager._copy_database(self.database.path, full_snapshot)
        payloads["data/panel.db"] = full_snapshot.read_bytes()
        manifest = json.loads(payloads["manifest.json"])
        manifest["files"]["data/panel.db"] = {
            "sha256": hashlib.sha256(payloads["data/panel.db"]).hexdigest(),
            "size": len(payloads["data/panel.db"]),
        }
        payloads["manifest.json"] = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        legacy_archive = self.root / "legacy-format-one.zip"
        with zipfile.ZipFile(
            legacy_archive, "w", compression=zipfile.ZIP_DEFLATED
        ) as package:
            for name, value in payloads.items():
                package.writestr(name, value)

        target_root = self.root / "legacy-target"
        target_root.mkdir()
        target_hmac = b"legacy-target-current-hmac-value"
        target_database = Database(target_root / "panel.db", target_hmac)
        target_database.initialize()
        target_admin_id = target_database.upsert_admin(
            "target-admin", "target-password"
        )
        target_database.create_proxy_user("target-old-user")
        target_node_id = "b" * 32
        with sqlite_connection(target_database.path) as connection:
            connection.execute(
                """INSERT INTO nodes(
                    node_id, name, status, created_at, policy_state,
                    data_plane_state, lifecycle_state
                ) VALUES (?, 'Target current node', 'pending_verification', 1,
                    'standby', 'not_issued', 'active')""",
                (target_node_id,),
            )
        target_certificate, target_key = create_test_certificate(
            target_root, "vpn.example.test"
        )
        target_lock = target_root / "maintenance.lock"
        target_lock.touch(mode=0o600)
        target_manager = self._manager(
            target_database,
            target_hmac,
            target_certificate,
            target_key,
            target_root / "work",
            target_lock,
        )
        env_file = target_root / "panel.env"
        env_file.write_text(
            "HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN=fixture-old-pin\n".format(
                target_hmac.hex()
            ),
            encoding="utf-8",
        )
        env_file.chmod(0o600)

        target_manager.apply_archive(
            legacy_archive,
            env_file=env_file,
            backup_root=target_root / "automatic-backups",
        )

        restored = Database(target_database.path, self.hmac_key)
        self.assertEqual(self.user["token"], restored.recover_proxy_token(self.user["id"]))
        with sqlite_connection(target_database.path) as connection:
            self.assertEqual(
                [(target_admin_id, "target-admin")],
                connection.execute(
                    "SELECT id, username FROM admins ORDER BY id"
                ).fetchall(),
            )
            self.assertEqual(
                [(target_node_id, "Target current node")],
                connection.execute(
                    "SELECT node_id, name FROM nodes ORDER BY node_id"
                ).fetchall(),
            )

    def test_interrupted_compaction_and_zip_failure_remove_sensitive_temporaries(self):
        source_digest = self._logical_digest(self.database.path)

        def interrupted_vacuum(_source, destination):
            Path(destination).write_bytes(b"partial-sensitive-database")
            Path(destination).chmod(0o600)
            raise KeyboardInterrupt("fixture interruption")

        with mock.patch.object(
            self.manager, "_vacuum_into", side_effect=interrupted_vacuum
        ):
            with self.assertRaisesRegex(KeyboardInterrupt, "fixture interruption"):
                self.manager.create_archive()

        self.assertEqual(source_digest, self._logical_digest(self.database.path))
        self.assertEqual([], list(self.work_dir.iterdir()))

        with mock.patch.object(
            zipfile.ZipFile,
            "write",
            side_effect=OSError("fixture ZIP write failure"),
        ):
            with self.assertRaisesRegex(OSError, "ZIP write failure"):
                self.manager.create_archive()

        self.assertEqual(source_digest, self._logical_digest(self.database.path))
        self.assertEqual([], list(self.work_dir.iterdir()))

    def test_snapshot_and_compaction_temporaries_are_private(self):
        observed = {}
        vacuum_into = self.manager._vacuum_into

        def inspect_permissions(source, destination):
            observed["snapshot_mode"] = Path(source).stat().st_mode & 0o777
            observed["directory_mode"] = Path(destination).parent.stat().st_mode & 0o777
            vacuum_into(source, destination)
            observed["compact_mode"] = Path(destination).stat().st_mode & 0o777

        with mock.patch.object(
            self.manager, "_vacuum_into", side_effect=inspect_permissions
        ):
            archive = self.manager.create_archive()

        self.assertTrue(archive.is_file())
        self.assertEqual(
            {"snapshot_mode": 0o600, "directory_mode": 0o700, "compact_mode": 0o600},
            observed,
        )
        self.assertEqual(0o600, archive.stat().st_mode & 0o777)

    def test_live_wal_database_bytes_and_inode_are_not_changed_by_compaction(self):
        connection = sqlite_connection(str(self.database.path), timeout=30)
        with connection as live:
            live.execute("PRAGMA journal_mode = WAL")
            live.execute("PRAGMA wal_autocheckpoint = 0")
            live.execute(
                """INSERT INTO audit_log(
                    created_at, actor, action, target, remote_ip
                ) VALUES (2, 'fixture', 'wal-source', 'runtime', '192.0.2.30')"""
            )
            live.commit()
            database_inode = self.database.path.stat().st_ino
            database_bytes = self.database.path.read_bytes()
            wal_path = Path(str(self.database.path) + "-wal")
            self.assertTrue(wal_path.is_file())
            wal_inode = wal_path.stat().st_ino
            wal_bytes = wal_path.read_bytes()

            self.manager.create_archive()

            self.assertEqual(database_inode, self.database.path.stat().st_ino)
            self.assertEqual(database_bytes, self.database.path.read_bytes())
            self.assertEqual(wal_inode, wal_path.stat().st_ino)
            self.assertEqual(wal_bytes, wal_path.read_bytes())

    def test_backup_rejects_symlinked_identity_and_work_directory(self):
        certificate_link = self.root / "certificate-link.pem"
        certificate_link.symlink_to(self.certificate)
        linked_identity = self._manager(
            self.database,
            self.hmac_key,
            certificate_link,
            self.private_key,
            self.root / "linked-identity-work",
            self.lock_path,
        )
        with self.assertRaisesRegex(BackupValidationError, "路径不安全"):
            linked_identity.create_archive()

        real_work = self.root / "real-work"
        real_work.mkdir(mode=0o700)
        linked_work = self.root / "linked-work"
        linked_work.symlink_to(real_work, target_is_directory=True)
        unsafe_work = self._manager(
            self.database,
            self.hmac_key,
            self.certificate,
            self.private_key,
            linked_work,
            self.lock_path,
        )
        with self.assertRaisesRegex(BackupValidationError, "工作目录.*不安全"):
            unsafe_work.create_archive()

    def test_daily_offsite_upload_uses_the_verified_compact_archive(self):
        self._populate_node_runtime(2_000)
        config_path = self.root / "offsite.json"
        config_path.write_text(
            json.dumps(
                {
                    "endpoint": "https://backup.example.test/panel/",
                    "username": "fixture-user",
                    "password": "fixture-password",
                }
            ),
            encoding="utf-8",
        )
        config_path.chmod(0o600)
        client = FakeWebDavClient()
        runner = OffsiteBackupRunner(
            config_path=config_path,
            status_path=self.root / "offsite-status.json",
            archive_factory=self.manager.create_archive,
            expected_uid=os.geteuid(),
            status_gid=os.getegid(),
            client_factory=lambda _config: client,
        )

        result = runner.run()

        self.assertEqual("success", result["state"])
        uploaded = self.root / "uploaded.zip"
        uploaded.write_bytes(client.asserted_body)
        self.manager.validate_archive(uploaded)
        uploaded_database = self._extract_database(uploaded, "uploaded.db")
        with sqlite_connection(uploaded_database) as connection:
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM node_traffic_batches"
                ).fetchone()[0],
            )
            self.assertEqual([("ok",)], connection.execute("PRAGMA quick_check").fetchall())
        self.assertFalse(any(self.work_dir.glob("*.zip")))


if __name__ == "__main__":
    unittest.main()
