#!/usr/bin/env bash
# Deliberately omit errtrace (-E): the root EXIT finalizer owns exactly one
# rollback for failures in functions, subshells, substitutions and pipelines.
# Inheriting ERR into child contexts can run stateful rollback diagnostics twice.
set -euo pipefail

PANEL_VERSION="0.37.0"
PANEL_REF="${PANEL_REF:-v${PANEL_VERSION}}"
PANEL_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hysteria2_panel.py"
OFFSITE_BACKUP_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/offsite_backup.py"
QRCODEGEN_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/qrcodegen.py"
TCP_PROBE_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/tcp_probe.py"
HY2PANEL_INIT_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/__init__.py"
HY2PANEL_VERSION_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/version.py"
HY2PANEL_BUDGETS_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/budgets.py"
HY2PANEL_WEB_ASSETS_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/web_assets.py"
HY2PANEL_OPERATIONS_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/operations.py"
HY2PANEL_RELEASE_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/release.py"
HY2PANEL_HEALTH_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/health.py"
HY2PANEL_CERTIFICATE_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/certificate.py"
HY2PANEL_SYSTEMD_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/systemd.py"
HY2PANEL_NODES_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/nodes.py"
HY2PANEL_DISTRIBUTED_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/distributed.py"
HY2PANEL_DASHBOARD_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/dashboard.py"
HY2PANEL_MOBILE_API_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/mobile_api.py"
NODE_AGENT_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/node_agent.py"
PANEL_SHA256="a97ee51991ea6b9805360bf95416e0ec22792caa30a1a02673d4febf389410d8"
OFFSITE_BACKUP_SHA256="631e756b4eba363f21e8e48603d8b672c646576b820699ffbf5d4eed94b2f07f"
QRCODEGEN_SHA256="c204a41677d7e3bbf1834699ced21c7dae7f3fe9b02787cca67388ffd6010b0a"
TCP_PROBE_SHA256="b63da9cc1e58ae3459e188a507d9e71bd205b5f3320448bc319d1f80a21885a2"
HY2PANEL_INIT_SHA256="b525d019edcaa9d90a3b4599650a64d8fb9fde2222f7c2707151318de515b79d"
HY2PANEL_VERSION_SHA256="3f1735ca17a47c5bf9c5f7d2c65f3872f6c81794f49f8d7e91f9bfec803ed6ad"
HY2PANEL_BUDGETS_SHA256="dc4fcb976ee2ad906ba84865f6d3d685a82177a4cca9af35f341d60bf1a83206"
HY2PANEL_WEB_ASSETS_SHA256="eb6faa88e06aa1f291ff7ca95015b3da9ccc79b64ac45be214763bea093c6708"
HY2PANEL_OPERATIONS_SHA256="1efa9e0435aa230db1c3c35371c07bfd5e290cfc3df0aa745bf2b065bed7c614"
HY2PANEL_RELEASE_SHA256="0214c1aad4d8ae9d60f76c540bc71ba9e39f51c1f2caf30c2dee90b13895deb7"
HY2PANEL_HEALTH_SHA256="08f83a4271a2de28172fddfde018c267135ff27c7bf6d802081aa0fc9388ced6"
HY2PANEL_CERTIFICATE_SHA256="018c9be7f68565766f0aee23e3f59ac20029a8c659bae625f061781ab516d5b9"
HY2PANEL_SYSTEMD_SHA256="7ef9075c04f71441f7b9c86fbdcded9f889d9edc10ef907fc1c85ab1144f4bf6"
HY2PANEL_NODES_SHA256="b6d4986c4c8169b7d3bbacc2ae2aefb95e2285b9843afaece58b553c1092e1d0"
HY2PANEL_DISTRIBUTED_SHA256="6cdd694fc13c76a26dd850a42e3a9f3cdd3f1921a836fb378d0148dde408359c"
HY2PANEL_DASHBOARD_SHA256="a1d65d3164e3d6d5b6d4a0e20769d37f784b5e379e57a20932243a221569c548"
HY2PANEL_MOBILE_API_SHA256="d299a1b3684ec9957f54f29d449dd088cb280c9bd746676de9fba95d1980d1a9"
NODE_AGENT_SHA256="9d801b76bab949e4b821b053552e9c8c2204f0b1d27b2ab6ccbe675486f0750e"
HYSTERIA_VERSION="2.12.1"
HYSTERIA_DATA_PLANE_URL="https://github.com/apernet/hysteria/releases/download/app/v${HYSTERIA_VERSION}/hysteria-linux"
HYSTERIA_SHA_AMD64="ffc032c7ca6b78676d337097ca7f61bebc3a90a4f3a656693adf368f304cdbc7"
HYSTERIA_SHA_ARM64="c9cd1af6395eee13a937f429ea71b290e3cc571eea2b4d7f8bc7c49c1d23a792"
COSIGN_VERSION="3.1.3"
COSIGN_SHA_AMD64="4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71"
COSIGN_SHA_ARM64="c5d324e091826b0d7a78eb16fef316450b4eb9aaec045611c08ba06f5e73220a"
DEFAULT_HYSTERIA_PORT=19999
DEFAULT_PANEL_PORT=19998
DEFAULT_STATS_PORT=19997
DEFAULT_AUTH_PORT=19996
DEFAULT_STATS_443_PORT=19995
PANEL_CERT_FILE=/etc/hysteria2-panel/panel.crt
PANEL_KEY_FILE=/etc/hysteria2-panel/panel.key
PANEL_TLS_ROOT=/etc/hysteria2-panel/panel-tls
ACME_CONFIG_DIR=/etc/hysteria2-panel/acme
ACME_WORK_DIR=/var/lib/hysteria2-panel/acme-work
ACME_LOGS_DIR=/var/lib/hysteria2-panel/acme-logs
MIN_QUIC_UDP_BUFFER=16777216
SYSCTL_FILE=/etc/sysctl.d/99-hysteria2-panel.conf
NODE_SYSCTL_FILE=/etc/sysctl.d/99-hysteria2-panel-node.conf
TMPFILES_FILE=/etc/tmpfiles.d/hysteria2-panel.conf
MAINTENANCE_RUNTIME_DIR=/run/hysteria2-panel-maintenance
MAINTENANCE_LOCK_FILE=${MAINTENANCE_RUNTIME_DIR}/lock
EGRESS_SWITCH_ACTIVE_MARKER=${MAINTENANCE_RUNTIME_DIR}/egress-switch-active
MANAGED_MARKER=/etc/hysteria2-panel/.managed-by-installer
NODE_AGENT_OPT_DIR=/opt/hysteria2-panel-node
NODE_AGENT_CONFIG_DIR=/etc/hysteria2-panel-node
NODE_AGENT_STATE_DIR=/var/lib/hysteria2-panel-node
NODE_AGENT_HEARTBEAT_SERVICE=/etc/systemd/system/hysteria2-panel-node-heartbeat.service
NODE_AGENT_HEARTBEAT_TIMER=/etc/systemd/system/hysteria2-panel-node-heartbeat.timer
NODE_ONBOARDING_INSTALLER=${NODE_AGENT_OPT_DIR}/onboarding-install.sh
NODE_ONBOARDING_SERVICE=/etc/systemd/system/hysteria2-panel-node-onboarding.service
NODE_ONBOARDING_TIMER=/etc/systemd/system/hysteria2-panel-node-onboarding.timer
NODE_ONBOARDING_MARKER=${NODE_AGENT_CONFIG_DIR}/.onboarding-pending
NODE_ONBOARDING_RUNTIME_DIR=/run/hysteria2-panel-node-onboarding
NODE_ONBOARDING_TOKEN_FILE=${NODE_ONBOARDING_RUNTIME_DIR}/bootstrap.token
NODE_DATA_PLANE_BACKUP_ROOT=/var/backups/hysteria2-panel-node
NODE_DATA_PLANE_TRANSACTION=/etc/hysteria2-panel-node/.data-plane-transaction
DATA_PLANE_TRANSACTION_MAGIC=HYSTERIA2_PANEL_NODE_DATA_PLANE_V1
NODE_REBIND_BACKUP_ROOT=/var/backups/hysteria2-panel-node/rebind
NODE_REBIND_TRANSACTION=/etc/hysteria2-panel-node/.rebind-transaction
NODE_REBIND_TRANSACTION_MAGIC=HYSTERIA2_PANEL_NODE_REBIND_V1
FRESH_IN_PROGRESS_MARKER=/etc/.hysteria2-panel-installing-by-installer
LEGACY_FRESH_IN_PROGRESS_MARKER=/etc/hysteria2-panel/.installing-by-installer
FRESH_TRANSACTION_MAGIC=HYSTERIA2_PANEL_FRESH_TRANSACTION_V1
FRESH_RECOVERY_SCRIPT=/var/backups/hysteria2-panel/.install-recover.sh
FRESH_RECOVERY_UNIT=/etc/systemd/system/hysteria2-panel-install-recover.service
FRESH_RECOVERY_DROPIN=/etc/systemd/system/hysteria2-panel.service.d/05-fresh-install-recovery.conf
FRESH_RECOVERY_SERVER_DROPIN=/etc/systemd/system/hysteria2-panel-server.service.d/05-fresh-install-recovery.conf
FRESH_RECOVERY_SERVER_443_DROPIN=/etc/systemd/system/hysteria2-panel-server-443.service.d/05-fresh-install-recovery.conf
RESTORE_ACTIVE_MARKER=/etc/hysteria2-panel/.restore-active
RESTORE_CAPTURED_ARCHIVE=/etc/hysteria2-panel/.restore-active.archive
RESTORE_PENDING_ARCHIVE=/var/lib/hysteria2-panel/backup-restore/pending-restore.zip
EGRESS_TRANSACTION_MARKER=/etc/hysteria2-panel/.egress-transaction.json
UPGRADE_ACTIVE_MARKER=/var/backups/hysteria2-panel/.upgrade-active
UPGRADE_RECOVERY_SCRIPT=/var/backups/hysteria2-panel/.upgrade-recover.sh
UPGRADE_RECOVERY_UNIT=/etc/systemd/system/hysteria2-panel-upgrade-recover.service
UPGRADE_WATCH_UNIT=hysteria2-panel-upgrade-watch.service
UPGRADE_RUNTIME_SYSCTL_STATE=runtime-sysctl.state
UPGRADE_RECOVERY_DROPIN_DIR=/etc/systemd/system/hysteria2-panel.service.d
UPGRADE_RECOVERY_DROPIN=${UPGRADE_RECOVERY_DROPIN_DIR}/10-hysteria2-panel-upgrade-recovery.conf
BACKUP_RETENTION_DAYS=90
BACKUP_MAX_COUNT=10
BACKUP_MIN_HEADROOM_KIB=65536
UFW_RULES_PATH=/etc/ufw
UFW_TEMPLATE_PATH=/usr/share/ufw/iptables
MANAGED_FIREWALL_STATE_FILE=/etc/hysteria2-panel/managed-firewall.rules
FIREWALL_TRANSACTION_FILE=/etc/hysteria2-panel/.firewall-transaction
FIREWALL_TRANSACTION_MAGIC=HYSTERIA2_PANEL_FIREWALL_TRANSACTION_V1
ROLLBACK_REQUIRED=0
FRESH_INSTALL_MUTATED=0
BACKUP_DIR=""
FIREWALL_MANAGER="unprepared"
FIREWALL_RESULT=""
FIREWALLD_HELP=""
FIREWALL_RULES=()
FIREWALL_ZONES=()
FIREWALL_PENDING=()
FIREWALL_APPLIED=()
FIREWALL_OWNED=()
FIREWALL_TRANSACTION_LINES=()
FIREWALL_NEWLY_OWNED=()
UFW_ADDED_RULES=""
INSTALL_COMMITTED=0
INSTALL_FINALIZING=0
LEGACY_RESTORE_UNIT=hysteria2-panel-restore.service
LEGACY_RESTORE_FRAGMENT=/etc/systemd/system/${LEGACY_RESTORE_UNIT}
LEGACY_RESTORE_GUARD_DIR=/run/systemd/system/${LEGACY_RESTORE_UNIT}.d
LEGACY_RESTORE_GUARD_DROPIN=${LEGACY_RESTORE_GUARD_DIR}/50-hysteria2-panel-install-guard.conf
LEGACY_RESTORE_GUARD_OWNED=0
TMP_DIR=""
RECOVER_UPGRADE=0
VERIFY_RECOVERED_UPGRADE=0
WATCH_UPGRADE=0
WATCH_UPGRADE_PID=""
WATCH_UPGRADE_START=""
RECOVER_FRESH=0
MAINTENANCE_LOCK_HELD=0
ORIGINAL_ARGS=()
JOIN_NODE=0
JOIN_NODE_MUTATED=0
REBIND_NODE=0
REBIND_NODE_MUTATED=0
REBIND_NODE_BACKUP_DIR=""
ACTIVATE_NODE_AGENT=0
ACTIVATE_NODE_AGENT_MUTATED=0
NODE_AGENT_BACKUP_FILE=""
ACTIVATE_DATA_PLANE=0
COMPLETE_NODE_ONBOARDING=0
DATA_PLANE_MUTATED=0
DATA_PLANE_EXISTING=0
DATA_PLANE_BACKUP_DIR=""
DATA_PLANE_NODE_AGENT_BACKUP_FILE=""
DATA_PLANE_MAIN_PORT=19999
DATA_PLANE_OWNED_FILES=()
DATA_PLANE_OWNED_UNITS=()

usage() {
  cat <<'EOF'
Hysteria2-panel 一键部署

用法：
  sudo bash install.sh

对接节点（只安装节点 Agent，不安装或修改 Hysteria）：
  sudo -E bash install.sh --join-node

已有数据节点安全重新绑定（保留节点私钥、Hysteria 身份和流量 spool）：
  sudo -E bash install.sh --rebind-node

验证后启用签名心跳（不安装或修改 Hysteria）：
  sudo bash install.sh --activate-node-agent

部署数据面（复制既有 Hysteria 身份，不安装面板、不修改 DNS）：
  sudo -E bash install.sh --activate-data-plane

自动对接收尾（仅供安装器创建的 systemd timer 调用）：
  sudo bash /opt/hysteria2-panel-node/onboarding-install.sh --complete-node-onboarding

默认端口：
  Hysteria 2: UDP 19999（同时提供 TCP 连通性探测）
  账号专属入口: UDP 443（同时提供 TCP 连通性探测）
  管理面板:   HTTPS TCP 19998（可显式选择 HTTP）

支持系统：
  Debian/Ubuntu（apt）
  RHEL/Rocky/Alma/CentOS Stream/Fedora（dnf 或 yum）
  Linux amd64/arm64、systemd、Python 3.8 或更高版本

可选环境变量：NODE_NAME、PUBLIC_HOST、HYSTERIA_PORT、PANEL_PORT、PANEL_SCHEME、PANEL_PUBLIC_HOST、EGRESS_POLICY、ADMIN_USER、ADMIN_PASSWORD、RESET_ADMIN
安装程序会交互式询问未提供的值，密码输入不会回显。
HTTPS 使用 Let’s Encrypt HTTP-01；面板域名须指向本机，公网 TCP 80 须持续可达。
升级默认保留现有管理员；需要重置时设置 RESET_ADMIN=1。
出站策略默认 full（放行公网目标的全部端口）；需要网页/视频端口白名单时设置 EGRESS_POLICY=web。
EOF
}

assert_reopenable_installer_entrypoint() {
  local entrypoint="${BASH_SOURCE[0]:-$0}"
  [[ -f "${entrypoint}" && ! -p "${entrypoint}" ]] \
    || fail "安装器不能通过管道或进程替换直接运行；请使用 README 中会先下载到临时文件的一行命令"
}

durable_replace_file() {
  local source_file="$1" destination="$2" mode="$3"
  local destination_directory="${destination%/*}"
  local destination_name="${destination##*/}"
  local staged_file
  [[ ! -L "${destination_directory}" && -d "${destination_directory}" ]] || return 1
  staged_file="$(mktemp "${destination_directory}/.${destination_name}.XXXXXXXX")" || return 1
  if ! install -o root -g root -m "${mode}" "${source_file}" "${staged_file}" ||
    ! sync -f "${staged_file}" ||
    ! mv -fT -- "${staged_file}" "${destination}" ||
    ! sync -f "${destination_directory}"; then
    rm -f -- "${staged_file}" >/dev/null 2>&1 || true
    return 1
  fi
}

durable_remove_file() {
  local destination="$1"
  local destination_directory="${destination%/*}"
  if [[ -e "${destination}" || -L "${destination}" ]]; then
    rm -f -- "${destination}" || return 1
    sync -f "${destination_directory}" || return 1
  fi
}

sync_existing_directories() {
  local path
  for path in "$@"; do
    if [[ -d "${path}" ]]; then
      sync -f "${path}" || return 1
    fi
  done
}

download_file() {
  local url="$1" destination="$2" attempt
  for attempt in 1 2 3 4; do
    if curl -q -fL --connect-timeout 10 --max-time 300 \
      "${url}" -o "${destination}"; then
      return 0
    fi
    rm -f -- "${destination}" || return 1
    (( attempt >= 4 )) || sleep "${attempt}" || return 1
  done
  return 1
}

flush_install_payload_for_commit() {
  sync -f \
    /opt/hysteria2-panel \
    /etc/hysteria2-panel \
    /var/lib/hysteria2-panel \
    /etc/systemd/system \
    /etc/sudoers.d \
    /etc/sysctl.d \
    /etc/tmpfiles.d
}

stop_loaded_units() {
  local active_state load_state unit_file
  for unit_file in "$@"; do
    load_state="$(systemctl show --no-pager --property=LoadState --value "${unit_file}" 2>/dev/null)" \
      || return 1
    active_state="$(systemctl show --no-pager --property=ActiveState --value "${unit_file}" 2>/dev/null)" \
      || return 1
    case "${load_state}" in
      not-found|loaded) ;;
      *) return 1 ;;
    esac
    if [[ "${active_state}" != "inactive" ]]; then
      systemctl stop "${unit_file}" || return 1
    fi
    active_state="$(systemctl show --no-pager --property=ActiveState --value "${unit_file}" 2>/dev/null)" \
      || return 1
    [[ "${active_state}" == "inactive" ]] || return 1
  done
}

stop_panel_preserving_hysteria() {
  local active_state panel_state server_unit
  local active_servers=()
  if [[ -f /etc/systemd/system/hysteria2-panel-node-dns-admission.timer ]]; then
    systemctl stop hysteria2-panel-node-dns-admission.timer \
      hysteria2-panel-node-dns-admission.service || return 1
  fi
  if [[ -f /etc/systemd/system/hysteria2-panel-offsite-backup.timer ]]; then
    systemctl stop hysteria2-panel-offsite-backup.timer \
      hysteria2-panel-offsite-backup.service || return 1
  fi
  for server_unit in hysteria2-panel-server.service hysteria2-panel-server-443.service; do
    active_state="$(systemctl show --no-pager --property=ActiveState --value "${server_unit}" 2>/dev/null)" \
      || return 1
    [[ "${active_state}" != "active" ]] || active_servers+=("${server_unit}")
  done
  panel_state="$(systemctl show --no-pager --property=ActiveState --value hysteria2-panel.service 2>/dev/null)" \
    || return 1
  if [[ "${panel_state}" != "inactive" && "${panel_state}" != "failed" ]]; then
    systemctl kill --kill-who=main --signal=SIGTERM hysteria2-panel.service || return 1
    for _attempt in {1..120}; do
      panel_state="$(systemctl show --no-pager --property=ActiveState --value hysteria2-panel.service 2>/dev/null)" \
        || return 1
      [[ "${panel_state}" != "inactive" ]] || break
      sleep 0.5
    done
  fi
  [[ "${panel_state}" == "inactive" || "${panel_state}" == "failed" ]] || return 1
  for server_unit in "${active_servers[@]}"; do
    systemctl is-active --quiet "${server_unit}" || return 1
  done
}

select_traffic_sync_options() {
  local primary_state secondary_state
  TRAFFIC_SYNC_OPTIONS=()
  primary_state="$(systemctl show --no-pager --property=ActiveState --value \
    hysteria2-panel-server.service 2>/dev/null)" || return 2
  secondary_state="$(systemctl show --no-pager --property=ActiveState --value \
    hysteria2-panel-server-443.service 2>/dev/null)" || return 2
  case "${primary_state}" in active|inactive|failed) ;; *) return 2 ;; esac
  case "${secondary_state}" in active|inactive|failed) ;; *) return 2 ;; esac
  if [[ "${primary_state}" == "active" && "${secondary_state}" == "active" ]]; then
    return 0
  fi
  if [[ "${primary_state}" == "active" ]]; then
    TRAFFIC_SYNC_OPTIONS+=(--primary-only)
    return 0
  fi
  if [[ "${secondary_state}" == "active" ]]; then
    TRAFFIC_SYNC_OPTIONS+=(--secondary-only)
    return 0
  fi
  return 1
}

select_upgrade_traffic_sync_script() {
  TRAFFIC_SYNC_SCRIPT=""
  if [[ -n "${TMP_DIR:-}" && ! -L "${TMP_DIR}/hysteria2_panel.py" && \
    -f "${TMP_DIR}/hysteria2_panel.py" && \
    "$(stat -c '%u:%h' "${TMP_DIR}/hysteria2_panel.py")" == "0:1" ]]; then
    TRAFFIC_SYNC_SCRIPT="${TMP_DIR}/hysteria2_panel.py"
  elif [[ ! -L "${BACKUP_DIR}/opt/hysteria2_panel.py" && \
    -f "${BACKUP_DIR}/opt/hysteria2_panel.py" && \
    "$(stat -c '%u:%h' "${BACKUP_DIR}/opt/hysteria2_panel.py")" == "0:1" ]]; then
    TRAFFIC_SYNC_SCRIPT="${BACKUP_DIR}/opt/hysteria2_panel.py"
  fi
  [[ -n "${TRAFFIC_SYNC_SCRIPT}" ]]
}

sync_traffic_before_upgrade_rollback() {
  local selection_status=0
  select_traffic_sync_options || selection_status=$?
  # Both Hysteria processes may already have been stopped after a successful
  # final settlement. In that case there is no live counter left to collect.
  if (( selection_status == 1 )); then
    return 0
  fi
  if (( selection_status != 0 )); then
    echo "警告：无法确认回滚前的 Hysteria 统计端点状态；已保留事务供下次恢复。" >&2
    return 1
  fi
  if ! select_upgrade_traffic_sync_script; then
    echo "警告：找不到经过验证的流量结算程序；为避免丢失流量，暂不停止 Hysteria。" >&2
    return 1
  fi
  if (
    set -a
    # Query the endpoints still served by the old Hysteria processes.
    # shellcheck disable=SC1091
    source "${BACKUP_DIR}/etc/panel.env"
    set +a
    "${PYTHON_BIN}" "${TRAFFIC_SYNC_SCRIPT}" \
      sync-traffic --quiesce "${TRAFFIC_SYNC_OPTIONS[@]}"
  ); then
    return 0
  fi
  echo "警告：回滚前无法完全清退在线连接，正在执行最后一次非清退流量结算。" >&2
  if (
    set -a
    # shellcheck disable=SC1091
    source "${BACKUP_DIR}/etc/panel.env"
    set +a
    "${PYTHON_BIN}" "${TRAFFIC_SYNC_SCRIPT}" \
      sync-traffic "${TRAFFIC_SYNC_OPTIONS[@]}"
  ); then
    return 0
  fi
  echo "警告：回滚前流量同步失败；Hysteria 与事务标记均已保留，拒绝覆盖运行中文件。" >&2
  return 1
}

write_backup_manifest() {
  local backup_dir="$1"
  "${PYTHON_BIN}" - "${backup_dir}" <<'PY'
import hashlib
import json
import os
import pathlib
import stat
import sys
import tempfile

root = pathlib.Path(sys.argv[1])
manifest_path = root / "backup-manifest.json"


def record(path):
    relative = path.relative_to(root).as_posix()
    metadata = path.lstat()
    item = {
        "path": relative,
        "mode": stat.S_IMODE(metadata.st_mode),
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
    }
    if path.is_symlink():
        item.update(type="symlink", target=os.readlink(path))
    elif path.is_dir():
        item["type"] = "directory"
    elif path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        item.update(type="file", sha256=digest.hexdigest(), size=metadata.st_size)
    else:
        raise SystemExit("unsupported backup entry: {}".format(relative))
    return item


entries = []
for directory, names, files in os.walk(str(root), followlinks=False):
    directory_path = pathlib.Path(directory)
    names.sort()
    files.sort()
    for name in names + files:
        path = directory_path / name
        if path == manifest_path:
            continue
        entries.append(record(path))
entries.sort(key=lambda item: item["path"])
payload = json.dumps(
    {"format": 1, "entries": entries},
    ensure_ascii=True,
    separators=(",", ":"),
).encode("utf-8") + b"\n"
descriptor, staged_name = tempfile.mkstemp(prefix=".backup-manifest-", dir=str(root))
try:
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(staged_name, manifest_path)
    directory_descriptor = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
finally:
    try:
        os.unlink(staged_name)
    except FileNotFoundError:
        pass
PY
}

verify_backup_manifest() {
  local backup_dir="$1"
  "${PYTHON_BIN}" - "${backup_dir}" <<'PY'
import hashlib
import json
import os
import pathlib
import stat
import sys

root = pathlib.Path(sys.argv[1])
manifest_path = root / "backup-manifest.json"
try:
    manifest_metadata = manifest_path.lstat()
except OSError:
    raise SystemExit(1)
if (
    not stat.S_ISREG(manifest_metadata.st_mode)
    or manifest_metadata.st_uid != 0
    or manifest_metadata.st_gid != 0
    or stat.S_IMODE(manifest_metadata.st_mode) != 0o600
    or manifest_metadata.st_nlink != 1
):
    raise SystemExit(1)
try:
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError):
    raise SystemExit(1)
if not isinstance(expected, dict) or expected.get("format") != 1:
    raise SystemExit(1)
expected_entries = expected.get("entries")
if not isinstance(expected_entries, list):
    raise SystemExit(1)


def record(path):
    relative = path.relative_to(root).as_posix()
    metadata = path.lstat()
    item = {
        "path": relative,
        "mode": stat.S_IMODE(metadata.st_mode),
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
    }
    if path.is_symlink():
        item.update(type="symlink", target=os.readlink(path))
    elif path.is_dir():
        item["type"] = "directory"
    elif path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        item.update(type="file", sha256=digest.hexdigest(), size=metadata.st_size)
    else:
        raise SystemExit(1)
    return item


actual_entries = []
for directory, names, files in os.walk(str(root), followlinks=False):
    directory_path = pathlib.Path(directory)
    names.sort()
    files.sort()
    for name in names + files:
        path = directory_path / name
        if path == manifest_path:
            continue
        actual_entries.append(record(path))
actual_entries.sort(key=lambda item: item["path"])
if actual_entries != expected_entries:
    raise SystemExit(1)
PY
}

capture_upgrade_runtime_state() {
  local backup_dir="$1" state_path state_stage
  local rmem wmem qdisc congestion_control
  rmem="$(sysctl -n net.core.rmem_max 2>/dev/null)" || return 1
  wmem="$(sysctl -n net.core.wmem_max 2>/dev/null)" || return 1
  qdisc="$(sysctl -n net.core.default_qdisc 2>/dev/null || true)"
  [[ -n "${qdisc}" ]] || qdisc="-"
  congestion_control="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null)" \
    || return 1
  [[ "${rmem}" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ "${wmem}" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ "${qdisc}" =~ ^[A-Za-z0-9_-]+$ ]] || return 1
  [[ "${congestion_control}" =~ ^[A-Za-z0-9_-]+$ ]] || return 1
  state_path="${backup_dir}/${UPGRADE_RUNTIME_SYSCTL_STATE}"
  state_stage="${state_path}.new"
  printf '%s\n' \
    "net.core.rmem_max=${rmem}" \
    "net.core.wmem_max=${wmem}" \
    "net.core.default_qdisc=${qdisc}" \
    "net.ipv4.tcp_congestion_control=${congestion_control}" > "${state_stage}" \
    || return 1
  chown root:root "${state_stage}" || return 1
  chmod 0600 "${state_stage}" || return 1
  sync -f "${state_stage}" || return 1
  mv -f -- "${state_stage}" "${state_path}" || return 1
  sync -f "${backup_dir}"
}

restore_upgrade_runtime_state() {
  local state_path="${BACKUP_DIR}/${UPGRADE_RUNTIME_SYSCTL_STATE}"
  local metadata line key value remainder seen=0
  local rmem="" wmem="" qdisc="" congestion_control=""
  if [[ ! -e "${state_path}" && ! -L "${state_path}" ]]; then
    # Backward compatibility for transactions created by older installers.
    return 0
  fi
  [[ ! -L "${state_path}" && -f "${state_path}" ]] || return 1
  metadata="$(stat -c '%u:%g:%a:%h' "${state_path}")" || return 1
  [[ "${metadata}" == "0:0:600:1" ]] || return 1
  while IFS= read -r line; do
    key=""
    value=""
    remainder=""
    IFS='=' read -r key value remainder <<< "${line}"
    [[ -z "${remainder}" ]] || return 1
    case "${key}" in
      net.core.rmem_max)
        [[ -z "${rmem}" && "${value}" =~ ^[1-9][0-9]*$ ]] || return 1
        rmem="${value}"
        ;;
      net.core.wmem_max)
        [[ -z "${wmem}" && "${value}" =~ ^[1-9][0-9]*$ ]] || return 1
        wmem="${value}"
        ;;
      net.core.default_qdisc)
        [[ -z "${qdisc}" && "${value}" =~ ^[A-Za-z0-9_-]+$ ]] || return 1
        qdisc="${value}"
        ;;
      net.ipv4.tcp_congestion_control)
        [[ -z "${congestion_control}" && "${value}" =~ ^[A-Za-z0-9_-]+$ ]] \
          || return 1
        congestion_control="${value}"
        ;;
      *) return 1 ;;
    esac
    ((seen += 1))
  done < "${state_path}"
  (( seen == 4 )) || return 1
  sysctl -w "net.core.rmem_max=${rmem}" >/dev/null || return 1
  sysctl -w "net.core.wmem_max=${wmem}" >/dev/null || return 1
  if [[ "${qdisc}" != "-" ]]; then
    sysctl -w "net.core.default_qdisc=${qdisc}" >/dev/null || return 1
  fi
  sysctl -w "net.ipv4.tcp_congestion_control=${congestion_control}" >/dev/null
}

require_backup_space() {
  local available_kib estimate_kib=0 path size_kib
  for path in /opt/hysteria2-panel /etc/hysteria2-panel /var/lib/hysteria2-panel/panel.db; do
    [[ ! -e "${path}" && ! -L "${path}" ]] || {
      size_kib="$(du -sk -- "${path}" | awk '{print $1}')" \
        || fail "无法估算升级备份大小；安装已停止"
      [[ "${size_kib}" =~ ^[0-9]+$ ]] || fail "升级备份大小无效；安装已停止"
      estimate_kib=$((estimate_kib + size_kib))
    }
  done
  available_kib="$(df -Pk /var/backups | awk 'NR == 2 {print $4}')" \
    || fail "无法读取备份分区可用空间；安装已停止"
  [[ "${available_kib}" =~ ^[0-9]+$ ]] || fail "备份分区可用空间无效；安装已停止"
  (( available_kib >= estimate_kib + BACKUP_MIN_HEADROOM_KIB )) \
    || fail "备份空间不足：至少需要 $((estimate_kib + BACKUP_MIN_HEADROOM_KIB)) KiB，当前仅 ${available_kib} KiB"
}

assert_upgrade_recovery_paths_owned() {
  local dropin_entries
  if [[ ! -e "${UPGRADE_RECOVERY_SCRIPT}" && ! -L "${UPGRADE_RECOVERY_SCRIPT}" && \
    ! -e "${UPGRADE_RECOVERY_UNIT}" && ! -L "${UPGRADE_RECOVERY_UNIT}" && \
    ! -e "${UPGRADE_RECOVERY_DROPIN_DIR}" && ! -L "${UPGRADE_RECOVERY_DROPIN_DIR}" ]]; then
    return 0
  fi
  [[ ! -L "${UPGRADE_RECOVERY_SCRIPT}" && -f "${UPGRADE_RECOVERY_SCRIPT}" && \
    "$(stat -c '%u:%g:%a:%h' "${UPGRADE_RECOVERY_SCRIPT}")" == "0:0:700:1" ]] \
    || fail "升级恢复脚本不是安装器管理的普通文件；安装已停止"
  grep -q '^#!/usr/bin/env bash$' "${UPGRADE_RECOVERY_SCRIPT}" \
    || fail "升级恢复脚本身份无效；安装已停止"
  grep -q '^PANEL_VERSION="[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*"$' \
    "${UPGRADE_RECOVERY_SCRIPT}" \
    || fail "升级恢复脚本版本无效；安装已停止"
  [[ ! -L "${UPGRADE_RECOVERY_UNIT}" && -f "${UPGRADE_RECOVERY_UNIT}" && \
    "$(stat -c '%u:%g:%a:%h' "${UPGRADE_RECOVERY_UNIT}")" == "0:0:644:1" ]] \
    || fail "升级恢复 unit 不是安装器管理的普通文件；安装已停止"
  [[ ! -L "${UPGRADE_RECOVERY_DROPIN_DIR}" && -d "${UPGRADE_RECOVERY_DROPIN_DIR}" && \
    "$(stat -c '%u:%g:%a' "${UPGRADE_RECOVERY_DROPIN_DIR}")" == "0:0:755" ]] \
    || fail "升级恢复 drop-in 目录无效；安装已停止"
  [[ ! -L "${UPGRADE_RECOVERY_DROPIN}" && -f "${UPGRADE_RECOVERY_DROPIN}" && \
    "$(stat -c '%u:%g:%a:%h' "${UPGRADE_RECOVERY_DROPIN}")" == "0:0:644:1" ]] \
    || fail "升级恢复 drop-in 不是安装器管理的普通文件；安装已停止"
  dropin_entries="$(find "${UPGRADE_RECOVERY_DROPIN_DIR}" -mindepth 1 -maxdepth 1 -print)" \
    || fail "无法核验升级恢复 drop-in；安装已停止"
  [[ "${dropin_entries}" == "${UPGRADE_RECOVERY_DROPIN}" ]] \
    || fail "面板 unit 存在非安装器管理的 drop-in；安装已停止"
  grep -Fqx "ConditionPathExists=${UPGRADE_ACTIVE_MARKER}" "${UPGRADE_RECOVERY_UNIT}" \
    || fail "升级恢复 unit 条件无效；安装已停止"
  grep -Fqx "ExecStart=/bin/bash ${UPGRADE_RECOVERY_SCRIPT} --recover-upgrade" \
    "${UPGRADE_RECOVERY_UNIT}" \
    || fail "升级恢复 unit 命令无效；安装已停止"
  grep -Fqx 'Requires=hysteria2-panel-upgrade-recover.service' \
    "${UPGRADE_RECOVERY_DROPIN}" \
    || fail "升级恢复 drop-in 身份无效；安装已停止"
}

install_upgrade_recovery_infrastructure() {
  local script_stage unit_stage dropin_stage
  assert_upgrade_recovery_paths_owned
  script_stage="${UPGRADE_RECOVERY_SCRIPT}.new"
  unit_stage="${UPGRADE_RECOVERY_UNIT}.new"
  dropin_stage="${UPGRADE_RECOVERY_DROPIN}.new"
  install -d -o root -g root -m 0700 /var/backups/hysteria2-panel
  install -o root -g root -m 0700 "$0" "${script_stage}"
  mv -f -- "${script_stage}" "${UPGRADE_RECOVERY_SCRIPT}"
  cat > "${TMP_DIR}/hysteria2-panel-upgrade-recover.service" <<EOF
[Unit]
Description=Recover an interrupted Hysteria 2 panel upgrade before startup
After=local-fs.target systemd-tmpfiles-setup.service network-online.target
Wants=network-online.target
Before=hysteria2-panel-restore-recover.service hysteria2-panel-egress-recover.service hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-server-443.service
ConditionPathExists=${UPGRADE_ACTIVE_MARKER}

[Service]
Type=oneshot
ExecStart=/bin/bash ${UPGRADE_RECOVERY_SCRIPT} --recover-upgrade
TimeoutStartSec=25min
TimeoutStopSec=30s
KillSignal=SIGTERM
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=false
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
ReadWritePaths=/opt/hysteria2-panel /etc/hysteria2-panel /etc/systemd/system /etc/sudoers.d /etc/sysctl.d /etc/tmpfiles.d /var/lib/hysteria2-panel /var/backups/hysteria2-panel ${MAINTENANCE_RUNTIME_DIR}
TasksMax=128
MemoryMax=768M

[Install]
WantedBy=multi-user.target
EOF
  install -o root -g root -m 0644 \
    "${TMP_DIR}/hysteria2-panel-upgrade-recover.service" "${unit_stage}"
  mv -f -- "${unit_stage}" "${UPGRADE_RECOVERY_UNIT}"
  install -d -o root -g root -m 0755 "${UPGRADE_RECOVERY_DROPIN_DIR}"
  cat > "${TMP_DIR}/hysteria2-panel-upgrade-recovery.conf" <<'EOF'
[Unit]
Requires=hysteria2-panel-upgrade-recover.service
After=hysteria2-panel-upgrade-recover.service
EOF
  install -o root -g root -m 0644 \
    "${TMP_DIR}/hysteria2-panel-upgrade-recovery.conf" "${dropin_stage}"
  mv -f -- "${dropin_stage}" "${UPGRADE_RECOVERY_DROPIN}"
  sync -f "${UPGRADE_RECOVERY_SCRIPT}"
  sync -f "${UPGRADE_RECOVERY_UNIT}"
  sync -f "${UPGRADE_RECOVERY_DROPIN}"
  systemctl daemon-reload
  systemctl enable hysteria2-panel-upgrade-recover.service
  sync -f /etc/systemd/system
  sync -f "${UPGRADE_RECOVERY_DROPIN_DIR}"
  sync -f /etc/systemd/system/multi-user.target.wants
  sync -f /var/backups/hysteria2-panel
}

watch_upgrade_parent() {
  local parent_pid="$1" expected_start="$2" current_start=""
  [[ "${parent_pid}" =~ ^[1-9][0-9]*$ && "${expected_start}" =~ ^[1-9][0-9]*$ ]] \
    || return 1
  while [[ -e "${UPGRADE_ACTIVE_MARKER}" || -L "${UPGRADE_ACTIVE_MARKER}" ]]; do
    [[ -r "/proc/${parent_pid}/stat" ]] || break
    current_start="$(awk '{print $22}' "/proc/${parent_pid}/stat" 2>/dev/null)" \
      || break
    [[ "${current_start}" == "${expected_start}" ]] || break
    sleep 2
  done
  [[ -e "${UPGRADE_ACTIVE_MARKER}" || -L "${UPGRADE_ACTIVE_MARKER}" ]] || return 0
  systemctl start --no-block hysteria2-panel-upgrade-recover.service
}

arm_upgrade_watchdog() {
  local parent_pid="$$" parent_start=""
  parent_start="$(awk '{print $22}' "/proc/${parent_pid}/stat" 2>/dev/null)" \
    || return 1
  [[ "${parent_start}" =~ ^[1-9][0-9]*$ ]] || return 1
  systemctl stop "${UPGRADE_WATCH_UNIT}" >/dev/null 2>&1 || true
  systemctl reset-failed "${UPGRADE_WATCH_UNIT}" >/dev/null 2>&1 || true
  systemd-run --quiet --collect --unit="${UPGRADE_WATCH_UNIT}" \
    --property=Type=exec \
    --property=NoNewPrivileges=yes \
    --property=PrivateTmp=yes \
    --property=ProtectHome=yes \
    --property=ProtectSystem=strict \
    /bin/bash "${UPGRADE_RECOVERY_SCRIPT}" \
      --watch-upgrade "${parent_pid}" "${parent_start}"
}

arm_upgrade_transaction() {
  local marker_stage="${UPGRADE_ACTIVE_MARKER}.new"
  verify_backup_manifest "${BACKUP_DIR}" \
    || fail "升级备份清单复核失败；尚未覆盖程序文件"
  install_upgrade_recovery_infrastructure
  printf '%s\n' "${BACKUP_DIR}" > "${marker_stage}"
  chown root:root "${marker_stage}"
  chmod 0600 "${marker_stage}"
  sync -f "${marker_stage}"
  mv -f -- "${marker_stage}" "${UPGRADE_ACTIVE_MARKER}"
  sync -f /var/backups/hysteria2-panel
  arm_upgrade_watchdog \
    || fail "无法启动升级中断 watchdog；正在恢复旧版本"
}

clear_upgrade_transaction() {
  sync -f /opt/hysteria2-panel /etc/hysteria2-panel \
    /var/lib/hysteria2-panel /etc/systemd/system || return 1
  rm -f -- "${UPGRADE_ACTIVE_MARKER}" || return 1
  sync -f /var/backups/hysteria2-panel || return 1
  systemctl stop "${UPGRADE_WATCH_UNIT}" >/dev/null 2>&1 || true
  systemctl reset-failed "${UPGRADE_WATCH_UNIT}" >/dev/null 2>&1 || true
}

read_upgrade_backup_path() {
  local marker_metadata marker_value root_metadata
  [[ ! -L /var/backups/hysteria2-panel && -d /var/backups/hysteria2-panel ]] || return 1
  root_metadata="$(stat -c '%u:%g:%a' /var/backups/hysteria2-panel)" || return 1
  [[ "${root_metadata}" == "0:0:700" ]] || return 1
  [[ ! -L "${UPGRADE_ACTIVE_MARKER}" && -f "${UPGRADE_ACTIVE_MARKER}" ]] || return 1
  marker_metadata="$(stat -c '%u:%g:%a:%h' "${UPGRADE_ACTIVE_MARKER}")" || return 1
  [[ "${marker_metadata}" == "0:0:600:1" ]] || return 1
  marker_value="$(cat "${UPGRADE_ACTIVE_MARKER}")" || return 1
  [[ "${marker_value}" =~ ^/var/backups/hysteria2-panel/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$ ]] \
    || return 1
  [[ ! -L "${marker_value}" && -d "${marker_value}" ]] || return 1
  [[ "$(stat -c '%u:%g:%a' "${marker_value}")" == "0:0:700" ]] || return 1
  printf '%s\n' "${marker_value}"
}

recover_interrupted_upgrade() {
  [[ -e "${UPGRADE_ACTIVE_MARKER}" || -L "${UPGRADE_ACTIVE_MARKER}" ]] || return 0
  BACKUP_DIR="$(read_upgrade_backup_path)" \
    || fail "升级事务标记或备份目录无效；拒绝自动覆盖文件"
  verify_backup_manifest "${BACKUP_DIR}" \
    || fail "升级备份清单不匹配；拒绝自动覆盖文件"
  EXISTING_INSTALL=1
  ROLLBACK_REQUIRED=1
  echo "检测到未完成的升级，正在从已验证备份恢复…"
  rollback_existing_install 75 \
    || fail "升级自动恢复未通过健康检查；事务标记已保留"
}

restart_backed_up_optional_runtime_units() {
  local unit_name
  for unit_name in \
    hysteria2-panel-tcp-probe.service \
    hysteria2-panel-server-443.service \
    hysteria2-panel-tcp-probe-443.service; do
    [[ -f "${BACKUP_DIR}/${unit_name}" ]] || continue
    systemctl reset-failed "${unit_name}" >/dev/null 2>&1 || true
    systemctl restart "${unit_name}" || return 1
  done
}

start_backed_up_timers() {
  local timer_name wants_name
  while IFS='|' read -r wants_name timer_name; do
    [[ -L "${BACKUP_DIR}/${wants_name}" ]] || continue
    systemctl start "${timer_name}" || return 1
  done <<'EOF'
hysteria2-panel-cert-renew.wants|hysteria2-panel-cert-renew.timer
hysteria2-panel-node-dns-admission.wants|hysteria2-panel-node-dns-admission.timer
hysteria2-panel-offsite-backup.wants|hysteria2-panel-offsite-backup.timer
EOF
}

verify_recovered_upgrade() {
  BACKUP_DIR="$(read_upgrade_backup_path)" \
    || fail "升级恢复复核找不到有效事务；标记已保留"
  verify_backup_manifest "${BACKUP_DIR}" \
    || fail "升级恢复复核发现备份清单漂移；标记已保留"
  systemctl reset-failed hysteria2-panel.service hysteria2-panel-server.service \
    >/dev/null 2>&1 || true
  systemctl restart hysteria2-panel.service hysteria2-panel-server.service \
    || fail "升级文件已恢复，但旧服务无法重新启动；标记已保留"
  restart_backed_up_optional_runtime_units \
    || fail "升级文件已恢复，但旧版可选入口无法重新启动；标记已保留"
  verify_rollback_recovery \
    || fail "升级文件已恢复，但旧服务或监听端口未通过健康复核；标记已保留"
  start_backed_up_timers \
    || fail "升级文件已恢复，但旧版定时任务无法重新启动；标记已保留"
  clear_upgrade_transaction \
    || fail "旧版本已恢复，但升级事务标记未能清除"
  echo "升级中断恢复完成；旧版本服务、端口和节点身份均已复核。"
}

restore_managed_directory() {
  local backup_source="$1" target="$2"
  [[ ! -L "${backup_source}" && -d "${backup_source}" ]] || return 1
  [[ ! -L "${target}" && -d "${target}" ]] || return 1
  find "${target}" -mindepth 1 -delete || return 1
  cp -a "${backup_source}/." "${target}/" || return 1
  chown --reference="${backup_source}" "${target}" || return 1
  chmod --reference="${backup_source}" "${target}" || return 1
}

prune_automatic_backups() {
  local backup_root=/var/backups/hysteria2-panel count=0 directory metadata name
  local automatic_backups=()
  [[ ! -L "${backup_root}" && -d "${backup_root}" ]] || return 1
  [[ "$(stat -c '%u:%g:%a' "${backup_root}")" == "0:0:700" ]] || return 1
  while IFS= read -r directory; do
    name="${directory##*/}"
    [[ "${name}" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$ ]] || continue
    [[ ! -L "${directory}" && -d "${directory}" ]] || continue
    metadata="$(stat -c '%u:%g:%a' "${directory}")" || return 1
    [[ "${metadata}" == "0:0:700" ]] || continue
    automatic_backups+=("${directory}")
  done < <(find "${backup_root}" -mindepth 1 -maxdepth 1 -type d -print | LC_ALL=C sort -r)
  for directory in "${automatic_backups[@]}"; do
    count=$((count + 1))
    [[ "${directory}" != "${BACKUP_DIR}" ]] || continue
    if (( count > BACKUP_MAX_COUNT )) || \
      find "${directory}" -maxdepth 0 -mtime "+${BACKUP_RETENTION_DAYS}" -print -quit | grep -q .; then
      rm -r -- "${directory}" || return 1
    fi
  done
}

rollback_firewall_after_service_recovery() {
  if declare -F rollback_firewall_changes >/dev/null 2>&1 && \
    { (( ${#FIREWALL_APPLIED[@]} > 0 )) || \
      [[ -e "${FIREWALL_TRANSACTION_FILE}" || -L "${FIREWALL_TRANSACTION_FILE}" ]]; }; then
    if ! rollback_firewall_changes; then
      echo "警告：本次新增的防火墙规则未能全部自动撤销，请立即人工检查" >&2
      return 1
    fi
  fi
}

verify_backed_up_runtime_units_active() {
  local required_unit
  for required_unit in hysteria2-panel.service hysteria2-panel-server.service; do
    systemctl is-active --quiet "${required_unit}" || return 1
  done
  for required_unit in \
    hysteria2-panel-tcp-probe.service \
    hysteria2-panel-server-443.service \
    hysteria2-panel-tcp-probe-443.service; do
    [[ ! -f "${BACKUP_DIR}/${required_unit}" ]] \
      || systemctl is-active --quiet "${required_unit}" \
      || return 1
  done
}

verify_rollback_recovery() {
  local health_tls_mode=strict
  set -a
  # The backup was created from the root-owned managed configuration.
  # shellcheck disable=SC1091
  source "${BACKUP_DIR}/etc/panel.env" || return 1
  set +a
  verify_backed_up_runtime_units_active || return 1
  [[ "${HY2PANEL_PANEL_SCHEME}" != "https" ]] || health_tls_mode=insecure
  wait_for_health \
    "${HY2PANEL_PANEL_SCHEME}://127.0.0.1:${HY2PANEL_PANEL_PORT}/healthz" \
    "${health_tls_mode}" \
    || return 1
  wait_for_health "http://127.0.0.1:${HY2PANEL_AUTH_PORT}/healthz" strict || return 1
  wait_for_listener udp "${HY2PANEL_HYSTERIA_PORT}" || return 1
  [[ ! -f "${BACKUP_DIR}/hysteria2-panel-tcp-probe.service" ]] \
    || wait_for_listener tcp "${HY2PANEL_HYSTERIA_PORT}" \
    || return 1
  if [[ -f "${BACKUP_DIR}/hysteria2-panel-server-443.service" ]]; then
    wait_for_listener udp 443 || return 1
  fi
  if [[ -f "${BACKUP_DIR}/hysteria2-panel-tcp-probe-443.service" ]]; then
    wait_for_listener tcp 443 || return 1
  fi
  verify_backed_up_runtime_units_active
}

rollback_existing_install() {
  local status="${1:-1}"
  local unit_file
  if [[ "${FRESH_INSTALL_MUTATED:-0}" == "1" && "${EXISTING_INSTALL:-0}" == "0" ]]; then
    FRESH_INSTALL_MUTATED=0
    trap - ERR
    set +e
    echo "首次部署失败（退出码 ${status}），正在清理本次创建的项目文件…" >&2
    if ( set -e; recover_interrupted_fresh_install ); then
      echo "已清理未完成的首次部署；可以直接重新运行安装器。" >&2
      return 0
    fi
    echo "警告：首次部署未能完整回滚；事务标记与开机恢复已保留，重启或重新运行安装器会继续清场。" >&2
    return 1
  fi
  if [[ "${ROLLBACK_REQUIRED:-0}" != "1" || "${EXISTING_INSTALL:-0}" != "1" || \
    "${BACKUP_DIR:-}" != /var/backups/hysteria2-panel/* || ! -d "${BACKUP_DIR}" ]]; then
    return 0
  fi
  if [[ -e "${UPGRADE_ACTIVE_MARKER}" || -L "${UPGRADE_ACTIVE_MARKER}" || \
    -e "${BACKUP_DIR}/backup-manifest.json" ]]; then
    if ! verify_backup_manifest "${BACKUP_DIR}"; then
      echo "警告：升级备份清单不匹配；拒绝自动覆盖文件。备份：${BACKUP_DIR}" >&2
      return 1
    fi
  fi

  ROLLBACK_REQUIRED=0
  trap - ERR
  set +e
  echo "升级失败（退出码 ${status}），正在自动恢复升级前版本和节点身份…" >&2
  if ! stop_panel_preserving_hysteria; then
    echo "警告：无法停止面板写入；为避免破坏数据库，已停止自动文件回滚。备份：${BACKUP_DIR}" >&2
    return 1
  fi
  if ! sync_traffic_before_upgrade_rollback; then
    echo "警告：回滚前流量无法安全结算；为避免计量丢失，已保留 Hysteria 与升级事务。" >&2
    return 1
  fi
  if ! stop_loaded_units \
    hysteria2-panel-node-dns-admission.timer \
    hysteria2-panel-node-dns-admission.service \
    hysteria2-panel-offsite-backup.timer \
    hysteria2-panel-offsite-backup.service \
    hysteria2-panel-cert-renew.timer \
    hysteria2-panel-cert-renew.service \
    hysteria2-panel-tcp-probe-443.service \
    hysteria2-panel-server-443.service \
    hysteria2-panel-tcp-probe.service \
    hysteria2-panel-server.service \
    hysteria2-panel.service; then
    echo "警告：无法确认所有项目服务均已停止；为避免覆盖运行中的文件，已停止自动文件回滚。备份：${BACKUP_DIR}" >&2
    return 1
  fi
  rollback_firewall_after_service_recovery \
    || { echo "警告：无法恢复升级前防火墙规则；已停止文件回滚。备份：${BACKUP_DIR}" >&2; return 1; }

  if [[ -d "${BACKUP_DIR}/opt" ]]; then
    restore_managed_directory "${BACKUP_DIR}/opt" /opt/hysteria2-panel \
      || { echo "警告：无法恢复升级前程序目录" >&2; return 1; }
  fi
  if [[ -d "${BACKUP_DIR}/etc" ]]; then
    restore_managed_directory "${BACKUP_DIR}/etc" /etc/hysteria2-panel \
      || { echo "警告：无法恢复升级前配置目录" >&2; return 1; }
  fi
  if ! preserve_or_restore_database \
    /var/lib/hysteria2-panel/panel.db "${BACKUP_DIR}/panel.db"; then
    echo "警告：最新数据库和升级前快照均未通过校验，请使用备份目录人工恢复：${BACKUP_DIR}" >&2
  fi
  chown -R hy2panel:hy2panel /var/lib/hysteria2-panel
  chmod 0750 /var/lib/hysteria2-panel
  find /var/lib/hysteria2-panel -type f -exec chmod 0600 {} +
  if [[ -d "${ACME_WORK_DIR}" && -d "${ACME_LOGS_DIR}" ]]; then
    secure_acme_runtime_directories \
      || { echo "警告：无法恢复 ACME 运行目录权限" >&2; return 1; }
  fi

  for unit_file in hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-server-443.service hysteria2-panel-tcp-probe.service hysteria2-panel-tcp-probe-443.service hysteria2-panel-egress-full.service hysteria2-panel-egress-web.service hysteria2-panel-egress-recover.service hysteria2-panel-restore.service hysteria2-panel-restore-recover.service hysteria2-panel-restore-resume.service hysteria2-panel-cert-renew.service hysteria2-panel-cert-renew.timer hysteria2-panel-node-dns-admission.service hysteria2-panel-node-dns-admission.timer hysteria2-panel-offsite-backup.service hysteria2-panel-offsite-backup.timer hysteria2-panel-update.service; do
    if [[ -f "${BACKUP_DIR}/${unit_file}" ]]; then
      cp -a "${BACKUP_DIR}/${unit_file}" "/etc/systemd/system/${unit_file}"
    else
      rm -f -- "/etc/systemd/system/${unit_file}"
    fi
  done
  if [[ -L "${BACKUP_DIR}/hysteria2-panel-restore-resume.wants" ]]; then
    systemctl enable hysteria2-panel-restore-resume.service >/dev/null 2>&1 \
      || echo "警告：无法恢复开机恢复服务的启用状态" >&2
  else
    systemctl disable hysteria2-panel-restore-resume.service >/dev/null 2>&1 || true
    rm -f -- /etc/systemd/system/multi-user.target.wants/hysteria2-panel-restore-resume.service
  fi
  if [[ -L "${BACKUP_DIR}/hysteria2-panel-cert-renew.wants" ]]; then
    systemctl enable hysteria2-panel-cert-renew.timer >/dev/null 2>&1 \
      || echo "警告：无法恢复面板证书续期 timer 的启用状态" >&2
  else
    systemctl disable hysteria2-panel-cert-renew.timer >/dev/null 2>&1 || true
    rm -f -- /etc/systemd/system/timers.target.wants/hysteria2-panel-cert-renew.timer
  fi
  if [[ -L "${BACKUP_DIR}/hysteria2-panel-node-dns-admission.wants" ]]; then
    systemctl enable hysteria2-panel-node-dns-admission.timer >/dev/null 2>&1 \
      || echo "警告：无法恢复节点 DNS 监测 timer 的启用状态" >&2
  else
    systemctl disable hysteria2-panel-node-dns-admission.timer >/dev/null 2>&1 || true
    rm -f -- /etc/systemd/system/timers.target.wants/hysteria2-panel-node-dns-admission.timer
  fi
  if [[ -L "${BACKUP_DIR}/hysteria2-panel-offsite-backup.wants" ]]; then
    systemctl enable hysteria2-panel-offsite-backup.timer >/dev/null 2>&1 \
      || echo "警告：无法恢复异地备份 timer 的启用状态" >&2
  else
    systemctl disable hysteria2-panel-offsite-backup.timer >/dev/null 2>&1 || true
    rm -f -- /etc/systemd/system/timers.target.wants/hysteria2-panel-offsite-backup.timer
  fi
  if [[ -f "${BACKUP_DIR}/99-hysteria2-panel.conf" ]]; then
    cp -a "${BACKUP_DIR}/99-hysteria2-panel.conf" "${SYSCTL_FILE}"
  else
    rm -f -- "${SYSCTL_FILE}"
  fi
  if [[ -f "${BACKUP_DIR}/hysteria2-panel.sudoers" ]]; then
    cp -a "${BACKUP_DIR}/hysteria2-panel.sudoers" /etc/sudoers.d/hysteria2-panel
  else
    rm -f -- /etc/sudoers.d/hysteria2-panel
  fi
  if [[ -f "${BACKUP_DIR}/hysteria2-panel.tmpfiles" ]]; then
    cp -a "${BACKUP_DIR}/hysteria2-panel.tmpfiles" "${TMPFILES_FILE}"
  else
    rm -f -- "${TMPFILES_FILE}"
  fi
  sync

  restore_upgrade_runtime_state || {
    echo "警告：无法恢复升级前运行时内核网络参数；事务标记已保留。" >&2
    return 1
  }

  systemctl daemon-reload
  if (( RECOVER_UPGRADE == 1 )); then
    systemctl stop hysteria2-panel-upgrade-verify.timer \
      hysteria2-panel-upgrade-verify.service >/dev/null 2>&1 || true
    systemctl reset-failed hysteria2-panel-upgrade-verify.service >/dev/null 2>&1 || true
    systemd-run --quiet --collect --unit=hysteria2-panel-upgrade-verify \
      --on-active=2s --timer-property=AccuracySec=1s \
      /bin/bash "${UPGRADE_RECOVERY_SCRIPT}" --verify-recovered-upgrade \
      || return 1
    echo "升级文件已恢复；旧服务启动和健康复核已排队，事务标记将在复核后清除。" >&2
    return 0
  fi
  systemctl restart hysteria2-panel.service hysteria2-panel-server.service
  restart_backed_up_optional_runtime_units || {
    echo "警告：旧版可选入口未能全部恢复；事务标记已保留。" >&2
    return 1
  }
  if ! verify_rollback_recovery; then
    echo "警告：文件已回滚，但旧服务或监听端口未完全恢复；已保留本次防火墙规则，请使用备份目录人工恢复：${BACKUP_DIR}" >&2
    return 1
  fi
  start_backed_up_timers || {
    echo "警告：旧版定时任务未能全部恢复；事务标记已保留。" >&2
    return 1
  }
  rollback_firewall_after_service_recovery || true
  if [[ -e "${UPGRADE_ACTIVE_MARKER}" || -L "${UPGRADE_ACTIVE_MARKER}" ]]; then
    clear_upgrade_transaction || {
      echo "警告：旧版本已恢复，但升级事务标记未能清除：${UPGRADE_ACTIVE_MARKER}" >&2
      return 1
    }
  fi
  echo "已恢复升级前版本；节点身份、用户数据库和全部入口均已复核。备份：${BACKUP_DIR}" >&2
}

fail() {
  echo "错误：$*" >&2
  exit 1
}

unexpected_error() {
  local status=$?
  echo "错误：部署在第 ${BASH_LINENO[0]} 行意外中断（退出码 ${status}）。请根据上一条系统输出处理后重试；重复运行会先备份并保持幂等。" >&2
  return "${status}"
}
trap unexpected_error ERR

interrupted() {
  case "$1" in
    HUP) exit 129 ;;
    INT) exit 130 ;;
    TERM) exit 143 ;;
  esac
}
trap 'interrupted HUP' HUP
trap 'interrupted INT' INT
trap 'interrupted TERM' TERM

cleanup() {
  local cleanup_status=0
  if declare -F release_legacy_restore_guard >/dev/null 2>&1; then
    release_legacy_restore_guard || cleanup_status=1
  fi
  if [[ -n "${TMP_DIR:-}" && -d "${TMP_DIR}" && "${TMP_DIR}" == /tmp/hysteria2-panel.* ]]; then
    rm -r -- "${TMP_DIR}" || cleanup_status=1
  fi
  return "${cleanup_status}"
}

finalize_install() {
  local status=$?
  local cleanup_status=0
  local join_node_state="${JOIN_NODE:-0}"
  local join_node_mutated="${JOIN_NODE_MUTATED:-0}"
  local rebind_node_state="${REBIND_NODE:-0}"
  local rebind_node_mutated="${REBIND_NODE_MUTATED:-0}"
  local activate_node_state="${ACTIVATE_NODE_AGENT:-0}"
  local activate_node_mutated="${ACTIVATE_NODE_AGENT_MUTATED:-0}"
  local data_plane_state="${ACTIVATE_DATA_PLANE:-0}"
  local data_plane_mutated="${DATA_PLANE_MUTATED:-0}"
  trap - EXIT ERR
  trap '' HUP INT TERM
  set +e
  (( INSTALL_FINALIZING == 0 )) || exit "${status}"
  INSTALL_FINALIZING=1
  if (( status != 0 && data_plane_state == 1 )); then
    if (( data_plane_mutated == 1 )); then
      rollback_data_plane_activation || status=1
    fi
  elif (( status != 0 && rebind_node_state == 1 )); then
    if (( rebind_node_mutated == 1 )); then
      rollback_node_rebind || status=1
    fi
  elif (( status != 0 && activate_node_state == 1 )); then
    if (( activate_node_mutated == 1 )); then
      rollback_node_agent_activation || status=1
    fi
  elif (( status != 0 && join_node_state == 1 )); then
    if (( join_node_mutated == 1 )); then
      rollback_join_node_install || status=1
    fi
  elif (( status != 0 && INSTALL_COMMITTED == 0 )); then
    rollback_existing_install "${status}"
  fi
  cleanup
  cleanup_status=$?
  if (( status == 0 && cleanup_status != 0 )); then
    status=1
  fi
  exit "${status}"
}
trap finalize_install EXIT

select_python() {
  local candidate
  PYTHON_BIN=""
  for candidate in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python3.8; do
    command -v "${candidate}" >/dev/null 2>&1 || continue
    if "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' \
      >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "${candidate}")"
      return 0
    fi
  done
  return 1
}

rollback_join_node_install() {
  local path
  systemctl disable --now hysteria2-panel-node-onboarding.timer >/dev/null 2>&1 || true
  systemctl stop hysteria2-panel-node-onboarding.service >/dev/null 2>&1 || true
  rm -f -- "${NODE_ONBOARDING_SERVICE}" "${NODE_ONBOARDING_TIMER}" \
    "${NODE_ONBOARDING_MARKER}" || return 1
  for path in "${NODE_AGENT_CONFIG_DIR}" "${NODE_AGENT_OPT_DIR}"; do
    if [[ -e "${path}" || -L "${path}" ]]; then
      [[ ! -L "${path}" && -d "${path}" ]] || return 1
      rm -r -- "${path}" || return 1
    fi
  done
  systemctl daemon-reload || return 1
  sync -f /etc || return 1
  sync -f /opt || return 1
  JOIN_NODE_MUTATED=0
}

write_node_rebind_backup() {
  local timestamp manifest
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  REBIND_NODE_BACKUP_DIR="${NODE_REBIND_BACKUP_ROOT}/${timestamp}-$$"
  [[ ! -e "${REBIND_NODE_BACKUP_DIR}" && ! -L "${REBIND_NODE_BACKUP_DIR}" ]] \
    || return 1
  install -d -o root -g root -m 0700 "${NODE_DATA_PLANE_BACKUP_ROOT}"
  install -d -o root -g root -m 0700 "${NODE_REBIND_BACKUP_ROOT}"
  install -d -o root -g root -m 0700 "${REBIND_NODE_BACKUP_DIR}"
  install -o root -g root -m 0755 "${NODE_AGENT_OPT_DIR}/node_agent.py" \
    "${REBIND_NODE_BACKUP_DIR}/node_agent.py"
  install -o root -g root -m 0600 \
    "${NODE_AGENT_CONFIG_DIR}/registration.json" \
    "${REBIND_NODE_BACKUP_DIR}/registration.json"
  manifest="${REBIND_NODE_BACKUP_DIR}/manifest.sha256"
  (
    cd "${REBIND_NODE_BACKUP_DIR}"
    sha256sum node_agent.py registration.json > manifest.sha256
  )
  chmod 0600 "${manifest}"
  sync -f "${REBIND_NODE_BACKUP_DIR}" "${NODE_REBIND_BACKUP_ROOT}"
}

arm_node_rebind_transaction() {
  local stage="${TMP_DIR}/node-rebind-transaction"
  {
    echo "${NODE_REBIND_TRANSACTION_MAGIC}"
    echo "${REBIND_NODE_BACKUP_DIR}"
  } > "${stage}"
  durable_replace_file "${stage}" "${NODE_REBIND_TRANSACTION}" 0600
}

rollback_node_rebind() {
  [[ -d "${REBIND_NODE_BACKUP_DIR}" && ! -L "${REBIND_NODE_BACKUP_DIR}" ]] \
    || return 1
  [[ -f "${REBIND_NODE_BACKUP_DIR}/manifest.sha256" \
    && ! -L "${REBIND_NODE_BACKUP_DIR}/manifest.sha256" \
    && -f "${REBIND_NODE_BACKUP_DIR}/node_agent.py" \
    && ! -L "${REBIND_NODE_BACKUP_DIR}/node_agent.py" \
    && -f "${REBIND_NODE_BACKUP_DIR}/registration.json" \
    && ! -L "${REBIND_NODE_BACKUP_DIR}/registration.json" ]] || return 1
  (
    cd "${REBIND_NODE_BACKUP_DIR}"
    sha256sum --check --status manifest.sha256
  ) || return 1
  systemctl stop hysteria2-panel-node-heartbeat.timer \
    hysteria2-panel-node-heartbeat.service >/dev/null 2>&1 || true
  durable_replace_file "${REBIND_NODE_BACKUP_DIR}/node_agent.py" \
    "${NODE_AGENT_OPT_DIR}/node_agent.py" 0755 || return 1
  durable_replace_file "${REBIND_NODE_BACKUP_DIR}/registration.json" \
    "${NODE_AGENT_CONFIG_DIR}/registration.json" 0600 || return 1
  systemctl enable --now hysteria2-panel-node-heartbeat.timer || return 1
  rm -f -- "${NODE_REBIND_TRANSACTION}" || return 1
  sync -f "${NODE_AGENT_OPT_DIR}" "${NODE_AGENT_CONFIG_DIR}" \
    /etc/systemd/system || return 1
  REBIND_NODE_MUTATED=0
}

recover_interrupted_node_rebind() {
  local marker_magic marker_backup
  local -a marker_lines=()
  [[ -e "${NODE_REBIND_TRANSACTION}" || -L "${NODE_REBIND_TRANSACTION}" ]] \
    || return 0
  [[ -f "${NODE_REBIND_TRANSACTION}" && ! -L "${NODE_REBIND_TRANSACTION}" ]] \
    || fail "节点重绑定事务标记不安全，拒绝自动恢复"
  [[ "$(stat -c '%u:%g:%a' "${NODE_REBIND_TRANSACTION}")" == "0:0:600" ]] \
    || fail "节点重绑定事务标记权限异常，拒绝自动恢复"
  mapfile -t marker_lines < "${NODE_REBIND_TRANSACTION}"
  [[ ${#marker_lines[@]} -eq 2 ]] \
    || fail "节点重绑定事务标记格式异常，拒绝自动恢复"
  marker_magic="${marker_lines[0]}"
  marker_backup="${marker_lines[1]}"
  [[ "${marker_magic}" == "${NODE_REBIND_TRANSACTION_MAGIC}" ]] \
    || fail "节点重绑定事务标记版本未知，拒绝自动恢复"
  [[ "${marker_backup}" =~ ^${NODE_REBIND_BACKUP_ROOT}/[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]] \
    || fail "节点重绑定回滚快照路径异常，拒绝自动恢复"
  [[ -d "${marker_backup}" && ! -L "${marker_backup}" ]] \
    || fail "节点重绑定回滚快照缺失或不安全"
  [[ "$(stat -c '%u:%g:%a' "${marker_backup}")" == "0:0:700" ]] \
    || fail "节点重绑定回滚快照权限异常"
  REBIND_NODE_BACKUP_DIR="${marker_backup}"
  REBIND_NODE_MUTATED=1
  rollback_node_rebind \
    || fail "中断的节点重绑定无法自动恢复；事务标记已保留"
  echo "已恢复重绑定前的节点注册状态；私钥、Hysteria 服务和流量 spool 未改动。"
}

rebind_node() {
  local command_name enrollment_token generated_public panel_url
  local -a rebind_commands=(cat chmod cmp curl date install mkdir mktemp mv openssl rm sha256sum stat sync systemctl uname)

  [[ "${PANEL_REF}" == "v${PANEL_VERSION}" ]] \
    || fail "节点重绑定只允许使用当前受签名正式版本 v${PANEL_VERSION}"
  [[ -d /run/systemd/system ]] \
    || fail "节点重绑定需要使用 systemd 的 Linux 服务器"
  [[ ! -e "${MANAGED_MARKER}" && ! -L "${MANAGED_MARKER}" ]] \
    || fail "完整面板服务器不能执行数据节点重绑定"
  require_node_agent_directory "${NODE_AGENT_OPT_DIR}" 755
  require_node_agent_directory "${NODE_AGENT_CONFIG_DIR}" 700
  require_node_agent_file "${NODE_AGENT_OPT_DIR}/node_agent.py" 755
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/node.key" 600
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/node-public.der" 644
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/registration.json" 600
  require_node_agent_file "${NODE_AGENT_HEARTBEAT_SERVICE}" 644
  require_node_agent_file "${NODE_AGENT_HEARTBEAT_TIMER}" 644
  for command_name in "${rebind_commands[@]}"; do
    command -v "${command_name}" >/dev/null 2>&1 \
      || fail "节点重绑定缺少命令 ${command_name}；未修改系统"
  done
  select_python || fail "节点重绑定需要 Python 3.8 或更高版本；未修改系统"
  case "$(uname -m)" in
    x86_64|amd64|aarch64|arm64) ;;
    *) fail "节点重绑定仅支持 Linux amd64 和 arm64" ;;
  esac
  recover_interrupted_node_rebind
  systemctl is-active --quiet hysteria2-panel-node-heartbeat.timer \
    || fail "节点签名心跳 timer 未运行；未修改系统"
  panel_url="${HY2PANEL_PANEL_URL:-}"
  enrollment_token="${HY2PANEL_ENROLLMENT_TOKEN:-}"
  unset HY2PANEL_ENROLLMENT_TOKEN
  [[ "${panel_url}" =~ ^https://[^/?#[:space:]]+/?$ ]] \
    || fail "节点重绑定要求有效的 HTTPS 面板地址"
  [[ "${enrollment_token}" =~ ^[A-Za-z0-9_-]{32,128}$ ]] \
    || fail "缺少或无效的一次性节点重绑定凭据"

  TMP_DIR="$(TMPDIR=/tmp mktemp -d -t hysteria2-panel.XXXXXXXX)"
  download_file "${NODE_AGENT_SOURCE_URL}" "${TMP_DIR}/node_agent.py"
  printf '%s  %s\n' "${NODE_AGENT_SHA256}" "${TMP_DIR}/node_agent.py" \
    | sha256sum --check --status \
    || fail "节点 Agent SHA-256 校验失败"
  "${PYTHON_BIN}" -m py_compile "${TMP_DIR}/node_agent.py" \
    || fail "节点 Agent 语法检查失败"
  generated_public="${TMP_DIR}/node-public.der"
  openssl pkey -in "${NODE_AGENT_CONFIG_DIR}/node.key" -pubout -outform DER \
    -out "${generated_public}" \
    || fail "无法验证既有节点私钥"
  cmp -s "${generated_public}" "${NODE_AGENT_CONFIG_DIR}/node-public.der" \
    || fail "节点公钥与私钥不匹配；未修改系统"

  write_node_rebind_backup \
    || fail "无法创建节点重绑定 root-only 回滚快照；未修改系统"
  arm_node_rebind_transaction \
    || fail "无法持久化节点重绑定事务；未修改系统"
  REBIND_NODE_MUTATED=1
  systemctl stop hysteria2-panel-node-heartbeat.timer \
    hysteria2-panel-node-heartbeat.service \
    || fail "无法暂停节点签名心跳；已安排恢复"
  durable_replace_file "${TMP_DIR}/node_agent.py" \
    "${NODE_AGENT_OPT_DIR}/node_agent.py" 0755 \
    || fail "无法更新节点 Agent；已安排恢复"
  if ! HY2PANEL_ENROLLMENT_TOKEN="${enrollment_token}" \
    "${PYTHON_BIN}" "${NODE_AGENT_OPT_DIR}/node_agent.py" register \
      --panel-url "${panel_url}" \
      --public-key "${NODE_AGENT_CONFIG_DIR}/node-public.der" \
      --state-file "${TMP_DIR}/registration.json"; then
    enrollment_token=""
    fail "节点重新注册失败；已安排恢复原注册状态"
  fi
  enrollment_token=""
  require_node_agent_file "${TMP_DIR}/registration.json" 600
  durable_replace_file "${TMP_DIR}/registration.json" \
    "${NODE_AGENT_CONFIG_DIR}/registration.json" 0600 \
    || fail "无法提交新的节点注册状态；已安排恢复"
  systemctl enable --now hysteria2-panel-node-heartbeat.timer \
    || fail "无法恢复节点签名心跳 timer；已安排恢复"
  rm -f -- "${NODE_REBIND_TRANSACTION}"
  sync -f "${NODE_AGENT_OPT_DIR}" "${NODE_AGENT_CONFIG_DIR}" \
    /etc/systemd/system
  REBIND_NODE_MUTATED=0
  echo "节点重绑定已进入待验证状态；私钥、Hysteria 身份、运行中的数据面和流量 spool 均保持不变。请在面板核对原公钥指纹；验证后 heartbeat timer 会自动上线节点，再启用控制协议。"
}

install_join_node() {
  local command_name enrollment_token fingerprint panel_url path
  local -a join_commands=(awk cat curl install mkdir mktemp openssl rm sha256sum stat sync systemctl uname)

  [[ "${PANEL_REF}" == "v${PANEL_VERSION}" ]] \
    || fail "节点对接只允许使用当前受签名正式版本 v${PANEL_VERSION}"
  [[ -d /run/systemd/system ]] \
    || fail "节点对接需要使用 systemd 的 Linux 服务器"
  panel_url="${HY2PANEL_PANEL_URL:-}"
  enrollment_token="${HY2PANEL_ENROLLMENT_TOKEN:-}"
  unset HY2PANEL_ENROLLMENT_TOKEN
  [[ "${panel_url}" =~ ^https://[^/?#[:space:]]+/?$ ]] \
    || fail "节点对接要求有效的 HTTPS 面板地址"
  [[ "${enrollment_token}" =~ ^[A-Za-z0-9_-]{32,128}$ ]] \
    || fail "缺少或无效的一次性节点对接凭据"
  [[ ! -e "${MANAGED_MARKER}" && ! -L "${MANAGED_MARKER}" ]] \
    || fail "该服务器已安装完整面板，不能作为第一阶段对接节点"
  for path in "${NODE_AGENT_OPT_DIR}" "${NODE_AGENT_CONFIG_DIR}"; do
    [[ ! -e "${path}" && ! -L "${path}" ]] \
      || fail "节点 Agent 路径已存在；为避免覆盖未知数据，对接已停止：${path}"
  done
  for command_name in "${join_commands[@]}"; do
    command -v "${command_name}" >/dev/null 2>&1 \
      || fail "节点对接缺少命令 ${command_name}；未修改系统"
  done
  select_python || fail "节点对接需要 Python 3.8 或更高版本；未修改系统"
  case "$(uname -m)" in
    x86_64|amd64|aarch64|arm64) ;;
    *) fail "节点对接仅支持 Linux amd64 和 arm64" ;;
  esac

  TMP_DIR="$(TMPDIR=/tmp mktemp -d -t hysteria2-panel.XXXXXXXX)"
  download_file "${NODE_AGENT_SOURCE_URL}" "${TMP_DIR}/node_agent.py"
  printf '%s  %s\n' "${NODE_AGENT_SHA256}" "${TMP_DIR}/node_agent.py" \
    | sha256sum --check --status \
    || fail "节点 Agent SHA-256 校验失败"
  "${PYTHON_BIN}" -m py_compile "${TMP_DIR}/node_agent.py" \
    || fail "节点 Agent 语法检查失败"
  umask 077
  openssl genpkey -algorithm ED25519 -out "${TMP_DIR}/node.key" \
    || fail "无法生成节点 Agent 私钥"
  openssl pkey -in "${TMP_DIR}/node.key" -pubout -outform DER \
    -out "${TMP_DIR}/node-public.der" \
    || fail "无法生成节点 Agent 公钥"

  cat > "${TMP_DIR}/hysteria2-panel-node-onboarding.service" <<EOF
[Unit]
Description=Complete Hysteria2-panel node onboarding after operator verification
After=network-online.target
Wants=network-online.target
ConditionPathExists=${NODE_ONBOARDING_MARKER}

[Service]
Type=oneshot
User=root
Group=root
ExecStart=${NODE_ONBOARDING_INSTALLER} --complete-node-onboarding
UMask=0077
TimeoutStartSec=25min
PrivateTmp=true
PrivateDevices=true
ProtectHome=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
TasksMax=512
MemoryMax=2G
EOF
  cat > "${TMP_DIR}/hysteria2-panel-node-onboarding.timer" <<'EOF'
[Unit]
Description=Retry Hysteria2-panel node onboarding until operator verification

[Timer]
OnBootSec=10s
OnUnitActiveSec=30s
Persistent=true
AccuracySec=1s
Unit=hysteria2-panel-node-onboarding.service

[Install]
WantedBy=timers.target
EOF
  printf '%s\n' 'HYSTERIA2_PANEL_NODE_ONBOARDING_V1' \
    > "${TMP_DIR}/onboarding-pending"

  JOIN_NODE_MUTATED=1
  install -d -o root -g root -m 0755 "${NODE_AGENT_OPT_DIR}"
  install -d -o root -g root -m 0700 "${NODE_AGENT_CONFIG_DIR}"
  install -o root -g root -m 0755 "${TMP_DIR}/node_agent.py" \
    "${NODE_AGENT_OPT_DIR}/node_agent.py"
  install -o root -g root -m 0700 "$0" "${NODE_ONBOARDING_INSTALLER}"
  install -o root -g root -m 0600 "${TMP_DIR}/node.key" \
    "${NODE_AGENT_CONFIG_DIR}/node.key"
  install -o root -g root -m 0644 "${TMP_DIR}/node-public.der" \
    "${NODE_AGENT_CONFIG_DIR}/node-public.der"
  install -o root -g root -m 0600 "${TMP_DIR}/onboarding-pending" \
    "${NODE_ONBOARDING_MARKER}"
  install -o root -g root -m 0644 \
    "${TMP_DIR}/hysteria2-panel-node-onboarding.service" \
    "${NODE_ONBOARDING_SERVICE}"
  install -o root -g root -m 0644 \
    "${TMP_DIR}/hysteria2-panel-node-onboarding.timer" \
    "${NODE_ONBOARDING_TIMER}"
  if ! HY2PANEL_ENROLLMENT_TOKEN="${enrollment_token}" \
    "${PYTHON_BIN}" "${NODE_AGENT_OPT_DIR}/node_agent.py" register \
      --panel-url "${panel_url}" \
      --public-key "${NODE_AGENT_CONFIG_DIR}/node-public.der" \
      --state-file "${NODE_AGENT_CONFIG_DIR}/registration.json"; then
    enrollment_token=""
    fail "节点注册失败；已安排清理本次新增文件"
  fi
  enrollment_token=""
  systemctl daemon-reload
  systemctl enable --now hysteria2-panel-node-onboarding.timer \
    || fail "无法启用节点自动收尾 timer；已安排清理本次新增文件"
  sync -f "${NODE_AGENT_OPT_DIR}"
  sync -f "${NODE_AGENT_CONFIG_DIR}"
  sync -f /etc/systemd/system
  fingerprint="$(sha256sum "${NODE_AGENT_CONFIG_DIR}/node-public.der" | awk '{print $1}')"
  echo "节点 Agent 已安装；请在面板核对并确认此公钥指纹："
  echo "  短码：${fingerprint:0:16}"
  echo "  完整：${fingerprint}"
  echo "确认后本机将自动完成签名心跳、FULL/UDP 443、fq/BBR、16 MiB UDP 缓冲和数据面部署。安装器不会修改 DNS。"
}

complete_node_onboarding() {
  local bootstrap_token marker_value

  [[ "${PANEL_REF}" == "v${PANEL_VERSION}" ]] \
    || fail "节点自动收尾只允许使用最初核验过的正式版本 v${PANEL_VERSION}"
  [[ -d /run/systemd/system ]] \
    || fail "节点自动收尾需要使用 systemd 的 Linux 服务器"
  [[ ! -e "${MANAGED_MARKER}" && ! -L "${MANAGED_MARKER}" ]] \
    || fail "完整面板服务器不能执行分流节点自动收尾"
  require_node_agent_directory "${NODE_AGENT_OPT_DIR}" 755
  require_node_agent_directory "${NODE_AGENT_CONFIG_DIR}" 700
  require_node_agent_file "${NODE_AGENT_OPT_DIR}/node_agent.py" 755
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/node.key" 600
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/node-public.der" 644
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/registration.json" 600
  require_node_agent_file "${NODE_ONBOARDING_INSTALLER}" 700
  require_node_agent_file "${NODE_ONBOARDING_SERVICE}" 644
  require_node_agent_file "${NODE_ONBOARDING_TIMER}" 644
  require_node_agent_file "${NODE_ONBOARDING_MARKER}" 600
  marker_value="$(cat "${NODE_ONBOARDING_MARKER}")"
  [[ "${marker_value}" == "HYSTERIA2_PANEL_NODE_ONBOARDING_V1" ]] \
    || fail "节点自动收尾标记无效；拒绝继续"
  select_python || fail "节点自动收尾需要 Python 3.8 或更高版本"

  # A successful activation removes its durable data-plane transaction only
  # after the central ACK.  If the process then dies before removing the
  # onboarding marker, the fully healthy local installation is authoritative
  # evidence that only the timer cleanup remains.
  if [[ ! -e "${NODE_DATA_PLANE_TRANSACTION}" \
    && ! -L "${NODE_DATA_PLANE_TRANSACTION}" ]]; then
    inspect_existing_data_plane
    if (( DATA_PLANE_EXISTING == 1 )); then
      rm -f -- "${NODE_ONBOARDING_MARKER}"
      systemctl disable --now --no-block \
        hysteria2-panel-node-onboarding.timer >/dev/null 2>&1 || true
      sync -f "${NODE_AGENT_CONFIG_DIR}" /etc/systemd/system
      echo "节点自动对接此前已完成；本次仅清理持久完成器。"
      return 0
    fi
  fi

  install -d -o root -g root -m 0700 "${NODE_ONBOARDING_RUNTIME_DIR}"
  rm -f -- "${NODE_ONBOARDING_TOKEN_FILE}"
  if ! "${PYTHON_BIN}" "${NODE_AGENT_OPT_DIR}/node_agent.py" claim-data-plane \
    --private-key "${NODE_AGENT_CONFIG_DIR}/node.key" \
    --state-file "${NODE_AGENT_CONFIG_DIR}/registration.json" \
    --output-token "${NODE_ONBOARDING_TOKEN_FILE}"; then
    rm -f -- "${NODE_ONBOARDING_TOKEN_FILE}"
    echo "节点尚未通过面板指纹确认，自动收尾将在 30 秒后安全重试。"
    return 0
  fi
  require_node_agent_file "${NODE_ONBOARDING_TOKEN_FILE}" 600
  bootstrap_token="$(< "${NODE_ONBOARDING_TOKEN_FILE}")"
  rm -f -- "${NODE_ONBOARDING_TOKEN_FILE}"
  [[ "${bootstrap_token}" =~ ^[A-Za-z0-9_-]{32,128}$ ]] \
    || fail "面板返回的一次性数据面凭据无效"

  if [[ ! -e "${NODE_AGENT_HEARTBEAT_SERVICE}" && \
    ! -L "${NODE_AGENT_HEARTBEAT_SERVICE}" && \
    ! -e "${NODE_AGENT_HEARTBEAT_TIMER}" && \
    ! -L "${NODE_AGENT_HEARTBEAT_TIMER}" ]]; then
    ACTIVATE_NODE_AGENT=1
    activate_node_agent
    ACTIVATE_NODE_AGENT_MUTATED=0
    ACTIVATE_NODE_AGENT=0
  else
    require_node_agent_file "${NODE_AGENT_HEARTBEAT_SERVICE}" 644
    require_node_agent_file "${NODE_AGENT_HEARTBEAT_TIMER}" 644
    systemctl is-active --quiet hysteria2-panel-node-heartbeat.timer \
      || fail "既有节点签名心跳 timer 未运行；自动收尾已停止"
  fi

  ACTIVATE_DATA_PLANE=1
  HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN="${bootstrap_token}" activate_data_plane
  bootstrap_token=""
  ACTIVATE_DATA_PLANE=0
  DATA_PLANE_MUTATED=0
  rm -f -- "${NODE_ONBOARDING_MARKER}"
  systemctl disable --now --no-block hysteria2-panel-node-onboarding.timer \
    >/dev/null 2>&1 || true
  sync -f "${NODE_AGENT_CONFIG_DIR}" /etc/systemd/system
  echo "节点自动对接已完成；可继续为该节点配置 DNS。"
}

rollback_node_agent_activation() {
  systemctl disable --now hysteria2-panel-node-heartbeat.timer >/dev/null 2>&1 || true
  systemctl stop hysteria2-panel-node-heartbeat.service >/dev/null 2>&1 || true
  if [[ -n "${NODE_AGENT_BACKUP_FILE}" && -f "${NODE_AGENT_BACKUP_FILE}" ]]; then
    install -o root -g root -m 0755 "${NODE_AGENT_BACKUP_FILE}" \
      "${NODE_AGENT_OPT_DIR}/node_agent.py" || return 1
  fi
  rm -f -- "${NODE_AGENT_HEARTBEAT_SERVICE}" "${NODE_AGENT_HEARTBEAT_TIMER}" \
    || return 1
  systemctl daemon-reload || return 1
  sync -f "${NODE_AGENT_OPT_DIR}" || return 1
  sync -f /etc/systemd/system || return 1
  ACTIVATE_NODE_AGENT_MUTATED=0
}

require_node_agent_directory() {
  local path="$1" expected_mode="$2"
  [[ -d "${path}" && ! -L "${path}" ]] \
    || fail "节点 Agent 目录缺失或不安全：${path}"
  [[ "$(stat -c '%u:%g:%a' "${path}")" == "0:0:${expected_mode}" ]] \
    || fail "节点 Agent 目录所有者或权限不符合要求：${path}"
}

require_node_agent_file() {
  local path="$1" expected_mode="$2"
  [[ -f "${path}" && ! -L "${path}" ]] \
    || fail "节点 Agent 文件缺失或不安全：${path}"
  [[ "$(stat -c '%u:%g:%a' "${path}")" == "0:0:${expected_mode}" ]] \
    || fail "节点 Agent 文件所有者或权限不符合要求：${path}"
}

activate_node_agent() {
  local command_name generated_public
  local -a activation_commands=(cat cmp curl install mktemp openssl rm sha256sum stat sync systemctl)

  [[ "${PANEL_REF}" == "v${PANEL_VERSION}" ]] \
    || fail "节点心跳只允许使用当前受签名正式版本 v${PANEL_VERSION}"
  [[ -d /run/systemd/system ]] \
    || fail "节点心跳需要使用 systemd 的 Linux 服务器"
  [[ ! -e "${MANAGED_MARKER}" && ! -L "${MANAGED_MARKER}" ]] \
    || fail "完整面板服务器不能启用分流节点 Agent"
  require_node_agent_directory "${NODE_AGENT_OPT_DIR}" 755
  require_node_agent_directory "${NODE_AGENT_CONFIG_DIR}" 700
  require_node_agent_file "${NODE_AGENT_OPT_DIR}/node_agent.py" 755
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/node.key" 600
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/node-public.der" 644
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/registration.json" 600
  [[ ! -e "${NODE_AGENT_HEARTBEAT_SERVICE}" && ! -L "${NODE_AGENT_HEARTBEAT_SERVICE}" ]] \
    || fail "节点心跳 service 已存在；为避免覆盖未知配置，启用已停止"
  [[ ! -e "${NODE_AGENT_HEARTBEAT_TIMER}" && ! -L "${NODE_AGENT_HEARTBEAT_TIMER}" ]] \
    || fail "节点心跳 timer 已存在；为避免覆盖未知配置，启用已停止"
  for command_name in "${activation_commands[@]}"; do
    command -v "${command_name}" >/dev/null 2>&1 \
      || fail "节点心跳缺少命令 ${command_name}；未修改系统"
  done
  select_python || fail "节点心跳需要 Python 3.8 或更高版本；未修改系统"

  TMP_DIR="$(TMPDIR=/tmp mktemp -d -t hysteria2-panel.XXXXXXXX)"
  download_file "${NODE_AGENT_SOURCE_URL}" "${TMP_DIR}/node_agent.py"
  printf '%s  %s\n' "${NODE_AGENT_SHA256}" "${TMP_DIR}/node_agent.py" \
    | sha256sum --check --status \
    || fail "节点 Agent SHA-256 校验失败"
  "${PYTHON_BIN}" -m py_compile "${TMP_DIR}/node_agent.py" \
    || fail "节点 Agent 语法检查失败"
  generated_public="${TMP_DIR}/node-public.der"
  openssl pkey -in "${NODE_AGENT_CONFIG_DIR}/node.key" -pubout -outform DER \
    -out "${generated_public}" \
    || fail "无法验证节点私钥"
  cmp -s "${generated_public}" "${NODE_AGENT_CONFIG_DIR}/node-public.der" \
    || fail "节点公钥与私钥不匹配；未修改系统"

  NODE_AGENT_BACKUP_FILE="${TMP_DIR}/node_agent.py.previous"
  install -o root -g root -m 0755 "${NODE_AGENT_OPT_DIR}/node_agent.py" \
    "${NODE_AGENT_BACKUP_FILE}"
  cat > "${TMP_DIR}/hysteria2-panel-node-heartbeat.service" <<EOF
[Unit]
Description=Hysteria2-panel signed node heartbeat
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
ExecStart=${PYTHON_BIN} "${NODE_AGENT_OPT_DIR}/node_agent.py" heartbeat --private-key "${NODE_AGENT_CONFIG_DIR}/node.key" --state-file "${NODE_AGENT_CONFIG_DIR}/registration.json"
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_INET AF_INET6
ReadOnlyPaths=${NODE_AGENT_OPT_DIR} ${NODE_AGENT_CONFIG_DIR}
UMask=0077
TimeoutStartSec=20
EOF
  cat > "${TMP_DIR}/hysteria2-panel-node-heartbeat.timer" <<'EOF'
[Unit]
Description=Run the Hysteria2-panel signed node heartbeat every minute

[Timer]
OnBootSec=60s
OnUnitActiveSec=60s
RandomizedDelaySec=5s
Persistent=true
AccuracySec=1s
Unit=hysteria2-panel-node-heartbeat.service

[Install]
WantedBy=timers.target
EOF

  ACTIVATE_NODE_AGENT_MUTATED=1
  install -o root -g root -m 0755 "${TMP_DIR}/node_agent.py" \
    "${NODE_AGENT_OPT_DIR}/node_agent.py"
  install -o root -g root -m 0644 \
    "${TMP_DIR}/hysteria2-panel-node-heartbeat.service" \
    "${NODE_AGENT_HEARTBEAT_SERVICE}"
  install -o root -g root -m 0644 \
    "${TMP_DIR}/hysteria2-panel-node-heartbeat.timer" \
    "${NODE_AGENT_HEARTBEAT_TIMER}"
  systemctl daemon-reload
  systemctl start hysteria2-panel-node-heartbeat.service \
    || fail "节点签名心跳未被面板接受；已安排回滚"
  systemctl enable --now hysteria2-panel-node-heartbeat.timer
  sync -f "${NODE_AGENT_OPT_DIR}"
  sync -f /etc/systemd/system
  ACTIVATE_NODE_AGENT_MUTATED=0
  echo "节点签名心跳已启用；未安装 Hysteria，也未修改网络、DNS 或任何节点证书。"
}

initialize_data_plane_owned_paths() {
  DATA_PLANE_OWNED_FILES=(
    "${NODE_AGENT_OPT_DIR}/bin/hysteria"
    "${NODE_AGENT_OPT_DIR}/tcp_probe.py"
    "${NODE_AGENT_CONFIG_DIR}/server.crt"
    "${NODE_AGENT_CONFIG_DIR}/server.key"
    "${NODE_AGENT_CONFIG_DIR}/hysteria-main.yaml"
    "${NODE_AGENT_CONFIG_DIR}/hysteria-udp443.yaml"
    "${NODE_AGENT_CONFIG_DIR}/stats.env"
    "${NODE_AGENT_CONFIG_DIR}/bootstrap.json"
    "${NODE_AGENT_CONFIG_DIR}/data-plane-firewall.state"
  )
  DATA_PLANE_OWNED_UNITS=(
    /etc/systemd/system/hysteria2-panel-node-auth.service
    /etc/systemd/system/hysteria2-panel-node-control.service
    /etc/systemd/system/hysteria2-panel-node-hysteria-main.service
    /etc/systemd/system/hysteria2-panel-node-hysteria-udp443.service
    /etc/systemd/system/hysteria2-panel-node-tcp-probe-main.service
    /etc/systemd/system/hysteria2-panel-node-tcp-probe-udp443.service
  )
}

assert_data_plane_network_stack_claimable() {
  if [[ -e "${NODE_SYSCTL_FILE}" || -L "${NODE_SYSCTL_FILE}" ]]; then
    [[ -f "${NODE_SYSCTL_FILE}" && ! -L "${NODE_SYSCTL_FILE}" ]] \
      || fail "数据节点内核配置路径不安全，拒绝修改：${NODE_SYSCTL_FILE}"
    [[ "$(stat -c '%u:%g:%a' "${NODE_SYSCTL_FILE}")" == "0:0:644" ]] \
      || fail "数据节点内核配置权限异常，拒绝修改：${NODE_SYSCTL_FILE}"
    grep -q '^# Managed by Hysteria2-panel data node$' "${NODE_SYSCTL_FILE}" \
      || fail "${NODE_SYSCTL_FILE} 已存在且不属于本安装器，拒绝覆盖"
  fi
}

write_data_plane_network_snapshot() {
  local cc qdisc rmem state_file sysctl_presence wmem
  state_file="${DATA_PLANE_BACKUP_DIR}/network-state"
  rmem="$(sysctl -n net.core.rmem_max 2>/dev/null)" || return 1
  wmem="$(sysctl -n net.core.wmem_max 2>/dev/null)" || return 1
  qdisc="$(sysctl -n net.core.default_qdisc 2>/dev/null)" || return 1
  cc="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null)" || return 1
  [[ "${rmem}" =~ ^[0-9]+$ && "${wmem}" =~ ^[0-9]+$ ]] || return 1
  [[ "${qdisc}" =~ ^[A-Za-z0-9_-]+$ && "${cc}" =~ ^[A-Za-z0-9_-]+$ ]] \
    || return 1
  sysctl_presence=absent
  if [[ -f "${NODE_SYSCTL_FILE}" && ! -L "${NODE_SYSCTL_FILE}" ]]; then
    sysctl_presence=present
    install -o root -g root -m 0644 "${NODE_SYSCTL_FILE}" \
      "${DATA_PLANE_BACKUP_DIR}/node-sysctl.conf"
  fi
  {
    echo "HYSTERIA2_PANEL_NODE_NETWORK_V1"
    echo "${rmem}"
    echo "${wmem}"
    echo "${qdisc}"
    echo "${cc}"
    echo "${sysctl_presence}"
  } > "${state_file}"
  chmod 0600 "${state_file}"
}

restore_data_plane_network_snapshot() {
  local cc qdisc rmem sysctl_presence wmem
  local -a state_lines=()
  [[ -f "${DATA_PLANE_BACKUP_DIR}/network-state" \
    && ! -L "${DATA_PLANE_BACKUP_DIR}/network-state" ]] || return 1
  mapfile -t state_lines < "${DATA_PLANE_BACKUP_DIR}/network-state"
  [[ ${#state_lines[@]} -eq 6 \
    && "${state_lines[0]}" == "HYSTERIA2_PANEL_NODE_NETWORK_V1" ]] || return 1
  rmem="${state_lines[1]}"
  wmem="${state_lines[2]}"
  qdisc="${state_lines[3]}"
  cc="${state_lines[4]}"
  sysctl_presence="${state_lines[5]}"
  [[ "${rmem}" =~ ^[0-9]+$ && "${wmem}" =~ ^[0-9]+$ ]] || return 1
  [[ "${qdisc}" =~ ^[A-Za-z0-9_-]+$ && "${cc}" =~ ^[A-Za-z0-9_-]+$ ]] \
    || return 1
  [[ "${sysctl_presence}" == "present" || "${sysctl_presence}" == "absent" ]] \
    || return 1
  sysctl -w "net.core.rmem_max=${rmem}" >/dev/null || return 1
  sysctl -w "net.core.wmem_max=${wmem}" >/dev/null || return 1
  sysctl -w "net.core.default_qdisc=${qdisc}" >/dev/null || return 1
  sysctl -w "net.ipv4.tcp_congestion_control=${cc}" >/dev/null || return 1
  if [[ "${sysctl_presence}" == "present" ]]; then
    [[ -f "${DATA_PLANE_BACKUP_DIR}/node-sysctl.conf" \
      && ! -L "${DATA_PLANE_BACKUP_DIR}/node-sysctl.conf" ]] || return 1
    install -o root -g root -m 0644 \
      "${DATA_PLANE_BACKUP_DIR}/node-sysctl.conf" "${NODE_SYSCTL_FILE}" \
      || return 1
  else
    rm -f -- "${NODE_SYSCTL_FILE}" || return 1
  fi
  sync -f /etc/sysctl.d || return 1
}

optimize_data_plane_network_stack() {
  local available_cc current_rmem current_wmem sysctl_stage target_rmem target_wmem
  current_rmem="$(sysctl -n net.core.rmem_max 2>/dev/null)" || return 1
  current_wmem="$(sysctl -n net.core.wmem_max 2>/dev/null)" || return 1
  [[ "${current_rmem}" =~ ^[0-9]+$ && "${current_wmem}" =~ ^[0-9]+$ ]] \
    || return 1
  target_rmem="${MIN_QUIC_UDP_BUFFER}"
  target_wmem="${MIN_QUIC_UDP_BUFFER}"
  (( current_rmem <= target_rmem )) || target_rmem="${current_rmem}"
  (( current_wmem <= target_wmem )) || target_wmem="${current_wmem}"
  if command -v modprobe >/dev/null 2>&1; then
    modprobe tcp_bbr >/dev/null 2>&1 || true
  fi
  available_cc="$(sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null)" \
    || return 1
  [[ " ${available_cc} " == *" bbr "* ]] || return 1
  sysctl -w "net.core.rmem_max=${target_rmem}" >/dev/null || return 1
  sysctl -w "net.core.wmem_max=${target_wmem}" >/dev/null || return 1
  sysctl -w net.core.default_qdisc=fq >/dev/null || return 1
  sysctl -w net.ipv4.tcp_congestion_control=bbr >/dev/null || return 1
  [[ "$(sysctl -n net.core.rmem_max)" -ge "${MIN_QUIC_UDP_BUFFER}" ]] || return 1
  [[ "$(sysctl -n net.core.wmem_max)" -ge "${MIN_QUIC_UDP_BUFFER}" ]] || return 1
  [[ "$(sysctl -n net.core.default_qdisc)" == "fq" ]] || return 1
  [[ "$(sysctl -n net.ipv4.tcp_congestion_control)" == "bbr" ]] || return 1
  sysctl_stage="${TMP_DIR}/99-hysteria2-panel-node.conf"
  cat > "${sysctl_stage}" <<EOF
# Managed by Hysteria2-panel data node
# Hysteria recommends 16 MiB UDP buffers for high-bandwidth QUIC transfers.
net.core.rmem_max=${target_rmem}
net.core.wmem_max=${target_wmem}
# TCP BBR benefits the data node's TCP egress to web and video origins.
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF
  install -o root -g root -m 0644 "${sysctl_stage}" "${NODE_SYSCTL_FILE}" \
    || return 1
  sync -f "${NODE_SYSCTL_FILE}" /etc/sysctl.d || return 1
  echo "数据节点网络优化：Hysteria BBR standard + 内核 fq/BBR + 16 MiB UDP 缓冲"
}

assert_data_plane_paths_unclaimed() {
  local path
  initialize_data_plane_owned_paths
  for path in "${DATA_PLANE_OWNED_FILES[@]}" "${DATA_PLANE_OWNED_UNITS[@]}" \
    "${NODE_AGENT_OPT_DIR}/bin" /var/lib/hysteria2-panel-node \
    "${NODE_DATA_PLANE_TRANSACTION}"; do
    [[ ! -e "${path}" && ! -L "${path}" ]] \
      || fail "数据面路径已存在；为避免覆盖未知数据，部署已停止：${path}"
  done
}

read_data_plane_main_port() {
  local metadata="$1" compatibility="${2:-strict}"
  "${PYTHON_BIN}" - "${metadata}" "${compatibility}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
raw = path.read_bytes()
if not raw or len(raw) > 8192:
    raise SystemExit(1)
record = json.loads(raw.decode("ascii"))
port = record.get("mainPort") if isinstance(record, dict) else None
if port is None and sys.argv[2] == "legacy-19999":
    port = 19999
if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535 or port in {443, 19995, 19996, 19997}:
    raise SystemExit(1)
print(port)
PY
}

inspect_data_plane_state_item() {
  local path="$1" metadata
  if ! metadata="$(stat -c '%u:%g:%a:%F' -- "${path}" 2>/dev/null)"; then
    if [[ "${path}" == "${NODE_AGENT_STATE_DIR}/spool/"* \
      && ! -e "${path}" && ! -L "${path}" ]]; then
      return 2
    fi
    return 1
  fi
  [[ "${metadata}" == "0:0:700:directory" \
    || "${metadata}" == "0:0:600:regular file" ]]
}

assert_existing_data_plane_healthy() {
  local inspection_status mode path unit
  initialize_data_plane_owned_paths
  for path in "${DATA_PLANE_OWNED_FILES[@]}"; do
    [[ "${path}" == "${NODE_AGENT_CONFIG_DIR}/data-plane-firewall.state" ]] \
      && [[ ! -e "${path}" && ! -L "${path}" ]] && continue
    [[ -f "${path}" && ! -L "${path}" ]] \
      || fail "已安装数据面缺少受管文件：${path}"
    mode=600
    [[ "${path}" == "${NODE_AGENT_OPT_DIR}/bin/hysteria" \
      || "${path}" == "${NODE_AGENT_OPT_DIR}/tcp_probe.py" ]] && mode=755
    [[ "$(stat -c '%u:%g:%a' "${path}")" == "0:0:${mode}" ]] \
      || fail "已安装数据面文件权限异常：${path}"
  done
  for path in "${DATA_PLANE_OWNED_UNITS[@]}"; do
    [[ -f "${path}" && ! -L "${path}" \
      && "$(stat -c '%u:%g:%a' "${path}")" == "0:0:644" ]] \
      || fail "已安装数据面 systemd 单元不安全：${path}"
    unit="${path##*/}"
    systemctl is-enabled --quiet "${unit}" \
      || fail "已安装数据面单元未启用：${unit}"
    systemctl is-active --quiet "${unit}" \
      || fail "已安装数据面单元未运行：${unit}"
  done
  [[ -d "${NODE_AGENT_OPT_DIR}/bin" \
    && ! -L "${NODE_AGENT_OPT_DIR}/bin" \
    && "$(stat -c '%u:%g:%a' "${NODE_AGENT_OPT_DIR}/bin")" == "0:0:755" ]] \
    || fail "已安装数据面二进制目录不安全"
  [[ -d "${NODE_AGENT_STATE_DIR}" \
    && ! -L "${NODE_AGENT_STATE_DIR}" \
    && "$(stat -c '%u:%g:%a' "${NODE_AGENT_STATE_DIR}")" == "0:0:700" ]] \
    || fail "已安装数据面状态目录不安全"
  [[ -z "$(find "${NODE_AGENT_STATE_DIR}" -xdev -type l -print -quit)" ]] \
    || fail "已安装数据面状态目录包含符号链接"
  [[ -z "$(find "${NODE_AGENT_STATE_DIR}" -xdev ! -type d ! -type f -print -quit)" ]] \
    || fail "已安装数据面状态目录包含特殊文件"
  DATA_PLANE_MAIN_PORT="$(read_data_plane_main_port \
    "${NODE_AGENT_CONFIG_DIR}/bootstrap.json" legacy-19999)" \
    || fail "已安装数据面主端口元数据异常"
  while IFS= read -r -d '' path; do
    if inspect_data_plane_state_item "${path}"; then
      :
    else
      inspection_status=$?
      (( inspection_status == 2 )) && continue
      fail "已安装数据面状态项身份或权限异常：${path}"
    fi
  done < <(find "${NODE_AGENT_STATE_DIR}" -xdev \
    \( -type d -o -type f \) -print0)
  ss -H -lun "sport = :${DATA_PLANE_MAIN_PORT}" | grep -q . \
    || fail "既有数据面 UDP ${DATA_PLANE_MAIN_PORT} 未监听"
  ss -H -lun "sport = :443" | grep -q . || fail "既有数据面 UDP 443 未监听"
  ss -H -ltn "sport = :${DATA_PLANE_MAIN_PORT}" | grep -q . \
    || fail "既有数据面 TCP ${DATA_PLANE_MAIN_PORT} 未监听"
  ss -H -ltn "sport = :443" | grep -q . || fail "既有数据面 TCP 443 未监听"
}

inspect_existing_data_plane() {
  local path present=0
  initialize_data_plane_owned_paths
  for path in "${DATA_PLANE_OWNED_FILES[@]}" "${DATA_PLANE_OWNED_UNITS[@]}" \
    "${NODE_AGENT_OPT_DIR}/bin" /var/lib/hysteria2-panel-node; do
    [[ -e "${path}" || -L "${path}" ]] && present=1
  done
  if (( present == 0 )); then
    DATA_PLANE_EXISTING=0
    return 0
  fi
  DATA_PLANE_EXISTING=1
  assert_existing_data_plane_healthy
}

assert_data_plane_ports_available() {
  local kind port
  for kind in -lun -ltn; do
    for port in 443 19995 19996 19997 "${DATA_PLANE_MAIN_PORT}"; do
      if ss -H "${kind}" "sport = :${port}" | grep -q .; then
        fail "数据面端口已被占用；未修改系统：${port}"
      fi
    done
  done
}

assert_data_plane_main_port_available() {
  local kind
  for kind in -lun -ltn; do
    if ss -H "${kind}" "sport = :${DATA_PLANE_MAIN_PORT}" | grep -q .; then
      fail "数据面主端口已被占用；未修改系统：${DATA_PLANE_MAIN_PORT}"
    fi
  done
}

write_data_plane_backup_manifest() {
  local path timestamp manifest
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  DATA_PLANE_BACKUP_DIR="${NODE_DATA_PLANE_BACKUP_ROOT}/${timestamp}-phase4"
  [[ ! -e "${DATA_PLANE_BACKUP_DIR}" && ! -L "${DATA_PLANE_BACKUP_DIR}" ]] \
    || return 1
  install -d -o root -g root -m 0700 "${NODE_DATA_PLANE_BACKUP_ROOT}"
  install -d -o root -g root -m 0700 "${DATA_PLANE_BACKUP_DIR}"
  DATA_PLANE_NODE_AGENT_BACKUP_FILE="${DATA_PLANE_BACKUP_DIR}/node_agent.py"
  install -o root -g root -m 0755 "${NODE_AGENT_OPT_DIR}/node_agent.py" \
    "${DATA_PLANE_NODE_AGENT_BACKUP_FILE}"
  write_data_plane_network_snapshot || return 1
  if (( DATA_PLANE_EXISTING == 1 )); then
    install -d -o root -g root -m 0700 \
      "${DATA_PLANE_BACKUP_DIR}/opt" \
      "${DATA_PLANE_BACKUP_DIR}/config" \
      "${DATA_PLANE_BACKUP_DIR}/units"
    install -o root -g root -m 0755 "${NODE_AGENT_OPT_DIR}/node_agent.py" \
      "${DATA_PLANE_BACKUP_DIR}/opt/node_agent.py"
    install -o root -g root -m 0755 "${NODE_AGENT_OPT_DIR}/tcp_probe.py" \
      "${DATA_PLANE_BACKUP_DIR}/opt/tcp_probe.py"
    install -o root -g root -m 0755 "${NODE_AGENT_OPT_DIR}/bin/hysteria" \
      "${DATA_PLANE_BACKUP_DIR}/opt/hysteria"
    for path in "${DATA_PLANE_OWNED_FILES[@]}"; do
      [[ "${path}" == "${NODE_AGENT_OPT_DIR}/bin/hysteria" \
        || "${path}" == "${NODE_AGENT_OPT_DIR}/tcp_probe.py" ]] && continue
      [[ -e "${path}" || -L "${path}" ]] || continue
      install -o root -g root -m 0600 "${path}" \
        "${DATA_PLANE_BACKUP_DIR}/config/${path##*/}"
    done
    for path in "${DATA_PLANE_OWNED_UNITS[@]}"; do
      install -o root -g root -m 0644 "${path}" \
        "${DATA_PLANE_BACKUP_DIR}/units/${path##*/}"
    done
    cp -a -- /var/lib/hysteria2-panel-node \
      "${DATA_PLANE_BACKUP_DIR}/state"
    printf '%s\n' existing > "${DATA_PLANE_BACKUP_DIR}/deployment-kind"
  else
    printf '%s\n' fresh > "${DATA_PLANE_BACKUP_DIR}/deployment-kind"
  fi
  chmod 0600 "${DATA_PLANE_BACKUP_DIR}/deployment-kind"
  manifest="${DATA_PLANE_BACKUP_DIR}/manifest.sha256"
  (
    cd "${DATA_PLANE_BACKUP_DIR}"
    : > manifest.sha256
    while IFS= read -r -d '' path; do
      sha256sum "${path#./}" >> manifest.sha256
    done < <(find . -type f ! -name manifest.sha256 -print0 | sort -z)
  )
  chmod 0600 "${manifest}"
  sync -f "${DATA_PLANE_BACKUP_DIR}" "${NODE_DATA_PLANE_BACKUP_ROOT}"
}

arm_data_plane_transaction() {
  local stage="${TMP_DIR}/data-plane-transaction"
  {
    echo "${DATA_PLANE_TRANSACTION_MAGIC}"
    echo "${DATA_PLANE_BACKUP_DIR}"
  } > "${stage}"
  durable_replace_file "${stage}" "${NODE_DATA_PLANE_TRANSACTION}" 0600
}

recover_interrupted_data_plane() {
  local marker_magic marker_backup
  local -a marker_lines=()
  [[ -e "${NODE_DATA_PLANE_TRANSACTION}" || -L "${NODE_DATA_PLANE_TRANSACTION}" ]] \
    || return 0
  [[ -f "${NODE_DATA_PLANE_TRANSACTION}" && ! -L "${NODE_DATA_PLANE_TRANSACTION}" ]] \
    || fail "数据面事务标记不安全，拒绝自动恢复"
  [[ "$(stat -c '%u:%g:%a' "${NODE_DATA_PLANE_TRANSACTION}")" == "0:0:600" ]] \
    || fail "数据面事务标记权限异常，拒绝自动恢复"
  mapfile -t marker_lines < "${NODE_DATA_PLANE_TRANSACTION}"
  [[ ${#marker_lines[@]} -eq 2 ]] \
    || fail "数据面事务标记格式异常，拒绝自动恢复"
  marker_magic="${marker_lines[0]}"
  marker_backup="${marker_lines[1]}"
  [[ "${marker_magic}" == "${DATA_PLANE_TRANSACTION_MAGIC}" ]] \
    || fail "数据面事务标记版本未知，拒绝自动恢复"
  [[ "${marker_backup}" =~ ^${NODE_DATA_PLANE_BACKUP_ROOT}/[0-9]{8}T[0-9]{6}Z-phase4$ ]] \
    || fail "数据面回滚快照路径异常，拒绝自动恢复"
  [[ -d "${marker_backup}" && ! -L "${marker_backup}" ]] \
    || fail "数据面回滚快照缺失或不安全"
  [[ "$(stat -c '%u:%g:%a' "${marker_backup}")" == "0:0:700" ]] \
    || fail "数据面回滚快照权限异常"
  [[ -f "${marker_backup}/node_agent.py" && ! -L "${marker_backup}/node_agent.py" ]] \
    || fail "数据面回滚节点 Agent 缺失"
  [[ -f "${marker_backup}/manifest.sha256" && ! -L "${marker_backup}/manifest.sha256" ]] \
    || fail "数据面回滚 manifest 缺失"
  (
    cd "${marker_backup}"
    sha256sum --check --status manifest.sha256
  ) || fail "数据面回滚快照摘要不匹配"
  DATA_PLANE_BACKUP_DIR="${marker_backup}"
  DATA_PLANE_NODE_AGENT_BACKUP_FILE="${marker_backup}/node_agent.py"
  if [[ -f "${marker_backup}/deployment-kind" \
    && "$(cat "${marker_backup}/deployment-kind")" == "existing" ]]; then
    DATA_PLANE_EXISTING=1
  else
    DATA_PLANE_EXISTING=0
  fi
  DATA_PLANE_MUTATED=1
  rollback_data_plane_activation \
    || fail "中断的数据面部署无法自动恢复；事务标记已保留"
  echo "已恢复中断的数据面部署；第二阶段节点身份和签名心跳保持不变。"
}

record_data_plane_firewall_change() {
  local line="$1" stage="${TMP_DIR}/data-plane-firewall.state"
  [[ "${line}" =~ ^(ufw|firewalld-runtime|firewalld-permanent)\|[-A-Za-z0-9_.]+\|([0-9]{1,5})\|(tcp|udp)$ ]] \
    || return 1
  if [[ -f "${NODE_AGENT_CONFIG_DIR}/data-plane-firewall.state" ]]; then
    cp -- "${NODE_AGENT_CONFIG_DIR}/data-plane-firewall.state" "${stage}"
  else
    : > "${stage}"
  fi
  echo "${line}" >> "${stage}"
  durable_replace_file "${stage}" \
    "${NODE_AGENT_CONFIG_DIR}/data-plane-firewall.state" 0600
}

configure_data_plane_firewall() {
  local active_firewalld=0 active_ufw=0 port protocol query_status rule scope
  local status zone zones
  if command -v firewall-cmd >/dev/null 2>&1; then
    if read_firewalld_state >/dev/null; then
      active_firewalld=1
    else
      status=$?
      (( status == 1 )) || fail "无法查询 firewalld 状态；数据面已安排回滚"
    fi
  fi
  if command -v ufw >/dev/null 2>&1; then
    if read_ufw_state >/dev/null; then
      active_ufw=1
    else
      status=$?
      (( status == 1 )) || fail "无法查询 UFW 状态；数据面已安排回滚"
    fi
  fi
  (( active_firewalld + active_ufw <= 1 )) \
    || fail "检测到多个活动主机防火墙，拒绝猜测数据面规则归属"
  if (( active_firewalld == 1 )); then
    if firewalld_has_global_conflicts; then
      fail "firewalld 存在可能提前阻断入站的全局规则；数据面已安排回滚"
    else
      status=$?
      (( status == 1 )) \
        || fail "无法完整核验 firewalld 全局规则；数据面已安排回滚"
    fi
    zones="$(read_firewalld_zones)" \
      || fail "无法读取 firewalld 活跃或默认区域；数据面已安排回滚"
    [[ -n "${zones}" ]] \
      || fail "firewalld 没有可验证区域；数据面已安排回滚"
    while IFS= read -r zone; do
      [[ "${zone}" =~ ^[A-Za-z0-9_.-]{1,64}$ ]] \
        || fail "firewalld 返回无效区域；数据面已安排回滚"
      for scope in runtime permanent; do
        if firewalld_zone_has_complex_rules "${scope}" "${zone}"; then
          fail "firewalld ${zone} 存在 rich rule；数据面已安排回滚"
        else
          status=$?
          (( status == 1 )) \
            || fail "无法读取 firewalld ${zone} rich rules；数据面已安排回滚"
        fi
        for protocol in tcp udp; do
          for port in 443 "${DATA_PLANE_MAIN_PORT}"; do
            rule="${port}/${protocol}"
            if [[ "${scope}" == "permanent" ]]; then
              if firewall-cmd --quiet --permanent --zone="${zone}" \
                --query-port="${rule}"; then
                continue
              else
                query_status=$?
              fi
            elif firewall-cmd --quiet --zone="${zone}" \
              --query-port="${rule}"; then
              continue
            else
              query_status=$?
            fi
            (( query_status == 1 )) \
              || fail "无法查询 firewalld ${zone} ${scope} 规则；数据面已安排回滚"
            record_data_plane_firewall_change \
              "firewalld-${scope}|${zone}|${port}|${protocol}" \
              || fail "无法持久化 firewalld 回滚归属"
            if [[ "${scope}" == "permanent" ]]; then
              firewall-cmd --quiet --permanent --zone="${zone}" \
                --add-port="${rule}" \
                || fail "无法开放 firewalld ${zone} ${scope} ${rule}"
              firewall-cmd --quiet --permanent --zone="${zone}" \
                --query-port="${rule}" \
                || fail "firewalld ${zone} ${scope} ${rule} 复核失败"
            else
              firewall-cmd --quiet --zone="${zone}" --add-port="${rule}" \
                || fail "无法开放 firewalld ${zone} ${scope} ${rule}"
              firewall-cmd --quiet --zone="${zone}" --query-port="${rule}" \
                || fail "firewalld ${zone} ${scope} ${rule} 复核失败"
            fi
          done
        done
      done
    done <<< "${zones}"
    return 0
  fi
  if (( active_ufw == 1 )); then
    if ufw_has_framework_customization; then
      fail "UFW framework 已自定义；数据面已安排回滚"
    else
      status=$?
      (( status == 1 )) \
        || fail "无法核验 UFW framework；数据面已安排回滚"
    fi
    if ufw_has_unmanaged_live_rules; then
      fail "UFW 之外存在可能阻断入站的实时规则；数据面已安排回滚"
    else
      status=$?
      (( status == 1 )) \
        || fail "无法核验 UFW 实时规则；数据面已安排回滚"
    fi
    UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" \
      || fail "无法读取 UFW 规则；数据面已安排回滚"
    for protocol in tcp udp; do
      for port in 443 "${DATA_PLANE_MAIN_PORT}"; do
        rule="${port}/${protocol}"
        if ufw_rule_is_denied "${rule}"; then
          fail "UFW 已存在拒绝 ${rule} 的规则；数据面已安排回滚"
        else
          status=$?
          (( status == 1 )) \
            || fail "无法解析 UFW ${rule} 规则；数据面已安排回滚"
        fi
        ufw_rule_is_recorded "${rule}" && continue
        record_data_plane_firewall_change "ufw|-|${port}|${protocol}" \
          || fail "无法持久化 UFW 回滚归属"
        ufw allow "${rule}" comment 'Hysteria2-panel-node data-plane' >/dev/null \
          || fail "UFW 无法开放 ${rule}"
        UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" \
          || fail "无法复核 UFW ${rule} 规则"
        ufw_rule_is_recorded "${rule}" \
          || fail "UFW ${rule} 开放后复核失败"
      done
    done
    return 0
  fi
  if has_unmanaged_firewall_restrictions; then
    fail "检测到未受支持的自定义 nftables/iptables 入站策略；数据面已安排回滚"
  else
    status=$?
    (( status == 1 )) \
      || fail "无法完整检查 nftables/iptables；数据面已安排回滚"
  fi
  echo "主机未启用 UFW/firewalld 且无自定义入站限制；数据面未修改防火墙。"
}

validate_data_plane_firewall_state() {
  local manager zone port protocol extra state="$1"
  [[ -e "${state}" || -L "${state}" ]] || return 0
  [[ -f "${state}" && ! -L "${state}" ]] || return 1
  while IFS='|' read -r manager zone port protocol extra; do
    [[ -z "${extra}" && "${port}" =~ ^[0-9]{1,5}$ \
      && "${port}" -ge 1 && "${port}" -le 65535 \
      && "${protocol}" =~ ^(tcp|udp)$ ]] \
      || return 1
    case "${manager}" in
      firewalld-runtime|firewalld-permanent)
        [[ "${zone}" =~ ^[A-Za-z0-9_.-]{1,64}$ ]] || return 1
        ;;
      ufw)
        [[ "${zone}" == "-" ]] || return 1
        ;;
      *) return 1 ;;
    esac
  done < "${state}"
}

remove_data_plane_firewall_rule() {
  local manager="$1" zone="$2" port="$3" protocol="$4" rule status
  rule="${port}/${protocol}"
  case "${manager}" in
    firewalld-runtime)
      if firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
        firewall-cmd --quiet --zone="${zone}" --remove-port="${rule}" \
          || return 1
      else
        status=$?
        (( status == 1 )) && return 0
        return 1
      fi
      if firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
        return 1
      else
        status=$?
        (( status == 1 ))
      fi
      ;;
    firewalld-permanent)
      if firewall-cmd --quiet --permanent --zone="${zone}" \
        --query-port="${rule}"; then
        firewall-cmd --quiet --permanent --zone="${zone}" \
          --remove-port="${rule}" || return 1
      else
        status=$?
        (( status == 1 )) && return 0
        return 1
      fi
      if firewall-cmd --quiet --permanent --zone="${zone}" \
        --query-port="${rule}"; then
        return 1
      else
        status=$?
        (( status == 1 ))
      fi
      ;;
    ufw)
      UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" || return 1
      if ufw_rule_is_recorded "${rule}"; then
        ufw --force delete allow proto "${protocol}" from any to any \
          port "${port}" >/dev/null || return 1
      else
        status=$?
        (( status == 1 )) && return 0
        return 1
      fi
      UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" || return 1
      if ufw_rule_is_recorded "${rule}"; then
        return 1
      else
        status=$?
        (( status == 1 ))
      fi
      ;;
    *) return 1 ;;
  esac
}

rollback_data_plane_firewall() {
  local failed=0 manager zone port protocol
  local state="${NODE_AGENT_CONFIG_DIR}/data-plane-firewall.state"
  validate_data_plane_firewall_state "${state}" || return 1
  [[ -e "${state}" ]] || return 0
  while IFS='|' read -r manager zone port protocol; do
    remove_data_plane_firewall_rule \
      "${manager}" "${zone}" "${port}" "${protocol}" || failed=1
  done < "${state}"
  (( failed == 0 )) || return 1
  rm -f -- "${state}"
}

rollback_new_data_plane_firewall_rules() {
  local backup_state failed=0 manager zone port protocol rule
  local state="${NODE_AGENT_CONFIG_DIR}/data-plane-firewall.state"
  backup_state="${DATA_PLANE_BACKUP_DIR}/config/data-plane-firewall.state"
  validate_data_plane_firewall_state "${state}" || return 1
  validate_data_plane_firewall_state "${backup_state}" || return 1
  [[ -e "${state}" ]] || return 0
  while IFS='|' read -r manager zone port protocol; do
    rule="${manager}|${zone}|${port}|${protocol}"
    if [[ -f "${backup_state}" ]] && grep -Fqx -- "${rule}" "${backup_state}"; then
      continue
    fi
    remove_data_plane_firewall_rule \
      "${manager}" "${zone}" "${port}" "${protocol}" || failed=1
  done < "${state}"
  (( failed == 0 ))
}

stop_existing_data_plane() {
  systemctl stop \
    hysteria2-panel-node-tcp-probe-udp443.service \
    hysteria2-panel-node-tcp-probe-main.service \
    hysteria2-panel-node-hysteria-udp443.service \
    hysteria2-panel-node-hysteria-main.service \
    hysteria2-panel-node-control.service \
    hysteria2-panel-node-auth.service
}

restore_existing_data_plane() {
  local path unit
  initialize_data_plane_owned_paths
  (
    cd "${DATA_PLANE_BACKUP_DIR}"
    sha256sum --check --status manifest.sha256
  ) || return 1
  rollback_new_data_plane_firewall_rules || return 1
  for path in "${DATA_PLANE_OWNED_UNITS[@]}"; do
    unit="${path##*/}"
    systemctl disable --now "${unit}" >/dev/null 2>&1 || true
  done
  install -o root -g root -m 0755 \
    "${DATA_PLANE_BACKUP_DIR}/opt/node_agent.py" \
    "${NODE_AGENT_OPT_DIR}/node_agent.py" || return 1
  install -o root -g root -m 0755 \
    "${DATA_PLANE_BACKUP_DIR}/opt/tcp_probe.py" \
    "${NODE_AGENT_OPT_DIR}/tcp_probe.py" || return 1
  durable_replace_file "${DATA_PLANE_BACKUP_DIR}/opt/hysteria" \
    "${NODE_AGENT_OPT_DIR}/bin/hysteria" 0755 || return 1
  for path in "${DATA_PLANE_OWNED_FILES[@]}"; do
    [[ "${path}" == "${NODE_AGENT_OPT_DIR}/bin/hysteria" \
      || "${path}" == "${NODE_AGENT_OPT_DIR}/tcp_probe.py" ]] && continue
    rm -f -- "${path}" || return 1
    if [[ -f "${DATA_PLANE_BACKUP_DIR}/config/${path##*/}" ]]; then
      install -o root -g root -m 0600 \
        "${DATA_PLANE_BACKUP_DIR}/config/${path##*/}" "${path}" || return 1
    fi
  done
  rm -r -- /var/lib/hysteria2-panel-node || return 1
  cp -a -- "${DATA_PLANE_BACKUP_DIR}/state" \
    /var/lib/hysteria2-panel-node || return 1
  for path in "${DATA_PLANE_OWNED_UNITS[@]}"; do
    install -o root -g root -m 0644 \
      "${DATA_PLANE_BACKUP_DIR}/units/${path##*/}" "${path}" || return 1
  done
  restore_data_plane_network_snapshot || return 1
  systemctl daemon-reload || return 1
  for path in "${DATA_PLANE_OWNED_UNITS[@]}"; do
    unit="${path##*/}"
    systemctl enable --now "${unit}" || return 1
    systemctl is-active --quiet "${unit}" || return 1
  done
  DATA_PLANE_MAIN_PORT="$(read_data_plane_main_port \
    "${NODE_AGENT_CONFIG_DIR}/bootstrap.json" legacy-19999)" || return 1
  wait_for_listener udp "${DATA_PLANE_MAIN_PORT}" || return 1
  wait_for_listener udp 443 || return 1
  wait_for_listener tcp "${DATA_PLANE_MAIN_PORT}" || return 1
  wait_for_listener tcp 443 || return 1
  rm -f -- "${NODE_DATA_PLANE_TRANSACTION}" || return 1
  sync -f "${NODE_AGENT_OPT_DIR}" "${NODE_AGENT_CONFIG_DIR}" \
    /var/lib/hysteria2-panel-node /etc/systemd/system || return 1
  DATA_PLANE_MUTATED=0
}

rollback_data_plane_activation() {
  local path unit
  initialize_data_plane_owned_paths
  if (( DATA_PLANE_EXISTING == 1 )); then
    restore_existing_data_plane
    return $?
  fi
  rollback_data_plane_firewall || return 1
  restore_data_plane_network_snapshot || return 1
  for path in "${DATA_PLANE_OWNED_UNITS[@]}"; do
    unit="${path##*/}"
    systemctl disable --now "${unit}" >/dev/null 2>&1 || true
  done
  if [[ -n "${DATA_PLANE_NODE_AGENT_BACKUP_FILE}" && \
    -f "${DATA_PLANE_NODE_AGENT_BACKUP_FILE}" && \
    ! -L "${DATA_PLANE_NODE_AGENT_BACKUP_FILE}" ]]; then
    install -o root -g root -m 0755 "${DATA_PLANE_NODE_AGENT_BACKUP_FILE}" \
      "${NODE_AGENT_OPT_DIR}/node_agent.py" || return 1
  fi
  for path in "${DATA_PLANE_OWNED_UNITS[@]}" "${DATA_PLANE_OWNED_FILES[@]}"; do
    rm -f -- "${path}" || return 1
  done
  if [[ -e /var/lib/hysteria2-panel-node || -L /var/lib/hysteria2-panel-node ]]; then
    [[ -d /var/lib/hysteria2-panel-node && ! -L /var/lib/hysteria2-panel-node ]] \
      || return 1
    rm -r -- /var/lib/hysteria2-panel-node || return 1
  fi
  if [[ -e "${NODE_AGENT_OPT_DIR}/bin" || -L "${NODE_AGENT_OPT_DIR}/bin" ]]; then
    [[ -d "${NODE_AGENT_OPT_DIR}/bin" && ! -L "${NODE_AGENT_OPT_DIR}/bin" ]] \
      || return 1
    rmdir -- "${NODE_AGENT_OPT_DIR}/bin" || return 1
  fi
  rm -f -- "${NODE_DATA_PLANE_TRANSACTION}" || return 1
  systemctl daemon-reload || return 1
  sync -f "${NODE_AGENT_OPT_DIR}" "${NODE_AGENT_CONFIG_DIR}" \
    /etc/systemd/system || return 1
  DATA_PLANE_MUTATED=0
}

activate_data_plane() {
  local bootstrap_token command_name existing_main_port="" hysteria_arch hysteria_sha hysteria_url main_capability="" path unit
  local -a data_plane_commands=(awk cat chmod cp curl date df find grep install mkdir mktemp mv openssl rm rmdir sha256sum sort ss stat sync sysctl systemctl)

  [[ "${PANEL_REF}" == "v${PANEL_VERSION}" ]] \
    || fail "数据面只允许使用当前受签名正式版本 v${PANEL_VERSION}"
  [[ -d /run/systemd/system ]] \
    || fail "数据面部署需要使用 systemd 的 Linux 服务器"
  [[ ! -e "${MANAGED_MARKER}" && ! -L "${MANAGED_MARKER}" ]] \
    || fail "完整面板服务器不能启用分流数据面"
  require_node_agent_directory "${NODE_AGENT_OPT_DIR}" 755
  require_node_agent_directory "${NODE_AGENT_CONFIG_DIR}" 700
  require_node_agent_file "${NODE_AGENT_OPT_DIR}/node_agent.py" 755
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/node.key" 600
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/node-public.der" 644
  require_node_agent_file "${NODE_AGENT_CONFIG_DIR}/registration.json" 600
  require_node_agent_file "${NODE_AGENT_HEARTBEAT_SERVICE}" 644
  require_node_agent_file "${NODE_AGENT_HEARTBEAT_TIMER}" 644
  systemctl is-active --quiet hysteria2-panel-node-heartbeat.timer \
    || fail "节点签名心跳 timer 未运行；未修改系统"
  systemctl start hysteria2-panel-node-heartbeat.service \
    || fail "节点签名心跳未被中央面板接受；未修改系统"
  for command_name in "${data_plane_commands[@]}"; do
    command -v "${command_name}" >/dev/null 2>&1 \
      || fail "数据面部署缺少命令 ${command_name}；未修改系统"
  done
  select_python || fail "数据面部署需要 Python 3.8 或更高版本；未修改系统"
  recover_interrupted_data_plane
  assert_data_plane_network_stack_claimable
  inspect_existing_data_plane
  if (( DATA_PLANE_EXISTING == 1 )); then
    assert_existing_data_plane_healthy
    existing_main_port="${DATA_PLANE_MAIN_PORT}"
  else
    assert_data_plane_paths_unclaimed
  fi
  (( $(df -Pk "${NODE_AGENT_OPT_DIR}" | awk 'NR == 2 {print $4}') >= 131072 )) \
    || fail "数据面部署至少需要 128 MiB 可用磁盘；未修改系统"
  bootstrap_token="${HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN:-}"
  unset HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN
  [[ "${bootstrap_token}" =~ ^[A-Za-z0-9_-]{32,128}$ ]] \
    || fail "缺少或无效的一次性数据面部署凭据"
  case "$(uname -m)" in
    x86_64|amd64)
      hysteria_arch=amd64
      hysteria_sha="${HYSTERIA_SHA_AMD64}"
      ;;
    aarch64|arm64)
      hysteria_arch=arm64
      hysteria_sha="${HYSTERIA_SHA_ARM64}"
      ;;
    *) fail "数据面仅支持 Linux amd64 和 arm64" ;;
  esac
  hysteria_url="${HYSTERIA_DATA_PLANE_URL}-${hysteria_arch}"

  TMP_DIR="$(TMPDIR=/tmp mktemp -d -t hysteria2-panel.XXXXXXXX)"
  download_file "${NODE_AGENT_SOURCE_URL}" "${TMP_DIR}/node_agent.py"
  download_file "${TCP_PROBE_SOURCE_URL}" "${TMP_DIR}/tcp_probe.py"
  download_file "${hysteria_url}" "${TMP_DIR}/hysteria"
  printf '%s  %s\n' "${NODE_AGENT_SHA256}" "${TMP_DIR}/node_agent.py" \
    | sha256sum --check --status || fail "节点 Agent SHA-256 校验失败"
  printf '%s  %s\n' "${TCP_PROBE_SHA256}" "${TMP_DIR}/tcp_probe.py" \
    | sha256sum --check --status || fail "TCP probe SHA-256 校验失败"
  printf '%s  %s\n' "${hysteria_sha}" "${TMP_DIR}/hysteria" \
    | sha256sum --check --status || fail "Hysteria SHA-256 校验失败"
  "${PYTHON_BIN}" -m py_compile "${TMP_DIR}/node_agent.py" "${TMP_DIR}/tcp_probe.py" \
    || fail "数据节点 Python 构件语法检查失败"
  chmod 0755 "${TMP_DIR}/hysteria"
  HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN="${bootstrap_token}" \
    "${PYTHON_BIN}" "${TMP_DIR}/node_agent.py" prepare-data-plane \
      --private-key "${NODE_AGENT_CONFIG_DIR}/node.key" \
      --state-file "${NODE_AGENT_CONFIG_DIR}/registration.json" \
      --output-dir "${TMP_DIR}/data-plane" \
    || fail "数据面身份取件或本地摘要验证失败；未修改系统"
  DATA_PLANE_MAIN_PORT="$(read_data_plane_main_port \
    "${TMP_DIR}/data-plane/bootstrap.json")" \
    || fail "中央返回的数据面主端口无效；未修改系统"
  if (( DATA_PLANE_EXISTING == 0 )); then
    assert_data_plane_ports_available
  elif [[ "${DATA_PLANE_MAIN_PORT}" != "${existing_main_port}" ]]; then
    assert_data_plane_main_port_available
  fi
  if (( DATA_PLANE_MAIN_PORT < 1024 )); then
    main_capability=CAP_NET_BIND_SERVICE
  fi

  write_data_plane_backup_manifest \
    || fail "无法创建数据面 root-only 回滚快照；未修改系统"
  arm_data_plane_transaction \
    || fail "无法持久化数据面回滚事务；未修改系统"
  DATA_PLANE_MUTATED=1
  optimize_data_plane_network_stack \
    || fail "数据节点无法完成 fq/BBR 和 16 MiB UDP 缓冲优化；已安排恢复"
  if (( DATA_PLANE_EXISTING == 1 )); then
    stop_existing_data_plane \
      || fail "无法停止既有数据面服务；已安排恢复旧数据面"
  fi
  install -d -o root -g root -m 0755 "${NODE_AGENT_OPT_DIR}/bin"
  install -d -o root -g root -m 0700 \
    /var/lib/hysteria2-panel-node \
    /var/lib/hysteria2-panel-node/spool \
    /var/lib/hysteria2-panel-node/state
  install -o root -g root -m 0755 "${TMP_DIR}/node_agent.py" \
    "${NODE_AGENT_OPT_DIR}/node_agent.py"
  install -o root -g root -m 0755 "${TMP_DIR}/tcp_probe.py" \
    "${NODE_AGENT_OPT_DIR}/tcp_probe.py"
  durable_replace_file "${TMP_DIR}/hysteria" \
    "${NODE_AGENT_OPT_DIR}/bin/hysteria" 0755
  for path in server.crt server.key hysteria-main.yaml hysteria-udp443.yaml stats.env bootstrap.json; do
    install -o root -g root -m 0600 "${TMP_DIR}/data-plane/${path}" \
      "${NODE_AGENT_CONFIG_DIR}/${path}"
  done

  cat > "${TMP_DIR}/hysteria2-panel-node-auth.service" <<EOF
[Unit]
Description=Hysteria2-panel loopback node authentication proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
NotifyAccess=main
WatchdogSec=30s
User=root
Group=root
ExecStart=${PYTHON_BIN} ${NODE_AGENT_OPT_DIR}/node_agent.py serve-auth-proxy --private-key ${NODE_AGENT_CONFIG_DIR}/node.key --state-file ${NODE_AGENT_CONFIG_DIR}/registration.json --port 19996 --metrics-file /var/lib/hysteria2-panel-node/state/node.prom
Restart=always
RestartSec=2s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadOnlyPaths=${NODE_AGENT_OPT_DIR} ${NODE_AGENT_CONFIG_DIR}
TasksMax=64
MemoryMax=192M
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
EOF

  cat > "${TMP_DIR}/hysteria2-panel-node-control.service" <<EOF
[Unit]
Description=Hysteria2-panel signed data-node control loop
After=network-online.target hysteria2-panel-node-auth.service
Wants=network-online.target

[Service]
Type=notify
NotifyAccess=main
WatchdogSec=90s
User=root
Group=root
EnvironmentFile=${NODE_AGENT_CONFIG_DIR}/stats.env
ExecStart=${PYTHON_BIN} ${NODE_AGENT_OPT_DIR}/node_agent.py control-loop --private-key ${NODE_AGENT_CONFIG_DIR}/node.key --state-file ${NODE_AGENT_CONFIG_DIR}/registration.json --protocol-state /var/lib/hysteria2-panel-node/state/protocol.json --spool-dir /var/lib/hysteria2-panel-node/spool --stats-url http://127.0.0.1:19997 --stats-url http://127.0.0.1:19995 --metrics-file /var/lib/hysteria2-panel-node/state/node.prom
Restart=always
RestartSec=2s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadOnlyPaths=${NODE_AGENT_OPT_DIR} ${NODE_AGENT_CONFIG_DIR}
ReadWritePaths=/var/lib/hysteria2-panel-node
TasksMax=64
MemoryMax=256M
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
EOF

  cat > "${TMP_DIR}/hysteria2-panel-node-hysteria-main.service" <<EOF
[Unit]
Description=Hysteria2-panel data node main UDP ${DATA_PLANE_MAIN_PORT}
After=network-online.target hysteria2-panel-node-auth.service hysteria2-panel-node-control.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
EnvironmentFile=${NODE_AGENT_CONFIG_DIR}/stats.env
Environment=HYSTERIA_DISABLE_UPDATE_CHECK=1
RuntimeDirectory=hysteria2-panel-node-main
RuntimeDirectoryMode=0700
ExecStart=${PYTHON_BIN} ${NODE_AGENT_OPT_DIR}/node_agent.py run-hysteria --template ${NODE_AGENT_CONFIG_DIR}/hysteria-main.yaml --runtime-config /run/hysteria2-panel-node-main/config.yaml
Restart=on-failure
RestartSec=3s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=${main_capability}
AmbientCapabilities=${main_capability}
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadOnlyPaths=${NODE_AGENT_OPT_DIR} ${NODE_AGENT_CONFIG_DIR}
TasksMax=256
MemoryMax=768M
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

  cat > "${TMP_DIR}/hysteria2-panel-node-hysteria-udp443.service" <<EOF
[Unit]
Description=Hysteria2-panel data node authorized UDP 443
After=network-online.target hysteria2-panel-node-auth.service hysteria2-panel-node-control.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
EnvironmentFile=${NODE_AGENT_CONFIG_DIR}/stats.env
Environment=HYSTERIA_DISABLE_UPDATE_CHECK=1
RuntimeDirectory=hysteria2-panel-node-udp443
RuntimeDirectoryMode=0700
ExecStart=${PYTHON_BIN} ${NODE_AGENT_OPT_DIR}/node_agent.py run-hysteria --template ${NODE_AGENT_CONFIG_DIR}/hysteria-udp443.yaml --runtime-config /run/hysteria2-panel-node-udp443/config.yaml
Restart=on-failure
RestartSec=3s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadOnlyPaths=${NODE_AGENT_OPT_DIR} ${NODE_AGENT_CONFIG_DIR}
TasksMax=256
MemoryMax=768M
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

  cat > "${TMP_DIR}/hysteria2-panel-node-tcp-probe-main.service" <<EOF
[Unit]
Description=Hysteria2-panel data node TCP ${DATA_PLANE_MAIN_PORT} probe
After=hysteria2-panel-node-hysteria-main.service
Requires=hysteria2-panel-node-hysteria-main.service

[Service]
Type=simple
DynamicUser=true
ExecStart=${PYTHON_BIN} ${NODE_AGENT_OPT_DIR}/tcp_probe.py ${DATA_PLANE_MAIN_PORT}
Restart=on-failure
RestartSec=3s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=${main_capability}
AmbientCapabilities=${main_capability}
RestrictAddressFamilies=AF_INET AF_INET6
TasksMax=16
MemoryMax=64M
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
EOF

  cat > "${TMP_DIR}/hysteria2-panel-node-tcp-probe-udp443.service" <<EOF
[Unit]
Description=Hysteria2-panel data node TCP 443 probe
After=hysteria2-panel-node-hysteria-udp443.service
Requires=hysteria2-panel-node-hysteria-udp443.service

[Service]
Type=simple
DynamicUser=true
ExecStart=${PYTHON_BIN} ${NODE_AGENT_OPT_DIR}/tcp_probe.py 443
Restart=on-failure
RestartSec=3s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
RestrictAddressFamilies=AF_INET AF_INET6
TasksMax=16
MemoryMax=64M
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
EOF

  for path in "${DATA_PLANE_OWNED_UNITS[@]}"; do
    install -o root -g root -m 0644 "${TMP_DIR}/${path##*/}" "${path}"
  done
  systemctl daemon-reload
  systemctl enable --now hysteria2-panel-node-auth.service
  systemctl enable --now hysteria2-panel-node-control.service
  systemctl enable --now hysteria2-panel-node-hysteria-main.service
  systemctl enable --now hysteria2-panel-node-hysteria-udp443.service
  systemctl enable --now hysteria2-panel-node-tcp-probe-main.service
  systemctl enable --now hysteria2-panel-node-tcp-probe-udp443.service
  for path in "${DATA_PLANE_OWNED_UNITS[@]}"; do
    unit="${path##*/}"
    systemctl is-active --quiet "${unit}" || fail "数据面服务未能健康启动：${unit}"
  done
  systemctl is-active --quiet hysteria2-panel-node-control.service \
    || fail "数据面控制循环未运行"
  wait_for_listener udp "${DATA_PLANE_MAIN_PORT}" \
    || fail "Hysteria UDP ${DATA_PLANE_MAIN_PORT} 未监听"
  wait_for_listener udp 443 || fail "Hysteria UDP 443 未监听"
  wait_for_listener tcp "${DATA_PLANE_MAIN_PORT}" \
    || fail "TCP ${DATA_PLANE_MAIN_PORT} probe 未监听"
  wait_for_listener tcp 443 || fail "TCP 443 probe 未监听"
  configure_data_plane_firewall
  (
    set -a
    # shellcheck disable=SC1090,SC1091
    source "${NODE_AGENT_CONFIG_DIR}/stats.env"
    set +a
    HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN="${bootstrap_token}" \
      "${PYTHON_BIN}" "${NODE_AGENT_OPT_DIR}/node_agent.py" ack-data-plane \
        --private-key "${NODE_AGENT_CONFIG_DIR}/node.key" \
        --state-file "${NODE_AGENT_CONFIG_DIR}/registration.json" \
        --metadata "${NODE_AGENT_CONFIG_DIR}/bootstrap.json" \
        --certificate "${NODE_AGENT_CONFIG_DIR}/server.crt" \
        --hysteria-key "${NODE_AGENT_CONFIG_DIR}/server.key"
  ) || fail "数据面本地健康证明或中央 ACK 失败"
  bootstrap_token=""
  rm -f -- "${NODE_DATA_PLANE_TRANSACTION}"
  sync -f "${NODE_AGENT_OPT_DIR}" "${NODE_AGENT_CONFIG_DIR}" \
    /var/lib/hysteria2-panel-node /etc/systemd/system
  DATA_PLANE_MUTATED=0
  if (( DATA_PLANE_EXISTING == 1 )); then
    echo "数据面升级完成；节点身份、统计队列和 DNS 准入状态保持不变。"
  else
    echo "数据面部署完成；未安装管理面板、未修改 DNS，Hysteria 身份来自中央生产身份的逐字节副本。"
  fi
}

install_system_dependencies() {
  local command_name
  local -a coreutils_commands=(cat chmod chown cp date df du id install mktemp mv rm sha256sum sleep sort stat sync uname)
  local -a rhel_packages

  [[ -r /etc/os-release ]] || fail "无法识别 Linux 发行版：缺少 /etc/os-release"
  # shellcheck disable=SC1091
  source /etc/os-release
  echo "检测到系统：${PRETTY_NAME:-${ID:-unknown}}，正在安装缺失依赖"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      ca-certificates curl openssl iproute2 python3 coreutils diffutils findutils gawk grep passwd procps sudo util-linux \
      nftables iptables
  elif command -v dnf >/dev/null 2>&1; then
    rhel_packages=(ca-certificates openssl iproute python3 diffutils findutils gawk grep shadow-utils procps-ng sed sudo util-linux)
    command -v curl >/dev/null 2>&1 || rhel_packages+=(curl)
    for command_name in "${coreutils_commands[@]}"; do
      command -v "${command_name}" >/dev/null 2>&1 || { rhel_packages+=(coreutils); break; }
    done
    dnf install -y "${rhel_packages[@]}"
    dnf install -y nftables iptables-nft || dnf install -y nftables iptables
  elif command -v yum >/dev/null 2>&1; then
    rhel_packages=(ca-certificates openssl iproute python3 diffutils findutils gawk grep shadow-utils procps-ng sed sudo util-linux)
    command -v curl >/dev/null 2>&1 || rhel_packages+=(curl)
    for command_name in "${coreutils_commands[@]}"; do
      command -v "${command_name}" >/dev/null 2>&1 || { rhel_packages+=(coreutils); break; }
    done
    yum install -y "${rhel_packages[@]}"
    yum install -y nftables iptables-nft || yum install -y nftables iptables
  else
    fail "当前系统没有受支持的包管理器（需要 apt、dnf 或 yum）"
  fi

  if ! select_python; then
    if command -v dnf >/dev/null 2>&1; then
      dnf install -y python39 || true
    elif command -v yum >/dev/null 2>&1; then
      yum install -y python39 || true
    fi
  fi
}

install_certbot_dependency() {
  [[ -x /usr/bin/certbot ]] && return 0
  echo "HTTPS 模式需要 Certbot，正在从系统软件源安装"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y certbot
  elif command -v dnf >/dev/null 2>&1; then
    if ! dnf install -y certbot; then
      echo "当前 RHEL 系仓库未提供 Certbot，正在通过包管理器启用 EPEL"
      dnf install -y epel-release
      dnf install -y certbot
    fi
  elif command -v yum >/dev/null 2>&1; then
    if ! yum install -y certbot; then
      echo "当前 RHEL 系仓库未提供 Certbot，正在通过包管理器启用 EPEL"
      yum install -y epel-release
      yum install -y certbot
    fi
  else
    fail "无法安装 Certbot：当前系统没有受支持的包管理器"
  fi
  [[ -x /usr/bin/certbot ]] \
    || fail "系统软件源未提供 /usr/bin/certbot；未执行任何远程 ACME 安装脚本"
}

validate_panel_public_host() {
  local hostname="$1" label
  local -a labels
  [[ -n "${hostname}" && ${#hostname} -le 253 && "${hostname}" == *.* ]] \
    || return 1
  [[ "${hostname}" =~ ^[a-z0-9.-]+$ && "${hostname}" != *..* ]] || return 1
  IFS='.' read -r -a labels <<< "${hostname}"
  for label in "${labels[@]}"; do
    [[ "${label}" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] || return 1
  done
}

preflight_panel_acme_dns() {
  "${PYTHON_BIN}" - "${PANEL_PUBLIC_HOST}" <<'PY' \
    || fail "面板域名 DNS 尚未解析到公网地址；未调用 Certbot，也不会自动降级为 HTTP"
import ipaddress
import socket
import sys

hostname = sys.argv[1]
try:
    records = socket.getaddrinfo(hostname, 80, type=socket.SOCK_STREAM)
except OSError:
    raise SystemExit(1)
addresses = {record[4][0].split("%", 1)[0] for record in records}
if not any(ipaddress.ip_address(address).is_global for address in addresses):
    raise SystemExit(1)
PY
}

issue_panel_acme_certificate() {
  preflight_panel_acme_dns
  install -d -o root -g root -m 0700 \
    "${ACME_CONFIG_DIR}" "${ACME_WORK_DIR}" "${ACME_LOGS_DIR}"
  /usr/bin/certbot certonly \
    --config-dir "${ACME_CONFIG_DIR}" \
    --work-dir "${ACME_WORK_DIR}" \
    --logs-dir "${ACME_LOGS_DIR}" \
    --standalone \
    --preferred-challenges http-01 \
    --cert-name "${PANEL_PUBLIC_HOST}" \
    -d "${PANEL_PUBLIC_HOST}" \
    --non-interactive \
    --agree-tos \
    --register-unsafely-without-email \
    --keep-until-expiring \
    || fail "Let’s Encrypt 证书签发失败；请核对 DNS、公网 TCP 80 和签发频率限制"
}

secure_acme_runtime_directories() {
  local directory
  for directory in "${ACME_WORK_DIR}" "${ACME_LOGS_DIR}"; do
    [[ ! -L "${directory}" && -d "${directory}" ]] || return 1
    chown -R root:root "${directory}" || return 1
    find "${directory}" -type d -exec chmod 0700 {} + || return 1
    find "${directory}" -type f -exec chmod 0600 {} + || return 1
  done
}

acquire_maintenance_lock() {
  local hy2panel_gid="" lock_metadata lock_status runtime_metadata
  if id -u hy2panel >/dev/null 2>&1; then
    hy2panel_gid="$(id -g hy2panel)" || fail "无法核验面板维护锁组；安装已停止"
  fi
  if [[ -L "${MAINTENANCE_RUNTIME_DIR}" ]]; then
    fail "维护锁目录不能是符号链接；安装已停止"
  fi
  if [[ -e "${MAINTENANCE_RUNTIME_DIR}" ]]; then
    [[ -d "${MAINTENANCE_RUNTIME_DIR}" ]] || fail "维护锁路径不是目录；安装已停止"
    runtime_metadata="$(stat -c '%u:%g:%a' "${MAINTENANCE_RUNTIME_DIR}")" \
      || fail "无法核验维护锁目录；安装已停止"
    [[ "${runtime_metadata}" == "0:0:700" || "${runtime_metadata}" == "0:${hy2panel_gid}:750" ]] \
      || fail "维护锁目录的所有者或权限无效；安装已停止"
  else
    install -d -o root -g root -m 0700 "${MAINTENANCE_RUNTIME_DIR}"
  fi
  [[ ! -L "${MAINTENANCE_LOCK_FILE}" ]] || fail "维护锁文件不能是符号链接；安装已停止"
  if [[ -e "${MAINTENANCE_LOCK_FILE}" ]]; then
    [[ -f "${MAINTENANCE_LOCK_FILE}" ]] || fail "维护锁路径不是普通文件；安装已停止"
    lock_metadata="$(stat -c '%u:%g:%a' "${MAINTENANCE_LOCK_FILE}")" \
      || fail "无法核验维护锁文件；安装已停止"
    [[ "${lock_metadata}" == "0:0:600" || "${lock_metadata}" == "0:${hy2panel_gid}:640" ]] \
      || fail "维护锁文件的所有者或权限无效；安装已停止"
  else
    install -o root -g root -m 0600 /dev/null "${MAINTENANCE_LOCK_FILE}"
  fi
  if (( MAINTENANCE_LOCK_HELD == 1 )); then
    return 0
  fi
  # Let flock supervise the installer and close its lock descriptor in the
  # child.  A SIGKILL can then never strand the lock in an inherited process.
  if flock -n -E 75 --close "${MAINTENANCE_LOCK_FILE}" \
    /bin/bash "$0" --maintenance-lock-held "${ORIGINAL_ARGS[@]}"; then
    lock_status=0
  else
    lock_status=$?
  fi
  if (( lock_status == 75 && (RECOVER_UPGRADE == 1 || RECOVER_FRESH == 1) )); then
    echo "安装事务仍由安装器持锁；恢复服务本次安全跳过。"
    exit 0
  fi
  if (( lock_status == 75 )); then
    fail "另一个安装、更新或恢复任务正在运行；本次操作未执行"
  fi
  exit "${lock_status}"
}

reset_maintenance_lock_permissions() {
  [[ ! -L "${MAINTENANCE_RUNTIME_DIR}" && -d "${MAINTENANCE_RUNTIME_DIR}" ]] || return 1
  [[ ! -L "${MAINTENANCE_LOCK_FILE}" && -f "${MAINTENANCE_LOCK_FILE}" ]] || return 1
  chown root:root "${MAINTENANCE_RUNTIME_DIR}" "${MAINTENANCE_LOCK_FILE}" || return 1
  chmod 0700 "${MAINTENANCE_RUNTIME_DIR}" || return 1
  chmod 0600 "${MAINTENANCE_LOCK_FILE}" || return 1
}

assert_no_pending_restore_state() {
  if [[ -e "${RESTORE_ACTIVE_MARKER}" || -L "${RESTORE_ACTIVE_MARKER}" ]]; then
    if [[ -f /etc/systemd/system/hysteria2-panel-restore-recover.service ]]; then
      fail "检测到未完成的恢复事务；请先运行 systemctl start hysteria2-panel-restore-recover.service 和 hysteria2-panel-restore-resume.service，确认恢复完成后再部署"
    fi
    fail "检测到旧版或不完整的恢复事务；请先用现有恢复服务或备份完成人工恢复，再重新部署"
  fi
  if [[ -e "${RESTORE_CAPTURED_ARCHIVE}" || -L "${RESTORE_CAPTURED_ARCHIVE}" ]]; then
    if [[ -f /etc/systemd/system/hysteria2-panel-restore-recover.service ]]; then
      fail "检测到待收口的恢复归档；请先运行 systemctl start hysteria2-panel-restore-recover.service，确认归档已隔离后再部署"
    fi
    fail "检测到旧版无法自动收口的恢复归档；请先人工隔离该归档并确认节点身份完整，再重新部署"
  fi
  if [[ -e "${RESTORE_PENDING_ARCHIVE}" || -L "${RESTORE_PENDING_ARCHIVE}" ]]; then
    fail "检测到待执行的恢复归档；请先运行 systemctl start hysteria2-panel-restore.service，确认恢复完成后再部署"
  fi
}

assert_no_pending_egress_state() {
  if [[ -e "${EGRESS_TRANSACTION_MARKER}" || -L "${EGRESS_TRANSACTION_MARKER}" ]]; then
    fail "检测到未完成的出站策略事务；请先重启服务器触发 hysteria2-panel-egress-recover.service，确认面板恢复后再部署"
  fi
}

assert_no_pending_upgrade_state() {
  if [[ -e "${UPGRADE_ACTIVE_MARKER}" || -L "${UPGRADE_ACTIVE_MARKER}" ]]; then
    fail "检测到未完成的升级事务；请先运行 systemctl start hysteria2-panel-upgrade-recover.service，确认旧版本恢复后再部署"
  fi
}

assert_no_unmanaged_install_paths() {
  local path
  [[ -e "${MANAGED_MARKER}" || -L "${MANAGED_MARKER}" ]] && return 0
  [[ -e "${FRESH_IN_PROGRESS_MARKER}" || -L "${FRESH_IN_PROGRESS_MARKER}" ]] && return 0
  [[ -e "${LEGACY_FRESH_IN_PROGRESS_MARKER}" || -L "${LEGACY_FRESH_IN_PROGRESS_MARKER}" ]] && return 0
  for path in \
    /opt/hysteria2-panel \
    /etc/hysteria2-panel \
    /var/lib/hysteria2-panel \
    /var/backups/hysteria2-panel \
    /etc/sudoers.d/hysteria2-panel \
    "${SYSCTL_FILE}" \
    "${TMPFILES_FILE}" \
    /etc/systemd/system/hysteria2-panel.service \
    /etc/systemd/system/hysteria2-panel-server.service \
    /etc/systemd/system/hysteria2-panel-server-443.service \
    /etc/systemd/system/hysteria2-panel-tcp-probe.service \
    /etc/systemd/system/hysteria2-panel-tcp-probe-443.service \
    /etc/systemd/system/hysteria2-panel-restore.service \
    /etc/systemd/system/hysteria2-panel-restore-recover.service \
    /etc/systemd/system/hysteria2-panel-restore-resume.service \
    /etc/systemd/system/hysteria2-panel-egress-full.service \
    /etc/systemd/system/hysteria2-panel-egress-web.service \
    /etc/systemd/system/hysteria2-panel-egress-recover.service \
    /etc/systemd/system/hysteria2-panel-update.service \
    /etc/systemd/system/hysteria2-panel-cert-renew.service \
    /etc/systemd/system/hysteria2-panel-cert-renew.timer \
    /etc/systemd/system/hysteria2-panel-node-dns-admission.service \
    /etc/systemd/system/hysteria2-panel-node-dns-admission.timer \
    /etc/systemd/system/hysteria2-panel-offsite-backup.service \
    /etc/systemd/system/hysteria2-panel-offsite-backup.timer \
    "${FRESH_RECOVERY_UNIT}" \
    "${UPGRADE_RECOVERY_UNIT}" \
    "${UPGRADE_RECOVERY_DROPIN_DIR}" \
    /etc/systemd/system/hysteria2-panel-server.service.d \
    /etc/systemd/system/hysteria2-panel-server-443.service.d \
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-upgrade-recover.service \
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-restore-resume.service \
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel.service \
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-server.service \
    /etc/systemd/system/timers.target.wants/hysteria2-panel-cert-renew.timer \
    /etc/systemd/system/timers.target.wants/hysteria2-panel-node-dns-admission.timer \
    /etc/systemd/system/timers.target.wants/hysteria2-panel-offsite-backup.timer; do
    [[ ! -e "${path}" && ! -L "${path}" ]] \
      || fail "发现非本安装器管理的同名路径或服务：${path}；为避免覆盖，安装已停止"
  done
}

legacy_restore_unit_is_quiescent() {
  local active_state jobs
  active_state="$(systemctl show --no-pager --property=ActiveState --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 2
  case "${active_state}" in inactive|failed) ;; *) return 1 ;; esac
  jobs="$(LC_ALL=C systemctl list-jobs --no-legend --no-pager 2>/dev/null)" || return 2
  if printf '%s\n' "${jobs}" | awk -v unit="${LEGACY_RESTORE_UNIT}" \
    '$2 == unit { found = 1 } END { exit(found ? 0 : 1) }'; then
    return 1
  fi
  active_state="$(systemctl show --no-pager --property=ActiveState --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 2
  case "${active_state}" in inactive|failed) return 0 ;; *) return 1 ;; esac
}

legacy_restore_guard_dir_is_empty() (
  local entries
  shopt -s dotglob nullglob
  entries=("${LEGACY_RESTORE_GUARD_DIR}"/*)
  (( ${#entries[@]} == 0 ))
)

legacy_restore_guard_dir_contains_only_dropin() (
  local entries
  shopt -s dotglob nullglob
  entries=("${LEGACY_RESTORE_GUARD_DIR}"/*)
  (( ${#entries[@]} == 1 )) && \
    [[ "${entries[0]}" == "${LEGACY_RESTORE_GUARD_DROPIN}" ]]
)

guard_legacy_restore_admission() {
  local dropin_paths fragment_metadata fragment_path guard_contents guard_dir_metadata
  local guard_metadata guard_status load_state marker_metadata refuse_manual_start
  [[ -e "${MANAGED_MARKER}" ]] || return 0
  [[ ! -L "${MANAGED_MARKER}" && -f "${MANAGED_MARKER}" && ! -s "${MANAGED_MARKER}" ]] \
    || return 2
  marker_metadata="$(stat -c '%u:%g:%a:%h' "${MANAGED_MARKER}")" || return 2
  [[ "${marker_metadata}" == "0:0:644:1" ]] || return 2
  [[ ! -L "${LEGACY_RESTORE_FRAGMENT}" && -f "${LEGACY_RESTORE_FRAGMENT}" ]] \
    || return 2
  fragment_metadata="$(stat -c '%u:%g:%a:%h' "${LEGACY_RESTORE_FRAGMENT}")" || return 2
  case "${fragment_metadata}" in 0:0:600:1|0:0:644:1) ;; *) return 2 ;; esac
  load_state="$(systemctl show --no-pager --property=LoadState --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 2
  fragment_path="$(systemctl show --no-pager --property=FragmentPath --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 2
  dropin_paths="$(systemctl show --no-pager --property=DropInPaths --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 2
  refuse_manual_start="$(systemctl show --no-pager --property=RefuseManualStart --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 2
  [[ "${load_state}" == "loaded" && \
    "${fragment_path}" == "${LEGACY_RESTORE_FRAGMENT}" ]] || return 2
  if [[ -z "${dropin_paths}" && "${refuse_manual_start}" == "no" ]]; then
    :
  elif [[ "${dropin_paths}" == "${LEGACY_RESTORE_GUARD_DROPIN}" && \
    "${refuse_manual_start}" == "yes" ]]; then
    :
  else
    return 2
  fi
  legacy_restore_unit_is_quiescent || return $?

  if [[ -L "${LEGACY_RESTORE_GUARD_DIR}" ]]; then
    return 2
  elif [[ ! -e "${LEGACY_RESTORE_GUARD_DIR}" ]]; then
    mkdir -m 0755 -- "${LEGACY_RESTORE_GUARD_DIR}" || return 2
  elif [[ ! -d "${LEGACY_RESTORE_GUARD_DIR}" ]]; then
    return 2
  fi
  guard_dir_metadata="$(stat -c '%u:%g:%a:%h' "${LEGACY_RESTORE_GUARD_DIR}")" || return 2
  [[ "${guard_dir_metadata}" == "0:0:755:2" ]] || return 2

  if [[ -e "${LEGACY_RESTORE_GUARD_DROPIN}" || -L "${LEGACY_RESTORE_GUARD_DROPIN}" ]]; then
    [[ ! -L "${LEGACY_RESTORE_GUARD_DROPIN}" && \
      -f "${LEGACY_RESTORE_GUARD_DROPIN}" ]] || return 2
    guard_metadata="$(stat -c '%u:%g:%a:%h' "${LEGACY_RESTORE_GUARD_DROPIN}")" || return 2
    guard_contents="$(<"${LEGACY_RESTORE_GUARD_DROPIN}")" || return 2
    [[ "${guard_metadata}" == "0:0:644:1" && \
      "${guard_contents}" == $'[Unit]\nRefuseManualStart=yes' ]] || return 2
    legacy_restore_guard_dir_contains_only_dropin || return 2
  else
    legacy_restore_guard_dir_is_empty || return 2
    if ! (
      umask 0022
      set -o noclobber
      printf '[Unit]\nRefuseManualStart=yes\n' >"${LEGACY_RESTORE_GUARD_DROPIN}"
    ); then
      rmdir -- "${LEGACY_RESTORE_GUARD_DIR}" >/dev/null 2>&1 || true
      return 2
    fi
    guard_metadata="$(stat -c '%u:%g:%a:%h' "${LEGACY_RESTORE_GUARD_DROPIN}")" \
      || guard_metadata=""
    [[ "${guard_metadata}" == "0:0:644:1" ]] || return 2
  fi
  LEGACY_RESTORE_GUARD_OWNED=1
  if ! systemctl daemon-reload >/dev/null 2>&1; then
    release_legacy_restore_guard >/dev/null 2>&1 || true
    return 2
  fi
  load_state="$(systemctl show --no-pager --property=LoadState --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || load_state=""
  fragment_path="$(systemctl show --no-pager --property=FragmentPath --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || fragment_path=""
  dropin_paths="$(systemctl show --no-pager --property=DropInPaths --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || dropin_paths=""
  refuse_manual_start="$(systemctl show --no-pager --property=RefuseManualStart --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || refuse_manual_start=""
  if [[ "${load_state}" != "loaded" || \
    "${fragment_path}" != "${LEGACY_RESTORE_FRAGMENT}" || \
    "${dropin_paths}" != "${LEGACY_RESTORE_GUARD_DROPIN}" || \
    "${refuse_manual_start}" != "yes" ]]; then
    release_legacy_restore_guard >/dev/null 2>&1 || true
    return 2
  fi
  if systemctl start "${LEGACY_RESTORE_UNIT}" >/dev/null 2>&1; then
    release_legacy_restore_guard >/dev/null 2>&1 || true
    return 2
  fi
  if legacy_restore_unit_is_quiescent; then
    return 0
  else
    guard_status=$?
  fi
  release_legacy_restore_guard >/dev/null 2>&1 || true
  return "${guard_status}"
}

release_legacy_restore_guard() {
  local cleanup_status=0 dropin_paths fragment_path guard_contents guard_dir_metadata
  local guard_metadata load_state refuse_manual_start
  (( LEGACY_RESTORE_GUARD_OWNED == 1 )) || return 0
  [[ ! -L "${LEGACY_RESTORE_GUARD_DIR}" && -d "${LEGACY_RESTORE_GUARD_DIR}" && \
    ! -L "${LEGACY_RESTORE_GUARD_DROPIN}" && -f "${LEGACY_RESTORE_GUARD_DROPIN}" ]] \
    || return 1
  guard_dir_metadata="$(stat -c '%u:%g:%a:%h' "${LEGACY_RESTORE_GUARD_DIR}")" || return 1
  guard_metadata="$(stat -c '%u:%g:%a:%h' "${LEGACY_RESTORE_GUARD_DROPIN}")" || return 1
  guard_contents="$(<"${LEGACY_RESTORE_GUARD_DROPIN}")" || return 1
  [[ "${guard_dir_metadata}" == "0:0:755:2" && \
    "${guard_metadata}" == "0:0:644:1" && \
    "${guard_contents}" == $'[Unit]\nRefuseManualStart=yes' ]] || return 1
  rm -f -- "${LEGACY_RESTORE_GUARD_DROPIN}" || return 1
  LEGACY_RESTORE_GUARD_OWNED=0
  rmdir -- "${LEGACY_RESTORE_GUARD_DIR}" >/dev/null 2>&1 || cleanup_status=1
  systemctl daemon-reload >/dev/null 2>&1 || cleanup_status=1
  (( cleanup_status == 0 )) || return 1
  load_state="$(systemctl show --no-pager --property=LoadState --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 1
  fragment_path="$(systemctl show --no-pager --property=FragmentPath --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 1
  dropin_paths="$(systemctl show --no-pager --property=DropInPaths --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 1
  refuse_manual_start="$(systemctl show --no-pager --property=RefuseManualStart --value \
    "${LEGACY_RESTORE_UNIT}" 2>/dev/null)" || return 1
  [[ "${load_state}" == "loaded" && \
    "${fragment_path}" == "${LEGACY_RESTORE_FRAGMENT}" && \
    -z "${dropin_paths}" && "${refuse_manual_start}" == "no" ]]
}

cleanup_orphaned_fresh_recovery_infrastructure() {
  local artifact_found=0 backup_root=/var/backups/hysteria2-panel entry gate metadata
  local script_contents unit_contents wants_link
  local -a artifact_stages=() gates=(
    "${FRESH_RECOVERY_DROPIN}"
    "${FRESH_RECOVERY_SERVER_DROPIN}"
    "${FRESH_RECOVERY_SERVER_443_DROPIN}"
  )
  local -a recovery_artifacts=(
    "${FRESH_RECOVERY_SCRIPT}"
    "${FRESH_RECOVERY_UNIT}"
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-install-recover.service
    "${FRESH_RECOVERY_DROPIN}"
    "${FRESH_RECOVERY_SERVER_DROPIN}"
    "${FRESH_RECOVERY_SERVER_443_DROPIN}"
  )
  [[ ! -e "${FRESH_IN_PROGRESS_MARKER}" && ! -L "${FRESH_IN_PROGRESS_MARKER}" && \
    ! -e "${LEGACY_FRESH_IN_PROGRESS_MARKER}" && \
    ! -L "${LEGACY_FRESH_IN_PROGRESS_MARKER}" ]] || return 0
  wants_link=/etc/systemd/system/multi-user.target.wants/hysteria2-panel-install-recover.service
  shopt -s nullglob
  artifact_stages=(
    /var/backups/hysteria2-panel/..install-recover.sh.*
    /etc/systemd/system/.hysteria2-panel-install-recover.service.*
    /etc/systemd/system/hysteria2-panel.service.d/.05-fresh-install-recovery.conf.*
    /etc/systemd/system/hysteria2-panel-server.service.d/.05-fresh-install-recovery.conf.*
    /etc/systemd/system/hysteria2-panel-server-443.service.d/.05-fresh-install-recovery.conf.*
  )
  shopt -u nullglob
  for entry in "${recovery_artifacts[@]}"; do
    [[ ! -e "${entry}" && ! -L "${entry}" ]] || artifact_found=1
  done
  (( ${#artifact_stages[@]} == 0 )) || artifact_found=1
  if (( artifact_found == 0 )); then
    rmdir -- /etc/systemd/system/hysteria2-panel-server.service.d \
      /etc/systemd/system/hysteria2-panel-server-443.service.d \
      "${UPGRADE_RECOVERY_DROPIN_DIR}" >/dev/null 2>&1 || true
    if [[ ! -e "${MANAGED_MARKER}" && ! -L "${MANAGED_MARKER}" && \
      ! -L "${backup_root}" && -d "${backup_root}" && \
      "$(stat -c '%u:%g:%a:%h' "${backup_root}")" == "0:0:700:2" ]]; then
      rmdir -- "${backup_root}" >/dev/null 2>&1 || true
    fi
    sync -f /etc/systemd/system \
      || fail "无法持久清除首次安装空恢复目录；安装已停止"
    if [[ -d /var/backups ]]; then
      sync -f /var/backups \
        || fail "无法持久清除首次安装空恢复目录；安装已停止"
    fi
    return 0
  fi
  if [[ -e "${FRESH_RECOVERY_SCRIPT}" || -L "${FRESH_RECOVERY_SCRIPT}" || \
    ${#artifact_stages[@]} -gt 0 ]]; then
    [[ ! -L "${backup_root}" && -d "${backup_root}" && \
      "$(stat -c '%u:%g:%a' "${backup_root}")" == "0:0:700" ]] \
      || fail "发现无法认证的首次安装恢复目录；安装已停止"
  fi
  if [[ -e "${FRESH_RECOVERY_SCRIPT}" || -L "${FRESH_RECOVERY_SCRIPT}" ]]; then
    [[ ! -L "${FRESH_RECOVERY_SCRIPT}" && -f "${FRESH_RECOVERY_SCRIPT}" && \
      "$(stat -c '%u:%g:%a:%h' "${FRESH_RECOVERY_SCRIPT}")" == "0:0:700:1" ]] \
      || fail "首次安装恢复脚本权限无效；安装已停止"
    script_contents="$(<"${FRESH_RECOVERY_SCRIPT}")" \
      || fail "无法读取首次安装恢复脚本；安装已停止"
    [[ "${script_contents}" == '#!/usr/bin/env bash'* && \
      "${script_contents}" == *"FRESH_TRANSACTION_MAGIC=${FRESH_TRANSACTION_MAGIC}"* && \
      "${script_contents}" == *'--recover-fresh'* ]] \
      || fail "首次安装恢复脚本身份无效；安装已停止"
  fi
  if [[ -e "${FRESH_RECOVERY_UNIT}" || -L "${FRESH_RECOVERY_UNIT}" ]]; then
    [[ ! -L "${FRESH_RECOVERY_UNIT}" && -f "${FRESH_RECOVERY_UNIT}" && \
      "$(stat -c '%u:%g:%a:%h' "${FRESH_RECOVERY_UNIT}")" == "0:0:644:1" ]] \
      || fail "首次安装恢复 unit 身份无效；安装已停止"
    unit_contents="$(<"${FRESH_RECOVERY_UNIT}")" \
      || fail "无法读取首次安装恢复 unit；安装已停止"
    [[ "${unit_contents}" == *"ConditionPathExists=${FRESH_IN_PROGRESS_MARKER}"* && \
      "${unit_contents}" == *"ExecStart=/bin/bash ${FRESH_RECOVERY_SCRIPT} --recover-fresh"* ]] \
      || fail "首次安装恢复 unit 内容无效；安装已停止"
  fi
  if (( ${#artifact_stages[@]} > 0 )); then
    for entry in "${artifact_stages[@]}"; do
      [[ ! -L "${entry}" && -f "${entry}" ]] \
        || fail "首次安装恢复暂存路径无效；安装已停止"
      metadata="$(stat -c '%u:%g:%a:%h' "${entry}")" \
        || fail "无法核验首次安装恢复暂存文件；安装已停止"
      [[ "${metadata}" == "0:0:600:1" || "${metadata}" == "0:0:644:1" ]] \
        || [[ "${metadata}" == "0:0:700:1" ]] \
        || fail "首次安装恢复暂存文件权限无效；安装已停止"
    done
  fi
  if [[ -e "${wants_link}" || -L "${wants_link}" ]]; then
    [[ -L "${wants_link}" && -f "${FRESH_RECOVERY_UNIT}" && \
      "${wants_link}" -ef "${FRESH_RECOVERY_UNIT}" ]] \
      || fail "首次安装恢复启用链接无效；安装已停止"
  fi
  for gate in "${gates[@]}"; do
    [[ ! -e "${gate}" && ! -L "${gate}" ]] && continue
    [[ ! -L "${gate}" && -f "${gate}" && \
      "$(stat -c '%u:%g:%a:%h' "${gate}")" == "0:0:644:1" && \
      "$(<"${gate}")" == $'[Unit]\nRequires=hysteria2-panel-install-recover.service\nAfter=hysteria2-panel-install-recover.service' ]] \
      || fail "首次安装启动门禁身份无效；安装已停止"
  done
  systemctl disable hysteria2-panel-install-recover.service >/dev/null 2>&1 || true
  rm -f -- "${wants_link}" "${FRESH_RECOVERY_UNIT}" "${FRESH_RECOVERY_SCRIPT}" \
    "${FRESH_RECOVERY_DROPIN}" "${FRESH_RECOVERY_SERVER_DROPIN}" \
    "${FRESH_RECOVERY_SERVER_443_DROPIN}"
  (( ${#artifact_stages[@]} == 0 )) || rm -f -- "${artifact_stages[@]}"
  rmdir -- "${UPGRADE_RECOVERY_DROPIN_DIR}" \
    /etc/systemd/system/hysteria2-panel-server.service.d \
    /etc/systemd/system/hysteria2-panel-server-443.service.d \
    "${backup_root}" >/dev/null 2>&1 || true
  sync -f /etc/systemd/system /etc/systemd/system/multi-user.target.wants /var/backups \
    || fail "无法持久清除首次安装恢复残留；安装已停止"
  systemctl daemon-reload \
    || fail "无法刷新首次安装恢复残留的 systemd 状态；安装已停止"
  echo "已清理上次在事务标记前中断的首次安装恢复基础设施。"
}

read_fresh_install_transaction() {
  local marker_path="$1" marker_hardlinks marker_line marker_metadata marker_magic
  local -a transaction_lines=()
  FRESH_ORIGINAL_RMEM=""
  FRESH_ORIGINAL_WMEM=""
  FRESH_ORIGINAL_QDISC=""
  FRESH_ORIGINAL_CC=""
  [[ ! -L "${marker_path}" && -f "${marker_path}" ]] || return 1
  marker_metadata="$(stat -c '%u:%g:%a' "${marker_path}")" || return 1
  marker_hardlinks="$(stat -c '%h' "${marker_path}")" || return 1
  [[ "${marker_metadata}" == "0:0:600" && "${marker_hardlinks}" == "1" ]] || return 1
  while IFS= read -r marker_line || [[ -n "${marker_line}" ]]; do
    transaction_lines+=("${marker_line}")
  done < "${marker_path}"
  if [[ "${marker_path}" == "${LEGACY_FRESH_IN_PROGRESS_MARKER}" ]]; then
    [[ ${#transaction_lines[@]} -eq 1 && \
      "${transaction_lines[0]}" =~ ^Hysteria2-panel\ installer\ [0-9]+\.[0-9]+\.[0-9]+$ ]] \
      || return 1
    return 0
  fi
  [[ ${#transaction_lines[@]} -eq 5 ]] || return 1
  marker_magic="${transaction_lines[0]}"
  [[ "${marker_magic}" == "${FRESH_TRANSACTION_MAGIC}" ]] || return 1
  [[ "${transaction_lines[1]}" =~ ^rmem=([0-9]+)$ ]] || return 1
  FRESH_ORIGINAL_RMEM="${BASH_REMATCH[1]}"
  [[ "${transaction_lines[2]}" =~ ^wmem=([0-9]+)$ ]] || return 1
  FRESH_ORIGINAL_WMEM="${BASH_REMATCH[1]}"
  [[ "${transaction_lines[3]}" =~ ^qdisc=([A-Za-z0-9_.+-]+)$ ]] || return 1
  FRESH_ORIGINAL_QDISC="${BASH_REMATCH[1]}"
  if [[ "${FRESH_ORIGINAL_QDISC}" == "-" ]]; then
    FRESH_ORIGINAL_QDISC=""
  fi
  [[ "${transaction_lines[4]}" =~ ^cc=([A-Za-z0-9_.+-]+)$ ]] || return 1
  FRESH_ORIGINAL_CC="${BASH_REMATCH[1]}"
}

restore_fresh_install_sysctls() {
  [[ -z "${FRESH_ORIGINAL_RMEM}" ]] || \
    sysctl -w "net.core.rmem_max=${FRESH_ORIGINAL_RMEM}" >/dev/null || return 1
  [[ -z "${FRESH_ORIGINAL_WMEM}" ]] || \
    sysctl -w "net.core.wmem_max=${FRESH_ORIGINAL_WMEM}" >/dev/null || return 1
  [[ -z "${FRESH_ORIGINAL_QDISC}" ]] || \
    sysctl -w "net.core.default_qdisc=${FRESH_ORIGINAL_QDISC}" >/dev/null || return 1
  [[ -z "${FRESH_ORIGINAL_CC}" ]] || \
    sysctl -w "net.ipv4.tcp_congestion_control=${FRESH_ORIGINAL_CC}" >/dev/null || return 1
}

remove_fresh_install_principals() {
  local principal principal_group
  for principal in hy2panel hy2server; do
    if id -u "${principal}" >/dev/null 2>&1; then
      if [[ "${principal}" == "hy2panel" ]]; then
        userdel --remove "${principal}" >/dev/null 2>&1 || return 1
      else
        userdel "${principal}" >/dev/null 2>&1 || return 1
      fi
    fi
    ! id -u "${principal}" >/dev/null 2>&1 || return 1
  done
  for principal_group in hy2panel hy2tls; do
    if getent group "${principal_group}" >/dev/null 2>&1; then
      groupdel "${principal_group}" >/dev/null 2>&1 || return 1
    fi
    ! getent group "${principal_group}" >/dev/null 2>&1 || return 1
  done
}

verify_fresh_install_commit_payload() {
  local expected_metadata panel_scheme_value path require_nonempty
  local -a required_files=(
    '/opt/hysteria2-panel/bin/hysteria|root:root:755:1|1'
    '/opt/hysteria2-panel/bin/cosign|root:root:755:1|1'
    '/opt/hysteria2-panel/hysteria2_panel.py|root:root:755:1|1'
    '/opt/hysteria2-panel/offsite_backup.py|root:root:755:1|1'
    '/opt/hysteria2-panel/qrcodegen.py|root:root:644:1|1'
    '/opt/hysteria2-panel/tcp_probe.py|root:root:755:1|1'
    '/opt/hysteria2-panel/hy2panel/systemd.py|root:root:644:1|1'
    '/opt/hysteria2-panel/hy2panel/dashboard.py|root:root:644:1|1'
    '/opt/hysteria2-panel/hy2panel/mobile_api.py|root:root:644:1|1'
    '/etc/hysteria2-panel/panel.env|root:hy2panel:640:1|1'
    '/etc/hysteria2-panel/hysteria.yaml|root:hy2tls:640:1|1'
    '/etc/hysteria2-panel/server.crt|root:hy2tls:640:1|1'
    '/etc/hysteria2-panel/server.key|root:hy2tls:640:1|1'
    '/var/lib/hysteria2-panel/panel.db|hy2panel:hy2panel:600:1|1'
    '/etc/systemd/system/hysteria2-panel.service|root:root:644:1|1'
    '/etc/systemd/system/hysteria2-panel-server.service|root:root:644:1|1'
    '/etc/systemd/system/hysteria2-panel-node-dns-admission.service|root:root:644:1|1'
    '/etc/systemd/system/hysteria2-panel-node-dns-admission.timer|root:root:644:1|1'
    '/etc/systemd/system/hysteria2-panel-offsite-backup.service|root:root:644:1|1'
    '/etc/systemd/system/hysteria2-panel-offsite-backup.timer|root:root:644:1|1'
    '/etc/systemd/system/hysteria2-panel-upgrade-recover.service|root:root:644:1|1'
    '/etc/systemd/system/hysteria2-panel.service.d/10-hysteria2-panel-upgrade-recovery.conf|root:root:644:1|1'
    '/etc/sudoers.d/hysteria2-panel|root:root:440:1|1'
    "${SYSCTL_FILE}|root:root:644:1|1"
    "${TMPFILES_FILE}|root:root:644:1|1"
  )
  for path in "${required_files[@]}"; do
    IFS='|' read -r path expected_metadata require_nonempty <<< "${path}"
    [[ ! -L "${path}" && -f "${path}" ]] || return 1
    [[ "$(stat -c '%U:%G:%a:%h' "${path}")" == "${expected_metadata}" ]] || return 1
    [[ "${require_nonempty}" != "1" || -s "${path}" ]] || return 1
  done
  panel_scheme_value="$(awk -F= '$1 == "HY2PANEL_PANEL_SCHEME" {print $2}' \
    /etc/hysteria2-panel/panel.env)" || return 1
  if [[ "${panel_scheme_value}" == "https" ]]; then
    for path in \
      /opt/hysteria2-panel/acme-deploy.sh \
      /opt/hysteria2-panel/acme-renew.sh \
      /etc/systemd/system/hysteria2-panel-cert-renew.service \
      /etc/systemd/system/hysteria2-panel-cert-renew.timer \
      /etc/hysteria2-panel/panel-tls-current/fullchain.pem \
      /etc/hysteria2-panel/panel-tls-current/privkey.pem; do
      [[ -f "${path}" && -s "${path}" ]] || return 1
    done
    [[ -L "${PANEL_CERT_FILE}" && \
      "$(readlink "${PANEL_CERT_FILE}")" == "panel-tls-current/fullchain.pem" ]] \
      || return 1
    [[ -L "${PANEL_KEY_FILE}" && \
      "$(readlink "${PANEL_KEY_FILE}")" == "panel-tls-current/privkey.pem" ]] \
      || return 1
    [[ -L /etc/systemd/system/timers.target.wants/hysteria2-panel-cert-renew.timer ]] \
      || return 1
  elif [[ "${panel_scheme_value}" != "http" ]]; then
    return 1
  fi
  [[ -L /etc/systemd/system/timers.target.wants/hysteria2-panel-node-dns-admission.timer ]] \
    || return 1
  [[ -L /etc/systemd/system/timers.target.wants/hysteria2-panel-offsite-backup.timer ]] \
    || return 1
}

flush_fresh_cleanup_before_disarm() {
  local current_value path
  local -a removed_paths=(
    /opt/hysteria2-panel
    /etc/hysteria2-panel
    /var/lib/hysteria2-panel
    /etc/systemd/system/hysteria2-panel.service
    /etc/systemd/system/hysteria2-panel-server.service
    /etc/systemd/system/hysteria2-panel-server-443.service
    /etc/systemd/system/hysteria2-panel-tcp-probe.service
    /etc/systemd/system/hysteria2-panel-tcp-probe-443.service
    /etc/systemd/system/hysteria2-panel-restore.service
    /etc/systemd/system/hysteria2-panel-restore-resume.service
    /etc/systemd/system/hysteria2-panel-restore-recover.service
    /etc/systemd/system/hysteria2-panel-update.service
    /etc/systemd/system/hysteria2-panel-cert-renew.service
    /etc/systemd/system/hysteria2-panel-cert-renew.timer
    /etc/systemd/system/hysteria2-panel-node-dns-admission.service
    /etc/systemd/system/hysteria2-panel-node-dns-admission.timer
    /etc/systemd/system/hysteria2-panel-offsite-backup.service
    /etc/systemd/system/hysteria2-panel-offsite-backup.timer
    /etc/systemd/system/hysteria2-panel-egress-full.service
    /etc/systemd/system/hysteria2-panel-egress-web.service
    /etc/systemd/system/hysteria2-panel-egress-recover.service
    "${UPGRADE_RECOVERY_SCRIPT}"
    "${UPGRADE_RECOVERY_UNIT}"
    "${UPGRADE_RECOVERY_DROPIN}"
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-restore-resume.service
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-upgrade-recover.service
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel.service
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-server.service
    /etc/systemd/system/timers.target.wants/hysteria2-panel-cert-renew.timer
    /etc/systemd/system/timers.target.wants/hysteria2-panel-node-dns-admission.timer
    /etc/systemd/system/timers.target.wants/hysteria2-panel-offsite-backup.timer
    /etc/sudoers.d/hysteria2-panel
    "${SYSCTL_FILE}"
    "${TMPFILES_FILE}"
  )
  local -a cleanup_sync_dirs=(
    /opt
    /etc
    /var/lib
    /var/backups
    /etc/systemd/system
    /etc/sudoers.d
    /etc/sysctl.d
    /etc/tmpfiles.d
  )
  for path in "${removed_paths[@]}"; do
    [[ ! -e "${path}" && ! -L "${path}" ]] || return 1
  done
  if [[ -n "${FRESH_ORIGINAL_RMEM}" ]]; then
    current_value="$(sysctl -n net.core.rmem_max)" || return 1
    [[ "${current_value}" == "${FRESH_ORIGINAL_RMEM}" ]] || return 1
  fi
  if [[ -n "${FRESH_ORIGINAL_WMEM}" ]]; then
    current_value="$(sysctl -n net.core.wmem_max)" || return 1
    [[ "${current_value}" == "${FRESH_ORIGINAL_WMEM}" ]] || return 1
  fi
  if [[ -n "${FRESH_ORIGINAL_QDISC}" ]]; then
    current_value="$(sysctl -n net.core.default_qdisc)" || return 1
    [[ "${current_value}" == "${FRESH_ORIGINAL_QDISC}" ]] || return 1
  fi
  if [[ -n "${FRESH_ORIGINAL_CC}" ]]; then
    current_value="$(sysctl -n net.ipv4.tcp_congestion_control)" || return 1
    [[ "${current_value}" == "${FRESH_ORIGINAL_CC}" ]] || return 1
  fi
  sync_existing_directories "${cleanup_sync_dirs[@]}"
}

arm_fresh_install_transaction() {
  local original_cc original_qdisc original_rmem original_wmem transaction_stage
  [[ ! -e "${FRESH_IN_PROGRESS_MARKER}" && ! -L "${FRESH_IN_PROGRESS_MARKER}" ]] \
    || fail "首次安装事务标记已存在；安装已停止"
  original_rmem="$(sysctl -n net.core.rmem_max)" \
    || fail "无法读取当前 UDP 接收缓冲；安装已停止"
  original_wmem="$(sysctl -n net.core.wmem_max)" \
    || fail "无法读取当前 UDP 发送缓冲；安装已停止"
  if [[ -e /proc/sys/net/core/default_qdisc ]]; then
    original_qdisc="$(sysctl -n net.core.default_qdisc)" \
      || fail "无法读取当前队列算法；安装已停止"
  else
    original_qdisc="-"
  fi
  original_cc="$(sysctl -n net.ipv4.tcp_congestion_control)" \
    || fail "无法读取当前拥塞控制算法；安装已停止"
  [[ "${original_rmem}" =~ ^[0-9]+$ && "${original_wmem}" =~ ^[0-9]+$ && \
    "${original_qdisc}" =~ ^[A-Za-z0-9_.+-]+$ && \
    "${original_cc}" =~ ^[A-Za-z0-9_.+-]+$ ]] \
    || fail "当前网络参数无法安全写入首次安装事务；安装已停止"
  transaction_stage="${TMP_DIR}/fresh-install-transaction"
  printf '%s\nrmem=%s\nwmem=%s\nqdisc=%s\ncc=%s\n' \
    "${FRESH_TRANSACTION_MAGIC}" "${original_rmem}" "${original_wmem}" \
    "${original_qdisc}" "${original_cc}" > "${transaction_stage}"
  FRESH_INSTALL_MUTATED=1
  durable_replace_file "${transaction_stage}" "${FRESH_IN_PROGRESS_MARKER}" 0600 \
    || fail "无法持久化首次安装事务；安装已停止"
}

install_fresh_recovery_infrastructure() {
  local recovery_unit_stage="${TMP_DIR}/hysteria2-panel-install-recover.service"
  install -d -o root -g root -m 0700 /var/backups/hysteria2-panel
  sync -f /var/backups /var/backups/hysteria2-panel \
    || fail "无法持久化首次安装恢复目录；安装已停止"
  durable_replace_file "$0" "${FRESH_RECOVERY_SCRIPT}" 0700 \
    || fail "无法持久化首次安装恢复脚本；安装已停止"
  cat > "${recovery_unit_stage}" <<EOF
[Unit]
Description=Recover an interrupted Hysteria 2 panel fresh install before startup
After=local-fs.target systemd-tmpfiles-setup.service
Before=hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-server-443.service
ConditionPathExists=${FRESH_IN_PROGRESS_MARKER}

[Service]
Type=oneshot
ExecStart=/bin/bash ${FRESH_RECOVERY_SCRIPT} --recover-fresh
TimeoutStartSec=15min
TimeoutStopSec=30s
KillSignal=SIGTERM
UMask=0077
PrivateTmp=true
ProtectHome=true
RestrictSUIDSGID=true
LockPersonality=true
TasksMax=128
MemoryMax=512M

[Install]
WantedBy=multi-user.target
EOF
  durable_replace_file "${recovery_unit_stage}" "${FRESH_RECOVERY_UNIT}" 0644 \
    || fail "无法持久化首次安装恢复 unit；安装已停止"
  systemctl daemon-reload || fail "无法加载首次安装恢复 unit；安装已停止"
  systemctl enable hysteria2-panel-install-recover.service \
    || fail "无法启用首次安装开机恢复；安装已停止"
  sync -f /etc/systemd/system \
    /etc/systemd/system/multi-user.target.wants \
    || fail "无法持久化首次安装开机恢复；安装已停止"
}

install_fresh_recovery_gate() {
  local dropin dropin_directory
  local gate_stage="${TMP_DIR}/05-fresh-install-recovery.conf"
  local -a dropins=(
    "${FRESH_RECOVERY_DROPIN}"
    "${FRESH_RECOVERY_SERVER_DROPIN}"
  )
  (( UDP_443_ENABLED == 0 )) || dropins+=("${FRESH_RECOVERY_SERVER_443_DROPIN}")
  cat > "${gate_stage}" <<'EOF'
[Unit]
Requires=hysteria2-panel-install-recover.service
After=hysteria2-panel-install-recover.service
EOF
  for dropin in "${dropins[@]}"; do
    dropin_directory="${dropin%/*}"
    install -d -o root -g root -m 0755 "${dropin_directory}"
    sync -f /etc/systemd/system "${dropin_directory}" \
      || fail "无法持久化首次安装启动门禁目录；安装已停止"
    durable_replace_file "${gate_stage}" "${dropin}" 0644 \
      || fail "无法持久化首次安装启动门禁；安装已停止"
  done
  systemctl daemon-reload || fail "无法加载首次安装启动门禁；安装已停止"
}

disarm_fresh_install_transaction() {
  durable_remove_file "${FRESH_IN_PROGRESS_MARKER}" || return 1
  rm -f -- "${FRESH_RECOVERY_DROPIN}" \
    "${FRESH_RECOVERY_SERVER_DROPIN}" \
    "${FRESH_RECOVERY_SERVER_443_DROPIN}" || return 1
  rmdir -- "${UPGRADE_RECOVERY_DROPIN_DIR}" >/dev/null 2>&1 || true
  rmdir -- /etc/systemd/system/hysteria2-panel-server.service.d \
    /etc/systemd/system/hysteria2-panel-server-443.service.d \
    >/dev/null 2>&1 || true
  sync -f /etc/systemd/system || return 1
  systemctl daemon-reload || return 1
  systemctl disable hysteria2-panel-install-recover.service >/dev/null 2>&1 || true
  rm -f -- \
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-install-recover.service \
    "${FRESH_RECOVERY_UNIT}" "${FRESH_RECOVERY_SCRIPT}" || return 1
  rmdir -- /var/backups/hysteria2-panel >/dev/null 2>&1 || true
  sync -f /etc/systemd/system /etc/systemd/system/multi-user.target.wants \
    /var/backups || return 1
  systemctl daemon-reload || return 1
}

recover_interrupted_fresh_install() {
  local active_marker="" marker_metadata
  if [[ -e "${FRESH_IN_PROGRESS_MARKER}" || -L "${FRESH_IN_PROGRESS_MARKER}" ]]; then
    active_marker="${FRESH_IN_PROGRESS_MARKER}"
  elif [[ -e "${LEGACY_FRESH_IN_PROGRESS_MARKER}" || \
    -L "${LEGACY_FRESH_IN_PROGRESS_MARKER}" ]]; then
    active_marker="${LEGACY_FRESH_IN_PROGRESS_MARKER}"
  else
    return 0
  fi
  [[ ! -L "${active_marker}" && -f "${active_marker}" ]] \
    || fail "发现无效的首次安装事务标记；为避免接管未知文件，安装已停止"
  marker_metadata="$(stat -c '%u:%g:%a' "${active_marker}")" \
    || fail "无法核验首次安装事务标记；安装已停止"
  [[ "${marker_metadata}" == "0:0:600" ]] \
    || fail "首次安装事务标记权限无效；安装已停止"
  read_fresh_install_transaction "${active_marker}" \
    || fail "首次安装事务标记不属于当前安装器；安装已停止"
  if [[ -e "${MANAGED_MARKER}" || -L "${MANAGED_MARKER}" ]]; then
    [[ ! -L "${MANAGED_MARKER}" && -f "${MANAGED_MARKER}" && ! -s "${MANAGED_MARKER}" && \
      "$(stat -c '%u:%g:%a:%h' "${MANAGED_MARKER}")" == "0:0:644:1" ]] \
      || fail "首次安装提交标记无效；安装已停止"
    verify_fresh_install_commit_payload \
      || fail "首次安装提交文件不完整；恢复门禁已保留，安装已停止"
    if declare -F finalize_firewall_transaction >/dev/null 2>&1; then
      finalize_firewall_transaction \
        || fail "无法收口已提交的防火墙事务；安装已停止"
    fi
    if [[ "${active_marker}" == "${FRESH_IN_PROGRESS_MARKER}" ]]; then
      disarm_fresh_install_transaction \
        || fail "无法清除已提交的首次安装恢复基础设施；安装已停止"
    else
      durable_remove_file "${active_marker}" \
        || fail "无法清除已提交的首次安装事务；安装已停止"
    fi
    echo "检测到已完成但未收口的首次部署，事务已安全提交。"
    return 0
  fi
  echo "检测到上次未完成的首次部署，正在安全清理后重试…"
  stop_loaded_units \
    hysteria2-panel-upgrade-recover.service \
    hysteria2-panel-node-dns-admission.timer \
    hysteria2-panel-node-dns-admission.service \
    hysteria2-panel-offsite-backup.timer \
    hysteria2-panel-offsite-backup.service \
    hysteria2-panel-cert-renew.timer \
    hysteria2-panel-cert-renew.service \
    hysteria2-panel-restore.service \
    hysteria2-panel-update.service \
    hysteria2-panel-egress-full.service \
    hysteria2-panel-egress-web.service \
    hysteria2-panel-egress-recover.service \
    hysteria2-panel-tcp-probe-443.service \
    hysteria2-panel-server-443.service \
    hysteria2-panel-tcp-probe.service \
    hysteria2-panel-server.service \
    hysteria2-panel-restore-resume.service \
    hysteria2-panel-restore-recover.service \
    hysteria2-panel.service \
    || fail "上次部署遗留进程无法全部停止；请人工检查后重试"
  systemctl disable hysteria2-panel-upgrade-recover.service \
    hysteria2-panel-cert-renew.timer \
    hysteria2-panel-node-dns-admission.timer \
    hysteria2-panel-offsite-backup.timer \
    hysteria2-panel-server.service hysteria2-panel.service \
    >/dev/null 2>&1 || true
  if declare -F rollback_persisted_firewall_transaction >/dev/null 2>&1; then
    rollback_persisted_firewall_transaction \
      || fail "无法撤销上次首次部署创建的防火墙规则；安装已停止"
  fi
  rm -f -- \
    /etc/systemd/system/hysteria2-panel.service \
    /etc/systemd/system/hysteria2-panel-server.service \
    /etc/systemd/system/hysteria2-panel-server-443.service \
    /etc/systemd/system/hysteria2-panel-tcp-probe.service \
    /etc/systemd/system/hysteria2-panel-tcp-probe-443.service \
    /etc/systemd/system/hysteria2-panel-restore.service \
    /etc/systemd/system/hysteria2-panel-restore-resume.service \
    /etc/systemd/system/hysteria2-panel-restore-recover.service \
    /etc/systemd/system/hysteria2-panel-update.service \
    /etc/systemd/system/hysteria2-panel-cert-renew.service \
    /etc/systemd/system/hysteria2-panel-cert-renew.timer \
    /etc/systemd/system/hysteria2-panel-node-dns-admission.service \
    /etc/systemd/system/hysteria2-panel-node-dns-admission.timer \
    /etc/systemd/system/hysteria2-panel-offsite-backup.service \
    /etc/systemd/system/hysteria2-panel-offsite-backup.timer \
    /etc/systemd/system/hysteria2-panel-egress-full.service \
    /etc/systemd/system/hysteria2-panel-egress-web.service \
    /etc/systemd/system/hysteria2-panel-egress-recover.service \
    "${UPGRADE_RECOVERY_SCRIPT}" \
    "${UPGRADE_RECOVERY_UNIT}" \
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-restore-resume.service \
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-upgrade-recover.service \
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel.service \
    /etc/systemd/system/multi-user.target.wants/hysteria2-panel-server.service \
    /etc/systemd/system/timers.target.wants/hysteria2-panel-cert-renew.timer \
    /etc/systemd/system/timers.target.wants/hysteria2-panel-node-dns-admission.timer \
    /etc/systemd/system/timers.target.wants/hysteria2-panel-offsite-backup.timer \
    /etc/sudoers.d/hysteria2-panel "${SYSCTL_FILE}" "${TMPFILES_FILE}"
  rm -f -- "${UPGRADE_RECOVERY_DROPIN}"
  rmdir -- "${UPGRADE_RECOVERY_DROPIN_DIR}" >/dev/null 2>&1 || true
  remove_fresh_install_principals \
    || fail "无法删除首次部署创建的系统账号或组；安装已停止"
  rm -rf -- \
    /opt/hysteria2-panel \
    /etc/hysteria2-panel \
    /var/lib/hysteria2-panel
  restore_fresh_install_sysctls \
    || fail "无法恢复首次部署前的内核网络参数；安装已停止"
  reset_maintenance_lock_permissions \
    || fail "无法收紧维护锁权限；为避免遗留未知共享权限，安装已停止"
  flush_fresh_cleanup_before_disarm \
    || fail "无法验证并持久化首次部署清场；恢复门禁已保留，安装已停止"
  if [[ "${active_marker}" == "${FRESH_IN_PROGRESS_MARKER}" ]]; then
    disarm_fresh_install_transaction \
      || fail "无法持久清除首次安装恢复基础设施；安装已安全清场但需人工检查残留"
  else
    durable_remove_file "${active_marker}" \
      || fail "无法持久清除首次安装事务标记；安装已停止"
  fi
  rm -rf -- /var/backups/hysteria2-panel
  sync
  systemctl daemon-reload || fail "无法刷新上次部署的 systemd 状态；安装已停止"
}

wait_for_listener() {
  local protocol="$1" port="$2"
  local listener_output port_number
  local -a socket_options
  [[ "${port}" =~ ^0*[0-9]{1,5}$ ]] || return 2
  port_number=$((10#${port}))
  (( port_number >= 1 && port_number <= 65535 )) || return 2
  case "${protocol}" in
    udp) socket_options=(-H -lun) ;;
    tcp) socket_options=(-H -ltn) ;;
    *) return 2 ;;
  esac
  for _attempt in {1..30}; do
    if listener_output="$(ss "${socket_options[@]}" "sport = :${port_number}")" \
      && [[ -n "${listener_output}" ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_health() {
  local url="$1"
  local tls_mode="$2"
  local curl_options=(-fsS --connect-timeout 2 --max-time 3)
  if [[ "${tls_mode}" == "insecure" ]]; then
    curl_options+=(-k)
  fi
  for _attempt in {1..30}; do
    if curl "${curl_options[@]}" "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

checkpoint_database() {
  local database_path="$1"
  "${PYTHON_BIN}" - "${database_path}" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1], timeout=30) as connection:
    checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if (
        checkpoint is None
        or len(checkpoint) != 3
        or any(type(value) is not int for value in checkpoint)
        or checkpoint[0] != 0
    ):
        raise SystemExit(1)
    result = connection.execute("PRAGMA quick_check").fetchone()
if not result or result[0] != "ok":
    raise SystemExit(1)
PY
}

assert_units_unclaimed() {
  local active_state drop_in_paths fragment_path key load_state output unit_file value
  local seen_active seen_dropins seen_fragment seen_load
  for unit_file in \
    hysteria2-panel-upgrade-recover.service \
    hysteria2-panel.service \
    hysteria2-panel-server.service \
    hysteria2-panel-server-443.service \
    hysteria2-panel-tcp-probe.service \
    hysteria2-panel-tcp-probe-443.service \
    hysteria2-panel-restore.service \
    hysteria2-panel-restore-recover.service \
    hysteria2-panel-restore-resume.service \
    hysteria2-panel-egress-full.service \
    hysteria2-panel-egress-web.service \
    hysteria2-panel-egress-recover.service \
    hysteria2-panel-cert-renew.service \
    hysteria2-panel-cert-renew.timer \
    hysteria2-panel-node-dns-admission.service \
    hysteria2-panel-node-dns-admission.timer \
    hysteria2-panel-offsite-backup.service \
    hysteria2-panel-offsite-backup.timer \
    hysteria2-panel-update.service; do
    output="$(systemctl show --no-pager \
      --property=LoadState --property=ActiveState \
      --property=FragmentPath --property=DropInPaths \
      "${unit_file}" 2>/dev/null)" \
      || fail "无法确认 ${unit_file} 是否已存在；首次安装已停止"
    load_state="" active_state="" fragment_path="" drop_in_paths=""
    seen_load=0 seen_active=0 seen_fragment=0 seen_dropins=0
    while IFS='=' read -r key value; do
      case "${key}" in
        LoadState) (( seen_load == 0 )) || fail "systemd 返回了重复字段；首次安装已停止"; load_state="${value}"; seen_load=1 ;;
        ActiveState) (( seen_active == 0 )) || fail "systemd 返回了重复字段；首次安装已停止"; active_state="${value}"; seen_active=1 ;;
        FragmentPath) (( seen_fragment == 0 )) || fail "systemd 返回了重复字段；首次安装已停止"; fragment_path="${value}"; seen_fragment=1 ;;
        DropInPaths) (( seen_dropins == 0 )) || fail "systemd 返回了重复字段；首次安装已停止"; drop_in_paths="${value}"; seen_dropins=1 ;;
        "") ;;
        *) fail "systemd 返回了未知字段；首次安装已停止" ;;
      esac
    done <<< "${output}"
    (( seen_load == 1 && seen_active == 1 && seen_fragment == 1 && seen_dropins == 1 )) \
      || fail "systemd 未返回完整的 unit 所有权信息；首次安装已停止"
    [[ "${load_state}" == "not-found" && "${active_state}" == "inactive" && \
      -z "${fragment_path}" && -z "${drop_in_paths}" ]] \
      || fail "首次安装检测到同名 systemd 服务 ${unit_file}；为避免接管现有服务，安装已停止"
  done
}

assert_units_claimed_by_installer() {
  local drop_in_paths expected_dropins expected_path fragment_path key load_state output unit_file value
  local seen_dropins seen_fragment seen_load
  for unit_file in \
    hysteria2-panel-upgrade-recover.service \
    hysteria2-panel.service \
    hysteria2-panel-server.service \
    hysteria2-panel-server-443.service \
    hysteria2-panel-tcp-probe.service \
    hysteria2-panel-tcp-probe-443.service \
    hysteria2-panel-restore.service \
    hysteria2-panel-restore-recover.service \
    hysteria2-panel-restore-resume.service \
    hysteria2-panel-egress-full.service \
    hysteria2-panel-egress-web.service \
    hysteria2-panel-egress-recover.service \
    hysteria2-panel-cert-renew.service \
    hysteria2-panel-cert-renew.timer \
    hysteria2-panel-node-dns-admission.service \
    hysteria2-panel-node-dns-admission.timer \
    hysteria2-panel-offsite-backup.service \
    hysteria2-panel-offsite-backup.timer \
    hysteria2-panel-update.service; do
    expected_path="/etc/systemd/system/${unit_file}"
    output="$(systemctl show --no-pager \
      --property=LoadState --property=FragmentPath --property=DropInPaths \
      "${unit_file}" 2>/dev/null)" \
      || fail "无法复查 ${unit_file} 的 systemd 所有权；安装已停止"
    load_state="" fragment_path="" drop_in_paths=""
    seen_load=0 seen_fragment=0 seen_dropins=0
    while IFS='=' read -r key value; do
      case "${key}" in
        LoadState) (( seen_load == 0 )) || fail "systemd 返回了重复字段；安装已停止"; load_state="${value}"; seen_load=1 ;;
        FragmentPath) (( seen_fragment == 0 )) || fail "systemd 返回了重复字段；安装已停止"; fragment_path="${value}"; seen_fragment=1 ;;
        DropInPaths) (( seen_dropins == 0 )) || fail "systemd 返回了重复字段；安装已停止"; drop_in_paths="${value}"; seen_dropins=1 ;;
        "") ;;
        *) fail "systemd 返回了未知字段；安装已停止" ;;
      esac
    done <<< "${output}"
    (( seen_load == 1 && seen_fragment == 1 && seen_dropins == 1 )) \
      || fail "systemd 未返回完整的 unit 所有权信息；安装已停止"
    if [[ -f "${expected_path}" ]]; then
      expected_dropins=""
      if [[ "${unit_file}" == "hysteria2-panel.service" ]]; then
        expected_dropins="${UPGRADE_RECOVERY_DROPIN}"
      fi
      if (( EXISTING_INSTALL == 0 )) && \
        [[ -e "${FRESH_IN_PROGRESS_MARKER}" && ! -L "${FRESH_IN_PROGRESS_MARKER}" ]]; then
        case "${unit_file}" in
          hysteria2-panel.service)
            expected_dropins="${FRESH_RECOVERY_DROPIN} ${UPGRADE_RECOVERY_DROPIN}"
            ;;
          hysteria2-panel-server.service)
            expected_dropins="${FRESH_RECOVERY_SERVER_DROPIN}"
            ;;
          hysteria2-panel-server-443.service)
            expected_dropins="${FRESH_RECOVERY_SERVER_443_DROPIN}"
            ;;
        esac
      fi
      [[ "${load_state}" == "loaded" && "${fragment_path}" == "${expected_path}" && \
        "${drop_in_paths}" == "${expected_dropins}" ]] \
        || fail "${unit_file} 被其他 systemd fragment 或 drop-in 覆盖；安装已停止"
    else
      [[ "${load_state}" == "not-found" && -z "${fragment_path}" && -z "${drop_in_paths}" ]] \
        || fail "已停用的 ${unit_file} 仍被其他 systemd 配置接管；安装已停止"
    fi
  done
}

database_is_healthy() {
  local database_path="$1"
  "${PYTHON_BIN}" - "${database_path}" <<'PY'
import sqlite3
import sys

with sqlite3.connect("file:{}?mode=ro".format(sys.argv[1]), uri=True, timeout=30) as connection:
    result = connection.execute("PRAGMA quick_check").fetchone()
if not result or result[0] != "ok":
    raise SystemExit(1)
PY
}

create_database_snapshot() {
  local database_path="$1" snapshot_path="$2"
  "${PYTHON_BIN}" - "${database_path}" "${snapshot_path}" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1], timeout=30) as source:
    with sqlite3.connect(sys.argv[2], timeout=30) as destination:
        source.backup(destination)
        result = destination.execute("PRAGMA quick_check").fetchone()
if not result or result[0] != "ok":
    raise SystemExit(1)
PY
}

preserve_or_restore_database() {
  local database_path="$1" snapshot_path="$2"
  if [[ -f "${database_path}" ]] && database_is_healthy "${database_path}"; then
    checkpoint_database "${database_path}" \
      || echo "警告：最新数据库健康但 WAL 正忙；回滚将保留数据库及 WAL 供 SQLite 自动恢复。" >&2
    echo "回滚保留已验证健康的最新用户数据库及流量。" >&2
    return 0
  fi
  [[ -f "${snapshot_path}" ]] || return 1
  rm -f -- "${database_path}-wal" "${database_path}-shm"
  cp -a "${snapshot_path}" "${database_path}" || return 1
  checkpoint_database "${database_path}"
}

stage_verified_installed_binary() {
  local installed_path="$1" expected_sha256="$2" destination="$3"
  local metadata
  [[ "${expected_sha256}" =~ ^[0-9a-f]{64}$ ]] || return 1
  [[ ! -L "${installed_path}" && -f "${installed_path}" ]] || return 1
  metadata="$(stat -c '%u:%g:%a:%h' "${installed_path}")" || return 1
  [[ "${metadata}" =~ ^0:0:([0-7]{3,4}):1$ ]] || return 1
  (( (8#${BASH_REMATCH[1]} & 022) == 0 )) || return 1
  printf '%s  %s\n' "${expected_sha256}" "${installed_path}" \
    | sha256sum --check --status || return 1
  install -o root -g root -m 0755 "${installed_path}" "${destination}" || return 1
  printf '%s  %s\n' "${expected_sha256}" "${destination}" \
    | sha256sum --check --status
}

ufw_rule_is_recorded() {
  local rule="$1"
  awk -v wanted="${rule}" '
    $1 == "ufw" {
      action = 2
      if ($2 == "insert" && $3 ~ /^[0-9]+$/) action = 4
      if ($2 == "prepend") action = 3
      if ($action != "allow") next
      field = action + 1
      if ($field == "in") field += 1
      if ($field == wanted) found = 1
    }
    END { exit(found ? 0 : 1) }
  ' <<< "${UFW_ADDED_RULES}"
}

ufw_rule_is_denied() {
  local rule="$1"
  "${PYTHON_BIN}" - "${rule}" 3<<< "${UFW_ADDED_RULES}" <<'PY'
import os
import re
import shlex
import sys

wanted_port_text, wanted_protocol = sys.argv[1].split("/", 1)
wanted_port = int(wanted_port_text)


def matches_port(spec):
    declared_protocol = None
    match = re.fullmatch(r"(.+?)/(tcp|udp)", spec)
    if match:
        spec, declared_protocol = match.groups()
    if declared_protocol is not None and declared_protocol != wanted_protocol:
        return False
    result = False
    for item in spec.split(","):
        if re.fullmatch(r"[0-9]+", item):
            low = high = int(item)
        else:
            match = re.fullmatch(r"([0-9]+):([0-9]+)", item)
            if not match:
                raise ValueError("unknown UFW port expression")
            low, high = map(int, match.groups())
        if not (1 <= low <= high <= 65535):
            raise ValueError("invalid UFW port expression")
        result = result or low <= wanted_port <= high
    return result


try:
    with os.fdopen(3) as rules:
        for raw_line in rules:
            try:
                words = shlex.split(raw_line, comments=False, posix=True)
            except ValueError:
                raise SystemExit(2)
            if not words or words[0] != "ufw":
                continue
            cursor = 1
            if cursor < len(words) and words[cursor] == "insert":
                if cursor + 1 >= len(words) or not words[cursor + 1].isdigit():
                    raise SystemExit(2)
                cursor += 2
            elif cursor < len(words) and words[cursor] == "prepend":
                cursor += 1
            if cursor < len(words) and words[cursor] == "route":
                continue
            if cursor >= len(words) or words[cursor] not in {"deny", "reject", "limit"}:
                continue
            action = words[cursor]
            cursor += 1
            if cursor < len(words) and words[cursor] == "out":
                continue
            if cursor < len(words) and words[cursor] == "in":
                cursor += 1
            if cursor >= len(words):
                raise SystemExit(2)

            tail = words[cursor:]
            if tail[0] not in {"on", "proto", "from", "to", "comment", "log", "log-all"}:
                if matches_port(tail[0]):
                    raise SystemExit(0)
                continue

            declared_protocol = None
            for index, token in enumerate(tail):
                if token == "proto":
                    if index + 1 >= len(tail):
                        raise SystemExit(2)
                    declared_protocol = tail[index + 1]
            if declared_protocol is not None and declared_protocol != wanted_protocol:
                continue
            if action == "limit" and declared_protocol is None and wanted_protocol != "tcp":
                continue

            try:
                to_index = tail.index("to")
            except ValueError:
                # No destination selector means some traffic to every destination
                # port can be blocked, even when a source-port selector is present.
                raise SystemExit(0)
            if to_index + 1 >= len(tail):
                raise SystemExit(2)
            destination_tail = tail[to_index + 2 :]
            if "port" not in destination_tail:
                raise SystemExit(0)
            port_index = destination_tail.index("port")
            if port_index + 1 >= len(destination_tail):
                raise SystemExit(2)
            if matches_port(destination_tail[port_index + 1]):
                raise SystemExit(0)
except (OSError, ValueError):
    raise SystemExit(2)
raise SystemExit(1)
PY
}

ufw_has_framework_customization() {
  local framework_file
  for framework_file in before.rules before6.rules after.rules after6.rules; do
    [[ -f "${UFW_RULES_PATH}/${framework_file}" && \
      -f "${UFW_TEMPLATE_PATH}/${framework_file}" ]] || return 2
    cmp -s -- "${UFW_RULES_PATH}/${framework_file}" \
      "${UFW_TEMPLATE_PATH}/${framework_file}" || return 0
  done
  for framework_file in before.init after.init; do
    [[ ! -x "${UFW_RULES_PATH}/${framework_file}" ]] || return 0
  done
  return 1
}

ufw_iptables_family_has_unmanaged_rules() {
  local command_name="$1" prefix="$2" rules status
  rules="$("${command_name}" 2>/dev/null)" || return 2
  [[ -n "${rules}" ]] || return 2
  if printf '%s\n' "${rules}" | "${PYTHON_BIN}" -c '
import shlex
import sys

prefix = sys.argv[1]
expected = [
    "before-logging-input",
    "before-input",
    "after-input",
    "after-logging-input",
    "reject-input",
    "track-input",
]
expected_rules = [["-A", "INPUT", "-j", f"{prefix}-{name}"] for name in expected]
table = None
filter_seen = False
filter_committed = False
input_seen = False
input_rules = []
disabled_ipv6 = [["-A", "INPUT", "-i", "lo", "-j", "ACCEPT"]]
try:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        words = shlex.split(line, comments=False, posix=True)
        if line.startswith("*"):
            if table is not None or len(words) != 1:
                raise ValueError
            table = line[1:]
            filter_seen = filter_seen or table == "filter"
            continue
        if line == "COMMIT":
            if table is None:
                raise ValueError
            filter_committed = filter_committed or table == "filter"
            table = None
            continue
        if table is None or not words:
            raise ValueError
        if words[0].startswith(":"):
            if len(words) < 2:
                raise ValueError
            chain = words[0][1:]
            if table == "filter" and chain == "INPUT":
                input_seen = True
            if chain in {"INPUT", "PREROUTING"} and table != "filter" and words[1] != "ACCEPT":
                raise SystemExit(0)
            continue
        if words[0] == "-P":
            if len(words) != 3:
                raise ValueError
            if words[1] in {"INPUT", "PREROUTING"} and table != "filter" and words[2] != "ACCEPT":
                raise SystemExit(0)
            continue
        if words[0] != "-A" or len(words) < 3:
            raise ValueError
        if words[1] in {"INPUT", "PREROUTING"}:
            if table == "filter" and words[1] == "INPUT":
                input_rules.append(words)
            else:
                raise SystemExit(0)
    if table is not None or not filter_seen or not filter_committed or not input_seen:
        raise ValueError
    if input_rules == expected_rules:
        raise SystemExit(1)
    if prefix == "ufw6" and input_rules == disabled_ipv6:
        raise SystemExit(1)
    raise SystemExit(0)
except (ValueError, IndexError):
    raise SystemExit(2)
' "${prefix}"; then
    return 0
  else
    status=$?
    (( status == 1 )) || return 2
  fi
  return 1
}

ufw_has_unmanaged_live_rules() {
  local nft_rules status
  LC_ALL=C ufw show raw >/dev/null 2>&1 || return 2
  if ufw_iptables_family_has_unmanaged_rules iptables-save ufw; then
    return 0
  else
    status=$?
    (( status == 1 )) || return 2
  fi
  if ufw_iptables_family_has_unmanaged_rules ip6tables-save ufw6; then
    return 0
  else
    status=$?
    (( status == 1 )) || return 2
  fi
  nft_rules="$(nft -j list ruleset 2>/dev/null)" || return 2
  if printf '%s' "${nft_rules}" | "${PYTHON_BIN}" -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (TypeError, ValueError):
    raise SystemExit(2)
if not isinstance(payload, dict) or not isinstance(payload.get("nftables"), list):
    raise SystemExit(2)
entries = payload["nftables"]
compat_tables = {("ip", "filter"), ("ip6", "filter")}
compat_inputs = set()
foreign_inbound = set()
for entry in entries:
    chain = entry.get("chain") if isinstance(entry, dict) else None
    if not isinstance(chain, dict) or chain.get("hook") not in {
        "ingress", "prerouting", "input"
    }:
        continue
    key = (chain.get("family"), chain.get("table"), chain.get("name"))
    if not all(isinstance(value, str) and value for value in key):
        raise SystemExit(2)
    if (key[0], key[1]) in compat_tables and key[2] in {"INPUT", "PREROUTING"}:
        if key[2] == "INPUT":
            compat_inputs.add((key[0], key[1]))
        continue
    foreign_inbound.add(key)
    if chain.get("policy", "accept") != "accept":
        raise SystemExit(0)
if ("ip", "filter") not in compat_inputs:
    raise SystemExit(2)
for entry in entries:
    rule = entry.get("rule") if isinstance(entry, dict) else None
    if not isinstance(rule, dict):
        continue
    key = (rule.get("family"), rule.get("table"), rule.get("chain"))
    if key in foreign_inbound:
        raise SystemExit(0)
raise SystemExit(1)
'; then
    return 0
  else
    status=$?
    (( status == 1 )) || return 2
  fi
  return 1
}

ufw_listeners_are_allowed() {
  local report="$1"
  awk -v wanted_rules="${FIREWALL_RULES[*]}" '
    function finish_listener() {
      if (tracking) {
        listener_seen[current_rule] = 1
        if (!broad_allow || blocked_before_allow) unsafe = 1
      }
      tracking = 0
      broad_allow = 0
      blocked_before_allow = 0
    }
    BEGIN {
      count = split(wanted_rules, rules, " ")
      for (i = 1; i <= count; i += 1) wanted[rules[i]] = 1
    }
    /^(tcp|tcp6|udp|udp6):$/ {
      finish_listener()
      section = $0
      sub(/6?:$/, "", section)
      next
    }
    /^[[:space:]]*[0-9]+[[:space:]]/ {
      finish_listener()
      port = $1
      rule = port "/" section
      tracking = (rule in wanted)
      current_rule = rule
      next
    }
    tracking && /^[[:space:]]*\[[^]]+\][[:space:]]/ {
      lowered = tolower($0)
      if (!broad_allow && lowered ~ /(^|[[:space:]])(deny|reject|limit)([[:space:]]|$)/) {
        blocked_before_allow = 1
      }
      if (lowered ~ "(^|[[:space:]])allow[[:space:]]+" current_rule "([[:space:]]|$)") {
        broad_allow = 1
      }
      next
    }
    END {
      finish_listener()
      for (rule in wanted) if (!(rule in listener_seen)) unsafe = 1
      exit(unsafe ? 1 : 0)
    }
  ' <<< "${report}"
}

firewalld_zone_has_complex_rules() {
  local rich_rules scope="$1" zone="$2"
  local options=(--zone="${zone}")
  [[ "${scope}" != "permanent" ]] || options=(--permanent --zone="${zone}")
  rich_rules="$(firewall-cmd "${options[@]}" --list-rich-rules 2>/dev/null)" || return 2
  [[ -z "${rich_rules}" ]] || return 0
  return 1
}

firewalld_option_supported() {
  grep -Fq -- "$1" <<< "${FIREWALLD_HELP}"
}

read_firewalld_backend() {
  local output
  command -v busctl >/dev/null 2>&1 || return 2
  output="$(busctl --system get-property \
    org.fedoraproject.FirewallD1 \
    /org/fedoraproject/FirewallD1/config \
    org.fedoraproject.FirewallD1.config \
    FirewallBackend 2>/dev/null)" || return 2
  case "${output}" in
    's "nftables"') printf 'nftables\n' ;;
    's "iptables"') printf 'iptables\n' ;;
    *) return 2 ;;
  esac
}

firewalld_policy_has_blocking_rich_rules() {
  local rich_rules="$1" status
  if printf '%s\n' "${rich_rules}" | "${PYTHON_BIN}" -c '
import shlex
import sys

for raw_line in sys.stdin:
    if not raw_line.strip():
        continue
    try:
        words = shlex.split(raw_line, comments=False, posix=True)
    except ValueError:
        raise SystemExit(2)
    actions = set(words) & {"accept", "drop", "reject", "mark"}
    if actions & {"drop", "reject", "mark"}:
        raise SystemExit(0)
    if "accept" in actions:
        continue
    if not (set(words) & {"log", "nflog", "audit"}):
        raise SystemExit(2)
raise SystemExit(1)
'; then
    return 0
  else
    status=$?
    (( status == 1 )) || return 2
  fi
  return 1
}

firewalld_has_unmanaged_legacy_ingress() {
  local command_name rules status
  for command_name in iptables-save ip6tables-save; do
    rules="$("${command_name}" 2>/dev/null)" || return 2
    [[ -n "${rules}" ]] || continue
    if printf '%s\n' "${rules}" | "${PYTHON_BIN}" -c '
import shlex
import sys

table = None
table_seen = False
reachable_direct = set()
direct_rules = set()
try:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        words = shlex.split(line, comments=False, posix=True)
        if line.startswith("*"):
            if table is not None or len(words) != 1:
                raise ValueError
            table = line[1:]
            table_seen = True
            continue
        if line == "COMMIT":
            if table is None:
                raise ValueError
            table = None
            continue
        if table is None or not words:
            raise ValueError
        if words[0].startswith(":"):
            if len(words) < 2:
                raise ValueError
            chain = words[0][1:]
            if chain in {"INPUT", "PREROUTING"} and words[1] != "ACCEPT":
                raise SystemExit(0)
            continue
        if words[0] == "-P":
            if len(words) != 3:
                raise ValueError
            if words[1] in {"INPUT", "PREROUTING"} and words[2] != "ACCEPT":
                raise SystemExit(0)
            continue
        if words[0] != "-A" or len(words) < 3:
            raise ValueError
        chain = words[1]
        if chain in {"INPUT", "PREROUTING"}:
            if len(words) == 4 and words[2] == "-j" and words[3] == f"{chain}_direct":
                reachable_direct.add(words[3])
            else:
                raise SystemExit(0)
        elif chain.endswith("_direct"):
            direct_rules.add(chain)
    if table is not None or not table_seen:
        raise ValueError
    if reachable_direct & direct_rules:
        raise SystemExit(0)
    raise SystemExit(1)
except (ValueError, IndexError):
    raise SystemExit(2)
'; then
      return 0
    else
      status=$?
      (( status == 1 )) || return 2
    fi
  done
  return 1
}

firewalld_has_global_conflicts() {
  local backend direct_state egress_zones ingress_zones options policy policies
  local query_status rich_rules scope target zone_name
  FIREWALLD_HELP="$(LC_ALL=C firewall-cmd --help 2>/dev/null)" || return 2
  [[ -n "${FIREWALLD_HELP}" ]] || return 2

  backend="$(read_firewalld_backend)" || return 2
  [[ "${backend}" == "nftables" ]] || return 0

  if firewalld_option_supported --query-panic; then
    if firewall-cmd --quiet --query-panic; then
      return 0
    else
      query_status=$?
      (( query_status == 1 )) || return 2
    fi
  fi

  if firewalld_option_supported --direct; then
    for direct_state in --get-all-chains --get-all-rules --get-all-passthroughs; do
      firewalld_option_supported "${direct_state}" || return 2
    done
    for scope in runtime permanent; do
      options=(firewall-cmd --direct)
      [[ "${scope}" != "permanent" ]] || options=(firewall-cmd --permanent --direct)
      for direct_state in --get-all-chains --get-all-rules --get-all-passthroughs; do
        direct_state="$("${options[@]}" "${direct_state}" 2>/dev/null)" || return 2
        [[ -z "${direct_state}" ]] || return 0
      done
    done
  fi

  if firewalld_option_supported --get-policies; then
    for scope in runtime permanent; do
      options=(firewall-cmd)
      [[ "${scope}" != "permanent" ]] || options=(firewall-cmd --permanent)
      policies="$("${options[@]}" --get-policies 2>/dev/null)" || return 2
      for policy in ${policies}; do
        [[ "${policy}" =~ ^[A-Za-z0-9_.-]+$ ]] || return 2
        if firewalld_option_supported --query-disable; then
          if "${options[@]}" --policy="${policy}" --query-disable \
            >/dev/null 2>&1; then
            continue
          else
            query_status=$?
            (( query_status == 1 )) || return 2
          fi
        fi
        ingress_zones="$("${options[@]}" --policy="${policy}" \
          --list-ingress-zones 2>/dev/null)" || return 2
        egress_zones="$("${options[@]}" --policy="${policy}" \
          --list-egress-zones 2>/dev/null)" || return 2
        for zone_name in ${ingress_zones} ${egress_zones}; do
          [[ "${zone_name}" =~ ^[A-Za-z0-9_.-]+$ ]] || return 2
        done
        [[ " ${egress_zones} " == *" HOST "* ]] || continue
        target="$(firewall-cmd --permanent --policy="${policy}" \
          --get-target 2>/dev/null)" || return 2
        case "${target}" in
          DROP|REJECT) return 0 ;;
          CONTINUE|ACCEPT) ;;
          *) return 2 ;;
        esac
        rich_rules="$("${options[@]}" --policy="${policy}" \
          --list-rich-rules 2>/dev/null)" || return 2
        if firewalld_policy_has_blocking_rich_rules "${rich_rules}"; then
          return 0
        else
          query_status=$?
          (( query_status == 1 )) || return 2
        fi
      done
    done
  fi

  if firewalld_has_unmanaged_nft_ingress; then
    return 0
  else
    query_status=$?
    (( query_status == 1 )) || return 2
  fi
  if firewalld_has_unmanaged_legacy_ingress; then
    return 0
  else
    query_status=$?
    (( query_status == 1 )) || return 2
  fi
  return 1
}

firewalld_has_unmanaged_nft_ingress() {
  local nft_rules status
  nft_rules="$(nft -j list ruleset 2>/dev/null)" || return 2
  if printf '%s' "${nft_rules}" | "${PYTHON_BIN}" -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (TypeError, ValueError):
    raise SystemExit(2)
if not isinstance(payload, dict) or not isinstance(payload.get("nftables"), list):
    raise SystemExit(2)
entries = payload["nftables"]
firewalld_table = False
inbound = set()
for entry in entries:
    table = entry.get("table") if isinstance(entry, dict) else None
    if isinstance(table, dict) and table.get("name") == "firewalld":
        firewalld_table = True
    chain = entry.get("chain") if isinstance(entry, dict) else None
    if not isinstance(chain, dict) or chain.get("hook") not in {
        "ingress", "prerouting", "input"
    }:
        continue
    key = (chain.get("family"), chain.get("table"), chain.get("name"))
    if not all(isinstance(value, str) and value for value in key):
        raise SystemExit(2)
    if chain.get("table") == "firewalld":
        continue
    inbound.add(key)
    if chain.get("policy", "accept") != "accept":
        raise SystemExit(0)
if not firewalld_table:
    raise SystemExit(2)
for entry in entries:
    rule = entry.get("rule") if isinstance(entry, dict) else None
    if not isinstance(rule, dict):
        continue
    key = (rule.get("family"), rule.get("table"), rule.get("chain"))
    if key in inbound:
        raise SystemExit(0)
raise SystemExit(1)
'; then
    return 0
  else
    status=$?
    (( status == 1 )) || return 2
  fi
  return 1
}

read_firewalld_zones() {
  local active_zones default_zone
  active_zones="$(firewall-cmd --get-active-zones 2>/dev/null)" || return 2
  default_zone="$(firewall-cmd --get-default-zone 2>/dev/null)" || return 2
  {
    awk '/^[^[:space:]]/ {print $1}' <<< "${active_zones}"
    printf '%s\n' "${default_zone}"
  } | awk 'NF && !seen[$0]++'
}

read_ufw_state() {
  local output
  if ! output="$(LC_ALL=C ufw status 2>/dev/null)"; then
    return 2
  fi
  if grep -q '^Status: active$' <<< "${output}"; then
    printf 'active\n'
    return 0
  fi
  if grep -q '^Status: inactive$' <<< "${output}"; then
    printf 'inactive\n'
    return 1
  fi
  return 2
}

read_firewalld_state() {
  local output status
  if output="$(LC_ALL=C firewall-cmd --state 2>&1)"; then
    [[ "${output}" == "running" ]] || return 2
    printf 'running\n'
    return 0
  else
    status=$?
  fi
  if [[ "${output}" == "not running" ]]; then
    printf 'not running\n'
    return 1
  fi
  (( status == 0 )) || return 2
  return 2
}

has_unmanaged_firewall_restrictions() {
  local nft_rules rules command_name status
  nft_rules="$(nft -j list ruleset 2>/dev/null)" || return 2
  if printf '%s' "${nft_rules}" | "${PYTHON_BIN}" -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (TypeError, ValueError):
    raise SystemExit(2)
if not isinstance(payload, dict):
    raise SystemExit(2)
entries = payload.get("nftables")
if not isinstance(entries, list):
    raise SystemExit(2)
inbound_chains = set()
for entry in entries:
    chain = entry.get("chain") if isinstance(entry, dict) else None
    if not isinstance(chain, dict) or chain.get("hook") not in {
        "ingress", "prerouting", "input"
    }:
        continue
    key = (chain.get("family"), chain.get("table"), chain.get("name"))
    if not all(isinstance(value, str) and value for value in key):
        raise SystemExit(2)
    inbound_chains.add(key)
    if chain.get("policy", "accept") != "accept":
        raise SystemExit(0)
for entry in entries:
    rule = entry.get("rule") if isinstance(entry, dict) else None
    if not isinstance(rule, dict):
        continue
    key = (rule.get("family"), rule.get("table"), rule.get("chain"))
    if not all(isinstance(value, str) and value for value in key):
        raise SystemExit(2)
    if key in inbound_chains:
        raise SystemExit(0)
raise SystemExit(1)
'; then
    return 0
  else
    status=$?
    (( status == 1 )) || return 2
  fi

  for command_name in iptables-save ip6tables-save; do
    rules="$("${command_name}" 2>/dev/null)" || return 2
    [[ -n "${rules}" ]] || continue
    if awk '
      $0 == "*filter" { in_filter = 1; found_filter = 1; next }
      /^\*/ { in_filter = 0; next }
      $1 == ":INPUT" || $1 == ":PREROUTING" {
        if (NF < 3) invalid = 1
        if (in_filter && $1 == ":INPUT") found_filter_input = 1
        if ($2 != "ACCEPT") restricted = 1
      }
      $1 == "-P" && ($2 == "INPUT" || $2 == "PREROUTING") {
        if (NF < 3) invalid = 1
        if ($3 != "ACCEPT") restricted = 1
      }
      $1 == "-A" && ($2 == "INPUT" || $2 == "PREROUTING") { restricted = 1 }
      in_filter && $1 == ":INPUT" {
        found_filter_input = 1
      }
      in_filter && $1 == "COMMIT" { committed_filter = 1; in_filter = 0 }
      END {
        if (invalid || !found_filter || !found_filter_input || !committed_filter) exit 2
        exit(restricted ? 0 : 1)
      }
    ' <<< "${rules}"; then
      return 0
    else
      status=$?
      (( status == 1 )) || return 2
    fi
  done
  return 1
}

prepare_firewall() {
  local firewalld_active=0 query_status rule status ufw_active=0 zone zones
  PANEL_SCHEME="${PANEL_SCHEME:-http}"
  FIREWALL_RULES=("${HYSTERIA_PORT}/tcp" "${HYSTERIA_PORT}/udp" "${PANEL_PORT}/tcp")
  [[ "${PANEL_SCHEME}" != "https" ]] || FIREWALL_RULES+=("80/tcp")
  (( UDP_443_ENABLED == 0 )) || FIREWALL_RULES+=("443/tcp" "443/udp")
  FIREWALL_ZONES=()
  FIREWALL_PENDING=()
  FIREWALL_APPLIED=()

  if command -v ufw >/dev/null 2>&1; then
    if read_ufw_state >/dev/null; then
      ufw_active=1
    else
      status=$?
      (( status == 1 )) || fail "无法查询 UFW 状态；未修改防火墙"
    fi
  fi
  if command -v firewall-cmd >/dev/null 2>&1; then
    if read_firewalld_state >/dev/null; then
      firewalld_active=1
    else
      status=$?
      (( status == 1 )) || fail "无法查询 firewalld 状态；未修改防火墙"
    fi
  fi
  if (( ufw_active == 1 && firewalld_active == 1 )); then
    fail "UFW 与 firewalld 同时启用，防火墙所有权不明确；请只保留一个管理器后重试"
  fi

  if (( ufw_active == 1 )); then
    if ufw_has_framework_customization; then
      fail "UFW framework 文件或 init hook 已自定义，无法证明普通 allow 不会被提前阻断；未修改防火墙"
    else
      status=$?
      (( status == 1 )) \
        || fail "无法核验 UFW framework 文件；未修改防火墙"
    fi
    if ufw_has_unmanaged_live_rules; then
      fail "UFW 之外存在可能提前阻断入站的实时 netfilter 规则；未修改防火墙"
    else
      status=$?
      (( status == 1 )) \
        || fail "无法完整核验 UFW 实时 netfilter 规则；未修改防火墙"
    fi
    UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" \
      || fail "无法读取 UFW 已配置规则；未修改防火墙"
    FIREWALL_MANAGER="ufw"
    for rule in "${FIREWALL_RULES[@]}"; do
      if ufw_rule_is_denied "${rule}"; then
        fail "UFW 已存在拒绝 ${rule} 的规则；未修改防火墙"
      else
        query_status=$?
        (( query_status == 1 )) \
          || fail "无法解析 UFW 已配置规则；未修改防火墙"
      fi
      ufw_rule_is_recorded "${rule}" || FIREWALL_PENDING+=("${rule}")
    done
    return 0
  fi

  if (( firewalld_active == 1 )); then
    if firewalld_has_global_conflicts; then
      fail "firewalld 存在 panic、direct、passthrough 或可能阻断入站的 policy；未修改防火墙"
    else
      query_status=$?
      (( query_status == 1 )) \
        || fail "无法完整读取 firewalld 全局策略；未修改防火墙"
    fi
    zones="$(read_firewalld_zones)" \
      || fail "无法读取 firewalld 活跃或默认区域；未修改防火墙"
    [[ -n "${zones}" ]] || fail "无法确定 firewalld 区域；未修改防火墙"
    while IFS= read -r zone; do
      [[ -n "${zone}" ]] || continue
      [[ "${zone}" =~ ^[A-Za-z0-9_.-]+$ ]] \
        || fail "firewalld 返回了无效区域名称；未修改防火墙"
      FIREWALL_ZONES+=("${zone}")
      for scope in runtime permanent; do
        if firewalld_zone_has_complex_rules "${scope}" "${zone}"; then
          fail "firewalld ${zone} 区域存在 rich rule，无法证明普通端口规则一定生效；未修改防火墙"
        else
          query_status=$?
          (( query_status == 1 )) \
            || fail "无法读取 firewalld ${zone} 区域的 rich rules；未修改防火墙"
        fi
      done
      for rule in "${FIREWALL_RULES[@]}"; do
        if firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
          :
        else
          query_status=$?
          (( query_status == 1 )) \
            || fail "无法查询 firewalld ${zone} 区域的即时规则；未修改防火墙"
          FIREWALL_PENDING+=("runtime|${zone}|${rule}")
        fi
        if firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"; then
          :
        else
          query_status=$?
          (( query_status == 1 )) \
            || fail "无法查询 firewalld ${zone} 区域的永久规则；未修改防火墙"
          FIREWALL_PENDING+=("permanent|${zone}|${rule}")
        fi
      done
    done <<< "${zones}"
    (( ${#FIREWALL_ZONES[@]} > 0 )) || fail "firewalld 没有可用区域；未修改防火墙"
    FIREWALL_MANAGER="firewalld"
    return 0
  fi

  if has_unmanaged_firewall_restrictions; then
    fail "检测到未受支持的自定义 nftables/iptables/ip6tables 入站策略；为避免破坏现有安全策略，未自动改写，请改用 UFW 或 firewalld 管理规则"
  else
    status=$?
    (( status == 1 )) \
      || fail "无法完整检查 nftables/iptables/ip6tables；为避免误判为无防火墙，安装已停止"
  fi
  FIREWALL_MANAGER="none"
}

firewall_entry_is_valid() {
  local entry="$1" manager rule zone
  IFS='|' read -r manager zone rule <<< "${entry}"
  [[ "${rule}" =~ ^([1-9][0-9]{0,4})/(tcp|udp)$ ]] || return 1
  (( BASH_REMATCH[1] <= 65535 )) || return 1
  case "${manager}" in
    ufw) [[ -z "${zone}" ]] ;;
    runtime|permanent) [[ "${zone}" =~ ^[A-Za-z0-9_.-]+$ ]] ;;
    *) return 1 ;;
  esac
}

firewall_array_contains() {
  local wanted="$1" entry
  shift
  for entry in "$@"; do
    [[ "${entry}" != "${wanted}" ]] || return 0
  done
  return 1
}

write_firewall_lines_durably() {
  local destination="$1" stage
  shift
  stage="$(mktemp)" || return 1
  if (( $# > 0 )); then
    printf '%s\n' "$@" > "${stage}" || { rm -f -- "${stage}"; return 1; }
  else
    : > "${stage}"
  fi
  if ! durable_replace_file "${stage}" "${destination}" 0600; then
    rm -f -- "${stage}" >/dev/null 2>&1 || true
    return 1
  fi
  rm -f -- "${stage}"
}

load_managed_firewall_state() {
  local entry hardlinks metadata
  FIREWALL_OWNED=()
  [[ -e "${MANAGED_FIREWALL_STATE_FILE}" || -L "${MANAGED_FIREWALL_STATE_FILE}" ]] \
    || return 0
  [[ ! -L "${MANAGED_FIREWALL_STATE_FILE}" && -f "${MANAGED_FIREWALL_STATE_FILE}" ]] \
    || return 1
  if (( EUID == 0 )); then
    metadata="$(stat -c '%u:%g:%a' "${MANAGED_FIREWALL_STATE_FILE}")" || return 1
    hardlinks="$(stat -c '%h' "${MANAGED_FIREWALL_STATE_FILE}")" || return 1
    [[ "${metadata}" == "0:0:600" && "${hardlinks}" == "1" ]] || return 1
  fi
  while IFS= read -r entry || [[ -n "${entry}" ]]; do
    [[ -n "${entry}" ]] || return 1
    firewall_entry_is_valid "${entry}" || return 1
    if (( ${#FIREWALL_OWNED[@]} > 0 )) && \
      firewall_array_contains "${entry}" "${FIREWALL_OWNED[@]}"; then
      return 1
    fi
    FIREWALL_OWNED+=("${entry}")
  done < "${MANAGED_FIREWALL_STATE_FILE}"
}

persist_firewall_transaction() {
  write_firewall_lines_durably \
    "${FIREWALL_TRANSACTION_FILE}" "${FIREWALL_TRANSACTION_LINES[@]}"
}

begin_firewall_transaction() {
  local entry
  # The project maintenance lock serializes installer/panel changes. Root operators
  # must pause independent UFW/firewalld automation while this transaction runs.
  load_managed_firewall_state \
    || fail "项目防火墙所有权记录无效；为避免删除未知规则，安装已停止"
  FIREWALL_TRANSACTION_LINES=("${FIREWALL_TRANSACTION_MAGIC}")
  FIREWALL_NEWLY_OWNED=()
  if (( ${#FIREWALL_OWNED[@]} > 0 )); then
    for entry in "${FIREWALL_OWNED[@]}"; do
      FIREWALL_TRANSACTION_LINES+=("old|${entry}")
    done
  fi
  persist_firewall_transaction \
    || fail "无法持久化防火墙事务；未修改规则"
}

record_firewall_transaction_operation() {
  local operation="$1" entry="$2"
  [[ "${operation}" == "add" || "${operation}" == "remove" ]] || return 1
  firewall_entry_is_valid "${entry}" || return 1
  FIREWALL_TRANSACTION_LINES+=("${operation}|${entry}")
  persist_firewall_transaction
}

add_managed_firewall_entry() {
  local entry="$1" manager query_status rule zone
  IFS='|' read -r manager zone rule <<< "${entry}"
  case "${manager}" in
    ufw)
      UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" || return 1
      ufw_rule_is_recorded "${rule}" && return 0
      ufw allow "${rule}" >/dev/null || return 1
      UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" || return 1
      ufw_rule_is_recorded "${rule}"
      ;;
    runtime)
      if firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
        return 0
      else
        query_status=$?
        (( query_status == 1 )) || return 1
      fi
      firewall-cmd --quiet --zone="${zone}" --add-port="${rule}" || return 1
      firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"
      ;;
    permanent)
      if firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"; then
        return 0
      else
        query_status=$?
        (( query_status == 1 )) || return 1
      fi
      firewall-cmd --quiet --permanent --zone="${zone}" --add-port="${rule}" || return 1
      firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"
      ;;
  esac
}

remove_managed_firewall_entry() {
  local entry="$1" manager query_status rule zone
  IFS='|' read -r manager zone rule <<< "${entry}"
  case "${manager}" in
    ufw)
      UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" || return 1
      ufw_rule_is_recorded "${rule}" || return 0
      ufw --force delete allow "${rule}" >/dev/null || return 1
      UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" || return 1
      ! ufw_rule_is_recorded "${rule}"
      ;;
    runtime)
      if ! firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
        query_status=$?
        (( query_status == 1 )) && return 0
        return 1
      fi
      firewall-cmd --quiet --zone="${zone}" --remove-port="${rule}" || return 1
      if firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
        return 1
      else
        query_status=$?
        (( query_status == 1 ))
      fi
      ;;
    permanent)
      if ! firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"; then
        query_status=$?
        (( query_status == 1 )) && return 0
        return 1
      fi
      firewall-cmd --quiet --permanent --zone="${zone}" --remove-port="${rule}" || return 1
      if firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"; then
        return 1
      else
        query_status=$?
        (( query_status == 1 ))
      fi
      ;;
  esac
}

force_remove_managed_firewall_entry() {
  local entry="$1" manager query_status rule zone
  IFS='|' read -r manager zone rule <<< "${entry}"
  case "${manager}" in
    ufw)
      ufw --force delete allow "${rule}" >/dev/null 2>&1 || true
      UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" || return 1
      ! ufw_rule_is_recorded "${rule}"
      ;;
    runtime)
      firewall-cmd --quiet --zone="${zone}" --remove-port="${rule}" \
        >/dev/null 2>&1 || true
      if firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
        return 1
      else
        query_status=$?
        (( query_status == 1 ))
      fi
      ;;
    permanent)
      firewall-cmd --quiet --permanent --zone="${zone}" --remove-port="${rule}" \
        >/dev/null 2>&1 || true
      if firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"; then
        return 1
      else
        query_status=$?
        (( query_status == 1 ))
      fi
      ;;
  esac
}

force_add_managed_firewall_entry() {
  local entry="$1" manager rule zone
  IFS='|' read -r manager zone rule <<< "${entry}"
  case "${manager}" in
    ufw)
      ufw allow "${rule}" >/dev/null 2>&1 || true
      UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" || return 1
      ufw_rule_is_recorded "${rule}"
      ;;
    runtime)
      firewall-cmd --quiet --zone="${zone}" --add-port="${rule}" \
        >/dev/null 2>&1 || true
      firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"
      ;;
    permanent)
      firewall-cmd --quiet --permanent --zone="${zone}" --add-port="${rule}" \
        >/dev/null 2>&1 || true
      firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"
      ;;
  esac
}

read_firewall_transaction() {
  local hardlinks line metadata operation payload
  local -a lines=()
  [[ ! -L "${FIREWALL_TRANSACTION_FILE}" && -f "${FIREWALL_TRANSACTION_FILE}" ]] \
    || return 1
  if (( EUID == 0 )); then
    metadata="$(stat -c '%u:%g:%a' "${FIREWALL_TRANSACTION_FILE}")" || return 1
    hardlinks="$(stat -c '%h' "${FIREWALL_TRANSACTION_FILE}")" || return 1
    [[ "${metadata}" == "0:0:600" && "${hardlinks}" == "1" ]] || return 1
  fi
  while IFS= read -r line || [[ -n "${line}" ]]; do
    lines+=("${line}")
  done < "${FIREWALL_TRANSACTION_FILE}"
  [[ ${#lines[@]} -ge 1 && "${lines[0]}" == "${FIREWALL_TRANSACTION_MAGIC}" ]] \
    || return 1
  for line in "${lines[@]:1}"; do
    operation="${line%%|*}"
    payload="${line#*|}"
    [[ "${operation}" == "old" || "${operation}" == "add" || \
      "${operation}" == "remove" ]] || return 1
    firewall_entry_is_valid "${payload}" || return 1
  done
  FIREWALL_TRANSACTION_LINES=("${lines[@]}")
}

rollback_persisted_firewall_transaction() {
  local entry index line operation rollback_failed=0
  local -a old_state=()
  [[ -e "${FIREWALL_TRANSACTION_FILE}" || -L "${FIREWALL_TRANSACTION_FILE}" ]] \
    || return 0
  read_firewall_transaction || return 1
  for line in "${FIREWALL_TRANSACTION_LINES[@]:1}"; do
    operation="${line%%|*}"
    entry="${line#*|}"
    [[ "${operation}" != "old" ]] || old_state+=("${entry}")
  done
  for (( index=${#FIREWALL_TRANSACTION_LINES[@]}-1; index>=1; index-- )); do
    line="${FIREWALL_TRANSACTION_LINES[index]}"
    operation="${line%%|*}"
    entry="${line#*|}"
    case "${operation}" in
      add) force_remove_managed_firewall_entry "${entry}" || rollback_failed=1 ;;
      remove) force_add_managed_firewall_entry "${entry}" || rollback_failed=1 ;;
    esac
  done
  (( rollback_failed == 0 )) || return 1
  if (( ${#old_state[@]} > 0 )); then
    write_firewall_lines_durably "${MANAGED_FIREWALL_STATE_FILE}" "${old_state[@]}" \
      || return 1
  else
    durable_remove_file "${MANAGED_FIREWALL_STATE_FILE}" || return 1
  fi
  durable_remove_file "${FIREWALL_TRANSACTION_FILE}" || return 1
  FIREWALL_TRANSACTION_LINES=()
  if (( ${#old_state[@]} > 0 )); then
    FIREWALL_OWNED=("${old_state[@]}")
  else
    FIREWALL_OWNED=()
  fi
  FIREWALL_APPLIED=()
}

desired_managed_firewall_entries() {
  local rule zone
  case "${FIREWALL_MANAGER}" in
    ufw)
      for rule in "${FIREWALL_RULES[@]}"; do printf 'ufw||%s\n' "${rule}"; done
      ;;
    firewalld)
      for zone in "${FIREWALL_ZONES[@]}"; do
        for rule in "${FIREWALL_RULES[@]}"; do
          printf 'runtime|%s|%s\npermanent|%s|%s\n' "${zone}" "${rule}" "${zone}" "${rule}"
        done
      done
      ;;
  esac
}

remove_obsolete_managed_firewall_rules() {
  local entry
  local -a desired_entries=() next_state=()
  while IFS= read -r entry || [[ -n "${entry}" ]]; do
    [[ -n "${entry}" ]] || continue
    desired_entries+=("${entry}")
  done < <(desired_managed_firewall_entries)
  if (( ${#FIREWALL_OWNED[@]} > 0 )); then
    for entry in "${FIREWALL_OWNED[@]}"; do
      if firewall_array_contains "${entry}" "${desired_entries[@]}"; then
        next_state+=("${entry}")
        continue
      fi
      record_firewall_transaction_operation remove "${entry}" \
        || firewall_change_failed "无法持久记录待删除的项目防火墙规则"
      remove_managed_firewall_entry "${entry}" \
        || firewall_change_failed "无法删除项目拥有的旧防火墙规则 ${entry}"
    done
  fi
  if (( ${#FIREWALL_NEWLY_OWNED[@]} > 0 )); then
    for entry in "${FIREWALL_NEWLY_OWNED[@]}"; do
      if (( ${#next_state[@]} == 0 )) || \
        ! firewall_array_contains "${entry}" "${next_state[@]}"; then
        next_state+=("${entry}")
      fi
    done
  fi
  if (( ${#next_state[@]} > 0 )); then
    write_firewall_lines_durably "${MANAGED_FIREWALL_STATE_FILE}" "${next_state[@]}" \
      || firewall_change_failed "无法持久化项目防火墙所有权"
  else
    durable_remove_file "${MANAGED_FIREWALL_STATE_FILE}" \
      || firewall_change_failed "无法清除空的项目防火墙所有权记录"
  fi
  if (( ${#next_state[@]} > 0 )); then
    FIREWALL_OWNED=("${next_state[@]}")
  else
    FIREWALL_OWNED=()
  fi
}

finalize_firewall_transaction() {
  [[ -e "${FIREWALL_TRANSACTION_FILE}" || -L "${FIREWALL_TRANSACTION_FILE}" ]] \
    || return 0
  read_firewall_transaction || return 1
  durable_remove_file "${FIREWALL_TRANSACTION_FILE}" || return 1
  FIREWALL_TRANSACTION_LINES=()
  FIREWALL_APPLIED=()
}

settle_committed_firewall_transaction() {
  [[ -e "${FIREWALL_TRANSACTION_FILE}" || -L "${FIREWALL_TRANSACTION_FILE}" ]] \
    || return 0
  if [[ -e "${FRESH_IN_PROGRESS_MARKER}" || -L "${FRESH_IN_PROGRESS_MARKER}" || \
    -e "${LEGACY_FRESH_IN_PROGRESS_MARKER}" || -L "${LEGACY_FRESH_IN_PROGRESS_MARKER}" || \
    -e "${UPGRADE_ACTIVE_MARKER}" || -L "${UPGRADE_ACTIVE_MARKER}" ]]; then
    return 0
  fi
  [[ ! -L "${MANAGED_MARKER}" && -f "${MANAGED_MARKER}" && ! -s "${MANAGED_MARKER}" && \
    "$(stat -c '%u:%g:%a:%h' "${MANAGED_MARKER}")" == "0:0:644:1" ]] \
    || fail "发现没有已提交安装标记的防火墙事务；为避免误删规则，安装已停止"
  finalize_firewall_transaction \
    || fail "无法收口已提交的防火墙事务；安装已停止"
}

rollback_firewall_changes() {
  local entry index manager query_status rule rollback_failed=0 zone
  if [[ ! -e "${FIREWALL_TRANSACTION_FILE}" && \
    ! -L "${FIREWALL_TRANSACTION_FILE}" && \
    ${#FIREWALL_TRANSACTION_LINES[@]} -gt 0 ]]; then
    [[ "${FIREWALL_TRANSACTION_LINES[0]}" == "${FIREWALL_TRANSACTION_MAGIC}" ]] \
      || return 1
    persist_firewall_transaction || return 1
  fi
  if [[ -e "${FIREWALL_TRANSACTION_FILE}" || -L "${FIREWALL_TRANSACTION_FILE}" ]]; then
    rollback_persisted_firewall_transaction
    return $?
  fi
  for (( index=${#FIREWALL_APPLIED[@]}-1; index>=0; index-- )); do
    entry="${FIREWALL_APPLIED[index]}"
    IFS='|' read -r manager zone rule <<< "${entry}"
    case "${manager}" in
      ufw)
        ufw --force delete allow "${rule}" >/dev/null 2>&1 || true
        if UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)"; then
          ufw_rule_is_recorded "${rule}" && rollback_failed=1
        else
          rollback_failed=1
        fi
        ;;
      runtime)
        firewall-cmd --quiet --zone="${zone}" --remove-port="${rule}" \
          >/dev/null 2>&1 || true
        if firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
          rollback_failed=1
        else
          query_status=$?
          (( query_status == 1 )) || rollback_failed=1
        fi
        ;;
      permanent)
        firewall-cmd --quiet --permanent --zone="${zone}" --remove-port="${rule}" \
          >/dev/null 2>&1 || true
        if firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"; then
          rollback_failed=1
        else
          query_status=$?
          (( query_status == 1 )) || rollback_failed=1
        fi
        ;;
    esac
  done
  FIREWALL_APPLIED=()
  return "${rollback_failed}"
}

firewall_change_failed() {
  local message="$1"
  if ! rollback_firewall_changes; then
    message+="；本次新增规则未能全部自动撤销，请立即检查主机防火墙"
  fi
  fail "${message}"
}

configure_firewall() {
  local entry final_zones owned_manager preflight_manager query_status rule scope status
  local ufw_listening_report zone
  preflight_manager="${FIREWALL_MANAGER}"
  prepare_firewall
  if [[ "${preflight_manager}" != "unprepared" && \
    "${preflight_manager}" != "${FIREWALL_MANAGER}" ]]; then
    fail "防火墙管理器在安装期间发生变化；未修改规则，请重试"
  fi
  load_managed_firewall_state \
    || fail "项目防火墙所有权记录无效；为避免删除未知规则，安装已停止"
  if (( ${#FIREWALL_OWNED[@]} > 0 )); then
    for entry in "${FIREWALL_OWNED[@]}"; do
      owned_manager="${entry%%|*}"
      if [[ "${owned_manager}" == "ufw" && "${FIREWALL_MANAGER}" != "ufw" ]] || \
        [[ "${owned_manager}" != "ufw" && "${FIREWALL_MANAGER}" != "firewalld" ]]; then
        fail "防火墙管理器与项目所有权记录不一致；未修改规则"
      fi
    done
  fi
  [[ "${FIREWALL_MANAGER}" == "none" ]] || begin_firewall_transaction
  case "${FIREWALL_MANAGER}" in
    none)
      if has_unmanaged_firewall_restrictions; then
        fail "防火墙状态在安装期间发生变化；未修改规则，请重试"
      else
        query_status=$?
        (( query_status == 1 )) \
          || fail "安装结束时无法复查主机防火墙；未修改规则"
      fi
      FIREWALL_RESULT="未检测到正在生效的主机防火墙，未修改规则"
      echo "${FIREWALL_RESULT}"
      ;;
    ufw)
      if ! read_ufw_state >/dev/null; then
        status=$?
        (( status == 1 )) \
          && fail "UFW 状态在安装期间发生变化；未修改规则，请重试"
        fail "安装结束时无法查询 UFW 状态；未修改规则"
      fi
      if command -v firewall-cmd >/dev/null 2>&1; then
        if read_firewalld_state >/dev/null; then
          fail "安装期间 firewalld 被启用，防火墙所有权不明确；未修改规则"
        else
          status=$?
          (( status == 1 )) || fail "安装结束时无法查询 firewalld 状态；未修改规则"
        fi
      fi
      echo "检测到已启用的 UFW，正在开放服务端口"
      for rule in "${FIREWALL_PENDING[@]}"; do
        UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" \
          || firewall_change_failed "无法复查 UFW 规则"
        if ufw_rule_is_denied "${rule}"; then
          firewall_change_failed "UFW 已存在拒绝 ${rule} 的规则"
        else
          query_status=$?
          (( query_status == 1 )) \
            || firewall_change_failed "无法解析 UFW 已配置规则"
        fi
        ufw_rule_is_recorded "${rule}" && continue
        record_firewall_transaction_operation add "ufw||${rule}" \
          || firewall_change_failed "无法持久记录待添加的 UFW 规则"
        FIREWALL_APPLIED+=("ufw||${rule}")
        FIREWALL_NEWLY_OWNED+=("ufw||${rule}")
        if ! ufw allow "${rule}" >/dev/null; then
          firewall_change_failed "UFW 无法开放 ${rule}"
        fi
        UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" \
          || firewall_change_failed "无法确认 UFW 已开放 ${rule}"
        if ufw_rule_is_denied "${rule}"; then
          firewall_change_failed "UFW 在开放期间新增了拒绝 ${rule} 的规则"
        else
          query_status=$?
          (( query_status == 1 )) \
            || firewall_change_failed "无法解析开放后的 UFW 规则"
        fi
        ufw_rule_is_recorded "${rule}" \
          || firewall_change_failed "UFW 未实际开放 ${rule}"
      done
      UFW_ADDED_RULES="$(LC_ALL=C ufw show added 2>/dev/null)" \
        || firewall_change_failed "无法最终复查 UFW 规则"
      for rule in "${FIREWALL_RULES[@]}"; do
        if ufw_rule_is_denied "${rule}"; then
          firewall_change_failed "UFW 最终检查发现拒绝 ${rule} 的规则"
        else
          query_status=$?
          (( query_status == 1 )) \
            || firewall_change_failed "无法解析最终 UFW 规则"
        fi
        ufw_rule_is_recorded "${rule}" \
          || firewall_change_failed "UFW 最终检查未发现 ${rule} 的开放规则"
      done
      if ufw_has_framework_customization; then
        firewall_change_failed "UFW framework 在开放期间发生变化"
      else
        query_status=$?
        (( query_status == 1 )) \
          || firewall_change_failed "无法最终核验 UFW framework 文件"
      fi
      if ufw_has_unmanaged_live_rules; then
        firewall_change_failed "UFW 开放期间出现了未受管的实时 netfilter 规则"
      else
        query_status=$?
        (( query_status == 1 )) \
          || firewall_change_failed "无法最终核验 UFW 实时 netfilter 规则"
      fi
      ufw_listening_report="$(LC_ALL=C ufw show listening 2>/dev/null)" \
        || firewall_change_failed "无法读取 UFW 内核生效顺序"
      ufw_listeners_are_allowed "${ufw_listening_report}" \
        || firewall_change_failed "UFW 内核规则顺序无法证明目标监听端口已开放"
      ;;
    firewalld)
      if ! read_firewalld_state >/dev/null; then
        status=$?
        (( status == 1 )) \
          && fail "firewalld 状态在安装期间发生变化；未修改规则，请重试"
        fail "安装结束时无法查询 firewalld 状态；未修改规则"
      fi
      if command -v ufw >/dev/null 2>&1; then
        if read_ufw_state >/dev/null; then
          fail "安装期间 UFW 被启用，防火墙所有权不明确；未修改规则"
        else
          status=$?
          (( status == 1 )) || fail "安装结束时无法查询 UFW 状态；未修改规则"
        fi
      fi
      echo "检测到已启用的 firewalld，正在开放服务端口"
      for entry in "${FIREWALL_PENDING[@]}"; do
        IFS='|' read -r scope zone rule <<< "${entry}"
        if [[ "${scope}" == "permanent" ]]; then
          if firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"; then
            continue
          else
            query_status=$?
            (( query_status == 1 )) \
              || firewall_change_failed "无法复查 firewalld ${zone} 区域的永久规则"
          fi
          record_firewall_transaction_operation add "permanent|${zone}|${rule}" \
            || firewall_change_failed "无法持久记录待添加的 firewalld 永久规则"
          FIREWALL_APPLIED+=("permanent|${zone}|${rule}")
          FIREWALL_NEWLY_OWNED+=("permanent|${zone}|${rule}")
          if ! firewall-cmd --quiet --permanent --zone="${zone}" --add-port="${rule}"; then
            firewall_change_failed "firewalld 无法永久开放 ${zone} 区域的 ${rule}"
          fi
          if ! firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}"; then
            firewall_change_failed "firewalld 未实际永久开放 ${zone} 区域的 ${rule}"
          fi
        else
          if firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
            continue
          else
            query_status=$?
            (( query_status == 1 )) \
              || firewall_change_failed "无法复查 firewalld ${zone} 区域的即时规则"
          fi
          record_firewall_transaction_operation add "runtime|${zone}|${rule}" \
            || firewall_change_failed "无法持久记录待添加的 firewalld 即时规则"
          FIREWALL_APPLIED+=("runtime|${zone}|${rule}")
          FIREWALL_NEWLY_OWNED+=("runtime|${zone}|${rule}")
          if ! firewall-cmd --quiet --zone="${zone}" --add-port="${rule}"; then
            firewall_change_failed "firewalld 无法立即开放 ${zone} 区域的 ${rule}"
          fi
          if ! firewall-cmd --quiet --zone="${zone}" --query-port="${rule}"; then
            firewall_change_failed "firewalld 未实际立即开放 ${zone} 区域的 ${rule}"
          fi
        fi
      done
      final_zones="$(read_firewalld_zones)" \
        || firewall_change_failed "无法最终复查 firewalld 区域"
      if firewalld_has_global_conflicts; then
        firewall_change_failed "firewalld 在开放期间出现了复杂全局策略"
      else
        query_status=$?
        (( query_status == 1 )) \
          || firewall_change_failed "无法最终复查 firewalld 全局策略"
      fi
      [[ "${final_zones}" == "$(printf '%s\n' "${FIREWALL_ZONES[@]}")" ]] \
        || firewall_change_failed "firewalld 区域在开放期间发生变化"
      for zone in "${FIREWALL_ZONES[@]}"; do
        for scope in runtime permanent; do
          if firewalld_zone_has_complex_rules "${scope}" "${zone}"; then
            firewall_change_failed "firewalld ${zone} 区域在开放期间新增了 rich rule"
          else
            query_status=$?
            (( query_status == 1 )) \
              || firewall_change_failed "无法最终复查 firewalld ${zone} 区域的 rich rules"
          fi
        done
        for rule in "${FIREWALL_RULES[@]}"; do
          firewall-cmd --quiet --zone="${zone}" --query-port="${rule}" \
            || firewall_change_failed "firewalld 最终检查未发现 ${zone} 区域的即时 ${rule}"
          firewall-cmd --quiet --permanent --zone="${zone}" --query-port="${rule}" \
            || firewall_change_failed "firewalld 最终检查未发现 ${zone} 区域的永久 ${rule}"
        done
      done
      ;;
    *)
      fail "防火墙尚未完成安全预检"
      ;;
  esac
  if [[ "${FIREWALL_MANAGER}" != "none" ]]; then
    remove_obsolete_managed_firewall_rules
    FIREWALL_RESULT="已自动开放 ${HYSTERIA_PORT}/tcp、${HYSTERIA_PORT}/udp、${PANEL_PORT}/tcp"
    [[ "${PANEL_SCHEME}" != "https" ]] || FIREWALL_RESULT+=", 80/tcp"
    (( UDP_443_ENABLED == 0 )) || FIREWALL_RESULT+=", 443/tcp、443/udp"
  fi
}

ensure_sysctl_directory() {
  local sysctl_directory="${SYSCTL_FILE%/*}"
  [[ ! -L "${sysctl_directory}" ]] \
    || fail "系统 sysctl 配置目录不能是符号链接；安装已停止"
  if [[ -e "${sysctl_directory}" ]]; then
    [[ -d "${sysctl_directory}" ]] \
      || fail "系统 sysctl 配置路径不是目录；安装已停止"
    return 0
  fi
  install -d -o root -g root -m 0755 "${sysctl_directory}"
  sync -f "${sysctl_directory}" \
    || fail "无法持久创建系统 sysctl 配置目录；安装已停止"
}

optimize_network_stack() {
  local current_rmem current_wmem target_rmem target_wmem available_cc
  local original_qdisc original_cc sysctl_stage
  current_rmem="$(sysctl -n net.core.rmem_max 2>/dev/null || echo 0)"
  current_wmem="$(sysctl -n net.core.wmem_max 2>/dev/null || echo 0)"
  [[ "${current_rmem}" =~ ^[0-9]+$ ]] || current_rmem=0
  [[ "${current_wmem}" =~ ^[0-9]+$ ]] || current_wmem=0
  target_rmem="${MIN_QUIC_UDP_BUFFER}"
  target_wmem="${MIN_QUIC_UDP_BUFFER}"
  (( current_rmem <= target_rmem )) || target_rmem="${current_rmem}"
  (( current_wmem <= target_wmem )) || target_wmem="${current_wmem}"
  if [[ -f "${SYSCTL_FILE}" ]] && ! grep -q '^# Managed by Hysteria2-panel$' "${SYSCTL_FILE}"; then
    fail "${SYSCTL_FILE} 已存在且不属于本安装器，拒绝覆盖"
  fi
  sysctl_stage="${TMP_DIR}/99-hysteria2-panel.conf"
  cat > "${sysctl_stage}" <<'EOF'
# Managed by Hysteria2-panel
# Hysteria recommends 16 MiB UDP buffers for high-bandwidth QUIC transfers.
EOF
  if sysctl -w "net.core.rmem_max=${target_rmem}" >/dev/null; then
    echo "net.core.rmem_max=${target_rmem}" >> "${sysctl_stage}"
  else
    (( current_rmem <= 0 )) || echo "net.core.rmem_max=${current_rmem}" >> "${sysctl_stage}"
    echo "警告：内核拒绝提高 UDP 接收缓冲，保留原值" >&2
  fi
  if sysctl -w "net.core.wmem_max=${target_wmem}" >/dev/null; then
    echo "net.core.wmem_max=${target_wmem}" >> "${sysctl_stage}"
  else
    (( current_wmem <= 0 )) || echo "net.core.wmem_max=${current_wmem}" >> "${sysctl_stage}"
    echo "警告：内核拒绝提高 UDP 发送缓冲，保留原值" >&2
  fi

  if command -v modprobe >/dev/null 2>&1; then
    modprobe tcp_bbr >/dev/null 2>&1 || true
  fi
  available_cc="$(sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null || true)"
  original_qdisc="$(sysctl -n net.core.default_qdisc 2>/dev/null || true)"
  original_cc="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"
  if [[ " ${available_cc} " == *" bbr "* ]] && \
    sysctl -w net.core.default_qdisc=fq >/dev/null 2>&1 && \
    sysctl -w net.ipv4.tcp_congestion_control=bbr >/dev/null 2>&1; then
    cat >> "${sysctl_stage}" <<'EOF'
# TCP BBR benefits the server's TCP egress to web and video origins.
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF
    echo "网络优化：Hysteria BBR standard + 内核 fq/BBR + 16 MiB UDP 缓冲"
  else
    [[ -z "${original_qdisc}" ]] || sysctl -w "net.core.default_qdisc=${original_qdisc}" >/dev/null 2>&1 || true
    [[ -z "${original_cc}" ]] || sysctl -w "net.ipv4.tcp_congestion_control=${original_cc}" >/dev/null 2>&1 || true
    echo "网络优化：Hysteria BBR standard + 16 MiB UDP 缓冲；当前内核不支持 fq/BBR，已安全跳过" >&2
  fi
  install -o root -g root -m 0644 "${sysctl_stage}" "${SYSCTL_FILE}"
}

if [[ "${1:-}" == "--maintenance-lock-held" ]]; then
  MAINTENANCE_LOCK_HELD=1
  shift
fi
ORIGINAL_ARGS=("$@")
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--recover-upgrade" ]]; then
  RECOVER_UPGRADE=1
  shift
elif [[ "${1:-}" == "--verify-recovered-upgrade" ]]; then
  VERIFY_RECOVERED_UPGRADE=1
  shift
elif [[ "${1:-}" == "--watch-upgrade" ]]; then
  [[ $# -eq 3 ]] || fail "升级 watchdog 参数无效；事务标记已保留"
  WATCH_UPGRADE=1
  WATCH_UPGRADE_PID="${2:-}"
  WATCH_UPGRADE_START="${3:-}"
  shift 3
elif [[ "${1:-}" == "--recover-fresh" ]]; then
  RECOVER_FRESH=1
  shift
elif [[ "${1:-}" == "--join-node" ]]; then
  JOIN_NODE=1
  shift
elif [[ "${1:-}" == "--rebind-node" ]]; then
  REBIND_NODE=1
  shift
elif [[ "${1:-}" == "--activate-node-agent" ]]; then
  ACTIVATE_NODE_AGENT=1
  shift
elif [[ "${1:-}" == "--activate-data-plane" ]]; then
  ACTIVATE_DATA_PLANE=1
  shift
elif [[ "${1:-}" == "--complete-node-onboarding" ]]; then
  COMPLETE_NODE_ONBOARDING=1
  shift
fi
[[ $# -eq 0 ]] || fail "未知参数：$1"
[[ ${EUID} -eq 0 ]] || fail "请使用 root 或 sudo 运行"
[[ "$(uname -s)" == "Linux" ]] || fail "仅支持 Linux"
assert_reopenable_installer_entrypoint
[[ -d /run/systemd/system ]] || fail "需要使用 systemd 的 Linux 系统"
if (( WATCH_UPGRADE == 1 )); then
  for command_name in awk sleep systemctl; do
    command -v "${command_name}" >/dev/null 2>&1 \
      || fail "升级 watchdog 缺少命令 ${command_name}；事务标记已保留"
  done
  INSTALL_COMMITTED=1
  watch_upgrade_parent "${WATCH_UPGRADE_PID}" "${WATCH_UPGRADE_START}" \
    || fail "升级 watchdog 无法启动恢复服务；事务标记已保留"
  exit 0
fi
if (( JOIN_NODE == 1 )); then
  install_join_node
  INSTALL_COMMITTED=1
  JOIN_NODE_MUTATED=0
  exit 0
fi
if (( REBIND_NODE == 1 )); then
  rebind_node
  INSTALL_COMMITTED=1
  REBIND_NODE_MUTATED=0
  exit 0
fi
if (( COMPLETE_NODE_ONBOARDING == 1 )); then
  # This mode owns no full-panel transaction. Its two reused activation
  # functions set their own rollback flags before making any changes.
  INSTALL_COMMITTED=1
  complete_node_onboarding
  exit 0
fi
if (( ACTIVATE_NODE_AGENT == 1 )); then
  activate_node_agent
  INSTALL_COMMITTED=1
  ACTIVATE_NODE_AGENT_MUTATED=0
  exit 0
fi
if (( ACTIVATE_DATA_PLANE == 1 )); then
  activate_data_plane
  INSTALL_COMMITTED=1
  DATA_PLANE_MUTATED=0
  exit 0
fi
AUTO_UPDATE="${HY2PANEL_AUTO_UPDATE:-0}"
[[ "${AUTO_UPDATE}" == "0" || "${AUTO_UPDATE}" == "1" ]] \
  || fail "HY2PANEL_AUTO_UPDATE 只能是 0 或 1"

# Package installation is itself a host mutation. Require the tiny set of
# baseline tools needed to serialize maintenance before installing anything.
for command_name in awk flock id install mkdir mktemp mv rm rmdir stat sync systemctl; do
  command -v "${command_name}" >/dev/null 2>&1 \
    || fail "缺少基础维护锁命令 ${command_name}；未修改系统，请先安装 util-linux 和 coreutils"
done
acquire_maintenance_lock
if (( RECOVER_FRESH == 1 )); then
  for command_name in cat chmod chown getent groupdel rm stat sync sysctl systemctl userdel; do
    command -v "${command_name}" >/dev/null 2>&1 \
      || fail "首次安装恢复缺少命令 ${command_name}；事务标记已保留"
  done
  EXISTING_INSTALL=0
  recover_interrupted_fresh_install
  INSTALL_COMMITTED=1
  exit 0
fi
if (( RECOVER_UPGRADE == 1 || VERIFY_RECOVERED_UPGRADE == 1 )); then
  for command_name in cat chmod chown cp find grep rm sha256sum sleep ss stat sync sysctl systemctl systemd-run; do
    command -v "${command_name}" >/dev/null 2>&1 \
      || fail "升级恢复缺少命令 ${command_name}；事务标记已保留"
  done
  select_python || fail "升级恢复需要 Python 3.8 或更高版本；事务标记已保留"
  if (( RECOVER_UPGRADE == 1 )); then
    recover_interrupted_upgrade
  else
    verify_recovered_upgrade
  fi
  INSTALL_COMMITTED=1
  exit 0
fi
cleanup_orphaned_fresh_recovery_infrastructure
settle_committed_firewall_transaction
assert_no_pending_restore_state
assert_no_pending_egress_state
assert_no_pending_upgrade_state
if [[ -e "${MANAGED_MARKER}" || -L "${MANAGED_MARKER}" ]]; then
  [[ ! -L "${MANAGED_MARKER}" && -f "${MANAGED_MARKER}" ]] \
    || fail "受管安装标记不是普通文件；为避免接管未知路径，安装已停止"
  managed_marker_metadata="$(stat -c '%u:%g:%a' "${MANAGED_MARKER}")" \
    || fail "无法核验受管安装标记；安装已停止"
  [[ "${managed_marker_metadata}" == "0:0:644" && ! -s "${MANAGED_MARKER}" ]] \
    || fail "受管安装标记的所有者、权限或内容无效；安装已停止"
fi
guard_legacy_restore_admission \
  || fail "旧版恢复任务正在运行、排队或无法安全阻断；本次部署未修改节点，请等待恢复完成后重试"
assert_no_pending_restore_state
assert_no_unmanaged_install_paths

required_commands=(awk busctl cat chmod chown cmp cp curl date df du find flock getent grep groupadd groupdel id install ip ip6tables-save iptables-save ln mktemp mv nft openssl readlink rm sed sha256sum sleep sort ss stat sudo sync sysctl systemctl systemd-run systemd-tmpfiles uname useradd userdel usermod visudo)
missing_commands=()
for command_name in "${required_commands[@]}"; do
  command -v "${command_name}" >/dev/null 2>&1 || missing_commands+=("${command_name}")
done
if ! select_python || (( ${#missing_commands[@]} > 0 )); then
  echo "缺失运行依赖：${missing_commands[*]:-Python 3.8+}"
  install_system_dependencies
fi
for command_name in "${required_commands[@]}"; do
  command -v "${command_name}" >/dev/null 2>&1 || fail "缺少命令：${command_name}"
done
select_python || fail "需要 Python 3.8 或更高版本；请升级系统 Python 后重试"
echo "运行环境：$(${PYTHON_BIN} -c 'import platform; print(platform.python_version())') / ${PYTHON_BIN}"

case "$(uname -m)" in
  x86_64|amd64)
    HYSTERIA_ASSET="hysteria-linux-amd64"
    HYSTERIA_SHA256="${HYSTERIA_SHA_AMD64}"
    COSIGN_ASSET="cosign-linux-amd64"
    COSIGN_SHA256="${COSIGN_SHA_AMD64}"
    ;;
  aarch64|arm64)
    HYSTERIA_ASSET="hysteria-linux-arm64"
    HYSTERIA_SHA256="${HYSTERIA_SHA_ARM64}"
    COSIGN_ASSET="cosign-linux-arm64"
    COSIGN_SHA256="${COSIGN_SHA_ARM64}"
    ;;
  *) fail "仅支持 Linux amd64 和 arm64" ;;
esac

recover_interrupted_fresh_install

EXISTING_INSTALL=0
if [[ -e "${MANAGED_MARKER}" && ! -s /etc/hysteria2-panel/panel.env ]]; then
  fail "受管安装缺少有效的 panel.env；为避免轮换节点身份，安装已停止，请先从备份恢复配置"
fi
if [[ -e "${MANAGED_MARKER}" ]]; then
  env_owner="$(stat -c %u /etc/hysteria2-panel/panel.env)"
  env_mode="$(stat -c %a /etc/hysteria2-panel/panel.env)"
  [[ "${env_owner}" == "0" && "${env_mode}" =~ ^[0-7]{3,4}$ ]] \
    || fail "受管安装的 panel.env 所有者或权限无效；安装已停止"
  (( (8#${env_mode} & 022) == 0 )) \
    || fail "受管安装的 panel.env 可被非 root 写入；安装已停止"
  EXISTING_INSTALL=1
  set -a
  # 仅加载本安装器创建、由 root 管理的现有配置，用作升级默认值。
  # shellcheck disable=SC1091
  source /etc/hysteria2-panel/panel.env \
    || fail "受管安装的 panel.env 无法读取；安装已停止"
  set +a
  required_identity_variables=(
    HY2PANEL_DB HY2PANEL_HMAC_KEY HY2PANEL_NODE_NAME HY2PANEL_PUBLIC_HOST
    HY2PANEL_HYSTERIA_PORT HY2PANEL_PANEL_PORT HY2PANEL_PANEL_SCHEME
    HY2PANEL_AUTH_PORT HY2PANEL_STATS_PORT HY2PANEL_STATS_SECRET
    HY2PANEL_TLS_CERT HY2PANEL_TLS_KEY HY2PANEL_CERT_PIN
  )
  for variable_name in "${required_identity_variables[@]}"; do
    [[ -n "${!variable_name:-}" ]] \
      || fail "受管安装缺少身份字段 ${variable_name}；为避免轮换节点身份，安装已停止"
  done
  [[ "${HY2PANEL_HMAC_KEY}" =~ ^[0-9A-Fa-f]{64,}$ && $(( ${#HY2PANEL_HMAC_KEY} % 2 )) -eq 0 ]] \
    || fail "受管安装的 HMAC 身份无效；安装已停止"
  [[ ${#HY2PANEL_STATS_SECRET} -ge 8 ]] \
    || fail "受管安装的统计身份无效；安装已停止"
  [[ -s "${HY2PANEL_DB}" ]] \
    || fail "受管安装的用户数据库缺失；安装已停止"
  HY2PANEL_IDENTITY_HMAC_KEY="${HY2PANEL_HMAC_KEY}" \
    "${PYTHON_BIN}" - "${HY2PANEL_DB}" <<'PY' \
    || fail "受管安装的用户数据库完整性检查失败；安装已停止"
import base64
import hashlib
import hmac
import os
import sqlite3
import sys

key = bytes.fromhex(os.environ.pop("HY2PANEL_IDENTITY_HMAC_KEY"))
with sqlite3.connect("file:{}?mode=ro".format(sys.argv[1]), uri=True) as connection:
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise SystemExit(1)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if not {"admins", "proxy_users"}.issubset(tables):
        raise SystemExit(1)
    admin_count = connection.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    if admin_count != 1:
        raise SystemExit(1)
    admin_columns = {row[1] for row in connection.execute("PRAGMA table_info(admins)")}
    if not {"id", "username", "password_hash", "created_at", "updated_at"}.issubset(
        admin_columns
    ):
        raise SystemExit(1)
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(proxy_users)")
    }
    required = {
        "id", "name", "token_fingerprint", "enabled", "generation",
        "created_at", "updated_at",
    }
    if not required.issubset(columns):
        raise SystemExit(1)
    if "token_seed" in columns:
        users = connection.execute(
            "SELECT token_seed, token_fingerprint FROM proxy_users"
        ).fetchall()
        for seed, expected in users:
            if seed is None:
                continue
            token = base64.urlsafe_b64encode(
                hmac.new(key, b"proxy-token\0" + bytes(seed), hashlib.sha256).digest()
            ).decode("ascii").rstrip("=")
            actual = hmac.new(key, token.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(actual, expected):
                raise SystemExit(1)
PY
  [[ -s "${HY2PANEL_TLS_CERT}" && -s "${HY2PANEL_TLS_KEY}" ]] \
    || fail "受管安装的 TLS 身份文件缺失；安装已停止"
  openssl x509 -in "${HY2PANEL_TLS_CERT}" -noout >/dev/null 2>&1 \
    || fail "受管安装的 TLS 证书无效；安装已停止"
  openssl pkey -in "${HY2PANEL_TLS_KEY}" -noout >/dev/null 2>&1 \
    || fail "受管安装的 TLS 私钥无效；安装已停止"
  cert_public_key="$(openssl x509 -in "${HY2PANEL_TLS_CERT}" -pubkey -noout 2>/dev/null | sha256sum | awk '{print $1}')"
  key_public_key="$(openssl pkey -in "${HY2PANEL_TLS_KEY}" -pubout 2>/dev/null | sha256sum | awk '{print $1}')"
  [[ -n "${cert_public_key}" && "${cert_public_key}" == "${key_public_key}" ]] \
    || fail "受管安装的 TLS 证书与私钥不匹配；安装已停止"
  existing_cert_pin="$(openssl x509 -in "${HY2PANEL_TLS_CERT}" -outform DER 2>/dev/null | sha256sum | awk '{print $1}')"
  [[ "${existing_cert_pin,,}" == "${HY2PANEL_CERT_PIN,,}" ]] \
    || fail "受管安装的 TLS 证书指纹不匹配；安装已停止"
fi
if [[ "${AUTO_UPDATE}" == "1" && "${EXISTING_INSTALL}" != "1" ]]; then
  fail "在线更新只允许用于现有的受管安装"
fi

detected_host="$(ip -4 -o addr show scope global 2>/dev/null | awk '{split($4,a,"/"); print a[1]; exit}')" || true
if (( EXISTING_INSTALL == 1 )); then
  EXISTING_NODE_NAME="${HY2PANEL_NODE_NAME}"
  EXISTING_PUBLIC_HOST="${HY2PANEL_PUBLIC_HOST}"
  EXISTING_HYSTERIA_PORT="${HY2PANEL_HYSTERIA_PORT}"
  EXISTING_PANEL_PORT="${HY2PANEL_PANEL_PORT}"
  EXISTING_PANEL_SCHEME="${HY2PANEL_PANEL_SCHEME}"
  EXISTING_PANEL_PUBLIC_HOST="${HY2PANEL_PANEL_PUBLIC_HOST:-}"
  EXISTING_EGRESS_POLICY="${HY2PANEL_EGRESS_POLICY:-full}"
  EXISTING_AUTH_PORT="${HY2PANEL_AUTH_PORT}"
  EXISTING_STATS_PORT="${HY2PANEL_STATS_PORT}"
  EXISTING_STATS_443_PORT="${HY2PANEL_STATS_443_PORT:-${DEFAULT_STATS_443_PORT}}"
else
  EXISTING_NODE_NAME="Hysteria 2"
  EXISTING_PUBLIC_HOST="${detected_host}"
  EXISTING_HYSTERIA_PORT="${DEFAULT_HYSTERIA_PORT}"
  EXISTING_PANEL_PORT="${DEFAULT_PANEL_PORT}"
  EXISTING_PANEL_SCHEME="https"
  EXISTING_PANEL_PUBLIC_HOST=""
  EXISTING_EGRESS_POLICY="full"
  EXISTING_AUTH_PORT="${DEFAULT_AUTH_PORT}"
  EXISTING_STATS_PORT="${DEFAULT_STATS_PORT}"
  EXISTING_STATS_443_PORT="${DEFAULT_STATS_443_PORT}"
fi

if (( EXISTING_INSTALL == 0 )); then
  assert_units_unclaimed
  for principal in hy2panel hy2server; do
    ! id -u "${principal}" >/dev/null 2>&1 \
      || fail "首次安装检测到同名系统账号 ${principal}；为避免权限劫持，安装已停止"
  done
  for principal_group in hy2panel hy2tls; do
    ! getent group "${principal_group}" >/dev/null 2>&1 \
      || fail "首次安装检测到同名系统组 ${principal_group}；为避免权限劫持，安装已停止"
  done
fi
if [[ "${AUTO_UPDATE}" == "1" ]]; then
  NODE_NAME="${EXISTING_NODE_NAME}"
  PUBLIC_HOST="${EXISTING_PUBLIC_HOST}"
  HYSTERIA_PORT="${EXISTING_HYSTERIA_PORT}"
  PANEL_PORT="${EXISTING_PANEL_PORT}"
  PANEL_SCHEME="${EXISTING_PANEL_SCHEME}"
  if [[ "${EXISTING_PANEL_SCHEME}" == "https" && -z "${EXISTING_PANEL_PUBLIC_HOST}" ]]; then
    fail "现有 HTTPS 安装缺少独立面板域名；为避免继续复用节点证书，请人工运行安装器补充 PANEL_PUBLIC_HOST"
  fi
  PANEL_PUBLIC_HOST="${EXISTING_PANEL_PUBLIC_HOST}"
  EGRESS_POLICY="${EXISTING_EGRESS_POLICY}"
  AUTH_PORT="${EXISTING_AUTH_PORT}"
  STATS_PORT="${EXISTING_STATS_PORT}"
  STATS_443_PORT="${EXISTING_STATS_443_PORT}"
  RESET_ADMIN="0"
  ADMIN_PASSWORD=""
fi
NODE_NAME="${NODE_NAME:-}"
if [[ -z "${NODE_NAME}" ]]; then
  read -r -p "分享链接节点名称 [${EXISTING_NODE_NAME}]: " NODE_NAME </dev/tty
  NODE_NAME="${NODE_NAME:-${EXISTING_NODE_NAME}}"
fi
[[ ${#NODE_NAME} -le 64 ]] || fail "节点名称最多 64 个字符"
[[ "${NODE_NAME}" != *$'\n'* && "${NODE_NAME}" != *$'\r'* ]] || fail "节点名称不能包含换行"
[[ "${NODE_NAME}" != *'"'* && "${NODE_NAME}" != *'`'* && "${NODE_NAME}" != *'$'* && "${NODE_NAME}" != *\\* ]] \
  || fail "节点名称不能包含引号、反引号、美元符号或反斜杠"

PUBLIC_HOST="${PUBLIC_HOST:-}"
if [[ -z "${PUBLIC_HOST}" ]]; then
  read -r -p "请输入节点域名 [${EXISTING_PUBLIC_HOST}]: " PUBLIC_HOST </dev/tty
  PUBLIC_HOST="${PUBLIC_HOST:-${EXISTING_PUBLIC_HOST}}"
fi
[[ -n "${PUBLIC_HOST}" ]] || fail "无法确定公网 IP 或域名"
[[ "${PUBLIC_HOST}" =~ ^[A-Za-z0-9.:-]+$ ]] || fail "公网 IP 或域名包含无效字符"

HYSTERIA_PORT="${HYSTERIA_PORT:-}"
if [[ -z "${HYSTERIA_PORT}" ]]; then
  read -r -p "Hysteria UDP 端口 [${EXISTING_HYSTERIA_PORT}]: " HYSTERIA_PORT </dev/tty
  HYSTERIA_PORT="${HYSTERIA_PORT:-${EXISTING_HYSTERIA_PORT}}"
fi
PANEL_PORT="${PANEL_PORT:-}"
if [[ -z "${PANEL_PORT}" ]]; then
  read -r -p "面板 TCP 端口 [${EXISTING_PANEL_PORT}]: " PANEL_PORT </dev/tty
  PANEL_PORT="${PANEL_PORT:-${EXISTING_PANEL_PORT}}"
fi
PANEL_SCHEME="${PANEL_SCHEME:-}"
if [[ -z "${PANEL_SCHEME}" ]]; then
  read -r -p "面板访问协议 http/https [${EXISTING_PANEL_SCHEME}]: " PANEL_SCHEME </dev/tty
  PANEL_SCHEME="${PANEL_SCHEME:-${EXISTING_PANEL_SCHEME}}"
fi
PANEL_SCHEME="${PANEL_SCHEME,,}"
[[ "${PANEL_SCHEME}" == "http" || "${PANEL_SCHEME}" == "https" ]] || fail "面板协议只能是 http 或 https"
if [[ "${PANEL_SCHEME}" == "http" ]]; then
  echo "警告：HTTP 不加密面板账号、密码和会话。仅在你明确接受风险时使用。" >&2
  PANEL_PUBLIC_HOST="${PANEL_PUBLIC_HOST:-${EXISTING_PANEL_PUBLIC_HOST:-${PUBLIC_HOST}}}"
else
  PANEL_PUBLIC_HOST="${PANEL_PUBLIC_HOST:-}"
  if [[ -z "${PANEL_PUBLIC_HOST}" ]]; then
    read -r -p "面板公网域名${EXISTING_PANEL_PUBLIC_HOST:+ [${EXISTING_PANEL_PUBLIC_HOST}]}: " PANEL_PUBLIC_HOST </dev/tty
    PANEL_PUBLIC_HOST="${PANEL_PUBLIC_HOST:-${EXISTING_PANEL_PUBLIC_HOST}}"
  fi
  PANEL_PUBLIC_HOST="${PANEL_PUBLIC_HOST,,}"
  validate_panel_public_host "${PANEL_PUBLIC_HOST}" \
    || fail "面板公网域名必须是完整的 ASCII DNS 名称，例如 panel.example.com"
fi
EGRESS_POLICY="${EGRESS_POLICY:-${EXISTING_EGRESS_POLICY}}"
EGRESS_POLICY="${EGRESS_POLICY,,}"
[[ "${EGRESS_POLICY}" == "web" || "${EGRESS_POLICY}" == "full" ]] \
  || fail "EGRESS_POLICY 只能是 web 或 full"
AUTH_PORT="${AUTH_PORT:-${EXISTING_AUTH_PORT}}"
STATS_PORT="${STATS_PORT:-${EXISTING_STATS_PORT}}"
STATS_443_PORT="${STATS_443_PORT:-${EXISTING_STATS_443_PORT}}"

for port in "${HYSTERIA_PORT}" "${PANEL_PORT}" "${AUTH_PORT}" "${STATS_PORT}" "${STATS_443_PORT}"; do
  if [[ ! "${port}" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
    fail "端口无效：${port}"
  fi
done
if [[ "${PANEL_SCHEME}" == "https" ]]; then
  if [[ "${HYSTERIA_PORT}" == "80" || "${PANEL_PORT}" == "80" || "${AUTH_PORT}" == "80" || "${STATS_PORT}" == "80" || "${STATS_443_PORT}" == "80" ]]; then
    fail "HTTPS 自动续期固定使用 TCP 80；Hysteria、面板和内部服务端口均不能设为 80"
  fi
  if ss -H -ltn "sport = :80" | grep -q .; then
    fail "ACME HTTP-01 需要独占 TCP 80，但该端口已被其他服务占用；安装器不会停止未知服务"
  fi
fi
[[ "${HYSTERIA_PORT}" != "${PANEL_PORT}" && "${HYSTERIA_PORT}" != "${AUTH_PORT}" && "${HYSTERIA_PORT}" != "${STATS_PORT}" ]] || fail "端口不能重复"
[[ "${PANEL_PORT}" != "${AUTH_PORT}" && "${PANEL_PORT}" != "${STATS_PORT}" && "${AUTH_PORT}" != "${STATS_PORT}" ]] || fail "端口不能重复"
[[ "${STATS_443_PORT}" != "${HYSTERIA_PORT}" && "${STATS_443_PORT}" != "${PANEL_PORT}" && "${STATS_443_PORT}" != "${AUTH_PORT}" && "${STATS_443_PORT}" != "${STATS_PORT}" ]] || fail "端口不能重复"

UDP_443_ENABLED=1
[[ "${HYSTERIA_PORT}" != "443" ]] || UDP_443_ENABLED=0
if (( UDP_443_ENABLED == 1 )) && [[ "${PANEL_PORT}" == "443" || "${AUTH_PORT}" == "443" || "${STATS_PORT}" == "443" || "${STATS_443_PORT}" == "443" ]]; then
  fail "启用账号专属 443 入口时，端口 443 不能用于面板或内部服务"
fi
prepare_firewall

if ss -H -lun "sport = :${HYSTERIA_PORT}" | grep -q . && ! systemctl is-active --quiet hysteria2-panel-server.service; then
  fail "UDP ${HYSTERIA_PORT} 已被其他服务占用"
fi
if ss -H -ltn "sport = :${HYSTERIA_PORT}" | grep -q . && ! systemctl is-active --quiet hysteria2-panel-tcp-probe.service; then
  fail "TCP ${HYSTERIA_PORT} 已被其他服务占用"
fi
if ss -H -ltn "sport = :${PANEL_PORT}" | grep -q . && ! systemctl is-active --quiet hysteria2-panel.service; then
  fail "TCP ${PANEL_PORT} 已被其他服务占用"
fi
if (( UDP_443_ENABLED == 1 )) && ss -H -lun "sport = :443" | grep -q . && ! systemctl is-active --quiet hysteria2-panel-server-443.service; then
  fail "UDP 443 已被其他服务占用"
fi
if (( UDP_443_ENABLED == 1 )) && ss -H -ltn "sport = :443" | grep -q . && ! systemctl is-active --quiet hysteria2-panel-tcp-probe-443.service; then
  fail "TCP 443 已被其他服务占用"
fi
if (( UDP_443_ENABLED == 1 )) && ss -H -ltn "sport = :${STATS_443_PORT}" | grep -q . && ! systemctl is-active --quiet hysteria2-panel-server-443.service; then
  fail "TCP ${STATS_443_PORT} 已被其他服务占用"
fi

ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
RESET_ADMIN="${RESET_ADMIN:-0}"
[[ "${RESET_ADMIN}" == "0" || "${RESET_ADMIN}" == "1" ]] || fail "RESET_ADMIN 只能是 0 或 1"
UPDATE_ADMIN=1
if (( EXISTING_INSTALL == 1 )) && [[ -s /var/lib/hysteria2-panel/panel.db && "${RESET_ADMIN}" == "0" && -z "${ADMIN_PASSWORD}" ]]; then
  UPDATE_ADMIN=0
  ADMIN_USER=""
  echo "检测到现有安装：本次升级保留当前管理员账号和密码（设置 RESET_ADMIN=1 可重置）"
else
  ADMIN_USER="${ADMIN_USER:-}"
  if [[ -z "${ADMIN_USER}" ]]; then
    read -r -p "面板管理员账号 [admin]: " ADMIN_USER </dev/tty
    ADMIN_USER="${ADMIN_USER:-admin}"
  fi
  if [[ -z "${ADMIN_PASSWORD}" ]]; then
    read -r -s -p "面板管理员密码: " ADMIN_PASSWORD </dev/tty
    echo
  fi
  [[ ${#ADMIN_PASSWORD} -ge 8 ]] || fail "面板密码至少需要 8 个字符"
fi

TMP_DIR="$(TMPDIR=/tmp mktemp -d -t hysteria2-panel.XXXXXXXX)"

if (( EXISTING_INSTALL == 0 )); then
  install_fresh_recovery_infrastructure
  arm_fresh_install_transaction
  install_upgrade_recovery_infrastructure
  install_fresh_recovery_gate
fi

echo "下载并校验 Hysteria ${HYSTERIA_VERSION}…"
if stage_verified_installed_binary \
  /opt/hysteria2-panel/bin/hysteria "${HYSTERIA_SHA256}" "${TMP_DIR}/hysteria"; then
  echo "复用已安装且哈希匹配的 root-owned Hysteria ${HYSTERIA_VERSION}"
else
  download_file \
    "https://github.com/apernet/hysteria/releases/download/app/v${HYSTERIA_VERSION}/${HYSTERIA_ASSET}" \
    "${TMP_DIR}/hysteria"
  printf '%s  %s\n' "${HYSTERIA_SHA256}" "${TMP_DIR}/hysteria" | sha256sum --check --status \
    || fail "Hysteria SHA-256 校验失败"
fi
echo "下载并校验 Cosign ${COSIGN_VERSION}…"
if stage_verified_installed_binary \
  /opt/hysteria2-panel/bin/cosign "${COSIGN_SHA256}" "${TMP_DIR}/cosign"; then
  echo "复用已安装且哈希匹配的 root-owned Cosign ${COSIGN_VERSION}"
else
  download_file \
    "https://github.com/sigstore/cosign/releases/download/v${COSIGN_VERSION}/${COSIGN_ASSET}" \
    "${TMP_DIR}/cosign"
  printf '%s  %s\n' "${COSIGN_SHA256}" "${TMP_DIR}/cosign" | sha256sum --check --status \
    || fail "Cosign SHA-256 校验失败"
fi
install -d -m 0755 "${TMP_DIR}/hy2panel"
download_file "${PANEL_SOURCE_URL}" "${TMP_DIR}/hysteria2_panel.py"
download_file "${OFFSITE_BACKUP_SOURCE_URL}" "${TMP_DIR}/offsite_backup.py"
download_file "${QRCODEGEN_SOURCE_URL}" "${TMP_DIR}/qrcodegen.py"
download_file "${TCP_PROBE_SOURCE_URL}" "${TMP_DIR}/tcp_probe.py"
download_file "${HY2PANEL_INIT_SOURCE_URL}" "${TMP_DIR}/hy2panel/__init__.py"
download_file "${HY2PANEL_VERSION_SOURCE_URL}" "${TMP_DIR}/hy2panel/version.py"
download_file "${HY2PANEL_BUDGETS_SOURCE_URL}" "${TMP_DIR}/hy2panel/budgets.py"
download_file "${HY2PANEL_WEB_ASSETS_SOURCE_URL}" "${TMP_DIR}/hy2panel/web_assets.py"
download_file "${HY2PANEL_OPERATIONS_SOURCE_URL}" "${TMP_DIR}/hy2panel/operations.py"
download_file "${HY2PANEL_RELEASE_SOURCE_URL}" "${TMP_DIR}/hy2panel/release.py"
download_file "${HY2PANEL_HEALTH_SOURCE_URL}" "${TMP_DIR}/hy2panel/health.py"
download_file "${HY2PANEL_CERTIFICATE_SOURCE_URL}" "${TMP_DIR}/hy2panel/certificate.py"
download_file "${HY2PANEL_SYSTEMD_SOURCE_URL}" "${TMP_DIR}/hy2panel/systemd.py"
download_file "${HY2PANEL_NODES_SOURCE_URL}" "${TMP_DIR}/hy2panel/nodes.py"
download_file "${HY2PANEL_DISTRIBUTED_SOURCE_URL}" "${TMP_DIR}/hy2panel/distributed.py"
download_file "${HY2PANEL_DASHBOARD_SOURCE_URL}" "${TMP_DIR}/hy2panel/dashboard.py"
download_file "${HY2PANEL_MOBILE_API_SOURCE_URL}" "${TMP_DIR}/hy2panel/mobile_api.py"
printf '%s  %s\n' "${PANEL_SHA256}" "${TMP_DIR}/hysteria2_panel.py" | sha256sum --check --status \
  || fail "面板源码 SHA-256 校验失败"
printf '%s  %s\n' "${OFFSITE_BACKUP_SHA256}" "${TMP_DIR}/offsite_backup.py" | sha256sum --check --status \
  || fail "异地备份源码 SHA-256 校验失败"
printf '%s  %s\n' "${QRCODEGEN_SHA256}" "${TMP_DIR}/qrcodegen.py" | sha256sum --check --status \
  || fail "二维码编码器 SHA-256 校验失败"
printf '%s  %s\n' "${TCP_PROBE_SHA256}" "${TMP_DIR}/tcp_probe.py" | sha256sum --check --status \
  || fail "TCP 探测源码 SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_INIT_SHA256}" "${TMP_DIR}/hy2panel/__init__.py" | sha256sum --check --status \
  || fail "hy2panel/__init__.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_VERSION_SHA256}" "${TMP_DIR}/hy2panel/version.py" | sha256sum --check --status \
  || fail "hy2panel/version.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_BUDGETS_SHA256}" "${TMP_DIR}/hy2panel/budgets.py" | sha256sum --check --status \
  || fail "hy2panel/budgets.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_WEB_ASSETS_SHA256}" "${TMP_DIR}/hy2panel/web_assets.py" | sha256sum --check --status \
  || fail "hy2panel/web_assets.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_OPERATIONS_SHA256}" "${TMP_DIR}/hy2panel/operations.py" | sha256sum --check --status \
  || fail "hy2panel/operations.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_RELEASE_SHA256}" "${TMP_DIR}/hy2panel/release.py" | sha256sum --check --status \
  || fail "hy2panel/release.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_HEALTH_SHA256}" "${TMP_DIR}/hy2panel/health.py" | sha256sum --check --status \
  || fail "hy2panel/health.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_CERTIFICATE_SHA256}" "${TMP_DIR}/hy2panel/certificate.py" | sha256sum --check --status \
  || fail "hy2panel/certificate.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_SYSTEMD_SHA256}" "${TMP_DIR}/hy2panel/systemd.py" | sha256sum --check --status \
  || fail "hy2panel/systemd.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_NODES_SHA256}" "${TMP_DIR}/hy2panel/nodes.py" | sha256sum --check --status \
  || fail "hy2panel/nodes.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_DISTRIBUTED_SHA256}" "${TMP_DIR}/hy2panel/distributed.py" | sha256sum --check --status \
  || fail "hy2panel/distributed.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_DASHBOARD_SHA256}" "${TMP_DIR}/hy2panel/dashboard.py" | sha256sum --check --status \
  || fail "hy2panel/dashboard.py SHA-256 校验失败"
printf '%s  %s\n' "${HY2PANEL_MOBILE_API_SHA256}" "${TMP_DIR}/hy2panel/mobile_api.py" | sha256sum --check --status \
  || fail "hy2panel/mobile_api.py SHA-256 校验失败"
"${PYTHON_BIN}" -m py_compile "${TMP_DIR}/hysteria2_panel.py" || fail "面板源码语法检查失败"
"${PYTHON_BIN}" -m py_compile "${TMP_DIR}/offsite_backup.py" || fail "异地备份源码语法检查失败"
"${PYTHON_BIN}" -m py_compile "${TMP_DIR}/qrcodegen.py" || fail "二维码编码器语法检查失败"
"${PYTHON_BIN}" -m py_compile "${TMP_DIR}/tcp_probe.py" || fail "TCP 探测源码语法检查失败"
"${PYTHON_BIN}" -m py_compile "${TMP_DIR}/hy2panel/"*.py || fail "面板模块语法检查失败"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/backups/hysteria2-panel/${timestamp}-$(openssl rand -hex 4)"
if [[ -e /opt/hysteria2-panel || -e /etc/hysteria2-panel || -e /var/lib/hysteria2-panel/panel.db ]]; then
  if (( EXISTING_INSTALL == 1 )); then
    require_backup_space
  fi
  install -d -m 0700 "${BACKUP_DIR}"
  [[ ! -d /opt/hysteria2-panel ]] || cp -a /opt/hysteria2-panel "${BACKUP_DIR}/opt"
  [[ ! -d /etc/hysteria2-panel ]] || cp -a /etc/hysteria2-panel "${BACKUP_DIR}/etc"
  for unit_file in hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-server-443.service hysteria2-panel-tcp-probe.service hysteria2-panel-tcp-probe-443.service hysteria2-panel-egress-full.service hysteria2-panel-egress-web.service hysteria2-panel-egress-recover.service hysteria2-panel-restore.service hysteria2-panel-restore-recover.service hysteria2-panel-restore-resume.service hysteria2-panel-cert-renew.service hysteria2-panel-cert-renew.timer hysteria2-panel-node-dns-admission.service hysteria2-panel-node-dns-admission.timer hysteria2-panel-offsite-backup.service hysteria2-panel-offsite-backup.timer hysteria2-panel-update.service; do
    [[ ! -f "/etc/systemd/system/${unit_file}" ]] || cp -a "/etc/systemd/system/${unit_file}" "${BACKUP_DIR}/${unit_file}"
  done
  [[ ! -L /etc/systemd/system/multi-user.target.wants/hysteria2-panel-restore-resume.service ]] \
    || cp -a /etc/systemd/system/multi-user.target.wants/hysteria2-panel-restore-resume.service \
      "${BACKUP_DIR}/hysteria2-panel-restore-resume.wants"
  [[ ! -L /etc/systemd/system/timers.target.wants/hysteria2-panel-cert-renew.timer ]] \
    || cp -a /etc/systemd/system/timers.target.wants/hysteria2-panel-cert-renew.timer \
      "${BACKUP_DIR}/hysteria2-panel-cert-renew.wants"
  [[ ! -L /etc/systemd/system/timers.target.wants/hysteria2-panel-node-dns-admission.timer ]] \
    || cp -a /etc/systemd/system/timers.target.wants/hysteria2-panel-node-dns-admission.timer \
      "${BACKUP_DIR}/hysteria2-panel-node-dns-admission.wants"
  [[ ! -L /etc/systemd/system/timers.target.wants/hysteria2-panel-offsite-backup.timer ]] \
    || cp -a /etc/systemd/system/timers.target.wants/hysteria2-panel-offsite-backup.timer \
      "${BACKUP_DIR}/hysteria2-panel-offsite-backup.wants"
  [[ ! -f "${SYSCTL_FILE}" ]] || cp -a "${SYSCTL_FILE}" "${BACKUP_DIR}/99-hysteria2-panel.conf"
  [[ ! -f /etc/sudoers.d/hysteria2-panel ]] || cp -a /etc/sudoers.d/hysteria2-panel "${BACKUP_DIR}/hysteria2-panel.sudoers"
  [[ ! -f "${TMPFILES_FILE}" ]] || cp -a "${TMPFILES_FILE}" "${BACKUP_DIR}/hysteria2-panel.tmpfiles"
  if (( EXISTING_INSTALL == 1 )); then
    ROLLBACK_REQUIRED=1
    systemctl is-active --quiet hysteria2-panel.service \
      || fail "升级前面板服务未运行；为避免不完整的流量快照，安装已停止"
    systemctl is-active --quiet hysteria2-panel-server.service \
      || fail "升级前 Hysteria 服务未运行；为避免不完整的流量快照，安装已停止"
    stop_panel_preserving_hysteria \
      || fail "无法暂停面板写入并保持 Hysteria 统计端点运行；安装已停止"
    systemctl is-active --quiet hysteria2-panel.service \
      && fail "面板写入未停止；安装已停止"
    systemctl is-active --quiet hysteria2-panel-server.service \
      || fail "暂停面板时 Hysteria 统计端点意外停止；安装已停止"
    legacy_restore_unit_is_quiescent \
      || fail "旧版恢复任务在升级准备期间进入运行或排队状态；安装已停止且旧面板将自动恢复"
    assert_no_pending_restore_state
    release_legacy_restore_guard \
      || fail "无法解除本次临时恢复门禁；安装已停止且旧面板将自动恢复"
    select_traffic_sync_options \
      || fail "升级前没有可用的 Hysteria 统计端点；安装已停止且旧版本将自动恢复"
    (
      set -a
      # shellcheck disable=SC1091
      source "${BACKUP_DIR}/etc/panel.env"
      set +a
      "${PYTHON_BIN}" "${TMP_DIR}/hysteria2_panel.py" \
        sync-traffic "${TRAFFIC_SYNC_OPTIONS[@]}"
    ) || fail "升级前流量结算失败；安装已停止且旧版本将自动恢复"
    [[ ! -e /var/lib/hysteria2-panel/pending-traffic.json ]] \
      || fail "升级前仍有未结算流量；安装已停止且旧版本将自动恢复"
    checkpoint_database /var/lib/hysteria2-panel/panel.db \
      || fail "升级前数据库校验或 WAL 截断失败；安装已停止"
    create_database_snapshot /var/lib/hysteria2-panel/panel.db "${BACKUP_DIR}/panel.db" \
      || fail "无法创建一致的用户数据库快照；安装已停止"
    capture_upgrade_runtime_state "${BACKUP_DIR}" \
      || fail "无法保存升级前运行时内核网络参数；安装已停止"
  fi
  write_backup_manifest "${BACKUP_DIR}" \
    || fail "无法生成升级备份完整性清单；安装已停止"
  sync -f "${BACKUP_DIR}" || fail "无法持久化升级备份；安装已停止"
  echo "升级前备份：${BACKUP_DIR}"
fi

if (( EXISTING_INSTALL == 1 )); then
  arm_upgrade_transaction
fi

if (( EXISTING_INSTALL == 0 )); then
  install -d -o root -g root -m 0700 /etc/hysteria2-panel
fi
ensure_sysctl_directory
if ! getent group hy2tls >/dev/null 2>&1; then
  groupadd --system hy2tls
fi
NOLOGIN_SHELL="$(command -v nologin 2>/dev/null || true)"
[[ -n "${NOLOGIN_SHELL}" ]] || NOLOGIN_SHELL=/sbin/nologin
if ! id -u hy2panel >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /var/lib/hysteria2-panel --shell "${NOLOGIN_SHELL}" hy2panel
fi
if ! id -u hy2server >/dev/null 2>&1; then
  useradd --system --gid hy2tls --home-dir /nonexistent --shell "${NOLOGIN_SHELL}" hy2server
fi
usermod -a -G hy2tls hy2panel
install -d -o root -g hy2tls -m 0750 /etc/hysteria2-panel
install -d -o hy2panel -g hy2panel -m 0750 /var/lib/hysteria2-panel
install -d -o root -g root -m 0700 /var/backups/hysteria2-panel
install -d -o hy2panel -g hy2panel -m 0700 /var/lib/hysteria2-panel/backup-restore
install -d -o root -g root -m 0700 /var/backups/hysteria2-panel/offsite-staging
install -d -o root -g root -m 0755 /opt/hysteria2-panel
install -d -o root -g root -m 0755 /opt/hysteria2-panel/bin
cat > "${TMP_DIR}/hysteria2-panel.tmpfiles" <<EOF
d ${MAINTENANCE_RUNTIME_DIR} 0750 root hy2panel -
f ${MAINTENANCE_LOCK_FILE} 0640 root hy2panel -
EOF
if [[ -e "${TMPFILES_FILE}" || -L "${TMPFILES_FILE}" ]]; then
  [[ ! -L "${TMPFILES_FILE}" && -f "${TMPFILES_FILE}" ]] \
    || fail "维护目录的 tmpfiles 配置不是普通文件；安装已停止"
  cmp -s -- "${TMP_DIR}/hysteria2-panel.tmpfiles" "${TMPFILES_FILE}" \
    || fail "已存在非本项目管理的 tmpfiles 配置；安装已停止"
fi
install -o root -g root -m 0644 "${TMP_DIR}/hysteria2-panel.tmpfiles" "${TMPFILES_FILE}"
systemd-tmpfiles --create "${TMPFILES_FILE}" \
  || fail "无法持久创建维护锁目录；安装已停止"
install -o root -g root -m 0755 "${TMP_DIR}/hysteria" /opt/hysteria2-panel/bin/hysteria
install -o root -g root -m 0755 "${TMP_DIR}/cosign" /opt/hysteria2-panel/bin/cosign
install -o root -g root -m 0755 "${TMP_DIR}/hysteria2_panel.py" /opt/hysteria2-panel/hysteria2_panel.py
install -o root -g root -m 0755 "${TMP_DIR}/offsite_backup.py" /opt/hysteria2-panel/offsite_backup.py
install -o root -g root -m 0644 "${TMP_DIR}/qrcodegen.py" /opt/hysteria2-panel/qrcodegen.py
install -o root -g root -m 0755 "${TMP_DIR}/tcp_probe.py" /opt/hysteria2-panel/tcp_probe.py
install -d -o root -g root -m 0755 /opt/hysteria2-panel/hy2panel
install -o root -g root -m 0644 "${TMP_DIR}/hy2panel/"*.py /opt/hysteria2-panel/hy2panel/
CERT_FILE=/etc/hysteria2-panel/server.crt
KEY_FILE=/etc/hysteria2-panel/server.key
if [[ ! -s "${CERT_FILE}" || ! -s "${KEY_FILE}" ]]; then
  /opt/hysteria2-panel/bin/hysteria cert --host "${PUBLIC_HOST}" --cert "${CERT_FILE}" --key "${KEY_FILE}" --valid-for 87600h
fi
chown root:hy2tls "${CERT_FILE}" "${KEY_FILE}"
chmod 0640 "${CERT_FILE}" "${KEY_FILE}"
CERT_PIN="$(openssl x509 -in "${CERT_FILE}" -outform DER | sha256sum | awk '{print $1}')"
[[ ${#CERT_PIN} -eq 64 ]] || fail "无法计算证书指纹"

if [[ "${PANEL_SCHEME}" == "https" ]]; then
  install_certbot_dependency
  configure_firewall
  issue_panel_acme_certificate
fi

ENV_FILE=/etc/hysteria2-panel/panel.env
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi
HMAC_KEY="${HY2PANEL_HMAC_KEY:-$(openssl rand -hex 32)}"
STATS_SECRET="${HY2PANEL_STATS_SECRET:-$(openssl rand -hex 32)}"
USAGE_ORIGIN_ID="${HY2PANEL_USAGE_ORIGIN_ID:-$(openssl rand -hex 16)}"

umask 0077
cat > "${ENV_FILE}" <<EOF
HY2PANEL_DB=/var/lib/hysteria2-panel/panel.db
HY2PANEL_HMAC_KEY=${HMAC_KEY}
HY2PANEL_USAGE_ORIGIN_ID=${USAGE_ORIGIN_ID}
HY2PANEL_NODE_NAME="${NODE_NAME}"
HY2PANEL_PUBLIC_HOST=${PUBLIC_HOST}
HY2PANEL_HYSTERIA_PORT=${HYSTERIA_PORT}
HY2PANEL_PANEL_PORT=${PANEL_PORT}
HY2PANEL_PANEL_SCHEME=${PANEL_SCHEME}
HY2PANEL_PANEL_PUBLIC_HOST=${PANEL_PUBLIC_HOST}
HY2PANEL_PANEL_TLS_CERT=${PANEL_CERT_FILE}
HY2PANEL_PANEL_TLS_KEY=${PANEL_KEY_FILE}
HY2PANEL_EGRESS_POLICY=${EGRESS_POLICY}
HY2PANEL_AUTH_PORT=${AUTH_PORT}
HY2PANEL_STATS_PORT=${STATS_PORT}
HY2PANEL_STATS_443_PORT=${STATS_443_PORT}
HY2PANEL_STATS_SECRET=${STATS_SECRET}
HY2PANEL_TLS_CERT=${CERT_FILE}
HY2PANEL_TLS_KEY=${KEY_FILE}
HY2PANEL_CERT_PIN=${CERT_PIN}
EOF
chown root:hy2panel "${ENV_FILE}"
chmod 0640 "${ENV_FILE}"

if [[ "${PANEL_SCHEME}" == "https" ]]; then
  install -d -o root -g hy2panel -m 0750 "${PANEL_TLS_ROOT}"
  cat > /opt/hysteria2-panel/acme-deploy.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

ENV_FILE=/etc/hysteria2-panel/panel.env
PANEL_TLS_ROOT=/etc/hysteria2-panel/panel-tls
PANEL_TLS_CURRENT=/etc/hysteria2-panel/panel-tls-current
stage=""
link_stage=""
rollback_link=""

cleanup() {
  if [[ -n "${stage}" && -d "${stage}" ]]; then
    rm -f -- "${stage}/fullchain.pem" "${stage}/privkey.pem"
    rmdir -- "${stage}"
  fi
  [[ -z "${link_stage}" ]] || rm -f -- "${link_stage}"
  [[ -z "${rollback_link}" ]] || rm -f -- "${rollback_link}"
}
trap cleanup EXIT

validate_hostname() {
  local hostname="$1" label
  local -a labels
  [[ -n "${hostname}" && ${#hostname} -le 253 && "${hostname}" == *.* ]]
  [[ "${hostname}" =~ ^[a-z0-9.-]+$ && "${hostname}" != *..* ]]
  IFS='.' read -r -a labels <<< "${hostname}"
  for label in "${labels[@]}"; do
    [[ "${label}" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]
  done
}

[[ ! -L "${ENV_FILE}" && -f "${ENV_FILE}" ]]
[[ "$(stat -c '%U:%G:%a:%h' "${ENV_FILE}")" == "root:hy2panel:640:1" ]]
set -a
# shellcheck disable=SC1091
source "${ENV_FILE}"
set +a
[[ "${HY2PANEL_PANEL_SCHEME}" == "https" ]]
[[ "${HY2PANEL_PANEL_TLS_CERT}" == "/etc/hysteria2-panel/panel.crt" ]]
[[ "${HY2PANEL_PANEL_TLS_KEY}" == "/etc/hysteria2-panel/panel.key" ]]
validate_hostname "${HY2PANEL_PANEL_PUBLIC_HOST}"

lineage="/etc/hysteria2-panel/acme/live/${HY2PANEL_PANEL_PUBLIC_HOST}"
source_cert="${lineage}/fullchain.pem"
source_key="${lineage}/privkey.pem"
[[ -s "${source_cert}" && -s "${source_key}" ]]

stage="$(mktemp -d "${PANEL_TLS_ROOT}/.deploy.XXXXXXXX")"
chown root:hy2panel "${stage}"
chmod 0750 "${stage}"
install -o root -g hy2panel -m 0640 "${source_cert}" "${stage}/fullchain.pem"
install -o root -g hy2panel -m 0640 "${source_key}" "${stage}/privkey.pem"
openssl x509 -in "${stage}/fullchain.pem" -noout -checkhost \
  "${HY2PANEL_PANEL_PUBLIC_HOST}" | grep -Fq "does match certificate"
cert_public_key="$(openssl x509 -in "${stage}/fullchain.pem" -pubkey -noout | sha256sum | awk '{print $1}')"
key_public_key="$(openssl pkey -in "${stage}/privkey.pem" -pubout | sha256sum | awk '{print $1}')"
[[ -n "${cert_public_key}" && "${cert_public_key}" == "${key_public_key}" ]]
serial="$(openssl x509 -in "${stage}/fullchain.pem" -noout -serial | sed 's/^serial=//')"
[[ "${serial}" =~ ^[0-9A-Fa-f]+$ ]]
final="${PANEL_TLS_ROOT}/${serial}"
if [[ -d "${final}" ]]; then
  cmp -s "${stage}/fullchain.pem" "${final}/fullchain.pem"
  cmp -s "${stage}/privkey.pem" "${final}/privkey.pem"
  cleanup
  stage=""
else
  mv -T -- "${stage}" "${final}"
  stage=""
  sync -f "${PANEL_TLS_ROOT}"
fi

previous_target=""
if [[ -e "${PANEL_TLS_CURRENT}" || -L "${PANEL_TLS_CURRENT}" ]]; then
  [[ -L "${PANEL_TLS_CURRENT}" ]]
  previous_target="$(readlink "${PANEL_TLS_CURRENT}")"
  [[ "${previous_target}" =~ ^panel-tls/[0-9A-Fa-f]+$ ]]
  [[ -d "/etc/hysteria2-panel/${previous_target}" ]]
fi
link_stage="$(mktemp "/etc/hysteria2-panel/.panel-tls-current.XXXXXXXX")"
rm -f -- "${link_stage}"
ln -s "panel-tls/${serial}" "${link_stage}"
mv -Tf -- "${link_stage}" "${PANEL_TLS_CURRENT}"
link_stage=""
sync -f /etc/hysteria2-panel

if systemctl is-active --quiet hysteria2-panel.service; then
  if ! systemctl restart hysteria2-panel.service; then
    if [[ -n "${previous_target}" ]]; then
      rollback_link="$(mktemp "/etc/hysteria2-panel/.panel-tls-rollback.XXXXXXXX")"
      rm -f -- "${rollback_link}"
      ln -s "${previous_target}" "${rollback_link}"
      mv -Tf -- "${rollback_link}" "${PANEL_TLS_CURRENT}"
      rollback_link=""
      sync -f /etc/hysteria2-panel
      systemctl restart hysteria2-panel.service || true
    fi
    exit 1
  fi
fi
EOF
  chmod 0755 /opt/hysteria2-panel/acme-deploy.sh

  cat > /opt/hysteria2-panel/acme-renew.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/certbot renew \
  --config-dir /etc/hysteria2-panel/acme \
  --work-dir /var/lib/hysteria2-panel/acme-work \
  --logs-dir /var/lib/hysteria2-panel/acme-logs \
  --cert-name "${HY2PANEL_PANEL_PUBLIC_HOST:?}" \
  --quiet \
  --deploy-hook /opt/hysteria2-panel/acme-deploy.sh
EOF
  chmod 0755 /opt/hysteria2-panel/acme-renew.sh

  for alias_spec in \
    "${PANEL_CERT_FILE}|panel-tls-current/fullchain.pem" \
    "${PANEL_KEY_FILE}|panel-tls-current/privkey.pem"; do
    IFS='|' read -r alias_path alias_target <<< "${alias_spec}"
    if [[ -e "${alias_path}" || -L "${alias_path}" ]]; then
      [[ -L "${alias_path}" && "$(readlink "${alias_path}")" == "${alias_target}" ]] \
        || fail "面板 TLS 别名路径已被其他文件占用：${alias_path}"
    else
      ln -s "${alias_target}" "${alias_path}"
    fi
  done
  /opt/hysteria2-panel/acme-deploy.sh \
    || fail "Let’s Encrypt 证书部署校验失败；未启动面板"
else
  rm -f -- /opt/hysteria2-panel/acme-deploy.sh /opt/hysteria2-panel/acme-renew.sh
fi

cat > /etc/hysteria2-panel/hysteria.yaml <<EOF
listen: :${HYSTERIA_PORT}
tls:
  cert: ${CERT_FILE}
  key: ${KEY_FILE}
auth:
  type: http
  http:
    url: http://127.0.0.1:${AUTH_PORT}/auth
    insecure: false
congestion:
  type: bbr
  bbrProfile: standard
ignoreClientBandwidth: true
trafficStats:
  listen: 127.0.0.1:${STATS_PORT}
  secret: ${STATS_SECRET}
EOF
# Hysteria ACL uses the first matching rule. Both policies reject local and private targets
# before allowing public traffic so proxy users cannot reach services inside the node's network.
# Source: https://v2.hysteria.network/docs/advanced/ACL/
cat >> /etc/hysteria2-panel/hysteria.yaml <<EOF
acl:
  inline:
    - "reject(0.0.0.0/8)"
    - "reject(127.0.0.0/8)"
    - "reject(10.0.0.0/8)"
    - "reject(100.64.0.0/10)"
    - "reject(169.254.0.0/16)"
    - "reject(172.16.0.0/12)"
    - "reject(192.168.0.0/16)"
    - "reject(224.0.0.0/4)"
    - "reject(240.0.0.0/4)"
    - "reject(::/128)"
    - "reject(::1/128)"
    - "reject(fc00::/7)"
    - "reject(fe80::/10)"
    - "reject(ff00::/8)"
EOF
if [[ "${EGRESS_POLICY}" == "web" ]]; then
  cat >> /etc/hysteria2-panel/hysteria.yaml <<EOF
    - "direct(all, tcp/22)"
    - "direct(all, tcp/${PANEL_PORT})"
    - "direct(all, tcp/53)"
    - "direct(all, udp/53)"
    - "direct(all, tcp/80)"
    - "direct(all, tcp/443)"
    - "direct(all, udp/443)"
    - "direct(all, udp/123)"
    - "reject(all)"
EOF
else
  cat >> /etc/hysteria2-panel/hysteria.yaml <<EOF
    - "direct(all)"
EOF
fi
cat >> /etc/hysteria2-panel/hysteria.yaml <<EOF
masquerade:
  type: string
  string:
    content: "404 page not found"
    statusCode: 404
EOF
chown root:hy2tls /etc/hysteria2-panel/hysteria.yaml
chmod 0640 /etc/hysteria2-panel/hysteria.yaml

if (( UDP_443_ENABLED == 1 )); then
  cp /etc/hysteria2-panel/hysteria.yaml /etc/hysteria2-panel/hysteria-443.yaml
  sed -i \
    -e "s|^listen: :${HYSTERIA_PORT}$|listen: :443|" \
    -e "s|url: http://127.0.0.1:${AUTH_PORT}/auth$|url: http://127.0.0.1:${AUTH_PORT}/auth/udp-443|" \
    -e "s|listen: 127.0.0.1:${STATS_PORT}$|listen: 127.0.0.1:${STATS_443_PORT}|" \
    /etc/hysteria2-panel/hysteria-443.yaml
  chown root:hy2tls /etc/hysteria2-panel/hysteria-443.yaml
  chmod 0640 /etc/hysteria2-panel/hysteria-443.yaml
else
  rm -f -- /etc/hysteria2-panel/hysteria-443.yaml
fi

cat > "${TMP_DIR}/hysteria2-panel.sudoers" <<'EOF'
hy2panel ALL=(root) NOPASSWD: /bin/systemctl start hysteria2-panel-server.service, /bin/systemctl stop hysteria2-panel-server.service, /bin/systemctl restart hysteria2-panel-server.service, /bin/systemctl start hysteria2-panel-egress-full.service, /bin/systemctl start hysteria2-panel-egress-web.service, /bin/systemctl --no-block start hysteria2-panel-restore.service, /bin/systemctl --no-block start hysteria2-panel-update.service, /bin/systemctl --no-block reboot
EOF
chmod 0440 "${TMP_DIR}/hysteria2-panel.sudoers"
visudo -cf "${TMP_DIR}/hysteria2-panel.sudoers" >/dev/null || fail "服务控制权限配置无效"
install -o root -g root -m 0440 "${TMP_DIR}/hysteria2-panel.sudoers" /etc/sudoers.d/hysteria2-panel

PANEL_BIND_CAPABILITY=""
if (( PANEL_PORT < 1024 || AUTH_PORT < 1024 )); then
  PANEL_BIND_CAPABILITY="AmbientCapabilities=CAP_NET_BIND_SERVICE"
fi
cat > /etc/systemd/system/hysteria2-panel.service <<EOF
[Unit]
Description=Hysteria 2 multi-user panel
Requires=hysteria2-panel-upgrade-recover.service hysteria2-panel-restore-recover.service hysteria2-panel-egress-recover.service
After=network-online.target hysteria2-panel-upgrade-recover.service hysteria2-panel-restore-recover.service hysteria2-panel-egress-recover.service
Wants=network-online.target
Before=hysteria2-panel-server.service hysteria2-panel-server-443.service

[Service]
Type=notify
NotifyAccess=main
TimeoutStartSec=60s
WatchdogSec=30s
User=hy2panel
Group=hy2panel
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py serve
Restart=on-failure
RestartSec=3s
UMask=0077
${PANEL_BIND_CAPABILITY}
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectControlGroups=true
# Options that imply a nosuid/NoNewPrivileges sandbox are intentionally omitted:
# this unit must execute only the exact sudoers-approved systemctl commands below.
ReadWritePaths=/var/lib/hysteria2-panel
TasksMax=160
MemoryMax=256M

[Install]
WantedBy=multi-user.target
EOF

SECONDARY_SERVER_WANTS=""
if (( UDP_443_ENABLED == 1 )); then
  SECONDARY_SERVER_WANTS="Wants=hysteria2-panel-server-443.service"
fi
PRIMARY_SERVER_BIND_CAPABILITIES=""
if (( HYSTERIA_PORT < 1024 || STATS_PORT < 1024 )); then
  PRIMARY_SERVER_BIND_CAPABILITIES=$'CapabilityBoundingSet=CAP_NET_BIND_SERVICE\nAmbientCapabilities=CAP_NET_BIND_SERVICE'
fi
cat > /etc/systemd/system/hysteria2-panel-server.service <<EOF
[Unit]
Description=Hysteria 2 server
After=network-online.target hysteria2-panel.service hysteria2-panel-upgrade-recover.service hysteria2-panel-restore-recover.service hysteria2-panel-egress-recover.service
Wants=network-online.target
Wants=hysteria2-panel.service
Requires=hysteria2-panel-upgrade-recover.service hysteria2-panel-restore-recover.service hysteria2-panel-egress-recover.service
Wants=hysteria2-panel-tcp-probe.service
${SECONDARY_SERVER_WANTS}

[Service]
Type=simple
User=hy2server
Group=hy2tls
ExecStart=/opt/hysteria2-panel/bin/hysteria server -c /etc/hysteria2-panel/hysteria.yaml
Nice=-5
Restart=on-failure
RestartSec=3s
UMask=0077
NoNewPrivileges=true
${PRIMARY_SERVER_BIND_CAPABILITIES}
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
TasksMax=256
MemoryMax=768M
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

if (( UDP_443_ENABLED == 1 )); then
  cat > /etc/systemd/system/hysteria2-panel-server-443.service <<'EOF'
[Unit]
Description=Hysteria 2 per-user UDP 443 server
After=network-online.target hysteria2-panel.service hysteria2-panel-upgrade-recover.service hysteria2-panel-restore-recover.service hysteria2-panel-egress-recover.service
Wants=network-online.target
Wants=hysteria2-panel.service
Requires=hysteria2-panel-upgrade-recover.service hysteria2-panel-restore-recover.service hysteria2-panel-egress-recover.service
PartOf=hysteria2-panel-server.service
Wants=hysteria2-panel-tcp-probe-443.service

[Service]
Type=simple
User=hy2server
Group=hy2tls
ExecStart=/opt/hysteria2-panel/bin/hysteria server -c /etc/hysteria2-panel/hysteria-443.yaml
Nice=-5
Restart=on-failure
RestartSec=3s
UMask=0077
NoNewPrivileges=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
TasksMax=256
MemoryMax=768M
LimitNOFILE=1048576
EOF

  cat > /etc/systemd/system/hysteria2-panel-tcp-probe-443.service <<EOF
[Unit]
Description=Hysteria 2 TCP 443 connectivity probe
After=hysteria2-panel-server-443.service
BindsTo=hysteria2-panel-server-443.service
PartOf=hysteria2-panel-server-443.service

[Service]
Type=simple
DynamicUser=true
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/tcp_probe.py 443
Restart=on-failure
RestartSec=3s
UMask=0077
NoNewPrivileges=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6
TasksMax=16
MemoryMax=64M
LimitNOFILE=4096
EOF
else
  rm -f -- /etc/systemd/system/hysteria2-panel-server-443.service /etc/systemd/system/hysteria2-panel-tcp-probe-443.service
fi

PRIMARY_PROBE_BIND_CAPABILITIES=""
if (( HYSTERIA_PORT < 1024 )); then
  PRIMARY_PROBE_BIND_CAPABILITIES=$'CapabilityBoundingSet=CAP_NET_BIND_SERVICE\nAmbientCapabilities=CAP_NET_BIND_SERVICE'
fi
cat > /etc/systemd/system/hysteria2-panel-tcp-probe.service <<EOF
[Unit]
Description=Hysteria 2 TCP connectivity probe
After=hysteria2-panel-server.service
BindsTo=hysteria2-panel-server.service
PartOf=hysteria2-panel-server.service

[Service]
Type=simple
DynamicUser=true
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/tcp_probe.py ${HYSTERIA_PORT}
Restart=on-failure
RestartSec=3s
UMask=0077
NoNewPrivileges=true
${PRIMARY_PROBE_BIND_CAPABILITIES}
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6
TasksMax=16
MemoryMax=64M
LimitNOFILE=4096
EOF

cat > /etc/systemd/system/hysteria2-panel-restore.service <<EOF
[Unit]
Description=Restore Hysteria 2 panel users and node identity

[Service]
Type=oneshot
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py restore-pending
ExecStopPost=/bin/systemctl --no-block start hysteria2-panel-restore-resume.service
TimeoutStartSec=25min
TimeoutStopSec=15min
KillSignal=SIGTERM
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadWritePaths=/etc/hysteria2-panel /var/lib/hysteria2-panel /var/backups/hysteria2-panel ${MAINTENANCE_RUNTIME_DIR}
TasksMax=32
MemoryMax=384M
EOF

cat > /etc/systemd/system/hysteria2-panel-restore-recover.service <<EOF
[Unit]
Description=Reconcile an interrupted Hysteria 2 panel restore before startup
After=local-fs.target systemd-tmpfiles-setup.service
Before=hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-server-443.service

[Service]
Type=oneshot
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py recover-restore-files
TimeoutStartSec=15min
TimeoutStopSec=15min
KillSignal=SIGTERM
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadWritePaths=/etc/hysteria2-panel /var/lib/hysteria2-panel /var/backups/hysteria2-panel ${MAINTENANCE_RUNTIME_DIR}
TasksMax=32
MemoryMax=384M
EOF

cat > /etc/systemd/system/hysteria2-panel-restore-resume.service <<EOF
[Unit]
Description=Resume an interrupted Hysteria 2 panel restore
After=network-online.target hysteria2-panel.service hysteria2-panel-server.service
Wants=network-online.target hysteria2-panel.service hysteria2-panel-server.service
ConditionPathExists=/etc/hysteria2-panel/.restore-active

[Service]
Type=oneshot
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py resume-after-restore
TimeoutStartSec=15min
TimeoutStopSec=15min
KillSignal=SIGTERM
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadWritePaths=/etc/hysteria2-panel /var/lib/hysteria2-panel /var/backups/hysteria2-panel ${MAINTENANCE_RUNTIME_DIR}
TasksMax=32
MemoryMax=384M

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/hysteria2-panel-egress-full.service <<EOF
[Unit]
Description=Switch Hysteria 2 to safe full egress
After=hysteria2-panel.service
Requires=hysteria2-panel.service

[Service]
Type=oneshot
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStartPre=/usr/bin/touch ${EGRESS_SWITCH_ACTIVE_MARKER}
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py apply-egress-policy full
ExecStopPost=-/bin/rm -f ${EGRESS_SWITCH_ACTIVE_MARKER}
TimeoutStartSec=5min
TimeoutStopSec=15s
KillSignal=SIGTERM
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX
ReadWritePaths=/etc/hysteria2-panel ${MAINTENANCE_RUNTIME_DIR}
TasksMax=32
MemoryMax=192M
EOF

cat > /etc/systemd/system/hysteria2-panel-egress-web.service <<EOF
[Unit]
Description=Switch Hysteria 2 to web-only egress
After=hysteria2-panel.service
Requires=hysteria2-panel.service

[Service]
Type=oneshot
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStartPre=/usr/bin/touch ${EGRESS_SWITCH_ACTIVE_MARKER}
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py apply-egress-policy web
ExecStopPost=-/bin/rm -f ${EGRESS_SWITCH_ACTIVE_MARKER}
TimeoutStartSec=5min
TimeoutStopSec=15s
KillSignal=SIGTERM
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX
ReadWritePaths=/etc/hysteria2-panel ${MAINTENANCE_RUNTIME_DIR}
TasksMax=32
MemoryMax=192M
EOF

cat > /etc/systemd/system/hysteria2-panel-egress-recover.service <<EOF
[Unit]
Description=Recover an interrupted Hysteria 2 egress policy transaction
After=local-fs.target systemd-tmpfiles-setup.service
Before=hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-server-443.service
ConditionPathExists=${EGRESS_TRANSACTION_MARKER}
ConditionPathExists=!${EGRESS_SWITCH_ACTIVE_MARKER}

[Service]
Type=oneshot
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py recover-egress-policy
TimeoutStartSec=5min
TimeoutStopSec=30s
KillSignal=SIGTERM
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX
ReadWritePaths=/etc/hysteria2-panel ${MAINTENANCE_RUNTIME_DIR}
TasksMax=32
MemoryMax=192M
EOF

if [[ "${PANEL_SCHEME}" == "https" ]]; then
  cat > /etc/systemd/system/hysteria2-panel-cert-renew.service <<'EOF'
[Unit]
Description=Renew the Hysteria 2 panel ACME certificate
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/hysteria2-panel/panel.env
SupplementaryGroups=hy2panel
ExecStart=/usr/bin/flock --exclusive --nonblock --conflict-exit-code 75 /run/hysteria2-panel-maintenance/lock /opt/hysteria2-panel/acme-renew.sh
SuccessExitStatus=75
TimeoutStartSec=30min
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadWritePaths=/etc/hysteria2-panel /var/lib/hysteria2-panel /run/hysteria2-panel-maintenance
TasksMax=64
MemoryMax=256M
EOF

  cat > /etc/systemd/system/hysteria2-panel-cert-renew.timer <<'EOF'
[Unit]
Description=Check the Hysteria 2 panel ACME certificate twice daily

[Timer]
OnCalendar=*-*-* 03,15:00:00
RandomizedDelaySec=1h
Persistent=true
Unit=hysteria2-panel-cert-renew.service

[Install]
WantedBy=timers.target
EOF
else
  systemctl disable --now hysteria2-panel-cert-renew.timer >/dev/null 2>&1 || true
  rm -f -- \
    /etc/systemd/system/hysteria2-panel-cert-renew.service \
    /etc/systemd/system/hysteria2-panel-cert-renew.timer \
    /etc/systemd/system/timers.target.wants/hysteria2-panel-cert-renew.timer
fi

cat > /etc/systemd/system/hysteria2-panel-node-dns-admission.service <<EOF
[Unit]
Description=Observe manual DNS and admit fresh Hysteria2 data nodes
After=network-online.target hysteria2-panel.service
Requires=hysteria2-panel.service
Wants=network-online.target

[Service]
Type=oneshot
User=hy2panel
Group=hy2panel
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py reconcile-node-dns
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadOnlyPaths=/opt/hysteria2-panel /etc/hysteria2-panel
ReadWritePaths=/var/lib/hysteria2-panel
TasksMax=32
MemoryMax=128M
TimeoutStartSec=20s
EOF
cat > /etc/systemd/system/hysteria2-panel-node-dns-admission.timer <<'EOF'
[Unit]
Description=Check manually managed data-node DNS every 30 seconds

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
Persistent=true
AccuracySec=1s
Unit=hysteria2-panel-node-dns-admission.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/hysteria2-panel-offsite-backup.service <<EOF
[Unit]
Description=Create and upload the daily Hysteria2-panel backup
After=network-online.target hysteria2-panel.service hysteria2-panel-server.service
Requires=hysteria2-panel.service hysteria2-panel-server.service
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=hy2panel
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py offsite-backup
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
CapabilityBoundingSet=CAP_DAC_OVERRIDE
AmbientCapabilities=CAP_DAC_OVERRIDE
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadOnlyPaths=/opt/hysteria2-panel /etc/hysteria2-panel
ReadWritePaths=/var/lib/hysteria2-panel /var/backups/hysteria2-panel/offsite-staging /run/hysteria2-panel-maintenance
TasksMax=48
MemoryMax=512M
TimeoutStartSec=30min
EOF
cat > /etc/systemd/system/hysteria2-panel-offsite-backup.timer <<'EOF'
[Unit]
Description=Run the Hysteria2-panel offsite backup once daily

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=2h
Persistent=true
Unit=hysteria2-panel-offsite-backup.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/hysteria2-panel-update.service <<EOF
[Unit]
Description=Install the latest formal Hysteria 2 panel release
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py apply-update --queued-target
TimeoutStartSec=25min
TimeoutStopSec=15min
KillSignal=SIGTERM
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectHome=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
TasksMax=128
MemoryMax=768M
EOF

if (( UPDATE_ADMIN == 1 )); then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  export HY2PANEL_ADMIN_PASSWORD="${ADMIN_PASSWORD}"
  set +a
  "${PYTHON_BIN}" /opt/hysteria2-panel/hysteria2_panel.py init-admin --username "${ADMIN_USER}"
fi
unset HY2PANEL_ADMIN_PASSWORD ADMIN_PASSWORD
chown -R hy2panel:hy2panel /var/lib/hysteria2-panel
chmod 0750 /var/lib/hysteria2-panel
find /var/lib/hysteria2-panel -type f -exec chmod 0600 {} +
if [[ "${PANEL_SCHEME}" == "https" ]]; then
  secure_acme_runtime_directories \
    || fail "无法收紧 ACME 运行目录权限；安装已停止"
fi

optimize_network_stack
systemctl daemon-reload
assert_units_claimed_by_installer
systemctl enable hysteria2-panel-restore-resume.service
systemctl enable hysteria2-panel.service
systemctl enable hysteria2-panel-server.service
systemctl enable hysteria2-panel-node-dns-admission.timer
systemctl enable hysteria2-panel-offsite-backup.timer
if [[ "${PANEL_SCHEME}" == "https" ]]; then
  systemctl enable hysteria2-panel-cert-renew.timer
  systemctl start hysteria2-panel-cert-renew.timer
fi
if (( EXISTING_INSTALL == 1 )); then
  systemctl is-active --quiet hysteria2-panel.service \
    && fail "切换新版本前面板写入意外恢复；旧版本将自动恢复"
  systemctl is-active --quiet hysteria2-panel-server.service \
    || fail "切换新版本前 Hysteria 服务已停止；旧版本将自动恢复"
  select_traffic_sync_options \
    || fail "切换新版本前没有可用的 Hysteria 统计端点；旧版本将自动恢复"
  (
    set -a
    # Use the endpoints served by the still-running old Hysteria processes.
    # shellcheck disable=SC1091
    source "${BACKUP_DIR}/etc/panel.env"
    set +a
    "${PYTHON_BIN}" /opt/hysteria2-panel/hysteria2_panel.py \
      sync-traffic --quiesce "${TRAFFIC_SYNC_OPTIONS[@]}"
  ) \
    || fail "切换新版本前的最终流量结算失败；旧版本将自动恢复"
  [[ ! -e /var/lib/hysteria2-panel/pending-traffic.json ]] \
    || fail "切换新版本前仍有未结算流量；旧版本将自动恢复"
  stop_loaded_units \
    hysteria2-panel-tcp-probe-443.service \
    hysteria2-panel-server-443.service \
    hysteria2-panel-tcp-probe.service \
    hysteria2-panel-server.service \
    || fail "无法停止旧 Hysteria 服务；旧版本将自动恢复"
  checkpoint_database /var/lib/hysteria2-panel/panel.db \
    || fail "最终流量结算后的数据库检查点失败；旧版本将自动恢复"
fi
systemctl restart hysteria2-panel.service hysteria2-panel-server.service
systemctl is-active --quiet hysteria2-panel.service || fail "面板服务启动失败"
systemctl is-active --quiet hysteria2-panel-server.service || fail "Hysteria 服务启动失败"
systemctl is-active --quiet hysteria2-panel-tcp-probe.service || fail "TCP 连通性探测服务启动失败"
if (( UDP_443_ENABLED == 1 )); then
  systemctl is-active --quiet hysteria2-panel-server-443.service || fail "Hysteria UDP 443 服务启动失败"
  systemctl is-active --quiet hysteria2-panel-tcp-probe-443.service || fail "TCP 443 连通性探测服务启动失败"
fi

PANEL_HEALTH_TLS_MODE=strict
[[ "${PANEL_SCHEME}" != "https" ]] || PANEL_HEALTH_TLS_MODE=insecure
wait_for_health "${PANEL_SCHEME}://127.0.0.1:${PANEL_PORT}/healthz" "${PANEL_HEALTH_TLS_MODE}" \
  || fail "面板存活检查失败"
wait_for_health "${PANEL_SCHEME}://127.0.0.1:${PANEL_PORT}/readyz" "${PANEL_HEALTH_TLS_MODE}" \
  || fail "面板就绪检查失败"
wait_for_health "http://127.0.0.1:${AUTH_PORT}/healthz" strict \
  || fail "认证服务健康检查失败"
systemctl start hysteria2-panel-node-dns-admission.timer \
  || fail "节点 DNS 只读监测 timer 启动失败"
systemctl start hysteria2-panel-offsite-backup.timer \
  || fail "异地备份 timer 启动失败"
ss -H -lun "sport = :${HYSTERIA_PORT}" | grep -q . || fail "Hysteria UDP 端口未监听"
if (( UDP_443_ENABLED == 1 )); then
  ss -H -lun "sport = :443" | grep -q . || fail "Hysteria UDP 443 端口未监听"
  ss -H -ltn "sport = :443" | grep -q . || fail "Hysteria TCP 443 探测端口未监听"
fi
ss -H -ltn "sport = :${HYSTERIA_PORT}" | grep -q . || fail "Hysteria TCP 探测端口未监听"
ss -H -ltn "sport = :${PANEL_PORT}" | grep -q . || fail "面板端口未监听"
"${PYTHON_BIN}" /opt/hysteria2-panel/hysteria2_panel.py \
  record-egress-policy-state "${EGRESS_POLICY}" \
  || fail "无法记录可验证的出站策略状态"
if [[ "${PANEL_SCHEME}" != "https" ]]; then
  configure_firewall
fi
flush_install_payload_for_commit \
  || fail "无法在提交前持久化首次部署文件；正在恢复部署前状态"
durable_replace_file /dev/null "${MANAGED_MARKER}" 0644 \
  || fail "无法持久化受管安装标记；正在恢复部署前状态"
if (( EXISTING_INSTALL == 1 )); then
  clear_upgrade_transaction \
    || fail "部署已通过健康检查，但无法清除升级事务标记；正在恢复旧版本"
fi
if (( EXISTING_INSTALL == 0 )); then
  disarm_fresh_install_transaction \
    || fail "部署已通过健康检查，但无法安全结束首次安装事务"
fi
finalize_firewall_transaction
INSTALL_COMMITTED=1
ROLLBACK_REQUIRED=0
FRESH_INSTALL_MUTATED=0
FIREWALL_APPLIED=()
if (( EXISTING_INSTALL == 1 )); then
  prune_automatic_backups \
    || echo "警告：自动备份保留策略执行失败；当前部署不受影响" >&2
fi

echo
echo "部署完成"
echo "面板地址：${PANEL_SCHEME}://${PANEL_PUBLIC_HOST}:${PANEL_PORT}/"
echo "Hysteria 端口：TCP/UDP ${HYSTERIA_PORT}"
if (( UDP_443_ENABLED == 1 )); then
  echo "账号专属 Hysteria 入口：UDP 443（需在编辑用户中单独开启）"
  echo "TCP 连通性探测：TCP 443"
fi
if [[ "${EGRESS_POLICY}" == "web" ]]; then
  echo "出站策略：web（网页/视频白名单，阻断常规 BT/PT 与非网页端口）"
  echo "运维访问：允许公网 TCP 22 与 ${PANEL_PORT}（私网目标仍拒绝）"
  echo "边界提示：端口 ACL 不是 DPI，无法保证识别伪装在 80/443 上的加密 P2P。"
else
  echo "出站策略：full（放行公网全端口，本地/私网/特殊用途目标仍拒绝）"
fi
echo "证书指纹：${CERT_PIN}"
echo "主机防火墙：${FIREWALL_RESULT}"
echo "云平台安全组仍需放行 TCP/UDP ${HYSTERIA_PORT} 与 TCP ${PANEL_PORT}。"
(( UDP_443_ENABLED == 0 )) || echo "云平台安全组还需放行 TCP/UDP 443。"
if [[ "${PANEL_SCHEME}" == "https" ]]; then
  echo "云平台安全组还需持续放行 TCP 80 用于 ACME HTTP-01 续期。"
  echo "面板 HTTPS：Let’s Encrypt 已签发，systemd 将每天检查两次续期。"
else
  echo "安全提示：面板当前使用明文 HTTP，请限制可信来源访问。"
  if [[ -n "${detected_host}" && "${PUBLIC_HOST}" != "${detected_host}" ]]; then
    echo "若域名的明文 HTTP 被网络重置，可尝试本机检测 IP：${PANEL_SCHEME}://${detected_host}:${PANEL_PORT}/"
  fi
fi
