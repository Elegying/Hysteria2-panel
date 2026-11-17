"""Prevent packaging drift as Python modules are split or changed."""
import tempfile
import unittest
from pathlib import Path

from ops.source_manifest import synchronize


class SourceManifestTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / 'hy2panel').mkdir()
        (self.root / 'hy2panel/example.py').write_text('value = 1\n')
        self.installer = self.root / 'install.sh'
        self.installer.write_text(
            'EXAMPLE_SOURCE_URL="https://raw.githubusercontent.com/Elegying/Hysteria2-panel/${PANEL_REF}/hy2panel/example.py"\n'
            'EXAMPLE_SHA256="' + '0' * 64 + '"\n'
            'HYSTERIA_SHA_AMD64="do-not-change"\n'
        )

    def test_check_is_read_only_and_write_preserves_binary_pins(self):
        before = self.installer.read_bytes()
        self.assertEqual(['hy2panel/example.py'], synchronize(self.root))
        self.assertEqual(before, self.installer.read_bytes())
        synchronize(self.root, write=True)
        self.assertEqual([], synchronize(self.root))
        self.assertIn('HYSTERIA_SHA_AMD64="do-not-change"', self.installer.read_text())

    def test_new_module_without_install_entry_is_rejected(self):
        (self.root / 'hy2panel/missing.py').write_text('')
        with self.assertRaisesRegex(ValueError, 'modules absent'):
            synchronize(self.root, write=True)

    def test_missing_hash_is_rejected(self):
        self.installer.write_text(self.installer.read_text().replace('EXAMPLE_SHA256', 'WRONG_SHA256'))
        with self.assertRaisesRegex(ValueError, 'exactly one SHA256'):
            synchronize(self.root)
