#!/usr/bin/env python3
"""Daily, self-validated Hysteria2-panel backup delivery to HTTPS WebDAV."""

import base64
import datetime
import hashlib
import html
import http.client
import json
import os
import pathlib
import re
import secrets
import ssl
import stat
import tempfile
import urllib.parse


REMOTE_NAME = re.compile(
    r"hysteria2-panel-offsite-([0-9]{8}T[0-9]{6}Z)-([0-9a-f]{8})\.zip"
)
TEMPORARY_REMOTE_NAME = re.compile(
    r"\.upload-([0-9]{8}T[0-9]{6}Z)-([0-9a-f]{32})"
)
MAX_ARCHIVE_BYTES = 131 * 1024 * 1024


class OffsiteBackupConfig:
    def __init__(self, endpoint, username, password):
        self.endpoint = endpoint
        self.username = username
        self.password = password

    @classmethod
    def load(cls, path, expected_uid=0):
        path = pathlib.Path(path)
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != expected_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size <= 0
            or metadata.st_size > 16 * 1024
        ):
            raise ValueError("offsite backup config is unsafe")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(str(path), flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise ValueError("offsite backup config changed while reading")
            raw = os.read(descriptor, 16 * 1024 + 1)
        finally:
            os.close(descriptor)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("offsite backup config is invalid") from exc
        if not isinstance(value, dict) or set(value) != {
            "endpoint",
            "username",
            "password",
        }:
            raise ValueError("offsite backup config is invalid")
        endpoint = value["endpoint"]
        username = value["username"]
        password = value["password"]
        if (
            not isinstance(endpoint, str)
            or len(endpoint) > 2048
            or not isinstance(username, str)
            or not 1 <= len(username) <= 256
            or not isinstance(password, str)
            or not 1 <= len(password) <= 4096
        ):
            raise ValueError("offsite backup config is invalid")
        parsed = urllib.parse.urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not parsed.path.endswith("/")
        ):
            raise ValueError("offsite backup endpoint must be an HTTPS directory")
        return cls(endpoint, username, password)


