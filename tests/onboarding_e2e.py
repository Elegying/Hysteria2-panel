"""Run the generated one-click installer against clean, isolated systemd nodes.

Ephemeral Linux CI runner required. No host service or firewall is modified.
Global net.core sysctls use a narrow host bridge (unavailable inside a network
namespace); CI restores these after the test. Only fixture
asset URLs and the signature trust anchor change: the installer remains signed
by a real disposable Cosign key. Production OIDC is checked in release CI.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socketserver
import threading
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hy2panel.nodes import NodeEnrollmentService, DataPlaneBootstrapService  # noqa: E402


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def download(url, path, digest):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                path.write_bytes(response.read())
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError('download digest mismatch')
            path.chmod(0o755)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def wait(check, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(2)
    raise RuntimeError('onboarding acceptance deadline exceeded')


def main():
    suffix = uuid.uuid4().hex[:8]
    network = 'hy2-e2e-' + suffix
    containers = []
    bridges = []
    with tempfile.TemporaryDirectory(prefix='hy2-onboarding-e2e-') as directory:
        root = Path(directory)
        assets = root/'assets'
        assets.mkdir()
        for name in ('node_agent.py', 'tcp_probe.py'):
            shutil.copy2(ROOT/name, assets/name)
        download('https://github.com/sigstore/cosign/releases/download/v3.1.3/cosign-linux-amd64',
                 assets/'cosign', NodeEnrollmentService.COSIGN_SHA_AMD64)
        download('https://github.com/Elegying/Hysteria2-panel/releases/download/core-egress-v3/hysteria-linux-amd64',
                 assets/'hysteria-linux-amd64', DataPlaneBootstrapService.HYSTERIA_SHA256['amd64'])
        installer = (ROOT/'install.sh').read_text()
        installer = installer.replace('https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/',
                                      'https://panel.e2e.test:19998/assets/')
        installer = installer.replace('https://github.com/Elegying/Hysteria2-panel/releases/download/core-egress-v3/hysteria-linux',
                                      'https://panel.e2e.test:19998/assets/hysteria-linux')
        (assets/'install.sh').write_text(installer)
        env = {**os.environ, 'COSIGN_PASSWORD': ''}
        run(str(assets/'cosign'), 'generate-key-pair', '--output-key-prefix', str(root/'cosign'), env=env)
        run(str(assets/'cosign'), 'sign-blob', '--yes', '--use-signing-config=false',
            '--key', str(root/'cosign.key'), '--bundle', str(assets/'install.sh.sigstore.json'),
            str(assets/'install.sh'), env=env)
        run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
            '-keyout', str(root/'tls.key'), '-out', str(root/'tls.crt'),
            '-subj', '/CN=panel.e2e.test', '-addext',
            'subjectAltName=DNS:panel.e2e.test,DNS:node.e2e.test,DNS:local.e2e.test',
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Minimal node: curl is deliberately absent to exercise bootstrapping.
        (root/'Dockerfile').write_text('''FROM hy2-onboarding-systemd
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
''')
        run('docker', 'build', '-f', str(ROOT/'tests/installer_e2e.Dockerfile'), '-t', 'hy2-onboarding-systemd', str(ROOT))
        run('docker', 'build', '-t', 'hy2-onboarding-node', str(root))
        (root/'Dockerfile').write_text('''FROM hy2-onboarding-node
RUN apt-get update && apt-get install -y --no-install-recommends python3 openssl curl iproute2 nftables && rm -rf /var/lib/apt/lists/*
''')
        run('docker', 'build', '-t', 'hy2-onboarding-controller', str(root))
        run('docker', 'network', 'create', '--subnet', '11.250.85.0/24', network)
        try:
            for tier, hopping in [('standard', False), ('premium', True)]:
                case = root/tier
                case.mkdir()
                # Linux hides or makes global net.core tuning read-only in network namespaces.
                # Forward only these three real kernel knobs to the ephemeral CI host.
                class SysctlHandler(socketserver.StreamRequestHandler):
                    def handle(self):
                        args = json.loads(self.rfile.readline(4096))
                        assert len(args) == 2 and args[0] in {'-n', '-w'}
                        assert re.fullmatch(r'net\.core\.(?:default_qdisc|rmem_max|wmem_max)(?:=[A-Za-z0-9_-]{1,40})?', args[1])
                        result = subprocess.run(['sudo', 'sysctl', *args], capture_output=True, text=True)
                        self.wfile.write(json.dumps([result.returncode, result.stdout, result.stderr]).encode()+b'\n')
                bridge = socketserver.UnixStreamServer(str(case/'sysctl.sock'), SysctlHandler)
                bridges.append(bridge)
                threading.Thread(target=bridge.serve_forever, daemon=True).start()
                (case/'sysctl.sock').chmod(0o666)
                (case/'sysctl-wrapper').write_text("""#!/usr/bin/python3
import json,os,socket,sys
args=sys.argv[1:]
if len(args)==2 and args[1].split('=',1)[0] in {'net.core.default_qdisc','net.core.rmem_max','net.core.wmem_max'}:
    with socket.socket(socket.AF_UNIX) as client:
        client.connect('/fixture/sysctl.sock')
        client.sendall(json.dumps(args).encode()+b'\\n')
        result=json.loads(client.makefile('rb').readline())
    sys.stdout.write(result[1]); sys.stderr.write(result[2]); sys.exit(result[0])
