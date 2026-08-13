#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID} -eq 0 ]] || { echo "firewall integration test requires root" >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUNCTIONS="$(sed -n '/^ufw_rule_is_recorded()/,/^optimize_network_stack()/p' "${ROOT}/install.sh" | sed '$d')"
# The extracted source is the exact installer implementation under test.
eval "${FUNCTIONS}"

fail() {
  echo "firewall integration failure: $*" >&2
  exit 1
}

# These globals are consumed indirectly by the extracted installer functions.
# shellcheck disable=SC2034
declare HYSTERIA_PORT=29999 PANEL_PORT=29998 UDP_443_ENABLED=1 PYTHON_BIN=python3
# shellcheck disable=SC2034
declare FIREWALL_MANAGER=unprepared FIREWALL_RESULT="" UFW_ADDED_RULES="" FIREWALLD_HELP=""
# shellcheck disable=SC2034
declare UFW_RULES_PATH=/etc/ufw UFW_TEMPLATE_PATH=/usr/share/ufw/iptables
# shellcheck disable=SC2034
declare -a FIREWALL_RULES=() FIREWALL_ZONES=() FIREWALL_PENDING=() FIREWALL_APPLIED=()
RULES=(29999/tcp 29999/udp 29998/tcp 443/tcp 443/udp)
TEST_TMP="$(mktemp -d /tmp/hysteria2-panel-firewall.XXXXXX)"
LISTENER_PID=""

cleanup() {
  local rule zone
  set +e
  if [[ -n "${LISTENER_PID}" ]]; then
    kill "${LISTENER_PID}" >/dev/null 2>&1
    wait "${LISTENER_PID}" >/dev/null 2>&1
  fi
  iptables -D INPUT -p tcp --dport 29999 -j DROP >/dev/null 2>&1
  if [[ -s "${TEST_TMP}/before.rules" ]]; then
    cp -a "${TEST_TMP}/before.rules" /etc/ufw/before.rules
  fi
  ufw --force disable >/dev/null 2>&1
  ufw --force reset >/dev/null 2>&1
  if firewall-cmd --state >/dev/null 2>&1; then
    zone="$(firewall-cmd --get-default-zone 2>/dev/null)"
    firewall-cmd --direct --remove-rule ipv4 filter INPUT 0 -p tcp --dport 29999 -j DROP >/dev/null 2>&1
    firewall-cmd --direct --remove-chain ipv4 filter H2P_TEST >/dev/null 2>&1
    firewall-cmd --direct --remove-passthrough ipv4 -I INPUT 1 -p tcp --dport 29999 -j DROP >/dev/null 2>&1
    for rule in "${RULES[@]}"; do
      firewall-cmd --quiet --zone="${zone}" --remove-port="${rule}" >/dev/null 2>&1
      firewall-cmd --quiet --permanent --zone="${zone}" --remove-port="${rule}" >/dev/null 2>&1
    done
  fi
  systemctl stop firewalld.service >/dev/null 2>&1
  rm -r -- "${TEST_TMP}"
}
trap cleanup EXIT

python3 - "${TEST_TMP}/listeners.ready" <<'PY' &
import pathlib
import signal
import socket
import sys

sockets = []
for kind, port in (
    (socket.SOCK_STREAM, 29999),
    (socket.SOCK_STREAM, 29998),
    (socket.SOCK_STREAM, 443),
    (socket.SOCK_DGRAM, 29999),
    (socket.SOCK_DGRAM, 443),
):
    listener = socket.socket(socket.AF_INET, kind)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", port))
    if kind == socket.SOCK_STREAM:
        listener.listen()
    sockets.append(listener)
pathlib.Path(sys.argv[1]).touch()
signal.pause()
PY
LISTENER_PID=$!
for _attempt in $(seq 1 50); do
  [[ ! -e "${TEST_TMP}/listeners.ready" ]] || break
  kill -0 "${LISTENER_PID}" 2>/dev/null || fail "test listeners exited before becoming ready"
  sleep 0.1
done
[[ -e "${TEST_TMP}/listeners.ready" ]] || fail "test listeners did not become ready"

expect_prepare_failure() {
  local message="$1"
  if (prepare_firewall) >"${TEST_TMP}/expected.out" 2>"${TEST_TMP}/expected.err"; then
    fail "${message} did not fail closed"
  fi
}

reset_ufw() {
  ufw --force reset >/dev/null
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw --force enable >/dev/null
}

