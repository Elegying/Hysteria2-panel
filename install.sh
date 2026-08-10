#!/usr/bin/env bash
set -Eeuo pipefail

PANEL_VERSION="0.10.0"
PANEL_REF="${PANEL_REF:-v${PANEL_VERSION}}"
PANEL_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hysteria2_panel.py"
TCP_PROBE_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/tcp_probe.py"
PANEL_SHA256="5e5dfaa38bdd3f91076e22870f41ca2144bc4f0dc7b96445f90f5e88038681f8"
TCP_PROBE_SHA256="b63da9cc1e58ae3459e188a507d9e71bd205b5f3320448bc319d1f80a21885a2"
HYSTERIA_VERSION="2.12.1"
HYSTERIA_SHA_AMD64="ffc032c7ca6b78676d337097ca7f61bebc3a90a4f3a656693adf368f304cdbc7"
HYSTERIA_SHA_ARM64="c9cd1af6395eee13a937f429ea71b290e3cc571eea2b4d7f8bc7c49c1d23a792"
DEFAULT_HYSTERIA_PORT=19999
DEFAULT_PANEL_PORT=19998
DEFAULT_STATS_PORT=19997
DEFAULT_AUTH_PORT=19996
MIN_QUIC_UDP_BUFFER=16777216
SYSCTL_FILE=/etc/sysctl.d/99-hysteria2-panel.conf

usage() {
  cat <<'EOF'
Hysteria2-panel 一键部署

用法：
  sudo bash install.sh

默认端口：
  Hysteria 2: UDP 19999（同时提供 TCP 连通性探测）
  管理面板:   HTTP TCP 19998（可选 HTTPS）

支持系统：
  Debian/Ubuntu（apt）
  RHEL/Rocky/Alma/CentOS Stream/Fedora（dnf 或 yum）
  Linux amd64/arm64、systemd、Python 3.8 或更高版本

可选环境变量：NODE_NAME、PUBLIC_HOST、HYSTERIA_PORT、PANEL_PORT、PANEL_SCHEME、ADMIN_USER、ADMIN_PASSWORD、RESET_ADMIN
安装程序会交互式询问未提供的值，密码输入不会回显。
升级默认保留现有管理员；需要重置时设置 RESET_ADMIN=1。
EOF
}

fail() {
  echo "错误：$*" >&2
  exit 1
}

unexpected_error() {
  local status=$?
  echo "错误：部署在第 ${BASH_LINENO[0]} 行意外中断（退出码 ${status}）。请根据上一条系统输出处理后重试；重复运行会先备份并保持幂等。" >&2
  exit "${status}"
}
trap unexpected_error ERR

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

