"""Real idle QUIC upgrade and SIGKILL cleanup on a disposable systemd host."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from runtime_lab import environment, run


def main():
    if os.geteuid() != 0 or os.environ.get('container') != 'docker':
        raise SystemExit('Only run on the disposable installer container')
    values = environment()
    if values['HY2PANEL_PUBLIC_HOST'] != '127.0.0.1' or values['HY2PANEL_PANEL_PORT'] != '31998':
        raise SystemExit('Refusing non-fixture settings')
    sys.path.insert(0, '/opt/hysteria2-panel')
    import hysteria2_panel as panel
    settings = panel.Settings.from_mapping(values)
    db = panel.Database(settings.database_path, settings.hmac_key)
    user = db.create_proxy_user('idle-upgrade-quic', device_limit=10, allow_udp_443=True)
    token = user['token']
    payload = b'upgrade-quic-regression\n' * 4096
    address = '198.18.0.1'
    if address not in run('ip', '-4', 'address', 'show', 'dev', 'lo'):
        run('ip', 'address', 'add', address + '/32', 'dev', 'lo')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer((address, 38080), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    clients = []
    logs = []
    try:
        with tempfile.TemporaryDirectory(prefix='hy2-idle-quic-') as directory:
            for index, port in enumerate((31999, 443)):
                config = Path(directory) / ('client-' + str(port) + '.json')
                config.write_text(json.dumps({
                    'server': '127.0.0.1:' + str(port), 'auth': token,
                    'tls': {'insecure': True, 'pinSHA256': settings.cert_pin},
                    'quic': {'keepAlivePeriod': '2s'},
                    'tcpForwarding': [{'listen': '127.0.0.1:' + str(38081 + index),
                                       'remote': address + ':38080'}],
                }))
                config.chmod(0o600)
                log = (Path(directory) / ('client-' + str(port) + '.log')).open('wb')
                logs.append(log)
                clients.append(subprocess.Popen(['/opt/hysteria2-panel/bin/hysteria', 'client', '-c', str(config)],
                                                stdin=subprocess.DEVNULL, stdout=log, stderr=log))

            def transfer():
                for index in range(2):
                    deadline = time.monotonic() + 25
                    while True:
                        connection = http.client.HTTPConnection('127.0.0.1', 38081 + index, timeout=3)
                        try:
                            connection.request('GET', '/')
                            response = connection.getresponse()
                            assert response.status == 200 and response.read() == payload
                            break
                        except (OSError, http.client.HTTPException):
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(.2)
                        finally:
                            connection.close()

            transfer()
            time.sleep(3)
            for url in (settings.stats_url, settings.stats_443_url):
                assert panel.HysteriaStatsClient(url, settings.stats_secret).online().get('idle-upgrade-quic', 0) > 0
            before = db.get_proxy_user_by_name('idle-upgrade-quic')
            started = time.monotonic()
            with open('/tmp/upgrade-idle-quic.log', 'w') as log:
                subprocess.run(['bash', '/workspace/install.sh'], check=True, timeout=600,
                               env=dict(os.environ, HY2PANEL_AUTO_UPDATE='1'), stdout=log, stderr=log)
            output = Path('/tmp/upgrade-idle-quic.log').read_text()
            assert 'temporarily isolating UDP ingress' in output, 'idle QUIC fallback was not exercised'
            assert 'sessions drained; temporary UDP isolation removed' in output
            assert 'hy2_drain_' not in run('nft', 'list', 'tables')
            after = db.get_proxy_user_by_name('idle-upgrade-quic')
            assert db.recover_proxy_token(after['id']) == token
            assert after['tx_bytes'] >= before['tx_bytes'] and after['rx_bytes'] >= before['rx_bytes']
            assert after['tx_bytes'] + after['rx_bytes'] >= 2 * len(payload)
            transfer()  # Both entrypoints reconnect with the original identity.
            print(json.dumps({'real_idle_quic_upgrade': 'passed', 'ports': [31999, 443],
                              'payload_bytes_per_port': len(payload),
                              'seconds': round(time.monotonic() - started, 3)}), flush=True)
    finally:
        for client in clients:
            client.terminate()
            client.wait(timeout=10)
        for log in logs:
            log.close()
        server.shutdown()
        server.server_close()

    # Kill the guard owner: the kernel lease and independent systemd cleanup
    # must survive. Never use a production port for this separate fault test.
    script = (
        "import sys,time; sys.path.insert(0,'/opt/hysteria2-panel'); "
        "from hy2panel.operations import UpgradeIngressDrain; "
        "g=UpgradeIngressDrain([38999]); g.__enter__(); "
        "print(g.table,flush=True); time.sleep(300)"
    )
    process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, text=True)
    try:
        table = process.stdout.readline().strip()
        assert table.startswith('hy2_drain_')
        process.kill()
        process.wait(timeout=10)
        # The timer runs at 150s: prove the kernel independently unblocks the
        # port earlier, even though the empty table still exists.
        time.sleep(125)
        rules = json.loads(run('nft', '-j', 'list', 'set', 'inet', table, 'ports'))
        sets = [item['set'] for item in rules['nftables'] if 'set' in item]
        assert len(sets) == 1 and not sets[0].get('elem'), 'kernel lease did not expire'
        deadline = time.monotonic() + 165
        while table in run('nft', 'list', 'tables'):
            assert time.monotonic() < deadline, 'SIGKILL left an orphan drain table'
            time.sleep(2)
        print(json.dumps({'drain_guard_sigkill_cleanup': 'passed'}), flush=True)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        process.stdout.close()


if __name__ == '__main__':
    main()
