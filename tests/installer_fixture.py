"""Privilege boundary for disposable installed-panel acceptance clients."""

import os
from pathlib import Path
import pwd


def become_database_owner(database_path, output_directory=None):
    """Drop root before concurrent SQLite access; never widen file permissions."""
    account = pwd.getpwnam("hy2panel")
    if (os.geteuid() != 0 or account.pw_uid == 0
            or Path(database_path).stat().st_uid != account.pw_uid):
        raise RuntimeError("Expected the installed panel's non-root database owner")
    if output_directory is not None:
        os.chown(output_directory, account.pw_uid, account.pw_gid)
    os.initgroups(account.pw_name, account.pw_gid)
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    if os.geteuid() != Path(database_path).stat().st_uid:
        raise RuntimeError("Failed to adopt the database owner's identity")
