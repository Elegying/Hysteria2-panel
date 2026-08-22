#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  echo "installer E2E must run as root" >&2
  exit 1
fi
pid1_comm=""
IFS= read -r pid1_comm < /proc/1/comm || true
if [[ "${pid1_comm}" != "systemd" ]]; then
  echo "installer E2E requires systemd as PID 1" >&2
  exit 1
fi
if [[ -z "${PANEL_REF:-}" ]]; then
  echo "PANEL_REF must identify the pushed source commit" >&2
  exit 1
fi

report_error() {
  local status="$1" line="$2"
  trap - ERR
  set +e
  echo "installer E2E failed at line ${line} (status ${status})" >&2
  systemctl --no-pager --full status \
    hysteria2-panel-install-recover.service \
    hysteria2-panel-upgrade-recover.service \
    hysteria2-panel-upgrade-verify.service \
    hysteria2-panel.service \
    hysteria2-panel-server.service \
    hysteria2-panel-tcp-probe.service \
    hysteria2-panel-server-443.service \
    hysteria2-panel-tcp-probe-443.service >&2
  journalctl --no-pager -n 200 \
    -u hysteria2-panel-install-recover.service \
    -u hysteria2-panel-upgrade-recover.service \
    -u hysteria2-panel-upgrade-verify.service \
    -u hysteria2-panel.service \
    -u hysteria2-panel-server.service \
    -u hysteria2-panel-tcp-probe.service \
    -u hysteria2-panel-server-443.service \
    -u hysteria2-panel-tcp-probe-443.service >&2
  exit "${status}"
}
trap 'report_error "$?" "$LINENO"' ERR

export NODE_NAME="CI full installer"
export PUBLIC_HOST=127.0.0.1
export HYSTERIA_PORT=31999
export PANEL_PORT=31998
export AUTH_PORT=31996
export STATS_PORT=31997
export STATS_443_PORT=31995
export PANEL_SCHEME=http
export EGRESS_POLICY=full
export ADMIN_USER=ci-admin
export ADMIN_PASSWORD='ci-only-password-42'

awk '
  { print }
  $0 == "  install_fresh_recovery_infrastructure" {
    print "kill -KILL \"$$\""
  }
' /workspace/install.sh > /workspace/install-fresh-orphan-crash.sh
chmod 0755 /workspace/install-fresh-orphan-crash.sh
if bash /workspace/install-fresh-orphan-crash.sh; then
  orphan_crash_status=0
else
  orphan_crash_status=$?
fi
[[ "${orphan_crash_status}" == "137" ]]
test ! -e /etc/.hysteria2-panel-installing-by-installer
test -f /etc/systemd/system/hysteria2-panel-install-recover.service
test -f /var/backups/hysteria2-panel/.install-recover.sh

awk '
  { print }
  $0 == "  install_fresh_recovery_gate" {
    print "kill -KILL \"$$\""
  }
' /workspace/install.sh > /workspace/install-fresh-crash.sh
chmod 0755 /workspace/install-fresh-crash.sh
if bash /workspace/install-fresh-crash.sh; then
  fresh_crash_status=0
else
  fresh_crash_status=$?
fi
[[ "${fresh_crash_status}" == "137" ]]
test -f /etc/.hysteria2-panel-installing-by-installer
test -f /etc/systemd/system/hysteria2-panel-install-recover.service
test -f /etc/systemd/system/hysteria2-panel.service.d/05-fresh-install-recovery.conf
test -f /etc/systemd/system/hysteria2-panel-server.service.d/05-fresh-install-recovery.conf
test -f /etc/systemd/system/hysteria2-panel-server-443.service.d/05-fresh-install-recovery.conf
test -L /etc/systemd/system/multi-user.target.wants/hysteria2-panel-install-recover.service

awk '
  { print }
  $0 == "  rm -f -- \"${UPGRADE_RECOVERY_DROPIN}\"" {
    print "  kill -KILL \"$$\""
  }
' /var/backups/hysteria2-panel/.install-recover.sh \
  > /workspace/install-fresh-recovery-crash.sh
install -o root -g root -m 0700 /workspace/install-fresh-recovery-crash.sh \
  /var/backups/hysteria2-panel/.install-recover.sh
systemctl daemon-reload
if systemctl start hysteria2-panel-install-recover.service; then
  recovery_crash_status=0
else
  recovery_crash_status=$?
fi
(( recovery_crash_status != 0 ))
test -f /etc/.hysteria2-panel-installing-by-installer
test -f /etc/systemd/system/hysteria2-panel-install-recover.service
test -L /etc/systemd/system/multi-user.target.wants/hysteria2-panel-install-recover.service
test -f /etc/systemd/system/hysteria2-panel.service.d/05-fresh-install-recovery.conf
awk '
  { print }
  $0 == "  durable_remove_file \"${FRESH_IN_PROGRESS_MARKER}\" || return 1" {
    print "  kill -KILL \"$$\""
  }
