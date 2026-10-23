"""Read a live database under the actual root backup capability boundary."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import uuid


def wait_for(path):
    until = time.monotonic() + 20
    while not path.exists():
        if time.monotonic() >= until:
            raise RuntimeError("backup permission probe did not reach its barrier")
        time.sleep(.02)


def copy_database(source, directory):
    sys.path.insert(0, "/opt/hysteria2-panel")
    from hysteria2_panel import BackupManager

    def preflight(_size):
        metadata = Path(str(source) + "-wal").stat()
        (directory / "ready.json").write_text(json.dumps({
            "walUid": metadata.st_uid, "walMode": metadata.st_mode & 0o777,
            "walInode": metadata.st_ino, "backupUid": os.geteuid(),
        }))
        wait_for(directory / "release")

    BackupManager._copy_database(source, directory / "backup.db", preflight=preflight)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--copy":
        copy_database(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    if (os.geteuid() != 0 or os.environ.get("container") != "docker"
            or not Path("/workspace/tests/installer_e2e.sh").is_file()):
        raise SystemExit("This check requires the disposable installer host")
    values = {line.split("=", 1)[0]: shlex.split(line.split("=", 1)[1])[0]
              for line in Path("/etc/hysteria2-panel/panel.env").read_text().splitlines()
              if line.startswith("HY2PANEL_") and line.split("=", 1)[1]}
    if values["HY2PANEL_PANEL_PORT"] != "31998":
        raise SystemExit("Refusing a non-fixture panel")
    source = Path(values["HY2PANEL_DB"])
    owner = source.stat().st_uid
    directory = Path(tempfile.mkdtemp(prefix="hy2-wal-backup-", dir="/var/tmp"))
    unit = "hy2-wal-backup-" + uuid.uuid4().hex[:12]
    command = [
        "systemd-run", "--quiet", "--wait", "--pipe", "--unit=" + unit,
        "--property=User=root", "--property=Group=hy2panel",
        "--property=NoNewPrivileges=yes",
        "--property=CapabilityBoundingSet=CAP_DAC_OVERRIDE",
        "--property=AmbientCapabilities=CAP_DAC_OVERRIDE",
        "--property=RuntimeMaxSec=30",
        sys.executable, __file__, "--copy", str(source), str(directory),
    ]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_for(directory / "ready.json")
        report = json.loads((directory / "ready.json").read_text())
        assert report["backupUid"] == 0
        assert report["walUid"] == owner != 0, report
        assert report["walMode"] == source.stat().st_mode & 0o777
        # Exercise a service-user read and write lock while the root backup has
        # pinned its snapshot. This never modifies application rows.
        probe = subprocess.check_output([
            "runuser", "-u", "hy2panel", "--", sys.executable, "-c",
            "import sqlite3,sys; c=sqlite3.connect(sys.argv[1],timeout=5); "
            "print(c.execute('SELECT COUNT(*) FROM proxy_users').fetchone()[0]); "
            "c.execute('BEGIN IMMEDIATE'); c.rollback(); c.close()", str(source),
        ], timeout=10)
        assert int(probe) == 1000
    finally:
        (directory / "release").touch()
        output, error = child.communicate(timeout=35)
        (directory / "copy.log").write_bytes(output + error)
    assert child.returncode == 0, (directory / "copy.log").read_text()
    assert Path(str(source) + "-wal").stat().st_ino == report["walInode"]
    checkpoint = subprocess.check_output([
        "runuser", "-u", "hy2panel", "--", sys.executable, "-c",
        "import sqlite3,sys,json; c=sqlite3.connect(sys.argv[1],timeout=5); "
        "print(json.dumps(c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())); c.close()",
        str(source),
    ], timeout=10)
    assert json.loads(checkpoint)[0] == 0
    report.update(result="passed", serviceReadAndWrite=True, checkpointBusy=0)
    (directory / "result.json").write_text(json.dumps(report))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
