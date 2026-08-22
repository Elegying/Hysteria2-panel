#!/usr/bin/env python3
"""Dependency-free Hysteria 2 multi-user panel."""

import argparse
import base64
import contextlib
import datetime
import errno
import fcntl
import functools
import getpass
import gzip
import hashlib
import heapq
import hmac
import html
import http.client
import http.cookies
import ipaddress
import json
import logging
import os
import queue
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import ssl
import stat
# Every subprocess invocation uses a fixed executable and an argv list.
import subprocess  # nosec B404
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from qrcodegen import DataTooLongError, QrCode

from hy2panel.certificate import (
    certificate_validity_timestamps,
)
from hy2panel.health import RuntimeHealth, is_loopback_address
from hy2panel.operations import (
    EgressPolicyController,
    EgressPolicyManager,
    EgressPolicyStateError,
    RebootController,
    RestoreController,
    ServiceController,
    SystemMetrics,
    UpdateController,
)
from hy2panel.release import UpdateChecker, UpdateInstaller
from hy2panel.systemd import SystemdNotifier
from hy2panel.version import PANEL_VERSION
from hy2panel.web_assets import FAVICON_SVG, PAGE_SCRIPT, PAGE_STYLE


SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
PBKDF2_ITERATIONS = 600000
NAME_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,64}$")
LOGGER = logging.getLogger("hysteria2-panel")
DEFAULT_DEVICE_LIMIT = 3
DEFAULT_TRAFFIC_LIMIT_BYTES = 250 * 1024**3
MAX_DEVICE_LIMIT = 100
MAX_TRAFFIC_LIMIT_BYTES = 1024 * 1024**4
BACKUP_FORMAT_VERSION = 1
MAX_BACKUP_CONTENT_BYTES = 128 * 1024**2
MAX_BACKUP_ARCHIVE_BYTES = MAX_BACKUP_CONTENT_BYTES + 3 * 1024**2
BACKUP_IO_CHUNK_BYTES = 1024 * 1024
RESTORE_DISK_SAFETY_BYTES = 16 * 1024**2
RESTORE_CERTIFICATE_MIN_VALIDITY_SECONDS = 15 * 60
RESTORE_BACKUP_RETENTION_SECONDS = 30 * 86400
RESTORE_BACKUP_MAX_ENTRIES = 10
FAILED_RESTORE_RETENTION_SECONDS = 7 * 86400
FAILED_RESTORE_MAX_ENTRIES = 10
RESTORE_BACKUP_NAME_PATTERN = re.compile(
    r"restore-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}"
)
FAILED_RESTORE_NAME_PATTERN = re.compile(
    r"failed-restore-(?:"
    r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}"
    r"|orphan-(?:pending|captured)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}"
    r")\.zip"
)
MAX_STATS_RESPONSE_BYTES = 8 * 1024**2
MAX_PENDING_TRAFFIC_BYTES = 2 * MAX_STATS_RESPONSE_BYTES + 64 * 1024
AUDIT_RETENTION_SECONDS = 90 * 86400
AUDIT_MAX_ROWS = 10000
TRAFFIC_BATCH_RETENTION_SECONDS = 30 * 86400
TRAFFIC_BATCH_MAX_ROWS = 100000
MAINTENANCE_LOCK_PATH = Path("/run/hysteria2-panel-maintenance/lock")
RESTORE_ACTIVE_MARKER = Path("/etc/hysteria2-panel/.restore-active")
RESTORE_TRANSACTION_VERSION = 1
RESTORE_ENV_FILE = Path("/etc/hysteria2-panel/panel.env")
RESTORE_BACKUP_ROOT = Path("/var/backups/hysteria2-panel")
RESTORE_WORK_DIR = Path("/var/lib/hysteria2-panel/backup-restore")
RESTORE_STOP_UNITS = (
    "hysteria2-panel-tcp-probe-443.service",
    "hysteria2-panel-server-443.service",
    "hysteria2-panel-tcp-probe.service",
    "hysteria2-panel-server.service",
    "hysteria2-panel.service",
)


class ConflictError(Exception):
    """Raised when an administrator submits a stale user mutation."""


class BackupValidationError(ValueError):
    """Raised when a backup cannot be restored safely."""


def _fsync_directory(path):
    descriptor = os.open(
        str(Path(path)), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_file(path):
    descriptor = os.open(str(Path(path)), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path, payload, attempts=3):
    path = Path(path)
    value = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    failure = None
    for _attempt in range(max(1, int(attempts))):
        descriptor = None
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=".restore-transaction.", dir=str(path.parent)
            )
            with os.fdopen(descriptor, "wb") as target:
                descriptor = None
                os.fchmod(target.fileno(), 0o600)
                target.write(value)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
            temporary = None
            _fsync_directory(path.parent)
            return
        except OSError as exc:
            failure = exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
    raise RuntimeError("restore transaction could not be persisted") from failure


def _durable_unlink(path, missing_ok=True):
    path = Path(path)
    try:
        path.unlink()
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    _fsync_directory(path.parent)


def _durable_move(source, destination):
    source = Path(source)
    destination = Path(destination)
    try:
        os.replace(source, destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        descriptor, temporary = tempfile.mkstemp(
            prefix=".restore-move.", dir=str(destination.parent)
        )
        try:
            with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
                descriptor = None
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temporary, destination)
            temporary = None
            _fsync_directory(destination.parent)
            _durable_unlink(source, missing_ok=False)
            return
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
    _fsync_directory(source.parent)
    if destination.parent != source.parent:
        _fsync_directory(destination.parent)


def _read_secure_regular(path, maximum, allowed_uids=None, required_mode=None):
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise RuntimeError("unsafe restore file: {}".format(path)) from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or (allowed_uids is not None and metadata.st_uid not in allowed_uids)
            or (
                required_mode is not None
                and stat.S_IMODE(metadata.st_mode) != required_mode
            )
            or metadata.st_size < 0
            or metadata.st_size > maximum
        ):
            raise RuntimeError("unsafe restore file: {}".format(path))
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        if len(value) > maximum:
            raise RuntimeError("restore file is too large: {}".format(path))
        return value
    finally:
        os.close(descriptor)


def _secure_regular_details(path, maximum, allowed_uids=None, required_mode=None):
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags)
    except OSError as exc:
        raise RuntimeError("unsafe restore file: {}".format(path)) from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or (allowed_uids is not None and metadata.st_uid not in allowed_uids)
            or (
                required_mode is not None
                and stat.S_IMODE(metadata.st_mode) != required_mode
            )
            or metadata.st_size < 0
            or metadata.st_size > maximum
        ):
            raise RuntimeError("unsafe restore file: {}".format(path))
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, BACKUP_IO_CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            if size > maximum:
                raise RuntimeError("restore file is too large: {}".format(path))
            digest.update(chunk)
        if size != metadata.st_size:
            raise RuntimeError("restore file changed while it was verified: {}".format(path))
        return {
            "sha256": digest.hexdigest(),
            "size": size,
            "metadata": metadata,
        }
    finally:
        os.close(descriptor)


def _same_inode(left, right):
    try:
        left_metadata = os.lstat(left)
        right_metadata = os.lstat(right)
    except FileNotFoundError:
        return False
    return (left_metadata.st_dev, left_metadata.st_ino) == (
        right_metadata.st_dev,
        right_metadata.st_ino,
    )


def _remove_safe_restore_temp(path, allowed_uids, directory=False, linked_path=None):
    path = Path(path)
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    if metadata.st_uid not in allowed_uids:
        return False
    if directory:
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700:
            return False
        shutil.rmtree(path)
    else:
        linked_temp = (
            metadata.st_nlink == 2
            and linked_path is not None
            and _same_inode(path, linked_path)
        )
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (metadata.st_nlink != 1 and not linked_temp)
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            return False
        path.unlink()
    _fsync_directory(path.parent)
    return True


def _cleanup_restore_temporary_files(
    work_dir,
    pending_path,
    captured_path,
    target_paths=(),
    expected_uid=0,
    pending_uid=None,
):
    work_dir = Path(work_dir)
    try:
        work_metadata = os.lstat(work_dir)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(work_metadata.st_mode)
        or stat.S_IMODE(work_metadata.st_mode) != 0o700
    ):
        raise RuntimeError("restore work directory is unsafe")
    allowed_work_uids = {
        work_metadata.st_uid,
        expected_uid,
        work_metadata.st_uid if pending_uid is None else pending_uid,
    }
    for path in tuple(work_dir.iterdir()):
        if re.fullmatch(r"\.(?:upload|backup)-[A-Za-z0-9_]{8}\.zip", path.name):
            _remove_safe_restore_temp(
                path,
                allowed_work_uids,
                linked_path=pending_path if path.name.startswith(".upload-") else None,
            )
        elif re.fullmatch(r"\.consumed-restore-[0-9a-f]{16}\.zip", path.name):
            _remove_safe_restore_temp(path, allowed_work_uids)
        elif re.fullmatch(
            r"\.(?:restore-orphan|restore-move)\.[A-Za-z0-9_]{8}", path.name
        ):
            _remove_safe_restore_temp(path, allowed_work_uids)
        elif re.fullmatch(r"\.consumed-orphan-[0-9a-f]{16}", path.name):
            _remove_safe_restore_temp(path, allowed_work_uids)
        elif re.fullmatch(r"tmp[A-Za-z0-9_]{8}", path.name):
            _remove_safe_restore_temp(path, allowed_work_uids, directory=True)

    captured_parent = Path(captured_path).parent
    if captured_parent.exists():
        for path in tuple(captured_parent.iterdir()):
            if re.fullmatch(
                r"\.(?:restore-capture|restore-transaction)\.[A-Za-z0-9_]{8}",
                path.name,
            ) or re.fullmatch(r"\.consumed-orphan-[0-9a-f]{16}", path.name):
                _remove_safe_restore_temp(path, {expected_uid})

    target_directories = {Path(path).parent for path in target_paths}
    for directory in target_directories:
        try:
            directory_owner = os.lstat(directory).st_uid
        except FileNotFoundError:
            continue
        for path in tuple(directory.iterdir()):
            if re.fullmatch(r"\.restore-[A-Za-z0-9_]{8}", path.name):
                _remove_safe_restore_temp(
                    path, {expected_uid, directory_owner}
                )


def _write_all(descriptor, value):
    view = memoryview(value)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short write while persisting restore data")
        offset += written


