"""Remote telemetry validation and bounded fixed server operations."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import node_agent
from hy2panel.diagnostics import ServerMonitor, valid_resources
from tests import test_panel


class ServerResourcesTests(unittest.TestCase):
    def test_validation_and_expiry(self):
        sample = dict(cpu=12.5, memory=40, disk=25, uptime=200, observedAt=100)
        monitor = ServerMonitor()
        self.assertTrue(monitor.accept('node', sample, 100))
        self.assertFalse(monitor.accept('node', sample, 100))
        self.assertTrue(monitor.snapshot(['node'], 110)['node']['fresh'])
        self.assertFalse(monitor.snapshot(['node'], 131)['node']['fresh'])
        self.assertEqual({}, monitor.snapshot(['node'], 401))
        for bad in [float('nan'), float('inf'), -1, 101, True, '12']:
            self.assertFalse(valid_resources(dict(sample, cpu=bad)))
        self.assertTrue(valid_resources(dict(sample, cpu=None)))
        extended = dict(sample, memoryUsed=10, memoryTotal=20, diskUsed=30, diskTotal=40)
        self.assertTrue(valid_resources(extended))
        self.assertFalse(valid_resources(dict(extended, memoryUsed=21)))
        self.assertFalse(valid_resources(dict(extended, diskTotal=-1)))
        self.assertFalse(valid_resources(dict(sample, memoryUsed=10)))
        self.assertFalse(monitor.accept('node', dict(sample, observedAt=200), 100))

    def test_linux_resource_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'proc').mkdir()
            (root/'proc/stat').write_text('cpu 10 0 10 80 0 0 0 0\n')
            (root/'proc/meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 400 kB\n')
            (root/'proc/uptime').write_text('123.45 0\n')
            with mock.patch.object(node_agent, '_RESOURCE_CPU', None), mock.patch.object(node_agent.shutil, 'disk_usage', return_value=SimpleNamespace(total=100,used=25)):
                self.assertIsNone(node_agent.read_resource_sample(root, lambda:100)['cpu'])
                (root/'proc/stat').write_text('cpu 30 0 30 140 0 0 0 0\n')
                result=node_agent.read_resource_sample(root, lambda:105)
                self.assertEqual(dict(cpu=40.0,memory=60.0,disk=25.0,uptime=123,observedAt=105,memoryUsed=600*1024,memoryTotal=1000*1024,diskUsed=25,diskTotal=100),result)

    def test_fixed_reboot_is_durable_and_not_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            cmd=dict(commandId='a'*32,kind='REBOOT_SERVER',payload={'expiresAt':150})
            runner=mock.Mock(return_value=SimpleNamespace(returncode=0))
            node_agent.queue_server_operation(cmd,directory,runner,lambda:100)
            node_agent.queue_server_operation(cmd,directory,runner,lambda:101)
            self.assertEqual(1, runner.call_count)
            argv=runner.call_args.args[0]
            self.assertEqual(['/bin/systemctl','reboot'],argv[-2:])
            self.assertIn('--on-active=5s',argv)
            self.assertFalse(runner.call_args.kwargs.get('shell',False))

    def test_service_restart_only_targets_fixed_data_plane_units(self):
        with tempfile.TemporaryDirectory() as directory:
            cmd = dict(commandId='c'*32, kind='RESTART_SERVICE', payload={'expiresAt': 150})
            runner = mock.Mock(return_value=SimpleNamespace(returncode=0))
            node_agent.queue_server_operation(cmd, directory, runner, lambda: 100)
            self.assertEqual(['/bin/systemctl', 'restart', *node_agent.DATA_PLANE_UNITS], runner.call_args.args[0][-(2+len(node_agent.DATA_PLANE_UNITS)):])

    def test_flush_failure_prevents_scheduling_and_expired_command_cannot_flush(self):
        import time
        command = dict(commandId='d'*32, kind='REBOOT_SERVER', payload={'expiresAt': int(time.time())+120})
        flush = mock.Mock(side_effect=RuntimeError('accounting unavailable'))
        with mock.patch.object(node_agent, 'queue_server_operation') as queue:
            with self.assertRaises(RuntimeError):
                node_agent.execute_control_command(command, None, flush_traffic=flush, protocol_state=SimpleNamespace(path=Path('/tmp/protocol.json')), quiesce_traffic=mock.Mock())
            queue.assert_not_called()
            command['payload']['expiresAt'] = 1
            with self.assertRaises(node_agent.ProtocolError):
                node_agent.execute_control_command(command, None, flush_traffic=flush, protocol_state=SimpleNamespace(path=Path('/tmp/protocol.json')), quiesce_traffic=mock.Mock())
            self.assertEqual(1, flush.call_count)

    def test_failed_or_uncertain_operation_is_never_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            cmd=dict(commandId='b'*32,kind='RESTART_SERVICE',payload={'expiresAt':150})
            runner=mock.Mock(return_value=SimpleNamespace(returncode=1))
            for _ in range(2):
                with self.assertRaises(node_agent.ProtocolError):
                    node_agent.queue_server_operation(cmd,directory,runner,lambda:100)
            self.assertEqual(1, runner.call_count)
            with self.assertRaises(node_agent.ProtocolError):
                node_agent.queue_server_operation(dict(cmd,commandId='c'*32),directory,runner,lambda:151)
            self.assertEqual(1, runner.call_count)


class ServerOperationsHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_panel.PanelHttpTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f=self.fixture
        issued=f.application.node_enrollment_service.create('remote','8.8.4.9',10,'Elegy')
        self.node=issued['nodeId']
        with f.db._connect() as conn:
            conn.execute("UPDATE nodes SET policy_state='protocol_ready',status='pending_verification',verified_at=1 WHERE node_id=?",(self.node,))

    def test_admin_csrf_freshness_and_duplicate_guard(self):
        import time
        import urllib.error
        f=self.fixture
        headers,csrf=f.authenticated_headers()
        path='/nodes/'+self.node+'/operations/reboot'
        with self.assertRaises(urllib.error.HTTPError) as error:
            f.request(path,{'csrf':csrf,'confirm':self.node},headers=headers)
        self.assertEqual(409,error.exception.code)
        f.db.server_monitor.accept(self.node,dict(cpu=1,memory=2,disk=3,uptime=10,observedAt=int(time.time())))
        with self.assertRaises(urllib.error.HTTPError) as error:
            f.request(path,{'csrf':'invalid','confirm':self.node},headers=headers)
        self.assertEqual(403,error.exception.code)
        with f.request(path,{'csrf':csrf,'confirm':self.node},headers=headers) as response:
            self.assertEqual(202,response.status)
            self.assertIn('commandId',json.load(response))
        with self.assertRaises(urllib.error.HTTPError) as error:
            f.request(path,{'csrf':csrf,'confirm':self.node},headers=headers)
        self.assertEqual(409,error.exception.code)
        with f.request('/api/v1/server-monitor',headers=headers) as response:
            payload=json.load(response)
        self.assertTrue(payload['servers'][self.node]['fresh'])
        self.assertIsNone(payload['operations'][self.node]['acked_at'])
        commands=f.db.poll_node_commands(self.node,'d'*64,int(time.time())+121)
        self.assertEqual([],commands)
        with f.db._connect() as conn:
            self.assertEqual('EXPIRED',conn.execute('SELECT last_error FROM node_commands').fetchone()[0])
