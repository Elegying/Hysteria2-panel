import hashlib
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
README = ROOT / "README.md"
TCP_PROBE = ROOT / "tcp_probe.py"


class InstallerContractTests(unittest.TestCase):
    def test_panel_install_generates_and_preserves_a_stable_usage_origin_identity(self):
        source = INSTALLER.read_text()

        self.assertIn(
            'USAGE_ORIGIN_ID="${HY2PANEL_USAGE_ORIGIN_ID:-$(openssl rand -hex 16)}"',
            source,
        )
        self.assertIn("HY2PANEL_USAGE_ORIGIN_ID=${USAGE_ORIGIN_ID}", source)
        self.assertLess(
            source.index('USAGE_ORIGIN_ID="${HY2PANEL_USAGE_ORIGIN_ID:-'),
            source.index("HY2PANEL_USAGE_ORIGIN_ID=${USAGE_ORIGIN_ID}"),
        )

    def run_firewall_function(self, mocks):
        source = INSTALLER.read_text()
        start = source.index("ufw_rule_is_recorded()")
        end = source.index("\n\noptimize_network_stack()", start)
        firewall_functions = source[start:end]
        script = f"""
set -Eeuo pipefail
{firewall_functions}
fail() {{
  printf 'FAIL:%s\n' "$*" >&2
  exit 97
}}
HYSTERIA_PORT=19999
PANEL_PORT=19998
UDP_443_ENABLED=1
PYTHON_BIN={sys.executable!r}
FIREWALL_RESULT=""
FIREWALL_MANAGER="unprepared"
FIREWALL_RULES=()
FIREWALL_ZONES=()
FIREWALL_PENDING=()
FIREWALL_APPLIED=()
UFW_ADDED_RULES=""
MANAGED_FIREWALL_STATE_FILE="${{CAPTURE}}.managed"
FIREWALL_TRANSACTION_FILE="${{CAPTURE}}.transaction"
FIREWALL_TRANSACTION_MAGIC=HYSTERIA2_PANEL_FIREWALL_TRANSACTION_V1
FIREWALL_OWNED=()
FIREWALL_TRANSACTION_LINES=()
FIREWALL_NEWLY_OWNED=()
durable_replace_file() {{
  local source_file="$1" destination="$2" mode="$3"
  install -m "$mode" "$source_file" "${{destination}}.new"
  mv "${{destination}}.new" "$destination"
}}
durable_remove_file() {{ rm -f -- "$1"; }}
{mocks}
UFW_RULES_PATH="${{CAPTURE}}.ufw"
UFW_TEMPLATE_PATH="${{CAPTURE}}.ufw-templates"
mkdir -p "${{UFW_RULES_PATH}}" "${{UFW_TEMPLATE_PATH}}"
for framework_file in before.rules before6.rules after.rules after6.rules; do
  printf '# pristine test framework\n' > "${{UFW_RULES_PATH}}/${{framework_file}}"
  printf '# pristine test framework\n' > "${{UFW_TEMPLATE_PATH}}/${{framework_file}}"
done
case "${{MOCK_UFW_FRAMEWORK_MODE:-}}" in
  rules) printf '# custom rule\n' >> "${{UFW_RULES_PATH}}/before.rules" ;;
  hook)
    printf '#!/bin/sh\nexit 0\n' > "${{UFW_RULES_PATH}}/before.init"
    chmod 700 "${{UFW_RULES_PATH}}/before.init"
    ;;
esac
eval "mocked_$(declare -f ufw)"
ufw() {{
  if [[ "$*" == "show raw" ]]; then
    [[ "${{MOCK_UFW_RAW_MODE:-}}" != "command-error" ]]
    return
  fi
  if [[ "$*" == "show listening" ]]; then
    if [[ -n "${{MOCK_UFW_LISTENING:-}}" ]]; then
      printf '%b' "${{MOCK_UFW_LISTENING}}"
      return "${{MOCK_UFW_LISTENING_STATUS:-0}}"
    fi
    added="$(mocked_ufw show added)" || return
    for protocol in tcp udp; do
      printf '%s:\n' "$protocol"
      awk -v protocol="$protocol" '
        $1 == "ufw" && $2 == "allow" && $3 ~ ("/" protocol "$") {{
          split($3, value, "/")
          print "  " value[1] " * (test-listener)"
          print "   [ 1] allow " $3
        }}
      ' <<< "$added"
    done
    return 0
  fi
  mocked_ufw "$@"
}}
eval "mocked_$(declare -f firewall-cmd)"
firewall-cmd() {{
  if [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "quiet-output" && "$*" == *"--quiet"* ]]; then
    case "$*" in
      *"--get-policies"*|*"--list-ingress-zones"*|*"--list-egress-zones"*|*"--get-target"*|*"--list-rich-rules"*)
        return 2
        ;;
    esac
  fi
  if [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "permanent-target" && "$*" == *"--get-target"* && "$*" != *"--permanent"* ]]; then
    return 2
  fi
  if [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "quiet-chain" && "$*" == *"--quiet"* && "$*" == *"--get-all-chains"* ]]; then
    return 0
  fi
  case "$*" in
    "--help")
      if [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "help-error" ]]; then
        return 2
      elif [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "incomplete-direct" ]]; then
        printf '%s\n' '--query-panic --direct --get-all-rules --get-policies'
      elif [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "old" ]]; then
        printf '%s\n' '--query-panic --direct --get-all-chains --get-all-rules --get-all-passthroughs'
      else
        printf '%s\n' '--query-panic --direct --get-all-chains --get-all-rules --get-all-passthroughs --get-policies --query-disable'
      fi
      ;;
    *"--query-panic")
      [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "error" ]] || return 2
      [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "panic" ]]
      ;;
    *"--direct --get-all-rules")
      [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "error" ]] || return 2
      [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "direct" ]] || printf 'ipv4 filter INPUT 0 -j DROP\n'
      ;;
    *"--direct --get-all-chains")
      [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "error" ]] || return 2
      [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "chain" && "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "quiet-chain" ]] || printf 'ipv4 filter H2P-BLOCK\n'
      ;;
    *"--direct --get-all-passthroughs")
      [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "error" ]] || return 2
      [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "passthrough" ]] || printf 'ipv4 -A INPUT -j DROP\n'
      ;;
    *"--get-policies")
      [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "error" ]] || return 2
      if [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "policy" ]]; then
        printf 'blocking-policy\n'
      elif [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "safe-policy" ]]; then
        printf 'allow-host-ipv6 safe-policy\n'
      elif [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "disabled-policy" ]]; then
        printf 'allow-host-ipv6 disabled-policy\n'
      else
        printf 'allow-host-ipv6\n'
      fi
      ;;
    *"--policy=disabled-policy --query-disable") return 0 ;;
    *"--query-disable") return 1 ;;
    *"--policy=allow-host-ipv6 --list-egress-zones") printf 'HOST\n' ;;
    *"--policy=allow-host-ipv6 --list-ingress-zones") printf 'ANY\n' ;;
    *"--policy=allow-host-ipv6 --get-target") printf 'CONTINUE\n' ;;
    *"--policy=allow-host-ipv6 --list-rich-rules") printf 'rule family=ipv6 icmp-type name=neighbour-solicitation accept\n' ;;
    *"--policy=blocking-policy --list-egress-zones") printf 'HOST\n' ;;
    *"--policy=blocking-policy --list-ingress-zones") printf 'ANY\n' ;;
    *"--policy=blocking-policy --get-target") printf 'DROP\n' ;;
    *"--policy=blocking-policy --list-rich-rules") : ;;
    *"--policy=safe-policy --list-egress-zones") printf 'HOST\n' ;;
    *"--policy=safe-policy --list-ingress-zones") printf 'ANY\n' ;;
    *"--policy=safe-policy --get-target") printf 'CONTINUE\n' ;;
    *"--policy=safe-policy --list-rich-rules") : ;;
    *"--policy=disabled-policy --list-egress-zones") printf 'HOST\n' ;;
    *"--policy=disabled-policy --list-ingress-zones") printf 'ANY\n' ;;
    *"--policy=disabled-policy --get-target") printf 'DROP\n' ;;
    *"--policy=disabled-policy --list-rich-rules") : ;;
    *) mocked_firewall-cmd "$@" ;;
  esac
}}
busctl() {{
  [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "backend-error" ]] || return 1
  if [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "legacy-backend" ]]; then
    printf 's "iptables"\n'
  else
    printf 's "nftables"\n'
  fi
}}
eval "mocked_$(declare -f nft)"
nft() {{
  if [[ "$*" == "-j list ruleset" ]] && mocked_firewall-cmd --state >/dev/null 2>&1; then
    if [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" == "raw" ]]; then
      printf '%s\n' '{{"nftables":[{{"table":{{"family":"inet","name":"firewalld"}}}},{{"table":{{"family":"inet","name":"custom"}}}},{{"chain":{{"family":"inet","table":"custom","name":"input","hook":"input","policy":"accept"}}}},{{"rule":{{"family":"inet","table":"custom","chain":"input","expr":[{{"drop":null}}]}}}}]}}'
    else
      printf '%s\n' '{{"nftables":[{{"table":{{"family":"inet","name":"firewalld"}}}}]}}'
    fi
    return 0
  fi
  if [[ "$*" == "-j list ruleset" ]] && mocked_ufw status | grep -q '^Status: active$'; then
    if [[ "${{MOCK_UFW_RAW_MODE:-}}" == "foreign-nft" ]]; then
      printf '%s\n' '{{"nftables":[{{"table":{{"family":"ip","name":"filter"}}}},{{"chain":{{"family":"ip","table":"filter","name":"INPUT","hook":"input","policy":"drop"}}}},{{"table":{{"family":"inet","name":"custom"}}}},{{"chain":{{"family":"inet","table":"custom","name":"early","hook":"input","priority":-100,"policy":"accept"}}}},{{"rule":{{"family":"inet","table":"custom","chain":"early","expr":[{{"drop":null}}]}}}}]}}'
    else
      printf '%s\n' '{{"nftables":[{{"table":{{"family":"ip","name":"filter"}}}},{{"chain":{{"family":"ip","table":"filter","name":"INPUT","hook":"input","policy":"drop"}}}}]}}'
    fi
    return 0
  fi
  mocked_nft "$@"
}}
if declare -F iptables-save >/dev/null; then
  eval "mocked_$(declare -f iptables-save)"
else
  mocked_iptables-save() {{ :; }}
fi
iptables-save() {{
  if mocked_ufw status | grep -q '^Status: active$'; then
    if [[ "${{MOCK_UFW_RAW_MODE:-}}" == "foreign-iptables" ]]; then
      printf '%s\n' '*raw' ':PREROUTING ACCEPT [0:0]' '-A PREROUTING -p tcp --dport 19999 -j DROP' 'COMMIT'
    fi
    printf '%s\n' '*filter' ':INPUT DROP [0:0]' \
      '-A INPUT -j ufw-before-logging-input' '-A INPUT -j ufw-before-input' \
      '-A INPUT -j ufw-after-input' '-A INPUT -j ufw-after-logging-input' \
      '-A INPUT -j ufw-reject-input' '-A INPUT -j ufw-track-input' 'COMMIT'
    return 0
  fi
  if mocked_firewall-cmd --state >/dev/null 2>&1; then
    printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]'
    [[ "${{MOCK_FIREWALLD_GLOBAL_MODE:-}}" != "untracked" ]] \
      || printf '%s\n' '-A INPUT -p tcp --dport 19999 -j DROP'
    printf '%s\n' 'COMMIT'
    return 0
  fi
  mocked_iptables-save "$@"
}}
if declare -F ip6tables-save >/dev/null; then
  eval "mocked_$(declare -f ip6tables-save)"
else
  mocked_ip6tables-save() {{ :; }}
fi
ip6tables-save() {{
  if mocked_ufw status | grep -q '^Status: active$'; then
    printf '%s\n' '*filter' ':INPUT DROP [0:0]' \
      '-A INPUT -j ufw6-before-logging-input' '-A INPUT -j ufw6-before-input' \
      '-A INPUT -j ufw6-after-input' '-A INPUT -j ufw6-after-logging-input' \
      '-A INPUT -j ufw6-reject-input' '-A INPUT -j ufw6-track-input' 'COMMIT'
    return 0
  fi
  if mocked_firewall-cmd --state >/dev/null 2>&1; then
    printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'
    return 0
  fi
  mocked_ip6tables-save "$@"
}}
prepare_firewall
configure_firewall
"""
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "firewall-calls"
            result = subprocess.run(
                ["bash"],
                input=script,
                capture_output=True,
                text=True,
                env={**os.environ, "CAPTURE": str(capture)},
            )
            calls = capture.read_text().splitlines() if capture.exists() else []
        return result, calls

    def run_database_rollback_helper(self, setup):
        source = INSTALLER.read_text()
        start = source.index("checkpoint_database()")
        end = source.index("\n\nufw_rule_is_recorded()", start)
        helpers = source[start:end]
        script = f"""
set -Eeuo pipefail
PYTHON_BIN={sys.executable!r}
{helpers}
database="$WORK/panel.db"
snapshot="$WORK/snapshot.db"
{setup}
preserve_or_restore_database "$database" "$snapshot"
"$PYTHON_BIN" - "$database" <<'PY'
import sqlite3
import sys
with sqlite3.connect(sys.argv[1]) as connection:
    print(connection.execute("SELECT value FROM state").fetchone()[0])
PY
"""
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(
                ["bash"],
                input=script,
                capture_output=True,
                text=True,
                env={**os.environ, "WORK": directory},
            )

    def run_checkpoint_helper(self, setup=""):
        source = INSTALLER.read_text()
        start = source.index("checkpoint_database()")
        end = source.index("\n\nassert_units_unclaimed()", start)
        helper = source[start:end].replace("timeout=30", "timeout=0.1")
        script = f"""
set -Eeuo pipefail
PYTHON_BIN={sys.executable!r}
{helper}
database="$WORK/panel.db"
"$PYTHON_BIN" - "$database" <<'PY'
import sqlite3
import sys
with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE state(value TEXT)")
    connection.execute("INSERT INTO state VALUES ('ready')")
PY
{setup}
checkpoint_database "$database"
"""
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(
                ["bash"],
                input=script,
                capture_output=True,
                text=True,
                env={**os.environ, "WORK": directory},
            )

    def run_installer_finalizer(self, mode):
        source = INSTALLER.read_text()
        traps = source[
            source.index("unexpected_error()") : source.index("\n\nselect_python()")
        ]
        script = f"""
set -euo pipefail
INSTALL_COMMITTED=0
INSTALL_FINALIZING=0
TMP_DIR="$INSTALLER_TMP"
{traps}
rollback_existing_install() {{ printf 'rollback:%s\n' "$1" >> "$CAPTURE"; }}
if [[ "$MODE" == "repeat-signal" ]]; then
  rollback_existing_install() {{
    printf 'rollback:%s\n' "$1" >> "$CAPTURE"
    kill -TERM "$$"
  }}
fi
if [[ "$MODE" == "cleanup-fail" || "$MODE" == "error-cleanup-fail" ]]; then
  rm() {{ return 12; }}
fi
case "$MODE" in
  error) false ;;
  error7) exit 7 ;;
  error-cleanup-fail) false ;;
  hup) kill -HUP "$$" ;;
  int) kill -INT "$$" ;;
  term) kill -TERM "$$" ;;
  subshell) (false) ;;
  command-substitution) value="$(false)" ;;
  pipeline) false | true ;;
  repeat-signal) false ;;
  cleanup-fail) : ;;
  committed) INSTALL_COMMITTED=1; kill -TERM "$$" ;;
  *) exit 98 ;;
esac
"""
        with tempfile.TemporaryDirectory() as directory:
            with tempfile.TemporaryDirectory(
                prefix="hysteria2-panel.finalizer.", dir="/tmp"
            ) as installer_tmp:
                capture = Path(directory) / "finalizer-calls"
                result = subprocess.run(
                    ["bash"],
                    input=script,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env={
                        **os.environ,
                        "CAPTURE": str(capture),
                        "INSTALLER_TMP": installer_tmp,
                        "MODE": mode,
                    },
                )
                calls = capture.read_text().splitlines() if capture.exists() else []
                temporary_exists = Path(installer_tmp).exists()
        return result, calls, temporary_exists

    def test_installer_has_valid_shell_syntax_and_help_is_safe(self):
        syntax = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
        self.assertEqual(0, syntax.returncode, syntax.stderr)

        help_result = subprocess.run(
            ["bash", str(INSTALLER), "--help"], capture_output=True, text=True
        )
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        self.assertIn("19999", help_result.stdout)

    def test_readme_offers_one_line_bootstrap_and_strict_signed_install(self):
        source = README.read_text()
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        quick_command = (
            "bash <(curl -fsSL "
            "https://raw.githubusercontent.com/Elegying/Hysteria2-panel/main/install.sh)"
        )
        self.assertIn(quick_command, source)
        self.assertIn("首次信任入口", source)
        self.assertIn("GitHub HTTPS", source)
        self.assertIn("releases/download/v", source)
        self.assertIn("install.sh.sigstore.json", source)
        self.assertIn("verify-blob", source)
        self.assertIn("--certificate-identity", source)
        self.assertIn("--certificate-oidc-issuer", source)
        self.assertIn("bash -n", source)
        self.assertLess(source.index(quick_command), source.index("verify-blob"))
        self.assertLess(source.index("verify-blob"), source.index("sudo bash"))
        self.assertIn("if quick_command not in readme:", workflow)
        self.assertNotIn(
            "README must not execute an unsigned main-branch installer", workflow
        )

    def test_upgrade_is_armed_for_boot_recovery_before_payload_overwrite(self):
        source = INSTALLER.read_text()

        self.assertIn(
            "UPGRADE_ACTIVE_MARKER=/var/backups/hysteria2-panel/.upgrade-active",
            source,
        )
        self.assertIn("recover_interrupted_upgrade()", source)
        self.assertIn("--recover-upgrade", source)
        self.assertIn("hysteria2-panel-upgrade-recover.service", source)
        self.assertIn("ConditionPathExists=${UPGRADE_ACTIVE_MARKER}", source)
        self.assertIn("Before=hysteria2-panel-restore-recover.service", source)
        self.assertIn("systemctl enable hysteria2-panel-upgrade-recover.service", source)
        self.assertIn(
            "/etc/systemd/system/multi-user.target.wants/hysteria2-panel-upgrade-recover.service",
            source,
        )
        self.assertIn("verify_backup_manifest", source)
        arm = source.index("arm_upgrade_transaction")
        first_payload = source.index(
            'install -o root -g root -m 0755 "${TMP_DIR}/hysteria"', arm
        )
        self.assertLess(arm, first_payload)
        clear = source.index("clear_upgrade_transaction", first_payload)
        committed = source.index("INSTALL_COMMITTED=1", first_payload)
        self.assertLess(first_payload, clear)
        self.assertLess(clear, committed)

    def test_upgrade_checks_backup_space_and_prunes_only_automatic_backups(self):
        source = INSTALLER.read_text()

        self.assertIn("require_backup_space()", source)
        self.assertIn("prune_automatic_backups()", source)
        self.assertIn("BACKUP_RETENTION_DAYS=90", source)
        self.assertIn("BACKUP_MAX_COUNT=10", source)
        preflight = source.index("require_backup_space", source.index('timestamp="$(date'))
        create_backup = source.index('install -d -m 0700 "${BACKUP_DIR}"', preflight)
        self.assertLess(preflight, create_backup)
        commit = source.rindex("INSTALL_COMMITTED=1")
        prune = source.index("prune_automatic_backups", commit)
        self.assertLess(commit, prune)
        helper = source[
            source.index("prune_automatic_backups()") : source.index(
                "\n\nrollback_firewall_after_service_recovery()"
            )
        ]
        self.assertIn("[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}", helper)
        self.assertNotIn("restore-", helper)

    def test_unmanaged_path_collision_is_checked_before_package_installation(self):
        source = INSTALLER.read_text()
        main = source.split('if [[ "${1:-}" == "--help"', 1)[1]
        collision = main.index("assert_no_unmanaged_install_paths")
        dependencies = main.index("install_system_dependencies")
        self.assertLess(collision, dependencies)

    def test_repository_enforces_lf_for_scripts_and_hash_fixed_sources(self):
        tracked = subprocess.run(
            ["git", "ls-files", "--", "*.py", "*.sh", "*.yml", "*.yaml"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        self.assertTrue(tracked)

        attributes = subprocess.run(
            ["git", "check-attr", "eol", "--", *tracked],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        self.assertEqual(len(tracked), len(attributes))
        self.assertTrue(all(line.endswith(": eol: lf") for line in attributes))
        for relative_path in tracked:
            self.assertNotIn(b"\r\n", (ROOT / relative_path).read_bytes(), relative_path)

    def test_installer_pins_upstream_release_and_checksums(self):
        source = INSTALLER.read_text()

        self.assertIn('PANEL_VERSION="0.32.1"', source)
        self.assertIn('HYSTERIA_VERSION="2.12.1"', source)
        self.assertIn(
            'HYSTERIA_SHA_AMD64="ffc032c7ca6b78676d337097ca7f61bebc3a90a4f3a656693adf368f304cdbc7"',
            source,
        )
        self.assertIn(
            'HYSTERIA_SHA_ARM64="c9cd1af6395eee13a937f429ea71b290e3cc571eea2b4d7f8bc7c49c1d23a792"',
            source,
        )
        self.assertRegex(source, r'PANEL_SHA256="[0-9a-f]{64}"')
        self.assertRegex(source, r'QRCODEGEN_SHA256="[0-9a-f]{64}"')
        self.assertIn('QRCODEGEN_SOURCE_URL=', source)
        self.assertIn(
            'TCP_PROBE_SHA256="b63da9cc1e58ae3459e188a507d9e71bd205b5f3320448bc319d1f80a21885a2"',
            source,
        )
        self.assertIn('面板源码 SHA-256 校验失败', source)
        self.assertIn('二维码编码器 SHA-256 校验失败', source)
        self.assertIn('TCP 探测源码 SHA-256 校验失败', source)
        self.assertIn('"${PYTHON_BIN}" -m py_compile "${TMP_DIR}/qrcodegen.py"', source)
        self.assertIn(
            'install -o root -g root -m 0644 "${TMP_DIR}/qrcodegen.py" /opt/hysteria2-panel/qrcodegen.py',
            source,
        )
        self.assertIn("sha256sum", source)
        panel_sha = source.split('PANEL_SHA256="', 1)[1].split('"', 1)[0]
        qrcodegen_sha = source.split('QRCODEGEN_SHA256="', 1)[1].split('"', 1)[0]
        probe_sha = source.split('TCP_PROBE_SHA256="', 1)[1].split('"', 1)[0]
        self.assertEqual(
            hashlib.sha256((ROOT / "hysteria2_panel.py").read_bytes()).hexdigest(),
            panel_sha,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "qrcodegen.py").read_bytes()).hexdigest(),
            qrcodegen_sha,
        )
        self.assertEqual(hashlib.sha256(TCP_PROBE.read_bytes()).hexdigest(), probe_sha)

    def test_vendored_qrcodegen_is_importable_on_supported_python_3_8(self):
        source = (ROOT / "qrcodegen.py").read_text()

        self.assertIn("class _BitBuffer(list):", source)
        self.assertNotIn("class _BitBuffer(list[int]):", source)

    def test_installer_pins_and_installs_every_panel_module(self):
        source = INSTALLER.read_text()
        modules = {
            "hy2panel/__init__.py": "HY2PANEL_INIT_SHA256",
            "hy2panel/version.py": "HY2PANEL_VERSION_SHA256",
            "hy2panel/web_assets.py": "HY2PANEL_WEB_ASSETS_SHA256",
            "hy2panel/operations.py": "HY2PANEL_OPERATIONS_SHA256",
            "hy2panel/release.py": "HY2PANEL_RELEASE_SHA256",
            "hy2panel/health.py": "HY2PANEL_HEALTH_SHA256",
            "hy2panel/certificate.py": "HY2PANEL_CERTIFICATE_SHA256",
            "hy2panel/systemd.py": "HY2PANEL_SYSTEMD_SHA256",
            "hy2panel/nodes.py": "HY2PANEL_NODES_SHA256",
            "hy2panel/distributed.py": "HY2PANEL_DISTRIBUTED_SHA256",
        }

        for relative_path, variable in modules.items():
            self.assertRegex(source, variable + r'="[0-9a-f]{64}"')
            self.assertIn(relative_path, source)
            expected = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
            actual = source.split(variable + '="', 1)[1].split('"', 1)[0]
            self.assertEqual(expected, actual)
        self.assertIn('"${PYTHON_BIN}" -m py_compile "${TMP_DIR}/hy2panel/"*.py', source)
        self.assertIn('install -o root -g root -m 0755 "${TMP_DIR}/cosign" /opt/hysteria2-panel/bin/cosign', source)
        self.assertRegex(source, r'COSIGN_SHA_AMD64="[0-9a-f]{64}"')
        self.assertRegex(source, r'COSIGN_SHA_ARM64="[0-9a-f]{64}"')

    def test_daily_offsite_backup_is_pinned_sandboxed_and_persistent(self):
        source = INSTALLER.read_text()
        expected = hashlib.sha256((ROOT / "offsite_backup.py").read_bytes()).hexdigest()
        actual = source.split('OFFSITE_BACKUP_SHA256="', 1)[1].split('"', 1)[0]
        unit_start = source.index(
            "cat > /etc/systemd/system/hysteria2-panel-offsite-backup.service"
        )
        unit_end = source.index("\nEOF", unit_start)
        offsite_unit = source[unit_start:unit_end]

        self.assertEqual(expected, actual)
        self.assertIn("offsite_backup.py", source)
        self.assertIn("hysteria2-panel-offsite-backup.service", source)
        self.assertIn("hysteria2-panel-offsite-backup.timer", source)
        self.assertIn("OnCalendar=*-*-* 03:30:00", source)
        self.assertIn("RandomizedDelaySec=2h", source)
        self.assertIn("Persistent=true", source)
        self.assertIn("Group=hy2panel", offsite_unit)
        self.assertIn("ProtectSystem=strict", offsite_unit)
        self.assertIn(
            "ReadOnlyPaths=/opt/hysteria2-panel /etc/hysteria2-panel", offsite_unit
        )
        self.assertIn("CapabilityBoundingSet=CAP_DAC_OVERRIDE", offsite_unit)
        self.assertIn("AmbientCapabilities=CAP_DAC_OVERRIDE", offsite_unit)
        self.assertIn("systemctl enable hysteria2-panel-offsite-backup.timer", source)

    def test_join_node_mode_is_isolated_from_hysteria_identity_and_network_mutations(self):
        source = INSTALLER.read_text()
        start = source.index("install_join_node()")
        end = source.index("\n}\n", start) + 2
        join_function = source[start:end]

        self.assertIn('NODE_AGENT_SOURCE_URL=', source)
        self.assertRegex(source, r'NODE_AGENT_SHA256="[0-9a-f]{64}"')
        node_agent_sha = source.split('NODE_AGENT_SHA256="', 1)[1].split('"', 1)[0]
        self.assertEqual(
            hashlib.sha256((ROOT / "node_agent.py").read_bytes()).hexdigest(),
            node_agent_sha,
        )
        self.assertIn('JOIN_NODE=1', source)
        self.assertIn('install_join_node', source)
        self.assertIn('openssl genpkey -algorithm ED25519', join_function)
        self.assertIn('/node_agent.py" register', join_function)
        self.assertIn('HY2PANEL_ENROLLMENT_TOKEN', join_function)
        self.assertIn('[[ -d /run/systemd/system ]]', join_function)
        self.assertIn('NODE_AGENT_OPT_DIR=/opt/hysteria2-panel-node', source)
        self.assertIn('NODE_AGENT_CONFIG_DIR=/etc/hysteria2-panel-node', source)
        self.assertNotIn('hysteria cert', join_function)
        self.assertNotIn('configure_firewall', join_function)
        self.assertNotIn('server.crt', join_function)
        self.assertNotIn('HY2PANEL_HMAC_KEY', join_function)
        self.assertNotIn('vpn.example.com', join_function)

        dispatch = source.index('if (( JOIN_NODE == 1 )); then')
        full_install = source.index('\nacquire_maintenance_lock\n', dispatch)
        self.assertLess(dispatch, full_install)

    def test_existing_data_node_rebind_is_durable_and_preserves_identity_and_spool(self):
        source = INSTALLER.read_text()
        start = source.index("rebind_node()")
        rebind = source[start:source.index("\n}\n", start) + 2]
        rollback_start = source.index("rollback_node_rebind()")
        rollback = source[
            rollback_start:source.index("\n}\n", rollback_start) + 2
        ]

        self.assertIn("--rebind-node", source)
        self.assertIn("REBIND_NODE=1", source)
        self.assertIn("NODE_REBIND_TRANSACTION", source)
        self.assertIn("NODE_REBIND_TRANSACTION_MAGIC", source)
        self.assertIn("recover_interrupted_node_rebind", rebind)
        self.assertLess(
            rebind.index("recover_interrupted_node_rebind"),
            rebind.index(
                "systemctl is-active --quiet hysteria2-panel-node-heartbeat.timer"
            ),
        )
        self.assertIn("write_node_rebind_backup", rebind)
        self.assertIn("arm_node_rebind_transaction", rebind)
        self.assertIn('openssl pkey -in "${NODE_AGENT_CONFIG_DIR}/node.key"', rebind)
        self.assertIn('cmp -s "${generated_public}"', rebind)
        self.assertIn('node_agent.py" register', rebind)
        self.assertIn('"${TMP_DIR}/registration.json"', rebind)
        self.assertIn("durable_replace_file", rebind)
        self.assertIn("hysteria2-panel-node-heartbeat.service", rebind)
        self.assertNotIn(
            "systemctl start hysteria2-panel-node-heartbeat.service", rebind
        )
        self.assertIn(
            "systemctl enable --now hysteria2-panel-node-heartbeat.timer", rebind
        )
        self.assertNotIn("hysteria2-panel-node-hysteria-main.service", rebind)
        self.assertNotIn("hysteria2-panel-node-hysteria-udp443.service", rebind)
        for preserved in (
            "node.key",
            "node-public.der",
            "server.crt",
            "server.key",
            "spool",
        ):
            self.assertNotRegex(rebind + rollback, r"rm[^\n]*" + re.escape(preserved))
        self.assertIn("registration.json", rollback)
        self.assertIn("node_agent.py", rollback)
        self.assertNotIn("rm -r -- /var/lib/hysteria2-panel-node", rollback)

    def test_node_rebind_rollback_restores_registration_without_touching_spool(self):
        source = INSTALLER.read_text()
        start = source.index("rollback_node_rebind()")
        rollback = source[start:source.index("\n}\n", start) + 2]
        script = f"""
set -euo pipefail
{rollback}
REBIND_NODE_BACKUP_DIR="$WORK/backup"
NODE_AGENT_OPT_DIR="$WORK/opt"
NODE_AGENT_CONFIG_DIR="$WORK/config"
NODE_REBIND_TRANSACTION="$WORK/config/.rebind-transaction"
mkdir -p "$REBIND_NODE_BACKUP_DIR" "$NODE_AGENT_OPT_DIR" "$NODE_AGENT_CONFIG_DIR" "$WORK/state/spool"
printf 'old-agent\n' > "$REBIND_NODE_BACKUP_DIR/node_agent.py"
printf 'old-registration\n' > "$REBIND_NODE_BACKUP_DIR/registration.json"
(
  cd "$REBIND_NODE_BACKUP_DIR"
  sha256sum node_agent.py registration.json > manifest.sha256
)
printf 'new-agent\n' > "$NODE_AGENT_OPT_DIR/node_agent.py"
printf 'new-registration\n' > "$NODE_AGENT_CONFIG_DIR/registration.json"
printf 'pending-traffic\n' > "$WORK/state/spool/batch.json"
printf 'transaction\n' > "$NODE_REBIND_TRANSACTION"
durable_replace_file() {{
  command cp "$1" "$2"
  command chmod "$3" "$2"
}}
systemctl() {{ :; }}
sync() {{ :; }}
REBIND_NODE_MUTATED=1
rollback_node_rebind
printf '%s:%s:%s:%s\n' \
  "$(cat "$NODE_AGENT_OPT_DIR/node_agent.py")" \
  "$(cat "$NODE_AGENT_CONFIG_DIR/registration.json")" \
  "$(cat "$WORK/state/spool/batch.json")" \
  "$(test ! -e "$NODE_REBIND_TRANSACTION" && echo marker-cleared)"
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["bash"],
                input=script,
                text=True,
                capture_output=True,
                env={**os.environ, "WORK": directory},
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            "old-agent:old-registration:pending-traffic:marker-cleared",
            result.stdout,
        )

    def test_node_agent_activation_installs_only_a_sandboxed_heartbeat_timer(self):
        source = INSTALLER.read_text()
        start = source.index("activate_node_agent()")
        end = source.index("\n}\n", start) + 2
        activation = source[start:end]

        self.assertIn("--activate-node-agent", source)
        self.assertIn("hysteria2-panel-node-heartbeat.service", activation)
        self.assertIn("hysteria2-panel-node-heartbeat.timer", activation)
        self.assertIn('node_agent.py\" heartbeat', activation)
        self.assertIn("NoNewPrivileges=true", activation)
        self.assertIn("ProtectSystem=strict", activation)
        self.assertIn("PrivateDevices=true", activation)
        self.assertIn("CapabilityBoundingSet=", activation)
        self.assertIn("OnUnitActiveSec=60s", activation)
        self.assertIn("openssl pkey", activation)
        self.assertIn("sha256sum", activation)
        self.assertNotIn("configure_firewall", activation)
        self.assertNotIn("server.crt", activation)
        self.assertNotIn("HY2PANEL_HMAC_KEY", activation)
        self.assertNotIn("vpn.example.com", activation)

        dispatch = source.index('if (( ACTIVATE_NODE_AGENT == 1 )); then')
        full_install = source.index('\nacquire_maintenance_lock\n', dispatch)
        self.assertLess(dispatch, full_install)

    def test_ci_static_analysis_covers_the_standalone_node_agent(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        self.assertIn(
            "ruff check hysteria2_panel.py tcp_probe.py node_agent.py hy2panel",
            workflow,
        )
        self.assertIn(
            "bandit -q -r hysteria2_panel.py tcp_probe.py node_agent.py hy2panel",
            workflow,
        )

    def test_tag_ci_requires_the_tag_to_match_both_source_versions(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

        self.assertIn("Verify release tag matches source version", workflow)
        self.assertIn("if: startsWith(github.ref, 'refs/tags/')", workflow)
        self.assertIn("RELEASE_TAG: ${{ github.ref_name }}", workflow)
        self.assertIn('expected_tag = "v{}".format(panel_version)', workflow)
        self.assertIn("installer_version != panel_version", workflow)

    def test_installer_prompts_without_embedding_an_admin_password(self):
        source = INSTALLER.read_text()

        self.assertIn("read -r -s", source)
        self.assertNotRegex(source, r'ADMIN_PASSWORD="[^"$]{8,}"')
        self.assertIn("NODE_NAME", source)
        self.assertIn("PUBLIC_HOST", source)
        self.assertIn("PANEL_PUBLIC_HOST", source)
        self.assertIn("HYSTERIA_PORT", source)
        self.assertIn("PANEL_SCHEME", source)
        self.assertNotIn("--if-missing", source)

    def test_upgrade_preserves_existing_administrator_unless_reset_is_requested(self):
        source = INSTALLER.read_text()

        self.assertIn('RESET_ADMIN="${RESET_ADMIN:-0}"', source)
        self.assertIn('UPDATE_ADMIN=0', source)
        self.assertIn('保留当前管理员账号和密码', source)
        self.assertIn('if (( UPDATE_ADMIN == 1 )); then', source)

    def test_online_update_mode_requires_an_existing_managed_install_and_keeps_settings(self):
        source = INSTALLER.read_text()

        self.assertIn('AUTO_UPDATE="${HY2PANEL_AUTO_UPDATE:-0}"', source)
        self.assertIn('在线更新只允许用于现有的受管安装', source)
        self.assertIn(
            """detected_host="$(ip -4 -o addr show scope global 2>/dev/null | awk '{split($4,a,"/"); print a[1]; exit}')" || true""",
            source,
        )
        self.assertIn('NODE_NAME="${EXISTING_NODE_NAME}"', source)
        self.assertIn('PUBLIC_HOST="${EXISTING_PUBLIC_HOST}"', source)
        self.assertIn('HYSTERIA_PORT="${EXISTING_HYSTERIA_PORT}"', source)
        self.assertIn('PANEL_PORT="${EXISTING_PANEL_PORT}"', source)
        self.assertIn('PANEL_SCHEME="${EXISTING_PANEL_SCHEME}"', source)
        self.assertIn('PANEL_PUBLIC_HOST="${EXISTING_PANEL_PUBLIC_HOST}"', source)
        self.assertIn('EGRESS_POLICY="${EXISTING_EGRESS_POLICY}"', source)
        self.assertIn('RESET_ADMIN="0"', source)

    def test_upgrade_uses_existing_node_settings_as_prompt_defaults(self):
        source = INSTALLER.read_text()

        self.assertIn('EXISTING_INSTALL=1', source)
        self.assertIn('EXISTING_NODE_NAME="${HY2PANEL_NODE_NAME}"', source)
        self.assertIn('EXISTING_PUBLIC_HOST="${HY2PANEL_PUBLIC_HOST}"', source)
        self.assertIn('EXISTING_HYSTERIA_PORT="${HY2PANEL_HYSTERIA_PORT}"', source)
        self.assertIn('EXISTING_PANEL_PORT="${HY2PANEL_PANEL_PORT}"', source)
        self.assertIn('EXISTING_PANEL_SCHEME="${HY2PANEL_PANEL_SCHEME}"', source)
        self.assertIn(
            'EXISTING_PANEL_PUBLIC_HOST="${HY2PANEL_PANEL_PUBLIC_HOST:-}"',
            source,
        )
        self.assertIn('EXISTING_AUTH_PORT="${HY2PANEL_AUTH_PORT}"', source)
        self.assertIn('EXISTING_STATS_PORT="${HY2PANEL_STATS_PORT}"', source)
        self.assertIn("required_identity_variables=(", source)
        self.assertIn("为避免轮换节点身份", source)

    def test_installer_defaults_new_panels_to_https_without_migrating_existing_http(self):
        source = INSTALLER.read_text()

        self.assertIn('EXISTING_PANEL_SCHEME="https"', source)
        self.assertIn('PANEL_SCHEME="${PANEL_SCHEME:-${EXISTING_PANEL_SCHEME}}"', source)
        self.assertIn('管理面板:   HTTPS TCP 19998（可显式选择 HTTP）', source)
        self.assertIn('EXISTING_PANEL_SCHEME="${HY2PANEL_PANEL_SCHEME}"', source)
        self.assertIn('PANEL_SCHEME="${EXISTING_PANEL_SCHEME}"', source)
        self.assertIn('${PANEL_SCHEME}://${detected_host}:${PANEL_PORT}/', source)

    def test_https_uses_a_validated_panel_domain_and_never_the_node_certificate(self):
        source = INSTALLER.read_text()

        self.assertIn(
            'read -r -p "面板公网域名',
            source,
        )
        self.assertIn('PANEL_PUBLIC_HOST="${PANEL_PUBLIC_HOST,,}"', source)
        self.assertIn("validate_panel_public_host", source)
        self.assertIn(
            "HY2PANEL_PANEL_PUBLIC_HOST=${PANEL_PUBLIC_HOST}",
            source,
        )
        self.assertIn(
            "HY2PANEL_PANEL_TLS_CERT=${PANEL_CERT_FILE}",
            source,
        )
        self.assertIn(
            "HY2PANEL_PANEL_TLS_KEY=${PANEL_KEY_FILE}",
            source,
        )
        self.assertIn("HY2PANEL_TLS_CERT=${CERT_FILE}", source)
        self.assertIn("HY2PANEL_TLS_KEY=${KEY_FILE}", source)
        self.assertIn("cert: ${CERT_FILE}", source)
        self.assertIn("key: ${KEY_FILE}", source)

        acme_block = source.split("issue_panel_acme_certificate()", 1)[1].split(
            "\n}", 1
        )[0]
        self.assertNotIn("${CERT_FILE}", acme_block)
        self.assertNotIn("${KEY_FILE}", acme_block)
        self.assertNotIn("server.crt", acme_block)
        self.assertNotIn("server.key", acme_block)

    def test_https_uses_certbot_http01_and_a_panel_only_renewal_timer(self):
        source = INSTALLER.read_text()

        self.assertIn("certbot certonly", source)
        self.assertIn("--standalone", source)
        self.assertIn("--preferred-challenges http-01", source)
        self.assertIn('--cert-name "${PANEL_PUBLIC_HOST}"', source)
        self.assertIn('-d "${PANEL_PUBLIC_HOST}"', source)
        self.assertIn("--non-interactive", source)
        self.assertIn("--agree-tos", source)
        self.assertIn("--register-unsafely-without-email", source)
        self.assertIn("dnf install -y epel-release", source)
        self.assertIn("yum install -y epel-release", source)
        self.assertIn("-noout -checkhost", source)
        self.assertIn('chown root:hy2panel "${stage}"', source)
        self.assertIn('chmod 0750 "${stage}"', source)
        self.assertIn("hysteria2-panel-cert-renew.service", source)
        self.assertIn("hysteria2-panel-cert-renew.timer", source)
        self.assertIn("OnCalendar=*-*-* 03,15:00:00", source)
        self.assertIn("RandomizedDelaySec=1h", source)
        self.assertIn("Persistent=true", source)

        deploy_script = source.split(
            "cat > /opt/hysteria2-panel/acme-deploy.sh <<'EOF'", 1
        )[1].split("\nEOF", 1)[0]
        self.assertIn('previous_target="$(readlink "${PANEL_TLS_CURRENT}")"', deploy_script)
        self.assertIn('if ! systemctl restart hysteria2-panel.service; then', deploy_script)
        self.assertIn('ln -s "${previous_target}" "${rollback_link}"', deploy_script)
        self.assertNotIn("hysteria2-panel-server.service", deploy_script)
        self.assertNotIn("server.crt", deploy_script)
        self.assertNotIn("server.key", deploy_script)

        renew_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-cert-renew.service <<'EOF'",
            1,
        )[1].split("\nEOF", 1)[0]
        self.assertIn("/opt/hysteria2-panel/acme-renew.sh", renew_unit)
        self.assertIn("SupplementaryGroups=hy2panel", renew_unit)
        self.assertNotIn("hysteria2-panel-server.service", renew_unit)
        self.assertNotIn("server.crt", renew_unit)
        self.assertNotIn("server.key", renew_unit)

    def test_https_opens_http01_port_and_reports_the_acme_panel_address(self):
        source = INSTALLER.read_text()

        self.assertIn(
            '[[ "${PANEL_SCHEME}" != "https" ]] || FIREWALL_RULES+=("80/tcp")',
            source,
        )
        self.assertIn('ss -H -ltn "sport = :80"', source)
        self.assertIn(
            'echo "面板地址：${PANEL_SCHEME}://${PANEL_PUBLIC_HOST}:${PANEL_PORT}/"',
            source,
        )
        self.assertIn("云平台安全组还需持续放行 TCP 80 用于 ACME HTTP-01 续期", source)
        self.assertNotIn("首次打开自签名 HTTPS 地址", source)

    def test_https_fails_before_certbot_when_panel_dns_has_no_public_address(self):
        source = INSTALLER.read_text()
        start = source.index("preflight_panel_acme_dns()")
        end = source.index("\n\nissue_panel_acme_certificate()", start)
        helper = source[start:end]
        script = f"""
set -euo pipefail
{helper}
PYTHON_BIN={sys.executable!r}
PANEL_PUBLIC_HOST=panel-does-not-exist.invalid
fail() {{ printf 'FAIL:%s\n' "$*" >&2; exit 97; }}
preflight_panel_acme_dns
"""
        result = subprocess.run(
            ["bash"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(97, result.returncode)
        self.assertIn("DNS", result.stderr)
        acme = source.split("issue_panel_acme_certificate()", 1)[1].split(
            "\n}", 1
        )[0]
        self.assertLess(
            acme.index("preflight_panel_acme_dns"),
            acme.index("/usr/bin/certbot certonly"),
        )
        self.assertNotIn("PANEL_SCHEME=http", acme)

    def test_generated_acme_scripts_have_valid_shell_syntax(self):
        source = INSTALLER.read_text()

        for script_path in (
            "/opt/hysteria2-panel/acme-deploy.sh",
            "/opt/hysteria2-panel/acme-renew.sh",
        ):
            with self.subTest(script_path=script_path):
                marker = f"cat > {script_path} <<'EOF'"
                script = source.split(marker, 1)[1].split("\nEOF", 1)[0]
                result = subprocess.run(
                    ["bash", "-n"], input=script, capture_output=True, text=True
                )
                self.assertEqual(0, result.returncode, result.stderr)

    def test_installer_supports_debian_and_rhel_package_managers(self):
        source = INSTALLER.read_text()

        self.assertIn("install_system_dependencies", source)
        self.assertIn("apt-get install", source)
        self.assertIn("dnf install", source)
        self.assertIn("yum install", source)
        self.assertIn("/etc/os-release", source)
        self.assertIn("Python 3.8", source)
        self.assertIn("systemd", source)
        self.assertIn("PYTHON_BIN", source)
        required_commands = source.split("required_commands=(", 1)[1].split(")", 1)[0]
        for command in (
            "awk",
            "cat",
            "chmod",
            "chown",
            "cp",
            "date",
            "find",
            "grep",
            "id",
            "ip",
            "rm",
            "uname",
        ):
            self.assertIn(command, required_commands.split())

    def test_rhel_dependencies_preserve_minimal_package_variants(self):
        source = INSTALLER.read_text()
        function = source.split("install_system_dependencies() {", 1)[1].split(
            "\n}\n\nacquire_maintenance_lock()", 1
        )[0]

        self.assertIn("diffutils", function)
        self.assertIn('command -v curl >/dev/null 2>&1 || rhel_packages+=(curl)', function)
        self.assertIn('rhel_packages+=(coreutils)', function)
        self.assertNotIn("dnf install -y ca-certificates curl", function)
        self.assertNotIn("yum install -y ca-certificates curl", function)
        self.assertNotIn("python3 coreutils findutils", function)

    def test_verified_root_owned_hysteria_and_cosign_are_reused_before_download(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index('stage_verified_installed_binary()'):
            source.index('\n\nufw_rule_is_recorded()', source.index('stage_verified_installed_binary()'))
        ]

        self.assertIn("stat -c '%u:%g:%a:%h'", helper)
        self.assertIn('[[ ! -L "${installed_path}" && -f "${installed_path}" ]]', helper)
        self.assertIn('"${metadata}" =~ ^0:0:([0-7]{3,4}):1$', helper)
        self.assertIn('(( (8#${BASH_REMATCH[1]} & 022) == 0 ))', helper)
        self.assertIn('sha256sum --check --status', helper)
        self.assertIn('install -o root -g root -m 0755', helper)

        hysteria_reuse = source.index(
            'stage_verified_installed_binary \\\n  /opt/hysteria2-panel/bin/hysteria "${HYSTERIA_SHA256}" "${TMP_DIR}/hysteria"'
        )
        hysteria_download = source.index(
            'https://github.com/apernet/hysteria/releases/download', hysteria_reuse
        )
        cosign_reuse = source.index(
            'stage_verified_installed_binary \\\n  /opt/hysteria2-panel/bin/cosign "${COSIGN_SHA256}" "${TMP_DIR}/cosign"'
        )
        cosign_download = source.index(
            'https://github.com/sigstore/cosign/releases/download', cosign_reuse
        )
        self.assertLess(hysteria_reuse, hysteria_download)
        self.assertLess(cosign_reuse, cosign_download)

    def test_installer_is_namespaced_and_separates_service_identities(self):
        source = INSTALLER.read_text()

        self.assertIn("/opt/hysteria2-panel/bin/hysteria", source)
        self.assertIn("hysteria2-panel-server.service", source)
        self.assertNotIn("/etc/systemd/system/hysteria2.service", source)
        self.assertIn("User=hy2panel", source)
        self.assertIn("User=hy2server", source)
        self.assertIn("Group=hy2tls", source)

    def test_installer_adds_a_per_user_udp_443_entrypoint(self):
        source = INSTALLER.read_text()

        self.assertIn('DEFAULT_STATS_443_PORT=19995', source)
        self.assertIn('HY2PANEL_STATS_443_PORT=${STATS_443_PORT}', source)
        self.assertIn('/etc/hysteria2-panel/hysteria-443.yaml', source)
        self.assertIn('url: http://127.0.0.1:${AUTH_PORT}/auth/udp-443', source)
        self.assertIn('hysteria2-panel-server-443.service', source)
        self.assertIn('PartOf=hysteria2-panel-server.service', source)
        self.assertIn('Wants=hysteria2-panel-server-443.service', source)
        secondary_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-server-443.service <<'EOF'",
            1,
        )[1].split("\nEOF", 1)[0]
        self.assertIn('AmbientCapabilities=CAP_NET_BIND_SERVICE', secondary_unit)
        self.assertIn('CapabilityBoundingSet=CAP_NET_BIND_SERVICE', secondary_unit)
        self.assertGreaterEqual(source.count('AmbientCapabilities=CAP_NET_BIND_SERVICE'), 2)
        self.assertGreaterEqual(source.count('CapabilityBoundingSet=CAP_NET_BIND_SERVICE'), 2)
        self.assertIn('if (( HYSTERIA_PORT < 1024 || STATS_PORT < 1024 )); then', source)
        self.assertIn('if (( HYSTERIA_PORT < 1024 )); then', source)
        self.assertIn('ss -H -lun "sport = :443"', source)
        self.assertIn('云平台安全组还需放行 TCP/UDP 443', source)

    def test_installer_restarts_upgrades_and_configures_only_active_firewalls(self):
        source = INSTALLER.read_text()

        self.assertIn("systemctl restart hysteria2-panel.service", source)
        self.assertIn("systemctl restart hysteria2-panel-server.service", source)
        self.assertIn("configure_firewall()", source)
        self.assertIn('"${HYSTERIA_PORT}/tcp"', source)
        self.assertIn('"${HYSTERIA_PORT}/udp"', source)
        self.assertIn('"${PANEL_PORT}/tcp"', source)
        self.assertIn('"443/tcp" "443/udp"', source)
        self.assertIn("Status: active", source)
        self.assertIn('ufw allow "${rule}"', source)
        self.assertIn("firewall-cmd --state", source)
        self.assertIn('--query-port="${rule}"', source)
        self.assertIn('--permanent --zone="${zone}" --add-port="${rule}"', source)
        self.assertIn('--zone="${zone}" --add-port="${rule}"', source)
        self.assertIn("configure_firewall\n", source)
        self.assertNotIn("ufw enable", source)
        self.assertNotIn("systemctl enable --now firewalld", source)
        self.assertIn("未检测到正在生效的主机防火墙", source)
        self.assertIn("未受支持的自定义 nftables/iptables/ip6tables", source)
        self.assertIn(".managed-by-installer", source)

    def test_active_ufw_gets_every_public_service_port(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    awk '$1 == "ADD" {print "ufw allow " $2}' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "ADD 19999/tcp",
                "ADD 19999/udp",
                "ADD 19998/tcp",
                "ADD 443/tcp",
                "ADD 443/udp",
            ],
            calls,
        )

    def test_active_firewalld_is_idempotent_across_active_zones(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  state_file="${CAPTURE}.state"
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones")
      printf 'public\n  interfaces: eth0\ntrusted\n  sources: 192.0.2.0/24\n'
      ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      [[ -f "$state_file" ]] || return 1
      grep -Fqx -- "${*//--query-port=/--add-port=}" "$state_file" 2>/dev/null
      ;;
    *"--add-port="*)
      printf '%s\n' "$*" >> "$CAPTURE"
      printf '%s\n' "$*" >> "$state_file"
      ;;
    *) return 1 ;;
  esac
}
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(20, len(calls))
        for zone in ("public", "trusted"):
            for rule in ("19999/tcp", "19999/udp", "19998/tcp", "443/tcp", "443/udp"):
                self.assertTrue(
                    any(
                        f"--permanent --zone={zone} --add-port={rule}" in call
                        for call in calls
                    )
                )
                self.assertTrue(
                    any(
                        f"--zone={zone} --add-port={rule}" in call
                        and "--permanent" not in call
                        for call in calls
                    )
                )

    def test_firewalld_includes_default_zone_alongside_active_zones(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  state_file="${CAPTURE}.state"
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") printf 'docker\n  interfaces: docker0\n' ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      [[ -f "$state_file" ]] || return 1
      grep -Fqx -- "${*//--query-port=/--add-port=}" "$state_file" 2>/dev/null
      ;;
    *"--add-port="*)
      printf '%s\n' "$*" >> "$CAPTURE"
      printf '%s\n' "$*" >> "$state_file"
      ;;
    *) return 1 ;;
  esac
}
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        for zone in ("docker", "public"):
            self.assertTrue(any(f"--zone={zone} " in call for call in calls))

    def test_inactive_firewalls_leave_host_rules_untouched(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], calls)
        self.assertIn("未检测到正在生效的主机防火墙", result.stdout)

    def test_unmanaged_restrictive_input_firewall_fails_without_mutation(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() {
  printf '%s\n' '{"nftables":[' \
    '{"chain":{"family":"inet","table":"filter","name":"input","hook":"input","policy":"accept"}},' \
    '{"chain":{"family":"inet","table":"filter","name":"custom_input"}},' \
    '{"rule":{"family":"inet","table":"filter","chain":"input","expr":[{"jump":{"target":"custom_input"}}]}},' \
    '{"rule":{"family":"inet","table":"filter","chain":"custom_input","expr":[{"drop":null}]}}' \
    ']}'
}
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("未受支持的自定义 nftables/iptables/ip6tables", result.stderr)

    def test_forward_only_firewall_restrictions_do_not_trigger_input_failure(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() {
  printf '%s\n' '{"nftables":[' \
    '{"chain":{"family":"inet","table":"filter","name":"forward","hook":"forward","policy":"drop"}}' \
    ']}'
}
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], calls)

    def test_dual_active_firewall_managers_fail_before_any_write(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    awk '$1 == "ADD" {print "ufw allow " $2}' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'running\n'; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("UFW 与 firewalld 同时启用", result.stderr)

    def test_active_ufw_uses_manager_rules_without_rejecting_owned_raw_rules(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    awk '$1 == "ADD" {print "ufw allow " $2}' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { printf '%s\n' '*filter' ':INPUT DROP [0:0]' '-A INPUT -j ufw-before-input' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT DROP [0:0]' '-A INPUT -j ufw6-before-input' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(5, len(calls))

    def test_active_ufw_conflicting_deny_fails_before_writes(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    printf 'ufw insert 1 deny 19999/tcp\n'
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("UFW 已存在拒绝 19999/tcp", result.stderr)

    def test_active_ufw_protocol_agnostic_deny_fails_before_writes(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    printf 'ufw insert 1 deny 19999\n'
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("UFW 已存在拒绝 19999/tcp", result.stderr)

    def test_active_ufw_broad_inbound_deny_fails_before_writes(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    printf 'ufw insert 1 deny in from any to any\n'
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("UFW 已存在拒绝 19999/tcp", result.stderr)

    def test_active_ufw_range_list_and_limit_conflicts_fail_before_writes(self):
        for conflict in (
            "ufw deny in proto tcp from any to any port 19000:20000",
            "ufw reject 25,19999/tcp",
            "ufw limit 19999/tcp",
        ):
            with self.subTest(conflict=conflict):
                result, calls = self.run_firewall_function(
                    rf'''
ufw() {{
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    printf '%s\n' {conflict!r}
  fi
}}
firewall-cmd() {{ printf 'not running\n'; return 1; }}
nft() {{ return 2; }}
iptables-save() {{ :; }}
ip6tables-save() {{ :; }}
'''
                )

                self.assertEqual(97, result.returncode)
                self.assertEqual([], calls)
                self.assertIn("UFW 已存在拒绝 19999/tcp", result.stderr)

    def test_active_ufw_prepend_conflict_fails_before_writes(self):
        result, calls = self.run_firewall_function(
            r'''
MOCK_UFW_LISTENING=$'tcp:\n  19999 * (probe)\n   [ 1] deny 19999/tcp\n   [ 2] allow 19999/tcp\n'
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    printf 'ufw prepend deny 19999/tcp\n'
    awk '$1 == "ADD" {print "ufw allow " $2}' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("UFW 已存在拒绝 19999/tcp", result.stderr)

    def test_active_ufw_source_port_does_not_match_destination_port(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    printf 'ufw deny in proto tcp from any port 19999 to any port 25\n'
    awk '$1 == "ADD" {print "ufw allow " $2}' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(5, len(calls))

    def test_active_ufw_framework_customizations_fail_before_writes(self):
        for mode in ("rules", "hook"):
            with self.subTest(mode=mode):
                result, calls = self.run_firewall_function(
                    rf'''
MOCK_UFW_FRAMEWORK_MODE={mode!r}
ufw() {{
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    awk '$1 == "ADD" {{print "ufw allow " $2}}' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  fi
}}
firewall-cmd() {{ printf 'not running\n'; return 1; }}
nft() {{ return 2; }}
iptables-save() {{ :; }}
ip6tables-save() {{ :; }}
'''
                )

                self.assertEqual(97, result.returncode)
                self.assertEqual([], calls)
                self.assertIn("UFW framework", result.stderr)

    def test_active_ufw_unmanaged_live_rules_fail_before_writes(self):
        for mode in ("foreign-iptables", "foreign-nft"):
            with self.subTest(mode=mode):
                result, calls = self.run_firewall_function(
                    rf'''
MOCK_UFW_RAW_MODE={mode!r}
ufw() {{
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    awk '$1 == "ADD" {{print "ufw allow " $2}}' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  fi
}}
firewall-cmd() {{ printf 'not running\n'; return 1; }}
nft() {{ return 2; }}
iptables-save() {{ :; }}
ip6tables-save() {{ :; }}
'''
                )

                self.assertEqual(97, result.returncode)
                self.assertEqual([], calls)
                self.assertIn("UFW", result.stderr)

    def test_active_ufw_kernel_order_conflict_rolls_back_added_rules(self):
        result, calls = self.run_firewall_function(
            r'''
MOCK_UFW_LISTENING=$'tcp:\n  19999 * (probe)\n   [ 1] deny 19000:20000/tcp\n   [ 2] allow 19999/tcp\n  19998 * (panel)\n   [ 1] allow 19998/tcp\n  443 * (probe)\n   [ 1] allow 443/tcp\nudp:\n  19999 * (hysteria)\n   [ 1] allow 19999/udp\n  443 * (hysteria)\n   [ 1] allow 443/udp\n'
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    awk '
      $1 == "ADD" {added[$2] = 1}
      $1 == "DEL" {delete added[$2]}
      END {for (rule in added) print "ufw allow " rule}
    ' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual(5, len([call for call in calls if call.startswith("ADD ")]))
        self.assertEqual(5, len([call for call in calls if call.startswith("DEL ")]))
        self.assertIn("内核规则顺序无法证明", result.stderr)

    def test_active_ufw_ignores_unrelated_and_outbound_denies(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    printf 'ufw deny 25/tcp\nufw reject out from any to any\n'
    awk '$1 == "ADD" {print "ufw allow " $2}' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(5, len(calls))

    def test_active_ufw_deny_added_during_last_write_rolls_back_every_allow(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    awk '
      $1 == "ADD" {added[$2] = 1}
      $1 == "DEL" {delete added[$2]}
      END {for (rule in added) print "ufw allow " rule}
    ' "$CAPTURE" 2>/dev/null || true
    if grep -q '^ADD 443/udp$' "$CAPTURE" 2>/dev/null && \
      ! grep -q '^DEL 443/udp$' "$CAPTURE" 2>/dev/null; then
      printf 'ufw insert 1 deny in from any to any\n'
    fi
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual(5, len([call for call in calls if call.startswith("ADD ")]))
        self.assertEqual(5, len([call for call in calls if call.startswith("DEL ")]))
        self.assertIn("开放期间新增了拒绝 443/udp", result.stderr)

    def test_active_ufw_final_check_catches_removed_earlier_allow(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    count="$(awk '$1 == "SHOW" {count += 1} END {print count + 0}' "$CAPTURE" 2>/dev/null)"
    printf 'SHOW\n' >> "$CAPTURE"
    awk -v count="$count" '
      $1 == "ADD" {added[$2] = 1}
      $1 == "DEL" {delete added[$2]}
      END {for (rule in added) if (!(count >= 10 && rule == "19999/tcp")) print "ufw allow " rule}
    ' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertIn("最终检查未发现 19999/tcp", result.stderr)
        self.assertTrue(any(call.startswith("DEL ") for call in calls))

    def test_active_firewalld_uses_manager_rules_without_rejecting_owned_raw_rules(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  state_file="${CAPTURE}.state"
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") printf 'public\n  interfaces: eth0\n' ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      [[ -f "$state_file" ]] || return 1
      grep -Fqx -- "${*//--query-port=/--add-port=}" "$state_file"
      ;;
    *"--add-port="*) printf '%s\n' "$*" | tee -a "$CAPTURE" "$state_file" >/dev/null ;;
    *) return 1 ;;
  esac
}
nft() { return 2; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' '-A INPUT -j IN_public_allow' 'COMMIT'; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(10, len(calls))

    def test_active_firewalld_with_rich_rules_fails_before_writes(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") printf 'public\n  interfaces: eth0\n' ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*)
      printf 'rule priority="-100" port port="19999" protocol="tcp" reject\n'
      ;;
    *"--query-port="*) return 1 ;;
    *"--add-port="*) printf 'ADD %s\n' "$*" >> "$CAPTURE" ;;
    *) return 1 ;;
  esac
}
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("存在 rich rule", result.stderr)

    def test_active_firewalld_global_conflicts_fail_before_writes(self):
        for mode in (
            "panic",
            "chain",
            "quiet-chain",
            "direct",
            "passthrough",
            "policy",
            "raw",
            "untracked",
            "legacy-backend",
            "backend-error",
            "incomplete-direct",
            "help-error",
            "error",
        ):
            with self.subTest(mode=mode):
                result, calls = self.run_firewall_function(
                    rf'''
MOCK_FIREWALLD_GLOBAL_MODE={mode!r}
ufw() {{ printf 'Status: inactive\n'; }}
firewall-cmd() {{
  case "$*" in
    "--state") printf 'running\n' ;;
    *) return 1 ;;
  esac
}}
nft() {{ return 2; }}
iptables-save() {{ :; }}
ip6tables-save() {{ :; }}
'''
                )

                self.assertEqual(97, result.returncode)
                self.assertEqual([], calls)
                self.assertRegex(result.stderr, "全局策略|panic")

    def test_active_firewalld_without_policy_capability_remains_supported(self):
        result, calls = self.run_firewall_function(
            r'''
MOCK_FIREWALLD_GLOBAL_MODE=old
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  state_file="${CAPTURE}.state"
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") printf 'public\n  interfaces: eth0\n' ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      [[ -f "$state_file" ]] || return 1
      grep -Fqx -- "${*//--query-port=/--add-port=}" "$state_file" 2>/dev/null
      ;;
    *"--add-port="*)
      printf '%s\n' "$*" >> "$CAPTURE"
      printf '%s\n' "$*" >> "$state_file"
      ;;
    *) return 1 ;;
  esac
}
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(10, len(calls))

    def test_active_firewalld_allows_safe_or_disabled_host_policy(self):
        for mode in (
            "safe-policy",
            "disabled-policy",
            "quiet-output",
            "permanent-target",
        ):
            with self.subTest(mode=mode):
                result, calls = self.run_firewall_function(
                    r'''
MOCK_FIREWALLD_GLOBAL_MODE=__MODE__
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  state_file="${CAPTURE}.state"
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") printf 'public\n  interfaces: eth0\n' ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      [[ -f "$state_file" ]] || return 1
      grep -Fqx -- "${*//--query-port=/--add-port=}" "$state_file" 2>/dev/null
      ;;
    *"--add-port="*)
      printf '%s\n' "$*" >> "$CAPTURE"
      printf '%s\n' "$*" >> "$state_file"
      ;;
    *) return 1 ;;
  esac
}
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''.replace("__MODE__", mode)
                )

                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(10, len(calls))

    def test_ipv6_custom_input_policy_fails_closed(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() {
  printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' ':CUSTOM - [0:0]' \
    '-A INPUT -j CUSTOM' '-A CUSTOM -j DROP' 'COMMIT'
}
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("未受支持的自定义 nftables/iptables/ip6tables", result.stderr)

    def test_firewall_inspection_error_fails_closed(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { return 1; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("无法完整检查", result.stderr)

    def test_malformed_nft_json_shape_fails_closed(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '[]'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("无法完整检查", result.stderr)

    def test_empty_iptables_compatibility_views_are_clean(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { :; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], calls)
        self.assertIn("未检测到正在生效的主机防火墙", result.stdout)

    def test_nonempty_malformed_iptables_output_fails_closed(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' 'unexpected output'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("无法完整检查", result.stderr)

    def test_iptables_prerouting_rules_in_other_tables_fail_closed(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() {
  printf '%s\n' '*raw' ':PREROUTING ACCEPT [0:0]' \
    '-A PREROUTING -p tcp --dport 19999 -j DROP' 'COMMIT' \
    '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'
}
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("未受支持的自定义", result.stderr)

    def test_iptables_input_rules_in_security_table_fail_closed(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() {
  printf '%s\n' '*security' ':INPUT ACCEPT [0:0]' '-A INPUT -j DROP' 'COMMIT' \
    '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'
}
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("未受支持的自定义", result.stderr)

    def test_firewall_rule_drift_is_recomputed_before_writes(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  state_file="${CAPTURE}.state"
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    count="$(awk '$1 == "SHOW" {count += 1} END {print count + 0}' "$CAPTURE" 2>/dev/null)"
    printf 'SHOW\n' >> "$CAPTURE"
    if (( count == 0 )); then
      printf 'ufw allow 19999/tcp\n'
    fi
    [[ ! -f "$state_file" ]] || awk '{print "ufw allow " $1}' "$state_file"
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
    printf '%s\n' "$2" >> "$state_file"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("ADD 19999/tcp", calls)

    def test_firewalld_zone_drift_is_recomputed_before_writes(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  state_file="${CAPTURE}.state"
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones")
      count="$(awk '$1 == "ZONES" {count += 1} END {print count + 0}' "$CAPTURE" 2>/dev/null)"
      printf 'ZONES\n' >> "$CAPTURE"
      if (( count == 0 )); then printf 'public\n  interfaces: eth0\n'; else printf 'dmz\n  interfaces: eth0\n'; fi
      ;;
    "--get-default-zone") printf 'dmz\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      [[ -f "$state_file" ]] || return 1
      grep -Fqx -- "${*//--query-port=/--add-port=}" "$state_file" 2>/dev/null
      ;;
    *"--add-port="*)
      printf '%s\n' "$*" >> "$CAPTURE"
      printf '%s\n' "$*" >> "$state_file"
      ;;
    *) return 1 ;;
  esac
}
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        additions = [call for call in calls if "--add-port=" in call]
        self.assertTrue(additions)
        self.assertTrue(all("--zone=dmz" in call for call in additions))

    def test_firewalld_zone_drift_during_writes_rolls_back(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  state_file="${CAPTURE}.state"
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones")
      count="$(awk '$1 == "ZONES" {count += 1} END {print count + 0}' "$CAPTURE" 2>/dev/null)"
      printf 'ZONES\n' >> "$CAPTURE"
      if (( count < 2 )); then printf 'public\n  interfaces: eth0\n'; else printf 'dmz\n  interfaces: eth0\n'; fi
      ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      [[ -f "$state_file" ]] || return 1
      grep -Fqx -- "${*//--query-port=/--add-port=}" "$state_file" 2>/dev/null
      ;;
    *"--add-port="*)
      printf 'ADD %s\n' "$*" >> "$CAPTURE"
      printf '%s\n' "$*" >> "$state_file"
      ;;
    *"--remove-port="*) printf 'DEL %s\n' "$*" >> "$CAPTURE" ;;
    *) return 1 ;;
  esac
}
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertTrue(any(call.startswith("ADD ") for call in calls))
        self.assertTrue(any(call.startswith("DEL ") for call in calls))
        self.assertIn("区域在开放期间发生变化", result.stderr)

    def test_firewalld_final_check_catches_removed_earlier_port(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  state_file="${CAPTURE}.state"
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") printf 'public\n  interfaces: eth0\n' ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      query_count="$(awk '$1 == "QUERY" {count += 1} END {print count + 0}' "$CAPTURE" 2>/dev/null)"
      printf 'QUERY\n' >> "$CAPTURE"
      if (( query_count >= 30 )) && [[ "$*" == *"--query-port=19999/tcp" ]]; then
        return 1
      fi
      [[ -f "$state_file" ]] || return 1
      grep -Fqx -- "${*//--query-port=/--add-port=}" "$state_file" 2>/dev/null
      ;;
    *"--add-port="*)
      printf 'ADD %s\n' "$*" >> "$CAPTURE"
      printf '%s\n' "$*" >> "$state_file"
      ;;
    *"--remove-port="*) printf 'DEL %s\n' "$*" >> "$CAPTURE" ;;
    *) return 1 ;;
  esac
}
nft() { return 2; }
iptables-save() { :; }
ip6tables-save() { :; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertIn("最终检查未发现", result.stderr)
        self.assertTrue(any(call.startswith("DEL ") for call in calls))

    def test_firewalld_active_zone_query_error_fails_before_writes(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") return 2 ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--query-port="*) return 1 ;;
    *"--add-port="*) printf 'ADD %s\n' "$*" >> "$CAPTURE" ;;
    *) return 1 ;;
  esac
}
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertFalse(any(call.startswith("ADD ") for call in calls))
        self.assertIn("无法读取 firewalld 活跃或默认区域", result.stderr)

    def test_nft_prerouting_rules_are_treated_as_unmanaged_restrictions(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() { printf 'not running\n'; return 1; }
nft() {
  printf '%s\n' '{"nftables":[' \
    '{"chain":{"family":"inet","table":"filter","name":"prerouting","hook":"prerouting","policy":"accept"}},' \
    '{"rule":{"family":"inet","table":"filter","chain":"prerouting","expr":[{"drop":null}]}}' \
    ']}'
}
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("未受支持的自定义", result.stderr)

    def test_firewall_manager_status_errors_stop_before_writes(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { return 2; }
firewall-cmd() { printf 'running\n'; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual([], calls)
        self.assertIn("无法查询 UFW 状态", result.stderr)

    def test_ufw_partial_failure_removes_only_rules_added_by_this_run(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    awk '$1 == "ADD" {print "ufw allow " $2}' "$CAPTURE" 2>/dev/null || true
  elif [[ "$1" == "allow" ]]; then
    [[ "$2" != "19998/tcp" ]] || return 1
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual(
            [
                "ADD 19999/tcp",
                "ADD 19999/udp",
                "DEL 19998/tcp",
                "DEL 19999/udp",
                "DEL 19999/tcp",
            ],
            calls,
        )

    def test_ufw_applied_but_nonzero_write_is_still_rolled_back(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    [[ -f "$CAPTURE" ]] && return 2
    return 0
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
    return 1
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual(["ADD 19999/tcp", "DEL 19999/tcp"], calls)

    def test_ufw_success_without_recorded_postcondition_rolls_back(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() {
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    return 0
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual(["ADD 19999/tcp", "DEL 19999/tcp"], calls)

    def test_firewalld_success_without_query_postcondition_rolls_back(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") printf 'public\n  interfaces: eth0\n' ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*) return 1 ;;
    *"--remove-port="*) printf 'DEL %s\n' "$*" >> "$CAPTURE" ;;
    *"--add-port="*) printf 'ADD %s\n' "$*" >> "$CAPTURE" ;;
    *) return 1 ;;
  esac
}
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual(2, len(calls))
        self.assertTrue(calls[0].startswith("ADD "))
        self.assertTrue(calls[1].startswith("DEL "))

    def test_firewalld_partial_failure_removes_runtime_and_permanent_additions(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  state_file="${CAPTURE}.state"
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") printf 'public\n  interfaces: eth0\n' ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      [[ -f "$state_file" ]] || return 1
      grep -Fqx -- "${*//--query-port=/--add-port=}" "$state_file" 2>/dev/null
      ;;
    *"--remove-port="*) printf 'DEL %s\n' "$*" >> "$CAPTURE" ;;
    *"--add-port="*)
      count="$(awk '$1 == "ADD" {count += 1} END {print count + 0}' "$CAPTURE" 2>/dev/null)"
      (( count < 2 )) || return 1
      printf 'ADD %s\n' "$*" >> "$CAPTURE"
      printf '%s\n' "$*" >> "$state_file"
      ;;
    *) return 1 ;;
  esac
}
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual(5, len(calls))
        self.assertTrue(calls[0].startswith("ADD "))
        self.assertTrue(calls[1].startswith("ADD "))
        self.assertTrue(calls[2].startswith("DEL "))
        self.assertTrue(calls[3].startswith("DEL "))
        self.assertTrue(calls[4].startswith("DEL "))

    def test_firewalld_applied_but_nonzero_write_is_still_rolled_back(self):
        result, calls = self.run_firewall_function(
            r'''
ufw() { printf 'Status: inactive\n'; }
firewall-cmd() {
  case "$*" in
    "--state") printf 'running\n' ;;
    "--get-active-zones") printf 'public\n  interfaces: eth0\n' ;;
    "--get-default-zone") printf 'public\n' ;;
    *"--list-rich-rules"*) : ;;
    *"--query-port="*)
      if [[ -f "$CAPTURE" ]] && ! grep -q '^DEL ' "$CAPTURE"; then
        return 2
      fi
      return 1
      ;;
    *"--remove-port="*) printf 'DEL %s\n' "$*" >> "$CAPTURE" ;;
    *"--add-port="*)
      printf 'ADD %s\n' "$*" >> "$CAPTURE"
      return 1
      ;;
    *) return 1 ;;
  esac
}
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(97, result.returncode)
        self.assertEqual(2, len(calls))
        self.assertTrue(calls[0].startswith("ADD "))
        self.assertTrue(calls[1].startswith("DEL "))

    def test_firewall_port_migration_adds_new_rules_before_removing_only_owned_old_rules(self):
        result, calls = self.run_firewall_function(
            r'''
printf '%s\n' \
  'ufw||18888/tcp' \
  'ufw||18888/udp' \
  'ufw||18887/tcp' > "$MANAGED_FIREWALL_STATE_FILE"
chmod 0600 "$MANAGED_FIREWALL_STATE_FILE"
printf '%s\n' \
  '18888/tcp' \
  '18888/udp' \
  '18887/tcp' \
  '17777/tcp' > "${CAPTURE}.ufw-state"
ufw() {
  state_file="${CAPTURE}.ufw-state"
  if [[ "$1" == "status" ]]; then
    printf 'Status: active\n'
  elif [[ "$1 $2" == "show added" ]]; then
    awk '{print "ufw allow " $1}' "$state_file"
  elif [[ "$1" == "allow" ]]; then
    printf 'ADD %s\n' "$2" >> "$CAPTURE"
    grep -Fxq -- "$2" "$state_file" || printf '%s\n' "$2" >> "$state_file"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    printf 'DEL %s\n' "$4" >> "$CAPTURE"
    awk -v removed="$4" '$0 != removed' "$state_file" > "${state_file}.new"
    mv "${state_file}.new" "$state_file"
  fi
}
firewall-cmd() { printf 'not running\n'; return 1; }
nft() { printf '%s\n' '{"nftables":[]}'; }
iptables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        additions = [index for index, call in enumerate(calls) if call.startswith("ADD ")]
        deletions = [index for index, call in enumerate(calls) if call.startswith("DEL ")]
        self.assertEqual(5, len(additions))
        self.assertEqual(3, len(deletions))
        self.assertLess(max(additions), min(deletions))
        self.assertEqual(
            {"DEL 18888/tcp", "DEL 18888/udp", "DEL 18887/tcp"},
            {calls[index] for index in deletions},
        )
        self.assertNotIn("DEL 17777/tcp", calls)

    def test_firewall_ownership_and_crash_rollback_are_durable(self):
        source = INSTALLER.read_text()

        self.assertIn(
            'MANAGED_FIREWALL_STATE_FILE=/etc/hysteria2-panel/managed-firewall.rules',
            source,
        )
        self.assertIn(
            'FIREWALL_TRANSACTION_FILE=/etc/hysteria2-panel/.firewall-transaction',
            source,
        )
        self.assertIn('load_managed_firewall_state()', source)
        self.assertIn('record_firewall_transaction_operation()', source)
        self.assertIn('rollback_persisted_firewall_transaction()', source)
        self.assertIn('remove_obsolete_managed_firewall_rules()', source)
        ufw_record = source.index('record_firewall_transaction_operation add "ufw||${rule}"')
        ufw_write = source.index('ufw allow "${rule}"', ufw_record)
        self.assertLess(ufw_record, ufw_write)
        remove_start = source.index('remove_obsolete_managed_firewall_rules')
        self.assertGreater(remove_start, source.index('ufw_listeners_are_allowed'))
        self.assertIn('finalize_firewall_transaction', source)
        self.assertGreater(
            source.rindex('\nfinalize_firewall_transaction\n'),
            source.rindex('clear_upgrade_transaction'),
        )

    def test_firewall_finalize_fsync_failure_replays_the_in_memory_journal(self):
        source = INSTALLER.read_text()
        start = source.index("ufw_rule_is_recorded()")
        end = source.index("\n\noptimize_network_stack()", start)
        firewall_functions = source[start:end]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transaction = root / "transaction"
            managed = root / "managed"
            ufw_state = root / "ufw-state"
            transaction.write_text(
                "HYSTERIA2_PANEL_FIREWALL_TRANSACTION_V1\n"
                "old|ufw||18888/tcp\n"
                "add|ufw||19999/tcp\n"
                "remove|ufw||18888/tcp\n"
            )
            managed.write_text("ufw||19999/tcp\n")
            ufw_state.write_text("19999/tcp\n")
            transaction.chmod(0o600)
            managed.chmod(0o600)
            script = f"""
set -Eeuo pipefail
{firewall_functions}
FIREWALL_TRANSACTION_FILE={str(transaction)!r}
MANAGED_FIREWALL_STATE_FILE={str(managed)!r}
FIREWALL_TRANSACTION_MAGIC=HYSTERIA2_PANEL_FIREWALL_TRANSACTION_V1
FIREWALL_TRANSACTION_LINES=()
FIREWALL_APPLIED=("ufw||19999/tcp")
FIREWALL_OWNED=()
FIREWALL_NEWLY_OWNED=()
UFW_ADDED_RULES=""
FAIL_FINALIZE_SYNC=1
durable_replace_file() {{
  install -m "$3" "$1" "$2.new"
  mv "$2.new" "$2"
}}
durable_remove_file() {{
  if [[ "$1" == "${{FIREWALL_TRANSACTION_FILE}}" && "${{FAIL_FINALIZE_SYNC}}" == 1 ]]; then
    rm -f -- "$1"
    FAIL_FINALIZE_SYNC=0
    return 1
  fi
  rm -f -- "$1"
}}
ufw() {{
  state={str(ufw_state)!r}
  if [[ "$1 $2" == "show added" ]]; then
    awk '{{print "ufw allow " $1}}' "$state"
  elif [[ "$1" == "allow" ]]; then
    grep -Fxq -- "$2" "$state" || printf '%s\\n' "$2" >> "$state"
  elif [[ "$1 $2 $3" == "--force delete allow" ]]; then
    awk -v removed="$4" '$0 != removed' "$state" > "$state.new"
    mv "$state.new" "$state"
  fi
}}
if finalize_firewall_transaction; then
  exit 91
fi
[[ ! -e "${{FIREWALL_TRANSACTION_FILE}}" ]]
rollback_firewall_changes
"""
            result = subprocess.run(
                ["bash"], input=script, capture_output=True, text=True
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("ufw||18888/tcp\n", managed.read_text())
            self.assertEqual("18888/tcp\n", ufw_state.read_text())
            self.assertFalse(transaction.exists())

    def test_failed_upgrade_automatically_rolls_back_node_identity_and_runtime(self):
        source = INSTALLER.read_text()

        self.assertIn("rollback_existing_install()", source)
        self.assertIn('ROLLBACK_REQUIRED=1', source)
        self.assertIn('rollback_existing_install "${status}"', source)
        self.assertIn('(( ${#FIREWALL_APPLIED[@]} > 0 ))', source)
        self.assertIn("restore_managed_directory()", source)
        self.assertIn(
            'restore_managed_directory "${BACKUP_DIR}/opt" /opt/hysteria2-panel',
            source,
        )
        self.assertIn(
            'restore_managed_directory "${BACKUP_DIR}/etc" /etc/hysteria2-panel',
            source,
        )
        self.assertNotIn("rm -r -- /opt/hysteria2-panel", source)
        self.assertNotIn("rm -r -- /etc/hysteria2-panel", source)
        verifier = source[
            source.index("verify_recovered_upgrade()") : source.index(
                "\n\nprune_automatic_backups()"
            )
        ]
        self.assertLess(
            verifier.index("systemctl restart hysteria2-panel.service"),
            verifier.index("verify_rollback_recovery"),
        )
        recovery_health = source[
            source.index("verify_rollback_recovery()") : source.index(
                "\n\nrollback_existing_install()"
            )
        ]
        self.assertIn(
            '"${HY2PANEL_PANEL_SCHEME}://127.0.0.1:${HY2PANEL_PANEL_PORT}/healthz"',
            recovery_health,
        )
        self.assertNotIn("/readyz", recovery_health)
        self.assertIn(
            'wait_for_listener udp "${HY2PANEL_HYSTERIA_PORT}"', recovery_health
        )
        self.assertIn(
            'wait_for_listener tcp "${HY2PANEL_HYSTERIA_PORT}"', recovery_health
        )
        self.assertIn('wait_for_listener udp 443', recovery_health)
        self.assertIn('wait_for_listener tcp 443', recovery_health)
        self.assertEqual(
            2, recovery_health.count("verify_backed_up_runtime_units_active")
        )
        self.assertLess(
            recovery_health.rindex("wait_for_listener"),
            recovery_health.rindex("verify_backed_up_runtime_units_active"),
        )
        unit_check = source[
            source.index("verify_backed_up_runtime_units_active()") : source.index(
                "\n\nverify_rollback_recovery()"
            )
        ]
        for unit in (
            "hysteria2-panel.service",
            "hysteria2-panel-server.service",
            "hysteria2-panel-tcp-probe.service",
            "hysteria2-panel-server-443.service",
            "hysteria2-panel-tcp-probe-443.service",
        ):
            with self.subTest(unit=unit):
                self.assertIn(unit, unit_check)
        listener_wait = source[
            source.index("wait_for_listener()") : source.index(
                "\n\nwait_for_health()"
            )
        ]
        self.assertIn("for _attempt in {1..30}", listener_wait)
        self.assertIn(
            'listener_output="$(ss "${socket_options[@]}" "sport = :${port_number}")"',
            listener_wait,
        )
        listener_result = subprocess.run(
            ["bash"],
            input=(
                "set -euo pipefail\n"
                + listener_wait
                + "\nss() { [[ \"$*\" == *\"sport = :443\"* ]] || return 3; "
                + "awk 'BEGIN { for (i = 0; i < 100000; i++) print \"listener\" }'; }\n"
                + "sleep() { :; }\n"
                + "wait_for_listener tcp 0443\n"
            ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, listener_result.returncode, listener_result.stderr)
        self.assertIn("--timer-property=AccuracySec=1s", source)
        self.assertIn('preserve_or_restore_database', source)
        self.assertIn('rm -f -- "${database_path}-wal" "${database_path}-shm"', source)
        self.assertIn('sync-traffic', source)
        self.assertIn('TRAFFIC_SYNC_OPTIONS+=(--primary-only)', source)
        self.assertIn('TRAFFIC_SYNC_OPTIONS+=(--secondary-only)', source)
        self.assertIn('systemctl is-active --quiet hysteria2-panel-server-443.service', source)
        self.assertIn('source "${BACKUP_DIR}/etc/panel.env"', source)
        self.assertIn('stop_loaded_units', source)
        self.assertIn('checkpoint_database /var/lib/hysteria2-panel/panel.db', source)
        self.assertIn('hysteria2-panel-restore-recover.service', source)
        self.assertIn('hysteria2-panel-restore-resume.wants', source)
        self.assertIn('systemctl disable hysteria2-panel-restore-resume.service', source)
        self.assertIn('/etc/systemd/system/multi-user.target.wants/hysteria2-panel-restore-resume.service', source)
        configure = source.rindex("configure_firewall\n")
        marker = source.index(
            'durable_replace_file /dev/null "${MANAGED_MARKER}" 0644',
            configure,
        )
        clear = source.index("clear_upgrade_transaction", marker)
        committed = source.index("INSTALL_COMMITTED=1", clear)
        rollback_disabled = source.index("ROLLBACK_REQUIRED=0", committed)
        self.assertLess(configure, marker)
        self.assertLess(marker, clear)
        self.assertLess(clear, committed)
        self.assertLess(committed, rollback_disabled)
        self.assertLess(source.index('ROLLBACK_REQUIRED=1'), source.rindex('\noptimize_network_stack\n'))
        self.assertLess(source.index('面板端口未监听'), source.rindex('ROLLBACK_REQUIRED=0'))

    def test_installer_exit_finalizer_rolls_back_once_on_error_and_signals(self):
        source = INSTALLER.read_text()
        self.assertTrue(source.startswith("#!/usr/bin/env bash\n# Deliberately omit errtrace"))
        self.assertIn("\nset -euo pipefail\n", source[:500])
        self.assertNotIn("\nset -Eeuo pipefail\n", source[:500])
        for mode, expected_status, expected_calls in (
            ("error", 1, ["rollback:1"]),
            ("error7", 7, ["rollback:7"]),
            ("error-cleanup-fail", 1, ["rollback:1"]),
            ("hup", 129, ["rollback:129"]),
            ("int", 130, ["rollback:130"]),
            ("term", 143, ["rollback:143"]),
            ("subshell", 1, ["rollback:1"]),
            ("command-substitution", 1, ["rollback:1"]),
            ("pipeline", 1, ["rollback:1"]),
            ("repeat-signal", 1, ["rollback:1"]),
            ("cleanup-fail", 1, []),
            ("committed", 143, []),
        ):
            with self.subTest(mode=mode):
                result, calls, temporary_exists = self.run_installer_finalizer(mode)
                self.assertEqual(expected_status, result.returncode, result.stderr)
                self.assertEqual(expected_calls, calls)
                self.assertEqual(mode in {"cleanup-fail", "error-cleanup-fail"}, temporary_exists)

    def test_stopping_upgrade_units_skips_absent_optional_443_services(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index("stop_loaded_units()") : source.index(
                "\n\nrollback_existing_install()"
            )
        ]
        script = f"""
set -euo pipefail
{helper}
systemctl() {{
  if [[ "$1" == "show" && "$*" == *"--property=LoadState"* ]]; then
    [[ "${{@: -1}}" != "hysteria2-panel-server-443.service" ]] || {{ printf 'not-found\n'; return 0; }}
    printf 'loaded\n'
    return 0
  fi
  if [[ "$1" == "show" && "$*" == *"--property=ActiveState"* ]]; then
    printf 'inactive\n'
    return 0
  fi
  if [[ "$1" == "stop" ]]; then
    printf 'STOP:%s\n' "$2" >> "$CAPTURE"
    return 0
  fi
  return 2
}}
stop_loaded_units hysteria2-panel-server-443.service hysteria2-panel-server.service
"""
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "calls"
            result = subprocess.run(
                ["bash"],
                input=script,
                capture_output=True,
                text=True,
                env={**os.environ, "CAPTURE": str(capture)},
            )
            calls = capture.read_text().splitlines() if capture.exists() else []

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], calls)

    def test_stopping_upgrade_units_stops_not_found_but_still_active_processes(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index("stop_loaded_units()") : source.index(
                "\n\nstop_panel_preserving_hysteria()"
            )
        ]
        script = f"""
set -euo pipefail
{helper}
systemctl() {{
  if [[ "$1" == "show" && "$*" == *"--property=LoadState"* ]]; then
    printf 'not-found\n'
    return 0
  fi
  if [[ "$1" == "show" && "$*" == *"--property=ActiveState"* ]]; then
    cat "$STATE_FILE"
    return 0
  fi
  if [[ "$1" == "stop" ]]; then
    printf 'STOP:%s\n' "$2" >> "$CAPTURE"
    printf 'inactive\n' > "$STATE_FILE"
    return 0
  fi
  return 2
}}
stop_loaded_units hysteria2-panel-server-443.service
"""
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "calls"
            state_file = Path(directory) / "state"
            state_file.write_text("active\n")
            result = subprocess.run(
                ["bash"],
                input=script,
                capture_output=True,
                text=True,
                env={**os.environ, "CAPTURE": str(capture), "STATE_FILE": str(state_file)},
            )
            calls = capture.read_text().splitlines() if capture.exists() else []

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["STOP:hysteria2-panel-server-443.service"], calls)

    def test_traffic_sync_endpoint_selection_handles_every_partial_stop_state(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index("select_traffic_sync_options()") : source.index(
                "\n\nrollback_firewall_after_service_recovery()"
            )
        ]
        script = f"""
set -u
{helper}
systemctl() {{
  [[ "$1" == "show" ]] || return 2
  case "${{@: -1}}" in
    hysteria2-panel-server.service) [[ "$PRIMARY" != error ]] || return 2; printf '%s\n' "$PRIMARY" ;;
    hysteria2-panel-server-443.service) [[ "$SECONDARY" != error ]] || return 2; printf '%s\n' "$SECONDARY" ;;
    *) return 2 ;;
  esac
}}
select_traffic_sync_options
status=$?
printf 'status=%s options=%s\n' "$status" "${{TRAFFIC_SYNC_OPTIONS[*]-}}"
exit "$status"
"""
        for primary, secondary, status, options in (
            ("active", "active", 0, ""),
            ("active", "inactive", 0, "--primary-only"),
            ("inactive", "active", 0, "--secondary-only"),
            ("inactive", "inactive", 1, ""),
            ("error", "inactive", 2, ""),
        ):
            with self.subTest(primary=primary, secondary=secondary):
                result = subprocess.run(
                    ["bash"],
                    input=script,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PRIMARY": primary, "SECONDARY": secondary},
                )
                self.assertEqual(status, result.returncode, result.stderr)
                self.assertIn(f"status={status} options={options}", result.stdout)

    def test_panel_signal_shutdown_preserves_running_hysteria_services(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index("stop_panel_preserving_hysteria()") : source.index(
                "\n\nselect_traffic_sync_options()"
            )
        ]
        script = f"""