def _quarantine_secure_orphan(source, destination, maximum, owner_uid):
    source = Path(source)
    destination = Path(destination)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(source), flags)
    except OSError as exc:
        raise RuntimeError("unsafe orphan restore file: {}".format(source)) from exc
    temporary = None
    target_descriptor = None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != owner_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size <= 0
            or metadata.st_size > maximum
        ):
            raise RuntimeError("unsafe orphan restore file: {}".format(source))
        target_descriptor, temporary = tempfile.mkstemp(
            prefix=".restore-orphan.", dir=str(destination.parent)
        )
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            _write_all(target_descriptor, chunk)
        os.fchmod(target_descriptor, 0o600)
        os.fsync(target_descriptor)
        os.close(target_descriptor)
        target_descriptor = None
        os.replace(temporary, destination)
        temporary = None
        _fsync_directory(destination.parent)
        consumed = source.parent / ".consumed-orphan-{}".format(secrets.token_hex(8))
        os.replace(source, consumed)
        _fsync_directory(source.parent)
        moved = os.lstat(consumed)
        if (moved.st_dev, moved.st_ino) != (metadata.st_dev, metadata.st_ino):
            _durable_unlink(consumed)
            _durable_unlink(destination)
            raise RuntimeError("orphan restore file changed during quarantine")
        _durable_unlink(consumed)
    finally:
        if target_descriptor is not None:
            os.close(target_descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        os.close(descriptor)


class BackupManager:
    CREATED_AT_PATTERN = re.compile(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
        r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z"
    )
    PANEL_VERSION_PATTERN = re.compile(
        r"(?:0|[1-9][0-9]*)\."
        r"(?:0|[1-9][0-9]*)\."
        r"(?:0|[1-9][0-9]*)"
        r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
        r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    )
    FILE_LIMITS = {
        "manifest.json": 64 * 1024,
        "data/panel.db": MAX_BACKUP_CONTENT_BYTES,
        "secrets/hmac-key.hex": 512,
        "tls/server.crt": 1024 * 1024,
        "tls/server.key": 1024 * 1024,
    }
    PAYLOAD_NAMES = {
        "data/panel.db",
        "secrets/hmac-key.hex",
        "tls/server.crt",
        "tls/server.key",
    }
    PROXY_COLUMNS = (
        "id",
        "name",
        "token_fingerprint",
        "token_seed",
        "enabled",
        "generation",
        "device_limit",
        "traffic_limit_bytes",
        "tx_bytes",
        "rx_bytes",
        "allow_udp_443",
        "created_at",
        "updated_at",
    )
    REQUIRED_PROXY_COLUMNS = tuple(
        column for column in PROXY_COLUMNS if column != "allow_udp_443"
    )

    def __init__(
        self,
        database,
        hmac_key,
        tls_cert,
        tls_key,
        public_host,
        hysteria_port,
        node_name="Hysteria 2",
        work_dir=Path("/var/lib/hysteria2-panel/backup-restore"),
        maintenance_lock_path=MAINTENANCE_LOCK_PATH,
        maintenance_lock_owner=0,
        maintenance_lock_group=None,
        maintenance_lock_mode=0o640,
        restore_marker_path=RESTORE_ACTIVE_MARKER,
        runner=subprocess.run,
    ):
        self.database = database
        self.hmac_key = bytes(hmac_key)
        self.tls_cert = Path(tls_cert)
        self.tls_key = Path(tls_key)
        self.public_host = str(public_host).strip()
        self.hysteria_port = int(hysteria_port)
        self.node_name = str(node_name)
        self.work_dir = Path(work_dir)
        self.maintenance_lock_path = Path(maintenance_lock_path)
        self.maintenance_lock_owner = maintenance_lock_owner
        self.maintenance_lock_group = maintenance_lock_group
        self.maintenance_lock_mode = maintenance_lock_mode
        self.restore_marker_path = Path(restore_marker_path)
        self.runner = runner

    @property
    def pending_archive(self):
        return self.work_dir / "pending-restore.zip"

    @staticmethod
    def _sha256(value):
        return hashlib.sha256(value).hexdigest()

    @classmethod
    def _validate_manifest_metadata(cls, manifest):
        created_at = manifest.get("createdAt")
        panel_version = manifest.get("panelVersion")
        if (
            not isinstance(created_at, str)
            or cls.CREATED_AT_PATTERN.fullmatch(created_at) is None
            or not isinstance(panel_version, str)
            or not 1 <= len(panel_version) <= 64
            or cls.PANEL_VERSION_PATTERN.fullmatch(panel_version) is None
        ):
            raise BackupValidationError("备份清单元数据无效")
        try:
            datetime.datetime.fromisoformat(created_at[:-1] + "+00:00")
        except ValueError as exc:
            raise BackupValidationError("备份清单元数据无效") from exc

    @staticmethod
    def _certificate_pin(certificate):
        try:
            pem = certificate.decode("ascii")
            der = ssl.PEM_cert_to_DER_cert(pem)
            return hashlib.sha256(der).hexdigest()
        except (UnicodeDecodeError, ValueError) as exc:
            raise BackupValidationError("证书格式无效") from exc

    def _certificate_details(self, certificate_path, private_key_path):
        certificate_public_key = self.runner(
            ["/usr/bin/openssl", "x509", "-in", str(certificate_path), "-pubkey", "-noout"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        private_public_key = self.runner(
            ["/usr/bin/openssl", "pkey", "-in", str(private_key_path), "-pubout"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if (
            certificate_public_key.returncode != 0
            or private_public_key.returncode != 0
            or not hmac.compare_digest(certificate_public_key.stdout, private_public_key.stdout)
        ):
            raise BackupValidationError("证书与私钥不匹配")
        try:
            not_before_timestamp, expires_at_timestamp = certificate_validity_timestamps(
                certificate_path, runner=self.runner
            )
        except ValueError as exc:
            raise BackupValidationError("无法读取证书有效期") from exc
        now = time.time()
        if not_before_timestamp > now:
            raise BackupValidationError("证书尚未生效")
        if expires_at_timestamp <= now + RESTORE_CERTIFICATE_MIN_VALIDITY_SECONDS:
            raise BackupValidationError("证书已过期或剩余有效期不足")
        expires_at = datetime.datetime.fromtimestamp(
            expires_at_timestamp,
            tz=datetime.timezone.utc,
        )
        return expires_at.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _database_logical_size(path):
        try:
            with sqlite3.connect(str(path), timeout=10) as connection:
                page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
                page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError) as exc:
            raise BackupValidationError("无法估算数据库备份空间") from exc
        size = page_count * page_size
        if size <= 0 or size > MAX_BACKUP_CONTENT_BYTES:
            raise BackupValidationError("数据库大小超过备份上限")
        return size

    @staticmethod
    def _copy_database(source_path, destination_path, preflight=None):
        with sqlite3.connect(str(source_path), timeout=10) as source:
            source.execute("BEGIN")
            logical_size = (
                int(source.execute("PRAGMA page_count").fetchone()[0])
                * int(source.execute("PRAGMA page_size").fetchone()[0])
            )
            if logical_size <= 0 or logical_size > MAX_BACKUP_CONTENT_BYTES:
                raise BackupValidationError("数据库大小超过备份上限")
            if preflight is not None:
                preflight(logical_size)
            with sqlite3.connect(str(destination_path), timeout=10) as destination:
                source.backup(destination)
        descriptor = os.open(str(destination_path), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return logical_size

    @staticmethod
    def _read_bounded(path, maximum):
        with Path(path).open("rb") as source:
            value = source.read(maximum + 1)
        if len(value) > maximum:
            raise BackupValidationError("备份内容超过允许大小")
        return value

    @staticmethod
    def _file_details(path, maximum=None):
        digest = hashlib.sha256()
        size = 0
        with Path(path).open("rb") as source:
            while True:
                chunk = source.read(BACKUP_IO_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if maximum is not None and size > maximum:
                    raise BackupValidationError("备份内容超过允许大小")
                digest.update(chunk)
        return {"sha256": digest.hexdigest(), "size": size}

    @staticmethod
    def _replace_file(path, source_path):
        path = Path(path)
        source_path = Path(source_path)
        existing = path.stat()
        descriptor, temporary = tempfile.mkstemp(
            prefix=".restore-", dir=str(path.parent)
        )
        try:
            with source_path.open("rb") as source, os.fdopen(descriptor, "wb") as target:
                descriptor = None
                shutil.copyfileobj(source, target, length=BACKUP_IO_CHUNK_BYTES)
                target.flush()
                if hasattr(os, "fchown"):
                    os.fchown(target.fileno(), existing.st_uid, existing.st_gid)
                os.fchmod(target.fileno(), stat.S_IMODE(existing.st_mode))
                os.fsync(target.fileno())
            os.replace(temporary, path)
            temporary = None
            _fsync_directory(path.parent)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _require_free_space(path, required_bytes):
        try:
            free = shutil.disk_usage(Path(path)).free
        except OSError as exc:
            raise BackupValidationError("无法检查恢复所需磁盘空间") from exc
        if free < max(0, int(required_bytes)):
            raise BackupValidationError("磁盘可用空间不足，无法安全恢复")

    def _require_space_allocations(self, allocations):
        requirements = {}
        for path, required_bytes in allocations:
            path = Path(path)
            try:
                device = path.stat().st_dev
            except OSError as exc:
                raise BackupValidationError("无法检查恢复目录所在文件系统") from exc
            if device not in requirements:
                requirements[device] = [path, 0]
            requirements[device][1] += max(0, int(required_bytes))
        for path, required_bytes in requirements.values():
            self._require_free_space(
                path, required_bytes + RESTORE_DISK_SAFETY_BYTES
            )

    @staticmethod
    def _prune_entries(root, name_pattern, retention_seconds, maximum, keep=()):
        root = Path(root)
        if not root.exists():
            return
        resolved_root = root.resolve()
        keep = {Path(path).resolve() for path in keep}
        kept_count = sum(
            1
            for path in keep
            if path.parent == resolved_root
            and name_pattern.fullmatch(path.name)
            and path.exists()
        )
        available_slots = max(0, int(maximum) - kept_count)
        now = time.time()
        candidates = []
        for path in root.iterdir():
            if not name_pattern.fullmatch(path.name) or path.resolve() in keep:
                continue
            try:
                modified = path.stat().st_mtime
            except FileNotFoundError:
                continue
            candidates.append((modified, path))
        candidates.sort(reverse=True)
        removed = False
        for index, (modified, path) in enumerate(candidates):
            if index < available_slots and now - modified <= retention_seconds:
                continue
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            removed = True
        if removed:
            _fsync_directory(root)

    def create_archive(self):
        with maintenance_upload_slot(
            self.maintenance_lock_path,
            expected_uid=self.maintenance_lock_owner,
            expected_gid=self.maintenance_lock_group,
            expected_mode=self.maintenance_lock_mode,
        ):
            return self._create_archive_locked()

    def _create_archive_locked(self):
        self.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_path = self.work_dir / "hysteria2-panel-backup-{}-{}.zip".format(
            timestamp, secrets.token_hex(4)
        )
        descriptor, temporary_archive = tempfile.mkstemp(
            prefix=".backup-", suffix=".zip", dir=str(self.work_dir)
        )
        os.close(descriptor)
        try:
            with tempfile.TemporaryDirectory(dir=str(self.work_dir)) as temporary:
                temporary_path = Path(temporary)
                database_path = temporary_path / "panel.db"
                extra_payload_bytes = (
                    self.tls_cert.stat().st_size
                    + self.tls_key.stat().st_size
                    + self.FILE_LIMITS["secrets/hmac-key.hex"]
                    + self.FILE_LIMITS["manifest.json"]
                )
                self._copy_database(
                    self.database.path,
                    database_path,
                    preflight=lambda logical_size: self._require_free_space(
                        self.work_dir,
                        3 * logical_size
                        + 2 * extra_payload_bytes
                        + RESTORE_DISK_SAFETY_BYTES,
                    ),
                )
                with sqlite3.connect(str(database_path)) as connection:
                    connection.execute("PRAGMA journal_mode = DELETE")
                    connection.execute("PRAGMA foreign_keys = ON")
                    connection.execute("DELETE FROM sessions")
                    connection.execute("DELETE FROM admins")
                    connection.execute("DELETE FROM audit_log")
                    connection.execute("DELETE FROM applied_traffic_batches")
                    user_count = connection.execute(
                        "SELECT COUNT(*) FROM proxy_users"
                    ).fetchone()[0]
                certificate = self._read_bounded(
                    self.tls_cert, self.FILE_LIMITS["tls/server.crt"]
                )
                private_key = self._read_bounded(
                    self.tls_key, self.FILE_LIMITS["tls/server.key"]
                )
                payload_paths = {
                    "data/panel.db": database_path,
                    "secrets/hmac-key.hex": temporary_path / "hmac-key.hex",
                    "tls/server.crt": temporary_path / "server.crt",
                    "tls/server.key": temporary_path / "server.key",
                }
                payload_paths["secrets/hmac-key.hex"].write_bytes(
                    self.hmac_key.hex().encode("ascii") + b"\n"
                )
                payload_paths["tls/server.crt"].write_bytes(certificate)
                payload_paths["tls/server.key"].write_bytes(private_key)
                expires_at = self._certificate_details(
                    payload_paths["tls/server.crt"], payload_paths["tls/server.key"]
                )
                manifest = {
                    "formatVersion": BACKUP_FORMAT_VERSION,
                    "createdAt": datetime.datetime.now(datetime.timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "panelVersion": PANEL_VERSION,
                    "proxyUserCount": int(user_count),
                    "source": {
                        "publicHost": self.public_host,
                        "hysteriaPort": self.hysteria_port,
                        "nodeName": self.node_name,
                    },
                    "certificate": {
                        "pinSHA256": self._certificate_pin(certificate),
                        "notAfter": expires_at,
                    },
                    "files": {
                        name: self._file_details(path, self.FILE_LIMITS[name])
                        for name, path in sorted(payload_paths.items())
                    },
                }
                manifest_bytes = json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                with zipfile.ZipFile(
                    temporary_archive,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                ) as package:
                    package.writestr("manifest.json", manifest_bytes)
                    for name, path in payload_paths.items():
                        package.write(path, arcname=name)
            os.chmod(temporary_archive, 0o600)
            _fsync_file(temporary_archive)
            self.validate_archive(temporary_archive)
            os.replace(temporary_archive, archive_path)
            temporary_archive = None
            _fsync_directory(self.work_dir)
            return archive_path
        finally:
            if temporary_archive is not None:
                try:
                    os.unlink(temporary_archive)
                except FileNotFoundError:
                    pass

    def _extract_archive(self, archive_path, destination):
        archive_path = Path(archive_path)
        destination = Path(destination)
        try:
            archive_size = archive_path.stat().st_size
        except OSError as exc:
            raise BackupValidationError("无法读取备份文件") from exc
        if archive_size <= 0 or archive_size > MAX_BACKUP_ARCHIVE_BYTES:
            raise BackupValidationError("备份文件大小无效")
        try:
            with zipfile.ZipFile(archive_path) as package:
                entries = package.infolist()
                names = [entry.filename for entry in entries]
                if len(names) != len(set(names)) or set(names) != set(self.FILE_LIMITS):
                    raise BackupValidationError("备份文件结构无效")
                total_size = 0
                payload_paths = {}
                payload_details = {}
                for entry in entries:
                    mode = (entry.external_attr >> 16) & 0o170000
                    if (
                        entry.is_dir()
                        or mode == stat.S_IFLNK
                        or entry.filename.startswith(("/", "\\"))
                        or ".." in Path(entry.filename).parts
                        or entry.file_size < 0
                        or entry.file_size > self.FILE_LIMITS[entry.filename]
                    ):
                        raise BackupValidationError("备份文件结构无效")
                    total_size += entry.file_size
                    if total_size > MAX_BACKUP_CONTENT_BYTES + 3 * 1024**2:
                        raise BackupValidationError("备份解压内容过大")
                self._require_free_space(
                    destination.parent,
                    total_size + RESTORE_DISK_SAFETY_BYTES,
                )
                for entry in entries:
                    target = destination / entry.filename
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    digest = hashlib.sha256()
                    extracted_size = 0
                    with package.open(entry) as source, target.open("xb") as output:
                        while True:
                            chunk = source.read(BACKUP_IO_CHUNK_BYTES)
                            if not chunk:
                                break
                            extracted_size += len(chunk)
                            if extracted_size > self.FILE_LIMITS[entry.filename]:
                                raise BackupValidationError("备份内容大小无效")
                            output.write(chunk)
                            digest.update(chunk)
                    if extracted_size != entry.file_size:
                        raise BackupValidationError("备份内容大小无效")
                    os.chmod(target, 0o600)
                    payload_paths[entry.filename] = target
                    payload_details[entry.filename] = {
                        "sha256": digest.hexdigest(),
                        "size": extracted_size,
                    }
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            if isinstance(exc, BackupValidationError):
                raise
            raise BackupValidationError("ZIP 备份文件无效") from exc
        try:
            manifest = json.loads(
                self._read_bounded(
                    payload_paths["manifest.json"], self.FILE_LIMITS["manifest.json"]
                ).decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupValidationError("备份清单无效") from exc
        if not isinstance(manifest, dict) or manifest.get("formatVersion") != BACKUP_FORMAT_VERSION:
            raise BackupValidationError("不支持的备份格式版本")
        self._validate_manifest_metadata(manifest)
        file_manifest = manifest.get("files")
        if not isinstance(file_manifest, dict) or set(file_manifest) != self.PAYLOAD_NAMES:
            raise BackupValidationError("备份校验清单无效")
        for name in self.PAYLOAD_NAMES:
            details = file_manifest.get(name)
            if (
                not isinstance(details, dict)
                or details.get("size") != payload_details[name]["size"]
                or details.get("sha256") != payload_details[name]["sha256"]
            ):
                raise BackupValidationError("备份文件校验失败")
        return manifest, payload_paths

    def _validate_database_path(self, database_path, hmac_key):
        database_path = Path(database_path)
        try:
            with sqlite3.connect(str(database_path)) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise BackupValidationError("用户数据库完整性检查失败")
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                if not {"admins", "proxy_users", "sessions", "audit_log"}.issubset(tables):
                    raise BackupValidationError("用户数据库结构不完整")
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(proxy_users)")
                }
                if not set(self.REQUIRED_PROXY_COLUMNS).issubset(columns):
                    raise BackupValidationError("用户数据库版本不兼容")
                users = connection.execute(
                    "SELECT id, token_seed, token_fingerprint FROM proxy_users"
                )
                verifier = Database(database_path, hmac_key)
                user_count = 0
                for _user_id, seed, expected_fingerprint in users:
                    user_count += 1
                    if seed is None:
                        continue
                    if not isinstance(seed, bytes):
                        raise BackupValidationError("用户数据库令牌种子格式无效")
                    token = verifier._token_from_seed(bytes(seed))
                    if not hmac.compare_digest(
                        verifier._fingerprint(token), expected_fingerprint
                    ):
                        raise BackupValidationError("用户签名密钥与数据库不匹配")
                return user_count
        except sqlite3.DatabaseError as exc:
            raise BackupValidationError("用户数据库无效") from exc

    def _validate_database(self, database_bytes, hmac_key, directory):
        database_path = Path(directory) / "validated.db"
        database_path.write_bytes(database_bytes)
        return self._validate_database_path(database_path, hmac_key)

    def _validate_extracted_archive(
        self, manifest, payload_paths, require_compatible_endpoint=False
    ):
        try:
            hmac_hex = self._read_bounded(
                payload_paths["secrets/hmac-key.hex"],
                self.FILE_LIMITS["secrets/hmac-key.hex"],
            ).decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise BackupValidationError("签名密钥格式无效") from exc
        if not re.fullmatch(r"[0-9a-f]{64,256}", hmac_hex) or len(hmac_hex) % 2:
            raise BackupValidationError("签名密钥格式无效")
        hmac_key = bytes.fromhex(hmac_hex)
        source = manifest.get("source")
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("publicHost"), str)
            or not isinstance(source.get("hysteriaPort"), int)
            or not isinstance(source.get("nodeName"), str)
        ):
            raise BackupValidationError("备份来源信息无效")
        if require_compatible_endpoint:
            if source["publicHost"].lower() != self.public_host.lower():
                raise BackupValidationError(
                    "备份域名与当前部署域名不一致，旧节点无法无感迁移"
                )
            if source["hysteriaPort"] != self.hysteria_port:
                raise BackupValidationError(
                    "备份 UDP 端口与当前部署端口不一致，旧节点无法无感迁移"
                )
        user_count = self._validate_database_path(
            payload_paths["data/panel.db"], hmac_key
        )
        expires_at = self._certificate_details(
            payload_paths["tls/server.crt"], payload_paths["tls/server.key"]
        )
        certificate_bytes = self._read_bounded(
            payload_paths["tls/server.crt"], self.FILE_LIMITS["tls/server.crt"]
        )
        certificate = manifest.get("certificate")
        pin = self._certificate_pin(certificate_bytes)
        if (
            not isinstance(certificate, dict)
            or certificate.get("pinSHA256") != pin
            or certificate.get("notAfter") != expires_at
            or manifest.get("proxyUserCount") != user_count
        ):
            raise BackupValidationError("证书或用户数量校验失败")
        return hmac_key

    def validate_archive(self, archive_path, require_compatible_endpoint=False):
        self.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=str(self.work_dir)) as temporary:
            manifest, payload_paths = self._extract_archive(archive_path, temporary)
            self._validate_extracted_archive(
                manifest,
                payload_paths,
                require_compatible_endpoint=require_compatible_endpoint,
            )
        return manifest

    def stage_archive(self, source, content_length):
        if content_length <= 0 or content_length > MAX_BACKUP_ARCHIVE_BYTES:
            raise BackupValidationError("备份文件大小无效")
        try:
            with maintenance_upload_slot(
                self.maintenance_lock_path,
                expected_uid=self.maintenance_lock_owner,
                expected_gid=self.maintenance_lock_group,
                expected_mode=self.maintenance_lock_mode,
            ):
                try:
                    os.lstat(self.restore_marker_path)
                except FileNotFoundError:
                    pass
                else:
                    raise BackupValidationError(
                        "已有恢复事务正在完成健康检查，请稍后再上传"
                    )
                self.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor, temporary = tempfile.mkstemp(
                    prefix=".upload-", suffix=".zip", dir=str(self.work_dir)
                )
                remaining = content_length
                try:
                    with os.fdopen(descriptor, "wb") as target:
                        while remaining:
                            chunk = source.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise BackupValidationError("备份文件上传不完整")
                            target.write(chunk)
                            remaining -= len(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                    manifest = self.validate_archive(
                        temporary, require_compatible_endpoint=True
                    )
                    os.chmod(temporary, 0o600)
                    try:
                        os.link(temporary, self.pending_archive)
                    except FileExistsError as exc:
                        raise BackupValidationError("已有恢复任务正在等待或执行") from exc
                    _fsync_directory(self.work_dir)
                    return manifest
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
        except RuntimeError as exc:
            if "维护任务正在运行" in str(exc):
                raise BackupValidationError("服务器维护任务正在运行，请稍后重试恢复") from exc
            raise

    @staticmethod
    def _updated_env(original, values):
        lines = original.decode("utf-8").splitlines()
        found = set()
        updated = []
        for line in lines:
            match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
            if match and match.group(1) in values:
                key = match.group(1)
                if key in found:
                    raise BackupValidationError("环境配置包含重复关键项")
                updated.append("{}={}".format(key, values[key]))
                found.add(key)
            else:
                updated.append(line)
        for key, value in values.items():
            if key not in found:
                updated.append("{}={}".format(key, value))
        return ("\n".join(updated) + "\n").encode("utf-8")

    @staticmethod
    def _replace_bytes(path, value):
        path = Path(path)
        existing = path.stat()
        descriptor, temporary = tempfile.mkstemp(prefix=".restore-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(value)
                target.flush()
                if hasattr(os, "fchown"):
                    os.fchown(target.fileno(), existing.st_uid, existing.st_gid)
                os.fchmod(target.fileno(), stat.S_IMODE(existing.st_mode))
                os.fsync(target.fileno())
            os.replace(temporary, path)
            _fsync_directory(path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _secure_pending_archive(self, captured_path=None, pending_path=None):
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        target_descriptor = None
        temporary = None
        try:
            descriptor = os.open(str(pending_path or self.pending_archive), flags)
        except OSError as exc:
            raise BackupValidationError("待恢复文件不安全或不存在") from exc
        try:
            metadata = os.fstat(descriptor)
            database_owner = self.database.path.stat().st_uid
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != database_owner
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size <= 0
                or metadata.st_size > MAX_BACKUP_ARCHIVE_BYTES
            ):
                raise BackupValidationError("待恢复文件所有权或类型无效")
            digest = hashlib.sha256()
            if captured_path is not None:
                captured_path = Path(captured_path)
                target_descriptor, temporary = tempfile.mkstemp(
                    prefix=".restore-capture.", dir=str(captured_path.parent)
                )
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                if target_descriptor is not None:
                    _write_all(target_descriptor, chunk)
            if target_descriptor is not None:
                os.fchmod(target_descriptor, 0o600)
                os.fsync(target_descriptor)
                os.close(target_descriptor)
                target_descriptor = None
                os.replace(temporary, captured_path)
                temporary = None
                _fsync_directory(captured_path.parent)
            return digest.hexdigest(), metadata.st_size, metadata
        finally:
            if target_descriptor is not None:
                os.close(target_descriptor)
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
            os.close(descriptor)

    def _consume_captured_pending(self, captured_metadata):
        consumed = self.work_dir / ".consumed-restore-{}.zip".format(
            secrets.token_hex(8)
        )
        os.replace(self.pending_archive, consumed)
        _fsync_directory(self.work_dir)
        consumed_metadata = os.lstat(consumed)
        if (consumed_metadata.st_dev, consumed_metadata.st_ino) != (
            captured_metadata.st_dev,
            captured_metadata.st_ino,
        ):
            _durable_unlink(consumed)
            raise BackupValidationError("待恢复文件在捕获期间发生变化")
        _durable_unlink(consumed)

    def _discard_matching_pending(self, digest, size):
        try:
            pending_digest, pending_size, metadata = self._secure_pending_archive()
        except BackupValidationError:
            return
        if pending_digest != digest or pending_size != size:
            raise BackupValidationError("待恢复文件在捕获期间发生变化")
        self._consume_captured_pending(metadata)

    def queue_restore_transaction(self, marker_path, env_file, backup_root):
        captured_archive = Path(str(marker_path) + ".archive")
        digest, size, captured_metadata = self._secure_pending_archive(captured_archive)
        try:
            self.validate_archive(captured_archive, require_compatible_endpoint=True)
        except Exception:
            quarantine = self.work_dir / "failed-restore-{}-{}.zip".format(
                datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                secrets.token_hex(4),
            )
            _durable_move(captured_archive, quarantine)
            self._discard_matching_pending(digest, size)
            self._prune_entries(
                self.work_dir,
                FAILED_RESTORE_NAME_PATTERN,
                FAILED_RESTORE_RETENTION_SECONDS,
                FAILED_RESTORE_MAX_ENTRIES,
                keep=(quarantine,),
            )
            raise
        record = {
            "version": RESTORE_TRANSACTION_VERSION,
            "phase": "queued",
            "pendingArchive": str(self.pending_archive),
            "pendingSha256": digest,
            "pendingSize": size,
            "queuedArchive": str(captured_archive),
            "databasePath": str(self.database.path),
            "tlsCert": str(self.tls_cert),
            "tlsKey": str(self.tls_key),
            "envFile": str(Path(env_file)),
            "workDir": str(self.work_dir),
            "backupRoot": str(Path(backup_root)),
            "publicHost": self.public_host,
            "hysteriaPort": self.hysteria_port,
            "nodeName": self.node_name,
        }
        _atomic_write_json(marker_path, record)
        self._consume_captured_pending(captured_metadata)
        return record

    def _quarantine_pending(self):
        quarantine = self.work_dir / "failed-restore-{}-{}.zip".format(
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            secrets.token_hex(4),
        )
        try:
            os.replace(self.pending_archive, quarantine)
        except FileNotFoundError:
            return None
        _fsync_directory(self.work_dir)
        self._prune_entries(
            self.work_dir,
            FAILED_RESTORE_NAME_PATTERN,
            FAILED_RESTORE_RETENTION_SECONDS,
            FAILED_RESTORE_MAX_ENTRIES,
            keep=(quarantine,),
        )
        return quarantine

    @staticmethod
    def _required_env_value(env_bytes, key):
        try:
            lines = env_bytes.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise BackupValidationError("恢复后的环境配置编码无效") from exc
        values = []
        for line in lines:
            match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
            if match and match.group(1) == key:
                values.append(match.group(2))
        if len(values) != 1:
            raise BackupValidationError("恢复后的环境配置缺少或重复关键项")
        return values[0]

    def _proxy_rows_equal(self, first_database, second_database):
        try:
            with sqlite3.connect(str(first_database)) as first, sqlite3.connect(
                str(second_database)
            ) as second:
                query = (
                    # Identifiers come only from the fixed PROXY_COLUMNS tuple.
                    "SELECT {} FROM proxy_users ORDER BY id".format(  # nosec B608
                        ",".join(self.PROXY_COLUMNS)
                    )
                )
                first_rows = first.execute(query)
                second_rows = second.execute(query)
                while True:
                    first_batch = first_rows.fetchmany(256)
                    second_batch = second_rows.fetchmany(256)
                    if first_batch != second_batch:
                        return False
                    if not first_batch:
                        return True
        except sqlite3.DatabaseError as exc:
            raise BackupValidationError("恢复后的用户数据库无法读取") from exc

    def _validate_applied_restore(
        self, env_file, restored_hmac, manifest, directory, expected_database
    ):
        user_count = self._validate_database_path(self.database.path, restored_hmac)
        if not self._proxy_rows_equal(self.database.path, expected_database):
            raise BackupValidationError("恢复后的用户数据与备份不一致")
        certificate = self._read_bounded(
            self.tls_cert, self.FILE_LIMITS["tls/server.crt"]
        )
        private_key = self._read_bounded(
            self.tls_key, self.FILE_LIMITS["tls/server.key"]
        )
        expires_at = self._certificate_details(self.tls_cert, self.tls_key)
        expected_certificate = manifest["certificate"]
        if (
            user_count != manifest["proxyUserCount"]
            or self._sha256(certificate)
            != manifest["files"]["tls/server.crt"]["sha256"]
            or self._sha256(private_key)
            != manifest["files"]["tls/server.key"]["sha256"]
            or self._certificate_pin(certificate) != expected_certificate["pinSHA256"]
            or expires_at != expected_certificate["notAfter"]
        ):
            raise BackupValidationError("恢复后的节点身份校验失败")
        env_bytes = Path(env_file).read_bytes()
        if not hmac.compare_digest(
            self._required_env_value(env_bytes, "HY2PANEL_HMAC_KEY"),
            restored_hmac.hex(),
        ) or not hmac.compare_digest(
            self._required_env_value(env_bytes, "HY2PANEL_CERT_PIN"),
            expected_certificate["pinSHA256"],
        ):
            raise BackupValidationError("恢复后的签名密钥或证书指纹不一致")

    def apply_archive(
        self, archive_path, env_file, backup_root, transaction_path=None
    ):
        self.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup_root = Path(backup_root)
        backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        env_file = Path(env_file)
        with tempfile.TemporaryDirectory(dir=str(self.work_dir)) as temporary:
            temporary_path = Path(temporary)
            manifest, payload_paths = self._extract_archive(
                archive_path, temporary_path / "incoming"
            )
            restored_hmac = self._validate_extracted_archive(
                manifest, payload_paths, require_compatible_endpoint=True
            )
            self._prune_entries(
                backup_root,
                RESTORE_BACKUP_NAME_PATTERN,
                RESTORE_BACKUP_RETENTION_SECONDS,
                max(0, RESTORE_BACKUP_MAX_ENTRIES - 1),
            )
            database_size = self._database_logical_size(self.database.path)
            incoming_database_size = int(
                manifest["files"]["data/panel.db"]["size"]
            )
            # SQLite can keep the destination's retained tables/pages while it
            # inserts every proxy row from the incoming database. The sum is a
            # conservative upper bound for both staging and atomic replacement.
            replacement_database_size = database_size + incoming_database_size
            archive_size = Path(archive_path).stat().st_size
            new_env = self._updated_env(
                env_file.read_bytes(),
                {
                    "HY2PANEL_HMAC_KEY": restored_hmac.hex(),
                    "HY2PANEL_CERT_PIN": manifest["certificate"]["pinSHA256"],
                },
            )
            backup_bytes = (
                database_size
                + archive_size
                + self.tls_cert.stat().st_size
                + self.tls_key.stat().st_size
                + env_file.stat().st_size
            )
            self._require_space_allocations(
                (
                    (backup_root, backup_bytes),
                    (self.work_dir, replacement_database_size),
                    (self.database.path.parent, replacement_database_size),
                    (
                        self.tls_cert.parent,
                        payload_paths["tls/server.crt"].stat().st_size,
                    ),
                    (
                        self.tls_key.parent,
                        payload_paths["tls/server.key"].stat().st_size,
                    ),
                    (env_file.parent, len(new_env)),
                )
            )

            backup_dir = backup_root / "restore-{}-{}".format(
                datetime.datetime.now(datetime.timezone.utc).strftime(
                    "%Y%m%dT%H%M%SZ"
                ),
                secrets.token_hex(4),
            )
            backup_dir.mkdir(mode=0o700)
            self._copy_database(self.database.path, backup_dir / "panel.db")
            shutil.copy2(self.tls_cert, backup_dir / "server.crt")
            shutil.copy2(self.tls_key, backup_dir / "server.key")
            shutil.copy2(env_file, backup_dir / "panel.env")
            incoming_archive = backup_dir / "incoming.zip"
            shutil.copyfile(archive_path, incoming_archive)
            for durable_file in (
                backup_dir / "panel.db",
                backup_dir / "server.crt",
                backup_dir / "server.key",
                backup_dir / "panel.env",
                incoming_archive,
            ):
                os.chmod(durable_file, 0o600)
                _fsync_file(durable_file)
            _fsync_directory(backup_dir)
            _fsync_directory(backup_root)
            if transaction_path is not None:
                record = _read_restore_transaction(
                    transaction_path,
                    expected_uid=os.geteuid() if hasattr(os, "geteuid") else None,
                    strict_paths=False,
                )
                if record["phase"] != "queued":
                    raise RuntimeError("restore transaction phase is invalid")
                record.update(
                    {
                        "phase": "prepared",
                        "backupDir": str(backup_dir),
                        "incomingArchive": str(incoming_archive),
                        "oldFiles": {
                            name: self._file_details(backup_dir / name)["sha256"]
                            for name in (
                                "panel.db",
                                "server.crt",
                                "server.key",
                                "panel.env",
                            )
                        },
                    }
                )
                _atomic_write_json(transaction_path, record)
            staged_database = Path(temporary) / "panel.db"
            self._copy_database(self.database.path, staged_database)
            incoming_database = payload_paths["data/panel.db"]
            with sqlite3.connect(str(incoming_database)) as source:
                source.row_factory = sqlite3.Row
                incoming_columns = {
                    row[1] for row in source.execute("PRAGMA table_info(proxy_users)")
                }
                if "allow_udp_443" not in incoming_columns:
                    source.execute(
                        "ALTER TABLE proxy_users ADD COLUMN allow_udp_443 INTEGER NOT NULL DEFAULT 0"
                    )
                rows = source.execute(
                    # Identifiers come only from the fixed PROXY_COLUMNS tuple.
                    "SELECT {} FROM proxy_users ORDER BY id".format(  # nosec B608
                        ",".join(self.PROXY_COLUMNS)
                    )
                )
                with sqlite3.connect(str(staged_database)) as destination:
                    destination.execute("PRAGMA journal_mode = DELETE")
                    destination.execute("PRAGMA foreign_keys = ON")
                    destination.execute("DELETE FROM sessions")
                    destination.execute("DELETE FROM proxy_users")
                    destination.executemany(
                        # Identifiers come only from the fixed PROXY_COLUMNS tuple.
                        "INSERT INTO proxy_users ({}) VALUES ({})".format(  # nosec B608
                            ",".join(self.PROXY_COLUMNS),
                            ",".join("?" for _ in self.PROXY_COLUMNS),
                        ),
                        (
                            tuple(row[column] for column in self.PROXY_COLUMNS)
                            for row in rows
                        ),
                    )
            self._validate_database_path(staged_database, restored_hmac)
            try:
                self._replace_file(self.database.path, staged_database)
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(self.database.path) + suffix)
                    _durable_unlink(sidecar)
                self._replace_file(self.tls_cert, payload_paths["tls/server.crt"])
                self._replace_file(self.tls_key, payload_paths["tls/server.key"])
                self._replace_bytes(env_file, new_env)
                self._validate_applied_restore(
                    env_file,
                    restored_hmac,
                    manifest,
                    temporary,
                    incoming_database,
                )
            except Exception:
                self._replace_file(self.database.path, backup_dir / "panel.db")
                for suffix in ("-wal", "-shm"):
                    _durable_unlink(Path(str(self.database.path) + suffix))
                self._replace_file(self.tls_cert, backup_dir / "server.crt")
                self._replace_file(self.tls_key, backup_dir / "server.key")
                self._replace_bytes(env_file, (backup_dir / "panel.env").read_bytes())
                if transaction_path is not None:
                    record["phase"] = "disk-consistent"
                    record["outcome"] = "rolled-back"
                    _atomic_write_json(transaction_path, record)
                raise
            self._prune_entries(
                backup_root,
                RESTORE_BACKUP_NAME_PATTERN,
                RESTORE_BACKUP_RETENTION_SECONDS,
                RESTORE_BACKUP_MAX_ENTRIES,
                keep=(backup_dir,),
            )
        if transaction_path is not None:
            record["phase"] = "disk-consistent"
            record["outcome"] = "applied"
            _atomic_write_json(transaction_path, record)
        result = dict(manifest)
        result["automaticBackup"] = str(backup_dir)
        return result

    def apply_pending_archive(
        self, env_file, backup_root, transaction_path=None, archive_path=None
    ):
        archive_path = Path(archive_path) if archive_path is not None else self.pending_archive
        if archive_path == self.pending_archive:
            self._secure_pending_archive()
        try:
            result = self.apply_archive(
                archive_path,
                env_file=env_file,
                backup_root=backup_root,
                transaction_path=transaction_path,
            )
        except Exception:
            try:
                if archive_path == self.pending_archive:
                    self._quarantine_pending()
            except OSError:
                LOGGER.exception("failed restore archive could not be quarantined")
            raise
        _durable_unlink(archive_path)
        return result


def hash_password(password):
    if not isinstance(password, str) or len(password) < 8 or len(password) > 1024:
        raise ValueError("password must contain 8 to 1024 characters")
    salt = secrets.token_bytes(16)
    if hasattr(hashlib, "scrypt"):
        derived = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
        )
        return "scrypt${}${}${}${}${}".format(
            SCRYPT_N, SCRYPT_R, SCRYPT_P, salt.hex(), derived.hex()
        )
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32
    )
    return "pbkdf2_sha256${}${}${}".format(PBKDF2_ITERATIONS, salt.hex(), derived.hex())


def verify_password(password, encoded):
    try:
        if not isinstance(password, str) or len(password) > 1024:
            return False
        parts = encoded.split("$")
        algorithm = parts[0]
        if algorithm == "scrypt" and len(parts) == 6 and hasattr(hashlib, "scrypt"):
            _, n, r, p, salt_hex, expected_hex = parts
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(expected_hex)
            if (
                (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)
                or len(salt) != 16
                or len(expected) != 32
            ):
                return False
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=SCRYPT_N,
                r=SCRYPT_R,
                p=SCRYPT_P,
                dklen=32,
            )
        elif algorithm == "pbkdf2_sha256" and len(parts) == 4:
            _, iterations, salt_hex, expected_hex = parts
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(expected_hex)
            if (
                int(iterations) != PBKDF2_ITERATIONS
                or len(salt) != 16
                or len(expected) != 32
            ):
                return False
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                PBKDF2_ITERATIONS,
                dklen=32,
            )
        else:
            return False
        return hmac.compare_digest(actual, expected)
    except (AttributeError, TypeError, ValueError):
        return False


@functools.lru_cache(maxsize=1)
def _dummy_admin_password_hash():
    # Use the runtime's preferred KDF so unknown usernames do not take a cheaper path.
    return hash_password(secrets.token_urlsafe(32))


def _validate_name(name):
    if not isinstance(name, str):
        raise ValueError("name must be text")
    normalized = name.strip()
    if not NAME_PATTERN.fullmatch(normalized):
        raise ValueError("name must contain 1 to 64 printable characters")
    return normalized


def _validate_token(token):
    if not isinstance(token, str) or not 8 <= len(token) <= 512:
        raise ValueError("token must contain 8 to 512 characters")
    return token


class Database:
    def __init__(self, path, hmac_key):
        self.path = Path(path)
        if not isinstance(hmac_key, bytes) or len(hmac_key) < 32:
            raise ValueError("hmac key must contain at least 32 bytes")
        self.hmac_key = hmac_key
        self._dummy_password_hash = _dummy_admin_password_hash()

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def readiness_probe(self):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'proxy_users'"
            ).fetchone()
        return row is not None

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proxy_users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    token_fingerprint TEXT NOT NULL UNIQUE,
                    token_seed BLOB,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                    generation INTEGER NOT NULL DEFAULT 0,
                    device_limit INTEGER NOT NULL DEFAULT 3 CHECK (device_limit BETWEEN 1 AND 100),
                    traffic_limit_bytes INTEGER NOT NULL DEFAULT 268435456000 CHECK (traffic_limit_bytes > 0),
                    tx_bytes INTEGER NOT NULL DEFAULT 0 CHECK (tx_bytes >= 0),
                    rx_bytes INTEGER NOT NULL DEFAULT 0 CHECK (rx_bytes >= 0),
                    allow_udp_443 INTEGER NOT NULL DEFAULT 0 CHECK (allow_udp_443 IN (0, 1)),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    remote_ip TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS audit_log_created_at_idx
                    ON audit_log(created_at);
                CREATE TABLE IF NOT EXISTS applied_traffic_batches (
                    batch_id TEXT PRIMARY KEY,
                    applied_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS applied_traffic_batches_applied_at_idx
                    ON applied_traffic_batches(applied_at);
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(proxy_users)")
            }
            if "generation" not in columns:
                connection.execute(
                    "ALTER TABLE proxy_users ADD COLUMN generation INTEGER NOT NULL DEFAULT 0"
                )
            migrations = {
                "token_seed": "ALTER TABLE proxy_users ADD COLUMN token_seed BLOB",
                "device_limit": "ALTER TABLE proxy_users ADD COLUMN device_limit INTEGER NOT NULL DEFAULT 3",
                "traffic_limit_bytes": "ALTER TABLE proxy_users ADD COLUMN traffic_limit_bytes INTEGER NOT NULL DEFAULT 268435456000",
                "tx_bytes": "ALTER TABLE proxy_users ADD COLUMN tx_bytes INTEGER NOT NULL DEFAULT 0",
                "rx_bytes": "ALTER TABLE proxy_users ADD COLUMN rx_bytes INTEGER NOT NULL DEFAULT 0",
                "allow_udp_443": "ALTER TABLE proxy_users ADD COLUMN allow_udp_443 INTEGER NOT NULL DEFAULT 0",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    connection.execute(statement)

    def _fingerprint(self, token):
        return hmac.new(self.hmac_key, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _token_from_seed(self, seed):
        digest = hmac.new(self.hmac_key, b"proxy-token\0" + seed, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def upsert_admin(self, username, password):
        username = _validate_name(username)
        password_hash = hash_password(password)
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM admins ORDER BY id LIMIT 1"
            ).fetchone()
            if row:
                # The panel has one administrator. Renaming it must not leave an old
                # credential valid, and any credential change revokes every session.
                connection.execute("DELETE FROM sessions")
                connection.execute("DELETE FROM admins WHERE id <> ?", (row["id"],))
                connection.execute(
                    "UPDATE admins SET username = ?, password_hash = ?, updated_at = ? WHERE id = ?",
                    (username, password_hash, now, row["id"]),
                )
                return row["id"]
            cursor = connection.execute(
                "INSERT INTO admins(username, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, now, now),
            )
            return cursor.lastrowid

    def has_admin(self):
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM admins LIMIT 1").fetchone() is not None

    def verify_admin(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str):
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, password_hash FROM admins WHERE username = ?", (username,)
            ).fetchone()
        password_hash = row["password_hash"] if row else self._dummy_password_hash
        if verify_password(password, password_hash) and row:
            return row["id"]
        return None

    def create_session(self, admin_id, ttl_seconds=43200):
        raw_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            connection.execute(
                "INSERT INTO sessions(token_hash, admin_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (hashlib.sha256(raw_token.encode()).hexdigest(), admin_id, csrf_token, now + ttl_seconds, now),
            )
        return raw_token, csrf_token

    def get_session(self, raw_token):
        if not raw_token:
            return None
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT sessions.admin_id, sessions.csrf_token, admins.username
                FROM sessions JOIN admins ON admins.id = sessions.admin_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
        return dict(row) if row else None

    def revoke_session(self, raw_token):
        if raw_token:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash = ?",
                    (hashlib.sha256(raw_token.encode()).hexdigest(),),
                )

    def create_proxy_user(
        self,
        name,
        token=None,
        device_limit=DEFAULT_DEVICE_LIMIT,
        traffic_limit_bytes=DEFAULT_TRAFFIC_LIMIT_BYTES,
    ):
        name = _validate_name(name)
        device_limit = int(device_limit)
        traffic_limit_bytes = int(traffic_limit_bytes)
        if not 1 <= device_limit <= MAX_DEVICE_LIMIT:
            raise ValueError("device limit must be between 1 and 100")
        if not 1 <= traffic_limit_bytes <= MAX_TRAFFIC_LIMIT_BYTES:
            raise ValueError("traffic limit is out of range")
        token_seed = None
        if token is None:
            token_seed = secrets.token_bytes(32)
            token = self._token_from_seed(token_seed)
        token = _validate_token(token)
        now = int(time.time())
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """INSERT INTO proxy_users(
                    name, token_fingerprint, token_seed, enabled, device_limit,
                    traffic_limit_bytes, tx_bytes, rx_bytes, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?, 0, 0, ?, ?)""",
                    (
                        name,
                        self._fingerprint(token),
                        token_seed,
                        device_limit,
                        traffic_limit_bytes,
                        now,
                        now,
                    ),
                )
                return {"id": cursor.lastrowid, "name": name, "token": token}
        except sqlite3.IntegrityError as exc:
            raise ValueError("user name or token already exists") from exc

    def authenticate_token(self, token, require_udp_443=False):
        if not isinstance(token, str) or not 1 <= len(token) <= 512:
            return None
        with self._connect() as connection:
            query = "SELECT name FROM proxy_users WHERE token_fingerprint = ? AND enabled = 1"
            if require_udp_443:
                query += " AND allow_udp_443 = 1"
            row = connection.execute(query, (self._fingerprint(token),)).fetchone()
        return row["name"] if row else None

    def _get_proxy_user(self, user_id, connection):
        row = connection.execute(
            """SELECT id, name, enabled, generation, device_limit, traffic_limit_bytes,
            allow_udp_443,
            tx_bytes, rx_bytes, created_at, updated_at
            FROM proxy_users WHERE id = ?""",
            (int(user_id),),
        ).fetchone()
        if not row:
            raise KeyError("proxy user not found")
        return row

    def get_proxy_user(self, user_id):
        with self._connect() as connection:
            return dict(self._get_proxy_user(user_id, connection))

    def get_proxy_user_by_name(self, name):
        with self._connect() as connection:
            row = connection.execute(
                """SELECT id, name, enabled, generation, device_limit, traffic_limit_bytes,
                allow_udp_443,
                tx_bytes, rx_bytes, created_at, updated_at
                FROM proxy_users WHERE name = ? COLLATE NOCASE""",
                (name,),
            ).fetchone()
        return dict(row) if row else None

    def recover_proxy_token(self, user_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT token_seed FROM proxy_users WHERE id = ?", (int(user_id),)
            ).fetchone()
        if not row:
            raise KeyError("proxy user not found")
        seed = row["token_seed"]
        return self._token_from_seed(bytes(seed)) if seed is not None else None

    def set_proxy_user_enabled(self, user_id, enabled, expected_generation=None):
        now = int(time.time())
        with self._connect() as connection:
            row = self._get_proxy_user(user_id, connection)
            generation = row["generation"] if expected_generation is None else int(expected_generation)
            if generation != row["generation"]:
                raise ConflictError("proxy user changed; refresh and try again")
            cursor = connection.execute(
                "UPDATE proxy_users SET enabled = ?, generation = generation + 1, updated_at = ? WHERE id = ? AND generation = ?",
                (1 if enabled else 0, now, row["id"], generation),
            )
            if cursor.rowcount != 1:
                raise ConflictError("proxy user changed; refresh and try again")

    def update_proxy_user_limits(
        self,
        user_id,
        device_limit,
        traffic_limit_bytes,
        allow_udp_443=None,
        expected_generation=None,
    ):
        device_limit = int(device_limit)
        traffic_limit_bytes = int(traffic_limit_bytes)
        if allow_udp_443 not in {None, True, False, 0, 1}:
            raise ValueError("UDP 443 access must be a boolean")
        if not 1 <= device_limit <= MAX_DEVICE_LIMIT:
            raise ValueError("device limit must be between 1 and 100")
        if not 1 <= traffic_limit_bytes <= MAX_TRAFFIC_LIMIT_BYTES:
            raise ValueError("traffic limit is out of range")
        now = int(time.time())
        with self._connect() as connection:
            row = self._get_proxy_user(user_id, connection)
            generation = row["generation"] if expected_generation is None else int(expected_generation)
            if generation != row["generation"]:
                raise ConflictError("proxy user changed; refresh and try again")
            udp_443_value = row["allow_udp_443"]
            if allow_udp_443 is not None:
                udp_443_value = int(bool(allow_udp_443))
            cursor = connection.execute(
                """UPDATE proxy_users
                SET device_limit = ?, traffic_limit_bytes = ?, allow_udp_443 = ?,
                    generation = generation + 1, updated_at = ?
                WHERE id = ? AND generation = ?""",
                (
                    device_limit,
                    traffic_limit_bytes,
                    udp_443_value,
                    now,
                    row["id"],
                    generation,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("proxy user changed; refresh and try again")
            return self._get_proxy_user(row["id"], connection)

    def rotate_proxy_token(self, user_id, token=None, expected_generation=None):
        token_seed = None
        if token is None:
            token_seed = secrets.token_bytes(32)
            token = self._token_from_seed(token_seed)
        token = _validate_token(token)
        now = int(time.time())
        try:
            with self._connect() as connection:
                row = self._get_proxy_user(user_id, connection)
                generation = row["generation"] if expected_generation is None else int(expected_generation)
                if generation != row["generation"]:
                    raise ConflictError("proxy user changed; refresh and try again")
                cursor = connection.execute(
                    """UPDATE proxy_users
                    SET token_fingerprint = ?, token_seed = ?, generation = generation + 1, updated_at = ?
                    WHERE id = ? AND generation = ?""",
                    (self._fingerprint(token), token_seed, now, row["id"], generation),
                )
                if cursor.rowcount != 1:
                    raise ConflictError("proxy user changed; refresh and try again")
                return {"id": row["id"], "name": row["name"], "token": token}
        except sqlite3.IntegrityError as exc:
            raise ValueError("token already exists") from exc

    def delete_proxy_user(self, user_id, expected_generation=None):
        with self._connect() as connection:
            row = self._get_proxy_user(user_id, connection)
            generation = row["generation"] if expected_generation is None else int(expected_generation)
            if generation != row["generation"]:
                raise ConflictError("proxy user changed; refresh and try again")
            cursor = connection.execute(
                "DELETE FROM proxy_users WHERE id = ? AND generation = ?",
                (row["id"], generation),
            )
            if cursor.rowcount != 1:
                raise ConflictError("proxy user changed; refresh and try again")
            return dict(row)

    def list_proxy_users(self, limit=50, offset=0):
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM proxy_users").fetchone()[0]
            rows = connection.execute(
                """
                SELECT id, name, enabled, generation, device_limit, traffic_limit_bytes,
                allow_udp_443,
                tx_bytes, rx_bytes, created_at, updated_at
                FROM proxy_users ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return {"users": [dict(row) for row in rows], "total": total}

    def list_proxy_user_names(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM proxy_users ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [row["name"] for row in rows]

    def list_proxy_users_for_usage(self):
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, name, enabled, generation, device_limit, traffic_limit_bytes,
                allow_udp_443,
                tx_bytes, rx_bytes, created_at, updated_at
                FROM proxy_users ORDER BY name COLLATE NOCASE"""
            ).fetchall()
        return [dict(row) for row in rows]

    def add_traffic(self, traffic_by_user):
        self.apply_traffic_batch(uuid.uuid4().hex, traffic_by_user)

    def apply_traffic_batch(self, batch_id, traffic_by_user):
        if not isinstance(batch_id, str) or not re.fullmatch(r"[0-9a-f]{32}", batch_id):
            raise ValueError("traffic batch id is invalid")
        if not isinstance(traffic_by_user, dict):
            raise ValueError("traffic must be a mapping")
        now = int(time.time())
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM applied_traffic_batches WHERE batch_id = ?", (batch_id,)
            ).fetchone():
                return False
            for name, traffic in traffic_by_user.items():
                if not isinstance(name, str) or not isinstance(traffic, dict):
                    raise ValueError("traffic entry is invalid")
                tx = traffic.get("tx", 0)
                rx = traffic.get("rx", 0)
                if not isinstance(tx, int) or not isinstance(rx, int) or tx < 0 or rx < 0:
                    raise ValueError("traffic counters must be non-negative integers")
                connection.execute(
                    """UPDATE proxy_users SET tx_bytes = tx_bytes + ?, rx_bytes = rx_bytes + ?,
                    updated_at = ? WHERE name = ? COLLATE NOCASE""",
                    (tx, rx, now, name),
                )
            connection.execute(
                "INSERT INTO applied_traffic_batches(batch_id, applied_at) VALUES (?, ?)",
                (batch_id, now),
            )
            connection.execute(
                "DELETE FROM applied_traffic_batches WHERE applied_at < ? AND batch_id <> ?",
                (now - max(1, int(TRAFFIC_BATCH_RETENTION_SECONDS)), batch_id),
            )
            connection.execute(
                """DELETE FROM applied_traffic_batches
                WHERE rowid <= (SELECT MAX(rowid) - ? FROM applied_traffic_batches)
                AND batch_id <> ?""",
                (max(1, int(TRAFFIC_BATCH_MAX_ROWS)), batch_id),
            )
        return True

    def reset_proxy_user_traffic(self, user_id, expected_generation=None):
        now = int(time.time())
        with self._connect() as connection:
            row = self._get_proxy_user(user_id, connection)
            generation = row["generation"] if expected_generation is None else int(expected_generation)
            if generation != row["generation"]:
                raise ConflictError("proxy user changed; refresh and try again")
            cursor = connection.execute(
                """UPDATE proxy_users SET tx_bytes = 0, rx_bytes = 0,
                generation = generation + 1, updated_at = ?
                WHERE id = ? AND generation = ?""",
                (now, row["id"], generation),
            )
            if cursor.rowcount != 1:
                raise ConflictError("proxy user changed; refresh and try again")

    def reset_all_traffic(self):
        with self._connect() as connection:
            connection.execute(
                """UPDATE proxy_users SET tx_bytes = 0, rx_bytes = 0,
                generation = generation + 1, updated_at = ?""",
                (int(time.time()),),
            )

    def audit(self, actor, action, target, remote_ip):
        now = int(time.time())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_log(created_at, actor, action, target, remote_ip) VALUES (?, ?, ?, ?, ?)",
                (now, actor, action, target, remote_ip),
            )
            connection.execute(
                "DELETE FROM audit_log WHERE created_at < ?",
                (now - AUDIT_RETENTION_SECONDS,),
            )
            connection.execute(
                """DELETE FROM audit_log
                WHERE id <= COALESCE((
                    SELECT id FROM audit_log ORDER BY id DESC LIMIT 1 OFFSET ?
                ), 0)""",
                (AUDIT_MAX_ROWS,),
            )