' /workspace/install.sh > /workspace/install-fresh-disarm-crash.sh
install -o root -g root -m 0700 /workspace/install-fresh-disarm-crash.sh \
  /var/backups/hysteria2-panel/.install-recover.sh
systemctl reset-failed hysteria2-panel-install-recover.service
if systemctl start hysteria2-panel-install-recover.service; then
  disarm_crash_status=0
else
  disarm_crash_status=$?
fi
(( disarm_crash_status != 0 ))
test ! -e /etc/.hysteria2-panel-installing-by-installer
test -f /etc/systemd/system/hysteria2-panel-install-recover.service
test -L /etc/systemd/system/multi-user.target.wants/hysteria2-panel-install-recover.service
test -f /etc/systemd/system/hysteria2-panel.service.d/05-fresh-install-recovery.conf
test ! -e /opt/hysteria2-panel
test ! -e /etc/hysteria2-panel
test ! -e /var/lib/hysteria2-panel
test ! -e /etc/sysctl.d/99-hysteria2-panel.conf
if systemctl is-active --quiet hysteria2-panel.service; then
  exit 1
fi
if systemctl is-active --quiet hysteria2-panel-server.service; then
  exit 1
fi

bash /workspace/install.sh
systemctl is-active --quiet hysteria2-panel.service
systemctl is-active --quiet hysteria2-panel-server.service
systemctl is-active --quiet hysteria2-panel-tcp-probe.service
curl -fsS "http://127.0.0.1:${PANEL_PORT}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${PANEL_PORT}/readyz" >/dev/null
grep -Fxq 'HY2PANEL_EGRESS_POLICY=full' /etc/hysteria2-panel/panel.env
test ! -e /var/backups/hysteria2-panel/.upgrade-active
test ! -e /etc/.hysteria2-panel-installing-by-installer
test ! -e /etc/systemd/system/hysteria2-panel-install-recover.service
test ! -e /etc/systemd/system/hysteria2-panel.service.d/05-fresh-install-recovery.conf
test ! -e /etc/systemd/system/hysteria2-panel-server.service.d/05-fresh-install-recovery.conf
test ! -e /etc/systemd/system/hysteria2-panel-server-443.service.d/05-fresh-install-recovery.conf
test ! -e /var/backups/hysteria2-panel/.install-recover.sh

panel_pid_before="$(systemctl show --property=MainPID --value hysteria2-panel.service)"
server_pid_before="$(systemctl show --property=MainPID --value hysteria2-panel-server.service)"
secondary_pid_before=""
if systemctl is-active --quiet hysteria2-panel-server-443.service; then
  secondary_pid_before="$(systemctl show --property=MainPID --value hysteria2-panel-server-443.service)"
  [[ "${secondary_pid_before}" =~ ^[1-9][0-9]*$ ]]
fi
[[ "${panel_pid_before}" =~ ^[1-9][0-9]*$ ]]
[[ "${server_pid_before}" =~ ^[1-9][0-9]*$ ]]
systemctl kill --kill-who=main --signal=SIGKILL hysteria2-panel.service
for _attempt in $(seq 1 120); do
  panel_pid_after="$(systemctl show --property=MainPID --value hysteria2-panel.service)"
  if [[ "${panel_pid_after}" =~ ^[1-9][0-9]*$ && \
    "${panel_pid_after}" != "${panel_pid_before}" ]] && \
    curl -fsS "http://127.0.0.1:${PANEL_PORT}/readyz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
[[ "${panel_pid_after}" =~ ^[1-9][0-9]*$ ]]
[[ "${panel_pid_after}" != "${panel_pid_before}" ]]
systemctl is-active --quiet hysteria2-panel.service
systemctl is-active --quiet hysteria2-panel-server.service
systemctl is-active --quiet hysteria2-panel-tcp-probe.service
[[ "$(systemctl show --property=MainPID --value hysteria2-panel-server.service)" == "${server_pid_before}" ]]
if [[ -n "${secondary_pid_before}" ]]; then
  systemctl is-active --quiet hysteria2-panel-server-443.service
  systemctl is-active --quiet hysteria2-panel-tcp-probe-443.service
  [[ "$(systemctl show --property=MainPID --value hysteria2-panel-server-443.service)" == "${secondary_pid_before}" ]]
fi

watchdog_panel_pid_before="$(systemctl show --property=MainPID --value hysteria2-panel.service)"
watchdog_server_pid_before="$(systemctl show --property=MainPID --value hysteria2-panel-server.service)"
watchdog_secondary_pid_before=""
if systemctl is-active --quiet hysteria2-panel-server-443.service; then
  watchdog_secondary_pid_before="$(systemctl show --property=MainPID --value hysteria2-panel-server-443.service)"
  [[ "${watchdog_secondary_pid_before}" =~ ^[1-9][0-9]*$ ]]
