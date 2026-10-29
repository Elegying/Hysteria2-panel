"""Read the original subscription and connect through a real Hysteria client."""
import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, '/workspace')
from hysteria2_panel import Database
from hy2panel.nodes import HysteriaCanaryRunner

root = Path('/fixture')
record = json.loads((root/'case.json').read_text())
db = Database(root/'panel.db', b'onboarding-test-key-32-bytes-only!')
user = db.get_proxy_user_by_name('acceptance-user')
subscription = db.get_subscription(user_id=user['id'])
assert db.recover_subscription_token(subscription['id']) == record['subscription']
if len(sys.argv) > 1 and sys.argv[1] == 'identity-only':
    print('Original user and subscription identity preserved after node removal')
    raise SystemExit(0)
url = 'https://panel.e2e.test:19998/sub/'+record['subscription']
request = urllib.request.Request(url, headers={'User-Agent':'SSRVPN/acceptance'})
with urllib.request.urlopen(request, timeout=10) as response:
    config = json.load(response)
    assert 'total=' in response.headers['Subscription-Userinfo']
node = next(p for p in config['proxies'] if p['server'] == 'node.e2e.test')
assert node['password'] == record['password']
assert node['port'] == (443 if record['hopping'] else 19999)
if record['hopping']:
    assert node['ports'] == '20000-50000'
pin = node.get('fingerprint', node.get('pinSHA256'))
runner = HysteriaCanaryRunner('node.e2e.test', hysteria_path='/fixture/assets/hysteria-linux-amd64')
runner.TRACE_URLS = {4:'https://panel.e2e.test:19998/cdn-cgi/trace'}
runner(node_ip='11.250.85.3', main_port=19999, token=node['password'],
       pin_sha256=pin, port_hopping=record['hopping'])
try:
    runner._check_entrypoint('11.250.85.3', node['port'], record['wrong_password'],
                            pin, runner.TRACE_URLS[4])
except RuntimeError:
    pass
else:
    raise AssertionError('Cross-tier account unexpectedly authenticated')
print('Original subscription, user proxy traffic and tier isolation verified')
