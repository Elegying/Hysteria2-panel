"""Accounting and maintenance boundaries reproduced against the real root paths."""

import contextlib
import functools
import json
import os
import sqlite3
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import hysteria2_panel as panel
import node_agent
from hy2panel.mobile_api import match_mobile_route
from tests import test_monthly_user_traffic
from tests import test_data_plane_bootstrap
from tests import test_panel
from tests import test_distributed_control


class AuditAccountingRegressions(unittest.TestCase):
    def test_first_signed_new_month_batch_is_not_erased_by_the_local_collector(self):
        f = test_distributed_control.DistributedControlCase("runTest")
        f.setUp()
        self.addCleanup(f.tearDown)
        user = f.db.create_proxy_user("monthly-user")
        with f.db._connect() as connection:
            connection.execute("UPDATE user_traffic_reset_state SET period='2033-04'")
            connection.execute(
                "UPDATE proxy_users SET tx_bytes=300 WHERE id=?", (user["id"],)
            )
        payload = f.common(f.nodes[0], 93)
        payload.update(
            batchId="e" * 32,
            observedAt=f.now[0],
            traffic={"monthly-user": {"tx": 100, "rx": 0}},
        )
        self.assertTrue(
            f.service.apply_traffic_batch(payload, "203.0.113.1")["committed"]
        )
        manager = panel.UsageManager(
            f.db, test_panel.PolicyStatsClient(), wall_clock=lambda: f.now[0]
        )
        manager.collect_once()
        self.assertEqual(100, f.db.get_proxy_user(user["id"])["tx_bytes"])

    def test_accepted_reboot_keeps_auth_closed_and_failed_queue_reopens_it(self):
        f = self.monthly_fixture()
        manager = panel.UsageManager(
            f.db, test_panel.PolicyStatsClient(), quiesce=lambda _: None
        )
        manager.run_after_collect(lambda: True, quiesce=True, resume_auth=False)
        self.assertTrue(manager._quiescing.is_set())
        self.assertFalse(manager.authorize("monthly-user"))
        manager._quiescing.clear()
        with self.assertRaises(RuntimeError):
            manager.run_after_collect(
                mock.Mock(side_effect=RuntimeError("queue failed")),
                quiesce=True,
                resume_auth=False,
            )
        self.assertFalse(manager._quiescing.is_set())

    def test_egress_gate_removes_its_marker_after_failure_and_rejects_symlinks(self):
        f = self.monthly_fixture()
        root = Path(f.tmp.name)
        marker = root / "egress-active"
        with self.assertRaisesRegex(RuntimeError, "operation failed"):
            with panel.egress_auth_gate(marker):
                self.assertTrue(marker.exists())
                raise RuntimeError("operation failed")
        self.assertFalse(marker.exists())
        target = root / "untouched"
        target.write_text("retain")
        marker.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "unsafe"):
            with panel.egress_auth_gate(marker):
                self.fail("unsafe gate was accepted")
        self.assertEqual("retain", target.read_text())

    def monthly_fixture(self):
        fixture = test_monthly_user_traffic.MonthlyTrafficTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_first_new_month_collection_keeps_quota_and_history(self):
        f = self.monthly_fixture()
        stats = test_panel.PolicyStatsClient(
            traffic={"monthly-user": {"tx": 7, "rx": 11}}
        )
        manager = panel.UsageManager(f.db, stats, wall_clock=lambda: f.boundary)
        manager.collect_once()
        self.assertEqual(18, f.traffic())
        self.assertEqual(
            18, f.db.user_traffic_history(f.user["id"], now=f.boundary)["totalBytes"]
        )
        manager.collect_once()
        self.assertEqual(18, f.traffic())

    def test_month_reset_and_sample_roll_back_together_and_recover_from_journal(self):
        f = self.monthly_fixture()
        stats = test_panel.PolicyStatsClient(
            traffic={"monthly-user": {"tx": 7, "rx": 11}}
        )
        manager = panel.UsageManager(f.db, stats, wall_clock=lambda: f.boundary)
        with f.db._connect() as c:
            c.execute(
                "CREATE TRIGGER fail_batch BEFORE INSERT ON applied_traffic_batches "
                "BEGIN SELECT RAISE(ABORT, 'write unavailable'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            manager.collect_once()
        self.assertEqual(300, f.traffic())
        with f.db._connect() as c:
            self.assertEqual(
                "2026-09",
                c.execute("SELECT period FROM user_traffic_reset_state").fetchone()[0],
            )
            c.execute("DROP TRIGGER fail_batch")
        recovered = panel.UsageManager(f.db, stats, wall_clock=lambda: f.boundary + 1)
        recovered.collect_once()
        self.assertEqual(18, f.traffic())
        self.assertFalse(recovered.pending_traffic_path.exists())

    def test_old_journal_is_not_charged_to_new_month(self):
        f = self.monthly_fixture()
        stats = test_panel.PolicyStatsClient()
        manager = panel.UsageManager(f.db, stats, wall_clock=lambda: f.boundary)
        with manager.lock:
            manager._persist_pending_traffic_locked(
                {"monthly-user": {"tx": 7, "rx": 11}},
                observed_at=int(f.boundary) - 1,
            )
        recovered = panel.UsageManager(f.db, stats, wall_clock=lambda: f.boundary)
        recovered.collect_once()
        self.assertEqual(0, f.traffic())
        with f.db._connect() as c:
            self.assertEqual(
                318,
                c.execute(
                    "SELECT SUM(tx_bytes+rx_bytes) FROM origin_traffic_daily"
                ).fetchone()[0],
            )

    def test_unicode_accounts_keep_distinct_domain_usage_and_ascii_case_still_matches(
        self,
    ):
        f = self.monthly_fixture()
        upper, lower = f.db.create_proxy_user("Ä"), f.db.create_proxy_user("ä")
        with mock.patch.object(panel.time, "time", return_value=f.boundary):
            f.db.apply_traffic_batch(
                "f" * 32,
                {},
                observed_at=int(f.boundary),
                domain_usage=[
                    {"user": "Ä", "domain": "upper.example", "tx": 10, "rx": 20},
                    {"user": "ä", "domain": "lower.example", "tx": 1, "rx": 2},
                    {
                        "user": "MONTHLY-USER",
                        "domain": "ascii.example",
                        "tx": 3,
                        "rx": 4,
                    },
                ],
            )
        for user, domain, used in (
            (upper, "upper.example", 30),
            (lower, "lower.example", 3),
            (f.user, "ascii.example", 7),
        ):
            entries = f.db.domain_usage_top(user["id"], now=f.boundary)["items"]
            self.assertEqual(
                [(domain, used)], [(r["domain"], r["usedBytes"]) for r in entries]
            )

    def test_destructive_action_drains_late_traffic_and_denies_new_auth(self):
        f = self.monthly_fixture()
        stats = test_panel.PolicyStatsClient(
            traffic={"monthly-user": {"tx": 100, "rx": 0}}
        )
        stats.online = mock.Mock(side_effect=[{"monthly-user": 1}, {}, {}, {}])
        manager = panel.UsageManager(f.db, stats, wall_clock=lambda: f.boundary)
        events = []

        def kick(names):
            events.append(("kick", names))
            stats.traffic_values["monthly-user"]["tx"] += 50

        def sleep(_delay):
            self.assertFalse(manager.authorize("monthly-user"))

        stats.kick_many = kick
        drain = functools.partial(panel.quiesce_stats_client, sleeper=sleep)
        with mock.patch.object(panel, "quiesce_stats_client", drain):
            manager.run_after_collect(
                lambda: events.append(("restart", f.traffic())), quiesce=True
            )
        self.assertEqual([("kick", ["monthly-user"]), ("restart", 150)], events)
        self.assertFalse(manager._quiescing.is_set())

    def test_failed_drain_retains_counters_and_does_not_run_action(self):
        f = self.monthly_fixture()
        stats = test_panel.PolicyStatsClient(
            traffic={"monthly-user": {"tx": 50, "rx": 0}}, online={"monthly-user": 1}
        )
        manager = panel.UsageManager(f.db, stats)
        action = mock.Mock()
        drain = functools.partial(
            panel.quiesce_stats_client, attempts=3, sleeper=lambda _: None
        )
        with mock.patch.object(panel, "quiesce_stats_client", drain):
            with self.assertRaisesRegex(RuntimeError, "did not drain"):
                manager.run_after_collect(action, quiesce=True)
        action.assert_not_called()
        self.assertEqual(50, stats.traffic_values["monthly-user"]["tx"])
        self.assertFalse(manager._quiescing.is_set())

    def test_live_collection_respects_root_maintenance_lock(self):
        f = self.monthly_fixture()
        stats = mock.Mock()
        manager = panel.UsageManager(
            f.db, stats, maintenance_lock_path=Path("/fixture/lock")
        )
        with mock.patch.object(
            panel, "maintenance_upload_slot", side_effect=RuntimeError("busy")
        ):
            with self.assertRaisesRegex(RuntimeError, "busy"):
                manager.collect_once()
        stats.collect_and_clear.assert_not_called()

    def test_real_file_lock_excludes_live_collection_and_releases_after_maintenance(
        self,
    ):
        f = self.monthly_fixture()
        lock = Path(f.tmp.name) / "maintenance.lock"
        lock.touch(mode=0o640)
        lock.chmod(0o640)
        stats = test_panel.PolicyStatsClient()
        manager = panel.UsageManager(f.db, stats, maintenance_lock_path=lock)
        real_slot = panel.maintenance_upload_slot

        # Temp files belong to the test user; production requires root ownership.
        def slot(path, **options):
            return real_slot(path, expected_uid=os.getuid(), **options)

        with mock.patch.object(panel, "maintenance_upload_slot", slot):
            with panel.exclusive_maintenance_lock(lock):
                with self.assertRaises(panel.MaintenanceBusyError):
                    manager.collect_once()
            manager.collect_once()

    def test_install_transaction_does_not_block_live_readiness_collection(self):
        f = self.monthly_fixture()
        root = Path(f.tmp.name)
        transaction, traffic_lock = root / "lock", root / "traffic-lock"
        traffic_lock.touch(mode=0o640)
        traffic_lock.chmod(0o640)
        stats = test_panel.PolicyStatsClient()
        manager = panel.UsageManager(f.db, stats, maintenance_lock_path=traffic_lock)
        slot = panel.maintenance_upload_slot
        with mock.patch.object(
            panel, "maintenance_upload_slot",
            lambda path, **options: slot(path, expected_uid=os.getuid(), **options),
        ):
            with panel.exclusive_maintenance_lock(transaction):
                manager.collect_once()
                self.assertTrue(manager.snapshot()["available"])
            with panel.exclusive_maintenance_lock(traffic_lock):
                with self.assertRaises(panel.MaintenanceBusyError):
                    manager.collect_once()

    def test_egress_settlement_selects_only_active_endpoints(self):
        for states, expected in (
            (["active", "inactive"], (True, False)),
            (["inactive", "active"], (False, True)),
            (["active", "active"], (False, False)),
            (["inactive", "inactive"], None),
        ):
            with (
                self.subTest(states=states),
                mock.patch.object(
                    panel,
                    "_systemd_unit_state",
                    side_effect=[("loaded", state) for state in states],
                ),
                mock.patch.object(panel, "sync_traffic") as sync,
            ):
                settings = mock.Mock()
                panel.settle_egress_traffic(settings)
                if expected is None:
                    sync.assert_not_called()
                else:
                    sync.assert_called_once_with(
                        settings,
                        primary_only=expected[0],
                        secondary_only=expected[1],
                        quiesce=True,
                    )

    def test_direct_egress_cli_gates_auth_and_settles_before_policy_apply(self):
        events = []

        @contextlib.contextmanager
        def gate():
            events.append("deny-auth")
            yield
            events.append("resume-auth")

        with (
            mock.patch.object(panel.os, "geteuid", return_value=0),
            mock.patch.object(panel.Settings, "from_mapping"),
            mock.patch.object(
                panel,
                "exclusive_maintenance_lock",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch.object(panel, "egress_auth_gate", gate),
            mock.patch.object(
                panel,
                "settle_egress_traffic",
                side_effect=lambda _: events.append("settle"),
            ),
            mock.patch.object(panel, "EgressPolicyManager") as policy,
            mock.patch("sys.stdout"),
        ):
            policy.return_value.apply.side_effect = lambda *_: events.append("apply")
            self.assertEqual(0, panel.main(["apply-egress-policy", "full"]))
        self.assertEqual(["deny-auth", "settle", "apply", "resume-auth"], events)


class AuditPortAndRouteRegressions(unittest.TestCase):
    def test_real_listener_helper_is_used_by_custom_port_attestation(self):
        f = test_data_plane_bootstrap.DataPlaneAttestationTests("runTest")
        f.setUp()
        self.addCleanup(f.tearDown)
        original_run = subprocess.run

        def run(command, **options):
            if command[0] == "/usr/bin/ss":
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"UNCONN 0 0 0.0.0.0:24443 0.0.0.0:*\n"
                )
            return original_run(command, **options)

        with mock.patch.object(node_agent.subprocess, "run", side_effect=run) as runner:
            result = node_agent.collect_data_plane_attestation(
                f.metadata_path,
                f.cert_path,
                f.key_path,
                "S" * 48,
                service_checker=lambda _: True,
                stats_checker=lambda *_: True,
            )
        self.assertTrue(result["udp19999Listening"])
        self.assertTrue(result["tcp19999Listening"])
        self.assertEqual(
            [":24443", ":443", ":24443", ":443"],
            [
                c.args[0][-1]
                for c in runner.call_args_list
                if c.args[0][0] == "/usr/bin/ss"
            ],
        )
        with mock.patch.object(node_agent.subprocess, "run") as runner:
            for port in (True, 0, -1, 65536, "24443"):
                self.assertFalse(node_agent._socket_is_listening("udp", port))
            runner.assert_not_called()

    def test_max_sqlite_user_id_history_works_over_web_and_mobile_http(self):
        f = test_panel.PanelHttpTests("runTest")
        f.setUp()
        self.addCleanup(f.tearDown)
        identifier = 2**63 - 1
        user = f.db.create_proxy_user("large-id")
        with f.db._connect() as c:
            c.execute(
                "UPDATE proxy_users SET id=? WHERE id=?", (identifier, user["id"])
            )
        route = "/api/v1/mobile/users/{}/traffic-history".format(identifier)
        self.assertEqual(
            ("user-traffic-history", (str(identifier),)),
            match_mobile_route("GET", route),
        )
        token = f.db.create_mobile_session(f.admin_id, "audit-history", "Fixture")[
            "accessToken"
        ]
        status, payload = f.mobile_json_request("GET", route, access_token=token)
        self.assertEqual(200, status)
        self.assertEqual(identifier, payload["data"]["userId"])
        headers, _ = f.authenticated_headers()
        with f.request(
            "/api/v1/users/{}/traffic-history".format(identifier), headers=headers
        ) as response:
            self.assertEqual(identifier, json.load(response)["userId"])
