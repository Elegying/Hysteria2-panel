#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  echo "installer E2E must run as root" >&2
  exit 1
fi
if [[ "$(ps -p 1 -o comm= | tr -d '[:space:]')" != "systemd" ]]; then
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
    hysteria2-panel-upgrade-recover.service \
    hysteria2-panel-upgrade-verify.service \
    hysteria2-panel.service hysteria2-panel-server.service >&2
  journalctl --no-pager -n 200 \
    -u hysteria2-panel-upgrade-recover.service \
    -u hysteria2-panel-upgrade-verify.service \
    -u hysteria2-panel.service -u hysteria2-panel-server.service >&2
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

bash /workspace/install.sh
systemctl is-active --quiet hysteria2-panel.service
systemctl is-active --quiet hysteria2-panel-server.service
systemctl is-active --quiet hysteria2-panel-tcp-probe.service
curl -fsS "http://127.0.0.1:${PANEL_PORT}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${PANEL_PORT}/readyz" >/dev/null
grep -Fxq 'HY2PANEL_EGRESS_POLICY=full' /etc/hysteria2-panel/panel.env
test ! -e /var/backups/hysteria2-panel/.upgrade-active

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
curl -fsS "http://127.0.0.1:${PANEL_PORT}/healthz" >/dev/null
curl -fsS "http://127.0.0.1:${PANEL_PORT}/readyz" >/dev/null
[[ "$(sha256sum /opt/hysteria2-panel/bin/hysteria | awk '{print $1}')" == "${old_hysteria_sha}" ]]
grep -Fxq 'HY2PANEL_EGRESS_POLICY=full' /etc/hysteria2-panel/panel.env
find /var/backups/hysteria2-panel -mindepth 2 -maxdepth 2 \
  -name backup-manifest.json -type f -print -quit | grep -q .

echo "full install, managed upgrade, SIGKILL recovery and health verification: PASS"
