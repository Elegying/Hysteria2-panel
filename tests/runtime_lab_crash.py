"""Disposable lab systemd entrypoint: SIGKILL after an actual durable write."""
import os
from pathlib import Path
import signal
import sys

if os.environ.get('container') != 'docker' or not Path('/run/hy2-disposable-runtime-lab').is_file():
    raise SystemExit('Disposable runtime lab required')
sys.path.insert(0, '/opt/hysteria2-panel')
import hysteria2_panel as panel  # noqa: E402

phase = os.environ['HY2_LAB_CRASH_PHASE']
write_json = panel._atomic_write_json
replace_file = panel.BackupManager._replace_file


def crash():
    # Separate durable evidence confirms the requested fault point was reached.
    evidence = Path('/var/lib/hysteria2-panel/lab-crash-reached')
    with evidence.open('w') as handle:
        handle.write(phase)
        handle.flush()
        os.fsync(handle.fileno())
    os.kill(os.getpid(), signal.SIGKILL)


def after_write(path, payload, *args, **kwargs):
    write_json(path, payload, *args, **kwargs)
    if Path(path) == panel.RESTORE_ACTIVE_MARKER and payload.get('phase') == phase:
        crash()


def after_replace(path, source):
    replace_file(path, source)
    if phase == 'replaced-database' and Path(path) == Path('/var/lib/hysteria2-panel/panel.db'):
        crash()


panel._atomic_write_json = after_write
panel.BackupManager._replace_file = staticmethod(after_replace)
raise SystemExit(panel.main(['restore-pending']))