fi
[[ "${watchdog_panel_pid_before}" =~ ^[1-9][0-9]*$ ]]
[[ "${watchdog_server_pid_before}" =~ ^[1-9][0-9]*$ ]]
systemctl kill --kill-who=main --signal=SIGSTOP hysteria2-panel.service
systemctl is-active --quiet hysteria2-panel-server.service
[[ "$(systemctl show --property=MainPID --value hysteria2-panel-server.service)" == "${watchdog_server_pid_before}" ]]
sleep 40
# SIGCONT also makes the test bounded on systems that queue WatchdogSignal=SIGABRT
# while the deliberately hung process is stopped.
kill -CONT "${watchdog_panel_pid_before}" >/dev/null 2>&1 || true
watchdog_panel_pid_after=""
for _attempt in $(seq 1 120); do
  watchdog_panel_pid_after="$(systemctl show --property=MainPID --value hysteria2-panel.service)"
  if [[ "${watchdog_panel_pid_after}" =~ ^[1-9][0-9]*$ && \
    "${watchdog_panel_pid_after}" != "${watchdog_panel_pid_before}" ]] && \
    curl -fsS "http://127.0.0.1:${PANEL_PORT}/readyz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
[[ "${watchdog_panel_pid_after}" =~ ^[1-9][0-9]*$ ]]
[[ "${watchdog_panel_pid_after}" != "${watchdog_panel_pid_before}" ]]
systemctl is-active --quiet hysteria2-panel.service
systemctl is-active --quiet hysteria2-panel-server.service
systemctl is-active --quiet hysteria2-panel-tcp-probe.service
[[ "$(systemctl show --property=MainPID --value hysteria2-panel-server.service)" == "${watchdog_server_pid_before}" ]]
if [[ -n "${watchdog_secondary_pid_before}" ]]; then
  systemctl is-active --quiet hysteria2-panel-server-443.service
  systemctl is-active --quiet hysteria2-panel-tcp-probe-443.service
  [[ "$(systemctl show --property=MainPID --value hysteria2-panel-server-443.service)" == "${watchdog_secondary_pid_before}" ]]
fi

unset ADMIN_USER ADMIN_PASSWORD
HY2PANEL_AUTO_UPDATE=1 bash /workspace/install.sh
systemctl is-active --quiet hysteria2-panel.service
systemctl is-active --quiet hysteria2-panel-server.service
curl -fsS "http://127.0.0.1:${PANEL_PORT}/readyz" >/dev/null

old_hysteria_sha="$(sha256sum /opt/hysteria2-panel/bin/hysteria | awk '{print $1}')"
awk '
  { print }
  $0 == "install -o root -g root -m 0755 \"${TMP_DIR}/hysteria\" /opt/hysteria2-panel/bin/hysteria" {
    print "printf broken >> /opt/hysteria2-panel/bin/hysteria"
    print "kill -KILL \"$$\""
  }
' /workspace/install.sh > /workspace/install-crash.sh
chmod 0755 /workspace/install-crash.sh
if HY2PANEL_AUTO_UPDATE=1 bash /workspace/install-crash.sh; then
  crash_status=0
else
  crash_status=$?
fi
[[ "${crash_status}" == "137" ]]
test -f /var/backups/hysteria2-panel/.upgrade-active
[[ "$(sha256sum /opt/hysteria2-panel/bin/hysteria | awk '{print $1}')" != "${old_hysteria_sha}" ]]

systemctl start hysteria2-panel-upgrade-recover.service
for _attempt in $(seq 1 120); do
  [[ -e /var/backups/hysteria2-panel/.upgrade-active ]] || break
  sleep 1
done
test ! -e /var/backups/hysteria2-panel/.upgrade-active
systemctl is-active --quiet hysteria2-panel.service
systemctl is-active --quiet hysteria2-panel-server.service
systemctl is-active --quiet hysteria2-panel-tcp-probe.service
if [[ -n "${secondary_pid_before}" ]]; then
  systemctl is-active --quiet hysteria2-panel-server-443.service
  systemctl is-active --quiet hysteria2-panel-tcp-probe-443.service
  listener_output="$(ss -H -lun "sport = :443")"
  [[ -n "${listener_output}" ]]
  listener_output="$(ss -H -ltn "sport = :443")"
  [[ -n "${listener_output}" ]]
  listener_output="$(ss -H -ltn "sport = :${STATS_443_PORT}")"
  [[ -n "${listener_output}" ]]
fi
curl -fsS "http://127.0.0.1:${PANEL_PORT}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${PANEL_PORT}/readyz" >/dev/null
[[ "$(sha256sum /opt/hysteria2-panel/bin/hysteria | awk '{print $1}')" == "${old_hysteria_sha}" ]]
grep -Fxq 'HY2PANEL_EGRESS_POLICY=full' /etc/hysteria2-panel/panel.env
find /var/backups/hysteria2-panel -mindepth 2 -maxdepth 2 \
  -name backup-manifest.json -type f -print -quit | grep -q .

echo "fresh-install/upgrade SIGKILL recovery, watchdog restart and health verification: PASS"
