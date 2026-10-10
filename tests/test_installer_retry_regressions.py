"""Execute real installer functions through absent rules and repeated ACK failures."""

import pathlib
import subprocess
import tempfile
import unittest


def run_reproductions():
    ROOT = pathlib.Path(__file__).resolve().parents[1]
    source = (ROOT / "install.sh").read_text()

    def function(name):
        start = source.index("\n" + name + "() {") + 1
        return source[start : source.index("\n}\n", start) + 3]

    results = {}
    for scope in ("runtime", "permanent"):
        script = (
            function("remove_managed_firewall_entry")
            + '\nfirewall-cmd() { return 1; }\nremove_managed_firewall_entry "'
            + scope
            + '|public|24443/udp"\n'
        )
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        results["absent_firewalld_" + scope] = {
            "query_exit": 1,
            "expected_remove_exit": 0,
            "actual_remove_exit": result.returncode,
        }
        assert result.returncode == 0
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        for name in ("opt", "config", "state", "backups", "work", "units"):
            (root / name).mkdir()
        backup = root / "backups/20261002T000000Z-phase4"
        backup.mkdir()
        (backup / "deployment-kind").write_text("fresh\n")
        (backup / "manifest.sha256").touch()
        for name in ("node_agent.py", "onboarding-install.sh"):
            (root / "opt" / name).touch()
        for name in ("node.key", "registration.json", "stats.env", "bootstrap.json"):
            (root / "config" / name).touch()
        (root / "state/state").mkdir()
        (root / "state/state/protocol.json").touch()
        (root / "state/uninstall-command.json").touch()
        for name in (
            "uninstall.service",
            "heartbeat.service",
            "heartbeat.timer",
            "onboarding.service",
            "onboarding.timer",
        ):
            (root / "units" / name).touch()
        (root / "work/node_agent.py").touch()
        runner = root / "runner"
        runner_probe = (
            '#!/usr/bin/env bash\n'
            'if [[ "$2" == accounting-mode ]]; then printf "cumulative-v1\\n"; exit 0; fi\n'
        )
        runner.write_text(
            runner_probe + 'for item in "$@"; do [[ "$item" != ack-command ]] || exit 1; done\nexit 0\n'
        )
        runner.chmod(0o755)
        preamble = """set -eu
    NODE_AGENT_OPT_DIR="$1/opt"
    NODE_AGENT_CONFIG_DIR="$1/config"
    NODE_AGENT_STATE_DIR="$1/state"
    NODE_DATA_PLANE_BACKUP_ROOT="$1/backups"
    NODE_AGENT_HEARTBEAT_SERVICE="$1/units/heartbeat.service"
    NODE_AGENT_HEARTBEAT_TIMER="$1/units/heartbeat.timer"
    NODE_ONBOARDING_SERVICE="$1/units/onboarding.service"
    NODE_ONBOARDING_TIMER="$1/units/onboarding.timer"
    NODE_ONBOARDING_INSTALLER="$1/opt/onboarding-install.sh"
    NODE_UNINSTALL_SERVICE="$1/units/uninstall.service"
    NODE_UNINSTALL_COMMAND="$1/state/uninstall-command.json"
    MANAGED_MARKER="$1/absent-marker"
    TMP_DIR="$1/work"
    PYTHON_BIN="$1/runner"
    require_node_agent_directory() { [[ -d "$1" ]]; }
    require_node_agent_file() { [[ -f "$1" ]] || fail "required file missing"; }
    select_python() { return 0; }
    prepare_node_maintenance_agent() { return 0; }
    initialize_data_plane_owned_paths() { DATA_PLANE_OWNED_FILES=("${NODE_AGENT_CONFIG_DIR}/stats.env" "${NODE_AGENT_CONFIG_DIR}/bootstrap.json"); DATA_PLANE_OWNED_UNITS=(); }
    stat() { printf '0:0:700\\n'; }
    sha256sum() { return 0; }
    sync() { return 0; }
    sysctl() { return 0; }
    systemctl() { if [[ "$1" == show ]]; then printf 'inactive\\n'; fi; return 0; }
    stop_loaded_units() { return 0; }
    rollback_data_plane_firewall() { return 0; }
    restore_data_plane_network_snapshot() { return 0; }
    fail() { printf '%s\\n' "$*" >&2; exit 1; }
    """
        body = (
            preamble
            + "\n"
            + "\n".join(
                function(n)
                for n in (
                    "settle_existing_node_traffic",
                    "quiesce_existing_data_plane",
                    "stop_existing_data_plane",
                    "uninstall_node",
                )
            )
            + "\nuninstall_node\n"
        )
        outputs = []
        for attempt in (1, 2):
            result = subprocess.run(
                ["bash", "-c", body, "isolated-installer", str(root)],
                capture_output=True,
                text=True,
            )
            outputs.append(
                {
                    "attempt": attempt,
                    "exit": result.returncode,
                    "stderr": result.stderr.strip(),
                    "stats_env_present": (root / "config/stats.env").exists(),
                    "command_present": (root / "state/uninstall-command.json").exists(),
                }
            )
        assert all(
            "中央面板尚未确认" in row["stderr"] and row["stats_env_present"]
            for row in outputs
        )
        assert outputs[1]["command_present"]
        runner.write_text(runner_probe + "exit 0\n")
        confirmed = subprocess.run(
            ["bash", "-c", body, "isolated-installer", str(root)],
            capture_output=True,
            text=True,
        )
        assert confirmed.returncode == 0, confirmed.stderr
        assert not (root / "config").exists() and not (root / "state").exists()
        results["uninstall_ack_failure_retry"] = outputs
    return results


class InstallerRetryRegressions(unittest.TestCase):
    def test_absent_firewall_rules_and_failed_uninstall_ack_are_retryable(self):
        run_reproductions()
