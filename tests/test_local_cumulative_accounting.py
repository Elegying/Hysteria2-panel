"""Real loopback stats, SQLite, process interruption and maintenance handoff."""

import copy
import datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest import mock

import hysteria2_panel as panel
from hy2panel.accounting import LOCAL_STATS_UNITS


ROOT = Path(__file__).resolve().parents[1]


class LocalCumulativeAccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = panel.Database(self.root / "panel.db", b"a" * 32)
        self.db.initialize()
        self.user = self.db.create_proxy_user("alice")
        self.traffic = [{"alice": {"tx": 100, "rx": 200}}, {"alice": {"tx": 10, "rx": 20}}]
        self.epochs = ["a" * 32, "b" * 32]
        self.paths = []
        self.clients = []
        self.fail_endpoints = set()
        fixture = self
        for index, unit in enumerate(LOCAL_STATS_UNITS):
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass

                def do_GET(self):
                    current = self.server.endpoint_index
                    fixture.paths.append((current, self.path))
                    if self.path == "/dump/streams":
                        value = {"streams": []}
                    elif self.path == "/online":
                        value = {}
                    else:
                        if current in fixture.fail_endpoints:
                            self.send_error(503)
                            return
                        value = copy.deepcopy(fixture.traffic[current])
                        if self.path == "/traffic?clear=1":
                            fixture.traffic[current] = {}
                    body = json.dumps(value).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.endpoint_index = index
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            client = panel.HysteriaStatsClient(
                "http://127.0.0.1:{}".format(server.server_port), "synthetic",
                service_unit=unit,
            )
            client.service_epoch = lambda index=index: self.epochs[index]
            self.clients.append(client)

    def manager(self, clients=None, database=None, **options):
        clients = self.clients if clients is None else clients
        stats = clients[0] if len(clients) == 1 else panel.CombinedHysteriaStatsClient(*clients)
        return panel.UsageManager(database or self.db, stats, **options)

    def total(self, database=None):
        user = (database or self.db).get_proxy_user_by_name("alice")
        return user["tx_bytes"] + user["rx_bytes"]

    def test_samples_do_not_clear_and_restarts_count_only_deltas(self):
        manager = self.manager()
        manager.collect_once()
        self.assertEqual(330, self.total())
        self.assertEqual(100, self.traffic[0]["alice"]["tx"])
        self.traffic[0]["alice"]["tx"] += 7
        self.manager().collect_once()
        self.assertEqual(337, self.total())
        self.epochs[1] = "c" * 32
        self.traffic[1] = {"alice": {"tx": 40, "rx": 60}}
        self.manager().collect_once()
        self.assertEqual(437, self.total())
        self.assertNotIn("/traffic?clear=1", [path for _, path in self.paths])

    def test_process_exits_before_journal_after_journal_and_after_commit(self):
        worker = r'''
import os, sys
import hysteria2_panel as p
db = p.Database(sys.argv[1], b'a' * 32)
client = p.HysteriaStatsClient(sys.argv[2], 'synthetic', service_unit=p.LOCAL_STATS_UNITS[0])
client.service_epoch = lambda: 'a' * 32
manager = p.UsageManager(db, client)
collector = manager.cumulative_collector
mode = sys.argv[3]
save = collector._save
apply = collector.apply_batch
def interrupted_save(document):
    if mode == 'before-journal':
        os._exit(79)
    save(document)
    os._exit(79)
def interrupted_commit(*args, **kwargs):
    apply(*args, **kwargs)
    os._exit(79)
if mode == 'after-commit':
    collector.apply_batch = interrupted_commit
else:
    collector._save = interrupted_save
manager.collect_once()
'''
        for mode in ("before-journal", "after-journal", "after-commit"):
            with self.subTest(mode=mode):
                path = self.root / mode / "panel.db"
                db = panel.Database(path, b"a" * 32)
                db.initialize()
                db.create_proxy_user("alice")
                result = subprocess.run(
                    [sys.executable, "-c", worker, str(path), self.clients[0].base_url, mode],
                    cwd=ROOT, capture_output=True, text=True, timeout=10, check=False,
                )
                self.assertEqual(79, result.returncode, result.stderr)
                self.assertEqual(300 if mode == "after-commit" else 0, self.total(db))
                self.manager(clients=[self.clients[0]], database=db).collect_once()
                self.assertEqual(300, self.total(db))
                self.assertEqual(100, self.traffic[0]["alice"]["tx"])

    def test_database_failure_and_live_maintenance_handoff_replay_once(self):
        live = self.manager()
        with mock.patch.object(self.db, "apply_traffic_batch", side_effect=sqlite3.OperationalError("busy")):
            with self.assertRaises(sqlite3.OperationalError):
                live.collect_once()
        self.assertEqual(0, self.total())
        self.traffic[0]["alice"]["tx"] += 10
        maintenance = self.manager()
        maintenance.collect_once()
        self.assertEqual(340, self.total())
        self.traffic[1]["alice"]["rx"] += 20
        live.collect_once()
        self.assertEqual(360, self.total())

    def test_failed_journal_write_preserves_source_and_retries(self):
        manager = self.manager()
        with mock.patch.object(manager.cumulative_collector, "_save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                manager.collect_once()
        self.assertEqual(0, self.total())
        self.assertEqual(100, self.traffic[0]["alice"]["tx"])
        self.manager().collect_once()
        self.assertEqual(330, self.total())

    def test_real_sqlite_writer_lock_retains_cumulative_sample_for_recovery(self):
        manager = self.manager()
        with self.db._connect() as writer:
            writer.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                manager.collect_once()
            self.assertEqual(0, self.total())
            self.assertEqual(100, self.traffic[0]["alice"]["tx"])
        self.manager().collect_once()
        self.assertEqual(330, self.total())
        self.manager().collect_once()
        self.assertEqual(330, self.total())

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory write permissions")
    def test_real_read_only_directory_preserves_core_counters(self):
        manager = self.manager()
        self.root.chmod(0o500)
        try:
            with self.assertRaises(PermissionError):
                manager.collect_once()
            self.assertEqual(100, self.traffic[0]["alice"]["tx"])
        finally:
            self.root.chmod(0o700)
        self.manager().collect_once()
        self.assertEqual(330, self.total())

    def test_partial_failure_commits_healthy_entrypoint_without_double_counting(self):
        self.fail_endpoints.add(1)
        with self.assertRaises(OSError):
            self.manager().collect_once()
        self.assertEqual(300, self.total())
        self.fail_endpoints.clear()
        self.manager().collect_once()
        self.assertEqual(330, self.total())

    def test_external_clear_and_unstable_epoch_fail_closed(self):
        manager = self.manager()
        manager.collect_once()
        self.traffic[0] = {}
        with self.assertRaisesRegex(RuntimeError, "cleared outside"):
            manager.collect_once()
        self.assertEqual(330, self.total())
        self.assertFalse(manager.snapshot()["available"])
        with mock.patch.object(self.clients[0], "service_epoch", side_effect=["d" * 32, "e" * 32]):
            with self.assertRaisesRegex(RuntimeError, "restarted during"):
                self.manager(clients=[self.clients[0]]).collect_once()

    def test_oversized_response_never_destroys_upstream_counters(self):
        with mock.patch.object(panel, "MAX_STATS_RESPONSE_BYTES", 16):
            with self.assertRaises(ValueError):
                self.manager().collect_once()
        self.assertEqual(0, self.total())
        self.manager().collect_once()
        self.assertEqual(330, self.total())
        self.assertNotIn("/traffic?clear=1", [path for _, path in self.paths])

    def test_partial_endpoint_maintenance_preserves_the_other_checkpoint(self):
        self.manager().collect_once()
        self.traffic[0]["alice"]["tx"] += 11
        self.manager(clients=[self.clients[0]]).collect_once()
        self.traffic[1]["alice"]["rx"] += 13
        self.manager().collect_once()
        self.assertEqual(354, self.total())

    def test_old_pending_journal_is_replayed_before_first_cumulative_sample(self):
        journal = self.root / "pending-traffic.json"
        journal.write_text(json.dumps({"batch_id": "f" * 32,
                                       "traffic": {"alice": {"tx": 5, "rx": 6}}}))
        manager = self.manager()
        manager.collect_once()
        self.assertEqual(341, self.total())
        self.assertFalse(journal.exists())

    def test_manual_reset_and_traffic_edit_keep_the_core_baseline(self):
        manager = self.manager()
        manager.collect_once()
        manager.reset_user(self.user["id"])
        self.assertEqual(0, self.total())
        self.traffic[0]["alice"]["tx"] += 17
        manager.collect_once()
        self.assertEqual(17, self.total())
        current = self.db.get_proxy_user(self.user["id"])
        manager.update_user_limits(self.user["id"], device_limit=3,
                                   traffic_limit_bytes=current["traffic_limit_bytes"],
                                   expected_generation=current["generation"], used_traffic_bytes=1234)
        self.traffic[1]["alice"]["rx"] += 19
        manager.collect_once()
        self.assertEqual(1253, self.total())

    def test_month_boundary_and_failed_transaction_recover_without_rebilling_history(self):
        boundary = int(datetime.datetime.fromisoformat("2033-05-01T00:00:00+08:00").timestamp())
        now = [boundary - 1]
        clock = mock.patch.object(panel.time, "time", side_effect=lambda: now[0])
        clock.start()
        self.addCleanup(clock.stop)
        self.manager(wall_clock=lambda: boundary - 1).collect_once()
        self.assertEqual(330, self.total())
        self.traffic[0]["alice"]["tx"] += 7
        self.traffic[1]["alice"]["rx"] += 11
        now[0] = boundary
        with self.db._connect() as connection:
            connection.execute("CREATE TRIGGER fail_batch BEFORE INSERT ON applied_traffic_batches "
                               "BEGIN SELECT RAISE(ABORT, 'write unavailable'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.manager(wall_clock=lambda: boundary).collect_once()
        self.assertEqual(330, self.total())
        with self.db._connect() as connection:
            self.assertEqual("2033-04", connection.execute(
                "SELECT period FROM user_traffic_reset_state").fetchone()[0])
            connection.execute("DROP TRIGGER fail_batch")
        now[0] = boundary + 1
        recovered = self.manager(wall_clock=lambda: boundary + 1)
        recovered.collect_once()
        self.assertEqual(18, self.total())
        self.assertEqual(18, self.db.user_traffic_history(self.user["id"], now=boundary)["totalBytes"])
        self.traffic[0]["alice"]["tx"] += 5
        recovered.collect_once()
        self.assertEqual(23, self.total())

    def test_cumulative_quota_exhaustion_still_denies_auth_and_kicks_online_user(self):
        self.db.update_proxy_user_limits(self.user["id"], device_limit=2, traffic_limit_bytes=320)
        manager = self.manager()
        with mock.patch.object(manager.stats_client, "online", return_value={"alice": 1}), \
                mock.patch.object(manager.stats_client, "kick_many") as kick:
            manager.collect_once()
        self.assertEqual(330, self.total())
        kick.assert_called_once_with(["alice"])
        self.assertFalse(manager.authorize("alice"))
        self.assertEqual(330, self.total())

    def test_corrupt_symlink_and_oversized_journals_preserve_evidence(self):
        manager = self.manager()
        path = manager.cumulative_collector.path
        path.write_bytes(b"bad json")
        path.chmod(0o600)
        self.paths.clear()
        with self.assertRaises(ValueError):
            manager.collect_once()
        self.assertEqual(b"bad json", path.read_bytes())
        self.assertEqual([], self.paths)
        path.unlink()
        target = self.root / "target"
        target.write_text("preserve")
        path.symlink_to(target)
        with self.assertRaises(OSError):
            manager.collect_once()
        self.assertEqual("preserve", target.read_text())
        path.unlink()
        path.write_bytes(b"x" * 100)
        path.chmod(0o600)
        manager.cumulative_collector.maximum_bytes = 16
        with self.assertRaises(ValueError):
            manager.collect_once()
        self.assertEqual(100, path.stat().st_size)

    def test_production_factories_and_cli_enable_cumulative_only_for_normal_service(self):
        settings = SimpleNamespace(stats_url=self.clients[0].base_url,
                                   stats_443_url=self.clients[1].base_url,
                                   stats_secret="synthetic", hysteria_port=19999)
        stats = panel.make_stats_client(settings)
        self.assertEqual(list(LOCAL_STATS_UNITS), [client.service_unit for client in stats.clients])
        legacy = panel.make_stats_client(settings, legacy_traffic=True)
        self.assertTrue(all(client.service_unit is None for client in legacy.clients))
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("builtins.print") as output:
            self.assertEqual(0, panel.main(["accounting-mode"]))
        output.assert_called_once_with("cumulative-v1")

    def test_sync_cli_factory_preserves_counters_and_journal_across_calls(self):
        settings = SimpleNamespace(
            stats_url=self.clients[0].base_url, stats_443_url=self.clients[1].base_url,
            stats_secret="synthetic", hysteria_port=19999, database_path=self.db.path,
            hmac_key=b"a" * 32, local_origin_id="local:" + "0" * 32, node_name="fixture",
        )
        with mock.patch.object(panel.Settings, "from_mapping", return_value=settings), \
                mock.patch.object(panel.os, "geteuid", return_value=0), \
                mock.patch.object(panel, "service_epoch", side_effect=lambda unit: self.epochs[LOCAL_STATS_UNITS.index(unit)]):
            self.assertEqual(0, panel.main(["sync-traffic"]))
            self.assertEqual(0, panel.main(["sync-traffic", "--primary-only"]))
        self.assertEqual(330, self.total())
        self.assertNotIn("/traffic?clear=1", [path for _, path in self.paths])

    def installer_options(self, installed):
        source = (ROOT / "install.sh").read_text()
        start = source.index("select_panel_accounting_options() {")
        helper = source[start:source.index("\n}\n", start) + 2]
        probe = self.root / "installed.py"
        probe.write_text({"legacy": "raise SystemExit(2)",
                          "cumulative": "print('cumulative-v1')",
                          "broken": "raise SystemExit(1)",
                          "unknown": "print('future-mode')"}[installed])
        result = subprocess.run(
            ["bash", "-eu"], text=True, capture_output=True, check=False,
            input=helper + '\nTRAFFIC_SYNC_OPTIONS=(--primary-only)\n'
            'select_panel_accounting_options "$PROBE"\nprintf "%s\\n" "${TRAFFIC_SYNC_OPTIONS[@]}"\n',
            env={**os.environ, "PROBE": str(probe), "PYTHON_BIN": sys.executable},
        )
        if installed in {"broken", "unknown"}:
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("", result.stdout)
            return None
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.splitlines()

    def test_installer_preserves_old_accounting_until_cutover_and_rejects_unknown_modes(self):
        self.assertEqual(["--primary-only", "--legacy-traffic"], self.installer_options("legacy"))
        self.assertEqual(["--primary-only"], self.installer_options("cumulative"))
        self.installer_options("broken")
        self.installer_options("unknown")

    def test_aborted_legacy_upgrade_then_successful_cutover_does_not_double_count(self):
        options = self.installer_options("legacy")
        self.assertIn("--legacy-traffic", options)
        legacy = panel.HysteriaStatsClient(self.clients[0].base_url, "synthetic")
        panel.UsageManager(self.db, legacy).collect_once()
        self.assertEqual(300, self.total())
        # The preflight aborts: the installed old collector resumes the same core.
        panel.UsageManager(self.db, legacy).collect_once()
        self.assertEqual(300, self.total())
        # A subsequent successful upgrade stops that core and starts a new epoch.
        self.epochs[0] = "d" * 32
        self.traffic[0] = {"alice": {"tx": 20, "rx": 30}}
        self.manager(clients=[self.clients[0]]).collect_once()
        self.assertEqual(350, self.total())


if __name__ == "__main__":
    unittest.main()