os.execv('/usr/sbin/sysctl.real', ['sysctl', *args])
""")
                shutil.copytree(assets, case/'assets')
                for name in ('tls.crt', 'tls.key', 'cosign.pub'):
                    shutil.copy2(root/name, case/name)
                panel, node = 'hy2-panel-'+suffix, 'hy2-node-'+suffix
                for name, ip, image in [(panel, '11.250.85.2', 'hy2-onboarding-controller'),
                                        (node, '11.250.85.3', 'hy2-onboarding-node')]:
                    run('docker', 'run', '-d', '--privileged', '--cgroupns=host',
                        '--name', name, '--hostname', name, '--network', network, '--ip', ip,
                        '--tmpfs', '/run', '--tmpfs', '/run/lock',
                        *(['--memory', '512m', '--memory-swap', '512m', '--tmpfs', '/tmp:exec,size=256m,mode=1777'] if name == node else []),
                        '-v', '/sys/fs/cgroup:/sys/fs/cgroup:rw',
                        '-v', str(ROOT)+':/workspace:ro', '-v', str(case)+':/fixture',
                        '--add-host', 'panel.e2e.test:11.250.85.2',
                        '--add-host', 'local.e2e.test:11.250.85.2',
                        '--add-host', 'node.e2e.test:11.250.85.3', image)
                    containers.append(name)
                    wait(lambda: subprocess.run(['docker','exec',name,'systemctl','is-system-running'], capture_output=True, text=True).stdout.strip() in {'running', 'degraded'})
                    run('docker', 'exec', name, 'sh', '-c',
                        'cp /fixture/tls.crt /usr/local/share/ca-certificates/hy2-e2e.crt && update-ca-certificates')
                run('docker', 'exec', node, 'sh', '-c', '! command -v curl')
                run('docker', 'exec', node, 'sh', '-c',
                    'dpkg-divert --add --rename --divert /usr/sbin/sysctl.real /usr/sbin/sysctl && cp /fixture/sysctl-wrapper /usr/sbin/sysctl && chmod 755 /usr/sbin/sysctl')
                run('docker', 'exec', '-d', '-e', 'TEST_TIER='+tier,
                    '-e', 'TEST_HOPPING='+str(int(hopping)), panel, 'sh', '-c',
                    'python3 /workspace/tests/onboarding_e2e_panel.py serve > /fixture/panel.log 2>&1')
                wait(lambda: (case/'join.sh').exists())
                with (case/'install.log').open('w') as log:
                    process = subprocess.Popen(['docker', 'exec', node, 'bash', '/fixture/join.sh'],
                        stdout=log, stderr=subprocess.STDOUT)
                    try:
                        deadline = time.monotonic() + 600
                        while process.poll() is None:
                            failed = subprocess.run(['docker','exec',node,'systemctl','is-failed','--quiet',
                                'hysteria2-panel-node-onboarding.service'], capture_output=True)
                            if failed.returncode == 0:
                                raise RuntimeError('first onboarding attempt failed; refusing to hide it behind timer retries')
                            if time.monotonic() >= deadline:
                                raise RuntimeError('generated join command exceeded acceptance deadline')
                            time.sleep(2)
                        if process.returncode:
                            raise RuntimeError('generated join command failed')
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            process.wait(timeout=10)
                wait(lambda: subprocess.run(['docker','exec',panel,'python3','/workspace/tests/onboarding_e2e_panel.py','assert'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0)
                run('docker','exec',panel,'python3','/workspace/tests/onboarding_e2e_probe.py')
                # Actual container restart: /run and kernel NAT state are rebuilt.
                run('docker','restart',node)
                wait(lambda: subprocess.run(['docker','exec',node,'systemctl','is-active','--quiet',
                    'hysteria2-panel-node-control.service','hysteria2-panel-node-port-hopping.service']).returncode == 0)
                run('docker','exec',panel,'python3','/workspace/tests/onboarding_e2e_probe.py')
                run('docker','exec',panel,'python3','/workspace/tests/onboarding_e2e_panel.py','disconnect')
                wait(lambda: subprocess.run(['docker','exec',node,'test','!','-d','/etc/hysteria2-panel-node']).returncode == 0, 180)
                check = subprocess.run(['docker','exec',node,'nft','list','table','inet','hy2_port_hopping'],capture_output=True)
                assert check.returncode != 0, 'uninstall left NAT rules behind'
                run('docker','exec',panel,'python3','/workspace/tests/onboarding_e2e_probe.py','identity-only')
                print(json.dumps({'tier':tier,'hopping':hopping,'install_restart_subscription_uninstall':'passed'}), flush=True)
                for name in (node,panel):
                    run('docker','rm','-f',name)
                    containers.remove(name)
        except Exception:
            for name in containers:
                subprocess.run(['docker','exec',name,'sysctl', 'net.core.rmem_max',
                    'net.core.wmem_max', 'net.core.default_qdisc', 'net.ipv4.tcp_available_congestion_control'])
                subprocess.run(['docker','exec',name,'journalctl','--no-pager','-n','150',
                    '-u','hysteria2-panel-node-onboarding.service',
                    '-u','hysteria2-panel-node-auth.service',
                    '-u','hysteria2-panel-node-control.service'])
            for path in root.glob('*/**/*.log'):
                print('LOG:', path.name, flush=True)
                print(path.read_text(errors='replace')[-24000:], flush=True)
            raise
        finally:
            for bridge in bridges:
                bridge.shutdown()
                bridge.server_close()
            for name in containers:
                subprocess.run(['docker','rm','-f',name], capture_output=True)
            subprocess.run(['docker','network','rm',network], capture_output=True)


if __name__ == '__main__':
    main()
