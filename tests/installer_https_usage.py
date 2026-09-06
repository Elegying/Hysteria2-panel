"""Disposable systemd installer host only: strict TLS and synthetic account lifecycle."""
import grp
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import ssl
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile


def run(*args, **kwargs):
    return subprocess.run(args, check=True, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, **kwargs)


def main():
    if (os.geteuid() != 0 or not Path('/workspace/tests/installer_e2e.sh').is_file()
            or os.environ.get('container') != 'docker'):
        raise SystemExit('This check requires the disposable installer Docker host')
    sys.path.insert(0, '/opt/hysteria2-panel')
    import hysteria2_panel as panel

    env_path = Path('/etc/hysteria2-panel/panel.env')
    original = env_path.read_bytes()
    values = dict(line.split('=', 1) for line in original.decode().splitlines()
                  if line.startswith('HY2PANEL_') and '=' in line)
    values = {key: shlex.split(value)[0] if value else '' for key, value in values.items()}
    if values['HY2PANEL_PANEL_PORT'] != '31998' or values['HY2PANEL_PANEL_SCHEME'] != 'http':
        raise SystemExit('Refusing to modify a non-fixture panel')
    database = panel.Database(Path(values['HY2PANEL_DB']), bytes.fromhex(values['HY2PANEL_HMAC_KEY']))
    cert = env_path.parent / 'installer-e2e.crt'
    key = env_path.parent / 'installer-e2e.key'
    if cert.exists() or key.exists():
        raise SystemExit('Fixture certificate path already exists')
    name = 'installer-' + secrets.token_hex(8)
    user = None
    try:
        run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=panel.installer.test', '-addext', 'subjectAltName=DNS:panel.installer.test',
            '-keyout', str(key), '-out', str(cert))
        key.chmod(0o640)
        os.chown(key, 0, grp.getgrnam('hy2panel').gr_gid)
        replacements = {'HY2PANEL_PANEL_SCHEME': 'https',
                        'HY2PANEL_PANEL_PUBLIC_HOST': 'panel.installer.test',
                        'HY2PANEL_PANEL_TLS_CERT': str(cert), 'HY2PANEL_PANEL_TLS_KEY': str(key)}
        lines = [line for line in original.decode().splitlines()
                 if line.split('=', 1)[0] not in replacements]
        env_path.write_text('\n'.join(lines + [k + '=' + v for k, v in replacements.items()]) + '\n')
        run('systemctl', 'restart', 'hysteria2-panel.service')
        context = ssl.create_default_context(cafile=str(cert))

        def request(token=None):
            connection = http.client.HTTPSConnection('panel.installer.test', 31998,
                                                     context=context, timeout=3)
            connection._create_connection = lambda address, timeout, source_address=None: socket.create_connection(
                ('127.0.0.1', address[1]), timeout, source_address)
            try:
                headers = {} if token is None else {'Authorization': 'Bearer ' + token}
                connection.request('GET', '/api/v1/user/usage', headers=headers)
                response = connection.getresponse()
                payload = json.loads(response.read())
                assert response.getheader('Cache-Control') == 'no-store'
                return response.status, payload
            finally:
                connection.close()

        def expect(token, status):
            deadline = time.monotonic() + 30
            while True:
                try:
                    result = request(token)
                    if result[0] == status:
                        return result[1]
                    assert result[0] == 503, 'Unexpected account query status'
                except (ConnectionError, TimeoutError):
                    pass
                assert time.monotonic() < deadline, 'Installed query did not become ready'
                time.sleep(1)

        assert expect(None, 401) == {'apiVersion': 1, 'error': {'code': 'INVALID_CREDENTIALS'}}
        expect(secrets.token_urlsafe(24), 401)
        user = database.create_proxy_user(name)
        payload = expect(user['token'], 200)
        assert payload['data']['usedBytes'] == 0 and payload['data']['onlineDevices'] == 0
        database.add_traffic({name: {'tx': 29, 'rx': 31}})
        assert expect(user['token'], 200)['data']['usedBytes'] == 60
        run('systemctl', 'restart', 'hysteria2-panel.service')
        assert expect(user['token'], 200)['data']['usedBytes'] == 60
        replacement = database.rotate_proxy_token(user['id'])['token']
        expect(user['token'], 401)
        expect(replacement, 200)
        database.delete_proxy_user(user['id'])
        user = None
        expect(replacement, 401)
        try:
            database.create_proxy_user(name.upper())
        except ValueError:
            pass
        else:
            raise AssertionError('Deleted account name was reused')
        # Exercise the exact installer checks with the fixture CA, keeping hostname verification.
        installer = Path('/workspace/install.sh').read_text()
        helpers = installer[installer.index('wait_for_health() {'):installer.index('checkpoint_database() {')]
        with tempfile.TemporaryDirectory() as work:
            script_env = dict(os.environ, PANEL_SCHEME='https', PANEL_PUBLIC_HOST='panel.installer.test',
                              PANEL_PORT='31998', TMP_DIR=work, PYTHON_BIN=sys.executable,
                              CURL_CA_BUNDLE=str(cert))
            run('bash', '-euc', helpers + '\nwait_for_health https://panel.installer.test:31998/healthz strict\n'
                'verify_user_usage_endpoint\n! wait_for_health https://panel.installer.test:31998/healthz insecure',
                env=script_env)
        user = database.create_proxy_user('restore-' + secrets.token_hex(8))
        database.add_traffic({user['name']: {'tx': 13, 'rx': 17}})
        with tempfile.TemporaryDirectory() as work:
            manager = panel.BackupManager(
                database, bytes.fromhex(values['HY2PANEL_HMAC_KEY']),
                Path(values['HY2PANEL_TLS_CERT']), Path(values['HY2PANEL_TLS_KEY']),
                values['HY2PANEL_PUBLIC_HOST'], int(values['HY2PANEL_HYSTERIA_PORT']),
                work_dir=Path(work),
            )
            archive = manager._create_archive_locked()
            with zipfile.ZipFile(archive) as package:
                payloads = {name: package.read(name) for name in package.namelist()}
            source_db = Path(work) / 'legacy.db'
            source_db.write_bytes(payloads['data/panel.db'])
            with sqlite3.connect(source_db) as connection:
                connection.execute('DROP TABLE retired_proxy_names')
                connection.execute('DROP TABLE node_usage_checkpoints')
                original_origin = 'local:' + values['HY2PANEL_USAGE_ORIGIN_ID']
                source_origin = 'local:' + secrets.token_hex(16)
                for table in ('usage_origins', 'usage_origin_users', 'origin_traffic_daily',
                              'origin_traffic_budgets'):
                    connection.execute('UPDATE ' + table + ' SET origin_id=? WHERE origin_id=?',
                                       (source_origin, original_origin))
            payloads['data/panel.db'] = source_db.read_bytes()
            manifest = json.loads(payloads['manifest.json'])
            manifest['panelVersion'] = '0.39.7'
            manifest['files']['data/panel.db'] = {
                'sha256': hashlib.sha256(payloads['data/panel.db']).hexdigest(),
                'size': len(payloads['data/panel.db']),
            }
            payloads['manifest.json'] = json.dumps(manifest).encode()
            pending = Path('/var/lib/hysteria2-panel/backup-restore/pending-restore.zip')
            assert not pending.exists()
            with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_DEFLATED) as package:
                for name, value in payloads.items():
                    package.writestr(name, value)
            pending.chmod(0o600)
            owner = database.path.stat()
            os.chown(pending, owner.st_uid, owner.st_gid)
            run('systemctl', 'start', 'hysteria2-panel-restore.service')
            assert expect(user['token'], 200)['data']['usedBytes'] == 30
            deadline = time.monotonic() + 30
            while Path('/etc/hysteria2-panel/.restore-active').exists():
                assert time.monotonic() < deadline, 'Restore did not finish health verification'
                time.sleep(1)
            run('systemctl', 'is-active', '--quiet', 'hysteria2-panel-server.service')
            run('systemctl', 'is-active', '--quiet', 'hysteria2-panel-server-443.service')
        print('Installed legacy backup restore, service recovery and authenticated HTTPS usage: PASS')
        print('Installed strict HTTPS query, synthetic ledger, restart, rotation and deletion: PASS')
    finally:
        if user is not None:
            database.delete_proxy_user(user['id'])
        env_path.write_bytes(original)
        run('systemctl', 'restart', 'hysteria2-panel.service')
        cert.unlink(missing_ok=True)
        key.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
