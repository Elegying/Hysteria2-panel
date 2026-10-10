"""Keep pending traffic intact when maintenance hands collection back to a live panel."""

import contextlib
import functools
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import hysteria2_panel as panel


class Stats:
    def __init__(self, tx=0, on_collect=None):
        self.tx = tx
        self.collections = 0
        self.on_collect = on_collect

    def collect_and_clear(self):
        if self.on_collect is not None:
            self.on_collect()
        self.collections += 1
        tx, self.tx = self.tx, 0
        return {"fixture": {"tx": tx, "rx": 0}} if tx else {}

    def online(self):
        return {}

    def dump_streams(self):
        return []

    def kick_many(self, _names):
        pass


class MaintenanceJournalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.settings = SimpleNamespace(
            database_path=self.root / "panel.db", hmac_key=b"r" * 32,
            local_origin_id="local:" + "a" * 32, node_name="fixture",
            hysteria_port=443, panel_port=19998,
        )
        self.database = panel.Database(self.settings.database_path, self.settings.hmac_key)
        self.database.initialize()
        self.user = self.database.create_proxy_user("fixture")
        self.traffic_lock = self.root / "traffic-lock"
        self.maintenance_lock = self.root / "maintenance-lock"
        self.auth_gate = self.root / "egress-active"
        for path in (self.traffic_lock, self.maintenance_lock):
            path.touch(mode=0o640)
            path.chmod(0o640)
        self.real_slot = panel.maintenance_upload_slot
        self.real_exclusive = panel.exclusive_maintenance_lock
        # Keep real flock and mode checks, using this fixture's owner instead of root.
        patcher = mock.patch.object(panel, "maintenance_upload_slot", side_effect=self._slot)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.foreground_stats = Stats()
        self.foreground = self._manager(self.foreground_stats)
        self.journal = self.root / "pending-traffic.json"

    def _slot(self, path, **kwargs):
        kwargs["expected_uid"] = os.getuid()
        return self.real_slot(path, **kwargs)

    def _exclusive(self, path=None, **kwargs):
        kwargs.update(expected_uid=os.getuid(), expected_mode=0o640)
        return self.real_exclusive(path or self.maintenance_lock, **kwargs)

    def _manager(self, stats):
        return panel.UsageManager(
            self.database, stats, local_origin_id=self.settings.local_origin_id,
            maintenance_lock_path=self.traffic_lock,
        )

    def _leave_foreground_batch(self, committed=False):
        self.foreground_stats.tx = 100
        domains = [{"user": "fixture", "domain": "example.test", "tx": 12, "rx": 0}]
        with mock.patch.object(self.foreground.domain_usage_collector, "collect", return_value=domains):
            if committed:
                with mock.patch.object(self.foreground, "_remove_pending_traffic_locked", side_effect=OSError("synthetic cleanup failure")):
                    with self.assertRaises(OSError):
                        self.foreground.collect_once()
            else:
                with mock.patch.object(self.database, "apply_traffic_batch", side_effect=sqlite3.OperationalError("synthetic database failure")):
                    with self.assertRaises(sqlite3.OperationalError):
                        self.foreground.collect_once()

    def _failed_policy_switch(self):
        def assert_exclusive_lock():
            with self.assertRaisesRegex(RuntimeError, "维护任务"):
                with self._slot(self.traffic_lock, expected_gid=os.getgid()):
                    self.fail("maintenance must exclude foreground collection")

        stats = Stats(200, on_collect=assert_exclusive_lock)
        original_apply = panel.Database.apply_traffic_batch

        def fail_new_batch(database, batch_id, traffic, **kwargs):
            if traffic.get("fixture", {}).get("tx") == 200:
                raise sqlite3.OperationalError("synthetic maintenance database failure")
            return original_apply(database, batch_id, traffic, **kwargs)

        quiesce = functools.partial(panel.quiesce_stats_client, sleeper=lambda _delay: None)
        gate = functools.partial(panel.egress_auth_gate, path=self.auth_gate)
        with mock.patch.object(panel.Settings, "from_mapping", return_value=self.settings), \
                mock.patch.object(panel.os, "geteuid", return_value=0), \
                mock.patch.object(panel, "exclusive_maintenance_lock", side_effect=self._exclusive), \
                mock.patch.object(panel, "TRAFFIC_COLLECTION_LOCK_PATH", self.traffic_lock), \
                mock.patch.object(panel, "egress_auth_gate", side_effect=gate), \
                mock.patch.object(panel, "_systemd_unit_state", side_effect=[("loaded", "active"), ("not-found", "inactive")]), \
                mock.patch.object(panel, "quiesce_stats_client", side_effect=quiesce), \
                mock.patch.object(panel, "make_stats_client", return_value=stats), \
                mock.patch.object(panel.Database, "apply_traffic_batch", fail_new_batch), \
                mock.patch.object(panel.EgressPolicyManager, "apply") as apply_policy, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(sqlite3.OperationalError):
                panel.main(["apply-egress-policy", "web"])
        apply_policy.assert_not_called()
        self.assertEqual(1, stats.collections)
        self.assertFalse(self.auth_gate.exists())
        self.assertEqual(200, json.loads(self.journal.read_text())["traffic"]["fixture"]["tx"])
        self.assertEqual(0o600, self.journal.stat().st_mode & 0o777)
        self.assertEqual(self.database.path.stat().st_uid, self.journal.stat().st_uid)

    def _tx(self):
        return self.database.get_proxy_user(self.user["id"])["tx_bytes"]

    def test_live_panel_reloads_a_maintenance_journal_when_its_memory_is_empty(self):
        self._failed_policy_switch()
        self.foreground_stats.tx = 50

        self.foreground.collect_once()

        self.assertEqual(250, self._tx())
        self.assertFalse(self.journal.exists())

    def test_stale_foreground_batch_cannot_delete_the_new_maintenance_batch(self):
        self._leave_foreground_batch()
        self._failed_policy_switch()
        self.foreground_stats.tx = 50

        self.foreground.collect_once()

        self.assertEqual(350, self._tx())
        with panel.sqlite_connection(str(self.database.path)) as connection:
            self.assertEqual(12, connection.execute("SELECT SUM(tx_bytes) FROM domain_usage_monthly").fetchone()[0])
        self.assertFalse(self.journal.exists())

    def test_committed_foreground_batch_is_not_counted_twice_during_handoff(self):
        self._leave_foreground_batch(committed=True)
        self._failed_policy_switch()
        self.foreground_stats.tx = 50

        self.foreground.collect_once()

        self.assertEqual(350, self._tx())
        self.assertFalse(self.journal.exists())

    def test_failed_handoff_replay_preserves_the_journal_and_unread_counters(self):
        self._leave_foreground_batch()
        self._failed_policy_switch()
        original = self.journal.read_bytes()
        self.foreground_stats.tx = 50
        before_collections = self.foreground_stats.collections
        apply = self.database.apply_traffic_batch

        def fail_new_batch(batch_id, traffic, **kwargs):
            if traffic.get("fixture", {}).get("tx") == 200:
                raise sqlite3.OperationalError("synthetic retry failure")
            return apply(batch_id, traffic, **kwargs)

        with mock.patch.object(self.database, "apply_traffic_batch", side_effect=fail_new_batch):
            with self.assertRaises(sqlite3.OperationalError):
                self.foreground.collect_once()
        self.assertEqual(original, self.journal.read_bytes())
        self.assertEqual(before_collections, self.foreground_stats.collections)
        self.assertEqual(50, self.foreground_stats.tx)
        self.foreground.collect_once()
        self.assertEqual(350, self._tx())

    def test_restart_after_handoff_commit_replays_without_duplicate_traffic(self):
        self._failed_policy_switch()
        with mock.patch.object(self.foreground, "_remove_pending_traffic_locked", side_effect=OSError("synthetic restart before cleanup")):
            with self.assertRaises(OSError):
                self.foreground.collect_once()
        self.assertEqual(200, self._tx())
        self.assertTrue(self.journal.exists())

        restarted = self._manager(Stats(50))
        restarted.collect_once()

        self.assertEqual(250, self._tx())
        self.assertFalse(self.journal.exists())

    def test_invalid_new_journal_fails_before_reading_or_clearing_more_traffic(self):
        self.journal.write_bytes(b'{"batch_id":')
        self.journal.chmod(0o600)
        self.foreground_stats.tx = 50

        with self.assertRaises(ValueError):
            self.foreground.collect_once()

        self.assertEqual(b'{"batch_id":', self.journal.read_bytes())
        self.assertEqual(0, self.foreground_stats.collections)
        self.assertEqual(50, self.foreground_stats.tx)
