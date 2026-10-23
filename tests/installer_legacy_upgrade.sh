#!/usr/bin/env bash
set -euo pipefail
[[ "${container:-}" == docker && ${EUID} == 0 && -n "${PANEL_REF:-}" ]]
export NODE_NAME="CI legacy upgrade" PUBLIC_HOST=127.0.0.1
export HYSTERIA_PORT=31999 PANEL_PORT=31998 AUTH_PORT=31996 STATS_PORT=31997 STATS_443_PORT=31995
export PANEL_SCHEME=http EGRESS_POLICY=full ADMIN_USER=ci-admin ADMIN_PASSWORD=ci-only-password-42
candidate_ref="${PANEL_REF}"
legacy_ref=6d14976a44bdda112314407ed94a2a50e1c71316
curl -fsSL --retry 3 "https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${legacy_ref}/install.sh" -o /workspace/install-legacy.sh
PANEL_REF="${legacy_ref}" bash /workspace/install-legacy.sh
systemctl stop hysteria2-panel.service
set -a
# shellcheck disable=SC1091
source /etc/hysteria2-panel/panel.env
set +a
cat > /workspace/legacy_identity.py <<'PY'
import hashlib,json,os,sys
sys.path.insert(0,'/opt/hysteria2-panel')
import hysteria2_panel as p
s=p.Settings.from_mapping(os.environ)
db=p.Database(s.database_path,s.hmac_key)
if sys.argv[1]=='seed':
    db.create_proxy_user('migration-fixture')
    db.apply_traffic_batch('a'*32,{'migration-fixture':{'tx':123,'rx':456}})
with db._connect() as c:
    rows=[tuple(r) for r in c.execute('SELECT id,name,token_fingerprint,hex(token_seed),tx_bytes,rx_bytes FROM proxy_users ORDER BY id')]
print(hashlib.sha256(json.dumps(rows).encode()).hexdigest())
PY
runuser -u hy2panel --preserve-environment -- python3 /workspace/legacy_identity.py seed > /workspace/legacy-before.sha
systemctl start hysteria2-panel.service
unset ADMIN_USER ADMIN_PASSWORD
HY2PANEL_AUTO_UPDATE=1 PANEL_REF="${candidate_ref}" bash /workspace/install.sh
runuser -u hy2panel --preserve-environment -- python3 /workspace/legacy_identity.py verify > /workspace/legacy-after.sha
cmp /workspace/legacy-before.sha /workspace/legacy-after.sha
[[ "$(python3 /opt/hysteria2-panel/hysteria2_panel.py accounting-mode)" == cumulative-v1 ]]
curl -fsS "http://127.0.0.1:${PANEL_PORT}/readyz"
old_sha="$(sha256sum /opt/hysteria2-panel/bin/hysteria | cut -d' ' -f1)"
awk '
  { print }
  $0 == "install -o root -g root -m 0755 \"${TMP_DIR}/hysteria\" /opt/hysteria2-panel/bin/hysteria" {
    print "printf broken >> /opt/hysteria2-panel/bin/hysteria"
    print "false"
  }
' /workspace/install.sh > /workspace/install-fail.sh
if HY2PANEL_AUTO_UPDATE=1 PANEL_REF="${candidate_ref}" bash /workspace/install-fail.sh; then
  echo "injected upgrade failure unexpectedly succeeded" >&2
  exit 1
fi
[[ "$(sha256sum /opt/hysteria2-panel/bin/hysteria | cut -d' ' -f1)" == "${old_sha}" ]]
test ! -e /var/backups/hysteria2-panel/.upgrade-active
runuser -u hy2panel --preserve-environment -- python3 /workspace/legacy_identity.py verify > /workspace/legacy-rollback.sha
cmp /workspace/legacy-before.sha /workspace/legacy-rollback.sha
curl -fsS "http://127.0.0.1:${PANEL_PORT}/readyz"
echo 'legacy upgrade and failure rollback preserve identities and accounting: PASS'