set -euo pipefail
{helper}
systemctl() {{
  if [[ "$1" == "show" && "$*" == *"--property=ActiveState"* ]]; then
    case "${{@: -1}}" in
      hysteria2-panel.service) cat "$STATE_FILE" ;;
      hysteria2-panel-server.service) printf 'active\n' ;;
      hysteria2-panel-server-443.service) printf 'inactive\n' ;;
      *) return 2 ;;
    esac
    return 0
  fi
  if [[ "$1" == "kill" ]]; then
    printf 'KILL:%s\n' "$*" >> "$CAPTURE"
    printf 'inactive\n' > "$STATE_FILE"
    return 0
  fi
  if [[ "$1" == "is-active" ]]; then
    [[ "${{@: -1}}" == hysteria2-panel-server.service ]]
    return
  fi
  return 2
}}
sleep() {{ :; }}
stop_panel_preserving_hysteria
"""
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "calls"
            state_file = Path(directory) / "state"
            state_file.write_text("active\n")
            result = subprocess.run(
                ["bash"],
                input=script,
                capture_output=True,
                text=True,
                env={**os.environ, "CAPTURE": str(capture), "STATE_FILE": str(state_file)},
            )
            calls = capture.read_text().splitlines() if capture.exists() else []

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "KILL:kill --kill-who=main --signal=SIGTERM hysteria2-panel.service"
            ],
            calls,
        )

    def test_database_rollback_keeps_a_valid_newer_database(self):
        result = self.run_database_rollback_helper(
            r'''
"$PYTHON_BIN" - "$database" "$snapshot" <<'PY'
import sqlite3
import sys
for path, value in zip(sys.argv[1:], ("latest", "snapshot")):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE state(value TEXT)")
        connection.execute("INSERT INTO state VALUES (?)", (value,))
PY
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("latest", result.stdout.strip())

    def test_database_rollback_removes_wal_sidecars_and_restores_corrupt_database(self):
        result = self.run_database_rollback_helper(
            r'''
"$PYTHON_BIN" - "$snapshot" <<'PY'
import sqlite3
import sys
with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute("CREATE TABLE state(value TEXT)")
    connection.execute("INSERT INTO state VALUES ('snapshot')")
PY
printf 'not sqlite' > "$database"
printf 'stale wal' > "$database-wal"
printf 'stale shm' > "$database-shm"
'''
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("snapshot", result.stdout.strip())

    def test_database_checkpoint_succeeds_when_wal_is_not_busy(self):
        result = self.run_checkpoint_helper()

        self.assertEqual(0, result.returncode, result.stderr)

    def test_database_checkpoint_fails_when_a_reader_keeps_wal_busy(self):
        result = self.run_checkpoint_helper(
            r'''
"$PYTHON_BIN" - "$database" "$WORK/reader-ready" <<'PY' &
import pathlib
import sqlite3
import sys
import time
connection = sqlite3.connect(sys.argv[1])
connection.execute("BEGIN")
connection.execute("SELECT * FROM state").fetchall()
pathlib.Path(sys.argv[2]).touch()
time.sleep(10)
PY
reader_pid=$!
for _attempt in {1..100}; do
  [[ ! -e "$WORK/reader-ready" ]] || break
  sleep 0.01
done
trap 'kill "$reader_pid" 2>/dev/null || true; wait "$reader_pid" 2>/dev/null || true' EXIT
"$PYTHON_BIN" - "$database" <<'PY'
import sqlite3
import sys
with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute("INSERT INTO state VALUES ('after-reader')")
PY
'''
        )

        self.assertNotEqual(0, result.returncode)

    def test_successful_upgrade_settles_traffic_again_before_stopping_hysteria(self):
        source = INSTALLER.read_text()
        final_sync = source.rindex("sync-traffic --quiesce")
        stop_old_server = source.index(
            '|| fail "无法停止旧 Hysteria 服务', final_sync
        )
        final_checkpoint = source.index(
            "checkpoint_database /var/lib/hysteria2-panel/panel.db", stop_old_server
        )
        restart_services = source.index(
            "systemctl restart hysteria2-panel.service hysteria2-panel-server.service",
            final_checkpoint,
        )

        self.assertLess(final_sync, stop_old_server)
        self.assertLess(stop_old_server, final_checkpoint)
        self.assertLess(final_checkpoint, restart_services)
        self.assertIn(
            '[[ ! -e /var/lib/hysteria2-panel/pending-traffic.json ]]',
            source[final_sync:stop_old_server],
        )

    def test_fresh_install_rejects_loaded_vendor_or_runtime_units(self):
        source = INSTALLER.read_text()
        helper_start = source.index("assert_units_unclaimed()")
        helper_end = source.index("\n\ncreate_database_snapshot()", helper_start)
        helper = source[helper_start:helper_end]
        script = f"""
