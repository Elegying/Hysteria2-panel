"""Fail closed when a release cannot preserve external subscription nodes."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hysteria2_panel import BackupManager, BackupValidationError

ROOT = Path(__file__).resolve().parents[1]


class ExternalNodeUpgradeGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.database = self.root / 'panel.db'
        self.target = self.root / 'target.py'
        self.target.write_text('class Database:\n    pass\n')
        with sqlite3.connect(self.database) as c:
            c.execute('CREATE TABLE external_subscription_nodes (id INTEGER, nodes_json TEXT)')
        source = (ROOT / 'install.sh').read_text()
        self.function = source[source.index('check_external_nodes_upgrade_compatibility() {'):
                               source.index('\nif (( EXISTING_INSTALL == 1 )) && [[ -f /var/lib/hysteria2-panel/panel.db ]]',
                                            source.index('check_external_nodes_upgrade_compatibility() {'))]

    def run_guard(self):
        return subprocess.run(['bash', '-c', self.function + '\ncheck_external_nodes_upgrade_compatibility "$1" "$2"',
                               'guard', str(self.database), str(self.target)],
                              env=dict(os.environ, PYTHON_BIN=sys.executable), capture_output=True)

    def test_blocks_unsupported_code_when_external_data_exists(self):
        with sqlite3.connect(self.database) as c:
            c.execute("INSERT INTO external_subscription_nodes VALUES (1, 'opaque')")
        self.assertNotEqual(0, self.run_guard().returncode)
        self.target.write_text('external_subscription_nodes = 1\ndef get_external_nodes(): pass\ndef publish_external_nodes(): pass\ndef decode_external_nodes(): pass\n')
        self.assertNotEqual(0, self.run_guard().returncode)
        self.target.write_text('EXTERNAL_SUBSCRIPTION_BACKUP_FORMAT = 1\n' + self.target.read_text())
        self.assertEqual(0, self.run_guard().returncode)

    def test_current_release_preserves_external_credentials_contract(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("INSERT INTO external_subscription_nodes VALUES (1, 'opaque')")
        self.target.write_text((ROOT / 'hysteria2_panel.py').read_text())
        self.assertEqual(0, self.run_guard().returncode)

    def test_allows_older_code_without_external_records(self):
        self.assertEqual(0, self.run_guard().returncode)

    def test_restore_refuses_external_data_in_user_archive(self):
        other = self.root / 'other.db'
        with sqlite3.connect(other):
            pass
        manager = BackupManager.__new__(BackupManager)
        with sqlite3.connect(self.database) as c:
            c.execute("INSERT INTO external_subscription_nodes VALUES (1, 'opaque')")
        for source, destination in ((self.database, other),):
            with self.subTest(source=source):
                with self.assertRaises(BackupValidationError):
                    manager._stage_user_restore(source, destination, b'k' * 32)


if __name__ == '__main__':
    unittest.main()
