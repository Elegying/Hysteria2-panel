#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  echo "systemd integration test must run as root" >&2
  exit 1
fi

if [[ "$(ps -p 1 -o comm= | tr -d '[:space:]')" != "systemd" ]]; then
  echo "systemd is not PID 1" >&2
  exit 1
fi

PANEL_UNIT="hysteria2-panel-ci-panel.service"
SERVER_UNIT="hysteria2-panel-ci-server.service"
RECOVER_UNIT="hysteria2-panel-ci-restore-recover.service"
RESUME_UNIT="hysteria2-panel-ci-restore-resume.service"
LEGACY_RESTORE_UNIT="hysteria2-panel-ci-legacy-restore.service"
PANEL_PATH="/etc/systemd/system/${PANEL_UNIT}"
SERVER_PATH="/etc/systemd/system/${SERVER_UNIT}"
RECOVER_PATH="/etc/systemd/system/${RECOVER_UNIT}"
RESUME_PATH="/etc/systemd/system/${RESUME_UNIT}"
LEGACY_RESTORE_PATH="/etc/systemd/system/${LEGACY_RESTORE_UNIT}"
LEGACY_RESTORE_GUARD_DIR="/run/systemd/system/${LEGACY_RESTORE_UNIT}.d"
LEGACY_RESTORE_GUARD_DROPIN="${LEGACY_RESTORE_GUARD_DIR}/50-hysteria2-panel-install-guard.conf"
LEGACY_RESTORE_CAPTURE="/run/hysteria2-panel-ci-legacy-restore-started"
RESUME_MARKER="/run/hysteria2-panel-ci-restore-active"
RESUME_CAPTURE="/run/hysteria2-panel-ci-resume-capture"
RECOVER_FAILURE="/run/hysteria2-panel-ci-recover-failure"

report_error() {
  local status="$1" line="$2"
  trap - ERR
  set +e
  echo "systemd integration failed at line ${line} (status ${status})" >&2
  systemctl --no-pager --full status \
    "${RECOVER_UNIT}" "${PANEL_UNIT}" "${SERVER_UNIT}" "${RESUME_UNIT}" \
    "${LEGACY_RESTORE_UNIT}" >&2
  journalctl --no-pager -n 120 \
    -u "${RECOVER_UNIT}" -u "${PANEL_UNIT}" -u "${SERVER_UNIT}" \
    -u "${RESUME_UNIT}" -u "${LEGACY_RESTORE_UNIT}" >&2
  exit "${status}"
}

cleanup() {
  local status=$?
  trap - EXIT
  set +e
  systemctl disable "${RESUME_UNIT}" >/dev/null 2>&1
  systemctl stop "${RESUME_UNIT}" "${SERVER_UNIT}" "${PANEL_UNIT}" "${RECOVER_UNIT}" \
    "${LEGACY_RESTORE_UNIT}" >/dev/null 2>&1
  rm -f -- "${SERVER_PATH}" "${PANEL_PATH}" "${RECOVER_PATH}" "${RESUME_PATH}" \
    "${LEGACY_RESTORE_PATH}" "${LEGACY_RESTORE_GUARD_DROPIN}" \
    "${LEGACY_RESTORE_CAPTURE}" "${RESUME_MARKER}" "${RESUME_CAPTURE}" "${RECOVER_FAILURE}"
  rmdir -- "${LEGACY_RESTORE_GUARD_DIR}" >/dev/null 2>&1 || true
  systemctl daemon-reload >/dev/null 2>&1
  exit "${status}"
}
trap cleanup EXIT
trap 'report_error "$?" "$LINENO"' ERR

cat >"${PANEL_PATH}" <<EOF
[Unit]
Description=Hysteria2 panel CI signal target
Requires=${RECOVER_UNIT}
After=${RECOVER_UNIT}

[Service]
Type=simple
ExecStart=/bin/sleep infinity
Restart=on-failure
EOF

cat >"${SERVER_PATH}" <<EOF
[Unit]
Description=Hysteria2 server CI dependency probe
Requires=${PANEL_UNIT}
After=${PANEL_UNIT}