def handle_auth_payload(database, raw_body, usage_manager=None, require_udp_443=False):
    if len(raw_body) > 4096:
        return 413, {"error": {"code": "REQUEST_TOO_LARGE", "message": "Request too large"}}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("auth"), str):
            raise ValueError
        if len(payload["auth"]) > 512:
            raise ValueError
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return 400, {"error": {"code": "INVALID_REQUEST", "message": "Invalid request"}}
    user_id = database.authenticate_token(
        payload["auth"], require_udp_443=require_udp_443
    )
    if user_id and usage_manager is not None and not usage_manager.authorize(user_id):
        user_id = None
    return 200, {"ok": bool(user_id), "id": user_id or ""}


def build_connection_uri(host, port, auth, pin_sha256, label):
    bracketed_host = "[{}]".format(host) if ":" in host and not host.startswith("[") else host
    encoded_auth = urllib.parse.quote(auth, safe="")
    query = urllib.parse.urlencode({"insecure": "1", "pinSHA256": pin_sha256})
    return "hysteria2://{}@{}:{}/?{}#{}".format(
        encoded_auth,
        bracketed_host,
        int(port),
        query,
        urllib.parse.quote(label, safe=""),
    )


def build_qr_matrix(value):
    """Return a bounded QR module matrix without a quiet zone."""
    if not isinstance(value, str) or not value:
        raise ValueError("二维码内容不能为空")
    try:
        code = QrCode.encode_text(value, QrCode.Ecc.MEDIUM)
    except DataTooLongError as exc:
        raise ValueError("节点代码过长，无法生成二维码") from exc
    size = code.get_size()
    if size < 21 or size > 177:
        raise ValueError("二维码尺寸无效")
    return [
        "".join("1" if code.get_module(x, y) else "0" for x in range(size))
        for y in range(size)
    ]


class LoginRateLimiter:
    def __init__(
        self,
        max_attempts=5,
        window_seconds=900,
        max_addresses=4096,
        clock=time.time,
        max_concurrent_verifications=2,
        busy_retry_after=1,
    ):
        self.max_attempts = int(max_attempts)
        self.window_seconds = int(window_seconds)
        self.max_addresses = max(1, int(max_addresses))
        self.clock = clock
        self.busy_retry_after = max(1, int(busy_retry_after))
        self._attempts = {}
        self._lock = threading.Lock()
        self._authentication_locks = tuple(threading.Lock() for _ in range(64))
        self._verification_slots = threading.BoundedSemaphore(
            max(1, int(max_concurrent_verifications))
        )

    @staticmethod
    def _address_key(address):
        raw_address = str(address)
        try:
            parsed = ipaddress.ip_address(raw_address.split("%", 1)[0])
        except ValueError:
            return raw_address
        if isinstance(parsed, ipaddress.IPv6Address):
            if parsed.ipv4_mapped is not None:
                return parsed.ipv4_mapped.compressed
            return str(ipaddress.ip_network((parsed, 64), strict=False))
        return parsed.compressed

    def _recent(self, address):
        cutoff = self.clock() - self.window_seconds
        recent = [timestamp for timestamp in self._attempts.get(address, []) if timestamp > cutoff]
        if recent:
            self._attempts[address] = recent
        else:
            self._attempts.pop(address, None)
        return recent

    def is_allowed(self, address):
        address = self._address_key(address)
        with self._lock:
            return len(self._recent(address)) < self.max_attempts

    def _retry_after(self, address):
        recent = self._recent(address)
        if len(recent) < self.max_attempts:
            return 0
        remaining = recent[0] + self.window_seconds - self.clock()
        whole_seconds = int(remaining)
        return max(1, whole_seconds + (0 if remaining == whole_seconds else 1))

    def retry_after(self, address):
        address = self._address_key(address)
        with self._lock:
            return self._retry_after(address)

    def record_failure(self, address):
        address = self._address_key(address)
        with self._lock:
            recent = self._recent(address)
            if not recent and len(self._attempts) >= self.max_addresses:
                oldest = min(
                    self._attempts,
                    key=lambda item: self._attempts[item][-1] if self._attempts[item] else 0,
                )
                self._attempts.pop(oldest, None)
            recent.append(self.clock())
            self._attempts[address] = recent
            return self._retry_after(address)

    def record_success(self, address):
        address = self._address_key(address)
        with self._lock:
            self._attempts.pop(address, None)

    def authenticate(self, address, verifier):
        address = self._address_key(address)
        slot = hashlib.sha256(address.encode("utf-8")).digest()[0] % len(
            self._authentication_locks
        )
        with self._authentication_locks[slot]:
            retry_after = self.retry_after(address)
            if retry_after:
                return None, retry_after, False
            if not self._verification_slots.acquire(blocking=False):
                return None, self.busy_retry_after, False
            try:
                result = verifier()
            finally:
                self._verification_slots.release()
            if result:
                self.record_success(address)
                return result, 0, True
            return None, self.record_failure(address), True


