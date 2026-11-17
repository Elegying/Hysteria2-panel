#!/usr/bin/env bash
# HTTPS bootstrap for the signed, version-pinned installer.
(
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo '请切换到 root 后重新粘贴此代码' >&2; exit 1; fi
if [ "$(uname -s)" != Linux ] || [ ! -d /run/systemd/system ]; then
  echo '对接需要使用 systemd 的 Linux 服务器' >&2; exit 1
fi
if [ "${1:-}" = "--join-node" ] && [ -e /etc/hysteria2-panel/.managed-by-installer ]; then
  echo '完整面板服务器不能作为对接节点' >&2; exit 1
fi
join_tmp="$(mktemp -d -t hy2panel-node-join.XXXXXXXX)"
trap 'rm -rf -- "$join_tmp"' EXIT HUP INT TERM
case "$(uname -m)" in
  x86_64|amd64) cosign_asset=cosign-linux-amd64; cosign_sha=4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71 ;;
  aarch64|arm64) cosign_asset=cosign-linux-arm64; cosign_sha=c5d324e091826b0d7a78eb16fef316450b4eb9aaec045611c08ba06f5e73220a ;;
  *) echo '仅支持 Linux amd64 和 arm64' >&2; exit 1 ;;
esac
bootstrap_dependencies=0
command -v curl >/dev/null 2>&1 || bootstrap_dependencies=1
command -v sha256sum >/dev/null 2>&1 || bootstrap_dependencies=1
if [ ! -s /etc/ssl/certs/ca-certificates.crt ] && [ ! -s /etc/pki/tls/certs/ca-bundle.crt ]; then bootstrap_dependencies=1; fi
if [ "$bootstrap_dependencies" -eq 1 ]; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get 'update'
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl ca-certificates coreutils
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y ca-certificates
    command -v curl >/dev/null 2>&1 || dnf install -y curl
    command -v sha256sum >/dev/null 2>&1 || dnf install -y coreutils
  elif command -v yum >/dev/null 2>&1; then
    yum install -y ca-certificates
    command -v curl >/dev/null 2>&1 || yum install -y curl
    command -v sha256sum >/dev/null 2>&1 || yum install -y coreutils
  else
    echo '请先安装 curl、ca-certificates 和 coreutils，然后重新运行对接代码' >&2; exit 1
  fi
fi
command -v curl >/dev/null 2>&1
command -v sha256sum >/dev/null 2>&1
curl -q -fL --retry 3 --connect-timeout 10 --max-time 300 \
  "https://github.com/sigstore/cosign/releases/download/v3.1.3/$cosign_asset" \
  -o "$join_tmp/cosign"
printf '%s  %s\n' "$cosign_sha" "$join_tmp/cosign" | sha256sum --check --status
chmod 0700 "$join_tmp/cosign"
curl -q -fL --retry 3 --connect-timeout 10 --max-time 300 'https://raw.githubusercontent.com/Elegying/Hysteria2-panel/v0.39.56/install.sh' -o "$join_tmp/install.sh"
curl -q -fL --retry 3 --connect-timeout 10 --max-time 300 'https://github.com/Elegying/Hysteria2-panel/releases/download/v0.39.56/install.sh.sigstore.json' -o "$join_tmp/install.sh.sigstore.json"
"$join_tmp/cosign" verify-blob "$join_tmp/install.sh" \
  --bundle "$join_tmp/install.sh.sigstore.json" \
  --certificate-identity 'https://github.com/Elegying/Hysteria2-panel/.github/workflows/release-signature.yml@refs/tags/v0.39.56' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
bash -n "$join_tmp/install.sh"
/bin/rm -f -- "$join_tmp/cosign" "$join_tmp/install.sh.sigstore.json"
export HY2PANEL_PANEL_URL
export HY2PANEL_ENROLLMENT_TOKEN
export PANEL_REF='v0.39.56'
/bin/bash "$join_tmp/install.sh" "${@}"
unset HY2PANEL_ENROLLMENT_TOKEN
)