set -Eeuo pipefail
{helper}
fail() {{ printf 'FAIL:%s\\n' "$*" >&2; exit 97; }}
systemctl() {{
  case "$*" in
    *"hysteria2-panel-server.service")
      printf '%s\\n' \
        'LoadState=loaded' \
        'ActiveState=inactive' \
        'FragmentPath=/usr/lib/systemd/system/hysteria2-panel-server.service' \
        'DropInPaths='
      ;;
    *)
      printf '%s\\n' \
        'LoadState=not-found' \
        'ActiveState=inactive' \
        'FragmentPath=' \
        'DropInPaths='
      ;;
  esac
}}
assert_units_unclaimed
"""
        result = subprocess.run(["bash"], input=script, capture_output=True, text=True)

        self.assertEqual(97, result.returncode)
        self.assertIn("同名 systemd 服务 hysteria2-panel-server.service", result.stderr)

    def test_managed_upgrade_requires_existing_admin_and_user_schema(self):
        source = INSTALLER.read_text()

        self.assertIn('{"admins", "proxy_users"}.issubset(tables)', source)
        self.assertIn('admin_count != 1', source)
        self.assertIn('"password_hash"', source)
        self.assertIn('admin_columns', source)
        self.assertIn('required.issubset(columns)', source)
        self.assertIn('hmac.compare_digest(actual, expected)', source)
        self.assertIn('os.environ.pop("HY2PANEL_IDENTITY_HMAC_KEY")', source)
        self.assertNotIn('"${HY2PANEL_DB}" "${HY2PANEL_HMAC_KEY}"', source)

    def test_fresh_install_writes_managed_marker_only_after_success(self):
        source = INSTALLER.read_text()
        marker_write = 'durable_replace_file /dev/null "${MANAGED_MARKER}" 0644'

        self.assertEqual(1, source.count(marker_write))
        self.assertGreater(source.index(marker_write), source.rindex("configure_firewall\n"))
        self.assertIn('FRESH_INSTALL_MUTATED=1', source)
        self.assertIn('stop_loaded_units', source)
        self.assertIn('/var/backups/hysteria2-panel', source)
        self.assertIn('remove_fresh_install_principals', source)
        self.assertIn('userdel --remove "${principal}"', source)
        self.assertIn('userdel "${principal}"', source)
        self.assertIn('groupdel "${principal_group}"', source)
        self.assertIn('可以直接重新运行安装器', source)

    def test_fresh_install_uses_a_durable_version_independent_transaction_before_mutation(self):
        source = INSTALLER.read_text()
        transaction_write = 'durable_replace_file "${transaction_stage}" "${FRESH_IN_PROGRESS_MARKER}" 0600'

        self.assertIn('FRESH_IN_PROGRESS_MARKER=/etc/.hysteria2-panel-installing-by-installer', source)
        self.assertIn('FRESH_TRANSACTION_MAGIC=HYSTERIA2_PANEL_FRESH_TRANSACTION_V1', source)
        self.assertIn('recover_interrupted_fresh_install()', source)
        self.assertIn('arm_fresh_install_transaction()', source)
        self.assertIn(transaction_write, source)
        self.assertLess(source.index(transaction_write), source.index('groupadd --system hy2tls'))
        recovery = source[
            source.index('read_fresh_install_transaction()'):
            source.index('\n\nwait_for_health()', source.index('recover_interrupted_fresh_install()'))
        ]
        self.assertIn('"${marker_magic}" == "${FRESH_TRANSACTION_MAGIC}"', recovery)
        self.assertNotIn('PANEL_VERSION', recovery)
        self.assertIn('stat -c \'%u:%g:%a\' "${marker_path}"', recovery)
        self.assertIn('stop_loaded_units', recovery)
        self.assertIn('restore_fresh_install_sysctls', recovery)
        self.assertIn('if [[ -e /proc/sys/net/core/default_qdisc ]]; then', source)
        self.assertIn(
            'original_qdisc="$(sysctl -n net.core.default_qdisc)"', source
        )
        self.assertIn('original_qdisc="-"', source)
        self.assertIn('if [[ "${FRESH_ORIGINAL_QDISC}" == "-" ]]; then', recovery)
        self.assertIn('FRESH_ORIGINAL_QDISC=""', recovery)

    def test_fresh_install_installs_boot_recovery_before_persistent_payload(self):
        source = INSTALLER.read_text()
        recovery_infrastructure = source.rindex(
            '\n  install_fresh_recovery_infrastructure\n'
        )
        arm = source.index('\n  arm_fresh_install_transaction\n', recovery_infrastructure)
        recovery_gate = source.index('\n  install_fresh_recovery_gate\n', arm)
        first_principal = source.index('groupadd --system hy2tls', arm)

        self.assertIn(
            'FRESH_RECOVERY_SCRIPT=/var/backups/hysteria2-panel/.install-recover.sh',
            source,
        )
        self.assertIn(
            'FRESH_RECOVERY_UNIT=/etc/systemd/system/hysteria2-panel-install-recover.service',
            source,
        )
        self.assertIn(
            'FRESH_RECOVERY_DROPIN=/etc/systemd/system/hysteria2-panel.service.d/05-fresh-install-recovery.conf',
            source,
        )
        self.assertLess(recovery_infrastructure, arm)
        self.assertLess(arm, recovery_gate)
        self.assertLess(recovery_gate, first_principal)
        unit_start = source.index('cat > "${recovery_unit_stage}"')
        recovery_unit = source[unit_start:source.index('\nEOF', unit_start)]
        self.assertIn('ConditionPathExists=${FRESH_IN_PROGRESS_MARKER}', recovery_unit)
        self.assertIn('Before=hysteria2-panel.service hysteria2-panel-server.service', recovery_unit)
        self.assertIn('ExecStart=/bin/bash ${FRESH_RECOVERY_SCRIPT} --recover-fresh', recovery_unit)
        self.assertIn('systemctl enable hysteria2-panel-install-recover.service', source)
        gate_start = source.index('install_fresh_recovery_gate()')
        recovery_gate_helper = source[
            gate_start:source.index('\n\ndisarm_fresh_install_transaction()', gate_start)
        ]
        self.assertIn('Requires=hysteria2-panel-install-recover.service', recovery_gate_helper)
        self.assertIn('After=hysteria2-panel-install-recover.service', recovery_gate_helper)
        self.assertIn('durable_replace_file "${gate_stage}" "${dropin}" 0644', recovery_gate_helper)
        ownership_check = source[
            source.index('assert_units_claimed_by_installer()'):
            source.index('\n\ndatabase_is_healthy()', source.index('assert_units_claimed_by_installer()'))
        ]
        self.assertIn('${FRESH_RECOVERY_DROPIN}', ownership_check)
        self.assertIn('${FRESH_RECOVERY_SERVER_DROPIN}', ownership_check)
        self.assertIn('${FRESH_RECOVERY_SERVER_443_DROPIN}', ownership_check)
        disarm = source[
            source.index('disarm_fresh_install_transaction()'):
            source.index('\n\nrecover_interrupted_fresh_install()', source.index('disarm_fresh_install_transaction()'))
        ]
        self.assertIn('"${FRESH_RECOVERY_DROPIN}"', disarm)

    def test_markerless_fresh_recovery_orphans_are_authenticated_and_cleaned_before_admission(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index('cleanup_orphaned_fresh_recovery_infrastructure()'):
            source.index('\n\nread_fresh_install_transaction()', source.index('cleanup_orphaned_fresh_recovery_infrastructure()'))
        ]
        main = source.split('if [[ "${1:-}" == "--help"', 1)[1]

        self.assertIn('FRESH_TRANSACTION_MAGIC=HYSTERIA2_PANEL_FRESH_TRANSACTION_V1', source)
        self.assertIn('FRESH_TRANSACTION_MAGIC=${FRESH_TRANSACTION_MAGIC}', helper)
        self.assertIn('ConditionPathExists=${FRESH_IN_PROGRESS_MARKER}', helper)
        self.assertIn('ExecStart=/bin/bash ${FRESH_RECOVERY_SCRIPT} --recover-fresh', helper)
        self.assertIn("stat -c '%u:%g:%a:%h'", helper)
        self.assertIn('systemctl disable hysteria2-panel-install-recover.service', helper)
        cleanup = main.index('cleanup_orphaned_fresh_recovery_infrastructure')
        admission = main.index('assert_no_unmanaged_install_paths')
        self.assertLess(cleanup, admission)

    def test_clean_host_orphan_recovery_does_not_require_var_backups(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index('cleanup_orphaned_fresh_recovery_infrastructure()'):
            source.index('\n\nread_fresh_install_transaction()', source.index('cleanup_orphaned_fresh_recovery_infrastructure()'))
        ]

        self.assertNotIn('sync -f /etc/systemd/system /var/backups', helper)
        self.assertIn('sync -f /etc/systemd/system', helper)
        self.assertRegex(
            helper,
            r'if \[\[ -d /var/backups \]\]; then\s+'
            r'sync -f /var/backups',
        )

    def test_fresh_install_commit_is_durable_before_disarming_recovery(self):
        source = INSTALLER.read_text()
        marker_write = 'durable_replace_file /dev/null "${MANAGED_MARKER}" 0644'
        payload_flush = 'flush_install_payload_for_commit'

        self.assertEqual(1, source.count(marker_write))
        self.assertGreater(source.index(marker_write), source.rindex('configure_firewall\n'))
        self.assertLess(source.rindex(payload_flush), source.index(marker_write))
        self.assertGreater(
            source.rindex('\n  disarm_fresh_install_transaction \\'),
            source.index(marker_write),
        )
        self.assertIn('durable_remove_file "${FRESH_IN_PROGRESS_MARKER}"', source)

        flush_helper = source[
            source.index('flush_install_payload_for_commit()'):
            source.index('\n\nstop_loaded_units()', source.index('flush_install_payload_for_commit()'))
        ]
        for path in (
            '/opt/hysteria2-panel',
            '/etc/hysteria2-panel',
            '/var/lib/hysteria2-panel',
            '/etc/systemd/system',
            '/etc/sudoers.d',
            '/etc/sysctl.d',
            '/etc/tmpfiles.d',
        ):
            self.assertIn(path, flush_helper)

    def test_fresh_install_failure_keeps_boot_recovery_armed_until_strict_cleanup(self):
        source = INSTALLER.read_text()
        rollback = source[
            source.index('rollback_existing_install()'):
            source.index('\n\nfinalize_install()', source.index('rollback_existing_install()'))
        ]
        fresh_branch = rollback[
            rollback.index('if [[ "${FRESH_INSTALL_MUTATED:-0}" == "1"'):
            rollback.index('\n  if [[ "${ROLLBACK_REQUIRED:-0}"', rollback.index('if [[ "${FRESH_INSTALL_MUTATED:-0}" == "1"'))
        ]

        self.assertIn('( set -e; recover_interrupted_fresh_install )', fresh_branch)
        self.assertNotIn('rollback_firewall_after_service_recovery || true', fresh_branch)
        self.assertNotIn('durable_remove_file "${FRESH_IN_PROGRESS_MARKER}"', fresh_branch)

        recovery = source[
            source.index('recover_interrupted_fresh_install()'):
            source.index('\n\nwait_for_health()', source.index('recover_interrupted_fresh_install()'))
        ]
        self.assertIn('verify_fresh_install_commit_payload', recovery)
        self.assertIn('remove_fresh_install_principals', recovery)
        self.assertIn('disarm_fresh_install_transaction', recovery)
        strict_cleanup = recovery[recovery.index('检测到上次未完成'):]
        disarm_index = strict_cleanup.index('disarm_fresh_install_transaction')
        self.assertLess(strict_cleanup.index('remove_fresh_install_principals'), disarm_index)
        self.assertLess(strict_cleanup.index('flush_fresh_cleanup_before_disarm'), disarm_index)
        self.assertNotIn(
            'hysteria2-panel-install-recover.service',
            strict_cleanup[strict_cleanup.index('systemctl disable'):disarm_index],
        )

        cleanup_barrier = source[
            source.index('flush_fresh_cleanup_before_disarm()'):
            source.index('\n\narm_fresh_install_transaction()', source.index('flush_fresh_cleanup_before_disarm()'))
        ]
        for path in (
            '/opt',
            '/etc',
            '/var/lib',
            '/var/backups',
            '/etc/systemd/system',
            '/etc/sudoers.d',
            '/etc/sysctl.d',
            '/etc/tmpfiles.d',
        ):
            self.assertIn(path, cleanup_barrier)
        self.assertIn('/opt/hysteria2-panel', cleanup_barrier)
        self.assertIn('/var/lib/hysteria2-panel', cleanup_barrier)
        self.assertIn('${UPGRADE_RECOVERY_SCRIPT}', cleanup_barrier)

        commit_verifier = source[
            source.index('verify_fresh_install_commit_payload()'):
            source.index('\n\narm_fresh_install_transaction()', source.index('verify_fresh_install_commit_payload()'))
        ]
        for path in (
            '/opt/hysteria2-panel/bin/hysteria',
            '/opt/hysteria2-panel/hysteria2_panel.py',
            '/opt/hysteria2-panel/hy2panel/systemd.py',
            '/etc/hysteria2-panel/panel.env',
            '/etc/hysteria2-panel/hysteria.yaml',
            '/etc/hysteria2-panel/server.crt',
            '/etc/hysteria2-panel/server.key',
            '/var/lib/hysteria2-panel/panel.db',
            '/etc/systemd/system/hysteria2-panel.service',
            '/etc/systemd/system/hysteria2-panel-server.service',
        ):
            self.assertIn(path, commit_verifier)

    def test_fresh_cleanup_skips_optional_directories_that_never_existed(self):
        source = INSTALLER.read_text()
        cleanup_barrier = source[
            source.index('flush_fresh_cleanup_before_disarm()'):
            source.index(
                '\n\narm_fresh_install_transaction()',
                source.index('flush_fresh_cleanup_before_disarm()'),
            )
        ]

        self.assertIn('local -a cleanup_sync_dirs=(', cleanup_barrier)
        self.assertIn(
            'sync_existing_directories "${cleanup_sync_dirs[@]}"',
            cleanup_barrier,
        )
        self.assertNotRegex(
            cleanup_barrier,
            r'sync -f\s+\\\s+(?:/[^\s]+\s+)+',
        )

    def test_sync_existing_directories_propagates_an_intermediate_failure(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index('sync_existing_directories()'):
            source.index(
                '\n\ndownload_file()',
                source.index('sync_existing_directories()'),
            )
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / 'first'
            missing = root / 'missing'
            failing = root / 'failing'
            after = root / 'after'
            log = root / 'sync.log'
            for directory in (first, failing, after):
                directory.mkdir()
            script = f'''
set -euo pipefail
{helper}
sync() {{
  printf '%s\n' "$2" >> {str(log)!r}
  [[ "$2" != {str(failing)!r} ]]
}}
if sync_existing_directories \
  {str(first)!r} {str(missing)!r} {str(failing)!r} {str(after)!r}; then
  exit 91
fi
'''
            result = subprocess.run(
                ['bash', '-c', script],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual([str(first), str(failing)], log.read_text().splitlines())

    def test_download_file_retries_all_errors_and_clears_partial_output(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index('download_file()'):
            source.index(
                '\n\nflush_install_payload_for_commit()',
                source.index('download_file()'),
            )
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / 'download'
            script = f'''
set -euo pipefail
{helper}
attempts=0
curl_mode=eventual
curl() {{
  local output=''
  [[ "$1" == '-q' ]] || return 96
  while (( $# > 0 )); do
    if [[ "$1" == '-o' ]]; then
      output="$2"
      shift 2
    else
      shift
    fi
  done
  [[ ! -e "${{output}}" ]] || return 97
  attempts=$((attempts + 1))
  printf 'partial-%s\n' "${{attempts}}" > "${{output}}"
  if [[ "${{curl_mode}}" == 'fail' || "${{attempts}}" -lt 3 ]]; then
    return 35
  fi
  printf 'complete\n' > "${{output}}"
}}
sleep() {{ :; }}
download_file https://example.invalid/source {str(destination)!r}
[[ "${{attempts}}" == 3 ]]
[[ "$(cat {str(destination)!r})" == 'complete' ]]
rm -f -- {str(destination)!r}
attempts=0
curl_mode=fail
if download_file https://example.invalid/source {str(destination)!r}; then
  exit 92
fi
[[ "${{attempts}}" == 4 ]]
[[ ! -e {str(destination)!r} ]]
'''
            result = subprocess.run(
                ['bash', '-c', script],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)

    def test_existing_install_requires_an_owned_regular_managed_marker(self):
        source = INSTALLER.read_text()
        main = source.split('if [[ "${1:-}" == "--help"', 1)[1]
        ownership_gate = source[
            source.index('if [[ -e "${MANAGED_MARKER}"', source.index(main)) :
            source.index("guard_legacy_restore_admission", source.index(main))
        ]

        self.assertIn('[[ ! -L "${MANAGED_MARKER}" && -f "${MANAGED_MARKER}" ]]', ownership_gate)
        self.assertIn("stat -c '%u:%g:%a' \"${MANAGED_MARKER}\"", ownership_gate)
        self.assertIn('"${managed_marker_metadata}" == "0:0:644"', ownership_gate)
        self.assertIn('! -s "${MANAGED_MARKER}"', ownership_gate)

    def test_fresh_install_claims_every_persistent_artifact_before_mutation(self):
        source = INSTALLER.read_text()
        ownership_check = source[
            source.index('MANAGED_MARKER=/etc/hysteria2-panel/.managed-by-installer'):
            source.index('\nEXISTING_INSTALL=0')
        ]

        for path in (
            '/opt/hysteria2-panel',
            '/etc/hysteria2-panel',
            '/var/lib/hysteria2-panel',
            '/var/backups/hysteria2-panel',
            '/etc/sudoers.d/hysteria2-panel',
            '${SYSCTL_FILE}',
            '${TMPFILES_FILE}',
            '/etc/systemd/system/hysteria2-panel.service',
            '/etc/systemd/system/hysteria2-panel-server.service',
            '/etc/systemd/system/multi-user.target.wants/hysteria2-panel.service',
            '/etc/systemd/system/multi-user.target.wants/hysteria2-panel-server.service',
        ):
            self.assertIn(path, ownership_check)

        self.assertLess(
            source.index('发现非本安装器管理的同名路径或服务'),
            source.index('groupadd --system hy2tls'),
        )

    def test_fresh_install_rejects_preexisting_service_principals(self):
        source = INSTALLER.read_text()

        self.assertIn('首次安装检测到同名系统账号 ${principal}', source)
        self.assertIn('首次安装检测到同名系统组 ${principal_group}', source)
        self.assertIn('for principal_group in hy2panel hy2tls', source)
        self.assertIn('useradd --system --user-group', source)
        self.assertLess(source.index('首次安装检测到同名系统账号'), source.index('groupadd --system hy2tls'))

    def test_secondary_443_entrypoint_reserves_443_from_panel_and_internal_ports(self):
        source = INSTALLER.read_text()

        validation = (
            'if (( UDP_443_ENABLED == 1 )) && '
            '[[ "${PANEL_PORT}" == "443" || "${AUTH_PORT}" == "443" || '
            '"${STATS_PORT}" == "443" || "${STATS_443_PORT}" == "443" ]]; then'
        )
        self.assertIn(validation, source)
        self.assertIn("启用账号专属 443 入口时，端口 443 不能用于面板或内部服务", source)
        self.assertLess(source.index(validation), source.index('ss -H -lun "sport = :${HYSTERIA_PORT}"'))

    def test_installer_adds_tcp_probe_on_the_hysteria_port(self):
        source = INSTALLER.read_text()

        self.assertIn("TCP_PROBE_SOURCE_URL", source)
        self.assertIn("tcp_probe.py", source)
        self.assertIn("hysteria2-panel-tcp-probe.service", source)
        self.assertIn("BindsTo=hysteria2-panel-server.service", source)
        self.assertIn("PartOf=hysteria2-panel-server.service", source)
        self.assertIn("Wants=hysteria2-panel-tcp-probe.service", source)
        self.assertIn("DynamicUser=true", source)
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/tcp_probe.py ${HYSTERIA_PORT}",
            source,
        )
        self.assertIn('ss -H -ltn "sport = :${HYSTERIA_PORT}"', source)
        self.assertIn('TCP/UDP ${HYSTERIA_PORT}', source)

    def test_installer_mirrors_the_tcp_probe_on_the_udp_443_entrypoint(self):
        source = INSTALLER.read_text()

        self.assertIn("hysteria2-panel-tcp-probe-443.service", source)
        self.assertIn("Wants=hysteria2-panel-tcp-probe-443.service", source)
        secondary_probe_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-tcp-probe-443.service <<EOF",
            1,
        )[1].split("\nEOF", 1)[0]
        self.assertIn("BindsTo=hysteria2-panel-server-443.service", secondary_probe_unit)
        self.assertIn("PartOf=hysteria2-panel-server-443.service", secondary_probe_unit)
        self.assertIn("DynamicUser=true", secondary_probe_unit)
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/tcp_probe.py 443",
            secondary_probe_unit,
        )
        self.assertIn(
            "CapabilityBoundingSet=CAP_NET_BIND_SERVICE", secondary_probe_unit
        )
        self.assertIn("AmbientCapabilities=CAP_NET_BIND_SERVICE", secondary_probe_unit)
        self.assertIn(
            'if (( UDP_443_ENABLED == 1 )) && ss -H -ltn "sport = :443" | grep -q . && ! systemctl is-active --quiet hysteria2-panel-tcp-probe-443.service; then',
            source,
        )
        self.assertIn("stop_loaded_units", source)
        self.assertIn(
            'systemctl is-active --quiet hysteria2-panel-tcp-probe-443.service || fail "TCP 443 连通性探测服务启动失败"',
            source,
        )
        self.assertIn(
            'ss -H -ltn "sport = :443" | grep -q . || fail "Hysteria TCP 443 探测端口未监听"',
            source,
        )
        self.assertIn("云平台安全组还需放行 TCP/UDP 443", source)

    def test_installer_waits_for_service_readiness(self):
        source = INSTALLER.read_text()

        self.assertIn("wait_for_health", source)
        self.assertIn("for _attempt in {1..30}", source)
        self.assertIn('wait_for_health "${PANEL_SCHEME}://127.0.0.1:${PANEL_PORT}/healthz"', source)
        self.assertIn('wait_for_health "${PANEL_SCHEME}://127.0.0.1:${PANEL_PORT}/readyz"', source)

    def test_panel_service_uses_native_systemd_readiness_and_watchdog_contract(self):
        source = INSTALLER.read_text()
        panel_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel.service <<EOF", 1
        )[1].split("\nEOF", 1)[0]

        self.assertIn("Type=notify", panel_unit)
        self.assertIn("NotifyAccess=main", panel_unit)
        self.assertIn("TimeoutStartSec=60s", panel_unit)
        self.assertIn("WatchdogSec=30s", panel_unit)
        self.assertIn("Restart=on-failure", panel_unit)
        self.assertNotIn("Type=simple", panel_unit)

    def test_panel_watchdog_restart_does_not_stop_hysteria_data_plane(self):
        source = INSTALLER.read_text()
        primary = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-server.service <<EOF", 1
        )[1].split("\nEOF", 1)[0]
        secondary = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-server-443.service <<'EOF'", 1
        )[1].split("\nEOF", 1)[0]

        for server_unit in (primary, secondary):
            self.assertIn("Wants=hysteria2-panel.service", server_unit)
            self.assertIn("After=", server_unit)
            self.assertIn("hysteria2-panel.service", server_unit)
            self.assertNotIn("Requires=hysteria2-panel.service", server_unit)
            for recovery in (
                "hysteria2-panel-upgrade-recover.service",
                "hysteria2-panel-restore-recover.service",
                "hysteria2-panel-egress-recover.service",
            ):
                self.assertIn(recovery, server_unit)

        gate = source[
            source.index("install_fresh_recovery_gate()"):
            source.index(
                "\n\ndisarm_fresh_install_transaction()",
                source.index("install_fresh_recovery_gate()"),
            )
        ]
        self.assertIn("${FRESH_RECOVERY_DROPIN}", gate)
        self.assertIn("${FRESH_RECOVERY_SERVER_DROPIN}", gate)
        self.assertIn("${FRESH_RECOVERY_SERVER_443_DROPIN}", gate)

    def test_hysteria_restart_does_not_reenter_transaction_recovery(self):
        source = INSTALLER.read_text()
        panel = source.split(
            "cat > /etc/systemd/system/hysteria2-panel.service <<EOF", 1
        )[1].split("\nEOF", 1)[0]
        primary = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-server.service <<EOF", 1
        )[1].split("\nEOF", 1)[0]
        secondary = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-server-443.service <<'EOF'", 1
        )[1].split("\nEOF", 1)[0]

        recovery_requires = (
            "Requires=hysteria2-panel-upgrade-recover.service "
            "hysteria2-panel-restore-recover.service "
            "hysteria2-panel-egress-recover.service"
        )
        self.assertIn(recovery_requires, panel)
        for server_unit in (primary, secondary):
            self.assertIn(recovery_requires, server_unit)
            self.assertIn("Wants=hysteria2-panel.service", server_unit)
            after = next(
                line for line in server_unit.splitlines() if line.startswith("After=")
            )
            self.assertIn("hysteria2-panel.service", after)

        self.assertIn(
            "EGRESS_SWITCH_ACTIVE_MARKER=${MAINTENANCE_RUNTIME_DIR}/egress-switch-active",
            source,
        )
        active_marker = "${EGRESS_SWITCH_ACTIVE_MARKER}"
        full = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-egress-full.service <<EOF",
            1,
        )[1].split("\nEOF", 1)[0]
        web = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-egress-web.service <<EOF",
            1,
        )[1].split("\nEOF", 1)[0]
        recover = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-egress-recover.service <<EOF",
            1,
        )[1].split("\nEOF", 1)[0]
        for switch_unit in (full, web):
            self.assertIn("ExecStartPre=/usr/bin/touch {}".format(active_marker), switch_unit)
            self.assertIn("ExecStopPost=-/bin/rm -f {}".format(active_marker), switch_unit)
        self.assertIn("ConditionPathExists=!{}".format(active_marker), recover)

    def test_installer_e2e_exercises_watchdog_hang_without_restarting_data_plane(self):
        e2e = (ROOT / "tests" / "installer_e2e.sh").read_text()

        self.assertIn("--signal=SIGSTOP hysteria2-panel.service", e2e)
        self.assertIn('kill -CONT "${watchdog_panel_pid_before}"', e2e)
        self.assertIn(
            '"$(systemctl show --property=MainPID --value '
            'hysteria2-panel-server.service)" == "${watchdog_server_pid_before}"',
            e2e,
        )
        self.assertIn(
            '"$(systemctl show --property=MainPID --value '
            'hysteria2-panel-server-443.service)" == '
            '"${watchdog_secondary_pid_before}"',
            e2e,
        )

    def test_installer_e2e_waits_for_readiness_after_recovery_commit(self):
        e2e = (ROOT / "tests" / "installer_e2e.sh").read_text()
        recovery_checks = e2e[e2e.rindex(
            "test ! -e /var/backups/hysteria2-panel/.upgrade-active"
        ) :]

        self.assertIn("recovery_ready=0", recovery_checks)
        self.assertIn("recovery_deadline=$((SECONDS + 30))", recovery_checks)
        self.assertIn("while (( SECONDS < recovery_deadline )); do", recovery_checks)
        self.assertIn('--connect-timeout 1 --max-time "${recovery_remaining}"', recovery_checks)
        self.assertIn("recovery_ready=1", recovery_checks)
        self.assertIn("(( recovery_ready == 1 ))", recovery_checks)

    def test_installer_persists_quic_udp_buffer_optimization(self):
        source = INSTALLER.read_text()

        self.assertIn("/etc/sysctl.d/99-hysteria2-panel.conf", source)
        self.assertIn("ensure_sysctl_directory()", source)
        ensure_call = source.split(
            'if [[ "${1:-}" == "--maintenance-lock-held"', 1
        )[1].index("ensure_sysctl_directory")
        arm_transaction = source.split(
            'if [[ "${1:-}" == "--maintenance-lock-held"', 1
        )[1].index("arm_upgrade_transaction")
        self.assertGreater(ensure_call, arm_transaction)
        self.assertIn("net.core.rmem_max", source)
        self.assertIn("net.core.wmem_max", source)
        self.assertIn("16777216", source)
        self.assertIn("net.core.default_qdisc", source)
        self.assertIn("net.ipv4.tcp_congestion_control", source)
        self.assertIn("LimitNOFILE=1048576", source)

    def test_installer_explicitly_enables_hysteria_quic_bbr(self):
        source = INSTALLER.read_text()

        self.assertIn("congestion:", source)
        self.assertIn("type: bbr", source)
        self.assertIn("bbrProfile: standard", source)
        self.assertIn("ignoreClientBandwidth: true", source)
        self.assertIn("Nice=-5", source)

    def test_installer_defaults_to_a_persisted_full_egress_policy(self):
        source = INSTALLER.read_text()

        self.assertIn('EXISTING_EGRESS_POLICY="${HY2PANEL_EGRESS_POLICY:-full}"', source)
        self.assertIn('EXISTING_EGRESS_POLICY="full"', source)
        self.assertIn('EGRESS_POLICY="${EGRESS_POLICY:-${EXISTING_EGRESS_POLICY}}"', source)
        self.assertIn('HY2PANEL_EGRESS_POLICY=${EGRESS_POLICY}', source)
        self.assertIn('EGRESS_POLICY 只能是 web 或 full', source)

    def test_full_egress_policy_blocks_private_networks_and_allows_all_public_ports(self):
        source = INSTALLER.read_text()

        for rule in (
            "reject(0.0.0.0/8)",
            "reject(127.0.0.0/8)",
            "reject(10.0.0.0/8)",
            "reject(100.64.0.0/10)",
            "reject(169.254.0.0/16)",
            "reject(172.16.0.0/12)",
            "reject(192.168.0.0/16)",
            "reject(224.0.0.0/4)",
            "reject(240.0.0.0/4)",
            "reject(::/128)",
            "reject(::1/128)",
            "reject(fc00::/7)",
            "reject(fe80::/10)",
            "reject(ff00::/8)",
            "direct(all)",
        ):
            self.assertIn(rule, source)
        self.assertLess(source.index("reject(127.0.0.0/8)"), source.index("direct(all)"))
        self.assertLess(source.index("reject(fe80::/10)"), source.index("direct(all)"))
        self.assertIn('else\n  cat >> /etc/hysteria2-panel/hysteria.yaml <<EOF\n    - "direct(all)"', source)

    def test_web_egress_policy_blocks_private_networks_and_allows_public_ssh(self):
        source = INSTALLER.read_text()

        for rule in (
            "reject(0.0.0.0/8)",
            "reject(127.0.0.0/8)",
            "reject(10.0.0.0/8)",
            "reject(100.64.0.0/10)",
            "reject(169.254.0.0/16)",
            "reject(172.16.0.0/12)",
            "reject(192.168.0.0/16)",
            "reject(224.0.0.0/4)",
            "reject(240.0.0.0/4)",
            "reject(::/128)",
            "reject(::1/128)",
            "reject(fc00::/7)",
            "reject(fe80::/10)",
            "reject(ff00::/8)",
            "direct(all, tcp/22)",
            "direct(all, tcp/53)",
            "direct(all, udp/53)",
            "direct(all, tcp/80)",
            "direct(all, tcp/443)",
            "direct(all, udp/443)",
            "direct(all, udp/123)",
            "reject(all)",
        ):
            self.assertIn(rule, source)
        self.assertLess(source.index("reject(127.0.0.0/8)"), source.index("direct(all, tcp/80)"))
        self.assertLess(source.index("reject(fe80::/10)"), source.index("direct(all, tcp/22)"))
        self.assertLess(source.index("direct(all, tcp/22)"), source.index("reject(all)"))
        self.assertIn('if [[ "${EGRESS_POLICY}" == "web" ]]; then', source)

    def test_web_egress_policy_allows_the_public_panel_port_on_future_servers(self):
        source = INSTALLER.read_text()

        self.assertIn('direct(all, tcp/${PANEL_PORT})', source)
        self.assertNotIn("PANEL_ACCESS_IPS", source)
        self.assertNotIn("HY2PANEL_PANEL_ACCESS_IPS", source)
        self.assertLess(
            source.index('direct(all, tcp/${PANEL_PORT})'),
            source.index('reject(all)'),
        )
        self.assertLess(
            source.index("reject(127.0.0.0/8)"),
            source.index('direct(all, tcp/${PANEL_PORT})'),
        )

    def test_installer_grants_only_exact_hysteria_service_controls(self):
        source = INSTALLER.read_text()

        self.assertIn("/etc/sudoers.d/hysteria2-panel", source)
        self.assertIn(
            "hy2panel ALL=(root) NOPASSWD: /bin/systemctl start hysteria2-panel-server.service",
            source,
        )
        self.assertIn(
            "/bin/systemctl stop hysteria2-panel-server.service",
            source,
        )
        self.assertIn(
            "/bin/systemctl restart hysteria2-panel-server.service",
            source,
        )
        self.assertIn(
            "/bin/systemctl --no-block reboot",
            source,
        )
        self.assertIn("visudo -cf", source)
        self.assertIn("sudo", source)
        panel_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel.service <<EOF", 1
        )[1].split("EOF", 1)[0]
        self.assertNotIn("NoNewPrivileges=true", panel_unit)

        hardened_units = (
            "hysteria2-panel-server.service",
            "hysteria2-panel-server-443.service",
            "hysteria2-panel-tcp-probe.service",
            "hysteria2-panel-tcp-probe-443.service",
            "hysteria2-panel-egress-full.service",
            "hysteria2-panel-egress-web.service",
            "hysteria2-panel-egress-recover.service",
            "hysteria2-panel-restore.service",
            "hysteria2-panel-restore-recover.service",
            "hysteria2-panel-restore-resume.service",
            "hysteria2-panel-update.service",
        )
        for unit in hardened_units:
            unit_start = source.index(
                "cat > /etc/systemd/system/{}".format(unit)
            )
            unit_source = source[unit_start:].split("\nEOF", 1)[0]
            for sandbox_option in (
                "NoNewPrivileges=true",
                "PrivateDevices=true",
                "RestrictSUIDSGID=true",
                "LockPersonality=true",
            ):
                self.assertIn(sandbox_option, unit_source, unit)

    def test_installer_adds_fixed_root_only_egress_policy_switch_services(self):
        source = INSTALLER.read_text()

        self.assertIn(
            "/bin/systemctl start hysteria2-panel-egress-full.service",
            source,
        )
        self.assertIn(
            "/bin/systemctl start hysteria2-panel-egress-web.service",
            source,
        )
        full_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-egress-full.service <<EOF",
            1,
        )[1].split("EOF", 1)[0]
        web_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-egress-web.service <<EOF",
            1,
        )[1].split("EOF", 1)[0]
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py apply-egress-policy full",
            full_unit,
        )
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py apply-egress-policy web",
            web_unit,
        )
        for unit in (full_unit, web_unit):
            self.assertIn("NoNewPrivileges=true", unit)
            self.assertIn("ProtectSystem=strict", unit)
            self.assertIn("ReadWritePaths=/etc/hysteria2-panel", unit)
            self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
            self.assertIn("TimeoutStartSec=5min", unit)
            self.assertNotIn("User=hy2panel", unit)

        recover_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel-egress-recover.service <<EOF",
            1,
        )[1].split("EOF", 1)[0]
        panel_unit = source.split(
            "cat > /etc/systemd/system/hysteria2-panel.service <<EOF", 1
        )[1].split("EOF", 1)[0]
        self.assertIn(
            "ConditionPathExists=${EGRESS_TRANSACTION_MARKER}", recover_unit
        )
        self.assertIn("Before=hysteria2-panel.service", recover_unit)
        self.assertIn("recover-egress-policy", recover_unit)
        self.assertIn("Requires=hysteria2-panel-upgrade-recover.service", panel_unit)
        self.assertIn("hysteria2-panel-restore-recover.service", panel_unit)
        self.assertIn("hysteria2-panel-egress-recover.service", panel_unit)
        self.assertIn(
            'record-egress-policy-state "${EGRESS_POLICY}"', source
        )

    def test_installer_adds_a_root_only_one_shot_restore_service(self):
        source = INSTALLER.read_text()

        self.assertIn("hysteria2-panel-restore.service", source)
        self.assertIn(
            "/bin/systemctl --no-block start hysteria2-panel-restore.service",
            source,
        )
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py restore-pending",
            source,
        )
        self.assertNotIn("Conflicts=hysteria2-panel.service", source)
        self.assertIn(
            "ExecStopPost=/bin/systemctl --no-block start hysteria2-panel-restore-resume.service",
            source,
        )
        self.assertIn("ReadWritePaths=/etc/hysteria2-panel /var/lib/hysteria2-panel /var/backups/hysteria2-panel ${MAINTENANCE_RUNTIME_DIR}", source)
        self.assertIn("TimeoutStartSec=25min", source)
        self.assertIn("TimeoutStopSec=15min", source)
        self.assertNotIn("User=hy2panel\nEnvironmentFile=/etc/hysteria2-panel/panel.env\nExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py restore-pending", source)

    def test_installer_adds_boot_recovery_for_interrupted_restore_transactions(self):
        source = INSTALLER.read_text()
        recover_unit = source.split(
            'cat > /etc/systemd/system/hysteria2-panel-restore-recover.service <<EOF', 1
        )[1].split("EOF", 1)[0]
        resume_unit = source.split(
            'cat > /etc/systemd/system/hysteria2-panel-restore-resume.service <<EOF', 1
        )[1].split("EOF", 1)[0]
        panel_unit = source.split(
            'cat > /etc/systemd/system/hysteria2-panel.service <<EOF', 1
        )[1].split("EOF", 1)[0]

        self.assertNotIn("EnvironmentFile=", recover_unit)
        self.assertIn("Before=hysteria2-panel.service", recover_unit)
        self.assertIn("ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py recover-restore-files", recover_unit)
        self.assertIn("hysteria2-panel-restore-recover.service", panel_unit)
        self.assertIn("After=network-online.target hysteria2-panel-upgrade-recover.service", panel_unit)
        self.assertIn("hysteria2-panel-restore-recover.service", panel_unit)
        self.assertIn("hysteria2-panel-egress-recover.service", panel_unit)
        self.assertIn("ConditionPathExists=/etc/hysteria2-panel/.restore-active", resume_unit)
        self.assertIn("After=network-online.target hysteria2-panel.service hysteria2-panel-server.service", resume_unit)
        self.assertIn("Wants=network-online.target hysteria2-panel.service hysteria2-panel-server.service", resume_unit)
        self.assertNotIn("Before=hysteria2-panel.service", resume_unit)
        self.assertIn("ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py resume-after-restore", resume_unit)
        self.assertIn("ReadWritePaths=/etc/hysteria2-panel /var/lib/hysteria2-panel /var/backups/hysteria2-panel ${MAINTENANCE_RUNTIME_DIR}", resume_unit)
        self.assertIn("WantedBy=multi-user.target", resume_unit)
        self.assertIn("systemctl enable hysteria2-panel-restore-resume.service", source)
        self.assertNotIn("systemctl enable hysteria2-panel-restore-recover.service", source)
        self.assertIn("hysteria2-panel-restore-resume.service", source)

    def test_installer_refuses_to_mutate_an_unfinished_restore_transaction(self):
        source = INSTALLER.read_text()

        self.assertIn("RESTORE_ACTIVE_MARKER=/etc/hysteria2-panel/.restore-active", source)
        self.assertIn(
            "RESTORE_PENDING_ARCHIVE=/var/lib/hysteria2-panel/backup-restore/pending-restore.zip",
            source,
        )
        self.assertIn(
            "RESTORE_CAPTURED_ARCHIVE=/etc/hysteria2-panel/.restore-active.archive",
            source,
        )
        helper = source[
            source.index("assert_no_pending_restore_state()") : source.index(
                "\n\nlegacy_restore_unit_is_quiescent()"
            )
        ]
        self.assertIn('[[ -e "${RESTORE_ACTIVE_MARKER}"', helper)
        self.assertIn('[[ -e "${RESTORE_CAPTURED_ARCHIVE}"', helper)
        self.assertIn('[[ -e "${RESTORE_PENDING_ARCHIVE}"', helper)
        self.assertIn("hysteria2-panel-restore-recover.service", helper)
        self.assertIn("hysteria2-panel-restore.service", helper)
        main = source.split('if [[ "${1:-}" == "--help"', 1)[1]
        self.assertIn(
            "for command_name in awk flock id install mkdir mktemp mv rm rmdir stat sync systemctl",
            main,
        )
        lock_index = main.index("acquire_maintenance_lock")
        first_gate = main.index("assert_no_pending_restore_state", lock_index)
        guard = main.index("guard_legacy_restore_admission", first_gate)
        second_gate = main.index("assert_no_pending_restore_state", guard)
        dependency_install = main.index("install_system_dependencies", second_gate)
        self.assertLess(lock_index, first_gate)
        self.assertLess(first_gate, guard)
        self.assertLess(guard, second_gate)
        self.assertLess(second_gate, dependency_install)
        self.assertLess(second_gate, main.index('TMP_DIR="$(TMPDIR=/tmp mktemp', second_gate))

    def test_installer_refuses_to_mutate_an_unfinished_egress_transaction(self):
        source = INSTALLER.read_text()
        self.assertIn(
            "EGRESS_TRANSACTION_MARKER=/etc/hysteria2-panel/.egress-transaction.json",
            source,
        )
        helper = source[
            source.index("assert_no_pending_egress_state()") : source.index(
                "\n\nlegacy_restore_unit_is_quiescent()"
            )
        ]
        self.assertIn('[[ -e "${EGRESS_TRANSACTION_MARKER}"', helper)
        main = source.split('if [[ "${1:-}" == "--help"', 1)[1]
        lock_index = main.index("acquire_maintenance_lock")
        egress_gate = main.index("assert_no_pending_egress_state", lock_index)
        dependency_install = main.index("install_system_dependencies", egress_gate)
        self.assertLess(lock_index, egress_gate)
        self.assertLess(egress_gate, dependency_install)

    def test_maintenance_lock_allows_only_read_only_panel_upload_gating(self):
        source = INSTALLER.read_text()

        self.assertIn(
            'd ${MAINTENANCE_RUNTIME_DIR} 0750 root hy2panel -', source
        )
        self.assertIn(
            'f ${MAINTENANCE_LOCK_FILE} 0640 root hy2panel -', source
        )
        self.assertIn(
            '[[ "${runtime_metadata}" == "0:0:700" || "${runtime_metadata}" == "0:${hy2panel_gid}:750" ]]',
            source,
        )
        self.assertIn(
            '[[ "${lock_metadata}" == "0:0:600" || "${lock_metadata}" == "0:${hy2panel_gid}:640" ]]',
            source,
        )
        self.assertIn(
            "for command_name in awk flock id install mkdir mktemp mv rm rmdir stat sync systemctl",
            source,
        )

    def test_maintenance_lock_is_held_by_a_non_inheritable_supervisor(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index("acquire_maintenance_lock()") : source.index(
                "\n\nreset_maintenance_lock_permissions()"
            )
        ]

        self.assertIn('flock -n -E 75 --close "${MAINTENANCE_LOCK_FILE}"', helper)
        self.assertIn('/bin/bash "$0" --maintenance-lock-held', helper)
        self.assertIn('"${ORIGINAL_ARGS[@]}"', helper)
        self.assertIn(
            "lock_status == 75 && (RECOVER_UPGRADE == 1 || RECOVER_FRESH == 1)", helper
        )
        self.assertIn("安装事务仍由安装器持锁", helper)
        self.assertNotIn('exec 9<>"${MAINTENANCE_LOCK_FILE}"', helper)
        self.assertNotIn("flock -n 9", helper)

    def test_legacy_restore_admission_is_guarded_until_the_old_panel_stops(self):
        source = INSTALLER.read_text()
        helper = source[
            source.index("legacy_restore_unit_is_quiescent()") : source.index(
                "\n\nrecover_interrupted_fresh_install()"
            )
        ]
        script = f"""
