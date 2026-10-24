"""Upgrade fallback must be bounded, scoped and independently recoverable."""
import unittest
from unittest import mock

import hysteria2_panel as panel
from hy2panel.operations import UpgradeIngressDrain


class UpgradeDrainTests(unittest.TestCase):
    def test_kernel_expiry_and_independent_cleanup_precede_packet_filter(self):
        runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout=""))
        with mock.patch("hy2panel.operations.shutil.which", return_value="/usr/sbin/nft"):
            with UpgradeIngressDrain([31999, 443], runner=runner) as guard:
                calls = runner.call_args_list
                self.assertEqual("systemd-run", calls[0].args[0][0])
                self.assertIn("--on-active=150s", calls[0].args[0])
                self.assertEqual(["/usr/sbin/nft", "-f", "-"], calls[1].args[0])
                rules = calls[1].kwargs["input"]
                self.assertIn("timeout 120s", rules)
                self.assertIn("443, 31999", rules)
                self.assertIn("udp dport @ports", rules)
                self.assertNotIn("flush", rules)
            self.assertEqual(["/usr/sbin/nft", "delete", "table", "inet", guard.table],
                             runner.call_args_list[2].args[0])

    def test_timer_failure_never_installs_packet_filter(self):
        runner = mock.Mock(return_value=mock.Mock(returncode=1))
        with mock.patch("hy2panel.operations.shutil.which", return_value="/usr/sbin/nft"):
            with self.assertRaisesRegex(RuntimeError, "arm"):
                with UpgradeIngressDrain([443], runner=runner):
                    self.fail("must not enter")
        self.assertEqual(1, runner.call_count)

    def test_cleanup_error_preserves_timer_and_fails_upgrade(self):
        runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout=""))
        with mock.patch("hy2panel.operations.shutil.which", return_value="/usr/sbin/nft"):
            guard = UpgradeIngressDrain([443], runner=runner)
            with self.assertRaisesRegex(RuntimeError, "cleanup pending"):
                with guard:
                    runner.side_effect = [mock.Mock(returncode=1),
                                          mock.Mock(returncode=0, stdout="table inet " + guard.table)]
        self.assertFalse(any(c.args[0][0] == "systemctl" for c in runner.call_args_list))

    def test_only_a_drain_timeout_triggers_isolation_and_then_rechecks_sessions(self):
        settings = mock.Mock(hysteria_port=31999)
        for failure in (panel.SessionDrainTimeout("busy"), OSError("stats failed")):
            with self.subTest(failure=type(failure).__name__), \
                    mock.patch.object(panel.os, "geteuid", return_value=0, create=True), \
                    mock.patch.object(panel, "_systemd_unit_state", return_value=("loaded", "inactive")), \
                    mock.patch.object(panel, "quiesce_stats_client", side_effect=[failure, None]) as drain, \
                    mock.patch.object(panel, "UpgradeIngressDrain") as guard:
                if isinstance(failure, OSError):
                    with self.assertRaises(OSError):
                        panel.quiesce_upgrade_stats(settings, mock.Mock())
                    guard.assert_not_called()
                else:
                    panel.quiesce_upgrade_stats(settings, mock.Mock())
                    guard.assert_called_once_with([31999, 443])
                    self.assertEqual(60, drain.call_args.kwargs["attempts"])

    def test_running_authentication_refuses_fallback(self):
        with mock.patch.object(panel.os, "geteuid", return_value=0, create=True), \
                mock.patch.object(panel, "_systemd_unit_state", return_value=("loaded", "active")), \
                mock.patch.object(panel, "UpgradeIngressDrain") as guard:
            with self.assertRaisesRegex(RuntimeError, "stop panel"):
                panel.quiesce_upgrade_stats(mock.Mock(), mock.Mock())
            guard.assert_not_called()
