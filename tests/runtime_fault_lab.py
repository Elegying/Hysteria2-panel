"""Opt-in real ENOSPC/SQLite lock tests in a marked disposable container.

Uses real loopback HTTP stats, SQLite and a bounded tmpfs. Service epoch IDs are
fixtures; separate installed-service tests cover the real systemd/data plane.
"""
import errno
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


def main():
    if (os.geteuid() != 0 or os.environ.get('container') != 'docker'
            or not Path('/workspace/.release-lab').is_file()):
        raise SystemExit('Explicitly marked disposable release container required')
    sys.path.insert(0, '/workspace')
    sys.path.insert(0, '/workspace/tests')
    from test_local_cumulative_accounting import LocalCumulativeAccountingTests
    import hysteria2_panel as panel

    fixture = LocalCumulativeAccountingTests('runTest')
    fixture.setUp()
    mountpoint = fixture.root / 'bounded-disk'
    mountpoint.mkdir()
    results = []
    subprocess.run(['mount', '-t', 'tmpfs', '-o', 'size=4m', 'tmpfs', str(mountpoint)], check=True)
    try:
        db = panel.Database(mountpoint / 'panel.db', b'a' * 32)
        db.initialize()
        db.create_proxy_user('alice')
        manager = fixture.manager(database=db)
        manager.collect_once()
        assert fixture.total(db) == 330
        filler = mountpoint / 'fill'
        with filler.open('wb', buffering=0) as handle:
            try:
                while True:
                    handle.write(b'x' * 65536)
            except OSError as error:
                assert error.errno == errno.ENOSPC
        fixture.traffic[0]['alice']['tx'] += 77
        try:
            manager.collect_once()
        except OSError as error:
            assert error.errno == errno.ENOSPC
        else:
            raise AssertionError('Collector unexpectedly committed on a full filesystem')
        assert fixture.traffic[0]['alice']['tx'] == 177
        filler.unlink()
        assert fixture.total(db) == 330
        fixture.manager(database=db).collect_once()
        fixture.manager(database=db).collect_once()
        assert fixture.total(db) == 407
        results.append({'scenario': 'real_tmpfs_enospc', 'filesystem_bytes': 4194304,
                        'before_bytes': 330, 'recovered_bytes': 407,
                        'source_not_cleared': '/traffic?clear=1' not in [p for _, p in fixture.paths]})

        fixture.traffic[0]['alice']['tx'] += 66
        manager = fixture.manager(database=db)
        started = time.monotonic()
        with db._connect() as writer:
            writer.execute('BEGIN IMMEDIATE')
            try:
                manager.collect_once()
            except sqlite3.OperationalError as error:
                assert 'locked' in str(error)
            else:
                raise AssertionError('Collector bypassed a real competing writer')
            assert fixture.total(db) == 407
            writer.rollback()
        blocked = time.monotonic() - started
        fixture.manager(database=db).collect_once()
        fixture.manager(database=db).collect_once()
        assert fixture.total(db) == 473
        results.append({'scenario': 'real_sqlite_writer_lock', 'blocked_seconds': round(blocked, 3),
                        'before_bytes': 407, 'recovered_bytes': 473, 'duplicate_bytes': 0})
        fixture.traffic[0]['alice']['tx'] += 88
        fixture.fail_endpoints.add(0)
        try:
            fixture.manager(database=db).collect_once()
        except Exception:
            pass
        else:
            raise AssertionError('Unavailable stats source was accepted')
        assert fixture.total(db) == 473
        fixture.fail_endpoints.clear()
        fixture.manager(database=db).collect_once()
        fixture.manager(database=db).collect_once()
        assert fixture.total(db) == 561
        results.append({'scenario': 'real_http_stats_503', 'before_bytes': 473,
                        'recovered_bytes': 561, 'duplicate_bytes': 0})
        Path('/tmp/release-faults.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results), flush=True)
    finally:
        subprocess.run(['umount', str(mountpoint)], check=True)
        fixture.doCleanups()


if __name__ == '__main__':
    main()
