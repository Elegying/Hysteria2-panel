"""Exercise the installer's real pruning policy with isolated GNU filesystem tools."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


@unittest.skipUnless(sys.platform == "linux", "requires GNU filesystem tools")
class BackupRetentionTests(unittest.TestCase):
    def test_pruning_preserves_recovery_points_and_unmanaged_paths(self):
        source = (Path(__file__).resolve().parents[1] / "install.sh").read_text()
        helper = source.split("prune_automatic_backups() {", 1)[1].split(
            "\n\nrollback_firewall_after_service_recovery()", 1
        )[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            names = ["202609{:02d}T120000Z-12345678".format(day) for day in range(1, 7)]
            for name in names:
                path = root / name
                path.mkdir(mode=0o700)
                (path / "data").write_bytes(b"x" * 8192)
                os.utime(path, (time.time() - 90 * 86400,) * 2)
            manual = root / "manual-keep"
            manual.mkdir()
            link = root / "20260907T120000Z-12345678"
            link.symlink_to(manual, target_is_directory=True)
            pinned = root / names[0]
            helper = "prune_automatic_backups() {" + helper.replace(
                "backup_root=/var/backups/hysteria2-panel", 'backup_root="${TEST_ROOT}"'
            )
            helper = helper.replace("0:0:700", "{}:{}:700".format(os.getuid(), os.getgid()))
            script = "set -euo pipefail\n" + helper + "\nprune_automatic_backups\n"
            result = subprocess.run(
                ["bash"], input=script, capture_output=True, text=True,
                env={**os.environ, "TEST_ROOT": str(root), "BACKUP_DIR": str(pinned),
                     "BACKUP_RETENTION_DAYS": "30", "BACKUP_MAX_COUNT": "3",
                     "BACKUP_MIN_COUNT": "2", "BACKUP_MAX_KIB": "1"},
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual({names[0], names[-1], names[-2], manual.name, link.name},
                             {path.name for path in root.iterdir()})
            self.assertIn("空间预算", result.stderr)


if __name__ == "__main__":
    unittest.main()
