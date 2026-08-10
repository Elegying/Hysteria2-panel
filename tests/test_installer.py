import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"


class InstallerContractTests(unittest.TestCase):
    def test_installer_has_valid_shell_syntax_and_help_is_safe(self):
        syntax = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
        self.assertEqual(0, syntax.returncode, syntax.stderr)

        help_result = subprocess.run(
            ["bash", str(INSTALLER), "--help"], capture_output=True, text=True
        )
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        self.assertIn("19999", help_result.stdout)

    def test_installer_pins_upstream_release_and_checksums(self):
        source = INSTALLER.read_text()

        self.assertIn('PANEL_VERSION="0.1.2"', source)
        self.assertIn('HYSTERIA_VERSION="2.12.1"', source)
        self.assertIn(
            'HYSTERIA_SHA_AMD64="ffc032c7ca6b78676d337097ca7f61bebc3a90a4f3a656693adf368f304cdbc7"',
            source,
        )
        self.assertIn(
            'HYSTERIA_SHA_ARM64="c9cd1af6395eee13a937f429ea71b290e3cc571eea2b4d7f8bc7c49c1d23a792"',
            source,
        )
        self.assertIn("sha256sum", source)

    def test_installer_prompts_without_embedding_an_admin_password(self):
        source = INSTALLER.read_text()

        self.assertIn("read -r -s", source)
        self.assertNotRegex(source, r'ADMIN_PASSWORD="[^"$]{8,}"')

    def test_installer_is_namespaced_and_separates_service_identities(self):
        source = INSTALLER.read_text()

        self.assertIn("/opt/hysteria2-panel/bin/hysteria", source)
        self.assertIn("hysteria2-panel-server.service", source)
        self.assertNotIn("/etc/systemd/system/hysteria2.service", source)
        self.assertIn("User=hy2panel", source)
        self.assertIn("User=hy2server", source)
        self.assertIn("Group=hy2tls", source)

    def test_installer_restarts_upgrades_and_does_not_mutate_firewall(self):
        source = INSTALLER.read_text()

        self.assertIn("systemctl restart hysteria2-panel.service", source)
        self.assertIn("systemctl restart hysteria2-panel-server.service", source)
        self.assertNotIn("ufw allow", source)
        self.assertIn(".managed-by-installer", source)

    def test_installer_waits_for_service_readiness(self):
        source = INSTALLER.read_text()

        self.assertIn("wait_for_health", source)
        self.assertIn("for _attempt in {1..30}", source)
        self.assertIn('wait_for_health "https://127.0.0.1:${PANEL_PORT}/healthz" insecure', source)


if __name__ == "__main__":
    unittest.main()
