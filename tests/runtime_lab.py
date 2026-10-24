"""Opt-in experiments on a disposable, installed Linux panel; never production.

Run inside the named lab container after installer_e2e.sh. Results contain no
tokens or private material. HTTP requests use the actual installed services.
"""

import argparse
import concurrent.futures
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import shlex
import ssl
import subprocess
import sys
import threading
import tempfile
import time
import urllib.parse


ROOT = Path('/opt/hysteria2-panel')
ENV = Path('/etc/hysteria2-panel/panel.env')
MARKER = Path('/run/hy2-disposable-runtime-lab')


def run(*args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True).strip()


def environment():
    return {key: shlex.split(value)[0] if value else ''
            for line in ENV.read_text().splitlines() if line.startswith('HY2PANEL_')
            for key, value in [line.split('=', 1)]}


def guard():
    if (os.geteuid() != 0 or os.environ.get('container') != 'docker'
            or not MARKER.is_file() or MARKER.read_text().strip() != 'synthetic-only'
            or not Path('/workspace/tests/installer_e2e.sh').is_file()):
        raise SystemExit('Requires an explicitly marked disposable installer container')
    values = environment()
    if values['HY2PANEL_PANEL_PORT'] != '31998' or values['HY2PANEL_PUBLIC_HOST'] != '127.0.0.1':
        raise SystemExit('Refusing a non-fixture deployment')
    sys.path.insert(0, str(ROOT))
    import hysteria2_panel as panel
    return panel, panel.Settings.from_mapping(values)


def request(path, method='GET', body=None, headers=None, auth=False):
    if auth:
        connection = http.client.HTTPConnection('127.0.0.1', 31996, timeout=12)
    else:
        context = ssl.create_default_context(cafile='/etc/hysteria2-panel/lab-panel.crt')
        connection = http.client.HTTPSConnection('127.0.0.1', 31998, context=context, timeout=20)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def ready(timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if (not (ENV.parent / '.restore-active').exists()
                    and request('/readyz')[0] == 200):
                return
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(0.2)
    raise RuntimeError('Installed service did not become ready')


def enable_tls():
    cert = ENV.parent / 'lab-panel.crt'
    key = ENV.parent / 'lab-panel.key'
    if not cert.exists():
        run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
            '-subj', '/CN=panel.runtime.test', '-addext', 'subjectAltName=DNS:panel.runtime.test,IP:127.0.0.1',
            '-keyout', str(key), '-out', str(cert))
        run('chown', 'root:hy2panel', str(key))
        key.chmod(0o640)
    changes = {'HY2PANEL_PANEL_SCHEME': 'https', 'HY2PANEL_PANEL_PUBLIC_HOST': 'panel.runtime.test',
               'HY2PANEL_PANEL_TLS_CERT': str(cert), 'HY2PANEL_PANEL_TLS_KEY': str(key)}
    original = ENV.read_text().splitlines()
    ENV.write_text('\n'.join([line for line in original if line.split('=', 1)[0] not in changes]
                            + [k + '=' + v for k, v in changes.items()]) + '\n')
    run('cp', str(cert), '/usr/local/share/ca-certificates/hy2-runtime-lab.crt')
    run('update-ca-certificates')
    run('systemctl', 'restart', 'hysteria2-panel.service')
    ready()


def database(panel, settings):
    return panel.Database(settings.database_path, settings.hmac_key)


def sessions(db):
    with db._connect() as connection:
        admin_id = connection.execute('SELECT id FROM admins ORDER BY id LIMIT 1').fetchone()[0]
    token, csrf = db.create_session(admin_id)
    return {'Cookie': 'hy2panel_session=' + token}, csrf


def mobile_login():
    status, body = request('/api/v1/mobile/auth/login', 'POST', json.dumps({
        'username': 'ci-admin', 'password': 'ci-only-password-42',
        'deviceId': 'runtime-lab', 'deviceName': 'Disposable lab',
    }), {'Content-Type': 'application/json'})
    if status != 200:
        raise RuntimeError('Fixture mobile login failed: {}'.format(status))
    payload = json.loads(body)
    return {'Authorization': 'Bearer ' + payload['data']['accessToken']}


def quantile(values, fraction):
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] * 1000, 2) if ordered else None


def process_metrics():
    pid = run('systemctl', 'show', '-p', 'MainPID', '--value', 'hysteria2-panel.service')
    fields = Path('/proc/' + pid + '/stat').read_text().split()
    memory = next(line for line in Path('/proc/' + pid + '/status').read_text().splitlines()
                  if line.startswith('VmRSS:'))
    return {'cpu_seconds': (int(fields[13]) + int(fields[14])) / os.sysconf('SC_CLK_TCK'),
            'rss_mib': round(int(memory.split()[1]) / 1024, 2)}


