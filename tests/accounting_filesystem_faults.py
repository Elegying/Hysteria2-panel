"""Actual ENOSPC/EROFS in a private tmpfs, with existing loopback stats fixtures.

Run only in the explicitly marked disposable Linux installer container. This
checks real filesystem/SQLite failures, not a full Hysteria data-plane outage.
"""
import argparse
import errno
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (os.geteuid() != 0 or os.environ.get("container") != "docker"
            or os.environ.get("HY2_STABILITY_ISOLATED") != "1"
            or not Path("/workspace/tests/installer_e2e.sh").is_file()):
        raise SystemExit("Requires the dedicated isolated installer container")
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    mount = args.output / "filesystem"
    mount.mkdir()
    sys.path[:0] = ["/workspace/tests", "/workspace"]
    from test_local_cumulative_accounting import LocalCumulativeAccountingTests

    def command(*parts):
        subprocess.run(parts, check=True, timeout=15, stdout=subprocess.DEVNULL)

    def fill():
        filler = mount / "filler"
        try:
            with filler.open("wb", buffering=0) as handle:
                while True:
                    handle.write(b"\0" * 65536)
        except OSError as error:
            if error.errno != errno.ENOSPC:
                raise
        return filler

    command("mount", "-t", "tmpfs", "-o", "size=16m,mode=0700", "hy2-fault-test", str(mount))
    report = {"result": "running", "cases": []}
    original_tempdir = tempfile.tempdir
    fixture = None
    try:
        for scenario in ("journal-full", "database-full", "journal-read-only"):
            tempfile.tempdir = str(mount) if scenario == "database-full" else original_tempdir
            fixture = LocalCumulativeAccountingTests()
            fixture.setUp()
            manager = fixture.manager()
            journal = (args.output / "database-pending.json" if scenario == "database-full"
                       else mount / (scenario + ".json"))
            manager.cumulative_collector.path = journal
            filler = None
            if scenario == "journal-read-only":
                command("mount", "-o", "remount,ro", str(mount))
            else:
                filler = fill()
            error_text = ""
            try:
                manager.collect_once()
            except (OSError, sqlite3.OperationalError) as error:
                error_text = str(error)
                if scenario == "database-full":
                    assert os.statvfs(mount).f_bavail == 0
                    # SQLite can report IOERR_SHMSIZE when a full filesystem
                    # prevents creating WAL shared memory before the write.
                    code = getattr(error, "sqlite_errorcode", 0)
                    assert code & 255 in (sqlite3.SQLITE_FULL, sqlite3.SQLITE_IOERR), error_text
                    pending = json.loads(journal.read_text())["pending"]
                    assert pending is not None
                    (args.output / "database-pending-before-recovery.json").write_bytes(journal.read_bytes())
                else:
                    assert error.errno == (errno.EROFS if scenario == "journal-read-only" else errno.ENOSPC)
                    assert not journal.exists()
            else:
                raise AssertionError("fault did not prevent settlement: " + scenario)
            finally:
                if scenario == "journal-read-only":
                    command("mount", "-o", "remount,rw", str(mount))
                if filler is not None:
                    filler.unlink()
            assert fixture.total() == 0
            assert fixture.traffic[0]["alice"] == {"tx": 100, "rx": 200}
            recovered = fixture.manager()
            recovered.cumulative_collector.path = journal
            recovered.collect_once()
            assert fixture.total() == 330
            recovered.collect_once()
            assert fixture.total() == 330
            assert not any(path == "/traffic?clear=1" for _, path in fixture.paths)
            report["cases"].append({"scenario": scenario, "result": "passed", "injectedError": error_text,
                                    "bytesAfterRecovery": fixture.total()})
            (args.output / (scenario + "-recovered.json")).write_bytes(journal.read_bytes())
            fixture.doCleanups()
            fixture = None
        report["result"] = "passed"
    except Exception as error:
        report["result"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        tempfile.tempdir = original_tempdir
        if fixture is not None:
            shutil.copytree(fixture.root, args.output / "failed-database", dirs_exist_ok=True)
            fixture.doCleanups()
        # On failure retain the mounted filesystem and its incomplete evidence.
        if report["result"] == "passed":
            command("umount", str(mount))
        (args.output / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