[Service]
Type=simple
ExecStart=/bin/sleep infinity
EOF

cat >"${RECOVER_PATH}" <<EOF
[Unit]
Description=Hysteria2 restore pre-start recovery probe
Before=${PANEL_UNIT} ${SERVER_UNIT}

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'printf pre >> ${RESUME_CAPTURE}; test ! -e ${RECOVER_FAILURE}'
EOF

cat >"${RESUME_PATH}" <<EOF
[Unit]
Description=Hysteria2 restore post-start health probe
After=${PANEL_UNIT} ${SERVER_UNIT}
Wants=${PANEL_UNIT} ${SERVER_UNIT}
ConditionPathExists=${RESUME_MARKER}

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'systemctl is-active --quiet ${PANEL_UNIT} && systemctl is-active --quiet ${SERVER_UNIT} && printf post >> ${RESUME_CAPTURE} && rm -f ${RESUME_MARKER}'

[Install]
WantedBy=multi-user.target
EOF

cat >"${LEGACY_RESTORE_PATH}" <<EOF
[Unit]
Description=Hysteria2 legacy restore admission probe

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'printf started > ${LEGACY_RESTORE_CAPTURE}'
RemainAfterExit=yes
EOF

chmod 0644 "${PANEL_PATH}" "${SERVER_PATH}" "${RECOVER_PATH}" "${RESUME_PATH}"
chmod 0600 "${LEGACY_RESTORE_PATH}"
systemctl daemon-reload
systemctl show "${PANEL_UNIT}" --property=Requires --value \
  | tr ' ' '\n' | grep -Fxq "${RECOVER_UNIT}"
systemctl show "${PANEL_UNIT}" --property=After --value \
  | tr ' ' '\n' | grep -Fxq "${RECOVER_UNIT}"
systemctl enable "${RESUME_UNIT}"
systemctl start "${SERVER_UNIT}"
systemctl is-active --quiet "${PANEL_UNIT}"
systemctl is-active --quiet "${SERVER_UNIT}"

# A runtime RefuseManualStart drop-in can guard an /etc local unit without
# replacing its persistent fragment. The refusal must create neither a process
# nor a queued/running start job, and removing /run state must restore it.
[[ "$(systemctl show "${LEGACY_RESTORE_UNIT}" --property=FragmentPath --value)" == "${LEGACY_RESTORE_PATH}" ]]
[[ "$(systemctl show "${LEGACY_RESTORE_UNIT}" --property=RefuseManualStart --value)" == "no" ]]
mkdir -m 0755 -- "${LEGACY_RESTORE_GUARD_DIR}"
(
  umask 0022
  set -o noclobber
  printf '[Unit]\nRefuseManualStart=yes\n' >"${LEGACY_RESTORE_GUARD_DROPIN}"
)
# This is the SIGKILL window after the exact file is durable but before PID 1
# has explicitly reloaded it. PID 1 may notice the drop-in first, so both the
# not-yet-loaded and already-loaded states are valid and recoverable.
pre_reload_refuse="$(systemctl show "${LEGACY_RESTORE_UNIT}" --property=RefuseManualStart --value)"
pre_reload_dropins="$(systemctl show "${LEGACY_RESTORE_UNIT}" --property=DropInPaths --value)"
if [[ "${pre_reload_refuse}" == "no" ]]; then
  [[ -z "${pre_reload_dropins}" ]]
else
  [[ "${pre_reload_refuse}" == "yes" ]]
  [[ "${pre_reload_dropins}" == "${LEGACY_RESTORE_GUARD_DROPIN}" ]]
fi
systemctl daemon-reload
[[ "$(systemctl show "${LEGACY_RESTORE_UNIT}" --property=RefuseManualStart --value)" == "yes" ]]
[[ "$(systemctl show "${LEGACY_RESTORE_UNIT}" --property=DropInPaths --value)" == "${LEGACY_RESTORE_GUARD_DROPIN}" ]]
if systemctl start "${LEGACY_RESTORE_UNIT}" >/dev/null 2>&1; then
  echo "RefuseManualStart unexpectedly allowed the legacy restore" >&2
  exit 1