class JsonHandler(BaseHTTPRequestHandler):
    server_version = "Hysteria2Panel"
    sys_version = ""

    def _request_id(self):
        if not hasattr(self, "request_id"):
            self.request_id = uuid.uuid4().hex
        return self.request_id

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", self._request_id())
        super().end_headers()

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, message_format, *args):
        LOGGER.info(
            json.dumps(
                {
                    "event": "http_request",
                    "requestId": self._request_id(),
                    "remoteAddress": self.client_address[0],
                    "method": getattr(self, "command", ""),
                    "path": getattr(self, "path", "").split("?", 1)[0],
                    "message": message_format % args,
                },
                separators=(",", ":"),
            )
        )


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 64

    def __init__(
        self,
        address,
        handler,
        max_workers=64,
        request_timeout=10,
        request_deadline=30,
        maintenance_request_deadline=15 * 60,
        worker_queue_timeout=0,
        request_queue_size=64,
    ):
        self.max_workers = max(1, int(max_workers))
        self.request_timeout = max(1, int(request_timeout))
        self.request_deadline = max(1, int(request_deadline))
        self.maintenance_request_deadline = max(
            self.request_deadline, int(maintenance_request_deadline)
        )
        self.worker_queue_timeout = max(0, float(worker_queue_timeout))
        self.request_queue_size = max(1, int(request_queue_size))
        self.tls_context = None
        self._worker_slots = threading.BoundedSemaphore(self.max_workers)
        self._active_requests = set()
        self._request_deadlines = {}
        self._deadline_heap = []
        self._deadline_sequence = 0
        self._deadline_shutdown = False
        self._active_requests_lock = threading.Lock()
        self._deadline_condition = threading.Condition(
            self._active_requests_lock
        )
        self._active_request_shutdown_started = False
        super().__init__(address, handler)
        self._deadline_thread = threading.Thread(
            target=self._run_deadline_scheduler,
            name="http-deadline-scheduler",
            daemon=True,
        )
        self._deadline_thread.start()

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(self.request_timeout)
        return request, client_address

    def process_request(self, request, client_address):
        if self.worker_queue_timeout:
            acquired = self._worker_slots.acquire(timeout=self.worker_queue_timeout)
        else:
            acquired = self._worker_slots.acquire(blocking=False)
        if not acquired:
            self.shutdown_request(request)
            return
        with self._active_requests_lock:
            reject_request = self._active_request_shutdown_started
            if not reject_request:
                self._active_requests.add(request)
        if reject_request:
            self._worker_slots.release()
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            with self._active_requests_lock:
                self._active_requests.discard(request)
            self._worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        tracked_request = request
        request_deadline = time.monotonic() + self.request_deadline
        self._arm_request_deadline_at(request, request_deadline)
        try:
            try:
                if self.tls_context is not None:
                    with self._deadline_condition:
                        request = self.tls_context.wrap_socket(
                            request,
                            server_side=True,
                            do_handshake_on_connect=False,
                        )
                        self._request_deadlines.pop(tracked_request, None)
                        self._active_requests.discard(tracked_request)
                        self._active_requests.add(request)
                        shutdown_started = self._active_request_shutdown_started
                        if not shutdown_started:
                            self._schedule_deadline_locked(
                                request, request_deadline
                            )
                        self._deadline_condition.notify()
                    tracked_request = request
                    if shutdown_started:
                        try:
                            request.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                        self.shutdown_request(request)
                        return
                    request.do_handshake()
            except OSError:
                self.shutdown_request(request)
            except Exception:
                try:
                    self.handle_error(request, client_address)
                finally:
                    self.shutdown_request(request)
            else:
                super().process_request_thread(request, client_address)
        finally:
            with self._deadline_condition:
                self._request_deadlines.pop(tracked_request, None)
                self._active_requests.discard(tracked_request)
                self._deadline_condition.notify()
            self._worker_slots.release()

    def _arm_request_deadline(self, request, seconds):
        deadline = time.monotonic() + max(0.0, float(seconds))
        return self._arm_request_deadline_at(request, deadline)

    def _schedule_deadline_locked(self, request, deadline):
        self._deadline_sequence += 1
        generation = self._deadline_sequence
        self._request_deadlines[request] = generation
        heapq.heappush(
            self._deadline_heap,
            (deadline, generation, request),
        )

    def _arm_request_deadline_at(self, request, deadline):
        with self._deadline_condition:
            if (
                request not in self._active_requests
                or self._deadline_shutdown
            ):
                return False
            self._schedule_deadline_locked(request, deadline)
            self._deadline_condition.notify()
        return True

    def _expire_deadline_if_current(self, request, generation):
        with self._deadline_condition:
            if self._request_deadlines.get(request) != generation:
                return False
            self._request_deadlines.pop(request, None)
        self._expire_request(request)
        return True

    def _run_deadline_scheduler(self):
        while True:
            due = None
            with self._deadline_condition:
                while not self._deadline_shutdown:
                    if not self._deadline_heap:
                        self._deadline_condition.wait()
                        continue
                    deadline, generation, request = self._deadline_heap[0]
                    if self._request_deadlines.get(request) != generation:
                        heapq.heappop(self._deadline_heap)
                        continue
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        self._deadline_condition.wait(remaining)
                        continue
                    heapq.heappop(self._deadline_heap)
                    due = (request, generation)
                    break
                if self._deadline_shutdown:
                    return
            self._expire_deadline_if_current(*due)

    def begin_maintenance_request(self, request):
        return self._arm_request_deadline(request, self.maintenance_request_deadline)

    @staticmethod
    def _expire_request(request):
        try:
            request.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def shutdown_active_requests(self):
        with self._active_requests_lock:
            self._active_request_shutdown_started = True
            requests = list(self._active_requests)
        for request in requests:
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def server_close(self):
        try:
            super().server_close()
        finally:
            with self._deadline_condition:
                self._deadline_shutdown = True
                self._deadline_condition.notify_all()
            self._deadline_thread.join(timeout=5)

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(
            error,
            (BrokenPipeError, ConnectionAbortedError, ConnectionResetError),
        ):
            return
        super().handle_error(request, client_address)


class InternalAuthHandler(JsonHandler):
    def do_POST(self):
        if self.path not in {"/auth", "/auth/udp-443"}:
            self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "Not found"}})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = -1
        if content_length < 0 or content_length > 4096:
            self.send_json(413, {"error": {"code": "REQUEST_TOO_LARGE", "message": "Request too large"}})
            return
        status, payload = handle_auth_payload(
            self.server.database,
            self.rfile.read(content_length),
            self.server.usage_manager,
            require_udp_443=self.path == "/auth/udp-443",
        )
        self.send_json(status, payload)

    def do_GET(self):
        if self.path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "Not found"}})


def make_internal_server(address, database, usage_manager=None):
    server = BoundedThreadingHTTPServer(
        address,
        InternalAuthHandler,
        worker_queue_timeout=5,
        request_queue_size=256,
    )
    server.database = database
    server.usage_manager = usage_manager
    return server


class PanelApplication:
    def __init__(
        self,
        database,
        public_host,
        hysteria_port,
        pin_sha256,
        stats_client,
        node_name="Hysteria 2",
        secure_cookies=True,
        rate_limiter=None,
        usage_manager=None,
        service_controller=None,
        egress_policy_controller=None,
        system_metrics=None,
        update_checker=None,
        update_controller=None,
        reboot_controller=None,
        backup_manager=None,
        restore_controller=None,
        health_monitor=None,
    ):
        self.database = database
        self.public_host = public_host
        self.hysteria_port = int(hysteria_port)
        self.pin_sha256 = pin_sha256
        self.stats_client = stats_client
        self.health_monitor = health_monitor or RuntimeHealth(database.readiness_probe)
        self.usage_manager = usage_manager or UsageManager(
            database,
            stats_client,
            health_monitor=self.health_monitor,
        )
        self.usage_manager.set_health_monitor(self.health_monitor)
        self.service_controller = service_controller or ServiceController()
        self.egress_policy_controller = (
            egress_policy_controller or EgressPolicyController()
        )
        self.system_metrics = system_metrics or SystemMetrics()
        self.update_checker = update_checker or UpdateChecker()
        self.update_controller = update_controller or UpdateController()
        self.reboot_controller = reboot_controller or RebootController()
        self.backup_manager = backup_manager
        self.restore_controller = restore_controller or RestoreController()
        self.update_result = None
        self.update_lock = threading.Lock()
        self.node_name = node_name
        self.secure_cookies = bool(secure_cookies)
        self.rate_limiter = rate_limiter or LoginRateLimiter()
        self.user_action_lock = threading.Lock()


def _human_bytes(value):
    value = max(0, int(value or 0))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return "{:.1f} {}".format(value, unit) if unit != "B" else "{} B".format(value)
        value /= 1024.0


def _stat_int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def summarize_dashboard(user_names, snapshot):
    traffic_by_user = snapshot.get("traffic", {})
    online_by_user = snapshot.get("online", {})
    summary = {
        "service_available": bool(snapshot.get("available")),
        "total_users": len(user_names),
        "inactive_users": 0,
        "online_devices": 0,
        "total_tx": 0,
        "total_rx": 0,
    }
    for name in user_names:
        traffic = traffic_by_user.get(name, {})
        tx = _stat_int(traffic.get("tx", 0))
        rx = _stat_int(traffic.get("rx", 0))
        summary["total_tx"] += tx
        summary["total_rx"] += rx
        summary["online_devices"] += _stat_int(online_by_user.get(name, 0))
        if tx == 0 and rx == 0:
            summary["inactive_users"] += 1
    return summary


class PanelHandler(JsonHandler):
    @property
    def cookie_name(self):
        if self.app.secure_cookies:
            return "hy2panel_session"
        return "hy2panel_http_session"

    @property
    def app(self):
        return self.server.application

    def _is_loopback_client(self):
        return is_loopback_address(self.client_address[0])

    def _send_metrics(self):
        body = self.app.health_monitor.prometheus_metrics().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _csp_nonce(self):
        if not hasattr(self, "_page_nonce"):
            self._page_nonce = secrets.token_urlsafe(18)
        return self._page_nonce

    def end_headers(self):
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{}'; connect-src 'self'; "
            "img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'".format(
                self._csp_nonce()
            ),
        )
        if self.app.secure_cookies:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()

    def _path(self):
        return urllib.parse.urlsplit(self.path).path

    def _redirect(self, location, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_html(self, status, body, headers=None):
        encoded = body.encode("utf-8")
        if len(encoded) >= 1024 and self._accepts_gzip():
            encoded = gzip.compress(encoded, compresslevel=5)
            content_encoding = "gzip"
        else:
            content_encoding = ""
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Vary", "Accept-Encoding")
        if content_encoding:
            self.send_header("Content-Encoding", content_encoding)
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _accepts_gzip(self):
        for choice in self.headers.get("Accept-Encoding", "").split(","):
            parts = [part.strip() for part in choice.split(";")]
            if not parts or parts[0].lower() != "gzip":
                continue
            quality = 1.0
            for parameter in parts[1:]:
                name, separator, value = parameter.partition("=")
                if separator and name.strip().lower() == "q":
                    try:
                        quality = float(value.strip())
                    except ValueError:
                        quality = 0.0
            return quality > 0
        return False

    def _send_favicon(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(FAVICON_SVG)))
        self.end_headers()
        self.wfile.write(FAVICON_SVG)

    def _send_archive(self, archive_path):
        archive_path = Path(archive_path)
        try:
            size = archive_path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header(
                "Content-Disposition",
                'attachment; filename="{}"'.format(archive_path.name),
            )
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with archive_path.open("rb") as source:
                shutil.copyfileobj(source, self.wfile, length=64 * 1024)
        finally:
            try:
                archive_path.unlink()
            except FileNotFoundError:
                pass

    def _read_form(self):
        content_type = self.headers.get("Content-Type", "application/x-www-form-urlencoded")
        if content_type.split(";", 1)[0].strip() != "application/x-www-form-urlencoded":
            raise ValueError("unsupported content type")
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if content_length < 0 or content_length > 16384:
            raise ValueError("invalid content length")
        parsed = urllib.parse.parse_qs(
            self.rfile.read(content_length).decode("utf-8"),
            keep_blank_values=True,
            max_num_fields=10,
        )
        return {key: values[-1] for key, values in parsed.items()}

    def _session_token(self):
        cookie = http.cookies.SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return ""
        morsel = cookie.get(self.cookie_name)
        return morsel.value if morsel else ""

    def _session(self):
        return self.app.database.get_session(self._session_token())

    def _require_session(self):
        session = self._session()
        if not session:
            self._redirect("/login")
        return session

    def _require_csrf(self, session, form):
        submitted = form.get("csrf", "")
        return bool(submitted) and hmac.compare_digest(session["csrf_token"], submitted)

    def _page(self, title, content):
        return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Hysteria 2 Panel</title><link rel="icon" type="image/svg+xml" href="/favicon.svg"><style>{style}</style></head><body><main>{content}</main>
<script nonce="{nonce}">{script}</script></body></html>""".format(
            title=html.escape(title),
            style=PAGE_STYLE,
            content=content,
            nonce=self._csp_nonce(),
            script=PAGE_SCRIPT,
        )

    def _login_page(self, error=""):
        error_html = '<p class="error" role="alert">{}</p>'.format(html.escape(error)) if error else ""
        content = """<section class="card login"><h1>Hysteria 2 Panel</h1><p class="muted">管理员登录</p>{error}
<form class="login-form" method="post" action="/login"><div><label for="username">账号</label><input id="username" name="username" autocomplete="username" required maxlength="64"></div>
<div><label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="1024"></div>
<p class="login-actions"><button type="submit">登录</button></p></form></section>""".format(error=error_html)
        return self._page("登录", content)

    def _dashboard(
        self,
        session,
        sort_by="",
        sort_order="",
        search_query="",
        status_filter="",
        online_filter="",
        udp443_filter="",
    ):
        try:
            snapshot = self.app.usage_manager.snapshot()
        except Exception:
            LOGGER.exception("stats snapshot failed")
            snapshot = {"traffic": {}, "online": {}, "available": False}
        all_users = self.app.database.list_proxy_users_for_usage()
        sort_by = sort_by if sort_by in {"traffic", "online"} else ""
        sort_order = sort_order if sort_order in {"asc", "desc"} else ""
        search_query = str(search_query)[:96]
        status_filter = status_filter if status_filter in {"enabled", "disabled"} else ""
        online_filter = online_filter if online_filter in {"active", "inactive"} else ""
        udp443_filter = udp443_filter if udp443_filter in {"allowed", "blocked"} else ""
        listed_users = sorted(
            all_users,
            key=lambda item: (item["created_at"], item["id"]),
            reverse=True,
        )
        if sort_by == "traffic" and sort_order:
            listed_users = sorted(
                all_users,
                key=lambda item: item["tx_bytes"] + item["rx_bytes"],
                reverse=sort_order == "desc",
            )
        elif sort_by == "online" and sort_order:
            listed_users = sorted(
                all_users,
                key=lambda item: _stat_int(
                    snapshot.get("online", {}).get(item["name"], 0)
                ),
                reverse=sort_order == "desc",
            )
        summary = summarize_dashboard([user["name"] for user in all_users], snapshot)
        try:
            service_status = self.app.service_controller.status()
        except Exception:
            LOGGER.exception("service status failed")
            service_status = "unknown"
        try:
            if hasattr(self.app.egress_policy_controller, "inspect"):
                egress_details = self.app.egress_policy_controller.inspect()
                egress_policy = egress_details["state"]
                configured_egress_policy = egress_details.get("configured_policy")
            else:
                egress_policy = self.app.egress_policy_controller.status()
                configured_egress_policy = egress_policy
        except Exception:
            LOGGER.exception("egress policy status failed")
            egress_policy = "unknown"
            configured_egress_policy = None
        try:
            resources = self.app.system_metrics.snapshot()
        except Exception:
            LOGGER.exception("system metrics failed")
            resources = {
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "memory_used": 0,
                "memory_total": 0,
                "disk_percent": 0.0,
                "disk_used": 0,
                "disk_total": 0,
                "uptime": "不可用",
                "tcp_congestion_control": "不可用",
                "default_qdisc": "不可用",
            }
        csrf = html.escape(session["csrf_token"], quote=True)
        rows = []
        for user in listed_users:
            name = user["name"]
            traffic = snapshot.get("traffic", {}).get(name, {})
            online = _stat_int(snapshot.get("online", {}).get(name, 0))
            device_limit = int(user["device_limit"])
            over_device_limit = online > device_limit
            used = _stat_int(traffic.get("tx", 0)) + _stat_int(traffic.get("rx", 0))
            limit = user["traffic_limit_bytes"]
            percent = min(100.0, 100.0 * used / limit) if limit else 0.0
            enabled = bool(user["enabled"])
            action_label = "禁用" if enabled else "启用"
            action_class = "danger" if enabled else "secondary"
            rows.append(
                """<tr data-user-name="{search_name}" data-enabled="{enabled_value}" data-online="{online}" data-allow-udp443="{allow_udp_443}" data-over-device-limit="{over_device_limit}"><td data-label="名称"><strong{name_class}>{name}</strong>{limit_alert}</td>
