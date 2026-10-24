"""Brief real packet loss and writer contention against the installed lab."""
import json
from pathlib import Path
import time

from runtime_lab import guard, database, request, ready, run, data_plane


def main():
    panel, settings = guard()
    ready()
    db = database(panel, settings)
    if not db.get_proxy_user_by_name('service-fault-probe'):
        db.create_proxy_user('service-fault-probe', device_limit=100)
    user = db.get_proxy_user_by_name('service-fault-probe')
    payload = json.dumps({'auth': db.recover_proxy_token(user['id']), 'tx': 0})
    last_status = None

    def allowed():
        nonlocal last_status
        status, body = request('/auth', 'POST', payload, {'Content-Type': 'application/json'}, auth=True)
        last_status = status
        return status == 200 and bool(json.loads(body).get('ok'))

    assert allowed()
    results = []
    rule = ['OUTPUT', '-d', '127.0.0.1', '-p', 'tcp', '--dport', '31997', '-j', 'DROP']
    run('iptables', '-I', *rule)
    started = time.monotonic()
    try:
        deadline = started + 40
        while request('/readyz')[0] == 200:
            if time.monotonic() >= deadline:
                raise AssertionError('Ready endpoint concealed unavailable stats')
            time.sleep(.2)
        degraded_seconds = time.monotonic() - started
        assert not allowed(), 'New authentication accepted during stats loss'
    finally:
        run('iptables', '-D', *rule)
    started = time.monotonic()
    ready()
    assert allowed()
    results.append({'scenario': 'installed_stats_packet_drop',
                    'unready_after_seconds': round(degraded_seconds, 3),
                    'ready_after_network_recovery_seconds': round(time.monotonic() - started, 3),
                    'auth_denied_during_fault': True, 'auth_allowed_after_recovery': True})
    with db._connect() as writer:
        writer.execute('BEGIN IMMEDIATE')
        started = time.monotonic()
        assert not allowed(), 'Authentication bypassed an uncommittable lease'
        assert last_status == 503, 'Storage failure did not return explicit service unavailable'
        blocked = time.monotonic() - started
        writer.rollback()
    ready()
    assert allowed()
    results.append({'scenario': 'installed_sqlite_writer_lock', 'denial_seconds': round(blocked, 3),
                    'http_status_during_fault': 503,
                    'auth_allowed_after_recovery': True})
    if not db.get_proxy_user_by_name('recovery-probe'):
        db.create_proxy_user('recovery-probe', allow_udp_443=True)
    results.append({'scenario': 'quic_after_faults', 'entrypoints': data_plane(settings, db)})
    Path('/tmp/service-faults.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results), flush=True)


if __name__ == '__main__':
    main()
