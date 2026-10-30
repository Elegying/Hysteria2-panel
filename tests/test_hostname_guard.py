import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import hysteria2_panel as panel


class HostnameGuardTests(unittest.TestCase):
    def test_collision_is_case_and_trailing_dot_insensitive(self):
        with patch.object(panel.socket, 'gethostname', return_value='Panel.Example.com.'):
            for hosts in [('panel.example.com',), ('vpn.example.com', 'panel.example.com')]:
                with self.subTest(hosts=hosts), self.assertRaisesRegex(RuntimeError, '订阅链接'):
                    panel.ensure_public_hostname_separate(*hosts)
            panel.ensure_public_hostname_separate('vpn.example.com', '', None)

    def test_restore_rejects_before_lock_database_or_service_mutation(self):
        settings = SimpleNamespace(panel_public_host='panel.example.com', public_host='vpn.example.com')
        with patch.object(panel.socket, 'gethostname', return_value='panel.example.com'), \
                patch.object(panel, 'exclusive_maintenance_lock') as lock, \
                patch.object(panel, 'BackupManager') as manager:
            with self.assertRaisesRegex(RuntimeError, '主机名'):
                panel.restore_pending(settings)
            lock.assert_not_called()
            manager.assert_not_called()

    def test_restore_health_cannot_report_success_for_collision(self):
        settings = SimpleNamespace(panel_public_host='panel.example.com', public_host='vpn.example.com')
        probe = Mock()
        with patch.object(panel.socket, 'gethostname', return_value='panel.example.com'):
            with self.assertRaisesRegex(RuntimeError, '主机名'):
                panel.verify_restore_services(settings, health_probe=probe)
        probe.assert_not_called()

    def test_installer_guard_executes_without_mutation(self):
        source = (Path(__file__).resolve().parents[1] / 'install.sh').read_text()
        start = source.index('preflight_public_hostname_separation() {')
        end = source.index('validate_panel_public_host() {', start)
        guard = source[start:end]
        for local, status in [('Panel.Example.com.', 97), ('hy2-panel-internal', 0)]:
            script = 'set -e\n' + guard + '\nhostname() { printf "%s" "$LOCAL_HOST"; }\nfail() { exit 97; }\npreflight_public_hostname_separation panel.example.com vpn.example.com\n'
            import os
            result = subprocess.run(['bash', '-c', script], env={**os.environ, 'LOCAL_HOST': local}, capture_output=True)
            self.assertEqual(result.returncode, status, result.stderr)
        self.assertLess(source.index('preflight_public_hostname_separation "${PANEL_PUBLIC_HOST}"'), source.index('BACKUP_DIR="/var/backups/hysteria2-panel/${timestamp}'))
