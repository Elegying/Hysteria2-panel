"""Node maintenance races and durable accounting at real process boundaries."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import node_agent


ROOT = Path(__file__).resolve().parents[1]


def installer_function(name):
    source = (ROOT / "install.sh").read_text()
    start = source.index(name + "() {")
    return source[start:source.index("\n}\n", start) + 3]


class NodeTrafficMaintenanceTests(unittest.TestCase):
    def test_quiesce_preserves_both_endpoints_and_waits_through_late_traffic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spool = node_agent.DurableTrafficSpool(root / "spool")
            state = node_agent.ProtocolState(root / "state" / "protocol.json")
            state.next_sequence()
            state.set_traffic_ack(10)
            state.record_command_completed("a" * 32, 10)
            state_before = state.path.read_bytes()
            observed = []

            class Stats:
                def __init__(self, counters):
                    self.counters = iter(counters)
                    self.collections = 0

                def online(self):
                    return {"alice": 1} if self.collections < 3 else {}

                def kick(self, users):
                    observed.append(("kick", users))

                def collect_and_clear(self):
                    value = next(self.counters)
                    self.collections += 1
                    return {"alice": {"tx": value, "rx": value * 2}}

            stats = node_agent.CombinedLocalStatsClient(
                Stats([10, 0, 20, 0, 0, 0]), Stats([100, 0, 200, 0, 0, 0])
            )
            cycle = node_agent.NodeControlCycle(mock.Mock(), stats, spool, state)
            sleeps = []
            cycle.quiesce_traffic(sleeper=sleeps.append)
            self.assertEqual(6, len(sleeps))
            self.assertEqual(10.0, sleeps[0])
            self.assertEqual(6, len(observed))
            pending = node_agent.DurableTrafficSpool(root / "spool").pending()
            self.assertEqual(330, sum(row["traffic"]["alice"]["tx"] for row in pending))
            self.assertEqual(660, sum(row["traffic"]["alice"]["rx"] for row in pending))
            self.assertEqual(state_before, state.path.read_bytes())
            cycle.protocol_client.assert_not_called()

    def test_nonquiet_or_partial_endpoint_failure_never_allows_a_stop(self):
        for partial in (False, True):
            with self.subTest(partial=partial), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                spool = node_agent.DurableTrafficSpool(root / "spool")
                state = node_agent.ProtocolState(root / "state" / "protocol.json")
                primary = mock.Mock(spec=node_agent.LocalStatsClient)
                primary.dump_streams.return_value = []
                primary.online.return_value = {"alice": 1}
                primary.collect_and_clear.return_value = {"alice": {"tx": 17, "rx": 0}}
                secondary = mock.Mock(spec=node_agent.LocalStatsClient)
                secondary.dump_streams.return_value = []
                secondary.online.return_value = {}
                if partial:
                    secondary.collect_and_clear.side_effect = OSError("endpoint unavailable")
                else:
                    secondary.collect_and_clear.return_value = {}
                cycle = node_agent.NodeControlCycle(
                    mock.Mock(), node_agent.CombinedLocalStatsClient(primary, secondary),
                    spool, state,
                )
                stopped = []
                with self.assertRaises(node_agent.ProtocolError):
                    node_agent.execute_control_command(
                        {"commandId": "b" * 32, "kind": "STOP_DATA_PLANE", "payload": {}},
                        cycle.stats_client,
                        flush_traffic=cycle.flush_traffic,
                        quiesce_traffic=lambda: cycle.quiesce_traffic(attempts=3, sleeper=lambda _: None),
                        protocol_state=state, stop_data_plane=lambda: stopped.append(True),
                    )
                self.assertEqual([], stopped)
                self.assertFalse(state.data_plane_stopped())
                expected = 17 if partial else 51
                self.assertEqual(expected, sum(row["traffic"].get("alice", {}).get("tx", 0) for row in spool.pending()))

    def test_stop_commands_quiesce_and_ack_before_destroying_stats(self):
        for kind in ("STOP_DATA_PLANE", "UNINSTALL_NODE"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                spool = node_agent.DurableTrafficSpool(root / "spool")
                state = node_agent.ProtocolState(root / "state" / "protocol.json")
                stats = mock.Mock(spec=node_agent.LocalStatsClient)
                stats.dump_streams.return_value = []
                stats.online.side_effect = [{"alice": 1}, {}, {}, {}]
                stats.collect_and_clear.side_effect = [
                    {"alice": {"tx": 99, "rx": 3}}, {}, {}, {}, {},
                ]
                protocol = mock.Mock()
                protocol.send_traffic.side_effect = lambda batch: {"batchId": batch["batchId"], "committed": True}
                cycle = node_agent.NodeControlCycle(protocol, stats, spool, state)
                stopped = []

                def stop():
                    self.assertEqual([], spool.pending())
                    self.assertFalse(state.data_plane_stopped())
                    self.assertEqual(5, stats.collect_and_clear.call_count)
                    stopped.append(True)

                queued = []
                result = node_agent.execute_control_command(
                    {"commandId": "c" * 32, "kind": kind, "payload": {}}, stats,
                    flush_traffic=cycle.flush_traffic,
                    quiesce_traffic=lambda: cycle.quiesce_traffic(sleeper=lambda _: None),
                    protocol_state=state, stop_data_plane=stop, queue_uninstall=queued.append,
                )
                self.assertEqual([True], stopped)
                self.assertTrue(state.data_plane_stopped())
                self.assertEqual(["c" * 32] if kind == "UNINSTALL_NODE" else [], queued)
                self.assertEqual("deferred-ack" if kind == "UNINSTALL_NODE" else None, result)

    def test_idle_multiple_sessions_cannot_be_mistaken_for_drained_traffic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spool = node_agent.DurableTrafficSpool(root / "spool")
            state = node_agent.ProtocolState(root / "state" / "protocol.json")
            stats = mock.Mock(spec=node_agent.LocalStatsClient)
            stats.online.return_value = {"alice": 2}
            stats.dump_streams.return_value = []
            stats.collect_and_clear.return_value = {}
            protocol = mock.Mock()
            cycle = node_agent.NodeControlCycle(protocol, stats, spool, state)
            stop = mock.Mock()
            with self.assertRaisesRegex(node_agent.ProtocolError, "sessions did not drain"):
                node_agent.execute_control_command(
                    {"commandId": "e" * 32, "kind": "STOP_DATA_PLANE", "payload": {}},
                    stats, flush_traffic=cycle.flush_traffic,
                    quiesce_traffic=lambda: cycle.quiesce_traffic(attempts=3, sleeper=lambda _: None),
                    protocol_state=state, stop_data_plane=stop,
                )
            stop.assert_not_called()
            protocol.send_traffic.assert_not_called()
            self.assertFalse(state.data_plane_stopped())

    def test_failed_systemd_stop_keeps_the_next_control_cycle_collecting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spool = node_agent.DurableTrafficSpool(root / "spool")
            state = node_agent.ProtocolState(root / "state" / "protocol.json")
            stats = mock.Mock(spec=node_agent.LocalStatsClient)
            stats.online.return_value = {}
            stats.dump_streams.return_value = []
            stats.collect_and_clear.side_effect = [
                {"alice": {"tx": 7, "rx": 0}}, {}, {}, {}, {},
                {"alice": {"tx": 9, "rx": 0}},
            ]
            totals = []

            class Protocol:
                def send_traffic(self, batch):
                    totals.append(batch["traffic"].get("alice", {}).get("tx", 0))
                    return {"batchId": batch["batchId"], "committed": True}

                def send_online(self, sequence, *_args):
                    return {"sequence": sequence}

                def poll_commands(self):
                    return []

            cycle = node_agent.NodeControlCycle(Protocol(), stats, spool, state)
            with self.assertRaises(node_agent.ProtocolError):
                node_agent.execute_control_command(
                    {"commandId": "f" * 32, "kind": "STOP_DATA_PLANE", "payload": {}},
                    stats, flush_traffic=cycle.flush_traffic,
                    quiesce_traffic=lambda: cycle.quiesce_traffic(sleeper=lambda _: None),
                    protocol_state=state,
                    stop_data_plane=mock.Mock(side_effect=node_agent.ProtocolError("systemd stop failed")),
                )
            self.assertFalse(state.data_plane_stopped())
            cycle.run_once()
            self.assertEqual(16, sum(totals))
            self.assertEqual([], spool.pending())

    def test_rollback_keeps_latest_spool_and_monotonic_protocol_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current"
            current.mkdir(mode=0o700)
            spool = node_agent.DurableTrafficSpool(current / "spool")
            state = node_agent.ProtocolState(current / "state" / "protocol.json")
            backup = root / "backup"
            backup.mkdir()
            shutil.copytree(current, backup / "state")
            spool.enqueue_many({"alice": {"tx": 4096, "rx": 1024}}, 11)
            for _ in range(5):
                state.next_sequence()
            state.set_traffic_ack(11)
            state.record_command_completed("d" * 32, 11)
            before = {str(p.relative_to(current)): p.read_bytes() for p in current.rglob("*") if p.is_file()}
            # External service/filesystem deployment adapters are inert. The
            # complete real rollback function still owns the state decision.
            helper = installer_function("restore_existing_data_plane").replace(
                "/var/lib/hysteria2-panel-node", '"${NODE_AGENT_STATE_DIR}"'
            )
            script = r'''
set -eu
NODE_AGENT_STATE_DIR="$WORK/current"
DATA_PLANE_BACKUP_DIR="$WORK/backup"
NODE_AGENT_CONFIG_DIR="$WORK/config"
NODE_AGENT_OPT_DIR="$WORK/opt"
NODE_UNINSTALL_SERVICE="$WORK/uninstall.service"
NODE_DATA_PLANE_TRANSACTION="$WORK/transaction"
initialize_data_plane_owned_paths() { DATA_PLANE_OWNED_FILES=(); DATA_PLANE_OWNED_UNITS=(); }
sha256sum() { :; }
stop_existing_data_plane() { :; }
rollback_new_data_plane_firewall_rules() { :; }
install() { :; }
durable_replace_file() { :; }
require_node_agent_directory() { test -d "$1" && test ! -L "$1"; }
restore_data_plane_heartbeat_units() { :; }
restore_data_plane_onboarding_installer() { :; }
restore_data_plane_network_snapshot() { :; }
systemctl() { :; }
restart_node_agent_heartbeat_timer() { :; }
read_data_plane_main_port() { echo 19999; }
wait_for_listener() { :; }
sync() { :; }
'''
            result = subprocess.run(["bash"], input=script + helper + "\nrestore_existing_data_plane\n", text=True,
                                    env={**os.environ, "WORK": directory}, capture_output=True, check=False)
            self.assertEqual(0, result.returncode, result.stderr)
            after = {str(p.relative_to(current)): p.read_bytes() for p in current.rglob("*") if p.is_file()}
            self.assertEqual(before, after)


    def test_installer_settles_before_stop_and_blocks_stop_on_collection_failure(self):
        for fail_collection in (False, True):
            with self.subTest(fail_collection=fail_collection), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                backup = root / "backup"
                config = root / "config"
                backup.mkdir()
                config.mkdir()
                (config / "stats.env").write_text("HY2PANEL_STATS_SECRET=synthetic-stats-secret\n")
                states = {
                    "hysteria2-panel-node-" + name + ".service": "active"
                    for name in ("auth", "control", "hysteria-main", "hysteria-udp443", "tcp-probe-main", "tcp-probe-udp443")
                }
                (root / "states.json").write_text(json.dumps(states))
                (root / "events.json").write_text("[]")
                adapter = root / "systemctl.py"
                adapter.write_text('''import json, os, pathlib, sys
root = pathlib.Path(os.environ["WORK"])
states = json.loads((root / "states.json").read_text())
args = sys.argv[1:]
if args[0] == "show":
    print("loaded" if "--property=LoadState" in args else states[args[-1]])
elif args[0] in {"stop", "start"}:
    events = json.loads((root / "events.json").read_text())
    events.extend(args[1:])
    (root / "events.json").write_text(json.dumps(events))
    for unit in args[1:]:
        states[unit] = "inactive" if args[0] == "stop" else "active"
    (root / "states.json").write_text(json.dumps(states))
elif args[0] == "is-active":
    raise SystemExit(0 if states[args[-1]] == "active" else 3)
else:
    raise SystemExit(1)
''')
                helper = backup / "maintenance-node-agent.py"
                helper.write_text('''import json, os, pathlib, sys
root = pathlib.Path(os.environ["WORK"])
states = json.loads((root / "states.json").read_text())
assert states["hysteria2-panel-node-auth.service"] == "inactive"
assert states["hysteria2-panel-node-control.service"] == "inactive"
assert states["hysteria2-panel-node-hysteria-main.service"] == "active"
assert states["hysteria2-panel-node-hysteria-udp443.service"] == "active"
assert sys.argv[1] == "quiesce-traffic"
assert "http://127.0.0.1:19997" in sys.argv and "http://127.0.0.1:19995" in sys.argv
assert os.environ["HY2PANEL_STATS_SECRET"] == "synthetic-stats-secret"
events = json.loads((root / "events.json").read_text())
events.append("quiesce-traffic")
(root / "events.json").write_text(json.dumps(events))
raise SystemExit(int(os.environ["FAIL_COLLECTION"]))
''')
                functions = "\n".join(installer_function(name) for name in (
                    "stop_loaded_units", "settle_existing_node_traffic", "quiesce_existing_data_plane", "stop_existing_data_plane"
                ))
                setup = r'''
set -eu
DATA_PLANE_BACKUP_DIR="$WORK/backup"
NODE_AGENT_CONFIG_DIR="$WORK/config"
NODE_AGENT_OPT_DIR="$WORK/old-agent"
NODE_AGENT_STATE_DIR="$WORK/current-state"
TMP_DIR="$WORK/staging"
require_node_agent_file() { test -f "$1" && test ! -L "$1"; }
systemctl() { "$PYTHON_BIN" "$WORK/systemctl.py" "$@"; }
'''
                result = subprocess.run(["bash"], input=setup + functions + "\nstop_existing_data_plane\n", text=True,
                    env={**os.environ, "WORK": directory, "PYTHON_BIN": sys.executable, "FAIL_COLLECTION": str(int(fail_collection))},
                    capture_output=True, check=False)
                self.assertEqual(int(fail_collection), result.returncode, result.stderr)
                after = json.loads((root / "states.json").read_text())
                events = json.loads((root / "events.json").read_text())
                self.assertEqual("active" if fail_collection else "inactive", after["hysteria2-panel-node-auth.service"])
                self.assertEqual("active" if fail_collection else "inactive", after["hysteria2-panel-node-control.service"])
                for unit in ("hysteria-main", "hysteria-udp443"):
                    name = "hysteria2-panel-node-" + unit + ".service"
                    self.assertEqual("active" if fail_collection else "inactive", after[name])
                    if not fail_collection:
                        self.assertLess(events.index("quiesce-traffic"), events.index(name))


class NodeMaintenanceLockTests(unittest.TestCase):
    def test_old_agent_gets_verified_maintenance_helper_without_replacing_live_code(self):
        import hashlib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = root / "opt"
            installed.mkdir()
            old_source = b"# old agent without the maintenance CLI\n"
            new_source = b"# authenticated release maintenance helper\n"
            agent = installed / "node_agent.py"
            agent.write_bytes(old_source)
            agent.chmod(0o755)
            (root / "download.py").write_bytes(new_source)
            setup = r'''
set -eu
NODE_AGENT_OPT_DIR="$WORK/opt"
NODE_AGENT_SOURCE_URL=https://example.invalid/fixed-release/node_agent.py
mktemp() { mkdir -p "$WORK/stage"; echo "$WORK/stage"; }
stat() { "$PYTHON_BIN" -c 'import os,sys; s=os.stat(sys.argv[1]); print("0:0:{:o}:{}".format(s.st_mode & 0o777,s.st_nlink))' "$3"; }
install() {
  local -a args=()
  while (( $# )); do
    if [[ "$1" == -o || "$1" == -g ]]; then shift 2
    else args+=("$1"); shift; fi
  done
  command install "${args[@]}"
}
sha256sum() {
  "$PYTHON_BIN" -c 'import hashlib,sys; expected,path=sys.stdin.read().strip().split("  ",1); raise SystemExit(0 if hashlib.sha256(open(path,"rb").read()).hexdigest()==expected else 1)'
}
download_file() { test "${NO_DOWNLOAD:-0}" = 0 || return 1; cp "$WORK/download.py" "$2"; touch "$WORK/downloaded"; }
fail() { echo "$*" >&2; exit 1; }
'''
            functions = "\n".join(installer_function(name) for name in (
                "stage_verified_installed_binary", "prepare_node_maintenance_agent"
            ))
            environment = {
                **os.environ, "WORK": directory, "PYTHON_BIN": sys.executable,
                "NODE_AGENT_SHA256": hashlib.sha256(new_source).hexdigest(),
            }

            def prepare(**extra):
                return subprocess.run(["bash"], input=setup + functions + "\nprepare_node_maintenance_agent\n", text=True,
                    env={**environment, **extra}, capture_output=True, check=False)

            result = prepare()
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(old_source, agent.read_bytes())
            self.assertEqual(new_source, (root / "stage/node_agent.py").read_bytes())
            self.assertTrue((root / "downloaded").exists())
            agent.write_bytes(new_source)
            (root / "downloaded").unlink()
            result = prepare(NO_DOWNLOAD="1")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse((root / "downloaded").exists())
            agent.write_bytes(old_source)
            (root / "download.py").write_bytes(b"# damaged download\n")
            result = prepare()
            self.assertEqual(1, result.returncode)
            self.assertIn("SHA-256", result.stderr)
            self.assertEqual(old_source, agent.read_bytes())

    def test_concurrent_join_cannot_delete_a_committed_identity_and_worker_takes_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "systemd").mkdir()
            (root / "units").mkdir()
            # Linux uses the deployed util-linux flock. macOS uses its kernel
            # flock through Python with the same supervising/close-fds contract.
            flock = shutil.which("flock")
            if flock is None:
                fallback = root / "flock"
                fallback.write_text("#!" + sys.executable + "\n" + '''import fcntl, os, subprocess, sys
args = sys.argv[1:]
assert args[:4] == ["-n", "-E", "75", "--close"]
with open(args[4], "a") as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(75)
    sys.exit(subprocess.call(args[5:], close_fds=True))
''')
                fallback.chmod(0o755)
                flock = str(fallback)
            source = (ROOT / "install.sh").read_text()
            dispatch_start = source.index("if (( WATCH_UPGRADE == 1 )); then", source.index('ORIGINAL_ARGS=("$@")'))
            dispatch = source[dispatch_start:source.index('AUTO_UPDATE="${HY2PANEL_AUTO_UPDATE:-0}"', dispatch_start)]
            # Current dispatch includes the lock; the old dispatcher runs the
            # same join functions without it, reproducing cross-task cleanup.
            header = r'''#!/usr/bin/env bash
set -euo pipefail
PANEL_VERSION=0.39.16
PANEL_REF=v0.39.16
WATCH_UPGRADE=0
UNINSTALL_NODE=0
JOIN_NODE=1
REBIND_NODE=0
COMPLETE_NODE_ONBOARDING=0
ACTIVATE_NODE_AGENT=0
ACTIVATE_DATA_PLANE=0
RECOVER_UPGRADE=0
RECOVER_FRESH=0
MAINTENANCE_LOCK_HELD=0
[[ "${1:-}" != --maintenance-lock-held ]] || MAINTENANCE_LOCK_HELD=1
ORIGINAL_ARGS=(--join-node)
NODE_AGENT_OPT_DIR="$WORK/opt"
NODE_AGENT_CONFIG_DIR="$WORK/etc"
NODE_ONBOARDING_INSTALLER="$NODE_AGENT_OPT_DIR/onboarding-install.sh"
NODE_ONBOARDING_SERVICE="$WORK/units/onboarding.service"
NODE_ONBOARDING_TIMER="$WORK/units/onboarding.timer"
NODE_ONBOARDING_MARKER="$NODE_AGENT_CONFIG_DIR/.onboarding-pending"
MAINTENANCE_RUNTIME_DIR="$WORK/maintenance"
MAINTENANCE_LOCK_FILE="$MAINTENANCE_RUNTIME_DIR/lock"
MANAGED_MARKER="$WORK/panel-managed"
NODE_AGENT_SOURCE_URL=https://example.invalid/synthetic.py
NODE_AGENT_SHA256=synthetic
HY2PANEL_PANEL_URL=https://example.invalid:19998
HY2PANEL_ENROLLMENT_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
PYTHON_BIN=python_stub
JOIN_NODE_MUTATED=0
uname() { echo amd64; }
id() { return 1; }
stat() {
  "$TEST_PYTHON" - "$3" <<'STAT'
import os, sys
print("0:0:{:o}".format(os.stat(sys.argv[1]).st_mode & 0o777))
STAT
}
ensure_node_dependencies() { :; }
sync() { :; }
sha256sum() { cat >/dev/null; }
sleep() { /bin/sleep 0.01; }
wait_path() {
  for _ in {1..1000}; do
    [[ ! -e "$1" ]] || return 0
    /bin/sleep 0.01
  done
  return 1
}
download_file() {
  touch "$WORK/preflight-$ROLE"
  [[ "$ROLE" != A ]] || wait_path "$WORK/release-A"
  printf '# synthetic verified source\n' > "$2"
}
openssl() {
  while (( $# )); do
    if [[ "$1" == -out ]]; then
      shift
      printf 'synthetic-key-%s\n' "$ROLE" > "$1"
      return 0
    fi
    shift
  done
  return 1
}
install() {
  local -a args=()
  while (( $# )); do
    if [[ "$1" == -o || "$1" == -g ]]; then shift 2
    else args+=("$1"); shift; fi
  done
  command install "${args[@]}"
}
python_stub() {
  [[ "$1" != -m ]] || return 0
  if [[ "$ROLE" == B ]]; then
    touch "$WORK/B-registering"
    wait_path "$WORK/A-finished"
    return 1
  fi
  while (( $# )); do
    if [[ "$1" == --state-file ]]; then
      shift
      printf '{"syntheticRegisteredRole":"A"}\n' > "$1"
      return 0
    fi
    shift
  done
  return 1
}
systemctl() {
  if [[ "$1" == start && "$ROLE" == A ]]; then
    # The real systemd worker is independent of the registration process.
    # Model its retry timer with a separate process taking the exact same lock.
    "$TEST_PYTHON" "$WORK/worker.py" >/dev/null 2>&1 &
  fi
}
fail() {
  echo "$ROLE: $*" >&2
  if (( JOIN_NODE_MUTATED == 1 )); then rollback_join_node_install; fi
  exit 1
}
'''
            worker = '''import os, pathlib, subprocess, time
root = pathlib.Path(os.environ["WORK"])
for _ in range(1000):
    result = subprocess.run([os.environ["TEST_FLOCK"], "-n", "-E", "75", "--close", str(root / "maintenance/lock"), os.environ["TEST_PYTHON"], "-c", "import os,pathlib; p=pathlib.Path(os.environ['WORK']); (p/'etc/.onboarding-pending').unlink(missing_ok=True); (p/'worker-finished').touch()"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode == 0:
        break
    time.sleep(.01)
'''
            # missing_ok is Python 3.8-compatible.
            (root / "worker.py").write_text(worker)
            header += "\nflock() { " + shlex.quote(flock) + ' "$@"; }\n'
            functions = "\n".join(installer_function(name) for name in (
                "rollback_join_node_install", "install_join_node", "wait_for_node_onboarding", "acquire_maintenance_lock"
            ))
            functions = functions.replace("/run/systemd/system", "${WORK}/systemd")
            script = root / "driver.sh"
            script.write_text(header + functions + dispatch)
            environment = {**os.environ, "WORK": directory, "TEST_PYTHON": sys.executable, "TEST_FLOCK": flock}
            a = subprocess.Popen(["bash", str(script)], env={**environment, "ROLE": "A"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            b = None
            try:
                deadline = time.monotonic() + 10
                while not (root / "preflight-A").exists():
                    self.assertIsNone(a.poll(), a.communicate() if a.poll() is not None else "")
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.01)
                b = subprocess.Popen(["bash", str(script)], env={**environment, "ROLE": "B"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                while b.poll() is None and not (root / "B-registering").exists():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.01)
                (root / "release-A").touch()
                a_out, a_err = a.communicate(timeout=15)
                self.assertEqual(0, a.returncode, a_out + a_err)
                self.assertTrue((root / "etc/registration.json").exists())
                (root / "A-finished").touch()
                b_out, b_err = b.communicate(timeout=15)
                self.assertEqual(1, b.returncode, b_out + b_err)
                self.assertIn("另一个安装", b_err)
                self.assertFalse((root / "preflight-B").exists())
                self.assertTrue((root / "worker-finished").exists())
                self.assertTrue((root / "etc/node.key").exists())
                self.assertEqual({"syntheticRegisteredRole": "A"}, json.loads((root / "etc/registration.json").read_text()))
            finally:
                for process in (a, b):
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
