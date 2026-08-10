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


if __name__ == "__main__":
    unittest.main()
