"""Real central protocol server for isolated Docker onboarding acceptance tests.

Only the empty local-machine statistics and the external trace destination are
fixtures. Registration, signatures, control/auth, accounting, subscriptions and
node installation use production code. Test assets use a separate local Cosign
key; production GitHub OIDC verification is covered by the release workflow.
"""
import json
import os
from pathlib import Path
import ssl
import sys
import threading
import time

sys.path.insert(0, '/workspace')
from hysteria2_panel import Database, PanelApplication, PanelHandler, make_panel_server
from hy2panel.distributed import DistributedControlService
from hy2panel.nodes import (NodeEnrollmentService, NodeHeartbeatService,
    DataPlaneBootstrapService, HysteriaIdentityProvider, HysteriaCanaryRunner,
    NodeDnsAdmissionReconciler)
from hy2panel.version import PANEL_VERSION

ROOT = Path('/fixture')
DB = ROOT / 'panel.db'
KEY = b'onboarding-test-key-32-bytes-only!'
URL = 'https://panel.e2e.test:19998'


def database():
    return Database(DB, KEY)


def main():
    db = database()
    if sys.argv[1] == 'disconnect':
        record = json.loads((ROOT / 'case.json').read_text())
        db.request_node_disconnect(record['node_id'], 'ci')
        return
    if sys.argv[1] == 'assert':
        record = json.loads((ROOT / 'case.json').read_text())
        node = db.get_node_for_heartbeat(record['node_id'])
        assert node['data_plane_state'] == 'dns_admitted', node['data_plane_state']
        assert node['listen_port'] == 19999
        assert node['subscription_port'] == (443 if record['hopping'] else 19999)
        print('Real node registered, bootstrapped, authenticated and DNS-admitted')
        return
    db.initialize()
    db.upsert_admin('ci', 'isolated-acceptance-password')
    tier = os.environ.get('TEST_TIER', 'standard')
    hopping = os.environ.get('TEST_HOPPING', '0') == '1'
    enroll = NodeEnrollmentService(db, URL, PANEL_VERSION)
    issued = enroll.create('acceptance-node', '11.250.85.3', 30, 'ci',
        tier=tier, region='hk' if tier == 'premium' else '',
        subscription_host='node.e2e.test', port_hopping=hopping)
    user = db.create_proxy_user('acceptance-user', user_type=int(tier == 'premium'), device_limit=100)
    subscription = db.ensure_subscription(user['id'])
    normal_user = db.create_proxy_user('other-tier', user_type=int(tier != 'premium'))
    identity = HysteriaIdentityProvider(ROOT/'tls.crt', ROOT/'tls.key', lambda: 'full')
    canary = HysteriaCanaryRunner('node.e2e.test', hysteria_path='/fixture/assets/hysteria-linux-amd64')
    canary.TRACE_URLS = {4: URL+'/cdn-cgi/trace', 6: URL+'/cdn-cgi/trace'}
    def local_state():
        now = int(time.time())
        return {'online': {}, 'observedAt': now, 'trafficAckedAt': now}
    app = PanelApplication(db, 'local.e2e.test', 24443,
        identity()['certificateDerSha256'], object(), secure_cookies=True,
        node_enrollment_service=enroll, node_heartbeat_service=NodeHeartbeatService(db),
        node_control_service=DistributedControlService(db, local_state_provider=local_state),
        data_plane_bootstrap_service=DataPlaneBootstrapService(db, URL, PANEL_VERSION,
            identity_provider=identity, canary_runner=canary, hysteria_port=24443))
    app.subscription_base_url = URL
    class Handler(PanelHandler):
        def do_GET(self):
            if self.path == '/cdn-cgi/trace':
                value = ('ip='+self.client_address[0]+'\n').encode()
            elif self.path.startswith('/assets/'):
                path = (ROOT/'assets'/self.path[8:]).resolve()
                if not path.is_relative_to((ROOT/'assets').resolve()) or not path.is_file():
                    self.send_error(404)
                    return
                value = path.read_bytes()
            else:
                return super().do_GET()
            self.send_response(200)
            self.send_header('Content-Length', str(len(value)))
            self.end_headers()
            self.wfile.write(value)
    server = make_panel_server(('0.0.0.0', 19998), app)
    server.RequestHandlerClass = Handler
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ROOT/'tls.crt', ROOT/'tls.key')
    server.tls_context = context
    command = issued['deploymentCommand']
    command = command.replace('https://raw.githubusercontent.com/Elegying/Hysteria2-panel/v'+PANEL_VERSION+'/install.sh', URL+'/assets/install.sh')
    command = command.replace('https://github.com/Elegying/Hysteria2-panel/releases/download/v'+PANEL_VERSION+'/install.sh.sigstore.json', URL+'/assets/install.sh.sigstore.json')
    command = command.replace('https://github.com/sigstore/cosign/releases/download/v3.1.3/$cosign_asset', URL+'/assets/cosign')
    import re
    command, replacements = re.subn(
        r"--certificate-identity\s+'[^']+'\s+--certificate-oidc-issuer\s+https://token.actions.githubusercontent.com",
        '--key /fixture/cosign.pub --insecure-ignore-tlog', command)
    assert replacements == 1, 'fixture signature trust anchor was not selected'
    (ROOT/'join.sh').write_text(command)
    (ROOT/'join.sh').chmod(0o600)
    (ROOT/'case.json').write_text(json.dumps({'node_id': issued['nodeId'],
        'hopping': hopping, 'subscription': subscription['token'],
        'password': user['token'], 'wrong_password': normal_user['token']}))
    (ROOT/'case.json').chmod(0o600)
    reconciler = NodeDnsAdmissionReconciler(db, 'local.e2e.test')
    def reconcile():
        while True:
            reconciler.reconcile()
            # The fixture panel has no local proxy; its empty local collector is
            # fresh. Remote accounting still comes only from the real agent.
            with app.usage_manager._user_usage_lock:
                now = int(time.time())
                app.usage_manager._user_usage_checkpoint = (now, now, {})
            time.sleep(1)
    threading.Thread(target=reconcile, daemon=True).start()
    server.serve_forever()


if __name__ == '__main__':
    main()