set -u
LEGACY_RESTORE_UNIT=hysteria2-panel-restore.service
LEGACY_RESTORE_GUARD_OWNED=0
MANAGED_MARKER="$MARKER"
LEGACY_RESTORE_FRAGMENT="$FRAGMENT"
LEGACY_RESTORE_GUARD_DIR="$GUARD_DIR"
LEGACY_RESTORE_GUARD_DROPIN="$GUARD_DIR/50-hysteria2-panel-install-guard.conf"
{helper}
stat() {{
  case "${{!#}}" in
    "$MARKER"|"$FRAGMENT"|"$LEGACY_RESTORE_GUARD_DROPIN")
      [[ "$MODE" != bad-metadata || "${{!#}}" != "$FRAGMENT" ]] \
        && {{
          if [[ "$MODE" == legacy-0600 && "${{!#}}" == "$FRAGMENT" ]]; then
            printf '0:0:600:1\n'
          else
            printf '0:0:644:1\n'
          fi
        }} || printf '1:1:600:2\n'
      ;;
    "$GUARD_DIR") printf '0:0:755:2\n' ;;
    *) command stat "$@" ;;
  esac
}}
guard_is_loaded() {{
  reloads=0
  [[ ! -f "$CAPTURE" ]] || reloads="$(grep -c '^RELOAD$' "$CAPTURE" || true)"
  case "$MODE" in
    stale-unloaded) [[ -e "$LEGACY_RESTORE_GUARD_DROPIN" && "$reloads" -ge 1 ]] ;;
    stale-empty-cached|stale-absent-cached)
      [[ -e "$LEGACY_RESTORE_GUARD_DROPIN" || "$reloads" -lt 2 ]]
      ;;
    *) [[ -e "$LEGACY_RESTORE_GUARD_DROPIN" ]] ;;
  esac
}}
systemctl() {{
  case "$1:$*" in
    show:*--property=ActiveState*)
      [[ "$MODE" == race && -e "$LEGACY_RESTORE_GUARD_DROPIN" ]] \
        && printf 'active\n' || printf 'inactive\n'
      ;;
    show:*--property=LoadState*) printf 'loaded\n' ;;
    show:*--property=FragmentPath*)
      [[ "$MODE" != foreign-fragment ]] && printf '%s\n' "$FRAGMENT" \
        || printf '/usr/lib/systemd/system/foreign.service\n'
      ;;
    show:*--property=DropInPaths*)
      if [[ "$MODE" == foreign-dropin && ! -e "$LEGACY_RESTORE_GUARD_DROPIN" ]]; then
        printf '/etc/systemd/system/hysteria2-panel-restore.service.d/foreign.conf\n'
      elif guard_is_loaded; then
        printf '%s\n' "$LEGACY_RESTORE_GUARD_DROPIN"
      fi
      ;;
    show:*--property=RefuseManualStart*)
      guard_is_loaded && printf 'yes\n' || printf 'no\n'
      ;;
    list-jobs:*) : ;;
    daemon-reload:*) printf 'RELOAD\n' >> "$CAPTURE" ;;
    start:*)
      if [[ "$MODE" == start-allowed ]]; then
        printf 'STARTED\n' >> "$CAPTURE"
        return 0
      fi
      printf 'REFUSED\n' >> "$CAPTURE"
      return 1
      ;;
    *) return 2 ;;
  esac
}}
if guard_legacy_restore_admission; then
  status=0
