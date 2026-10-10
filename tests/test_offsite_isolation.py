"""Daily backup must not become a second destructive traffic collector."""

import configparser
import contextlib
import io
import itertools
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import hysteria2_panel as panel
from test_panel import create_test_certificate


class Stats:
    def __init__(self, traffic=None):
        self.traffic = traffic or {}
        self.collections = 0

    def collect_and_clear(self):
        self.collections += 1
        traffic, self.traffic = self.traffic, {}
        return traffic

    def dump_streams(self):
        return []

    def online(self):
        return {}

    def kick_many(self, _names):
        pass


class OffsiteIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.key = b"h" * 32
        self.database = panel.Database(self.root / "panel.db", self.key)
        self.database.initialize()
        self.user = self.database.create_proxy_user("fixture")
        self.origin = "local:" + "a" * 32
        self.database.apply_traffic_batch("1" * 32, {"fixture": {"tx": 5, "rx": 0}})
        certificate, private_key = create_test_certificate(self.root)
        self.settings = SimpleNamespace(
            database_path=self.database.path, hmac_key=self.key,
            tls_cert=certificate, tls_key=private_key,
            public_host="vpn.example.test", hysteria_port=443,
            node_name="fixture", local_origin_id=self.origin,
        )
        self.lock = self.root / "maintenance.lock"
        self.lock.touch(mode=0o640)
        self.lock.chmod(0o640)
        self.archive = None

    def tearDown(self):
        self.temporary.cleanup()

    def _run_backup(self, stats, fail_background_batch=False):
        archive_result = []

        class Runner:
            def __init__(self, **kwargs):
                self.create_archive = kwargs["archive_factory"]

            def run(self):
                archive_result.append(self.create_archive())
                return {"state": "success"}

        original_init = panel.BackupManager.__init__
        original_apply = panel.Database.apply_traffic_batch

        def init_manager(manager, *args, **kwargs):
            kwargs.update(
                work_dir=self.root / "archives", maintenance_lock_path=self.lock,
                maintenance_lock_owner=os.getuid(), maintenance_lock_group=os.getgid(),
                restore_marker_path=self.root / "restore-active",
            )
            original_init(manager, *args, **kwargs)

        def apply_batch(database, batch_id, traffic, **kwargs):
            if fail_background_batch and traffic.get("fixture", {}).get("tx") == 200:
                raise OSError("synthetic storage unavailable")
            return original_apply(database, batch_id, traffic, **kwargs)

        with mock.patch.object(panel.Settings, "from_mapping", return_value=self.settings), \
                mock.patch.object(panel, "OffsiteBackupRunner", Runner), \
                mock.patch.object(panel.BackupManager, "__init__", init_manager), \
                mock.patch.object(panel.Database, "apply_traffic_batch", apply_batch), \
                mock.patch.object(panel, "make_stats_client", return_value=stats), \
                mock.patch.object(panel.grp, "getgrnam", return_value=SimpleNamespace(gr_gid=os.getgid())), \
                mock.patch.object(panel.os, "geteuid", side_effect=itertools.chain([0], itertools.repeat(os.getuid()))), \
                contextlib.redirect_stdout(io.StringIO()):
            result = panel.main(["offsite-backup"])
        self.archive = archive_result[0] if archive_result else None
        return result

    def _archived_tx(self):
        with zipfile.ZipFile(self.archive) as archive:
            snapshot = self.root / "snapshot.db"
            snapshot.write_bytes(archive.read("data/panel.db"))
        with contextlib.closing(sqlite3.connect(str(snapshot))) as connection:
            return connection.execute("SELECT tx_bytes FROM proxy_users WHERE name='fixture'").fetchone()[0]

    def test_daily_backup_keeps_live_counters_and_archives_committed_usage(self):
        stats = Stats({"fixture": {"tx": 200, "rx": 0}})

        self.assertEqual(0, self._run_backup(stats))

        self.assertEqual(0, stats.collections)
        self.assertEqual(5, self._archived_tx())
        self.assertEqual(5, self.database.get_proxy_user(self.user["id"])["tx_bytes"])
        self.assertEqual(200, stats.traffic["fixture"]["tx"])

    def test_daily_backup_preserves_journal_for_foreground_recovery(self):
        foreground = panel.UsageManager(
            self.database, Stats({"fixture": {"tx": 100, "rx": 0}}),
            local_origin_id=self.origin,
        )
        with mock.patch.object(self.database, "apply_traffic_batch", side_effect=OSError("synthetic storage unavailable")):
            with self.assertRaises(OSError):
                foreground.collect_once()
        journal = self.root / "pending-traffic.json"
        before = journal.read_bytes()
        remaining = Stats({"fixture": {"tx": 200, "rx": 0}})

        result = self._run_backup(remaining, fail_background_batch=True)
        after = journal.read_bytes()
        background_collections = remaining.collections
        foreground.stats_client = remaining
        foreground.collect_once()

        self.assertEqual(305, self.database.get_proxy_user(self.user["id"])["tx_bytes"])
        self.assertEqual(0, result)
        self.assertEqual(before, after)
        self.assertEqual(100, json.loads(after)["traffic"]["fixture"]["tx"])
        self.assertEqual(0, background_collections)
        self.assertFalse(journal.exists())
        self.assertEqual(5, self._archived_tx())

    def test_daily_backup_works_with_stopped_stats_endpoint(self):
        stats = Stats()
        with mock.patch.object(stats, "collect_and_clear", side_effect=ConnectionRefusedError) as collect:
            self.assertEqual(0, self._run_backup(stats))
        collect.assert_not_called()
        self.assertEqual(5, self._archived_tx())

    def test_daily_unit_does_not_activate_either_proxy_entrypoint(self):
        installer = (Path(__file__).resolve().parents[1] / "install.sh").read_text()
        body = installer.split("cat > /etc/systemd/system/hysteria2-panel-offsite-backup.service <<EOF\n", 1)[1]
        body = body.split("\nEOF", 1)[0]
        unit = configparser.ConfigParser(interpolation=None, strict=False)
        unit.read_string(body)
        dependencies = " ".join(unit["Unit"].get(kind, "") for kind in ("Requires", "Wants", "BindsTo", "Upholds")).split()
        self.assertNotIn("hysteria2-panel-server.service", dependencies)
        self.assertNotIn("hysteria2-panel-server-443.service", dependencies)
