#!/usr/bin/env bash
# Run only in a disposable clean distribution container, never a live host.
set -euo pipefail
[[ "${HY2PANEL_DISPOSABLE_TEST:-}" == "1" ]] || exit 1
cd /workspace
fail() { echo "$*" >&2; exit 1; }
eval "$(sed -n '/^select_python() {/,/^ensure_node_dependencies() {/p' install.sh | sed '$d')"
eval "$(sed -n '/^bootstrap_apt_repair_runtime() (/,/^install_certbot_dependency() {/p' install.sh | sed '$d')"
cat /etc/os-release
install_system_dependencies
select_python
"${PYTHON_BIN}" -c 'import hashlib, sqlite3, ssl; assert hasattr(hashlib, "scrypt")'
for executable in curl openssl nft iptables-save ip6tables-save ip ss sudo visudo flock; do
  command -v "${executable}"
done
# A second pass must also succeed with dependencies already present.
install_system_dependencies
echo 'DEPENDENCY_BOOTSTRAP_OK'
