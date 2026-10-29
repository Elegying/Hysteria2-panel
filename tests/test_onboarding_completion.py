"""Regression coverage for independent endpoints and one-click prerequisites."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

import node_agent

from hy2panel.nodes import (
    DATA_PLANE_BOOTSTRAP_FIELDS, DataPlaneBootstrapService,
    HysteriaCanaryRunner, NodeDnsAdmissionReconciler, NodeEnrollmentService,
)


class OnboardingCompletionTests(unittest.TestCase):
    def test_real_health_checker_accepts_managed_hopping_service(self):
        with mock.patch('node_agent.subprocess.run', return_value=mock.Mock(returncode=0)) as run:
            self.assertTrue(node_agent._systemd_service_active('hysteria2-panel-node-port-hopping.service'))
            self.assertEqual('hysteria2-panel-node-port-hopping.service', run.call_args.args[0][-1])
            self.assertFalse(node_agent._systemd_service_active('unrelated.service'))
            self.assertEqual(1, run.call_count)

    def test_independent_standard_dns_is_used_instead_of_local_dns(self):
        db = mock.Mock()
        db.list_nodes.return_value = [{
            'node_id': 'a' * 32, 'tier': 'standard',
            'subscription_host': 'remote.example.test', 'expected_ip': '8.8.8.8',
            'data_plane_state': 'direct_canary_passed',
        }]
        db.mark_node_dns_admitted.return_value = True
        queried = []
        def resolve(host, port, **kwargs):
            queried.append(host)
            ip = '8.8.8.8' if host == 'remote.example.test' else '1.1.1.1'
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))]
        result = NodeDnsAdmissionReconciler(db, 'local.example.test', resolver=resolve).reconcile()
        self.assertEqual(1, result['admitted'])
        self.assertIn('remote.example.test', queried)

    def test_bootstrap_uses_persisted_independent_port_and_preserves_legacy(self):
        service = DataPlaneBootstrapService.__new__(DataPlaneBootstrapService)
        service.hysteria_port = 24443
        service.database = mock.Mock()
        service.database.fetch_data_plane_bootstrap.return_value = {
            'grant_id': 'b' * 32, 'expires_at': 100, 'fetch_attempts': 1,
        }
        service._identity = mock.Mock(return_value={})
        for host, expected in [('remote.example.test', 19999), ('', 24443)]:
            node = {'node_id': 'a' * 32, 'tier': 'standard',
                    'subscription_host': host, 'listen_port': 19999}
            service._verify = mock.Mock(return_value=(node, 'nonce', 1, '8.8.8.8'))
            payload = dict.fromkeys(DATA_PLANE_BOOTSTRAP_FIELDS, '')
            payload.update(bootstrapToken='a' * 40, requestId='b' * 32)
            self.assertEqual(expected, service.fetch(payload, '8.8.8.8')['ports']['main'])

    def test_hopping_probes_boundaries_interior_and_tcp_and_rejects_failure(self):
        runner = HysteriaCanaryRunner('node.example.test')
        runner._check_entrypoint = mock.Mock()
        with mock.patch('hy2panel.nodes.secrets.randbelow', return_value=14999), \
             mock.patch('hy2panel.nodes.socket.create_connection') as tcp:
            runner(node_ip='8.8.8.8', main_port=19999, token='a'*40,
                   pin_sha256='b'*64, port_hopping=True)
            self.assertEqual([19999, 443, 20000, 35000, 50000],
                             [c.args[1] for c in runner._check_entrypoint.call_args_list])
            self.assertEqual(3, tcp.call_count)
        runner._check_entrypoint.side_effect = [None, None, OSError('blocked')]
        with self.assertRaises(OSError):
            runner(node_ip='8.8.8.8', main_port=19999, token='a'*40,
                   pin_sha256='b'*64, port_hopping=True)

    def test_generated_command_bootstraps_curl_before_first_download(self):
        service = NodeEnrollmentService.__new__(NodeEnrollmentService)
        service.panel_version = '0.39.47'
        service.panel_url = 'https://panel.example.test'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / 'calls'
            for name, body in {
                'id': 'echo 0', 'uname': 'if [ "$1" = -s ]; then echo Linux; else echo x86_64; fi',
                'mktemp': 'exec /usr/bin/mktemp -d', 'rm': 'exec /bin/rm "$@"',
                'apt-get': 'echo apt >> "$AUDIT_LOG"; if [ "$1" = install ]; then printf \'#!/bin/sh\\necho curl >> "$AUDIT_LOG"\\nexit 42\\n\' > "$BIN/curl"; /bin/chmod 755 "$BIN/curl"; fi',
                'sha256sum': 'exit 0',
            }.items():
                path = root / name
                path.write_text('#!/bin/sh\n' + body + '\n')
                path.chmod(0o755)
            result = subprocess.run(['/bin/bash', '-c', service._deployment_command('a'*40).replace('/run/systemd/system', directory)],
                env={**os.environ, 'PATH': directory, 'BIN': directory, 'AUDIT_LOG': str(log)},
                capture_output=True, text=True)
            self.assertEqual(42, result.returncode, result.stderr)
            self.assertEqual(['apt', 'apt', 'curl'], log.read_text().splitlines())
            self.assertNotIn('a'*40, result.stdout + result.stderr)
