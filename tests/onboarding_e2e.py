"""Run the generated one-click installer against clean, isolated systemd nodes.

Linux Docker required. No host service or firewall is modified. Only fixture
asset URLs and the signature trust anchor change: the installer remains signed
by a real disposable Cosign key. Production OIDC is checked in release CI.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
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
    with tempfile.TemporaryDirectory(prefix='hy2-onboarding-e2e-') as directory:
        root = Path(directory)
        assets = root/'assets'
        assets.mkdir()
        for name in ('node_agent.py', 'tcp_probe.py'):
            shutil.copy2(ROOT/name, assets/name)
        download('https://github.com/sigstore/cosign/releases/download/v3.1.3/cosign-linux-amd64',
                 assets/'cosign', NodeEnrollmentService.COSIGN_SHA_AMD64)
        download('https://github.com/apernet/hysteria/releases/download/app/v2.12.1/hysteria-linux-amd64',
                 assets/'hysteria-linux-amd64', DataPlaneBootstrapService.HYSTERIA_SHA256['amd64'])
        installer = (ROOT/'install.sh').read_text()
        installer = installer.replace('https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/',
                                      'https://panel.e2e.test:19998/assets/')
        installer = installer.replace('https://github.com/apernet/hysteria/releases/download/app/v${HYSTERIA_VERSION}/hysteria-linux',
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
                shutil.copytree(assets, case/'assets')
                for name in ('tls.crt', 'tls.key', 'cosign.pub'):
                    shutil.copy2(root/name, case/name)
                panel, node = 'hy2-panel-'+suffix, 'hy2-node-'+suffix
                for name, ip, image in [(panel, '11.250.85.2', 'hy2-onboarding-controller'),
                                        (node, '11.250.85.3', 'hy2-onboarding-node')]:
                    run('docker', 'run', '-d', '--privileged', '--cgroupns=host',
                        '--name', name, '--hostname', name, '--network', network, '--ip', ip,
                        '--tmpfs', '/run', '--tmpfs', '/run/lock',
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
                run('docker', 'exec', '-d', '-e', 'TEST_TIER='+tier,
                    '-e', 'TEST_HOPPING='+str(int(hopping)), panel, 'sh', '-c',
                    'python3 /workspace/tests/onboarding_e2e_panel.py serve > /fixture/panel.log 2>&1')
                wait(lambda: (case/'join.sh').exists())
                with (case/'install.log').open('w') as log:
                    run('docker', 'exec', node, 'bash', '/fixture/join.sh', stdout=log, stderr=subprocess.STDOUT, timeout=900)
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
            for path in root.glob('*/**/*.log'):
                print('LOG:', path.name, flush=True)
                print(path.read_text(errors='replace')[-24000:], flush=True)
            raise
        finally:
            for name in containers:
                subprocess.run(['docker','rm','-f',name], capture_output=True)
            subprocess.run(['docker','network','rm',network], capture_output=True)


if __name__ == '__main__':
    main()