<td data-label="状态"><span class="status {state_class}">{state}</span></td><td data-label="在线设备">{online} / {device_limit}</td><td data-label="上传 / 下载">{tx} / {rx}</td>
<td class="traffic-cell" data-label="总流量"><progress max="100" value="{percent:.1f}" aria-label="{name} 总流量使用 {percent:.1f}%"></progress><div class="traffic-label"><span>{used} / {limit}</span><span>{percent:.1f}%</span></div></td>
<td data-label="操作"><div class="actions">
<form class="inline" method="post" action="/users/{id}/toggle"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="{action_class}" type="submit">{action}</button></form>
<form class="inline" method="post" action="/users/{id}/rotate" data-confirm="轮换后旧连接地址会立即失效，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="warning" type="submit">轮换密钥</button></form>
<form class="inline" method="post" action="/users/{id}/delete" data-confirm="确定删除用户 {name} 吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="danger" type="submit">删除</button></form>
<form class="inline" method="post" action="/users/{id}/share" data-share-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><input type="hidden" name="inline" value="1"><button class="secondary" type="submit">分享</button></form>
<form class="inline" method="post" action="/users/{id}/share" data-qr-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><input type="hidden" name="inline" value="1"><input type="hidden" name="qr" value="1"><button class="secondary" type="submit">二维码</button></form>
<form class="inline" method="post" action="/users/{id}/reset" data-confirm="确定重置该用户的上传和下载流量吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="ghost" type="submit">重置流量</button></form>
</div></td></tr>""".format(
                    name=html.escape(name),
                    search_name=html.escape(name, quote=True),
                    name_class=' class="over-limit-name"' if over_device_limit else "",
                    limit_alert=(
                        '<span class="limit-alert">客户端实例超限</span>'
                        if over_device_limit
                        else ""
                    ),
                    over_device_limit="1" if over_device_limit else "0",
                    enabled_value="1" if enabled else "0",
                    allow_udp_443="1" if user["allow_udp_443"] else "0",
                    state="启用" if enabled else "禁用",
                    state_class="enabled" if enabled else "disabled",
                    online=online,
                    device_limit=device_limit,
                    tx=_human_bytes(traffic.get("tx", 0)),
                    rx=_human_bytes(traffic.get("rx", 0)),
                    used=_human_bytes(used),
                    limit=_human_bytes(limit),
                    percent=percent,
                    id=user["id"],
                    generation=user["generation"],
                    csrf=csrf,
                    action=action_label,
                    action_class=action_class,
                )
            )
        if not rows:
            rows.append('<tr><td colspan="6" class="muted empty-state">暂无用户，请先创建。</td></tr>')
        edit_options = "".join(
            """<option value="{id}" data-generation="{generation}" data-device-limit="{device_limit}" data-traffic-limit-gb="{traffic_limit_gb}" data-allow-udp443="{allow_udp_443}">{name}</option>""".format(
                id=user["id"],
                generation=user["generation"],
                device_limit=user["device_limit"],
                traffic_limit_gb=max(1, user["traffic_limit_bytes"] // 1024**3),
                allow_udp_443="1" if user["allow_udp_443"] else "0",
                name=html.escape(user["name"]),
            )
            for user in listed_users
        )
        first_edit_user = listed_users[0] if listed_users else None
        sort_marks = {"asc": "↑", "desc": "↓"}
        sort_aria = {"asc": "ascending", "desc": "descending"}
        online_sort_order = sort_order if sort_by == "online" else ""
        online_sort_next = "asc" if online_sort_order == "desc" else "desc"
        online_sort_mark = sort_marks.get(online_sort_order, "⇅")
        online_sort_aria = sort_aria.get(online_sort_order, "none")
        traffic_sort_order = sort_order if sort_by == "traffic" else ""
        traffic_sort_next = "asc" if traffic_sort_order == "desc" else "desc"
        traffic_sort_mark = sort_marks.get(traffic_sort_order, "⇅")
        traffic_sort_aria = sort_aria.get(traffic_sort_order, "none")
        filter_values = {
            "search_query": html.escape(search_query, quote=True),
            "status_enabled": " selected" if status_filter == "enabled" else "",
            "status_disabled": " selected" if status_filter == "disabled" else "",
            "online_active": " selected" if online_filter == "active" else "",
            "online_inactive": " selected" if online_filter == "inactive" else "",
            "udp443_allowed": " selected" if udp443_filter == "allowed" else "",
            "udp443_blocked": " selected" if udp443_filter == "blocked" else "",
        }
        stats_state = "正常" if summary["service_available"] else "异常"
        service_running = service_status == "active"
        service_label = "Hysteria 运行中" if service_running else "Hysteria 已停止"
        service_class = "" if service_running else " off"
        full_enabled = egress_policy == "full"
        if full_enabled:
            egress_state = "FULL 已开启"
            egress_state_class = " on"
            egress_target = "web"
            egress_action = "关闭"
            egress_confirm = (
                "关闭 FULL 会切换为 WEB 端口白名单，并短暂重启全部 Hysteria 连接，确定继续吗？"
            )
        elif egress_policy == "web":
            egress_state = "FULL 已关闭"
            egress_state_class = ""
            egress_target = "full"
            egress_action = "开启"
            egress_confirm = (
                "开启 FULL 会允许代理访问公网全部端口（包括 BT/PT 和邮件端口），"
                "并短暂重启全部 Hysteria 连接，确定继续吗？"
            )
        elif egress_policy == "inconsistent":
            egress_state = "FULL 状态不一致"
            egress_state_class = " unknown"
            egress_target = (
                configured_egress_policy
                if configured_egress_policy in {"web", "full"}
                else "web"
            )
            egress_action = "修复"
            egress_confirm = (
                "当前环境、ACL 或运行状态不一致；修复会重新应用已配置策略并短暂重启运行中的 Hysteria 连接，确定继续吗？"
            )
        else:
            egress_state = "FULL 状态未知"
            egress_state_class = " unknown"
            egress_target = "web"
            egress_action = "修复"
            egress_confirm = (
                "当前无法证明出站策略；修复会应用安全的 WEB 策略并短暂重启运行中的 Hysteria 连接，确定继续吗？"
            )
        top_users = sorted(
            all_users,
            key=lambda item: item["tx_bytes"] + item["rx_bytes"],
            reverse=True,
        )[:5]
        rank_rows = "".join(
            '<div class="rank-row"><span class="rank-number">#{rank}</span><span class="rank-main"><span class="rank-name">{name}</span><span class="rank-traffic">{traffic}</span></span></div>'.format(
                rank=index,
                name=html.escape(user["name"]),
                traffic=_human_bytes(user["tx_bytes"] + user["rx_bytes"]),
            )
            for index, user in enumerate(top_users, 1)
        ) or '<p class="muted">暂无用户流量。</p>'
        update = self.app.update_result
        if update:
            update_text = (
                '发现新版本 <a href="{url}">{latest}</a>'
                if update["update_available"]
                else "当前已是最新版本"
            ).format(url=html.escape(update["url"], quote=True), latest=html.escape(update["latest"]))
        else:
            update_text = "尚未检查远程版本"
        try:
            update_status = self.app.update_controller.status()
        except Exception:
            LOGGER.exception("update status failed")
            update_status = {
                "state": "failed",
                "message": "暂时无法读取更新任务状态",
            }
        update_state = update_status.get("state", "idle")
        if update_state not in {"idle", "queued", "running", "success", "failed"}:
            update_state = "failed"
        update_status_text = html.escape(str(update_status.get("message", "")))
        update_action = ""
        if update and update["update_available"]:
            update_action = """<form method="post" action="/updates/apply" data-update-form data-confirm="在线更新会短暂重启面板与 Hysteria 服务，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="compact-button success" type="submit">立即更新</button></form>""".format(
                csrf=csrf
            )
        certificate_status = self.app.health_monitor.certificate_status()
        certificate_remaining = certificate_status["seconds_remaining"]
        if certificate_remaining is None:
            certificate_text = "未监测"
            certificate_class = "bad"
        elif certificate_status["level"] == "not-yet-valid":
            certificate_text = "尚未生效"
            certificate_class = "bad"
        elif certificate_remaining <= 0:
            certificate_text = "已过期"
            certificate_class = "bad"
        else:
            certificate_days = max(1, (certificate_remaining + 86399) // 86400)
            certificate_prefix = {
                "critical": "紧急",
                "warning": "警告",
                "notice": "注意",
            }.get(certificate_status["level"], "正常")
            certificate_text = "{} · 剩余 {} 天".format(
                certificate_prefix, certificate_days
            )
            certificate_class = (
                "bad"
                if certificate_status["level"] in {"critical", "warning", "expired"}
                else "ok"
            )
        content = """<header class="topbar"><span class="eyebrow brand">HYSTERIA CONTROL CENTER</span><h1>Hysteria 2 用户管理面板</h1><span class="topbar-spacer"></span>
<span class="pill">服务状态 <strong>{service_label}</strong></span><span class="pill">最近刷新 <strong>{refreshed}</strong></span><span class="pill">当前用户 <strong>{total_users}</strong></span>
<button class="secondary topbar-action" type="button" data-dialog-open="migration-dialog">数据迁移</button><form class="logout-form" method="post" action="/logout"><input type="hidden" name="csrf" value="{csrf}"><button class="secondary" type="submit">退出登录</button></form></header>
<section class="metrics" aria-label="服务概览">
<div class="metric"><span>不活跃用户</span><strong>{inactive_users}</strong><small class="muted">上传与下载均为 0</small></div>
<div class="metric"><span>在线设备</span><strong>{online_devices}</strong><small class="muted">按 Hysteria 客户端实例统计</small></div>
<div class="metric"><span>总上传流量</span><strong>{total_tx}</strong><small class="muted">全部用户累计上传</small></div>
<div class="metric"><span>总下载流量</span><strong>{total_rx}</strong><small class="muted">全部用户累计下载</small></div>
</section>
<section class="operations dashboard-trio">
<article class="card"><div class="section-head"><div><h2>服务控制</h2><p class="muted">启停、重启和版本检查集中在这里。</p></div><span class="service-badge{service_class}">{service_label}</span></div>
<div class="button-row"><form method="post" action="/service/start"><input type="hidden" name="csrf" value="{csrf}"><button class="success" type="submit">启动 Hysteria</button></form>
<form method="post" action="/service/restart" data-confirm="确定重启 Hysteria 服务吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="warning" type="submit">重启 Hysteria</button></form>
<form method="post" action="/service/stop" data-confirm="停止后所有连接会中断，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger" type="submit">停止 Hysteria</button></form><a class="button secondary" href="/">刷新状态</a></div>
<div class="service-details primary-details"><div class="detail compact-detail"><span class="muted">流量统计</span><strong class="{stats_class}">{stats}</strong></div><div class="detail compact-detail port-detail"><div><span class="muted">服务端口</span><strong>UDP {port}</strong></div><form class="egress-control" method="post" action="/egress/{egress_target}" data-egress-form data-confirm="{egress_confirm}"><input type="hidden" name="csrf" value="{csrf}"><span class="egress-state{egress_state_class}" data-egress-state>{egress_state}</span><button class="egress-switch{egress_state_class}" type="submit" aria-pressed="{egress_checked}" aria-label="{egress_action} FULL 出口策略"><span class="egress-switch-track" aria-hidden="true"><span></span></span><span class="egress-switch-action">{egress_action}</span></button></form></div></div>
<div class="service-details version-details"><div class="detail compact-detail bbr-detail"><span class="muted">BBR 状态</span><strong class="ok">Hysteria BBR</strong><small class="muted">standard · 内核 {tcp_cc} / {qdisc}</small></div><div class="detail compact-detail version-panel"><div class="version-row"><div><span class="muted">当前版本</span><strong>v{version}</strong></div><div class="button-row"><form method="post" action="/updates/check"><input type="hidden" name="csrf" value="{csrf}"><button class="compact-button" type="submit">检查更新</button></form>{update_action}</div></div><p class="muted">{update_text}</p><p class="update-state" data-update-status data-state="{update_state}" role="status" aria-live="polite">{update_status_text}</p></div></div></article>
<article class="card"><div class="section-head"><div><h2>系统资源</h2><p class="muted">服务器实时负载与容量。</p></div><form class="system-actions" method="post" action="/system/reboot" data-confirm="重启服务器后，所有节点连接会暂时中断，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger compact-button" type="submit">重启服务器</button></form></div><div class="resource-grid">
<div class="resource"><span class="muted">CPU 使用率</span><strong>{cpu:.1f}%</strong></div><div class="resource"><span class="muted">内存占用</span><strong>{memory:.1f}%</strong><small class="muted">{memory_used} / {memory_total}</small></div>
<div class="resource"><span class="muted">磁盘占用</span><strong>{disk:.1f}%</strong><small class="muted">{disk_used} / {disk_total}</small></div><div class="resource"><span class="muted">运行时长</span><strong>{uptime}</strong></div>
<div class="resource"><span class="muted">节点证书</span><strong class="{certificate_class}">{certificate_text}</strong><small class="muted">180 / 90 / 30 天分级提醒</small></div></div></article>
<article class="card traffic-card"><div class="section-head"><div><h2>高流量用户</h2><p class="muted">当前累计总流量最高的 5 个账号。</p></div></div><div class="rank-list">{rank_rows}</div></article>
</section>
<dialog id="migration-dialog" class="migration-dialog" aria-labelledby="migration-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="migration-title">用户数据迁移</h2><p class="muted">完整备份或恢复节点身份与全部用户数据。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭数据迁移弹窗">×</button></div>
<p class="notice"><strong>重要：</strong>备份包含代理用户、累计流量、签名密钥、证书和私钥，请离线妥善保存。恢复时必须保持节点域名 <code>{public_host}</code> 与 UDP 端口 <code>{port}</code> 不变，旧客户端配置才可继续使用；更换服务器时先通过服务器 IP 登录新面板完成恢复并验证，再切换 DNS。当前面板管理员账号不会被替换。</p>
<div class="migration-grid"><article class="detail"><h3>一键备份</h3><p class="muted">生成经过完整性校验的 ZIP 文件并直接下载。</p><form method="post" action="/backup"><input type="hidden" name="csrf" value="{csrf}"><button type="submit">下载完整备份</button></form></article>
<article class="detail"><h3>一键恢复</h3><p class="muted">上传本面板生成的 ZIP。恢复会短暂重启服务，完成后旧会话失效。</p><form data-restore-form data-csrf="{csrf}"><label for="restore-file">ZIP 备份文件</label><input id="restore-file" type="file" accept=".zip,application/zip" required><p><button class="warning" type="submit">上传并恢复</button></p><p class="muted" data-restore-status role="status"></p></form></article></div></div></dialog>
<dialog id="credentials-dialog" class="migration-dialog credentials-dialog" aria-labelledby="credentials-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="credentials-title" data-credentials-title>节点信息</h2><p class="muted">连接地址包含认证凭据，请只分享给受信任的人。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭节点信息弹窗">×</button></div>
<div class="qr-panel" data-qr-panel hidden><canvas id="credentials-qr" class="qr-canvas" role="img" aria-label="Hysteria 2 节点配置二维码"></canvas><p class="muted">可直接扫描导入，或保存 PNG 到受信任的设备。</p></div>
<label for="credentials-uri">Hysteria 2 节点代码</label><textarea id="credentials-uri" rows="5" readonly></textarea><div class="credential-actions"><button type="button" data-copy-target="credentials-uri">复制节点代码</button><button class="secondary" type="button" data-save-qr hidden>保存二维码 PNG</button></div><p class="notice" data-credentials-notice>关闭弹窗后会刷新当前用户列表。</p></div></dialog>
<dialog id="create-user-dialog" class="migration-dialog create-dialog" aria-labelledby="create-user-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="create-user-title">添加用户</h2><p class="muted">设置用户名称、设备数和总流量限制。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭添加用户弹窗">×</button></div>
<form class="create-grid" method="post" action="/users" data-create-user-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="inline" value="1"><div class="wide"><label for="name">用户名称</label><input id="name" name="name" required maxlength="64" placeholder="例如：Alice 手机" autofocus></div>
<div><label for="device_limit">限制设备数</label><input id="device_limit" name="device_limit" type="number" min="1" max="100" value="3" required></div>
<div><label for="traffic_limit_gb">总流量（GB）</label><input id="traffic_limit_gb" name="traffic_limit_gb" type="number" min="1" max="1048576" value="250" required></div><button type="submit">添加用户</button></form></div></dialog>
<dialog id="edit-user-dialog" class="migration-dialog create-dialog" aria-labelledby="edit-user-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="edit-user-title">编辑用户</h2><p class="muted">修改限制或开放 UDP 443，不会改变已发放节点链接。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭编辑用户弹窗">×</button></div>
<form class="create-grid" method="post" action="/users/{first_edit_id}/edit" data-edit-user-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="inline" value="1"><input type="hidden" name="generation" value="{first_edit_generation}"><div class="wide"><label for="edit-user-select">选择用户</label><select id="edit-user-select" data-edit-user-select required>{edit_options}</select></div>
<div><label for="edit-device-limit">限制设备数</label><input id="edit-device-limit" name="device_limit" type="number" min="1" max="100" value="{first_edit_device_limit}" required></div>
<div><label for="edit-traffic-limit-gb">总流量（GB）</label><input id="edit-traffic-limit-gb" name="traffic_limit_gb" type="number" min="1" max="1048576" value="{first_edit_traffic_limit_gb}" required></div>
<label class="checkbox-field wide" for="edit-allow-udp-443"><input id="edit-allow-udp-443" name="allow_udp_443" type="checkbox" value="1"{first_edit_udp_443_checked}{udp_443_disabled}><span>允许该账号使用 UDP 443<small class="muted">开启后，客户端把服务器端口从 {port} 改为 443 即可；原 {port} 仍可继续使用。</small></span></label><button type="submit"{edit_disabled}>保存修改</button></form>
<p class="notice">设备数按在线 Hysteria 客户端实例估算；标准通用节点链接不包含硬件设备指纹。</p></div></dialog>
<p class="toast" data-page-status role="status" aria-live="polite" hidden></p>
<section class="card"><div class="section-head user-section-head"><div class="user-heading"><h2>用户管理</h2><p class="muted">创建用户并设置并发设备和总流量限制。</p></div>
<div class="section-actions"><button type="button" data-dialog-open="create-user-dialog">添加用户</button><button class="secondary" type="button" data-dialog-open="edit-user-dialog"{edit_disabled}>编辑用户</button><form method="post" action="/users/reset-traffic" data-confirm="确定重置所有用户的上传和下载流量吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger" type="submit">重置全部流量</button></form></div></div>
<div class="user-tools"><form class="user-filters" data-user-filters><div class="user-search"><label for="user-search">用户名</label><input id="user-search" name="q" type="search" value="{search_query}" placeholder="输入用户名搜索" autocomplete="off" maxlength="96" data-user-search></div>
<div><label for="user-status-filter">状态</label><select id="user-status-filter" name="status" data-status-filter><option value="">全部</option><option value="enabled"{status_enabled}>启用</option><option value="disabled"{status_disabled}>禁用</option></select></div>
<div><label for="user-online-filter">在线</label><select id="user-online-filter" name="online" data-online-filter><option value="">全部</option><option value="active"{online_active}>在线</option><option value="inactive"{online_inactive}>离线</option></select></div>
<div><label for="user-udp443-filter">UDP 443</label><select id="user-udp443-filter" name="udp443" data-udp443-filter><option value="">全部</option><option value="allowed"{udp443_allowed}>已开放</option><option value="blocked"{udp443_blocked}>未开放</option></select></div>
<button class="ghost" type="button" data-clear-user-filters>清除</button></form><p class="muted search-status" data-search-status role="status" aria-live="polite">共 {user_total} 个用户</p></div>
<p class="muted filter-empty" data-filter-empty hidden>没有符合当前条件的用户。</p>
<div class="table-wrap user-table"><table><thead><tr><th>名称</th><th>状态</th><th aria-sort="{online_sort_aria}"><a class="sort-link" href="/?sort=online&amp;order={online_sort_next}">在线设备 {online_sort_mark}</a></th><th>上传 / 下载</th><th aria-sort="{traffic_sort_aria}"><a class="sort-link" href="/?sort=traffic&amp;order={traffic_sort_next}">总流量 {traffic_sort_mark}</a></th><th>操作</th></tr></thead><tbody>{rows}</tbody></table></div></section>""".format(
            port=self.app.hysteria_port,
            public_host=html.escape(self.app.public_host),
            stats=stats_state,
            stats_class="ok" if summary["service_available"] else "bad",
            service_label=service_label,
            service_class=service_class,
            refreshed=time.strftime("%H:%M:%S"),
            total_users=summary["total_users"],
            inactive_users=summary["inactive_users"],
            online_devices=summary["online_devices"],
            total_tx=_human_bytes(summary["total_tx"]),
            total_rx=_human_bytes(summary["total_rx"]),
            csrf=csrf,
            version=PANEL_VERSION,
            update_text=update_text,
            update_action=update_action,
            update_state=update_state,
            update_status_text=update_status_text,
            egress_target=egress_target,
            egress_confirm=html.escape(egress_confirm, quote=True),
            egress_state=egress_state,
            egress_state_class=egress_state_class,
            egress_checked="true" if full_enabled else "false",
            egress_action=egress_action,
            cpu=resources["cpu_percent"],
            memory=resources["memory_percent"],
            memory_used=_human_bytes(resources["memory_used"]),
            memory_total=_human_bytes(resources["memory_total"]),
            disk=resources["disk_percent"],
            disk_used=_human_bytes(resources["disk_used"]),
            disk_total=_human_bytes(resources["disk_total"]),
            uptime=html.escape(resources["uptime"]),
            certificate_class=certificate_class,
            certificate_text=certificate_text,
            tcp_cc=html.escape(resources["tcp_congestion_control"]),
            qdisc=html.escape(resources["default_qdisc"]),
            rank_rows=rank_rows,
            rows="".join(rows),
            edit_options=(
                edit_options
                if edit_options
                else '<option value="">暂无可编辑用户</option>'
            ),
            first_edit_id=first_edit_user["id"] if first_edit_user else 0,
            first_edit_generation=(
                first_edit_user["generation"] if first_edit_user else 0
            ),
            first_edit_device_limit=(
                first_edit_user["device_limit"] if first_edit_user else DEFAULT_DEVICE_LIMIT
            ),
            first_edit_traffic_limit_gb=(
                max(1, first_edit_user["traffic_limit_bytes"] // 1024**3)
                if first_edit_user
                else DEFAULT_TRAFFIC_LIMIT_BYTES // 1024**3
            ),
            first_edit_udp_443_checked=(
                " checked"
                if first_edit_user and first_edit_user["allow_udp_443"]
                else ""
            ),
            udp_443_disabled="" if self.app.hysteria_port != 443 else " disabled",
            edit_disabled="" if first_edit_user else " disabled",
            user_total=len(listed_users),
            online_sort_aria=online_sort_aria,
            online_sort_next=online_sort_next,
            online_sort_mark=online_sort_mark,
            traffic_sort_aria=traffic_sort_aria,
            traffic_sort_next=traffic_sort_next,
            traffic_sort_mark=traffic_sort_mark,
            **filter_values,
        )
        return self._page("控制台", content)

    def _connection_payload(self, credentials):
        return {
            "name": credentials["name"],
            "uri": build_connection_uri(
                self.app.public_host,
                self.app.hysteria_port,
                credentials["token"],
                self.app.pin_sha256,
                self.app.node_name,
            ),
        }

    def _credentials_page(self, session, credentials):
        uri = self._connection_payload(credentials)["uri"]
        content = """<header class="topbar"><h1>连接分享</h1><span class="topbar-spacer"></span><a class="button secondary" href="/">返回控制台</a></header>
<section class="card"><h2>{name}</h2><p class="muted">连接地址包含认证凭据，请只分享给受信任的人。</p>
<div class="copy-grid"><div><label for="token">认证密钥</label><textarea id="token" rows="2" readonly>{token}</textarea></div><button class="secondary" type="button" data-copy-target="token">复制密钥</button></div>
<div class="copy-grid"><div><label for="uri">Hysteria 2 连接地址</label><textarea id="uri" rows="4" readonly>{uri}</textarea></div><button type="button" data-copy-target="uri">一键复制分享</button></div>
<p class="notice" role="status">客户端会使用自签名证书，并同时固定证书 SHA-256 指纹。</p></section>""".format(
            name=html.escape(credentials["name"]),
            token=html.escape(credentials["token"]),
            uri=html.escape(uri),
        )
        return self._page("连接信息", content)

    def _error_page(self, status, message):
        content = '<section class="card"><h1>操作失败</h1><p class="error">{}</p><p><a class="button secondary" href="/">返回</a></p></section>'.format(
            html.escape(message)
        )
        self._send_html(status, self._page("操作失败", content))

    def do_GET(self):
        path = self._path()
        if path == "/favicon.svg":
            self._send_favicon()
            return
        if path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        if path == "/readyz":
            ready, _checks = self.app.health_monitor.readiness()
            self.send_json(
                200 if ready else 503,
                {"status": "ready" if ready else "not-ready"},
            )
            return
        if path == "/metrics":
            if not self._is_loopback_client():
                self.send_json(404, {"error": "not found"})
                return
            self._send_metrics()
            return
        if path == "/login":
            if self._session():
                self._redirect("/")
            else:
                self._send_html(200, self._login_page())
            return
        if path == "/updates/status":
            session = self._require_session()
            if not session:
                return
            self.send_json(200, self.app.update_controller.status())
            return
        if path == "/":
            session = self._require_session()
            if not session:
                return
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            self._send_html(
                200,
                self._dashboard(
                    session,
                    query.get("sort", [""])[0],
                    query.get("order", [""])[0],
                    query.get("q", [""])[0],
                    query.get("status", [""])[0],
                    query.get("online", [""])[0],
                    query.get("udp443", [""])[0],
                ),
            )
            return
        self._error_page(404, "页面不存在")

    def do_POST(self):
        path = self._path()
        if path == "/restore":
            self._handle_restore_upload()
            return
        try:
            form = self._read_form()
        except (UnicodeDecodeError, ValueError):
            self._error_page(400, "请求格式无效")
            return
        if path == "/login":
            self._handle_login(form)
            return
        session = self._require_session()
        if not session:
            return
        if not self._require_csrf(session, form):
            self._error_page(403, "安全校验失败，请刷新页面后重试")
            return
        if path == "/logout":
            self.app.database.revoke_session(self._session_token())
            secure = "; Secure" if self.app.secure_cookies else ""
            self._redirect(
                "/login",
                "{}=; Path=/; Max-Age=0{}; HttpOnly; SameSite=Strict".format(
                    self.cookie_name, secure
                ),
            )
            return
        if path == "/users":
            self._handle_create_user(session, form)
            return
        if path == "/users/reset-traffic":
            self._handle_reset_all_traffic(session)
            return
        if path == "/system/reboot":
            self._handle_reboot(session)
            return
        if path == "/backup":
            self._handle_backup(session)
            return
        service_match = re.fullmatch(r"/service/(start|stop|restart)", path)
        if service_match:
            self._handle_service_action(session, service_match.group(1))
            return
        egress_match = re.fullmatch(r"/egress/(web|full)", path)
        if egress_match:
            self._handle_egress_policy(session, egress_match.group(1))
            return
        if path == "/updates/check":
            self._handle_update_check(session)
            return
        if path == "/updates/apply":
            self._handle_update_apply(session)
            return
        edit_match = re.fullmatch(r"/users/(\d+)/edit", path)
        if edit_match:
            self._handle_edit_user(session, int(edit_match.group(1)), form)
            return
        match = re.fullmatch(r"/users/(\d+)/(toggle|rotate|delete|share|reset)", path)
        if match:
            self._handle_user_action(session, int(match.group(1)), match.group(2), form)
            return
        self._error_page(404, "页面不存在")

    def _handle_backup(self, session):
        if self.app.backup_manager is None:
            self._error_page(503, "备份功能尚未配置")
            return
        self.server.begin_maintenance_request(self.connection)
        try:
            with self.app.user_action_lock:
                archive = self.app.usage_manager.run_after_collect(
                    self.app.backup_manager.create_archive
                )
            self._send_archive(archive)
            self._audit_safely(session["username"], "backup_downloaded", "proxy-users")
        except Exception:
            LOGGER.exception("backup creation failed")
            self._error_page(500, "备份生成失败，请检查服务日志")

    def _handle_restore_upload(self):
        session = self._require_session()
        if not session:
            return
        submitted = self.headers.get("X-HY2Panel-CSRF", "")
        if not submitted or not hmac.compare_digest(session["csrf_token"], submitted):
            self._error_page(403, "安全校验失败，请刷新页面后重试")
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/zip":
            self._error_page(400, "仅支持本面板生成的 ZIP 备份文件")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = -1
        if self.app.backup_manager is None:
            self._error_page(503, "恢复功能尚未配置")
            return
        self.server.begin_maintenance_request(self.connection)
        staged = False
        try:
            with self.app.user_action_lock:
                manifest = self.app.backup_manager.stage_archive(
                    self.rfile, content_length
                )
                staged = True
                self.app.restore_controller.queue()
                self._audit_safely(
                    session["username"], "restore_queued", manifest["createdAt"]
                )
        except BackupValidationError as exc:
            self._error_page(400, str(exc))
            return
        except Exception:
            if staged:
                try:
                    self.app.backup_manager.pending_archive.unlink()
                except FileNotFoundError:
                    pass
            LOGGER.exception("restore queue failed")
            self._error_page(500, "恢复任务启动失败，请检查服务日志")
            return
        content = """<section class="card login"><h1>恢复任务已启动</h1>
<p>面板与 Hysteria 服务将短暂重启。恢复完成后，当前登录会话会失效，请等待约 10 秒后重新登录。</p>
<p class="notice">原节点域名、UDP 端口、签名密钥与证书已通过预检；恢复服务仍会再次独立校验后才替换数据。</p>
<p><a class="button secondary" href="/login">稍后重新登录</a></p></section>"""
        self._send_html(202, self._page("正在恢复", content))

    def _handle_login(self, form):
        address = self.client_address[0]
        admin_id, retry_after, attempted = self.app.rate_limiter.authenticate(
            address,
            lambda: self.app.database.verify_admin(
                form.get("username", ""), form.get("password", "")
            ),
        )
        if not attempted:
            self._send_html(
                429,
                self._login_page("尝试次数过多，请 {} 秒后再试".format(retry_after)),
                {"Retry-After": str(retry_after)},
            )
            return
        if not admin_id:
            self._audit_safely("anonymous", "login_failed", "admin")
            if retry_after:
                self._audit_safely("anonymous", "login_locked", "admin")
                self._send_html(
                    429,
                    self._login_page("尝试次数过多，请 {} 秒后再试".format(retry_after)),
                    {"Retry-After": str(retry_after)},
                )
                return
            self._send_html(401, self._login_page("账号或密码错误"))
            return
        raw_token, _ = self.app.database.create_session(admin_id)
        self._audit_safely(form.get("username", "admin")[:64], "login_succeeded", "admin")
        secure = "; Secure" if self.app.secure_cookies else ""
        cookie = "{}={}; Path=/; Max-Age=43200{}; HttpOnly; SameSite=Strict".format(
            self.cookie_name, raw_token, secure
        )
        self._redirect("/", cookie)

    def _handle_create_user(self, session, form):
        inline = form.get("inline") == "1"
        try:
            device_limit = int(form.get("device_limit", DEFAULT_DEVICE_LIMIT))
            traffic_limit_gb = int(form.get("traffic_limit_gb", 250))
            with self.app.user_action_lock:
                credentials = self.app.database.create_proxy_user(
                    form.get("name", ""),
                    device_limit=device_limit,
                    traffic_limit_bytes=traffic_limit_gb * 1024**3,
                )
        except (TypeError, ValueError) as exc:
            if inline:
                self.send_json(400, {"error": str(exc)})
                return
            self._error_page(400, str(exc))
            return
        self._audit_safely(session["username"], "proxy_user_created", credentials["name"])
        if inline:
            self.send_json(201, self._connection_payload(credentials))
            return
        self._send_html(201, self._credentials_page(session, credentials))

    def _handle_edit_user(self, session, user_id, form):
        inline = form.get("inline") == "1" or "application/json" in self.headers.get(
            "Accept", ""
        )
        try:
            generation = int(form.get("generation", ""))
            device_limit = int(form.get("device_limit", ""))
            traffic_limit_gb = int(form.get("traffic_limit_gb", ""))
            allow_udp_443 = form.get("allow_udp_443") == "1"
            with self.app.user_action_lock:
                user = self.app.database.update_proxy_user_limits(
                    user_id,
                    device_limit=device_limit,
                    traffic_limit_bytes=traffic_limit_gb * 1024**3,
                    allow_udp_443=allow_udp_443,
                    expected_generation=generation,
                )
        except (TypeError, ValueError) as exc:
            if inline:
                self.send_json(400, {"error": str(exc)})
                return
            self._error_page(400, "设备数或流量额度无效")
            return
        except ConflictError:
            if inline:
                self.send_json(409, {"error": "用户状态已变化，请刷新页面后重试"})
                return
            self._error_page(409, "用户状态已变化，请刷新页面后重试")
            return
        except KeyError:
            if inline:
                self.send_json(404, {"error": "用户不存在"})
                return
            self._error_page(404, "用户不存在")
            return
        self._audit_safely(session["username"], "proxy_user_limits_updated", user["name"])
        payload = {
            "id": user["id"],
            "name": user["name"],
            "device_limit": user["device_limit"],
            "traffic_limit_gb": user["traffic_limit_bytes"] // 1024**3,
            "allow_udp_443": bool(user["allow_udp_443"]),
            "generation": user["generation"],
        }
        if inline:
            self.send_json(200, payload)
            return
        self._redirect("/")

    def _audit_safely(self, actor, action, target):
        try:
            self.app.database.audit(actor, action, target, self.client_address[0])
        except Exception:
            LOGGER.exception("audit write failed")

    def _kick_safely(self, name):
        try:
            self.app.stats_client.kick(name)
        except Exception:
            self.app.usage_manager._record_health(False)
            LOGGER.exception("disconnecting active user failed")

    def _handle_user_action(self, session, user_id, action, form):
        try:
            generation = int(form.get("generation", ""))
            with self.app.user_action_lock:
                if action == "toggle":
                    user = self.app.database.get_proxy_user(user_id)
                    enabled = not bool(user["enabled"])
                    self.app.database.set_proxy_user_enabled(
                        user_id, enabled, expected_generation=generation
                    )
                    if not enabled:
                        self._kick_safely(user["name"])
                    audit_action = "proxy_user_enabled" if enabled else "proxy_user_disabled"
                    self._audit_safely(session["username"], audit_action, user["name"])
                    self._redirect("/")
                    return
                if action == "rotate":
                    credentials = self.app.database.rotate_proxy_token(
                        user_id, expected_generation=generation
                    )
                    self._kick_safely(credentials["name"])
                    self._audit_safely(
                        session["username"], "proxy_token_rotated", credentials["name"]
                    )
                    self._send_html(200, self._credentials_page(session, credentials))
                    return
                if action == "share":
                    user = self.app.database.get_proxy_user(user_id)
                    if user["generation"] != generation:
                        raise ConflictError
                    token = self.app.database.recover_proxy_token(user_id)
                    if token is None:
                        if form.get("inline") == "1":
                            self.send_json(
                                409,
                                {"error": "该用户来自旧版本，请先轮换密钥后再分享"},
                            )
                            return
                        self._error_page(
                            409,
                            "该用户来自旧版本，原密钥不可逆保存；请先点击轮换密钥，再使用分享功能",
                        )
                        return
                    self._audit_safely(session["username"], "proxy_link_shared", user["name"])
                    credentials = {"id": user["id"], "name": user["name"], "token": token}
                    if form.get("inline") == "1":
                        payload = self._connection_payload(credentials)
                        if form.get("qr") == "1":
                            payload["qr"] = build_qr_matrix(payload["uri"])
                        self.send_json(200, payload)
                        return
                    self._send_html(
                        200,
                        self._credentials_page(session, credentials),
                    )
                    return
                if action == "reset":
                    user = self.app.database.get_proxy_user(user_id)
                    self.app.usage_manager.reset_user(
                        user_id, expected_generation=generation
                    )
                    self._audit_safely(
                        session["username"], "proxy_traffic_reset", user["name"]
                    )
                    self._redirect("/")
                    return
                user = self.app.database.delete_proxy_user(
                    user_id, expected_generation=generation
                )
                self.app.usage_manager.forget_user(user["name"])
                self._kick_safely(user["name"])
                self._audit_safely(session["username"], "proxy_user_deleted", user["name"])
            self._redirect("/")
        except (TypeError, ValueError):
            if form.get("inline") == "1":
                self.send_json(400, {"error": "请求无效，请刷新页面后重试"})
            else:
                self._error_page(400, "请求版本无效，请刷新页面后重试")
        except ConflictError:
            if form.get("inline") == "1":
                self.send_json(409, {"error": "用户状态已变化，请刷新页面后重试"})
            else:
                self._error_page(409, "用户状态已变化，请刷新页面后重试")
        except KeyError:
            if form.get("inline") == "1":
                self.send_json(404, {"error": "用户不存在"})
            else:
                self._error_page(404, "用户不存在")
        except Exception:
            LOGGER.exception("user action failed")
            self._error_page(500, "操作未完成，请检查服务日志")

    def _handle_reset_all_traffic(self, session):
        try:
            with self.app.user_action_lock:
                self.app.usage_manager.reset_all()
            self._audit_safely(session["username"], "all_proxy_traffic_reset", "all")
            self._redirect("/")
        except Exception:
            LOGGER.exception("resetting all traffic failed")
            self._error_page(500, "流量重置失败，请检查服务日志")

    def _handle_service_action(self, session, action):
        try:
            if action in {"stop", "restart"}:
                state = self.app.usage_manager.run_after_collect(
                    lambda: self.app.service_controller.action(action)
                )
            else:
                state = self.app.service_controller.action(action)
            self._audit_safely(
                session["username"], "hysteria_service_{}".format(action), state
            )
            self._redirect("/")
        except (RuntimeError, ValueError):
            LOGGER.exception("service action failed")
            self._error_page(500, "服务控制失败，请检查服务日志")

    def _handle_egress_policy(self, session, policy):
        try:
            state = self.app.usage_manager.run_after_collect(
                lambda: self.app.egress_policy_controller.switch(policy)
            )
            self._audit_safely(
                session["username"], "egress_policy_changed", state
            )
            self._redirect("/")
        except ValueError:
            self._error_page(400, "出站策略无效")
        except EgressPolicyStateError:
            LOGGER.exception("egress policy state is inconsistent")
            self._error_page(500, "出站策略切换未完成，当前状态不一致；请重启服务器触发安全恢复")
        except RuntimeError:
            LOGGER.exception("egress policy switch failed")
            self._error_page(500, "出站策略切换失败；未执行切换或旧策略已恢复，请刷新状态并检查服务日志")

    def _handle_reboot(self, session):
        try:
            def queue_reboot():
                self._audit_safely(
                    session["username"], "server_reboot_queued", "system"
                )
                return self.app.reboot_controller.queue()

            self.app.usage_manager.run_after_collect(queue_reboot)
        except RuntimeError:
            LOGGER.exception("server reboot queue failed")
            self._error_page(500, "服务器重启任务启动失败，请检查服务日志")
            return
        content = """<section class="card login"><h1>服务器正在重启</h1>
<p>面板和所有节点连接会暂时中断，systemd 会在服务器启动后自动恢复服务。</p>
<p class="notice">通常等待 30 到 90 秒后即可重新打开面板；服务器提供商的启动时间可能更长。</p>
<p><a class="button secondary" href="/">稍后重试</a></p></section>"""
        self._send_html(202, self._page("正在重启服务器", content))

    def _handle_update_check(self, session):
        try:
            with self.app.update_lock:
                self.app.update_result = self.app.update_checker.check()
                self._audit_safely(
                    session["username"], "panel_update_checked", PANEL_VERSION
                )
            self._redirect("/")
        except Exception:
            LOGGER.exception("update check failed")
            self._error_page(502, "暂时无法检查更新，请稍后重试")

    def _handle_update_apply(self, session):
        with self.app.update_lock:
            update_result = self.app.update_result
            if not update_result or not update_result.get("update_available"):
                if "application/json" in self.headers.get("Accept", ""):
                    self.send_json(409, {"error": "请先检查更新并确认存在新版本"})
                else:
                    self._error_page(409, "请先检查更新并确认存在新版本")
                return
            try:
                target = update_result["latest"]
                self.app.update_controller.queue(target)
                self._audit_safely(
                    session["username"], "panel_update_queued", target
                )
            except Exception:
                LOGGER.exception("update queue failed")
                if "application/json" in self.headers.get("Accept", ""):
                    self.send_json(500, {"error": "在线更新任务启动失败，请检查服务日志"})
                else:
                    self._error_page(500, "在线更新任务启动失败，请检查服务日志")
                return
        if "application/json" in self.headers.get("Accept", ""):
            self.send_json(202, self.app.update_controller.status())
            return
        content = """<section class="card login"><h1>在线更新任务已启动</h1>
<p>系统会重新核验最新正式版本，建立升级前备份并保留用户、节点参数、签名密钥、证书和管理员账号。</p>
<p class="notice">面板与 Hysteria 服务会短暂重启。请等待约 30 秒后刷新；失败原因与升级前备份位置会保留在更新服务日志中。</p>
<p><a class="button secondary" href="/">稍后刷新</a></p></section>"""
        self._send_html(202, self._page("正在更新", content))


def make_panel_server(address, application):
    server = BoundedThreadingHTTPServer(address, PanelHandler)
    server.application = application
    return server


class HysteriaStatsClient:
    def __init__(self, base_url, secret, timeout=2):
        self.base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Hysteria stats API URL is invalid") from exc
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Hysteria stats API must use plaintext loopback HTTP")
        self.secret = secret
        self.timeout = timeout

    def _request(self, path, data=None):
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={"Authorization": self.secret, "Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        # The constructor restricts the URL to loopback HTTP.
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310
            if response.status != 200:
                raise RuntimeError("Hysteria stats API returned {}".format(response.status))
            raw_body = response.read(MAX_STATS_RESPONSE_BYTES + 1)
        if len(raw_body) > MAX_STATS_RESPONSE_BYTES:
            raise ValueError("Hysteria stats API response is too large")
        if not raw_body and data is not None:
            return {}
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Hysteria stats API returned invalid JSON")
        return payload

    def snapshot(self):
        traffic = self._request("/traffic")
        online = self.online()
        self._validate_traffic(traffic)
        return {"traffic": traffic, "online": online, "available": True}

    @staticmethod
    def _validate_traffic(traffic):
        if not isinstance(traffic, dict) or not all(
            isinstance(name, str)
            and isinstance(stats, dict)
            and isinstance(stats.get("tx", 0), int)
            and isinstance(stats.get("rx", 0), int)
            and stats.get("tx", 0) >= 0
            and stats.get("rx", 0) >= 0
            for name, stats in traffic.items()
        ):
            raise ValueError("Hysteria traffic response is invalid")

    def collect_and_clear(self):
        traffic = self._request("/traffic?clear=1")
        self._validate_traffic(traffic)
        return traffic

    def online(self):
        online = self._request("/online")
        if not isinstance(online, dict) or not all(
            isinstance(name, str) and isinstance(count, int) and count >= 0
            for name, count in online.items()
        ):
            raise ValueError("Hysteria online response is invalid")
        return online

    def kick(self, name):
        self.kick_many([name])

    def kick_many(self, names):
        names = list(names)
        if names:
            self._request("/kick", names)


class PartialTrafficCollectionError(RuntimeError):
    def __init__(self, traffic):
        super().__init__("one or more Hysteria traffic endpoints are unavailable")
        self.traffic = traffic


class CombinedHysteriaStatsClient:
    def __init__(self, *clients):
        if len(clients) < 2:
            raise ValueError("combined stats require at least two clients")
        self.clients = clients

    @staticmethod
    def _merge_traffic(values):
        merged = {}
        for traffic in values:
            for name, stats in traffic.items():
                current = merged.setdefault(name, {"tx": 0, "rx": 0})
                current["tx"] += stats.get("tx", 0)
                current["rx"] += stats.get("rx", 0)
        return merged

    def collect_and_clear(self):
        collected = []
        failure = None
        for client in self.clients:
            try:
                collected.append(client.collect_and_clear())
            except Exception as exc:
                if failure is None:
                    failure = exc
        traffic = self._merge_traffic(collected)
        if failure is not None:
            raise PartialTrafficCollectionError(traffic) from failure
        return traffic

    def online(self):
        merged = {}
        for client in self.clients:
            for name, count in client.online().items():
                merged[name] = merged.get(name, 0) + count
        return merged

    def kick(self, name):
        self.kick_many([name])

    def kick_many(self, names):
        names = list(names)
        if not names:
            return
        failure = None
        for client in self.clients:
            try:
                client.kick_many(names)
            except Exception as exc:
                if failure is None:
                    failure = exc
        if failure is not None:
            raise failure


class UsageManager:
    def __init__(
        self,
        database,
        stats_client,
        pending_ttl=5,
        clock=time.monotonic,
        health_monitor=None,
        auth_stats_ttl=1,
    ):
        self.database = database
        self.stats_client = stats_client
        self.pending_ttl = max(1, int(pending_ttl))
        self.clock = clock
        self.lock = threading.Lock()
        self._authorization_lock = threading.Lock()
        self.auth_stats_ttl = max(0, float(auth_stats_ttl))
        self._auth_stats_at = None
        self._auth_online = {}
        self.pending = {}
        self.pending_traffic_path = database.path.with_name("pending-traffic.json")
        self.pending_traffic_batch_id = None
        self.pending_traffic = {}
        self._load_pending_traffic()
        self.last_online = {}
        self.health_monitor = health_monitor

    def set_health_monitor(self, health_monitor):
        self.health_monitor = health_monitor

    def _record_health(self, success):
        if self.health_monitor is None:
            return
        self.health_monitor.refresh_database()
        self.health_monitor.record_stats_sync(success)

    def _load_pending_traffic(self):
        try:
            raw = self.pending_traffic_path.read_bytes()
        except FileNotFoundError:
            return
        if len(raw) > MAX_PENDING_TRAFFIC_BYTES:
            raise ValueError("pending traffic journal is too large")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("pending traffic journal is invalid")
        batch_id = payload.get("batch_id")
        traffic = payload.get("traffic")
        if not isinstance(batch_id, str) or not re.fullmatch(r"[0-9a-f]{32}", batch_id):
            raise ValueError("pending traffic batch id is invalid")
        HysteriaStatsClient._validate_traffic(traffic)
        self.pending_traffic_batch_id = batch_id
        self.pending_traffic = traffic

    def _persist_pending_traffic_locked(self, traffic):
        if not traffic:
            return
        batch_id = uuid.uuid4().hex
        self.pending_traffic_batch_id = batch_id
        self.pending_traffic = traffic
        descriptor = None
        temporary = None
        try:
            payload = json.dumps(
                {"batch_id": batch_id, "traffic": traffic},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            if len(payload) > MAX_PENDING_TRAFFIC_BYTES:
                raise ValueError("pending traffic journal is too large")
            self.pending_traffic_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".pending-traffic.", dir=str(self.pending_traffic_path.parent)
            )
            metadata = self.database.path.stat()
            handle = os.fdopen(descriptor, "wb")
            descriptor = None
            with handle:
                os.fchmod(handle.fileno(), 0o600)
                if hasattr(os, "geteuid") and os.geteuid() == 0:
                    os.fchown(handle.fileno(), metadata.st_uid, metadata.st_gid)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.pending_traffic_path)
            temporary = None
            self._fsync_pending_directory()
        except Exception as journal_error:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    LOGGER.exception("pending traffic journal descriptor cleanup failed")
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError:
                    LOGGER.exception("pending traffic journal temporary cleanup failed")
            database_error = None
            for _attempt in range(3):
                try:
                    self.database.apply_traffic_batch(batch_id, traffic)
                    database_error = None
                    break
                except Exception as exc:
                    database_error = exc
            if database_error is not None:
                raise journal_error from database_error
            try:
                self._remove_pending_traffic_locked()
            except Exception:
                LOGGER.exception(
                    "pending traffic journal cleanup failed after database fallback"
                )
            self.pending_traffic_batch_id = None
            self.pending_traffic = {}

    def _remove_pending_traffic_locked(self):
        try:
            self.pending_traffic_path.unlink()
        except FileNotFoundError:
            return
        self._fsync_pending_directory()

    def _fsync_pending_directory(self):
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        descriptor = os.open(self.pending_traffic_path.parent, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _flush_pending_traffic_locked(self):
        if not self.pending_traffic:
            return
        self.database.apply_traffic_batch(
            self.pending_traffic_batch_id, self.pending_traffic
        )
        self._remove_pending_traffic_locked()
        self.pending_traffic_batch_id = None
        self.pending_traffic = {}

    def _collect_locked(self):
        self._auth_stats_at = None
        try:
            self._flush_pending_traffic_locked()
            try:
                traffic = self.stats_client.collect_and_clear()
            except PartialTrafficCollectionError as exc:
                self._persist_pending_traffic_locked(exc.traffic)
                self._flush_pending_traffic_locked()
                raise
            self._persist_pending_traffic_locked(traffic)
            self._flush_pending_traffic_locked()
        except Exception:
            self._record_health(False)
            raise
        self._record_health(True)
        return traffic

    def _blocked_online_names_locked(self):
        users = {
            user["name"]: user for user in self.database.list_proxy_users_for_usage()
        }
        online = self.stats_client.online()
        blocked = []
        for name, count in online.items():
            user = users.get(name)
            if count > 0 and (
                not user
                or not user["enabled"]
                or user["tx_bytes"] + user["rx_bytes"] >= user["traffic_limit_bytes"]
            ):
                blocked.append(name)
        return sorted(blocked)

    def collect_once(self):
        with self.lock:
            traffic = self._collect_locked()
            try:
                blocked = self._blocked_online_names_locked()
            except Exception:
                self._record_health(False)
                LOGGER.exception("online reconciliation failed during traffic sync")
                return traffic
            try:
                self.stats_client.kick_many(blocked)
            except Exception:
                self._record_health(False)
                raise
            return traffic

    def run_after_collect(self, action):
        with self.lock:
            self._collect_locked()
            return action()

    def forget_user(self, name):
        with self._authorization_lock:
            self.pending.pop(name, None)
            self.last_online.pop(name, None)

    def _authorization_online_locked(self):
        now = self.clock()
        if (
            self._auth_stats_at is not None
            and now - self._auth_stats_at < self.auth_stats_ttl
        ):
            return dict(self._auth_online)
        try:
            self._collect_locked()
        except Exception:
            LOGGER.exception("traffic sync failed during authentication")
            return None
        try:
            online = self.stats_client.online()
        except Exception:
            self._record_health(False)
            LOGGER.exception("online snapshot failed during authentication")
            return None
        self._auth_online = dict(online)
        self._auth_stats_at = self.clock()
        return dict(self._auth_online)

    def authorize(self, name):
        with self.lock:
            online = self._authorization_online_locked()
        if online is None:
            return False
        user = self.database.get_proxy_user_by_name(name)
        if not user or not user["enabled"]:
            return False
        if user["tx_bytes"] + user["rx_bytes"] >= user["traffic_limit_bytes"]:
            return False
        with self._authorization_lock:
            now = self.clock()
            pending = [
                timestamp
                for timestamp in self.pending.get(name, [])
                if now - timestamp < self.pending_ttl
            ]
            online_count = online.get(name, 0)
            previous_online = self.last_online.get(name, online_count)
            if online_count > previous_online:
                pending = pending[min(len(pending), online_count - previous_online) :]
            self.last_online[name] = online_count
            if online_count + len(pending) >= user["device_limit"]:
                self.pending[name] = pending
                return False
            pending.append(now)
            self.pending[name] = pending
            return True

    def snapshot(self):
        with self.lock:
            available = True
            try:
                self._collect_locked()
            except Exception:
                LOGGER.exception("traffic sync failed during dashboard snapshot")
                available = False
            try:
                online = self.stats_client.online()
            except Exception:
                LOGGER.exception("online snapshot failed during dashboard snapshot")
                online = {}
                available = False
            users = self.database.list_proxy_users_for_usage()
        return {
            "traffic": {
                user["name"]: {"tx": user["tx_bytes"], "rx": user["rx_bytes"]}
                for user in users
            },
            "online": online,
            "available": available,
        }

    def reset_user(self, user_id, expected_generation=None):
        with self.lock:
            self._collect_locked()
            user = self.database.get_proxy_user(user_id)
            self.database.reset_proxy_user_traffic(user_id, expected_generation)
            try:
                self.stats_client.kick(user["name"])
            except Exception:
                self._record_health(False)
                raise
            with self._authorization_lock:
                self.pending.pop(user["name"], None)

    def reset_all(self):
        with self.lock:
            self._collect_locked()
            self.database.reset_all_traffic()

    def run_collector(self, stop_event, interval=10):
        while not stop_event.is_set():
            heartbeat = getattr(self, "collector_heartbeat", None)
            if heartbeat is not None:
                heartbeat()
            try:
                self.collect_once()
            except Exception:
                LOGGER.exception("background traffic sync failed")
            if heartbeat is not None:
                heartbeat()
            if stop_event.wait(interval):
                break








def _parse_port(mapping, name, default):
    try:
        value = int(mapping.get(name, default))
    except (TypeError, ValueError) as exc:
        raise ValueError("{} must be a port number".format(name)) from exc
    if not 1 <= value <= 65535:
        raise ValueError("{} must be between 1 and 65535".format(name))
    return value


class Settings:
    def __init__(self, **values):
        self.__dict__.update(values)

    @classmethod
    def from_mapping(cls, mapping):
        try:
            hmac_key = bytes.fromhex(mapping.get("HY2PANEL_HMAC_KEY", ""))
        except ValueError as exc:
            raise ValueError("HY2PANEL_HMAC_KEY must be hexadecimal") from exc
        if len(hmac_key) < 32:
            raise ValueError("HY2PANEL_HMAC_KEY must decode to at least 32 bytes")
        public_host = mapping.get("HY2PANEL_PUBLIC_HOST", "").strip()
        node_name = mapping.get("HY2PANEL_NODE_NAME", "Hysteria 2").strip()
        panel_scheme = mapping.get("HY2PANEL_PANEL_SCHEME", "http").strip().lower()
        stats_secret = mapping.get("HY2PANEL_STATS_SECRET", "")
        cert_pin = mapping.get("HY2PANEL_CERT_PIN", "").strip()
        if not public_host:
            raise ValueError("HY2PANEL_PUBLIC_HOST is required")
        if not node_name or len(node_name) > 64 or any(ord(character) < 32 for character in node_name):
            raise ValueError("HY2PANEL_NODE_NAME must contain 1 to 64 printable characters")
        if panel_scheme not in {"http", "https"}:
            raise ValueError("HY2PANEL_PANEL_SCHEME must be http or https")
        if len(stats_secret) < 8:
            raise ValueError("HY2PANEL_STATS_SECRET must contain at least 8 characters")
        if not cert_pin:
            raise ValueError("HY2PANEL_CERT_PIN is required")
        auth_host = mapping.get("HY2PANEL_AUTH_HOST", "127.0.0.1").strip()
        if auth_host != "127.0.0.1":
            raise ValueError("HY2PANEL_AUTH_HOST must be 127.0.0.1")
        hysteria_port = _parse_port(mapping, "HY2PANEL_HYSTERIA_PORT", 19999)
        panel_port = _parse_port(mapping, "HY2PANEL_PANEL_PORT", 19998)
        auth_port = _parse_port(mapping, "HY2PANEL_AUTH_PORT", 19996)
        stats_port = _parse_port(mapping, "HY2PANEL_STATS_PORT", 19997)
        stats_443_port = _parse_port(mapping, "HY2PANEL_STATS_443_PORT", 19995)
        ports = {hysteria_port, panel_port, auth_port, stats_port, stats_443_port}
        if len(ports) != 5 or (
            hysteria_port != 443
            and 443 in {panel_port, auth_port, stats_port, stats_443_port}
        ):
            raise ValueError(
                "Hysteria, panel, auth, both stats and the secondary 443 ports must be different"
            )
        return cls(
            database_path=Path(mapping.get("HY2PANEL_DB", "/var/lib/hysteria2-panel/panel.db")),
            hmac_key=hmac_key,
            public_host=public_host,
            node_name=node_name,
            hysteria_port=hysteria_port,
            # Remote panel access is an explicit deployment feature.
            panel_host=mapping.get("HY2PANEL_PANEL_HOST", "0.0.0.0"),  # nosec B104
            panel_port=panel_port,
            panel_scheme=panel_scheme,
            auth_host=auth_host,
            auth_port=auth_port,
            stats_port=stats_port,
            stats_url="http://127.0.0.1:{}".format(stats_port),
            stats_443_url="http://127.0.0.1:{}".format(stats_443_port),
            stats_secret=stats_secret,
            tls_cert=Path(mapping.get("HY2PANEL_TLS_CERT", "/etc/hysteria2-panel/server.crt")),
            tls_key=Path(mapping.get("HY2PANEL_TLS_KEY", "/etc/hysteria2-panel/server.key")),
            cert_pin=cert_pin,
        )


def initialize_admin(settings, username, password, if_missing=False):
    database = Database(settings.database_path, settings.hmac_key)
    database.initialize()
    if if_missing and database.has_admin():
        return False
    database.upsert_admin(username, password)
    return True


def make_stats_client(settings, primary_only=False, secondary_only=False):
    if primary_only and secondary_only:
        raise ValueError("traffic maintenance endpoint selection is ambiguous")
    if secondary_only:
        if settings.hysteria_port == 443:
            raise ValueError("the secondary Hysteria stats endpoint is not enabled")
        return HysteriaStatsClient(settings.stats_443_url, settings.stats_secret)
    stats_client = HysteriaStatsClient(settings.stats_url, settings.stats_secret)
    if settings.hysteria_port != 443 and not primary_only:
        stats_client = CombinedHysteriaStatsClient(
            stats_client,
            HysteriaStatsClient(settings.stats_443_url, settings.stats_secret),
        )
    return stats_client


def quiesce_stats_client(
    stats_client,
    attempts=30,
    interval=0.1,
    stable_empty_snapshots=3,
    sleeper=time.sleep,
):
    attempts = max(1, int(attempts))
    interval = max(0, float(interval))
    stable_empty_snapshots = max(2, int(stable_empty_snapshots))
    empty_snapshots = 0
    for _attempt in range(attempts):
        online = {
            name: count
            for name, count in stats_client.online().items()
            if count > 0
        }
        if online:
            empty_snapshots = 0
            stats_client.kick_many(sorted(online))
        else:
            empty_snapshots += 1
            if empty_snapshots >= stable_empty_snapshots:
                return
        sleeper(interval)
    # Hysteria's /kick marks an ID for its next traffic event; an idle session
    # can therefore remain in /online until the server is stopped.


@contextlib.contextmanager
def defer_termination_signals():
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    deferred = []
    previous = {}

    def remember(signum, _frame):
        if not deferred:
            deferred.append(signum)

    handled = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
    failure = None
    for signum in handled:
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, remember)
    try:
        try:
            yield
        except BaseException as exc:
            failure = exc
    finally:
        for signum in handled:
            signal.signal(signum, previous[signum])
    if deferred:
        if failure is not None:
            raise SystemExit(128 + deferred[0]) from failure
        raise SystemExit(128 + deferred[0])
    if failure is not None:
        raise failure


@contextlib.contextmanager
def exclusive_maintenance_lock(
    path=MAINTENANCE_LOCK_PATH,
    blocking=False,
    expected_uid=None,
    expected_gid=None,
    expected_mode=None,
):
    path = Path(path)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or (expected_uid is not None and metadata.st_uid != expected_uid)
            or (expected_gid is not None and metadata.st_gid != expected_gid)
            or (
                expected_mode is not None
                and stat.S_IMODE(metadata.st_mode) != expected_mode
            )
        ):
            raise RuntimeError("维护锁不是普通文件")
        try:
            operation = fcntl.LOCK_EX
            if not blocking:
                operation |= fcntl.LOCK_NB
            fcntl.flock(descriptor, operation)
        except BlockingIOError as exc:
            raise RuntimeError("已有维护任务正在运行") from exc
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def maintenance_upload_slot(
    path=MAINTENANCE_LOCK_PATH,
    expected_uid=0,
    expected_gid=None,
    expected_mode=0o640,
):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(Path(path)), flags)
    except OSError as exc:
        raise RuntimeError("维护任务状态不可用") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or (expected_uid is not None and metadata.st_uid != expected_uid)
            or (expected_gid is not None and metadata.st_gid != expected_gid)
            or stat.S_IMODE(metadata.st_mode) != expected_mode
        ):
            raise RuntimeError("维护锁不安全")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("已有维护任务正在运行") from exc
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def sync_traffic(
    settings,
    primary_only=False,
    secondary_only=False,
    quiesce=False,
):
    database = Database(settings.database_path, settings.hmac_key)
    database.initialize()
    stats_client = make_stats_client(
        settings,
        primary_only=primary_only,
        secondary_only=secondary_only,
    )
    if quiesce:
        quiesce_stats_client(stats_client)
    UsageManager(database, stats_client).collect_once()