fi
[[ ! -e "${LEGACY_RESTORE_CAPTURE}" ]]
[[ "$(systemctl show "${LEGACY_RESTORE_UNIT}" --property=ActiveState --value)" == "inactive" ]]
if systemctl list-jobs --no-legend --no-pager \
  | awk -v unit="${LEGACY_RESTORE_UNIT}" '$2 == unit { found = 1 } END { exit(found ? 0 : 1) }'; then
  echo "legacy restore start left a systemd job behind" >&2
  exit 1
fi
rm -f -- "${LEGACY_RESTORE_GUARD_DROPIN}"
rmdir -- "${LEGACY_RESTORE_GUARD_DIR}"
systemctl daemon-reload
[[ "$(systemctl show "${LEGACY_RESTORE_UNIT}" --property=RefuseManualStart --value)" == "no" ]]
[[ -z "$(systemctl show "${LEGACY_RESTORE_UNIT}" --property=DropInPaths --value)" ]]
systemctl start "${LEGACY_RESTORE_UNIT}"
[[ "$(cat "${LEGACY_RESTORE_CAPTURE}")" == "started" ]]
systemctl stop "${LEGACY_RESTORE_UNIT}"

# Sending SIGTERM to the panel main process is not an explicit stop job. The
# dependent server must remain active while the panel exits cleanly.
systemctl kill --kill-who=main --signal=SIGTERM "${PANEL_UNIT}"
for _attempt in $(seq 1 50); do
  if [[ "$(systemctl show "${PANEL_UNIT}" --property=ActiveState --value)" == "inactive" ]]; then
    break
  fi
  sleep 0.1
done

[[ "$(systemctl show "${PANEL_UNIT}" --property=ActiveState --value)" == "inactive" ]]
systemctl is-active --quiet "${SERVER_UNIT}"

# A persistent restore marker must be consumed before the normal panel/server
# startup transaction is allowed to complete after a reboot.
systemctl stop "${RESUME_UNIT}" "${SERVER_UNIT}" "${PANEL_UNIT}" "${RECOVER_UNIT}"
: >"${RESUME_CAPTURE}"
: >"${RESUME_MARKER}"
timeout 20s systemctl start "${RESUME_UNIT}" "${SERVER_UNIT}"
[[ "$(cat "${RESUME_CAPTURE}")" =~ ^(pre)+post$ ]]
[[ ! -e "${RESUME_MARKER}" ]]
systemctl is-active --quiet "${PANEL_UNIT}"
systemctl is-active --quiet "${SERVER_UNIT}"

# A failed files-only pre-recovery is a required dependency. It must block both
# public services and leave the durable marker for an operator or next boot.
systemctl stop "${RESUME_UNIT}" "${SERVER_UNIT}" "${PANEL_UNIT}" "${RECOVER_UNIT}"
systemctl reset-failed "${RESUME_UNIT}" "${SERVER_UNIT}" "${PANEL_UNIT}" "${RECOVER_UNIT}" >/dev/null 2>&1 || true
: >"${RESUME_MARKER}"
: >"${RECOVER_FAILURE}"
if timeout 20s systemctl start "${RESUME_UNIT}" "${SERVER_UNIT}"; then
  echo "restore pre-recovery failure unexpectedly allowed startup" >&2
  exit 1
fi
[[ -e "${RESUME_MARKER}" ]]
[[ "$(systemctl show "${PANEL_UNIT}" --property=ActiveState --value)" != "active" ]]
[[ "$(systemctl show "${SERVER_UNIT}" --property=ActiveState --value)" != "active" ]]

echo "systemd dependency-preserving panel shutdown: PASS"
echo "systemd two-phase interrupted-restore ordering: PASS"
echo "systemd failed pre-recovery blocks public services: PASS"
echo "systemd legacy restore admission guard: PASS"