else
  status=$?
fi
if [[ "$MODE" == tampered-guard && "$status" == 0 ]]; then
  printf '[Unit]\nRefuseManualStart=no\n' > "$LEGACY_RESTORE_GUARD_DROPIN"
fi
release_legacy_restore_guard || status=3
exit "$status"
"""
        for mode, expected_status, expected_calls in (
            ("clean", 0, ["RELOAD", "REFUSED", "RELOAD"]),
            ("legacy-0600", 0, ["RELOAD", "REFUSED", "RELOAD"]),
            ("stale-owned", 0, ["RELOAD", "REFUSED", "RELOAD"]),
            ("stale-unloaded", 0, ["RELOAD", "REFUSED", "RELOAD"]),
            ("stale-empty-cached", 0, ["RELOAD", "REFUSED", "RELOAD"]),
            ("stale-absent-cached", 0, ["RELOAD", "REFUSED", "RELOAD"]),
            ("race", 1, ["RELOAD", "REFUSED", "RELOAD"]),
            ("foreign-dropin", 2, []),
            ("foreign-fragment", 2, []),
            ("bad-metadata", 2, []),
            ("symlink-fragment", 2, []),
            ("occupied-guard-dir", 2, []),
            ("start-allowed", 2, ["RELOAD", "STARTED", "RELOAD"]),
            ("tampered-guard", 3, ["RELOAD", "REFUSED"]),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                marker = root / "managed"
                marker.touch()
                fragment = root / "hysteria2-panel-restore.service"
                fragment.write_text("[Service]\nType=oneshot\n")
                if mode == "symlink-fragment":
                    fragment.unlink()
                    fragment.symlink_to(marker)
                guard_dir = root / "run" / "hysteria2-panel-restore.service.d"
                guard_dir.parent.mkdir()
                if mode == "occupied-guard-dir":
                    guard_dir.mkdir()
                    (guard_dir / "foreign.conf").write_text("[Unit]\n")
                elif mode in {"stale-owned", "stale-unloaded"}:
                    guard_dir.mkdir()
                    (guard_dir / "50-hysteria2-panel-install-guard.conf").write_text(
                        "[Unit]\nRefuseManualStart=yes\n"
                    )
                elif mode == "stale-empty-cached":
                    guard_dir.mkdir()
                capture = root / "calls"
                result = subprocess.run(
                    ["bash"],
                    input=script,
                    capture_output=True,
                    text=True,
                    env={
                        **os.environ,
                        "CAPTURE": str(capture),
                        "MARKER": str(marker),
                        "FRAGMENT": str(fragment),
                        "GUARD_DIR": str(guard_dir),
                        "MODE": mode,
                    },
                )
                calls = capture.read_text().splitlines() if capture.exists() else []
                self.assertEqual(expected_status, result.returncode, result.stderr)
                self.assertEqual(expected_calls, calls)
                if mode in {"occupied-guard-dir", "tampered-guard"}:
                    self.assertTrue(guard_dir.exists())
                else:
                    self.assertFalse(guard_dir.exists())
                if mode == "occupied-guard-dir":
                    self.assertEqual(
                        "[Unit]\n", (guard_dir / "foreign.conf").read_text()
                    )

        self.assertNotIn("systemctl mask --runtime", helper)
        self.assertIn("RefuseManualStart=yes", helper)
        self.assertIn("0:0:600:1|0:0:644:1", helper)
        self.assertIn('"${dropin_paths}" != "${LEGACY_RESTORE_GUARD_DROPIN}"', helper)

        early = source.index("acquire_maintenance_lock")
        guard = source.index("guard_legacy_restore_admission", early)
        dependencies = source.index("install_system_dependencies", guard)
        self.assertLess(guard, dependencies)
        stop = source.rindex("stop_panel_preserving_hysteria")
        final_gate = source.index("assert_no_pending_restore_state", stop)
        release = source.index("release_legacy_restore_guard", final_gate)
        self.assertLess(stop, final_gate)
        self.assertLess(final_gate, release)

    def test_installer_adds_a_fixed_root_only_online_update_service(self):
        source = INSTALLER.read_text()

        self.assertIn("hysteria2-panel-update.service", source)
        self.assertIn(
            "/bin/systemctl --no-block start hysteria2-panel-update.service",
            source,
        )
        self.assertIn(
            "ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py apply-update",
            source,
        )
        update_unit = source.split(
            'cat > /etc/systemd/system/hysteria2-panel-update.service <<EOF', 1
        )[1].split("EOF", 1)[0]
        self.assertIn("TimeoutStartSec=25min", update_unit)
        self.assertIn("TimeoutStopSec=15min", update_unit)
        self.assertIn(
            "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK",
            update_unit,
        )
        self.assertNotIn(
            "User=hy2panel\nEnvironmentFile=/etc/hysteria2-panel/panel.env\nExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py apply-update",
            source,
        )


class StreamlinedOnboardingInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = INSTALLER.read_text()

    def test_join_installs_a_persistent_fixed_onboarding_timer(self):
        start = self.source.index("install_join_node()")
        end = self.source.index("\n}\n", start) + 2
        join = self.source[start:end]

        self.assertIn("NODE_ONBOARDING_INSTALLER", join)
        self.assertIn("NODE_ONBOARDING_SERVICE", join)
        self.assertIn("NODE_ONBOARDING_TIMER", join)
        self.assertIn("NODE_ONBOARDING_MARKER", join)
        self.assertIn("ConditionPathExists=", join)
        self.assertIn("--complete-node-onboarding", join)
        self.assertIn("OnUnitActiveSec=30s", join)
        self.assertIn('sha256sum "${NODE_AGENT_CONFIG_DIR}/node-public.der"', join)
        self.assertNotIn("HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN", join)
        self.assertNotIn("server.key", join)

    def test_completion_claims_then_reuses_the_existing_transactional_deployers(self):
        start = self.source.index("complete_node_onboarding()")
        end = self.source.index("\n}\n", start) + 2
        completion = self.source[start:end]

        claim = completion.index("claim-data-plane")
        activate_agent = completion.index("activate_node_agent")
        activate_data_plane = completion.index("activate_data_plane")
        self.assertLess(claim, activate_agent)
        self.assertLess(activate_agent, activate_data_plane)
        self.assertIn("NODE_ONBOARDING_TOKEN_FILE", completion)
        self.assertIn('rm -f -- "${NODE_ONBOARDING_TOKEN_FILE}"', completion)
        self.assertIn("HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN", completion)
        self.assertIn("disable --now --no-block", completion)
        self.assertNotIn("eval ", completion)
        self.assertNotIn("bash -c", completion)

        local_commit = completion.index("inspect_existing_data_plane")
        transaction_gate = completion.index("NODE_DATA_PLANE_TRANSACTION")
        self.assertLess(transaction_gate, local_commit)
        self.assertLess(local_commit, claim)
        self.assertIn("本次仅清理持久完成器", completion)

        dispatch = self.source.split(
            "if (( COMPLETE_NODE_ONBOARDING == 1 )); then", 1
        )[1].split("fi", 1)[0]
        self.assertLess(
            dispatch.index("INSTALL_COMMITTED=1"),
            dispatch.index("complete_node_onboarding"),
        )

    def test_join_rollback_removes_every_owned_onboarding_artifact(self):
        start = self.source.index("rollback_join_node_install()")
        end = self.source.index("\n}\n", start) + 2
        rollback = self.source[start:end]

        for artifact in (
            "NODE_ONBOARDING_SERVICE",
            "NODE_ONBOARDING_TIMER",
            "NODE_ONBOARDING_MARKER",
        ):
            self.assertIn(artifact, rollback)
        self.assertIn("daemon-reload", rollback)

    def test_panel_installs_a_read_only_dns_admission_timer(self):
        service = self.source.split(
            "cat > /etc/systemd/system/hysteria2-panel-node-dns-admission.service <<EOF",
            1,
        )[1].split("EOF", 1)[0]
        timer = self.source.split(
            "cat > /etc/systemd/system/hysteria2-panel-node-dns-admission.timer <<'EOF'",
            1,
        )[1].split("EOF", 1)[0]
        self.assertIn("User=hy2panel", service)
        self.assertIn("reconcile-node-dns", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ReadWritePaths=/var/lib/hysteria2-panel", service)
        self.assertIn("OnUnitActiveSec=30s", timer)
        self.assertIn(
            "systemctl start hysteria2-panel-node-dns-admission.timer",
            self.source,
        )
        self.assertNotIn("CLOUDFLARE_API", service)
        self.assertNotIn("dns_records", service)

    def test_dns_timer_is_covered_by_fresh_and_upgrade_rollback(self):
        self.assertGreaterEqual(
            self.source.count("hysteria2-panel-node-dns-admission.service"),
            12,
        )
        self.assertGreaterEqual(
            self.source.count("hysteria2-panel-node-dns-admission.timer"),
            20,
        )
        self.assertIn(
            '"${BACKUP_DIR}/hysteria2-panel-node-dns-admission.wants"',
            self.source,
        )


class DataPlaneInstallerContractTests(unittest.TestCase):
    def setUp(self):
        self.source = INSTALLER.read_text()
        start = self.source.index("activate_data_plane()")
        self.activation = self.source[
            start:self.source.index("\n}\n", start) + 2
        ]

    def test_explicit_mode_requires_formal_phase2_node_and_zero_write_preflight(self):
        self.assertIn("--activate-data-plane", self.source)
        self.assertIn("ACTIVATE_DATA_PLANE=1", self.source)
        self.assertIn('"${PANEL_REF}" == "v${PANEL_VERSION}"', self.activation)
        for requirement in (
            'require_node_agent_directory "${NODE_AGENT_OPT_DIR}" 755',
            'require_node_agent_directory "${NODE_AGENT_CONFIG_DIR}" 700',
            'require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/node.key" 600',
            'require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/registration.json" 600',
            'systemctl is-active --quiet hysteria2-panel-node-heartbeat.timer',
            'systemctl start hysteria2-panel-node-heartbeat.service',
            'assert_data_plane_paths_unclaimed',
            'assert_data_plane_ports_available',
        ):
            self.assertIn(requirement, self.activation)
        first_mutation = self.activation.index("DATA_PLANE_MUTATED=1")
        self.assertLess(self.activation.index("assert_data_plane_ports_available"), first_mutation)
        self.assertNotIn("configure_firewall", self.activation[:first_mutation])

    def test_downloads_are_version_and_hash_pinned_before_identity_fetch(self):
        for value in (
            'NODE_AGENT_SHA256="',
            'TCP_PROBE_SHA256="',
            'HYSTERIA_SHA_AMD64="',
            'HYSTERIA_SHA_ARM64="',
            'NODE_AGENT_SOURCE_URL=',
            'TCP_PROBE_SOURCE_URL=',
            'HYSTERIA_DATA_PLANE_URL=',
        ):
            self.assertIn(value, self.source)
        self.assertIn('sha256sum --check --status', self.activation)
        self.assertIn('node_agent.py" prepare-data-plane', self.activation)
        self.assertIn('HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN=', self.activation)
        self.assertNotIn('server.crt', self.source.split("usage()", 1)[0])

    def test_transaction_snapshot_and_rollback_touch_only_phase4_owned_paths(self):
        self.assertIn("DATA_PLANE_TRANSACTION_MAGIC=HYSTERIA2_PANEL_NODE_DATA_PLANE_V1", self.source)
        self.assertIn("/var/backups/hysteria2-panel-node", self.source)
        self.assertIn("write_data_plane_backup_manifest", self.activation)
        self.assertIn("rollback_data_plane_activation()", self.source)
        rollback_start = self.source.index("rollback_data_plane_activation()")
        rollback = self.source[
            rollback_start:self.source.index("\n}\n", rollback_start) + 2
        ]
        for preserved in (
            "node.key",
            "node-public.der",
            "registration.json",
            "hysteria2-panel-node-heartbeat.timer",
        ):
            self.assertNotIn('rm -f -- "${NODE_AGENT_CONFIG_DIR}/' + preserved, rollback)
        self.assertNotIn("rm -rf", rollback)
        self.assertNotRegex(rollback, r"rm[^\n]*\*")
        self.assertIn("DATA_PLANE_OWNED_FILES", rollback)
        self.assertIn("DATA_PLANE_OWNED_UNITS", rollback)
        self.assertIn("recover_interrupted_data_plane()", self.source)
        self.assertIn('sha256sum --check --status manifest.sha256', self.source)
        self.assertIn("recover_interrupted_data_plane", self.activation)

    def test_network_optimization_is_inside_the_durable_data_plane_transaction(self):
        self.assertIn(
            "NODE_SYSCTL_FILE=/etc/sysctl.d/99-hysteria2-panel-node.conf",
            self.source,
        )
        self.assertIn("write_data_plane_network_snapshot", self.source)
        self.assertIn("restore_data_plane_network_snapshot", self.source)
        self.assertIn("optimize_data_plane_network_stack", self.activation)
        snapshot = self.activation.index("write_data_plane_backup_manifest")
        armed = self.activation.index("arm_data_plane_transaction")
        mutated = self.activation.index("DATA_PLANE_MUTATED=1")
        optimized = self.activation.index("optimize_data_plane_network_stack")
        self.assertLess(snapshot, armed)
        self.assertLess(armed, mutated)
        self.assertLess(mutated, optimized)

        optimizer_start = self.source.index("optimize_data_plane_network_stack()")
        optimizer = self.source[
            optimizer_start:self.source.index("\n}\n", optimizer_start) + 2
        ]
        for contract in (
            "net.core.rmem_max",
            "net.core.wmem_max",
            "MIN_QUIC_UDP_BUFFER",
            "net.core.default_qdisc=fq",
            "net.ipv4.tcp_congestion_control=bbr",
            "# Managed by Hysteria2-panel data node",
        ):
            self.assertIn(contract, optimizer)
        self.assertIn("MIN_QUIC_UDP_BUFFER=16777216", self.source)

        rollback_start = self.source.index("rollback_data_plane_activation()")
        rollback = self.source[
            rollback_start:self.source.index("\n}\n", rollback_start) + 2
        ]
        restore_start = self.source.index("restore_existing_data_plane()")
        restore = self.source[
            restore_start:self.source.index("\n}\n", restore_start) + 2
        ]
        self.assertIn("restore_data_plane_network_snapshot", rollback)
        self.assertIn("restore_data_plane_network_snapshot", restore)

    def test_network_snapshot_restores_runtime_values_and_removes_a_new_sysctl_file(self):
        start = self.source.index("assert_data_plane_network_stack_claimable()")
        end = self.source.index("\n\nassert_data_plane_paths_unclaimed()", start)
        helpers = self.source[start:end]
        script = f"""