def _probe_local_health(server, scheme, timeout=2):
    bound_host = str(server.server_address[0])
    try:
        bound_address = ipaddress.ip_address(bound_host)
    except ValueError:
        return False
    if bound_address.is_unspecified:
        host = "::1" if bound_address.version == 6 else "127.0.0.1"
    else:
        host = bound_host
    port = int(server.server_address[1])
    connection = None
    try:
        if scheme == "https":
            context = ssl._create_unverified_context()  # nosec B323
            connection = http.client.HTTPSConnection(
                host, port, timeout=timeout, context=context
            )
        else:
            connection = http.client.HTTPConnection(host, port, timeout=timeout)
        connection.request("GET", "/healthz", headers={"Connection": "close"})
        response = connection.getresponse()
        payload = response.read(1025)
        return (
            response.status == 200
            and len(payload) <= 1024
            and json.loads(payload.decode("utf-8")) == {"status": "ok"}
        )
    except (OSError, ValueError, http.client.HTTPException, json.JSONDecodeError):
        return False
    finally:
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass


def run_supervised_services(
    panel_server,
    auth_server,
    usage_manager,
    panel_scheme,
    notifier=None,
    watchdog_probe=None,
):
    stop_event = threading.Event()
    failures = queue.Queue()
    previous_termination_handler = None
    termination_requested = [False]
    application = getattr(panel_server, "application", None)
    health_monitor = getattr(application, "health_monitor", None)
    notifier = notifier or SystemdNotifier()
    watchdog_interval = notifier.watchdog_interval
    next_watchdog = None
    collector_heartbeat = [None]
    watchdog_unhealthy_reported = [False]
    previous_collector_heartbeat = getattr(
        usage_manager, "collector_heartbeat", None
    )
    had_collector_heartbeat = hasattr(usage_manager, "collector_heartbeat")

    def record_collector_heartbeat():
        collector_heartbeat[0] = time.monotonic()

    def watchdog_is_healthy():
        heartbeat = collector_heartbeat[0]
        if heartbeat is None:
            return False
        stale_after = max(5.0, 2 * watchdog_interval)
        if time.monotonic() - heartbeat >= stale_after:
            return False
        if watchdog_probe is not None:
            try:
                return bool(watchdog_probe())
            except Exception:
                return False
        return _probe_local_health(panel_server, panel_scheme) and _probe_local_health(
            auth_server, "http"
        )

    def request_graceful_shutdown(_signum, _frame):
        termination_requested[0] = True

    def worker(name, target):
        if health_monitor is not None:
            health_monitor.mark_worker(name, True)
        try:
            target()
        except BaseException as exc:
            failures.put((name, exc))
        else:
            failures.put((name, None))
        finally:
            if health_monitor is not None:
                health_monitor.mark_worker(name, False)

    workers = [
        threading.Thread(
            target=worker,
            args=("panel-{}".format(panel_scheme), panel_server.serve_forever),
            name="panel-{}".format(panel_scheme),
            daemon=True,
        ),
        threading.Thread(
            target=worker,
            args=("internal-auth", auth_server.serve_forever),
            name="internal-auth",
            daemon=True,
        ),
        threading.Thread(
            target=worker,
            args=("traffic-collector", lambda: usage_manager.run_collector(stop_event)),
            name="traffic-collector",
            daemon=True,
        ),
    ]
    started_workers = []
    started_servers = []
    if threading.current_thread() is threading.main_thread():
        previous_termination_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, request_graceful_shutdown)
    try:
        if watchdog_interval is not None:
            usage_manager.collector_heartbeat = record_collector_heartbeat
        for thread in workers:
            thread.start()
            started_workers.append(thread)
            if thread.name in {"panel-{}".format(panel_scheme), "internal-auth"}:
                started_servers.append(
                    panel_server if thread.name.startswith("panel-") else auth_server
                )
        notifier.ready("panel workers started")
        if watchdog_interval is not None:
            next_watchdog = time.monotonic() + watchdog_interval
        while not termination_requested[0]:
            if next_watchdog is not None and time.monotonic() >= next_watchdog:
                if watchdog_is_healthy():
                    notifier.watchdog()
                    watchdog_unhealthy_reported[0] = False
                elif not watchdog_unhealthy_reported[0]:
                    LOGGER.error(
                        "systemd watchdog withheld: a local worker is not responsive"
                    )
                    watchdog_unhealthy_reported[0] = True
                next_watchdog = time.monotonic() + watchdog_interval
            try:
                failed_worker, error = failures.get(timeout=0.2)
                break
            except queue.Empty:
                continue
        else:
            failed_worker, error = "termination", None
        if failed_worker == "termination":
            return
        message = "{} worker exited unexpectedly".format(failed_worker)
        if error is None:
            raise RuntimeError(message)
        raise RuntimeError(message) from error
    finally:
        primary_error = sys.exc_info()[1]
        cleanup_error = None
        notifier.stopping("panel stopping")
        try:
            try:
                stop_event.set()
                for server in started_servers:
                    try:
                        server.shutdown()
                        if hasattr(server, "shutdown_active_requests"):
                            server.shutdown_active_requests()
                    except Exception:
                        LOGGER.exception("local service shutdown failed")
                for thread in started_workers:
                    thread.join(timeout=30)
                for server in (panel_server, auth_server):
                    try:
                        server.server_close()
                    except Exception:
                        LOGGER.exception("local service close failed")
                alive = [thread.name for thread in started_workers if thread.is_alive()]
                if alive:
                    cleanup_error = RuntimeError(
                        "service workers did not stop: {}".format(", ".join(alive))
                    )
            except BaseException as exc:
                cleanup_error = exc
            if started_workers:
                try:
                    usage_manager.collect_once()
                except BaseException as exc:
                    if primary_error is None and cleanup_error is None:
                        cleanup_error = exc
                    else:
                        LOGGER.exception("final traffic sync failed during service shutdown")
            if primary_error is None and cleanup_error is not None:
                raise cleanup_error
        finally:
            if watchdog_interval is not None:
                if had_collector_heartbeat:
                    usage_manager.collector_heartbeat = previous_collector_heartbeat
                else:
                    try:
                        del usage_manager.collector_heartbeat
                    except AttributeError:
                        pass
            if previous_termination_handler is not None:
                signal.signal(signal.SIGTERM, previous_termination_handler)