systemctl stop firewalld.service >/dev/null 2>&1 || true
cmp -s /etc/ufw/before.rules /usr/share/ufw/iptables/before.rules
cmp -s /etc/ufw/before6.rules /usr/share/ufw/iptables/before6.rules
cmp -s /etc/ufw/after.rules /usr/share/ufw/iptables/after.rules
cmp -s /etc/ufw/after6.rules /usr/share/ufw/iptables/after6.rules
cp -a /etc/ufw/before.rules "${TEST_TMP}/before.rules"
reset_ufw
prepare_firewall
[[ "${FIREWALL_MANAGER}" == "ufw" ]]
configure_firewall
for rule in "${RULES[@]}"; do
  # shellcheck disable=SC2034
  UFW_ADDED_RULES="$(LC_ALL=C ufw show added)"
  ufw_rule_is_recorded "${rule}"
done
ufw_before="$(LC_ALL=C ufw show added | sha256sum | awk '{print $1}')"
prepare_firewall
configure_firewall
ufw_after="$(LC_ALL=C ufw show added | sha256sum | awk '{print $1}')"
[[ "${ufw_before}" == "${ufw_after}" ]]

reset_ufw
ufw prepend deny 29999/tcp >/dev/null
expect_prepare_failure "UFW prepend deny"

reset_ufw
ufw deny 29000:30000/tcp >/dev/null
expect_prepare_failure "UFW range deny"

reset_ufw
ufw deny proto tcp from any port 29999 to any port 25 >/dev/null
prepare_firewall

reset_ufw
sed -i '/^COMMIT$/i -A ufw-before-input -p tcp --dport 29999 -j DROP' /etc/ufw/before.rules
ufw reload >/dev/null
expect_prepare_failure "UFW before.rules customization"
cp -a "${TEST_TMP}/before.rules" /etc/ufw/before.rules
ufw reload >/dev/null

iptables -I INPUT 1 -p tcp --dport 29999 -j DROP
expect_prepare_failure "UFW unmanaged raw rule"
iptables -D INPUT -p tcp --dport 29999 -j DROP

ufw --force disable >/dev/null
ufw --force reset >/dev/null
# The UFW and firewalld scenarios share only this disposable network namespace.
# Remove UFW's live nft compatibility chains before starting the independent
# firewalld scenario; production correctly rejects both managers coexisting.
nft flush ruleset
systemctl start firewalld.service
[[ "$(read_firewalld_backend)" == "nftables" ]]
zone="$(firewall-cmd --get-default-zone)"
if firewalld_has_global_conflicts; then
  global_status=0
else
  global_status=$?
fi
if (( global_status != 1 )); then
  firewall-cmd --version >&2 || true
  firewall-cmd --get-policies >&2 || true
  firewall-cmd --permanent --get-policies >&2 || true
  PS4='+ firewalld diagnostic ${LINENO}: '
  set -x
  firewalld_has_global_conflicts || global_status=$?
  { set +x; } 2>/dev/null
  fail "default firewalld state was not clean (status ${global_status})"
fi
prepare_firewall
[[ "${FIREWALL_MANAGER}" == "firewalld" ]]
configure_firewall
for rule in "${RULES[@]}"; do
  firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"
  firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"
done
runtime_before="$(firewall-cmd --zone="${zone}" --list-ports | tr ' ' '\n' | sort | sha256sum | awk '{print $1}')"
permanent_before="$(firewall-cmd --permanent --zone="${zone}" --list-ports | tr ' ' '\n' | sort | sha256sum | awk '{print $1}')"
prepare_firewall
configure_firewall
runtime_after="$(firewall-cmd --zone="${zone}" --list-ports | tr ' ' '\n' | sort | sha256sum | awk '{print $1}')"
permanent_after="$(firewall-cmd --permanent --zone="${zone}" --list-ports | tr ' ' '\n' | sort | sha256sum | awk '{print $1}')"
[[ "${runtime_before}" == "${runtime_after}" ]]
[[ "${permanent_before}" == "${permanent_after}" ]]

firewall-cmd --direct --add-chain ipv4 filter H2P_TEST >/dev/null
expect_prepare_failure "firewalld direct chain"
firewall-cmd --direct --remove-chain ipv4 filter H2P_TEST >/dev/null

firewall-cmd --direct --add-rule ipv4 filter INPUT 0 -p tcp --dport 29999 -j DROP >/dev/null
expect_prepare_failure "firewalld direct rule"
firewall-cmd --direct --remove-rule ipv4 filter INPUT 0 -p tcp --dport 29999 -j DROP >/dev/null

firewall-cmd --direct --passthrough ipv4 -I INPUT 1 -p tcp --dport 29999 -j DROP >/dev/null
expect_prepare_failure "firewalld untracked passthrough"
firewall-cmd --direct --passthrough ipv4 -D INPUT -p tcp --dport 29999 -j DROP >/dev/null

echo "managed firewall integration checks passed"
