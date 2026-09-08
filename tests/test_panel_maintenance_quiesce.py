"""Maintenance must preserve live counters when sessions cannot drain."""

import functools
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import hysteria2_panel as panel
from tests.test_panel import create_test_certificate


ROOT = Path(__file__).resolve().parents[1]


def installer_function(name):
    source = (ROOT / "install.sh").read_text()
    start = source.index(name + "() {")
    return source[start:source.index("\n}\n", start) + 3]


class PanelMaintenanceQuiesceTests(unittest.TestCase):
    def test_failed_drain_does_not_initialize_database_or_clear_live_counters(self):
        stats = mock.Mock()
        stats.online.return_value = {"alice": 2}
        delays = []
        quiesce = functools.partial(
            panel.quiesce_stats_client, attempts=3, sleeper=delays.append
        )
        with mock.patch.object(panel, "make_stats_client", return_value=stats), \
                mock.patch.object(panel, "quiesce_stats_client", quiesce), \
                mock.patch.object(panel, "Database") as database, \
                mock.patch.object(panel, "UsageManager") as usage:
            with self.assertRaisesRegex(RuntimeError, "did not drain"):
                panel.sync_traffic(mock.Mock(), quiesce=True)
        self.assertEqual([10.0, 1, 1, 1], delays)
        database.assert_not_called()
        usage.assert_not_called()
        stats.traffic.assert_not_called()

    def test_late_auth_is_observed_after_the_upstream_auth_budget(self):
        stats = mock.Mock()
        events = []
        stats.online.side_effect = lambda: events.append("online") or next(snapshots)
        snapshots = iter([{"late-auth": 1}, {}, {}, {}])
        stats.kick_many.side_effect = lambda users: events.append(("kick", users))
        panel.quiesce_stats_client(
            stats, attempts=4, sleeper=lambda delay: events.append(("sleep", delay))
        )
        self.assertEqual(("sleep", 10.0), events[0])
        self.assertEqual(("kick", ["late-auth"]), events[2])
        self.assertEqual(4, stats.online.call_count)

    def test_restore_failed_drain_preserves_identity_and_resumes_via_existing_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = panel.Database(root / "panel.db", b"r" * 32)
            database.initialize()
            user = database.create_proxy_user("original")
            database.path.chmod(0o600)
            cert, key = create_test_certificate(root)
            cert.chmod(0o640)
            key.chmod(0o640)
            lock = root / "maintenance.lock"
            lock.touch(mode=0o600)
            marker = root / "restore-active"
            env = root / "panel.env"
            manager = panel.BackupManager(
                database, b"r" * 32, cert, key, "vpn.example.test", 19999,
                work_dir=root / "backup-restore", maintenance_lock_path=lock,
                maintenance_lock_owner=os.geteuid(), maintenance_lock_mode=0o600,
                restore_marker_path=marker,
            )
            env.write_text("HY2PANEL_HMAC_KEY={}\nHY2PANEL_CERT_PIN={}\n".format(
                (b"r" * 32).hex(), manager._certificate_pin(cert.read_bytes())
            ))
            env.chmod(0o640)
            archive = manager.create_archive().read_bytes()
            manager.stage_archive(io.BytesIO(archive), len(archive))
            identity = [path.read_bytes() for path in (cert, key, env)]
            settings = mock.Mock(
                database_path=database.path, hmac_key=b"r" * 32,
                tls_cert=cert, tls_key=key, public_host="vpn.example.test",
                hysteria_port=19999, node_name="test-node", local_origin_id="local:" + "a" * 32,
                panel_scheme="http", panel_port=19998, auth_port=19996,
                stats_url="http://127.0.0.1:19997", stats_443_url="http://127.0.0.1:19995",
                stats_secret="fixture-secret",
            )
            calls = []
            panel_active = [True]

            def runner(command, **_kwargs):
                calls.append(command)
                if command[1] == "kill":
                    panel_active[0] = False
                state = "active"
                if command[-1] == "hysteria2-panel.service" and not panel_active[0]:
                    state = "inactive"
                return mock.Mock(returncode=0, stdout="LoadState=loaded\nActiveState={}\n".format(state))

            stats = mock.Mock()
            stats.online.return_value = {"original": 2}
            quiesce = functools.partial(panel.quiesce_stats_client, attempts=3, sleeper=lambda _: None)
            with mock.patch.object(panel, "RESTORE_ENV_FILE", env), \
                    mock.patch.object(panel, "RESTORE_BACKUP_ROOT", root / "backups"), \
                    mock.patch.object(panel, "make_restore_stats_client", return_value=stats):
                with self.assertRaisesRegex(RuntimeError, "did not drain"):
                    panel.restore_pending(settings, lock_path=lock, marker_path=marker,
                                          runner=runner, quiesce=quiesce)
            record = panel._read_restore_transaction(marker, expected_uid=os.geteuid(), strict_paths=False)
            self.assertEqual(("services-pending", "rolled-back"), (record["phase"], record["outcome"]))
            self.assertFalse(any(command[1] == "stop" for command in calls))
            self.assertEqual(identity, [path.read_bytes() for path in (cert, key, env)])
            self.assertEqual("original", database.authenticate_token(user["token"]))
            # ExecStopPost starts restore-resume; its Wants starts the old panel.
            panel_active[0] = True
            panel.resume_after_restore(
                settings, lock_path=lock, marker_path=marker, runner=runner,
                expected_uid=os.geteuid(), strict_paths=False, egress_manager=mock.Mock(),
                health_probe=lambda *_: None, stats_probe=lambda *_: None,
                tcp_probe=lambda *_: None, attempts=2, sleeper=lambda _: None,
            )
            self.assertFalse(marker.exists())
            self.assertEqual("original", database.authenticate_token(user["token"]))

    def test_upgrade_preflight_error_and_signal_restore_only_original_services(self):
        functions = "\n".join(installer_function(name) for name in (
            "begin_upgrade_preflight", "restore_upgrade_preflight", "finalize_install",
        ))
        for interruption in ("exit 23", "kill -TERM $$"):
            with self.subTest(interruption=interruption), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "panel.db").write_text("original database")
                (root / "pending-traffic.json").write_text("original journal")
                script = """
set -euo pipefail
INSTALL_FINALIZING=0
INSTALL_COMMITTED=0
ROLLBACK_REQUIRED=0
UPGRADE_PREFLIGHT_ACTIVE=0
UPGRADE_PREFLIGHT_SERVICES=()
""" + functions.replace("/var/lib/hysteria2-panel", directory) + r'''
systemctl() {
  if [[ "$1" == show ]]; then
    case "${@: -1}" in
      hysteria2-panel.service|hysteria2-panel-node-dns-admission.timer) printf 'active\n' ;;
      hysteria2-panel-offsite-backup.timer) printf 'inactive\n' ;;
      *) return 91 ;;
    esac
    return
  fi
  printf 'systemctl %s\n' "$*"
}
chown() { printf 'chown %s\n' "$*"; }
chmod() { printf 'chmod %s\n' "$*"; }
release_legacy_restore_guard() { printf 'release-guard\n'; }
rollback_existing_install() { printf 'UNEXPECTED-full-rollback\n'; }
cleanup() { :; }
trap finalize_install EXIT
trap 'exit 143' TERM
begin_upgrade_preflight
''' + interruption + "\n"
                result = subprocess.run(["bash"], input=script, text=True, capture_output=True)
                self.assertEqual(143 if "TERM" in interruption else 23, result.returncode, result.stderr)
                self.assertNotIn("UNEXPECTED", result.stdout)
                self.assertNotIn("server.service", result.stdout)
                self.assertNotIn("offsite-backup.timer", result.stdout)
                self.assertIn("systemctl start hysteria2-panel.service", result.stdout)
                self.assertIn("systemctl start hysteria2-panel-node-dns-admission.timer", result.stdout)
                self.assertLess(result.stdout.index("chown"), result.stdout.index("systemctl start"))
                self.assertEqual("original database", (root / "panel.db").read_text())
                self.assertEqual("original journal", (root / "pending-traffic.json").read_text())

    def test_rollback_refuses_nonquiescent_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "etc").mkdir()
            (root / "etc" / "panel.env").write_text("")
            helper = root / "candidate.py"
            helper.write_text("import sys\nprint(' '.join(sys.argv[1:]))\nraise SystemExit(9)\n")
            script = installer_function("sync_traffic_before_upgrade_rollback") + "\n" + \
                "BACKUP_DIR={}\nPYTHON_BIN={}\nTRAFFIC_SYNC_SCRIPT={}\n".format(
                    shlex.quote(directory), shlex.quote(sys.executable), shlex.quote(str(helper))
                ) + """
select_traffic_sync_options() { TRAFFIC_SYNC_OPTIONS=(--primary-only); }
select_upgrade_traffic_sync_script() { return 0; }
sync_traffic_before_upgrade_rollback
"""
            result = subprocess.run(["bash"], input=script, text=True, capture_output=True)
            self.assertEqual(1, result.returncode)
            self.assertEqual(["sync-traffic --quiesce --primary-only"], result.stdout.splitlines())

    def test_reboot_recovery_uses_the_persisted_candidate_and_never_the_old_panel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "opt").mkdir()
            (root / "opt" / "hysteria2_panel.py").write_text("raise SystemExit('old unsafe helper')\n")
            script = "\n".join(installer_function(name) for name in (
                "stage_upgrade_maintenance", "select_upgrade_traffic_sync_script",
            )) + "\nTMP_DIR={}\nBACKUP_DIR={}\n".format(
                shlex.quote(str(ROOT)), shlex.quote(directory)
            ) + """
stage_upgrade_maintenance || exit 90
TMP_DIR=''
stat() { printf '0:1\n'; }
select_upgrade_traffic_sync_script || exit 91
""" + '{} -B "$TRAFFIC_SYNC_SCRIPT" --help >/dev/null || exit 92\n'.format(
                shlex.quote(sys.executable)
            ) + """
rm "$TRAFFIC_SYNC_SCRIPT"
if select_upgrade_traffic_sync_script; then exit 93; fi
"""
            result = subprocess.run(["bash"], input=script, text=True, capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse(list((root / "maintenance").rglob("__pycache__")))
            self.assertEqual((ROOT / "hy2panel/distributed.py").read_bytes(),
                             (root / "maintenance/hy2panel/distributed.py").read_bytes())

    def test_verified_preflight_precedes_transaction_and_program_replacement(self):
        source = (ROOT / "install.sh").read_text()
        main_start = source.rindex('timestamp="$(date -u +%Y%m%dT%H%M%SZ)"')
        main = source[main_start:]
        begin = main.index("\n    begin_upgrade_preflight")
        quiesce = main.index('sync-traffic --quiesce "${TRAFFIC_SYNC_OPTIONS[@]}"')
        arm = main.index("\n  arm_upgrade_transaction")
        self.assertLess(begin, quiesce)
        self.assertLess(quiesce, main.index("ROLLBACK_REQUIRED=1"))
        self.assertLess(main.index("ROLLBACK_REQUIRED=1"), arm)
        self.assertLess(main.index("stage_upgrade_maintenance"), main.index("write_backup_manifest"))
        self.assertLess(arm, main.index("install -d -o root -g root -m 0755 /opt/hysteria2-panel"))
        self.assertNotIn("systemctl start", main[begin:arm])
        self.assertLess(source.index('"${PANEL_SHA256}" "${TMP_DIR}/hysteria2_panel.py"'),
                        main_start)


if __name__ == "__main__":
    unittest.main()
