import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import node_agent as agent
from tests.test_premium_lines import PremiumSubscriptionTests


class NftRunner:
    def __init__(self):
        self.present = False
        self.corrupt = False
        self.fail_apply = False
        self.writes = []

    def __call__(self, command, **kwargs):
        if command[1:] == ['-j', 'list', 'tables']:
            rows = [{'table': {'family': 'inet', 'name': 'unrelated'}}]
            if self.present:
                rows.append({'table': {'family': 'inet', 'name': agent.NODE_HOPPING_TABLE}})
        elif command[1:4] == ['-j', 'list', 'table']:
            chain = {'family': 'inet', 'table': agent.NODE_HOPPING_TABLE,
                     'name': 'prerouting', 'type': 'nat', 'hook': 'prerouting',
                     'prio': -100, 'policy': 'accept', 'handle': 1}
            rows = [{'chain': chain}] + [{'rule': rule} for rule in agent.node_hopping_rules()]
            if self.corrupt:
                rows[-1]['rule']['expr'][-1]['redirect']['port'] = 22
        else:
            self.writes.append((command, kwargs['input']))
            if command[1] == '-f':
                if self.fail_apply:
                    raise subprocess.CalledProcessError(1, command)
                self.present = not kwargs['input'].startswith('delete')
            return mock.Mock(stdout='', returncode=0)
        return mock.Mock(stdout=json.dumps({'nftables': rows}), returncode=0)


class NodeHoppingTests(unittest.TestCase):
    def test_enable_restart_disable_idempotence_and_owned_cleanup(self):
        runner = NftRunner()
        with tempfile.TemporaryDirectory() as folder:
            def apply(enabled, **kwargs):
                agent.configure_node_hopping(enabled, runner=runner,
                    lock_path=str(Path(folder) / 'lock'), **kwargs)
            apply(True)
            self.assertTrue(runner.present)
            self.assertEqual(2, len(runner.writes))
            apply(True)
            apply(True, check_only=True)
            self.assertEqual(2, len(runner.writes))
            runner.present = False  # Kernel tables disappear across reboot.
            apply(True)
            self.assertTrue(runner.present)
            apply(False)
            apply(False)
            self.assertFalse(runner.present)
            self.assertEqual('delete table inet hy2_port_hopping\n', runner.writes[-1][1])
            self.assertTrue(all('flush ruleset' not in text and 'unrelated' not in text
                                for _, text in runner.writes))

    def test_unowned_table_failure_and_health_mismatch_fail_closed(self):
        runner = NftRunner()
        with tempfile.TemporaryDirectory() as folder:
            options = {'runner': runner, 'lock_path': str(Path(folder) / 'lock')}
            with self.assertRaises(agent.ProtocolError):
                agent.configure_node_hopping(True, check_only=True, **options)
            runner.present = True
            runner.corrupt = True
            with self.assertRaises(agent.ProtocolError):
                agent.configure_node_hopping(False, **options)
            self.assertEqual([], runner.writes)
            runner.present = False
            runner.fail_apply = True
            with self.assertRaises(subprocess.CalledProcessError):
                agent.configure_node_hopping(True, **options)
            self.assertFalse(runner.present)


class EnrollmentHoppingTests(PremiumSubscriptionTests):
    def test_enrollment_ignores_manual_port_and_accepts_both_switch_values(self):
        headers, csrf = self.authenticated_headers()
        for index, value in enumerate(("1", "0")):
            with self.request("/node-enrollments", {
                "csrf": csrf, "name": "remote-" + value, "expected_ip": "8.8.8.8",
                "tier": "premium", "region": ("hk", "us")[index],
                "subscription_host": value + ".example.test", "subscription_port": "22",
                "port_hopping": value,
            }, headers={**headers, "Accept": "application/json"}) as response:
                issued = json.load(response)
            with self.db._connect() as c:
                row = c.execute("SELECT * FROM nodes WHERE node_id=?", (issued["nodeId"],)).fetchone()
            self.assertEqual(19999, row["listen_port"])
            self.assertEqual(int(value), row["port_hopping"])
            self.assertEqual(443 if value == "1" else 19999, row["subscription_port"])

    def test_switch_persists_and_subscription_waits_for_deployment(self):
        node = self.db.create_node_enrollment('HK', '8.8.8.8', 'admin', 'a'*64,
            1, 2, tier='premium', region='hk', subscription_host='hk.example.test',
            port_hopping=True)
        with self.db._connect() as c:
            saved = c.execute('SELECT * FROM nodes WHERE node_id=?', (node['node_id'],)).fetchone()
            self.assertEqual((19999, 443, 1), (saved['listen_port'], saved['subscription_port'], saved['port_hopping']))
        self.assertEqual([], self.db.premium_subscription_nodes())
        self.db.get_or_create_node_identity(node['node_id'], lambda: {'egressPolicy': 'full'})
        with self.db._connect() as c:
            c.execute("UPDATE nodes SET status='pending_verification',verified_at=1,policy_state='protocol_ready',lifecycle_state='active',data_plane_state='dns_admitted' WHERE node_id=?", (node['node_id'],))
        line = self.db.premium_subscription_nodes()[0]
        self.assertEqual('20000-50000', line['hop_ports'])
        self.assertEqual(443, line['port'])
        with self.db._connect() as c:
            c.execute("UPDATE nodes SET status='revoked' WHERE node_id=?", (node['node_id'],))
        restored = self.db.create_node_enrollment('replacement', '1.1.1.1', 'admin', 'b'*64,
            3, 4, tier='premium', region='hk', subscription_host='changed.example.test',
            port_hopping=False)
        with self.db._connect() as c:
            saved = c.execute('SELECT * FROM nodes WHERE node_id=?', (restored['node_id'],)).fetchone()
            self.assertEqual(1, saved['port_hopping'])