set -euo pipefail
{helpers}
MIN_QUIC_UDP_BUFFER=16777216
DATA_PLANE_BACKUP_DIR="$WORK/backup"
NODE_SYSCTL_FILE="$WORK/99-hysteria2-panel-node.conf"
TMP_DIR="$WORK/tmp"
mkdir -p "$DATA_PLANE_BACKUP_DIR" "$TMP_DIR"
mock_rmem=4194304
mock_wmem=8388608
mock_qdisc=pfifo_fast
mock_cc=cubic
sysctl() {{
  if [[ "$1" == "-n" ]]; then
    case "$2" in
      net.core.rmem_max) echo "$mock_rmem" ;;
      net.core.wmem_max) echo "$mock_wmem" ;;
      net.core.default_qdisc) echo "$mock_qdisc" ;;
      net.ipv4.tcp_congestion_control) echo "$mock_cc" ;;
      net.ipv4.tcp_available_congestion_control) echo "cubic bbr" ;;
      *) return 1 ;;
    esac
    return
  fi
  [[ "$1" == "-w" ]] || return 1
  case "$2" in
    net.core.rmem_max=*) mock_rmem="${{2#*=}}" ;;
    net.core.wmem_max=*) mock_wmem="${{2#*=}}" ;;
    net.core.default_qdisc=*) mock_qdisc="${{2#*=}}" ;;
    net.ipv4.tcp_congestion_control=*) mock_cc="${{2#*=}}" ;;
    *) return 1 ;;
  esac
}}
install() {{
  local source_file="${{@: -2:1}}" destination="${{@: -1}}"
  command cp "$source_file" "$destination"
  command chmod 0644 "$destination"
}}
sync() {{ :; }}
modprobe() {{ :; }}
if ! command -v mapfile >/dev/null 2>&1; then
  mapfile() {{
    local _option="$1" _name="$2" _line
    eval "${{_name}}=()"
    while IFS= read -r _line; do
      eval "${{_name}}+=(\"\${{_line}}\")"
    done
  }}