def run_service(settings):
    database = Database(settings.database_path, settings.hmac_key)
    database.initialize()
    if not database.has_admin():
        raise RuntimeError("no administrator exists; run init-admin first")
    stats_client = make_stats_client(settings)
    usage_manager = UsageManager(database, stats_client)
    backup_manager = BackupManager(
        database=database,
        hmac_key=settings.hmac_key,
        tls_cert=settings.tls_cert,
        tls_key=settings.tls_key,
        public_host=settings.public_host,
        hysteria_port=settings.hysteria_port,
        node_name=settings.node_name,
        work_dir=settings.database_path.parent / "backup-restore",
        maintenance_lock_group=os.getgid() if hasattr(os, "getgid") else None,
    )
    health_monitor = RuntimeHealth(
        database.readiness_probe,
        certificate_validity_probe=functools.partial(
            certificate_validity_timestamps, settings.tls_cert
        ),
    )
    application = PanelApplication(
        database=database,
        public_host=settings.public_host,
        hysteria_port=settings.hysteria_port,
        pin_sha256=settings.cert_pin,
        stats_client=stats_client,
        node_name=settings.node_name,
        secure_cookies=settings.panel_scheme == "https",
        usage_manager=usage_manager,
        backup_manager=backup_manager,
        health_monitor=health_monitor,
    )
    panel_server = make_panel_server((settings.panel_host, settings.panel_port), application)
    if settings.panel_scheme == "https":
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if hasattr(ssl, "TLSVersion"):
            tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        tls_context.load_cert_chain(str(settings.tls_cert), str(settings.tls_key))
        panel_server.tls_context = tls_context
    auth_server = make_internal_server(
        (settings.auth_host, settings.auth_port), database, usage_manager
    )
    LOGGER.info(
        json.dumps(
            {
                "event": "service_started",
                "panelAddress": "{}:{}".format(settings.panel_host, settings.panel_port),
                "authAddress": "{}:{}".format(settings.auth_host, settings.auth_port),
            },
            separators=(",", ":"),
        )
    )
    run_supervised_services(
        panel_server,
        auth_server,
        usage_manager,
        panel_scheme=settings.panel_scheme,
    )


def _systemctl_result(runner, arguments, timeout=60):
    return runner(
        ["/bin/systemctl"] + list(arguments),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _systemd_unit_state(unit, runner=subprocess.run):
    result = _systemctl_result(
        runner,
        ["show", "--no-pager", "--property=LoadState", "--property=ActiveState", unit],
    )
    if result.returncode != 0:
        raise RuntimeError("systemd service state could not be inspected")
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in {"LoadState", "ActiveState"} or key in values:
            raise RuntimeError("systemd service state is invalid")
        values[key] = value
    if set(values) != {"LoadState", "ActiveState"}:
        raise RuntimeError("systemd service state is incomplete")
    return values["LoadState"], values["ActiveState"]


def stop_restore_services(runner=subprocess.run):
    for unit in RESTORE_STOP_UNITS:
        load_state, active_state = _systemd_unit_state(unit, runner=runner)
        if load_state not in {"loaded", "not-found"}:
            raise RuntimeError("restore service ownership is invalid")
        if active_state == "inactive":
            continue
        result = _systemctl_result(runner, ["stop", unit])
        if result.returncode != 0:
            raise RuntimeError("restore could not stop project services")
    for unit in RESTORE_STOP_UNITS:
        _load_state, active_state = _systemd_unit_state(unit, runner=runner)
        if active_state != "inactive":
            raise RuntimeError("restore project services did not stop")


def _default_restore_health_probe(url, settings):
    allowed_urls = {
        "{}://127.0.0.1:{}/readyz".format(
            settings.panel_scheme, settings.panel_port
        ),
        "http://127.0.0.1:{}/healthz".format(settings.auth_port),
    }
    if url not in allowed_urls:
        raise RuntimeError("restore health probe URL is not a fixed loopback endpoint")
    context = None
    if url.startswith("https://"):
        # The exact loopback URL above uses the panel's restored self-signed cert.
        context = ssl._create_unverified_context()  # nosec B323
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=2, context=context) as response:  # nosec B310
        expected_status = "ready" if url.endswith("/readyz") else "ok"
        if response.status != 200 or json.load(response) != {"status": expected_status}:
            raise RuntimeError("restored HTTP health endpoint is unavailable")


def _default_restore_stats_probe(url, secret):
    HysteriaStatsClient(url, secret).online()


def _default_restore_tcp_probe(port):
    with socket.create_connection(("127.0.0.1", int(port)), timeout=2):
        return


def _restore_expected_units(settings, runner):
    required_units = {
        "hysteria2-panel.service",
        "hysteria2-panel-server.service",
        "hysteria2-panel-tcp-probe.service",
    }
    if settings.hysteria_port != 443:
        required_units.update(
            {
                "hysteria2-panel-server-443.service",
                "hysteria2-panel-tcp-probe-443.service",
            }
        )
    expected = []
    for unit in RESTORE_STOP_UNITS:
        load_state, active_state = _systemd_unit_state(unit, runner=runner)
        if (
            load_state == "not-found"
            and active_state == "inactive"
            and unit not in required_units
        ):
            continue
        if load_state != "loaded" or active_state != "active":
            raise RuntimeError("restored project services are not active")
        expected.append(unit)
    return expected


def _probe_restored_services(
    settings,
    expected_units,
    health_probe,
    stats_probe,
    tcp_probe,
):
    panel_url = "{}://127.0.0.1:{}/readyz".format(
        settings.panel_scheme, settings.panel_port
    )
    auth_url = "http://127.0.0.1:{}/healthz".format(settings.auth_port)
    health_probe(panel_url, settings)
    health_probe(auth_url, settings)
    stats_probe(settings.stats_url, settings.stats_secret)
    tcp_probe(settings.hysteria_port)
    if "hysteria2-panel-server-443.service" in expected_units:
        stats_probe(settings.stats_443_url, settings.stats_secret)
    if "hysteria2-panel-tcp-probe-443.service" in expected_units:
        tcp_probe(443)


def start_restore_services(
    settings,
    runner=subprocess.run,
    health_probe=_default_restore_health_probe,
    stats_probe=_default_restore_stats_probe,
    tcp_probe=_default_restore_tcp_probe,
    attempts=30,
    interval=0.2,
    sleeper=time.sleep,
):
    result = _systemctl_result(
        runner,
        ["start", "hysteria2-panel.service", "hysteria2-panel-server.service"],
    )
    if result.returncode != 0:
        raise RuntimeError("restored project services could not be started")
    attempt_limit = max(2, int(attempts))
    failure = None
    consecutive_successes = 0
    for attempt in range(attempt_limit):
        try:
            expected_units = _restore_expected_units(settings, runner)
            _probe_restored_services(
                settings,
                expected_units,
                health_probe,
                stats_probe,
                tcp_probe,
            )
            consecutive_successes += 1
            if consecutive_successes >= 2:
                return
        except Exception as exc:
            failure = exc
            consecutive_successes = 0
        if attempt + 1 < attempt_limit:
            sleeper(max(0, float(interval)))
    if failure is not None:
        raise RuntimeError("restored project services are not healthy") from failure


def stop_panel_for_restore(runner=subprocess.run, attempts=120, sleeper=time.sleep):
    result = _systemctl_result(
        runner,
        ["kill", "--kill-who=main", "--signal=SIGTERM", "hysteria2-panel.service"],
    )
    if result.returncode != 0:
        raise RuntimeError("restore could not stop panel writes")
    for attempt in range(max(1, int(attempts))):
        _load_state, active_state = _systemd_unit_state(
            "hysteria2-panel.service", runner=runner
        )
        if active_state == "inactive":
            return
        if attempt + 1 < max(1, int(attempts)):
            sleeper(0.1)
    raise RuntimeError("restore panel writes did not stop")


def make_restore_stats_client(settings, runner=subprocess.run):
    primary_load, primary_state = _systemd_unit_state(
        "hysteria2-panel-server.service", runner=runner
    )
    secondary_load, secondary_state = _systemd_unit_state(
        "hysteria2-panel-server-443.service", runner=runner
    )
    allowed_load_states = {"loaded", "not-found"}
    allowed_active_states = {"active", "inactive", "failed"}
    for load_state, active_state in (
        (primary_load, primary_state),
        (secondary_load, secondary_state),
    ):
        if (
            load_state not in allowed_load_states
            or active_state not in allowed_active_states
            or (load_state == "not-found" and active_state != "inactive")
        ):
            raise RuntimeError("restore Hysteria service state is invalid")
    if primary_load != "loaded":
        raise RuntimeError("restore primary Hysteria service is missing")
    if settings.hysteria_port != 443 and secondary_load != "loaded":
        raise RuntimeError("restore secondary Hysteria service is missing")
    if primary_state == "active" and secondary_state == "active":
        return make_stats_client(settings)
    if primary_state == "active":
        return make_stats_client(settings, primary_only=True)
    if secondary_state == "active":
        return make_stats_client(settings, secondary_only=True)
    raise RuntimeError("restore has no active Hysteria stats endpoint")


