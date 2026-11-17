import re
import subprocess
import unittest
from pathlib import Path

from hy2panel.nodes import NodeEnrollmentService
from hy2panel.version import PANEL_VERSION


ROOT = Path(__file__).resolve().parents[1]


class CompactEntryTests(unittest.TestCase):
    def test_published_entry_uses_current_signature_and_payload(self):
        script = (ROOT / 'bootstrap.sh').read_text()
        self.assertIn('/v' + PANEL_VERSION + '/install.sh', script)
        self.assertIn('release-signature.yml@refs/tags/v' + PANEL_VERSION, script)
        self.assertIn('verify-blob', script)
        self.assertLess(script.index('verify-blob'), script.index('/bin/bash'))
        self.assertIn('"${@}"', script)
        subprocess.run(['bash', '-n'], input=script, text=True, check=True)

    def test_short_command_stops_on_download_failure(self):
        service = NodeEnrollmentService(None, 'https://panel.example.com:19999', PANEL_VERSION)
        command = service._deployment_command('x' * 40)
        self.assertLess(len(command), 600)
        command = command.replace('curl -fsSL', 'false')
        result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn('x' * 40, result.stdout + result.stderr)

    def test_installer_checks_panel_hostname_before_join_registration(self):
        source = (ROOT / 'install.sh').read_text()
        for name in ('install_join_node', 'rebind_node'):
            body = source.split(name + '() {', 1)[1].split('\n}\n', 1)[0]
            self.assertLess(body.index('preflight_public_hostname_separation'),
                            body.index('download_file'))

    def test_release_payload_hashes_are_current(self):
        import hashlib
        source = (ROOT / 'install.sh').read_text()
        for name, relative in re.findall(
            r'^([A-Z0-9_]+)_SOURCE_URL="https://raw\.githubusercontent\.com/Elegying/Hysteria2-panel/\$\{PANEL_REF\}/([^"]+)"',
            source, re.MULTILINE,
        ):
            expected = re.search(r'^' + name + r'_SHA256="([a-f0-9]+)"', source, re.MULTILINE)[1]
            self.assertEqual(expected, hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), relative)

    def test_shared_host_dropin_is_removed_before_config_deletion(self):
        source = (ROOT / 'install.sh').read_text()
        body = source.split('uninstall_node() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('shared-host.conf', body)
        self.assertLess(body.index('rm -f -- "${shared_dropin}"'),
                        body.rindex('for directory in "${uninstall_directories[@]}"'))

    def test_older_agents_keep_their_deployed_hopping_range(self):
        from hysteria2_panel import node_hopping_ports
        for version in (None, "invalid", "0.39.52"):
            self.assertEqual("20000-50000", node_hopping_ports(version))
        self.assertEqual("2000-50000", node_hopping_ports("0.39.53"))
