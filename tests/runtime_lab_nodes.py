"""Real signed HTTPS node batches and durable replay in the disposable lab.

Keys and node rows are synthetic fixtures; enrollment/DNS is not tested here.
"""
import base64
import concurrent.futures
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time

from runtime_lab import guard, database, request, ready, run, quantile


def main():
    panel, settings = guard()
    sys.path.insert(0, '/workspace')
    import node_agent
    from hy2panel.distributed import canonical_node_request

    db = database(panel, settings)
    names = []
    for index in range(100):
        name = 'node-lab-{:03d}'.format(index)
        if not db.get_proxy_user_by_name(name):
            db.create_proxy_user(name, device_limit=100)
        names.append(name)
    results = []
    with tempfile.TemporaryDirectory(prefix='hy2-lab-nodes-') as directory:
        root = Path(directory)
        nodes = []
        for index in range(5):
            key = root / ('key-' + str(index))
            public = key.with_suffix('.der')
            run('openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(key))
            key.chmod(0o600)
            run('openssl', 'pkey', '-in', str(key), '-pubout', '-outform', 'DER', '-out', str(public))
            node_id = secrets.token_hex(16)
            now = int(time.time())
            with db._connect() as connection:
                connection.execute('''INSERT INTO nodes(
                    node_id, name, expected_ip, observed_ip, status, public_key,
                    hostname, platform, architecture, agent_version, created_at,
                    registered_at, last_seen_at, verified_at, verified_by,
                    last_heartbeat_at, last_heartbeat_ip, policy_state,
                    policy_enabled_at, policy_enabled_by, data_plane_state
                ) VALUES (?, ?, '127.0.0.1', '127.0.0.1', 'pending_verification', ?,
                    'node.runtime.test', 'linux', 'amd64', '0.39.41', ?, ?, ?, ?, 'lab', ?,
                    '127.0.0.1', 'protocol_ready', ?, 'lab', 'direct_canary_passed')''',
                    (node_id, 'isolated-node-' + str(index), node_agent._public_key(public),
                     now, now, now, now, now, now))
            nodes.append({'id': node_id, 'key': key, 'sequence': 0,
                          'spool': node_agent.DurableTrafficSpool(root / ('spool-' + str(index)))})

        def post(node, batch):
            node['sequence'] += 1
            now = int(time.time())
            payload = {'nodeId': node['id'], 'sentAt': now, 'nonce': secrets.token_urlsafe(32),
                       'cycleId': secrets.token_hex(16),
                       'trafficBatches': [{k: batch[k] for k in ('batchId', 'observedAt', 'traffic')}],
                       'onlineSnapshot': {'snapshotId': secrets.token_hex(16), 'sequence': node['sequence'],
                                          'observedAt': now, 'trafficAckedAt': now, 'online': {}},
                       'commandPoll': {'requestId': secrets.token_hex(16)}}
            signature = node_agent._openssl_sign(node['key'], canonical_node_request('control-cycle', payload))
            payload['signature'] = base64.b64encode(signature).decode()
            status, body = request('/api/v1/node-control-cycles', 'POST', json.dumps(payload),
                                   {'Content-Type': 'application/json'})
            if status != 200:
                raise RuntimeError('Signed cycle rejected: ' + str(status))
            response = json.loads(body)
            if not any(item['batchId'] == batch['batchId'] for item in response['traffic']):
                raise RuntimeError('Missing durable commit ACK')

        traffic = {name: {'tx': 11, 'rx': 23} for name in names}

        def total():
            with db._connect() as connection:
                return connection.execute("SELECT SUM(tx_bytes+rx_bytes) FROM proxy_users "
                                          "WHERE name GLOB 'node-lab-*'").fetchone()[0]

        def cycles(node):
            elapsed = []
            for _ in range(20):
                batch = node['spool'].enqueue(traffic, int(time.time()))
                start = time.monotonic()
                post(node, batch)
                node['spool'].ack(batch['batchId'])
                elapsed.append(time.monotonic() - start)
                time.sleep(.1)
            return elapsed

        for count in (1, 2, 5):
            before = total()
            started = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
                samples = [sample for group in pool.map(cycles, nodes[:count]) for sample in group]
            delta = total() - before
            expected = 34 * len(names) * 20 * count
            if delta != expected:
                raise RuntimeError('Signed batches lost or duplicated bytes')
            result = {'scenario': 'signed_cycles', 'nodes': count, 'users_per_batch': len(names),
                      'cycles': len(samples), 'elapsed_seconds': round(time.monotonic() - started, 3),
                      'p95_ms': quantile(samples, .95), 'p99_ms': quantile(samples, .99),
                      'expected_bytes': expected, 'actual_bytes': delta}
            results.append(result)
            print(json.dumps(result), flush=True)

        # Stop the actual panel, persist unsent traffic, recreate spool readers,
        # then replay twice (simulated lost ACK) before removing acknowledged files.
        before = total()
        run('systemctl', 'stop', 'hysteria2-panel.service')
        try:
            for node in nodes:
                for _ in range(10):
                    node['spool'].enqueue(traffic, int(time.time()))
                node['spool'] = node_agent.DurableTrafficSpool(node['spool'].path)
                if len(node['spool'].pending()) != 10:
                    raise RuntimeError('Spool did not survive reader recreation')
        finally:
            run('systemctl', 'start', 'hysteria2-panel.service')
        started = time.monotonic()
        ready()

        def replay(node):
            for batch in node['spool'].pending():
                post(node, batch)
                post(node, batch)
                node['spool'].ack(batch['batchId'])
            return len(node['spool'].pending())

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            remaining = sum(pool.map(replay, nodes))
        delta = total() - before
        expected = 34 * len(names) * 10 * 5
        if delta != expected or remaining:
            raise RuntimeError('Outage replay lost or duplicated bytes')
        result = {'scenario': 'central_outage_and_duplicate_replay', 'nodes': 5,
                  'durable_batches': 50, 'http_submissions': 100,
                  'recovery_and_replay_seconds': round(time.monotonic() - started, 3),
                  'expected_bytes': expected, 'actual_bytes': delta, 'remaining_batches': remaining}
        results.append(result)
        print(json.dumps(result), flush=True)
        Path('/tmp/node-lab.json').write_text(json.dumps(results, indent=2) + '\n')
        with db._connect() as connection:
            for node in nodes:
                connection.execute('UPDATE nodes SET status = ?, policy_state = ? WHERE node_id = ?',
                                   ('revoked', 'standby', node['id']))


if __name__ == '__main__':
    main()