def settle_restore_traffic(settings, runner=subprocess.run, quiesce=quiesce_stats_client):
    stop_panel_for_restore(runner=runner)
    stats_client = make_restore_stats_client(settings, runner=runner)
    quiesce(stats_client)
    database = Database(settings.database_path, settings.hmac_key)
    database.initialize()
    manager = UsageManager(database, stats_client)
    manager.collect_once()
    if manager.pending_traffic_path.exists():
        raise RuntimeError("restore traffic journal is not empty")
    with sqlite3.connect(str(settings.database_path), timeout=5) as connection:
        busy, _checkpointed, _remaining = connection.execute(
            "PRAGMA wal_checkpoint(TRUNCATE)"
        ).fetchone()
    if busy:
        raise RuntimeError("restore database checkpoint is busy")


def _remove_restore_marker(path):
    _durable_unlink(path)


def _read_restore_transaction(
    path, expected_uid=0, strict_paths=True, maximum=64 * 1024
):
    path = Path(path)
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or (expected_uid is not None and metadata.st_uid != expected_uid)
        or (expected_uid == 0 and metadata.st_gid != 0)
        or metadata.st_size <= 0
        or metadata.st_size > maximum
        or metadata.st_nlink != 1
    ):
        raise RuntimeError("restore marker is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise RuntimeError("restore marker changed while being read")
        raw = os.read(descriptor, maximum + 1)
    finally:
        os.close(descriptor)
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("restore marker JSON is invalid") from exc
    required = {
        "version", "phase", "pendingArchive", "pendingSha256", "pendingSize",
        "databasePath", "tlsCert", "tlsKey", "envFile", "workDir",
        "backupRoot", "publicHost", "hysteriaPort", "nodeName",
        "queuedArchive",
    }
    if (
        not isinstance(record, dict)
        or not required.issubset(record)
        or record["version"] != RESTORE_TRANSACTION_VERSION
        or record["phase"]
        not in {"queued", "prepared", "disk-consistent", "services-pending"}
        or not re.fullmatch(r"[0-9a-f]{64}", record["pendingSha256"] or "")
        or not isinstance(record["pendingSize"], int)
        or record["pendingSize"] <= 0
        or not isinstance(record["hysteriaPort"], int)
    ):
        raise RuntimeError("restore marker fields are invalid")
    if strict_paths:
        expected = {
            "pendingArchive": str(RESTORE_WORK_DIR / "pending-restore.zip"),
            "databasePath": "/var/lib/hysteria2-panel/panel.db",
            "tlsCert": "/etc/hysteria2-panel/server.crt",
            "tlsKey": "/etc/hysteria2-panel/server.key",
            "envFile": str(RESTORE_ENV_FILE),
            "workDir": str(RESTORE_WORK_DIR),
            "backupRoot": str(RESTORE_BACKUP_ROOT),
            "queuedArchive": str(RESTORE_ACTIVE_MARKER) + ".archive",
        }
        if any(record.get(key) != value for key, value in expected.items()):
            raise RuntimeError("restore marker path is invalid")
    if record["phase"] == "prepared" or (
        record["phase"] in {"disk-consistent", "services-pending"}
        and (record.get("outcome") == "applied" or "backupDir" in record)
    ):
        backup_root = Path(record["backupRoot"])
        backup_dir = Path(record.get("backupDir", ""))
        incoming = Path(record.get("incomingArchive", ""))
        try:
            direct_child = backup_dir.parent == backup_root
            incoming_child = incoming.parent == backup_dir
        except (TypeError, ValueError):
            direct_child = incoming_child = False
        if (
            not direct_child
            or not incoming_child
            or not re.fullmatch(r"restore-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}", backup_dir.name)
            or incoming.name != "incoming.zip"
            or not isinstance(record.get("oldFiles"), dict)
            or set(record["oldFiles"]) != {"panel.db", "server.crt", "server.key", "panel.env"}
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", value or "")
                for value in record["oldFiles"].values()
            )
        ):
            raise RuntimeError("restore marker backup path is invalid")
    return record


def _restore_manager_from_record(record):
    return BackupManager(
        database=Database(Path(record["databasePath"]), b"\0" * 32),
        hmac_key=b"\0" * 32,
        tls_cert=Path(record["tlsCert"]),
        tls_key=Path(record["tlsKey"]),
        public_host=record["publicHost"],
        hysteria_port=record["hysteriaPort"],
        node_name=record["nodeName"],
        work_dir=Path(record["workDir"]),
    )


def _restore_env_identity(env_file, root_uid=0):
    raw = _read_secure_regular(
        env_file, 1024 * 1024, allowed_uids={root_uid}, required_mode=0o640
    )
    values = {}
    for line in raw.decode("utf-8").splitlines():
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
        if match:
            if match.group(1) in values:
                raise RuntimeError("restore environment has duplicate values")
            values[match.group(1)] = match.group(2)
    try:
        key = bytes.fromhex(values["HY2PANEL_HMAC_KEY"])
        pin = values["HY2PANEL_CERT_PIN"]
    except (KeyError, ValueError) as exc:
        raise RuntimeError("restore environment identity is invalid") from exc
    if len(key) < 32 or not pin:
        raise RuntimeError("restore environment identity is invalid")
    return raw, key, pin


def _validate_current_restore_identity(record, root_uid=0):
    manager = _restore_manager_from_record(record)
    env_bytes, hmac_key, pin = _restore_env_identity(record["envFile"], root_uid)
    database_path = Path(record["databasePath"])
    database_uid = os.lstat(database_path.parent).st_uid
    database_details = _secure_regular_details(
        database_path,
        manager.FILE_LIMITS["data/panel.db"],
        allowed_uids={database_uid},
        required_mode=0o600,
    )
    cert = _read_secure_regular(
        record["tlsCert"],
        manager.FILE_LIMITS["tls/server.crt"],
        allowed_uids={root_uid},
        required_mode=0o640,
    )
    key = _read_secure_regular(
        record["tlsKey"],
        manager.FILE_LIMITS["tls/server.key"],
        allowed_uids={root_uid},
        required_mode=0o640,
    )
    with tempfile.TemporaryDirectory(dir=record["workDir"]) as temporary:
        manager._validate_database_path(database_path, hmac_key)
        cert_path = Path(temporary) / "server.crt"
        key_path = Path(temporary) / "server.key"
        cert_path.write_bytes(cert)
        key_path.write_bytes(key)
        manager._certificate_details(cert_path, key_path)
    if not hmac.compare_digest(manager._certificate_pin(cert), pin):
        raise RuntimeError("restore certificate pin is inconsistent")
    return {
        "panel.db": database_details["sha256"],
        "server.crt": manager._sha256(cert),
        "server.key": manager._sha256(key),
        "panel.env": manager._sha256(env_bytes),
    }


def _validate_applied_transaction(record):
    manager = _restore_manager_from_record(record)
    with tempfile.TemporaryDirectory(dir=record["workDir"]) as temporary:
        manifest, payload_paths = manager._extract_archive(
            record["incomingArchive"], Path(temporary) / "incoming"
        )
        restored_hmac = manager._validate_extracted_archive(
            manifest, payload_paths, require_compatible_endpoint=True
        )
        expected_database = payload_paths["data/panel.db"]
        with sqlite3.connect(str(expected_database)) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(proxy_users)")}
            if "allow_udp_443" not in columns:
                connection.execute("ALTER TABLE proxy_users ADD COLUMN allow_udp_443 INTEGER NOT NULL DEFAULT 0")
        manager._validate_applied_restore(
            record["envFile"], restored_hmac, manifest, temporary, expected_database
        )


def _validate_backup_directory(record, root_uid=0):
    backup_dir = Path(record["backupDir"])
    metadata = os.lstat(backup_dir)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != root_uid
        or (root_uid == 0 and metadata.st_gid != 0)
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("restore backup directory is invalid")
    verified = {}
    for name, digest in record["oldFiles"].items():
        path = backup_dir / name
        maximum = {
            "panel.db": MAX_BACKUP_CONTENT_BYTES,
            "server.crt": 1024 * 1024,
            "server.key": 1024 * 1024,
            "panel.env": 1024 * 1024,
        }[name]
        details = _secure_regular_details(
            path, maximum, allowed_uids={root_uid}, required_mode=0o600
        )
        if details["sha256"] != digest:
            raise RuntimeError("restore backup file is invalid")
        verified[name] = details
    return verified


def _restore_old_files(record, root_uid=0):
    verified = _validate_backup_directory(record, root_uid)
    manager = _restore_manager_from_record(record)
    backup_dir = Path(record["backupDir"])
    replacements = (
        (record["databasePath"], "panel.db"),
        (record["tlsCert"], "server.crt"),
        (record["tlsKey"], "server.key"),
        (record["envFile"], "panel.env"),
    )
    manager._require_space_allocations(
        (Path(target).parent, verified[name]["size"])
        for target, name in replacements
    )
    for target, name in replacements:
        manager._replace_file(target, backup_dir / name)
    for suffix in ("-wal", "-shm"):
        _durable_unlink(Path(record["databasePath"] + suffix))
    if _validate_current_restore_identity(record, root_uid) != record["oldFiles"]:
        raise RuntimeError("restored rollback identity does not match its backup")


def _quarantine_queued_transaction(record, root_uid=0):
    manager = _restore_manager_from_record(record)
    archive = Path(record["queuedArchive"])
    details = _secure_regular_details(
        archive,
        MAX_BACKUP_ARCHIVE_BYTES,
        allowed_uids={root_uid},
        required_mode=0o600,
    )
    if (
        details["sha256"] != record["pendingSha256"]
        or details["size"] != record["pendingSize"]
    ):
        raise RuntimeError("pending restore archive changed")
    quarantine = manager.work_dir / "failed-restore-{}-{}.zip".format(
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        secrets.token_hex(4),
    )
    _durable_move(archive, quarantine)
    manager._prune_entries(
        manager.work_dir,
        FAILED_RESTORE_NAME_PATTERN,
        FAILED_RESTORE_RETENTION_SECONDS,
        FAILED_RESTORE_MAX_ENTRIES,
        keep=(quarantine,),
    )


def _discard_recorded_pending(record):
    manager = _restore_manager_from_record(record)
    try:
        digest, size, metadata = manager._secure_pending_archive()
    except BackupValidationError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            return
        raise
    if digest != record["pendingSha256"] or size != record["pendingSize"]:
        raise RuntimeError("pending restore archive changed")
    manager._consume_captured_pending(metadata)


def _cleanup_recorded_uploads(record, root_uid=0):
    try:
        _quarantine_queued_transaction(record, root_uid)
    except RuntimeError as exc:
        if not isinstance(exc.__cause__, FileNotFoundError):
            raise
    _discard_recorded_pending(record)


def _reconcile_restore_transaction(record, marker_path, identity_uid=0):
    if record["phase"] == "services-pending":
        _cleanup_recorded_uploads(record, identity_uid)
        return record
    if record["phase"] == "queued":
        record["oldFiles"] = _validate_current_restore_identity(record, identity_uid)
        record["phase"] = "disk-consistent"
        record["outcome"] = "rolled-back"
        _atomic_write_json(marker_path, record)
        _cleanup_recorded_uploads(record, identity_uid)
        return record
    if record["phase"] == "prepared":
        try:
            _validate_applied_transaction(record)
        except Exception:
            _restore_old_files(record, identity_uid)
            record["outcome"] = "rolled-back"
        else:
            record["outcome"] = "applied"
        record["phase"] = "disk-consistent"
        _atomic_write_json(marker_path, record)
        _cleanup_recorded_uploads(record, identity_uid)
        return record
    if record.get("outcome") == "applied":
        _validate_applied_transaction(record)
    elif record.get("outcome") == "rolled-back":
        current = _validate_current_restore_identity(record, identity_uid)
        if current != record["oldFiles"]:
            raise RuntimeError("rolled-back restore identity changed")
    else:
        raise RuntimeError("restore transaction outcome is invalid")
    _cleanup_recorded_uploads(record, identity_uid)
    return record


def _reconcile_to_services_pending(record, marker_path, identity_uid=0):
    record = _reconcile_restore_transaction(
        record, marker_path, identity_uid=identity_uid
    )
    if record["phase"] == "disk-consistent":
        record["phase"] = "services-pending"
        _atomic_write_json(marker_path, record)
    elif record["phase"] != "services-pending":
        raise RuntimeError("restore files are not consistent")
    return record


def recover_restore_files(
    lock_path=MAINTENANCE_LOCK_PATH,
    marker_path=RESTORE_ACTIVE_MARKER,
    pending_path=RESTORE_WORK_DIR / "pending-restore.zip",
    captured_path=None,
    work_dir=RESTORE_WORK_DIR,
    pending_uid=None,
    expected_uid=0,
    strict_paths=True,
):
    captured_path = Path(captured_path or (str(marker_path) + ".archive"))
    default_target_paths = (
        Path("/var/lib/hysteria2-panel/panel.db"),
        Path("/etc/hysteria2-panel/server.crt"),
        Path("/etc/hysteria2-panel/server.key"),
        Path(RESTORE_ENV_FILE),
    )
    try:
        os.lstat(marker_path)
    except FileNotFoundError:
        pending_exists = captured_exists = True
        try:
            os.lstat(pending_path)
        except FileNotFoundError:
            pending_exists = False
        try:
            os.lstat(captured_path)
        except FileNotFoundError:
            captured_exists = False
        if not pending_exists and not captured_exists:
            try:
                with exclusive_maintenance_lock(lock_path, blocking=False):
                    _cleanup_restore_temporary_files(
                        work_dir,
                        pending_path,
                        captured_path,
                        target_paths=default_target_paths,
                        expected_uid=expected_uid,
                        pending_uid=pending_uid,
                    )
            except RuntimeError as exc:
                if "维护任务正在运行" not in str(exc):
                    raise
            return
    with exclusive_maintenance_lock(lock_path, blocking=True):
        record = _read_restore_transaction(
            marker_path, expected_uid=expected_uid, strict_paths=strict_paths
        )
        target_paths = default_target_paths
        target_keys = ("databasePath", "tlsCert", "tlsKey", "envFile")
        if record is not None and all(name in record for name in target_keys):
            target_paths = tuple(
                Path(record[name])
                for name in target_keys
            )
        _cleanup_restore_temporary_files(
            work_dir,
            pending_path,
            captured_path,
            target_paths=target_paths,
            expected_uid=expected_uid,
            pending_uid=pending_uid,
        )
        if record is not None:
            _reconcile_to_services_pending(
                record, marker_path, identity_uid=expected_uid
            )
            return
        work_metadata = os.lstat(work_dir)
        if (
            not stat.S_ISDIR(work_metadata.st_mode)
            or stat.S_IMODE(work_metadata.st_mode) != 0o700
        ):
            raise RuntimeError("restore work directory is unsafe")
        allowed_pending_uid = work_metadata.st_uid if pending_uid is None else pending_uid
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        quarantines = []
        for source, owner_uid, label in (
            (Path(pending_path), allowed_pending_uid, "pending"),
            (captured_path, expected_uid, "captured"),
        ):
            try:
                os.lstat(source)
            except FileNotFoundError:
                continue
            quarantine = Path(work_dir) / "failed-restore-orphan-{}-{}-{}.zip".format(
                label, timestamp, secrets.token_hex(4)
            )
            _quarantine_secure_orphan(
                source, quarantine, MAX_BACKUP_ARCHIVE_BYTES, owner_uid
            )
            quarantines.append(quarantine)
        BackupManager._prune_entries(
            work_dir,
            FAILED_RESTORE_NAME_PATTERN,
            FAILED_RESTORE_RETENTION_SECONDS,
            FAILED_RESTORE_MAX_ENTRIES,
            keep=quarantines,
        )


def verify_restore_services(
    settings,
    runner=subprocess.run,
    health_probe=_default_restore_health_probe,
    stats_probe=_default_restore_stats_probe,
    tcp_probe=_default_restore_tcp_probe,
    attempts=30,
    interval=0.2,
    sleeper=time.sleep,
):
    failure = None
    consecutive = 0
    for attempt in range(max(2, int(attempts))):
        try:
            expected = _restore_expected_units(settings, runner)
            _probe_restored_services(settings, expected, health_probe, stats_probe, tcp_probe)
            consecutive += 1
            if consecutive >= 2:
                return
        except Exception as exc:
            failure = exc
            consecutive = 0
        if attempt + 1 < max(2, int(attempts)):
            sleeper(max(0, float(interval)))
    raise RuntimeError("restored project services are not healthy") from failure


def resume_after_restore(
    settings,
    lock_path=MAINTENANCE_LOCK_PATH,
    marker_path=RESTORE_ACTIVE_MARKER,
    runner=subprocess.run,
    marker_reader=_read_restore_transaction,
    expected_uid=0,
    strict_paths=True,
    **start_options
):
    with exclusive_maintenance_lock(lock_path, blocking=True):
        record = marker_reader(
            marker_path, expected_uid=expected_uid, strict_paths=strict_paths
        )
        if record is None:
            return
        if record["phase"] != "services-pending":
            raise RuntimeError("restore files have not passed preflight recovery")
        verify_restore_services(settings, runner=runner, **start_options)
        _remove_restore_marker(marker_path)


def restore_pending(
    settings,
    lock_path=MAINTENANCE_LOCK_PATH,
    marker_path=RESTORE_ACTIVE_MARKER,
    runner=subprocess.run,
    quiesce=quiesce_stats_client,
):
    with exclusive_maintenance_lock(lock_path, blocking=True), defer_termination_signals():
        manager = BackupManager(
            database=Database(settings.database_path, settings.hmac_key),
            hmac_key=settings.hmac_key,
            tls_cert=settings.tls_cert,
            tls_key=settings.tls_key,
            public_host=settings.public_host,
            hysteria_port=settings.hysteria_port,
            node_name=settings.node_name,
            work_dir=settings.database_path.parent / "backup-restore",
        )
        if _read_restore_transaction(
            marker_path,
            expected_uid=os.geteuid() if hasattr(os, "geteuid") else None,
            strict_paths=False,
        ) is not None:
            raise RuntimeError("an earlier restore transaction still requires recovery")
        manager.queue_restore_transaction(
            marker_path, RESTORE_ENV_FILE, RESTORE_BACKUP_ROOT
        )
        try:
            settle_restore_traffic(settings, runner=runner, quiesce=quiesce)
            stop_restore_services(runner=runner)
            result = manager.apply_pending_archive(
                env_file=RESTORE_ENV_FILE,
                backup_root=RESTORE_BACKUP_ROOT,
                transaction_path=marker_path,
                archive_path=Path(str(marker_path) + ".archive"),
            )
            record = _read_restore_transaction(
                marker_path,
                expected_uid=os.geteuid() if hasattr(os, "geteuid") else None,
                strict_paths=False,
            )
            if record is None:
                raise RuntimeError("restore transaction marker disappeared after apply")
            _reconcile_to_services_pending(
                record,
                marker_path,
                identity_uid=os.geteuid() if hasattr(os, "geteuid") else 0,
            )
        except Exception:
            record = _read_restore_transaction(
                marker_path,
                expected_uid=os.geteuid() if hasattr(os, "geteuid") else None,
                strict_paths=False,
            )
            if record is not None:
                _reconcile_to_services_pending(
                    record,
                    marker_path,
                    identity_uid=os.geteuid() if hasattr(os, "geteuid") else 0,
                )
            raise
    print(
        json.dumps(
            {
                "status": "ok",
                "proxyUserCount": result["proxyUserCount"],
                "automaticBackup": result["automaticBackup"],
            },
            separators=(",", ":"),
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hysteria 2 multi-user panel")
    subcommands = parser.add_subparsers(dest="command", required=True)
    init_parser = subcommands.add_parser("init-admin", help="create or update the administrator")
    init_parser.add_argument("--username", required=True)
    init_parser.add_argument("--if-missing", action="store_true")
    subcommands.add_parser("serve", help="run the authentication service and panel")
    sync_parser = subcommands.add_parser(
        "sync-traffic", help="flush Hysteria traffic before maintenance"
    )
    sync_endpoints = sync_parser.add_mutually_exclusive_group()
    sync_endpoints.add_argument("--primary-only", action="store_true")
    sync_endpoints.add_argument("--secondary-only", action="store_true")
    sync_parser.add_argument("--quiesce", action="store_true")
    subcommands.add_parser("restore-pending", help="apply the staged backup as root")
    subcommands.add_parser("recover-restore-files", help=argparse.SUPPRESS)
    subcommands.add_parser("resume-after-restore", help=argparse.SUPPRESS)
    subcommands.add_parser("recover-egress-policy", help=argparse.SUPPRESS)
    record_egress_parser = subcommands.add_parser(
        "record-egress-policy-state", help=argparse.SUPPRESS
    )
    record_egress_parser.add_argument("policy", choices=("web", "full"))
    subcommands.add_parser("apply-update", help="install the latest formal release as root")
    egress_parser = subcommands.add_parser(
        "apply-egress-policy", help="apply a fixed egress policy as root"
    )
    egress_parser.add_argument("policy", choices=("web", "full"))
    args = parser.parse_args(argv)
    try:
        if args.command == "recover-restore-files":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("recover-restore-files must run as root")
            recover_restore_files(strict_paths=False)
            return 0
        if args.command == "recover-egress-policy":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("recover-egress-policy must run as root")
            with exclusive_maintenance_lock(blocking=True), defer_termination_signals():
                EgressPolicyManager().recover()
            return 0
        settings = Settings.from_mapping(os.environ)
        if args.command == "record-egress-policy-state":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("record-egress-policy-state must run as root")
            EgressPolicyManager().record_current_state(args.policy, settings.panel_port)
            return 0
        if args.command == "resume-after-restore":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("resume-after-restore must run as root")
            resume_after_restore(settings, strict_paths=False)
            return 0
        if args.command == "init-admin":
            password = os.environ.get("HY2PANEL_ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
            changed = initialize_admin(settings, args.username, password, args.if_missing)
            print(json.dumps({"status": "ok", "adminCreated": changed}, separators=(",", ":")))
            return 0
        if args.command == "restore-pending":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("restore-pending must run as root")
            if EgressPolicyManager.TRANSACTION_PATH.exists():
                raise RuntimeError("egress policy recovery must complete before restore")
            restore_pending(settings)
            return 0
        if args.command == "sync-traffic":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("sync-traffic must run as root")
            with defer_termination_signals():
                sync_traffic(
                    settings,
                    primary_only=args.primary_only,
                    secondary_only=args.secondary_only,
                    quiesce=args.quiesce,
                )
            return 0
        if args.command == "apply-update":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("apply-update must run as root")
            if EgressPolicyManager.TRANSACTION_PATH.exists():
                raise RuntimeError("egress policy recovery must complete before update")
            result = UpdateInstaller().apply()
            print(json.dumps(result, separators=(",", ":")))
            return 0
        if args.command == "apply-egress-policy":
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                raise RuntimeError("apply-egress-policy must run as root")
            with exclusive_maintenance_lock(blocking=False), defer_termination_signals():
                EgressPolicyManager().apply(args.policy, settings.panel_port)
            print(json.dumps({"status": "ok", "policy": args.policy}, separators=(",", ":")))
            return 0
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        run_service(settings)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print("hysteria2-panel: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