install_system_dependencies() {
  [[ -r /etc/os-release ]] || fail "无法识别 Linux 发行版：缺少 /etc/os-release"
  # shellcheck disable=SC1091
  source /etc/os-release
  echo "检测到系统：${PRETTY_NAME:-${ID:-unknown}}，正在安装缺失依赖"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      ca-certificates curl openssl iproute2 python3 coreutils findutils gawk grep passwd procps sudo
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y ca-certificates curl openssl iproute python3 coreutils findutils gawk grep shadow-utils procps-ng sudo
  elif command -v yum >/dev/null 2>&1; then
    yum install -y ca-certificates curl openssl iproute python3 coreutils findutils gawk grep shadow-utils procps-ng sudo
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

  command -v modprobe >/dev/null 2>&1 && modprobe tcp_bbr >/dev/null 2>&1 || true
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

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
[[ $# -eq 0 ]] || fail "未知参数：$1"
[[ ${EUID} -eq 0 ]] || fail "请使用 root 或 sudo 运行"
[[ "$(uname -s)" == "Linux" ]] || fail "仅支持 Linux"
[[ -d /run/systemd/system ]] || fail "需要使用 systemd 的 Linux 系统"

required_commands=(awk cp curl date find getent grep groupadd install ip mktemp openssl rm sha256sum sleep ss sudo sysctl systemctl useradd usermod visudo)
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
    ;;
  aarch64|arm64)
    HYSTERIA_ASSET="hysteria-linux-arm64"
    HYSTERIA_SHA256="${HYSTERIA_SHA_ARM64}"
    ;;
  *) fail "仅支持 Linux amd64 和 arm64" ;;
esac

MANAGED_MARKER=/etc/hysteria2-panel/.managed-by-installer
if [[ ! -e "${MANAGED_MARKER}" ]] && {
  [[ -e /opt/hysteria2-panel ]] || [[ -e /etc/hysteria2-panel ]] ||
    [[ -e /etc/systemd/system/hysteria2-panel.service ]] ||
    [[ -e /etc/systemd/system/hysteria2-panel-server.service ]] ||
    [[ -e /etc/systemd/system/hysteria2-panel-tcp-probe.service ]] ||
    [[ -e /etc/systemd/system/hysteria2-panel-restore.service ]]
}; then
  fail "发现非本安装器管理的同名路径或服务；为避免覆盖，安装已停止"
fi

EXISTING_INSTALL=0
if [[ -e "${MANAGED_MARKER}" && -s /etc/hysteria2-panel/panel.env ]]; then
  EXISTING_INSTALL=1
  set -a
  # 仅加载本安装器创建、由 root 管理的现有配置，用作升级默认值。
  # shellcheck disable=SC1091
  source /etc/hysteria2-panel/panel.env
  set +a
fi

detected_host="$(ip -4 -o addr show scope global 2>/dev/null | awk '{split($4,a,"/"); print a[1]; exit}')"
if (( EXISTING_INSTALL == 1 )); then
  EXISTING_NODE_NAME="${HY2PANEL_NODE_NAME:-Hysteria 2}"
  EXISTING_PUBLIC_HOST="${HY2PANEL_PUBLIC_HOST:-${detected_host}}"
  EXISTING_HYSTERIA_PORT="${HY2PANEL_HYSTERIA_PORT:-${DEFAULT_HYSTERIA_PORT}}"
  EXISTING_PANEL_PORT="${HY2PANEL_PANEL_PORT:-${DEFAULT_PANEL_PORT}}"
  EXISTING_PANEL_SCHEME="${HY2PANEL_PANEL_SCHEME:-http}"
  EXISTING_AUTH_PORT="${HY2PANEL_AUTH_PORT:-${DEFAULT_AUTH_PORT}}"
  EXISTING_STATS_PORT="${HY2PANEL_STATS_PORT:-${DEFAULT_STATS_PORT}}"
else
  EXISTING_NODE_NAME="Hysteria 2"
  EXISTING_PUBLIC_HOST="${detected_host}"
  EXISTING_HYSTERIA_PORT="${DEFAULT_HYSTERIA_PORT}"
  EXISTING_PANEL_PORT="${DEFAULT_PANEL_PORT}"
  EXISTING_PANEL_SCHEME="http"
  EXISTING_AUTH_PORT="${DEFAULT_AUTH_PORT}"
  EXISTING_STATS_PORT="${DEFAULT_STATS_PORT}"
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
  read -r -p "服务器公网 IP 或域名 [${EXISTING_PUBLIC_HOST}]: " PUBLIC_HOST </dev/tty
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
fi
AUTH_PORT="${AUTH_PORT:-${EXISTING_AUTH_PORT}}"
STATS_PORT="${STATS_PORT:-${EXISTING_STATS_PORT}}"

for port in "${HYSTERIA_PORT}" "${PANEL_PORT}" "${AUTH_PORT}" "${STATS_PORT}"; do
  if [[ ! "${port}" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
    fail "端口无效：${port}"
  fi
done
[[ "${HYSTERIA_PORT}" != "${PANEL_PORT}" && "${HYSTERIA_PORT}" != "${AUTH_PORT}" && "${HYSTERIA_PORT}" != "${STATS_PORT}" ]] || fail "端口不能重复"
[[ "${PANEL_PORT}" != "${AUTH_PORT}" && "${PANEL_PORT}" != "${STATS_PORT}" && "${AUTH_PORT}" != "${STATS_PORT}" ]] || fail "端口不能重复"

if ss -H -lun "sport = :${HYSTERIA_PORT}" | grep -q . && ! systemctl is-active --quiet hysteria2-panel-server.service; then
  fail "UDP ${HYSTERIA_PORT} 已被其他服务占用"
fi
if ss -H -ltn "sport = :${HYSTERIA_PORT}" | grep -q . && ! systemctl is-active --quiet hysteria2-panel-tcp-probe.service; then
  fail "TCP ${HYSTERIA_PORT} 已被其他服务占用"
fi
if ss -H -ltn "sport = :${PANEL_PORT}" | grep -q . && ! systemctl is-active --quiet hysteria2-panel.service; then
  fail "TCP ${PANEL_PORT} 已被其他服务占用"
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

TMP_DIR="$(mktemp -d -t hysteria2-panel.XXXXXXXX)"
cleanup() {
  if [[ -n "${TMP_DIR:-}" && -d "${TMP_DIR}" && "${TMP_DIR}" == /tmp/hysteria2-panel.* ]]; then
    rm -r -- "${TMP_DIR}"
  fi
}
trap cleanup EXIT

echo "下载并校验 Hysteria ${HYSTERIA_VERSION}…"
curl -fL --retry 3 --connect-timeout 10 \
  "https://github.com/apernet/hysteria/releases/download/app/v${HYSTERIA_VERSION}/${HYSTERIA_ASSET}" \
  -o "${TMP_DIR}/hysteria"
printf '%s  %s\n' "${HYSTERIA_SHA256}" "${TMP_DIR}/hysteria" | sha256sum --check --status \
  || fail "Hysteria SHA-256 校验失败"
curl -fL --retry 3 --connect-timeout 10 "${PANEL_SOURCE_URL}" -o "${TMP_DIR}/hysteria2_panel.py"
curl -fL --retry 3 --connect-timeout 10 "${TCP_PROBE_SOURCE_URL}" -o "${TMP_DIR}/tcp_probe.py"
printf '%s  %s\n' "${PANEL_SHA256}" "${TMP_DIR}/hysteria2_panel.py" | sha256sum --check --status \
  || fail "面板源码 SHA-256 校验失败"
printf '%s  %s\n' "${TCP_PROBE_SHA256}" "${TMP_DIR}/tcp_probe.py" | sha256sum --check --status \
  || fail "TCP 探测源码 SHA-256 校验失败"
"${PYTHON_BIN}" -m py_compile "${TMP_DIR}/hysteria2_panel.py" || fail "面板源码语法检查失败"
"${PYTHON_BIN}" -m py_compile "${TMP_DIR}/tcp_probe.py" || fail "TCP 探测源码语法检查失败"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/backups/hysteria2-panel/${timestamp}"
if [[ -e /opt/hysteria2-panel || -e /etc/hysteria2-panel || -e /var/lib/hysteria2-panel/panel.db ]]; then
  install -d -m 0700 "${BACKUP_DIR}"
  [[ ! -d /opt/hysteria2-panel ]] || cp -a /opt/hysteria2-panel "${BACKUP_DIR}/opt"
  [[ ! -d /etc/hysteria2-panel ]] || cp -a /etc/hysteria2-panel "${BACKUP_DIR}/etc"
  for unit_file in hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-tcp-probe.service hysteria2-panel-restore.service; do
    [[ ! -f "/etc/systemd/system/${unit_file}" ]] || cp -a "/etc/systemd/system/${unit_file}" "${BACKUP_DIR}/${unit_file}"
  done
  [[ ! -f "${SYSCTL_FILE}" ]] || cp -a "${SYSCTL_FILE}" "${BACKUP_DIR}/99-hysteria2-panel.conf"
  [[ ! -f /etc/sudoers.d/hysteria2-panel ]] || cp -a /etc/sudoers.d/hysteria2-panel "${BACKUP_DIR}/hysteria2-panel.sudoers"
  if [[ -f /var/lib/hysteria2-panel/panel.db ]]; then
    "${PYTHON_BIN}" - /var/lib/hysteria2-panel/panel.db "${BACKUP_DIR}/panel.db" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as source, sqlite3.connect(sys.argv[2]) as destination:
    source.backup(destination)
PY
  fi
  echo "升级前备份：${BACKUP_DIR}"
fi

if ! getent group hy2tls >/dev/null 2>&1; then
  groupadd --system hy2tls
fi
NOLOGIN_SHELL="$(command -v nologin 2>/dev/null || true)"
[[ -n "${NOLOGIN_SHELL}" ]] || NOLOGIN_SHELL=/sbin/nologin
if ! id -u hy2panel >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/hysteria2-panel --shell "${NOLOGIN_SHELL}" hy2panel
fi
if ! id -u hy2server >/dev/null 2>&1; then
  useradd --system --gid hy2tls --home-dir /nonexistent --shell "${NOLOGIN_SHELL}" hy2server
fi
usermod -a -G hy2tls hy2panel
install -d -o root -g hy2tls -m 0750 /etc/hysteria2-panel
install -d -o hy2panel -g hy2panel -m 0750 /var/lib/hysteria2-panel
install -d -o root -g root -m 0700 /var/backups/hysteria2-panel
install -d -o root -g root -m 0755 /opt/hysteria2-panel
install -d -o root -g root -m 0755 /opt/hysteria2-panel/bin
install -o root -g root -m 0755 "${TMP_DIR}/hysteria" /opt/hysteria2-panel/bin/hysteria
install -o root -g root -m 0755 "${TMP_DIR}/hysteria2_panel.py" /opt/hysteria2-panel/hysteria2_panel.py
install -o root -g root -m 0755 "${TMP_DIR}/tcp_probe.py" /opt/hysteria2-panel/tcp_probe.py
install -o root -g root -m 0644 /dev/null "${MANAGED_MARKER}"

CERT_FILE=/etc/hysteria2-panel/server.crt
KEY_FILE=/etc/hysteria2-panel/server.key
if [[ ! -s "${CERT_FILE}" || ! -s "${KEY_FILE}" ]]; then
  /opt/hysteria2-panel/bin/hysteria cert --host "${PUBLIC_HOST}" --cert "${CERT_FILE}" --key "${KEY_FILE}" --valid-for 87600h
fi
chown root:hy2tls "${CERT_FILE}" "${KEY_FILE}"
chmod 0640 "${CERT_FILE}" "${KEY_FILE}"
CERT_PIN="$(openssl x509 -in "${CERT_FILE}" -outform DER | sha256sum | awk '{print $1}')"
[[ ${#CERT_PIN} -eq 64 ]] || fail "无法计算证书指纹"

ENV_FILE=/etc/hysteria2-panel/panel.env
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi
HMAC_KEY="${HY2PANEL_HMAC_KEY:-$(openssl rand -hex 32)}"
STATS_SECRET="${HY2PANEL_STATS_SECRET:-$(openssl rand -hex 32)}"

umask 0077
cat > "${ENV_FILE}" <<EOF
HY2PANEL_DB=/var/lib/hysteria2-panel/panel.db
HY2PANEL_HMAC_KEY=${HMAC_KEY}
HY2PANEL_NODE_NAME="${NODE_NAME}"
HY2PANEL_PUBLIC_HOST=${PUBLIC_HOST}
HY2PANEL_HYSTERIA_PORT=${HYSTERIA_PORT}
HY2PANEL_PANEL_PORT=${PANEL_PORT}
HY2PANEL_PANEL_SCHEME=${PANEL_SCHEME}
HY2PANEL_AUTH_PORT=${AUTH_PORT}
HY2PANEL_STATS_PORT=${STATS_PORT}
HY2PANEL_STATS_SECRET=${STATS_SECRET}
HY2PANEL_TLS_CERT=${CERT_FILE}
HY2PANEL_TLS_KEY=${KEY_FILE}
HY2PANEL_CERT_PIN=${CERT_PIN}
EOF
chown root:hy2panel "${ENV_FILE}"
chmod 0640 "${ENV_FILE}"

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
masquerade:
  type: string
  string:
    content: "404 page not found"
    statusCode: 404
EOF
chown root:hy2tls /etc/hysteria2-panel/hysteria.yaml
chmod 0640 /etc/hysteria2-panel/hysteria.yaml

cat > "${TMP_DIR}/hysteria2-panel.sudoers" <<'EOF'
hy2panel ALL=(root) NOPASSWD: /bin/systemctl start hysteria2-panel-server.service, /bin/systemctl stop hysteria2-panel-server.service, /bin/systemctl restart hysteria2-panel-server.service, /bin/systemctl --no-block start hysteria2-panel-restore.service
EOF
chmod 0440 "${TMP_DIR}/hysteria2-panel.sudoers"
visudo -cf "${TMP_DIR}/hysteria2-panel.sudoers" >/dev/null || fail "服务控制权限配置无效"
install -o root -g root -m 0440 "${TMP_DIR}/hysteria2-panel.sudoers" /etc/sudoers.d/hysteria2-panel

cat > /etc/systemd/system/hysteria2-panel.service <<EOF
[Unit]
Description=Hysteria 2 multi-user panel
After=network-online.target
Wants=network-online.target
Before=hysteria2-panel-server.service

[Service]
Type=simple
User=hy2panel
Group=hy2panel
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py serve
Restart=on-failure
RestartSec=3s
UMask=0077
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

cat > /etc/systemd/system/hysteria2-panel-server.service <<'EOF'
[Unit]
Description=Hysteria 2 server
After=network-online.target hysteria2-panel.service
Wants=network-online.target
Requires=hysteria2-panel.service
Wants=hysteria2-panel-tcp-probe.service

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
Conflicts=hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-tcp-probe.service
Before=hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-tcp-probe.service

[Service]
Type=oneshot
EnvironmentFile=/etc/hysteria2-panel/panel.env
ExecStart=${PYTHON_BIN} /opt/hysteria2-panel/hysteria2_panel.py restore-pending
ExecStopPost=/bin/systemctl --no-block start hysteria2-panel.service hysteria2-panel-server.service hysteria2-panel-tcp-probe.service
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
ReadWritePaths=/etc/hysteria2-panel /var/lib/hysteria2-panel /var/backups/hysteria2-panel
TasksMax=32
MemoryMax=384M
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

optimize_network_stack
systemctl daemon-reload
systemctl enable hysteria2-panel.service
systemctl enable hysteria2-panel-server.service
systemctl restart hysteria2-panel.service
systemctl restart hysteria2-panel-server.service
systemctl is-active --quiet hysteria2-panel.service || fail "面板服务启动失败"
systemctl is-active --quiet hysteria2-panel-server.service || fail "Hysteria 服务启动失败"
systemctl is-active --quiet hysteria2-panel-tcp-probe.service || fail "TCP 连通性探测服务启动失败"

PANEL_HEALTH_TLS_MODE=strict
[[ "${PANEL_SCHEME}" != "https" ]] || PANEL_HEALTH_TLS_MODE=insecure
wait_for_health "${PANEL_SCHEME}://127.0.0.1:${PANEL_PORT}/healthz" "${PANEL_HEALTH_TLS_MODE}" \
  || fail "面板健康检查失败"
wait_for_health "http://127.0.0.1:${AUTH_PORT}/healthz" strict \
  || fail "认证服务健康检查失败"
ss -H -lun "sport = :${HYSTERIA_PORT}" | grep -q . || fail "Hysteria UDP 端口未监听"
ss -H -ltn "sport = :${HYSTERIA_PORT}" | grep -q . || fail "Hysteria TCP 探测端口未监听"
ss -H -ltn "sport = :${PANEL_PORT}" | grep -q . || fail "面板端口未监听"

echo
echo "部署完成"
echo "面板地址：${PANEL_SCHEME}://${PUBLIC_HOST}:${PANEL_PORT}/"
echo "Hysteria 端口：TCP/UDP ${HYSTERIA_PORT}"
echo "证书指纹：${CERT_PIN}"
echo "如云平台或主机启用了防火墙，请放行 TCP/UDP ${HYSTERIA_PORT} 与 TCP ${PANEL_PORT}。"
if [[ "${PANEL_SCHEME}" == "https" ]]; then
  echo "首次打开自签名 HTTPS 地址时，浏览器会显示证书警告。"
else
  echo "安全提示：面板当前使用明文 HTTP，请限制可信来源访问。"
fi
