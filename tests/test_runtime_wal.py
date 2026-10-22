"""Keep live WAL sidecars owned by the service across root backup readers."""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import hysteria2_panel as panel


class RuntimeWalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.settings = panel.Settings.from_mapping({
            "HY2PANEL_DB": str(self.root / "panel.db"),
            "HY2PANEL_HMAC_KEY": "ab" * 32,
            "HY2PANEL_PUBLIC_HOST": "panel.example.test",
            "HY2PANEL_STATS_SECRET": "fixture-stats-secret",
            "HY2PANEL_CERT_PIN": "cd" * 32,
        })
        self.database = panel.Database(self.settings.database_path, self.settings.hmac_key)
        self.database.initialize()
        self.database.upsert_admin("fixture", "fixture-password")
        self.wal = Path(str(self.database.path) + "-wal")

    def run_service(self, observer, startup_failure=None):
        with mock.patch.object(panel, "make_stats_client", return_value=object()), \
                mock.patch.object(panel, "make_panel_server", side_effect=startup_failure), \
                mock.patch.object(panel, "make_internal_server"), \
                mock.patch.object(panel, "run_supervised_services", side_effect=observer):
            panel.run_service(self.settings)

    def test_idle_service_retains_wal_without_holding_a_read_transaction(self):
        def observe(*_args, **_kwargs):
            self.assertTrue(self.wal.exists(), "idle service must retain its own WAL")
            original_inode = self.wal.stat().st_ino
            self.database.create_proxy_user("during-backup")
            destination = self.root / "backup.db"
            panel.BackupManager._copy_database(self.database.path, destination)
            with self.database._connect() as connection:
                result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                self.assertEqual((0, 0, 0), tuple(result))
            self.assertEqual(original_inode, self.wal.stat().st_ino)
            self.assertEqual(0, self.wal.stat().st_size)
            with panel.sqlite_connection(str(destination)) as connection:
                self.assertEqual("during-backup", connection.execute(
                    "SELECT name FROM proxy_users").fetchone()[0])

        self.run_service(observe)
        self.assertFalse(self.wal.exists(), "service shutdown must close the keeper")

    def test_runtime_exception_closes_the_wal_keeper(self):
        def fail(*_args, **_kwargs):
            self.assertTrue(self.wal.exists())
            raise RuntimeError("fixture worker failed")

        with self.assertRaisesRegex(RuntimeError, "fixture worker failed"):
            self.run_service(fail)
        self.assertFalse(self.wal.exists())

    def test_startup_exception_closes_the_wal_keeper(self):
        with self.assertRaisesRegex(RuntimeError, "fixture bind failed"):
            self.run_service(None, RuntimeError("fixture bind failed"))
        self.assertFalse(self.wal.exists())


if __name__ == "__main__":
    unittest.main()