class HttpsWebDavClient:
    MAX_RESPONSE_BYTES = 1024 * 1024

    def __init__(self, config, timeout=60):
        self.config = config
        self.timeout = max(5, min(300, int(timeout)))
        self.parsed = urllib.parse.urlsplit(config.endpoint)
        token = base64.b64encode(
            (config.username + ":" + config.password).encode("utf-8")
        ).decode("ascii")
        self.authorization = "Basic " + token

    def _remote_url(self, name):
        return urllib.parse.urlunsplit(
            (
                "https",
                self.parsed.netloc,
                self.parsed.path + urllib.parse.quote(name, safe=""),
                "",
                "",
            )
        )

    def _request(self, method, name="", body=None, body_size=None, headers=None):
        path = self.parsed.path + urllib.parse.quote(name, safe="")
        connection = http.client.HTTPSConnection(
            self.parsed.hostname,
            self.parsed.port or 443,
            timeout=self.timeout,
            context=ssl.create_default_context(),
        )
        try:
            connection.putrequest(method, path)
            connection.putheader("Authorization", self.authorization)
            connection.putheader("User-Agent", "hysteria2-panel-offsite-backup/1")
            for key, value in (headers or {}).items():
                connection.putheader(key, value)
            if body is not None:
                if not isinstance(body_size, int) or body_size < 1:
                    raise ValueError("WebDAV request body size is invalid")
                connection.putheader("Content-Length", str(body_size))
                connection.putheader("Content-Type", "application/zip")
            else:
                connection.putheader("Content-Length", "0")
            connection.endheaders()
            if body is not None:
                remaining = body_size
                while remaining:
                    chunk = body.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise RuntimeError("backup archive changed while uploading")
                    connection.send(chunk)
                    remaining -= len(chunk)
            response = connection.getresponse()
            body = response.read(self.MAX_RESPONSE_BYTES + 1)
            if len(body) > self.MAX_RESPONSE_BYTES:
                raise RuntimeError("WebDAV response is too large")
            return response.status, dict(response.getheaders()), body
        finally:
            connection.close()

    @staticmethod
    def _require_status(status, allowed):
        if status not in allowed:
            raise RuntimeError("WebDAV operation failed with status {}".format(status))

    def put(self, name, handle, size, sha256):
        status, _headers, _body = self._request(
            "PUT",
            name,
            body=handle,
            body_size=size,
            headers={"X-Checksum-SHA256": sha256},
        )
        self._require_status(status, {200, 201, 204})

    def move(self, source, destination):
        status, _headers, _body = self._request(
            "MOVE",
            source,
            headers={"Destination": self._remote_url(destination), "Overwrite": "F"},
        )
        self._require_status(status, {201, 204})

    def size(self, name):
        status, headers, _body = self._request("HEAD", name)
        self._require_status(status, {200})
        try:
            size = int(headers["Content-Length"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("WebDAV object size is unavailable") from exc
        if size < 1:
            raise RuntimeError("WebDAV object size is invalid")
        return size

    def list_names(self):
        status, _headers, body = self._request(
            "PROPFIND", headers={"Depth": "1", "Content-Type": "application/xml"}
        )
        self._require_status(status, {207})
        try:
            document = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("WebDAV listing is invalid") from exc
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", document, re.IGNORECASE):
            raise RuntimeError("WebDAV listing is invalid")
        hrefs = re.findall(
            r"<(?:[A-Za-z_][\w.-]*:)?href(?:\s[^>]*)?>"
            r"([^<]{1,8192})"
            r"</(?:[A-Za-z_][\w.-]*:)?href\s*>",
            document,
            re.IGNORECASE,
        )
        if not hrefs:
            raise RuntimeError("WebDAV listing is invalid")
        names = []
        for href in hrefs:
            path = urllib.parse.unquote(
                urllib.parse.urlsplit(html.unescape(href.strip())).path
            )
            name = pathlib.PurePosixPath(path.rstrip("/")).name
            if name:
                names.append(name)
        return names

    def delete(self, name):
        status, _headers, _body = self._request("DELETE", name)
        self._require_status(status, {200, 204})


class WebDavBackupStore:
    def __init__(self, client, retention_days=30):
        self.client = client
        self.retention_days = max(1, min(3650, int(retention_days)))

    @staticmethod
    def _sha256(handle):
        digest = hashlib.sha256()
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _file_signature(metadata):
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_nlink,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_size,
            metadata.st_mtime_ns,
        )

    @staticmethod
    def _open_archive(path, expected_uid):
        path = pathlib.Path(path)
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != expected_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size <= 0
            or metadata.st_size > MAX_ARCHIVE_BYTES
        ):
            raise ValueError("backup archive is unsafe")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        descriptor = os.open(str(path), flags)
        try:
            opened = os.fstat(descriptor)
            if (
                (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
                or opened.st_nlink != 1
                or opened.st_uid != expected_uid
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_size != metadata.st_size
            ):
                raise ValueError("backup archive changed while opening")
            return os.fdopen(descriptor, "rb"), opened
        except Exception:
            os.close(descriptor)
            raise

    def _clean_stale_temporary_uploads(self, names, now):
        cutoff = now - datetime.timedelta(days=1)
        deleted = []
        for candidate in names:
            match = TEMPORARY_REMOTE_NAME.fullmatch(candidate)
            if match is None:
                continue
            created = datetime.datetime.strptime(
                match.group(1), "%Y%m%dT%H%M%SZ"
            ).replace(tzinfo=datetime.timezone.utc)
            if created < cutoff:
                self.client.delete(candidate)
                deleted.append(candidate)
        return deleted

    def upload(self, archive_path, now=None, expected_uid=None):
        expected_uid = os.geteuid() if expected_uid is None else int(expected_uid)
        now = now or datetime.datetime.now(datetime.timezone.utc)
        if now.tzinfo is None:
            raise ValueError("backup time must be timezone-aware")
        now = now.astimezone(datetime.timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        temporary = ".upload-{}-{}".format(stamp, secrets.token_hex(16))
        handle, opened = self._open_archive(archive_path, expected_uid)
        try:
            digest = self._sha256(handle)
            if self._file_signature(os.fstat(handle.fileno())) != self._file_signature(
                opened
            ):
                raise RuntimeError("backup archive changed while hashing")
            name = "hysteria2-panel-offsite-{}-{}.zip".format(stamp, digest[:8])
            handle.seek(0)
            try:
                self.client.put(temporary, handle, opened.st_size, digest)
                self.client.move(temporary, name)
            except Exception as upload_error:
                try:
                    self.client.delete(temporary)
                except Exception as cleanup_error:
                    raise upload_error from cleanup_error
                raise
            if self._file_signature(os.fstat(handle.fileno())) != self._file_signature(
                opened
            ):
                raise RuntimeError("backup archive changed while uploading")
        finally:
            handle.close()
        if int(self.client.size(name)) != opened.st_size:
            raise RuntimeError("uploaded WebDAV backup size does not match")
        cutoff = now - datetime.timedelta(days=self.retention_days)
        deleted = []
        names = self.client.list_names()
        deleted.extend(self._clean_stale_temporary_uploads(names, now))
        for candidate in names:
            match = REMOTE_NAME.fullmatch(candidate)
            if match is None or candidate == name:
                continue
            created = datetime.datetime.strptime(
                match.group(1), "%Y%m%dT%H%M%SZ"
            ).replace(tzinfo=datetime.timezone.utc)
            if created < cutoff:
                self.client.delete(candidate)
                deleted.append(candidate)
        return {
            "name": name,
            "sha256": digest,
            "size": opened.st_size,
            "deleted": deleted,
        }


class OffsiteBackupRunner:
    def __init__(
        self,
        config_path,
        status_path,
        archive_factory,
        expected_uid=0,
        status_gid=0,
        client_factory=HttpsWebDavClient,
        clock=None,
    ):
        self.config_path = pathlib.Path(config_path)
        self.status_path = pathlib.Path(status_path)
        self.archive_factory = archive_factory
        self.expected_uid = expected_uid
        self.status_gid = status_gid
        self.client_factory = client_factory
        self.clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))

    def _write_status(self, state, last_success_at=None, error_code=None):
        now = self.clock().astimezone(datetime.timezone.utc)
        value = {
            "state": state,
            "checkedAt": now.isoformat().replace("+00:00", "Z"),
            "lastSuccessAt": last_success_at,
            "errorCode": error_code,
        }
        self.status_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".offsite-status-", dir=str(self.status_path.parent)
        )
        try:
            os.fchmod(descriptor, 0o640)
            os.fchown(descriptor, os.geteuid(), self.status_gid)
            payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            ) + b"\n"
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.status_path)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
        return value

    def _previous_last_success_at(self):
        try:
            metadata = self.status_path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != self.expected_uid
                or metadata.st_size <= 0
                or metadata.st_size > 16 * 1024
            ):
                return None
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
                os, "O_NOFOLLOW", 0
            )
            descriptor = os.open(str(self.status_path), flags)
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    return None
                raw = os.read(descriptor, 16 * 1024 + 1)
            finally:
                os.close(descriptor)
            value = json.loads(raw.decode("utf-8"))
            previous = value.get("lastSuccessAt") if isinstance(value, dict) else None
            if previous is None or (
                isinstance(previous, str)
                and 1 <= len(previous) <= 64
                and previous.endswith("Z")
            ):
                return previous
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        return None

    def run(self):
        previous_last_success_at = self._previous_last_success_at()
        if not self.config_path.exists():
            return self._write_status(
                "not_configured", last_success_at=previous_last_success_at
            )
        archive = None
        try:
            config = OffsiteBackupConfig.load(
                self.config_path, expected_uid=self.expected_uid
            )
            archive = self.archive_factory()
            store = WebDavBackupStore(self.client_factory(config), retention_days=30)
            result = store.upload(
                archive, now=self.clock(), expected_uid=self.expected_uid
            )
        except Exception:
            self._write_status(
                "failed",
                last_success_at=previous_last_success_at,
                error_code="BACKUP_FAILED",
            )
            raise
        finally:
            if archive is not None:
                try:
                    pathlib.Path(archive).unlink()
                except FileNotFoundError:
                    pass
        status = self._write_status(
            "success",
            last_success_at=self.clock()
            .astimezone(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        )
        status["result"] = result
        return status