def capacity(panel, settings, args):
    db = database(panel, settings)
    if args.reset_load_users:
        with db._connect() as connection:
            if connection.execute("SELECT 1 FROM proxy_users WHERE name GLOB 'load-[0-9]*' "
                                  "AND (tx_bytes != 0 OR rx_bytes != 0) LIMIT 1").fetchone():
                raise RuntimeError('Refusing to reset load fixtures with real accounted traffic')
            connection.execute("DELETE FROM local_auth_leases WHERE user_name GLOB 'load-[0-9]*'")
            connection.execute("DELETE FROM proxy_users WHERE name GLOB 'load-[0-9]*'")
    auth_headers = {'Content-Type': 'application/json'}
    results = []
    for size in args.users:
        for index in range(size):
            name = 'load-{:05d}'.format(index)
            if not db.get_proxy_user_by_name(name):
                db.create_proxy_user(name, device_limit=100, allow_udp_443=True)
        users = [row for row in db.list_proxy_users_for_usage() if row['name'].startswith('load-')]
        tokens = [db.recover_proxy_token(row['id']) for row in users]
        headers = mobile_login()
        for concurrency in args.concurrency:
            for workload in ('auth', 'users', 'mixed'):
                # Separate scenarios so leases from earlier runs do not exhaust fixture quotas.
                with db._connect() as connection:
                    connection.execute('DELETE FROM local_auth_leases')
                ready()
                before = process_metrics()
                started = time.monotonic()
                deadline = started + args.seconds
                barrier = threading.Barrier(concurrency + 1)

                def worker(index):
                    samples = []
                    sequence = index
                    barrier.wait()
                    while ((started + sequence / args.rate < deadline) if args.rate
                           else time.monotonic() < deadline):
                        due = started + sequence / args.rate if args.rate else time.monotonic()
                        if args.rate:
                            time.sleep(max(0, due - time.monotonic()))
                        kind = 'auth' if workload == 'auth' or (workload == 'mixed' and index % 2 == 0) else 'users'
                        begin = due if args.rate else time.monotonic()
                        outcome = 'transport_error'
                        try:
                            if kind == 'auth':
                                status, body = request('/auth', 'POST', json.dumps({
                                    'auth': tokens[sequence % len(tokens)], 'tx': 0}), auth_headers, auth=True)
                                outcome = 'allowed' if status == 200 and json.loads(body).get('ok') else 'denied'
                            else:
                                status, body = request('/api/v1/mobile/users', headers=headers)
                                outcome = ('ok' if json.loads(body)['data']['available'] else 'unavailable') if status == 200 else 'http_' + str(status)
                        except (OSError, http.client.HTTPException, ValueError):
                            pass
                        samples.append((kind, time.monotonic() - begin, outcome))
                        sequence += concurrency
                    return samples

                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = [pool.submit(worker, index) for index in range(concurrency)]
                    barrier.wait()
                    samples = [sample for future in futures for sample in future.result()]
                elapsed = time.monotonic() - started
                after = process_metrics()
                for kind in sorted({sample[0] for sample in samples}):
                    selected = [sample for sample in samples if sample[0] == kind]
                    outcomes = {outcome: sum(sample[2] == outcome for sample in selected)
                                for outcome in sorted({sample[2] for sample in selected})}
                    result = {'users': len(users), 'concurrency': concurrency, 'workload': workload,
                              'offered_rps': args.rate or None,
                              'endpoint': kind, 'requests': len(selected), 'outcomes': outcomes,
                              'elapsed_seconds': round(elapsed, 3), 'rps': round(len(selected) / elapsed, 2),
                              'p50_ms': quantile([x[1] for x in selected], .5),
                              'p95_ms': quantile([x[1] for x in selected], .95),
                              'p99_ms': quantile([x[1] for x in selected], .99),
                              'panel_cpu_seconds': round(after['cpu_seconds'] - before['cpu_seconds'], 3),
                              'panel_rss_mib': after['rss_mib']}
                    results.append(result)
                    print(json.dumps(result), flush=True)
                Path(args.output).write_text(json.dumps(results, indent=2) + '\n')
    return results


def restore_upload(db, archive):
    headers, csrf = sessions(db)
    headers.update({'X-HY2Panel-CSRF': csrf, 'Content-Type': 'application/zip', 'Accept': 'application/json'})
    status, _ = request('/restore', 'POST', archive, headers)
    if status != 202:
        raise RuntimeError('Restore upload failed: {}'.format(status))


