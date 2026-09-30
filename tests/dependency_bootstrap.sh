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
if command -v apt-get >/dev/null 2>&1; then
  # Exercise real APT diagnostics inside this disposable container. The hook
  # sentinel proves unrelated errors never even enter repository migration.
  (
    trial=$(mktemp -d)
    probe_pid=""
    trap 'if [[ -n "${probe_pid}" ]]; then kill "${probe_pid}" 2>/dev/null || true; wait "${probe_pid}" 2>/dev/null || true; fi; rm -rf -- "${trial}"' EXIT
    python3 - "${trial}/port" <<'PY' &
import fcntl
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

lock = open('/var/lib/dpkg/lock-frontend', 'a')
fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
class MissingRepository(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_error(404)
    def log_message(self, *args):
        pass
server = HTTPServer(('127.0.0.1', 0), MissingRepository)
Path(sys.argv[1]).write_text(str(server.server_port) + '\n')
server.serve_forever()
PY
    probe_pid=$!
    for _attempt in {1..100}; do
      [[ ! -s "${trial}/port" ]] || break
      kill -0 "${probe_pid}"
      sleep 0.1
    done
    [[ -s "${trial}/port" ]]
    # Only shorten the native lock wait in this test, never bypass its lock.
    # shellcheck disable=SC2329,SC2317 # Invoked by the extracted retry helper.
    apt-get() { command apt-get "$@" -o DPkg::Lock::Timeout=0; }
    # shellcheck disable=SC2329,SC2317 # Hook invoked indirectly by the extracted helper.
    repair_debian_apt_sources() { echo UNEXPECTED_SOURCE_REPAIR >&2; return 1; }
    HY2PANEL_APT_REPAIR_ATTEMPTED=0
    if retry_package_command apt-get install -y python3 > "${trial}/lock.log" 2>&1; then
      fail "APT unexpectedly ignored an active dpkg lock"
    fi
    grep -F 'Could not get lock' "${trial}/lock.log"
    if grep -Fq UNEXPECTED_SOURCE_REPAIR "${trial}/lock.log"; then
      fail "A lock error entered repository repair"
    fi
    mkdir -p "${trial}/lists/partial"
    IFS= read -r port < "${trial}/port"
    printf 'deb http://127.0.0.1:%s missing main\n' "${port}" > "${trial}/sources.list"
    # shellcheck disable=SC2034 # Read by the extracted retry helper.
    HY2PANEL_APT_REPAIR_ATTEMPTED=0
    if retry_package_command apt-get -o "Dir::Etc::sourcelist=${trial}/sources.list" \
      -o Dir::Etc::sourceparts=- -o "Dir::State::lists=${trial}/lists" \
      -o Acquire::http::Proxy=false update > "${trial}/repository.log" 2>&1; then
      fail "APT unexpectedly accepted a repository without a Release file"
    fi
    grep -F 'does not have a Release file' "${trial}/repository.log"
    if grep -Fq UNEXPECTED_SOURCE_REPAIR "${trial}/repository.log"; then
      fail "A third-party repository error entered repository repair"
    fi
    echo 'APT_FAILURE_ISOLATION_OK'
  )
fi
echo 'DEPENDENCY_BOOTSTRAP_OK'
