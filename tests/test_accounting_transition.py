"""Exercise the installer/agent accounting handoff, including aborted drains."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import node_agent
import test_cumulative_traffic as fixture


class AccountingTransitionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.CumulativeTrafficTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = node_agent.ProtocolState(self.root / "state" / "protocol.json")

    def maintenance_arguments(self, installed="legacy"):
        source = (Path(__file__).resolve().parents[1] / "install.sh").read_text()
        start = source.index("settle_existing_node_traffic() {")
        function = source[start:source.index("\n}\n", start) + 2]
        for name in ("installed", "download", "config"):
            (self.root / name).mkdir(exist_ok=True)
        probe = {
            "legacy": "raise SystemExit(2)\n",
            "cumulative": "print('cumulative-v1')\n",
            "broken": "raise SystemExit(1)\n",
            "unknown": "print('future-accounting-mode')\n",
        }[installed]
        (self.root / "installed" / "node_agent.py").write_text(probe)
        (self.root / "download" / "node_agent.py").write_text(
            "import json, sys\nprint(json.dumps(sys.argv[1:]))\n"
        )
        (self.root / "config" / "stats.env").write_text("HY2PANEL_STATS_SECRET=synthetic\n")
        script = function + r'''
stop_loaded_units() { :; }
require_node_agent_file() { [[ -f "$1" ]]; }
systemctl() {
  case "$*" in
    *hysteria2-panel-node-hysteria-main.service) printf 'active\n' ;;
    *hysteria2-panel-node-hysteria-udp443.service) printf 'inactive\n' ;;
    *) return 1 ;;
  esac
}
settle_existing_node_traffic
'''
        result = subprocess.run(
            ["bash", "-eu"], input=script, text=True, capture_output=True, check=False,
            env={**os.environ, "TMP_DIR": str(self.root / "download"),
                 "NODE_AGENT_OPT_DIR": str(self.root / "installed"),
                 "NODE_AGENT_CONFIG_DIR": str(self.root / "config"),
                 "NODE_AGENT_STATE_DIR": str(self.root), "PYTHON_BIN": sys.executable},
        )
        if installed in {"broken", "unknown"}:
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("", result.stdout)
            return None
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def cycle(self, arguments):
        options = node_agent._parser().parse_args(arguments)
        with mock.patch.dict(os.environ, {"HY2PANEL_STATS_SECRET": "x" * 32}), \
                mock.patch.object(node_agent, "NodeProtocolClient", return_value=mock.Mock()), \
                mock.patch.object(node_agent, "LocalStatsClient", return_value=self.fixture.client):
            cycle = node_agent._make_control_cycle(options)
        cycle.clock = lambda: 100
        cycle._next_domain_collection_at = 1000
        if cycle.traffic_collector is not None:
            cycle.traffic_collector.epoch_reader = lambda _: self.fixture.epoch
        return cycle

    def fail_drain(self, cycle):
        with mock.patch.object(self.fixture.client, "online", return_value={"alice": 1}), \
                mock.patch.object(self.fixture.client, "kick"):
            with self.assertRaisesRegex(node_agent.ProtocolError, "did not drain"):
                cycle.quiesce_traffic(attempts=3, sleeper=lambda _: None)

    def test_aborted_legacy_upgrade_can_resume_old_collector_without_double_accounting(self):
        arguments = self.maintenance_arguments("legacy")
        helper = self.cycle(arguments)
        self.fail_drain(helper)
        self.assertEqual(300, self.fixture.total())
        resumed = node_agent.NodeControlCycle(
            mock.Mock(), self.fixture.client, self.fixture.spool, self.state, clock=lambda: 101,
        )
        resumed._next_domain_collection_at = 1000
        self.assertEqual(0, resumed._collect_to_spool())
        self.assertEqual(300, self.fixture.total())
        self.assertIsNone(helper.traffic_collector)

    def test_aborted_cumulative_upgrade_preserves_cursor_for_resumed_agent(self):
        arguments = self.maintenance_arguments("cumulative")
        self.fail_drain(self.cycle(arguments))
        self.assertEqual(300, self.fixture.total())
        resumed = self.cycle(["control-once"] + arguments[1:])
        self.assertEqual(0, resumed._collect_to_spool())
        self.assertEqual(300, self.fixture.total())
        self.assertNotIn("/traffic?clear=1", self.fixture.paths)

    def test_completed_legacy_drain_then_new_core_uses_cumulative_accounting(self):
        arguments = self.maintenance_arguments("legacy")
        helper = self.cycle(arguments)
        with mock.patch.object(self.fixture.client, "online", return_value={}):
            helper.quiesce_traffic(attempts=4, sleeper=lambda _: None)
        self.assertEqual(300, self.fixture.total())
        self.fixture.traffic = {"alice": {"tx": 20, "rx": 30}}
        self.fixture.epoch = "b" * 32  # Managed cutover starts a new core.
        arguments = [argument for argument in arguments[1:] if argument != "--legacy-traffic"]
        upgraded = self.cycle(["control-once"] + arguments)
        self.assertEqual(50, upgraded._collect_to_spool())
        self.assertEqual(0, upgraded._collect_to_spool())
        self.assertEqual(350, self.fixture.total())
        self.assertEqual({"tx": 20, "rx": 30}, self.fixture.traffic["alice"])

    def test_unknown_or_failed_mode_probe_never_runs_a_destructive_helper(self):
        for installed in ("broken", "unknown"):
            with self.subTest(installed=installed):
                self.maintenance_arguments(installed)

    def test_accounting_probe_needs_no_secrets_and_legacy_flag_is_maintenance_only(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(0, node_agent.main(["accounting-mode"]))
        self.assertEqual("cumulative-v1\n", output.getvalue())
        arguments = self.maintenance_arguments("legacy")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            node_agent._parser().parse_args(["control-loop"] + arguments[1:])
        self.assertEqual(2, raised.exception.code)