def rows(db):
    return [(row['name'], row['enabled'], row['device_limit'], row['traffic_limit_bytes'], row['allow_udp_443'],
             row['tx_bytes'], row['rx_bytes'], db.recover_proxy_token(row['id']))
            for row in db.list_proxy_users_for_usage()]


def data_plane(settings, db):
    """Real QUIC to both installed Hysteria processes, with a lab-only target."""
    address = '198.18.0.1'
    addresses = run('ip', '-4', 'address', 'show', 'dev', 'lo')
    if address not in addresses:
        run('ip', 'address', 'add', address + '/32', 'dev', 'lo')
    payload = b'isolated-quic-fixture\n' * 32768

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer((address, 38080), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    user = db.get_proxy_user_by_name('recovery-probe')
    token = db.recover_proxy_token(user['id'])
    result = []
    try:
        for port in (31999, 443):
            with tempfile.TemporaryDirectory(prefix='hy2-lab-quic-') as temporary:
                config = Path(temporary) / 'client.json'
                config.write_text(json.dumps({
                    'server': '127.0.0.1:' + str(port), 'auth': token,
                    'tls': {'insecure': True, 'pinSHA256': settings.cert_pin},
                    'tcpForwarding': [{'listen': '127.0.0.1:38081', 'remote': address + ':38080'}],
                }))
                config.chmod(0o600)
                with (Path(temporary) / 'client.log').open('wb') as log:
                    process = subprocess.Popen([str(ROOT / 'bin/hysteria'), 'client', '-c', str(config)],
                                               stdin=subprocess.DEVNULL, stdout=log, stderr=log)
                    start = time.monotonic()
                    try:
                        deadline = start + 15
                        while True:
                            connection = http.client.HTTPConnection('127.0.0.1', 38081, timeout=3)
                            try:
                                connection.request('GET', '/')
                                response = connection.getresponse()
                                received = response.read()
                                if response.status != 200 or received != payload:
                                    raise RuntimeError('Real QUIC payload mismatch')
                                break
                            except (OSError, http.client.HTTPException):
                                if time.monotonic() >= deadline or process.poll() is not None:
                                    raise RuntimeError('Real QUIC fixture did not connect') from None
                                time.sleep(.1)
                            finally:
                                connection.close()
                        result.append({'port': port, 'verified_payload_bytes': len(received),
                                       'connect_and_transfer_seconds': round(time.monotonic() - start, 3)})
                    finally:
                        process.terminate()
                        process.wait(timeout=10)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    return result


def recovery(panel, settings, args):
    ready()
    db = database(panel, settings)
    if not db.get_proxy_user_by_name('recovery-probe'):
        db.create_proxy_user('recovery-probe', allow_udp_443=True)
    data_plane_before = data_plane(settings, db)
    db.add_traffic({'recovery-probe': {'tx': 123456, 'rx': 654321}})
    headers, csrf = sessions(db)
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    start = time.monotonic()
    status, archive = request('/backup', 'POST', urllib.parse.urlencode({'csrf': csrf}), headers)
    if status != 200 or not archive.startswith(b'PK'):
        raise RuntimeError('Web backup failed: {}'.format(status))
    baseline = rows(db)
    identity = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (settings.tls_cert, settings.tls_key)}
    backup_seconds = time.monotonic() - start
    db.add_traffic({'recovery-probe': {'tx': 111, 'rx': 222}})
    started = time.monotonic()
    restore_upload(db, archive)
    deadline = started + 120
    while time.monotonic() < deadline:
        try:
            if (not panel.RESTORE_ACTIVE_MARKER.exists() and rows(db) == baseline
                    and request('/readyz')[0] == 200):
                break
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(.2)
    else:
        raise RuntimeError('Restore did not converge to backed-up users and usage')
    result = {'scenario': 'web_backup_restore', 'users': len(baseline), 'backup_bytes': len(archive),
              'backup_seconds': round(backup_seconds, 3), 'rto_seconds': round(time.monotonic() - started, 3),
              'exact_users_tokens_and_usage': rows(db) == baseline,
              'tls_identity_preserved': all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
                                            for path, digest in identity.items())}
    if not result['tls_identity_preserved']:
        raise RuntimeError('Restored TLS identity changed')
    result['real_quic_before'] = data_plane_before
    result['real_quic_after'] = data_plane(settings, db)
    result['both_auth_entrypoints'] = True
    results = [result]
    Path(args.output).write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    # Subsequent faults restore the same snapshot, and verify exact rollback of
    # the currently committed source when interruption precedes disk-consistent.
    dropin_dir = Path('/etc/systemd/system/hysteria2-panel-restore.service.d')
    dropin_dir.mkdir(exist_ok=True)
    dropin = dropin_dir / '90-runtime-lab.conf'
    evidence = Path('/var/lib/hysteria2-panel/lab-crash-reached')
    try:
        for phase in ('prepared', 'replaced-database', 'disk-consistent'):
            ready()
            # Settle payloads from the preceding real QUIC check before defining
            # the state that an interrupted restore must roll back to.
            with panel.exclusive_maintenance_lock(panel.TRAFFIC_COLLECTION_LOCK_PATH,
                                                  blocking=True, expected_mode=0o640):
                panel.sync_traffic(settings)
            db.add_traffic({'recovery-probe': {'tx': 111, 'rx': 222}})
            before = rows(db)
            evidence.unlink(missing_ok=True)
            dropin.write_text('[Service]\nExecStart=\n'
                              'ExecStart=/usr/bin/python3 /workspace/tests/runtime_lab_crash.py\n'
                              'Environment=container=docker\n'
                              'Environment=HY2_LAB_CRASH_PHASE=' + phase + '\n')
            run('systemctl', 'daemon-reload')
            subprocess.run(['systemctl', 'reset-failed', 'hysteria2-panel-restore.service'], check=False)
            started = time.monotonic()
            restore_upload(db, archive)
            # The source and destination TLS/HMAC identity are identical in this
            # drill. Once the DB replacement is complete, validating the whole
            # restored state can safely roll forward even before its phase write.
            applied = phase != 'prepared'
            expected = baseline if applied else before
            deadline = started + 120
            while time.monotonic() < deadline:
                try:
                    if (evidence.exists() and not panel.RESTORE_ACTIVE_MARKER.exists()
                            and rows(db) == expected and request('/readyz')[0] == 200):
                        break
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(.2)
            else:
                raise RuntimeError('Interrupted restore failed to recover: ' + phase)
            fault_result = {'scenario': 'restore_sigkill_' + phase,
                            'rto_seconds': round(time.monotonic() - started, 3),
                            'fault_reached': evidence.read_text() == phase,
                            'outcome': 'applied' if applied else 'rolled_back',
                            'exact_users_tokens_and_usage': rows(db) == expected,
                            'real_quic_after': data_plane(settings, db)}
            results.append(fault_result)
            Path(args.output).write_text(json.dumps(results, indent=2) + '\n')
            print(json.dumps(fault_result), flush=True)
    finally:
        dropin.unlink(missing_ok=True)
        run('systemctl', 'daemon-reload')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('tls', 'capacity', 'recovery'))
    parser.add_argument('--users', type=int, nargs='+', default=[100, 200, 500])
    parser.add_argument('--concurrency', type=int, nargs='+', default=[2, 8, 16])
    parser.add_argument('--seconds', type=int, default=10)
    parser.add_argument('--output', default='/tmp/runtime-lab.json')
    parser.add_argument('--reset-load-users', action='store_true')
    parser.add_argument('--rate', type=int, default=0,
                        help='Total scheduled requests/sec; latency includes scheduling delay')
    args = parser.parse_args()
    if (any(not 1 <= value <= 10000 for value in args.users)
            or args.users != sorted(set(args.users))
            or any(not 1 <= value <= 128 for value in args.concurrency)
            or not 1 <= args.seconds <= 120 or not 0 <= args.rate <= 500
            or args.rate * args.seconds > 10000):
        parser.error('Use increasing user sizes <=10000, concurrency <=128 and duration <=120 seconds')
    panel, settings = guard()
    Path(args.output + '.metadata.json').write_text(json.dumps({
        'python': sys.version.split()[0], 'panel_version': panel.PANEL_VERSION,
        'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                          for path in ('hysteria2_panel.py', 'hy2panel/mobile_api.py', 'hy2panel/dashboard.py')},
        'mode': args.mode, 'users': args.users, 'concurrency': args.concurrency,
        'seconds_per_scenario': args.seconds, 'offered_rps': args.rate or None,
        'load_model': ('scheduled arrivals, latency includes queue delay' if args.rate else 'closed-loop')
                      + ', new TCP/TLS connection per request',
    }, indent=2) + '\n')
    if args.mode == 'tls':
        enable_tls()
    elif args.mode == 'capacity':
        capacity(panel, settings, args)
    else:
        recovery(panel, settings, args)


if __name__ == '__main__':
    main()