fi
write_data_plane_network_snapshot
optimize_data_plane_network_stack
printf 'optimized:%s:%s:%s:%s:%s\n' "$mock_rmem" "$mock_wmem" "$mock_qdisc" "$mock_cc" "$(test -f "$NODE_SYSCTL_FILE" && echo present)"
restore_data_plane_network_snapshot
printf 'restored:%s:%s:%s:%s:%s\n' "$mock_rmem" "$mock_wmem" "$mock_qdisc" "$mock_cc" "$(test ! -e "$NODE_SYSCTL_FILE" && echo absent)"
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["bash"],
                input=script,
                text=True,
                capture_output=True,
                env={**os.environ, "WORK": directory},
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("optimized:16777216:16777216:fq:bbr:present", result.stdout)
        self.assertIn("restored:4194304:8388608:pfifo_fast:cubic:absent", result.stdout)

    def test_existing_managed_data_plane_uses_full_transactional_upgrade(self):
        self.assertIn("inspect_existing_data_plane", self.source)
        self.assertIn("DATA_PLANE_EXISTING=1", self.source)
        self.assertIn("stop_existing_data_plane", self.source)
        self.assertIn("restore_existing_data_plane", self.source)
        self.assertIn('if (( DATA_PLANE_EXISTING == 1 )); then', self.activation)
        self.assertIn('assert_existing_data_plane_healthy', self.activation)
        self.assertIn('assert_data_plane_paths_unclaimed', self.activation)
        self.assertIn('assert_data_plane_ports_available', self.activation)

        snapshot_start = self.source.index("write_data_plane_backup_manifest()")
        snapshot = self.source[
            snapshot_start:self.source.index("\n}\n", snapshot_start) + 2
        ]
        for preserved in (
            '"${DATA_PLANE_OWNED_FILES[@]}"',
            '"${DATA_PLANE_OWNED_UNITS[@]}"',
            '"${NODE_AGENT_OPT_DIR}/node_agent.py"',
            "/var/lib/hysteria2-panel-node",
        ):
            self.assertIn(preserved, snapshot)
        self.assertIn("manifest.sha256", snapshot)

        restore_start = self.source.index("restore_existing_data_plane()")
        restore = self.source[
            restore_start:self.source.index("\n}\n", restore_start) + 2
        ]
        self.assertIn("sha256sum --check --status manifest.sha256", restore)
        self.assertIn("systemctl enable --now", restore)
        self.assertNotIn("node.key", restore)
        self.assertNotIn("registration.json", restore)

        rollback_start = self.source.index("rollback_data_plane_activation()")
        rollback = self.source[
            rollback_start:self.source.index("\n}\n", rollback_start) + 2
        ]
        self.assertIn("DATA_PLANE_EXISTING", rollback)
        self.assertIn("restore_existing_data_plane", rollback)

    def test_existing_data_plane_tolerates_only_a_drained_spool_file(self):
        start = self.source.index("inspect_data_plane_state_item()")
        helper = self.source[start:self.source.index("\n}\n", start) + 2]
        script = f"""
set -u
{helper}
NODE_AGENT_STATE_DIR="$WORK/state"
mkdir -p "$NODE_AGENT_STATE_DIR/spool"
touch "$WORK/target"
ln -s "$WORK/target" "$NODE_AGENT_STATE_DIR/spool/replaced.json"
inspect_data_plane_state_item "$NODE_AGENT_STATE_DIR/spool/drained.json"
printf 'drained:%s\n' "$?"
inspect_data_plane_state_item "$NODE_AGENT_STATE_DIR/spool/replaced.json"
printf 'symlink:%s\n' "$?"
inspect_data_plane_state_item "$NODE_AGENT_STATE_DIR/missing.json"
printf 'missing:%s\n' "$?"
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["bash"],
                input=script,
                text=True,
                capture_output=True,
                env={**os.environ, "WORK": directory},
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("drained:2", result.stdout)
        self.assertIn("symlink:1", result.stdout)
        self.assertIn("missing:1", result.stdout)
        health_start = self.source.index("assert_existing_data_plane_healthy()")
        health = self.source[
            health_start:self.source.index("\n}\n", health_start) + 2
        ]
        self.assertIn("inspect_data_plane_state_item", health)

    def test_six_services_are_sandboxed_and_stats_secret_is_not_persisted_in_yaml(self):
        units = (
            "hysteria2-panel-node-auth.service",
            "hysteria2-panel-node-control.service",
            "hysteria2-panel-node-hysteria-main.service",
            "hysteria2-panel-node-hysteria-udp443.service",
            "hysteria2-panel-node-tcp-probe-main.service",
            "hysteria2-panel-node-tcp-probe-udp443.service",
        )
        for unit in units:
            self.assertIn(unit, self.activation)
        self.assertGreaterEqual(self.activation.count("NoNewPrivileges=true"), 6)
        self.assertGreaterEqual(self.activation.count("ProtectSystem=strict"), 6)
        self.assertGreaterEqual(
            self.activation.count("WantedBy=multi-user.target"), 6
        )
        self.assertIn("EnvironmentFile=${NODE_AGENT_CONFIG_DIR}/stats.env", self.activation)
        self.assertIn('node_agent.py run-hysteria', self.activation)
        self.assertIn("RuntimeDirectory=hysteria2-panel-node-main", self.activation)
        self.assertIn("RuntimeDirectory=hysteria2-panel-node-udp443", self.activation)
        self.assertIn(
            "--runtime-config /run/hysteria2-panel-node-main/config.yaml",
            self.activation,
        )
        self.assertIn(
            "--runtime-config /run/hysteria2-panel-node-udp443/config.yaml",
            self.activation,
        )
        self.assertIn("CapabilityBoundingSet=CAP_NET_BIND_SERVICE", self.activation)
        self.assertIn("AmbientCapabilities=CAP_NET_BIND_SERVICE", self.activation)
        self.assertIn("--stats-url http://127.0.0.1:19997", self.activation)
        self.assertIn("--stats-url http://127.0.0.1:19995", self.activation)
        self.assertIn("__HY2PANEL_STATS_SECRET__", (ROOT / "node_agent.py").read_text())

    def test_auth_proxy_outage_does_not_stop_established_data_plane_sessions(self):
        self.assertEqual(
            0,
            self.activation.count(
                "Requires=hysteria2-panel-node-auth.service"
            ),
        )
        self.assertGreaterEqual(
            self.activation.count(
                "After=network-online.target hysteria2-panel-node-auth.service"
            ),
            1,
        )
        self.assertGreaterEqual(
            self.activation.count(
                "After=network-online.target hysteria2-panel-node-auth.service "
                "hysteria2-panel-node-control.service"
            ),
            2,
        )

    def test_ack_occurs_only_after_services_stats_and_all_four_listeners(self):
        ack = self.activation.index('node_agent.py" ack-data-plane')
        parsed_port = self.activation.index("read_data_plane_main_port")
        transaction = self.activation.index("write_data_plane_backup_manifest")
        self.assertLess(parsed_port, transaction)
        self.assertIn(
            'tcp_probe.py ${DATA_PLANE_MAIN_PORT}', self.activation
        )
        self.assertIn(
            'for port in 443 19995 19996 19997 "${DATA_PLANE_MAIN_PORT}"',
            self.source,
        )
        for check in (
            "systemctl is-active --quiet hysteria2-panel-node-control.service",
            'ss -H -lun "sport = :${DATA_PLANE_MAIN_PORT}"',
            'ss -H -lun "sport = :443"',
            'ss -H -ltn "sport = :${DATA_PLANE_MAIN_PORT}"',
            'ss -H -ltn "sport = :443"',
        ):
            self.assertIn(check, self.activation)
            self.assertLess(self.activation.index(check), ack)
        self.assertIn('source "${NODE_AGENT_CONFIG_DIR}/stats.env"', self.activation)
        self.assertNotIn("vpn.example.com", self.activation)
        self.assertNotIn("cloudflare", self.activation.lower())
        self.assertNotIn("HY2PANEL_HMAC_KEY", self.activation)

    def test_firewall_changes_are_narrow_attributed_and_rollback_recorded(self):
        self.assertIn("configure_data_plane_firewall", self.activation)
        self.assertIn("data-plane-firewall.state", self.source)
        firewall_start = self.source.index("configure_data_plane_firewall()")
        firewall = self.source[
            firewall_start:self.source.index("\n}\n", firewall_start) + 2
        ]
        self.assertIn('for protocol in tcp udp', firewall)
        self.assertIn('for port in 443 "${DATA_PLANE_MAIN_PORT}"', firewall)
        self.assertIn("Hysteria2-panel-node data-plane", firewall)
        for guard in (
            "firewalld_has_global_conflicts",
            "read_firewalld_zones",
            "firewalld_zone_has_complex_rules",
            "ufw_has_framework_customization",
            "ufw_has_unmanaged_live_rules",
            "ufw_rule_is_denied",
            "ufw_rule_is_recorded",
            "has_unmanaged_firewall_restrictions",
            "firewalld-${scope}",
        ):
            self.assertIn(guard, firewall)
        rollback_start = self.source.index("rollback_data_plane_firewall()")
        rollback = self.source[
            rollback_start:self.source.index("\n}\n", rollback_start) + 2
        ]
        remove_start = self.source.index("remove_data_plane_firewall_rule()")
        remove = self.source[
            remove_start:self.source.index("\n}\n", remove_start) + 2
        ]
        self.assertIn("--remove-port", remove)
        self.assertIn("firewalld-runtime", remove)
        self.assertIn("firewalld-permanent", remove)
        self.assertIn("ufw --force delete allow", remove)
        self.assertIn("--query-port", remove)
        self.assertIn("ufw show added", remove)
        self.assertIn("remove_data_plane_firewall_rule", rollback)
        self.assertIn("failed=1", rollback)
        self.assertIn("rollback_data_plane_firewall", self.source.split("rollback_data_plane_activation()", 1)[1])

    def test_existing_data_plane_rollback_removes_only_new_firewall_rules(self):
        delta_start = self.source.index("rollback_new_data_plane_firewall_rules()")
        delta = self.source[
            delta_start:self.source.index("\n}\n", delta_start) + 2
        ]
        self.assertIn("validate_data_plane_firewall_state", delta)
        self.assertIn("config/data-plane-firewall.state", delta)
        self.assertIn('grep -Fqx -- "${rule}" "${backup_state}"', delta)
        self.assertIn("remove_data_plane_firewall_rule", delta)

        restore_start = self.source.index("restore_existing_data_plane()")
        restore = self.source[
            restore_start:self.source.index("\n}\n", restore_start) + 2
        ]
        verify = restore.index("sha256sum --check --status manifest.sha256")
        remove_delta = restore.index("rollback_new_data_plane_firewall_rules")
        overwrite = restore.index("durable_replace_file")
        self.assertLess(verify, remove_delta)
        self.assertLess(remove_delta, overwrite)


class TcpProbeTests(unittest.TestCase):
    def test_probe_accepts_tcp_connections_without_sending_application_data(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]

        process = subprocess.Popen(
            [sys.executable, str(TCP_PROBE), str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 3
            while True:
                try:
                    connection = socket.create_connection(("127.0.0.1", port), timeout=0.2)
                    break
                except OSError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        stdout, stderr = process.communicate(timeout=1)
                        self.fail(f"TCP probe did not start: {stdout}{stderr}")
                    time.sleep(0.05)

            with connection:
                connection.settimeout(1)
                self.assertEqual(b"", connection.recv(1))
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            process.communicate()


if __name__ == "__main__":
    unittest.main()
