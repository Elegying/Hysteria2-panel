#!/usr/bin/env python3
"""Minimal first-phase agent used to enroll a new node for verification."""

import argparse
import base64
import hashlib
import json
import os
import pathlib
import platform
import re
import secrets
import shutil
import signal
import socket
import ssl
import stat
import subprocess  # nosec B404 -- fixed executable and argv, never a shell.
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


AGENT_VERSION = "0.38.3"
MAX_RESPONSE_BYTES = 8192
CONTROL_REQUEST_TIMEOUT_SECONDS = 10
NODE_PROTOCOL_REQUEST_TIMEOUT_SECONDS = 8
CONTROL_LOOP_INTERVAL_SECONDS = 2
CONTROL_LOOP_MAX_INTERVAL_SECONDS = 5
CONTROL_LOOP_MAX_BACKOFF_SECONDS = 30
CONTROL_CYCLE_PAYLOAD_BUDGET_BYTES = 480 * 1024
LOCAL_TRAFFIC_RESPONSE_MAX_BYTES = 512 * 1024
TRAFFIC_SPOOL_ENTRY_MAX_BYTES = 240 * 1024
MAX_STATE_AGE_SECONDS = (
    NODE_PROTOCOL_REQUEST_TIMEOUT_SECONDS
    + CONTROL_LOOP_MAX_BACKOFF_SECONDS
    + CONTROL_LOOP_MAX_INTERVAL_SECONDS
)
ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
NODE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


class RegistrationError(RuntimeError):
    """Registration failed without exposing the enrollment credential."""


class HeartbeatError(RuntimeError):
    """Heartbeat failed without exposing local node identity material."""


class ProtocolError(RuntimeError):
    """Distributed control failed without exposing credentials or node identity."""


class ProtocolNotSupported(ProtocolError):
    """The panel does not yet support an additive node protocol endpoint."""


class PartialLocalTrafficCollectionError(ProtocolError):
    """One stats endpoint failed after another endpoint had already cleared data."""

    def __init__(self, batches):
        super().__init__("one or more local traffic endpoints are unavailable")
        self.batches = list(batches)


class SystemdNotifier:
    """Small dependency-free sd_notify client for the standalone node agent."""

    def __init__(self, environment=None, socket_factory=socket.socket):
        self._environment = os.environ if environment is None else environment
        self._socket_factory = socket_factory

    @property
    def watchdog_interval(self):
        configured_pid = self._environment.get("WATCHDOG_PID")
        if configured_pid:
            try:
                if int(configured_pid) != os.getpid():
                    return None
            except ValueError:
                return None
        try:
            microseconds = int(self._environment.get("WATCHDOG_USEC", "0"))
        except ValueError:
            return None
        if microseconds <= 0 or not self._environment.get("NOTIFY_SOCKET"):
            return None
        return microseconds / 2_000_000

    def _notify(self, fields):
        address = self._environment.get("NOTIFY_SOCKET")
        if not address:
            return False
        if address.startswith("@"):
            address = "\0" + address[1:]
        try:
            with self._socket_factory(socket.AF_UNIX, socket.SOCK_DGRAM) as notifier:
                notifier.sendto("\n".join(fields).encode("utf-8"), address)
        except OSError:
            return False
        return True

    @staticmethod
    def _status(value):
        return str(value).replace("\r", " ").replace("\n", " ")

    def ready(self, status="ready"):
        return self._notify(("READY=1", "STATUS={}".format(self._status(status))))

    def watchdog(self):
        if self.watchdog_interval is None:
            return False
        return self._notify(("WATCHDOG=1",))

    def stopping(self, status="stopping"):
        return self._notify(
            ("STOPPING=1", "STATUS={}".format(self._status(status)))
        )


def _panel_url(value):
    parsed = urllib.parse.urlsplit(str(value or ""))
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("node registration requires an HTTPS panel URL")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("panel URL port is invalid") from exc
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _architecture(value=None):
    machine = str(value or platform.machine()).lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    raise ValueError("only Linux amd64 and arm64 are supported")


def _hostname(value=None):
    hostname = str(value or socket.getfqdn() or socket.gethostname()).strip().rstrip(".")
    if not HOSTNAME_PATTERN.fullmatch(hostname):
        raise ValueError("the local hostname is not valid for node registration")
    return hostname


def _public_key(path):
    try:
        value = pathlib.Path(path).read_bytes()
    except OSError as exc:
        raise ValueError("cannot read the node public key") from exc
    if len(value) != 44 or not value.startswith(ED25519_SPKI_PREFIX):
        raise ValueError("the node public key is not Ed25519 SPKI DER")
    return base64.b64encode(value).decode("ascii")


def _write_state(path, payload):
    destination = pathlib.Path(path)
    parent = destination.parent
    if parent.exists():
        if parent.is_symlink() or not parent.is_dir():
            raise RegistrationError("node state directory is unsafe")
    else:
        parent.mkdir(parents=True, mode=0o700)
    if destination.exists() or destination.is_symlink():
        raise RegistrationError("node registration state already exists")
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    descriptor, staged_name = tempfile.mkstemp(prefix=".registration-", dir=str(parent))
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged_name, str(destination))
        directory_descriptor = os.open(str(parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            os.unlink(staged_name)
        except FileNotFoundError:
            pass


def _fsync_directory(path):
    descriptor = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def proxy_auth_payload(raw_body, authorize, entrypoint="main"):
    """Map the fixed Hysteria HTTP auth contract to a fail-closed local proxy."""

    denial = (200, {"ok": False, "id": ""})
    if entrypoint not in {"main", "udp443"} or len(raw_body) > 4096:
        return denial
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"addr", "auth", "tx"}:
            return denial
        if (
            not isinstance(payload["addr"], str)
            or not 1 <= len(payload["addr"]) <= 512
            or not isinstance(payload["auth"], str)
            or not 1 <= len(payload["auth"]) <= 512
            or isinstance(payload["tx"], bool)
            or not isinstance(payload["tx"], int)
            or not 0 <= payload["tx"] <= 2**63 - 1
        ):
            return denial
        result = authorize(
            {
                "entrypoint": entrypoint,
                "auth": payload["auth"],
                "tx": payload["tx"],
            }
        )
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("ok"), bool)
            or not isinstance(result.get("id"), str)
            or len(result["id"]) > 64
            or (result["ok"] and not result["id"])
            or (not result["ok"] and result["id"])
        ):
            return denial
        return 200, {"ok": result["ok"], "id": result["id"]}
    except Exception:
        return denial


class NodeAuthProxyHandler(BaseHTTPRequestHandler):
    """Loopback-only Hysteria authentication adapter."""

    server_version = "hy2panel-node-auth"
    sys_version = ""

    def log_message(self, _format, *_args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_metrics(self):
        metrics_file = getattr(self.server, "metrics_file", None)
        try:
            path = pathlib.Path(metrics_file)
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size > 64 * 1024
            ):
                raise OSError("unsafe metrics file")
            body = path.read_bytes()
        except (OSError, TypeError, ValueError):
            body = b"hy2panel_node_control_ready 0\n"
            status_code = 503
        else:
            status_code = 200
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return
        if self.path == "/metrics":
            self._send_metrics()
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        entrypoint = {
            "/auth": "main",
            "/auth/main": "main",
            "/auth/udp-443": "udp443",
            "/auth/udp443": "udp443",
        }.get(self.path)
        if entrypoint is None:
            self._send_json(404, {"ok": False, "id": ""})
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json(200, {"ok": False, "id": ""})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if length < 0 or length > 4096:
            self._send_json(200, {"ok": False, "id": ""})
            return
        body = self.rfile.read(length)
        _status, payload = proxy_auth_payload(
            body, self.server.protocol_client.authorize, entrypoint=entrypoint
        )
        self._send_json(200, payload)


class NodeAuthProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128

    def __init__(
        self,
        server_address,
        handler_class,
        max_workers=32,
        request_timeout=5.0,
    ):
        self.max_workers = max(1, min(128, int(max_workers)))
        self.request_timeout = max(0.1, min(30.0, float(request_timeout)))
        self._worker_slots = threading.BoundedSemaphore(self.max_workers)
        self._timer_lock = threading.Lock()
        self._request_timers = {}
        super().__init__(server_address, handler_class)

    @staticmethod
    def _expire_request(request):
        try:
            request.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def process_request(self, request, client_address):
        if not self._worker_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        timer = threading.Timer(
            self.request_timeout, self._expire_request, args=(request,)
        )
        timer.daemon = True
        with self._timer_lock:
            self._request_timers[id(request)] = timer
        timer.start()
        try:
            super().process_request(request, client_address)
        except Exception:
            self._finish_bounded_request(request)
            raise

    def _finish_bounded_request(self, request):
        with self._timer_lock:
            timer = self._request_timers.pop(id(request), None)
        if timer is not None:
            timer.cancel()
        self._worker_slots.release()

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._finish_bounded_request(request)

    def handle_error(self, _request, _client_address):
        return


def make_node_auth_proxy_server(
    address,
    protocol_client,
    max_workers=32,
    request_timeout=5.0,
    metrics_file=None,
):
    host, port = address
    if str(host) not in {"127.0.0.1", "::1"} or not 0 <= int(port) <= 65535:
        raise ValueError("node auth proxy must bind to loopback")
    server = NodeAuthProxyServer(
        (host, int(port)),
        NodeAuthProxyHandler,
        max_workers=max_workers,
        request_timeout=request_timeout,
    )
    server.protocol_client = protocol_client
    server.metrics_file = metrics_file
    return server


def serve_node_auth_proxy(server, stop_event, notifier=None):
    """Serve loopback auth while proving the accepting loop remains responsive."""
    notifier = notifier or SystemdNotifier()
    server.timeout = 0.2
    notifier.ready("node authentication proxy ready")
    try:
        while not stop_event.is_set():
            server.handle_request()
            notifier.watchdog()
    finally:
        notifier.stopping("node authentication proxy stopping")


class DurableTrafficSpool:
    """Root-only, fsync-backed traffic batches retained until central ACK."""

    def __init__(
        self,
        path,
        max_bytes=16 * 1024 * 1024,
        reserve_bytes=1024 * 1024,
        max_entries=4096,
    ):
        self.path = pathlib.Path(path)
        self.max_bytes = max(4096, int(max_bytes))
        self.reserve_bytes = max(0, int(reserve_bytes))
        self.max_entries = max(1, min(100000, int(max_entries)))
        if self.path.exists():
            metadata = self.path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077
            ):
                raise ProtocolError("traffic spool directory is unsafe")
        else:
            self.path.mkdir(parents=True, mode=0o700)
            self.path.chmod(0o700)
            _fsync_directory(self.path.parent)
        self._recover_staged_entries()

    @staticmethod
    def _validate_traffic(traffic):
        if (
            not isinstance(traffic, dict)
            or len(traffic) > 1000
            or not all(
                isinstance(name, str)
                and 1 <= len(name) <= 64
                and isinstance(counters, dict)
                and set(counters) == {"tx", "rx"}
                and all(
                    not isinstance(value, bool)
                    and isinstance(value, int)
                    and 0 <= value <= 2**63 - 1
                    for value in counters.values()
                )
                for name, counters in traffic.items()
            )
        ):
            raise ProtocolError("traffic batch is invalid")

    def _current_usage(self):
        total = 0
        count = 0
        for path in self.path.iterdir():
            metadata = path.lstat()
            if (
                not path.name.endswith(".json")
                or stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise ProtocolError("traffic spool contains an unsafe entry")
            total += metadata.st_size
            count += 1
            if count > self.max_entries:
                raise ProtocolError("traffic spool contains too many entries")
        return count, total

    @staticmethod
    def _validate_batch(batch):
        if (
            not isinstance(batch, dict)
            or set(batch) != {"batchId", "observedAt", "traffic"}
            or not NODE_ID_PATTERN.fullmatch(str(batch.get("batchId", "")))
            or isinstance(batch.get("observedAt"), bool)
            or not isinstance(batch.get("observedAt"), int)
        ):
            raise ProtocolError("traffic spool entry is invalid")
        DurableTrafficSpool._validate_traffic(batch["traffic"])

    def _recover_staged_entries(self):
        changed = False
        for path in list(self.path.iterdir()):
            if not path.name.startswith(".traffic-"):
                continue
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise ProtocolError("traffic spool contains an unsafe staged entry")
            batch = None
            if 0 < metadata.st_size <= TRAFFIC_SPOOL_ENTRY_MAX_BYTES:
                try:
                    batch = json.loads(path.read_text(encoding="utf-8"))
                    self._validate_batch(batch)
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProtocolError):
                    batch = None
            if batch is None:
                path.unlink()
                changed = True
                continue
            destination = self.path / (batch["batchId"] + ".json")
            if destination.exists():
                if destination.read_bytes() != path.read_bytes():
                    raise ProtocolError("traffic spool staged entry conflicts with a batch")
                path.unlink()
            else:
                os.replace(path, destination)
            changed = True
        if changed:
            _fsync_directory(self.path)

    def can_collect(self, maximum_response_bytes=LOCAL_TRAFFIC_RESPONSE_MAX_BYTES):
        self._recover_staged_entries()
        maximum_response_bytes = max(1, int(maximum_response_bytes))
        required_entries = 1 + (
            maximum_response_bytes + TRAFFIC_SPOOL_ENTRY_MAX_BYTES - 1
        ) // TRAFFIC_SPOOL_ENTRY_MAX_BYTES
        required_bytes = maximum_response_bytes + required_entries * 4096
        free = shutil.disk_usage(str(self.path)).free
        count, current_size = self._current_usage()
        return (
            count + required_entries <= self.max_entries
            and current_size + required_bytes <= self.max_bytes
            and free >= required_bytes + self.reserve_bytes
        )

    @staticmethod
    def _encode_batch(batch):
        return json.dumps(
            batch, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8") + b"\n"

    def _partition(self, traffic, observed_at):
        self._validate_traffic(traffic)
        if isinstance(observed_at, bool) or not isinstance(observed_at, int):
            raise ProtocolError("traffic observation time is invalid")
        encoded_batches = []
        current = {}
        batch_id = uuid.uuid4().hex
        for name, counters in traffic.items():
            candidate = dict(current)
            candidate[name] = counters
            batch = {
                "batchId": batch_id,
                "observedAt": observed_at,
                "traffic": candidate,
            }
            encoded = self._encode_batch(batch)
            if len(encoded) <= TRAFFIC_SPOOL_ENTRY_MAX_BYTES:
                current = candidate
                continue
            if not current:
                raise ProtocolError("traffic entry exceeds the spool entry limit")
            completed = {
                "batchId": batch_id,
                "observedAt": observed_at,
                "traffic": current,
            }
            encoded_batches.append((completed, self._encode_batch(completed)))
            batch_id = uuid.uuid4().hex
            current = {name: counters}
        batch = {
            "batchId": batch_id,
            "observedAt": observed_at,
            "traffic": current,
        }
        encoded = self._encode_batch(batch)
        if len(encoded) > TRAFFIC_SPOOL_ENTRY_MAX_BYTES:
            raise ProtocolError("traffic entry exceeds the spool entry limit")
        encoded_batches.append((batch, encoded))
        return encoded_batches

    def enqueue_collections(self, traffic_collections, observed_at):
        traffic_collections = list(traffic_collections)
        if not traffic_collections:
            return []
        self._recover_staged_entries()
        encoded_batches = []
        for traffic in traffic_collections:
            encoded_batches.extend(self._partition(traffic, observed_at))
        count, current_size = self._current_usage()
        total_size = sum(len(encoded) for _batch, encoded in encoded_batches)
        if (
            count + len(encoded_batches) > self.max_entries
            or current_size + total_size > self.max_bytes
            or shutil.disk_usage(str(self.path)).free
            < total_size + self.reserve_bytes
        ):
            raise ProtocolError("traffic spool is full")
        staged = []
        try:
            for batch, encoded in encoded_batches:
                staged_path = self.path / (".traffic-" + batch["batchId"] + ".json")
                destination = self.path / (batch["batchId"] + ".json")
                if destination.exists():
                    raise ProtocolError("traffic batch id already exists")
                descriptor = os.open(
                    staged_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                )
                staged.append((staged_path, destination))
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
            _fsync_directory(self.path)
            for staged_path, destination in staged:
                os.replace(staged_path, destination)
            _fsync_directory(self.path)
        except Exception as persist_error:
            # Keep every fsynced stage: startup/next-cycle recovery promotes a
            # complete entry and removes only a provably incomplete one.
            try:
                _fsync_directory(self.path)
            except Exception as directory_error:
                raise persist_error from directory_error
            raise
        return [batch for batch, _encoded in encoded_batches]

    def enqueue_many(self, traffic, observed_at):
        return self.enqueue_collections([traffic], observed_at)

    def enqueue(self, traffic, observed_at):
        encoded_batches = self._partition(traffic, observed_at)
        if len(encoded_batches) != 1:
            raise ProtocolError("traffic batch requires multiple spool entries")
        return self.enqueue_many(traffic, observed_at)[0]

    def pending(self):
        self._recover_staged_entries()
        batches = []
        paths = sorted(self.path.glob("*.json"))
        if len(paths) > self.max_entries:
            raise ProtocolError("traffic spool contains too many entries")
        for path in paths:
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size > TRAFFIC_SPOOL_ENTRY_MAX_BYTES
            ):
                raise ProtocolError("traffic spool entry is invalid")
            try:
                batch = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProtocolError("traffic spool entry is invalid") from exc
            self._validate_batch(batch)
            batches.append(
                (batch["observedAt"], metadata.st_mtime_ns, path.name, batch)
            )
        batches.sort(key=lambda item: item[:3])
        return [item[3] for item in batches]

    def ack(self, batch_id):
        if not NODE_ID_PATTERN.fullmatch(str(batch_id or "")):
            raise ProtocolError("traffic batch id is invalid")
        path = self.path / (batch_id + ".json")
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise ProtocolError("traffic spool entry is unsafe")
        path.unlink()
        _fsync_directory(self.path)
        return True


def _read_root_only_file(path, label):
    path = pathlib.Path(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise HeartbeatError("cannot read the node {}".format(label)) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or metadata.st_uid != os.geteuid()
    ):
        raise HeartbeatError("the node {} is not a root-only regular file".format(label))
    try:
        return path.read_bytes()
    except OSError as exc:
        raise HeartbeatError("cannot read the node {}".format(label)) from exc


def _registration_state(path):
    data = _read_root_only_file(path, "registration state")
    if len(data) > MAX_RESPONSE_BYTES:
        raise HeartbeatError("the node registration state is invalid")
    try:
        state = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HeartbeatError("the node registration state is invalid") from exc
    if (
        not isinstance(state, dict)
        or set(state) != {"nodeId", "panelUrl", "registeredAt", "status"}
        or not NODE_ID_PATTERN.fullmatch(str(state.get("nodeId", "")))
        or state.get("status") != "PENDING_VERIFICATION"
        or isinstance(state.get("registeredAt"), bool)
        or not isinstance(state.get("registeredAt"), int)
    ):
        raise HeartbeatError("the node registration state is invalid")
    state["panelUrl"] = _panel_url(state.get("panelUrl"))
    return state


def _canonical_heartbeat(payload):
    return b"hy2panel-node-heartbeat-v1\n" + json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _openssl_message_input(message):
    creator = getattr(os, "memfd_create", None)
    if creator is None or not os.path.isdir("/proc/self/fd"):
        return "/dev/stdin", {"input": message}, None
    descriptor = creator("hy2panel-openssl-message", getattr(os, "MFD_CLOEXEC", 0))
    try:
        remaining = memoryview(message)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("cannot stage the OpenSSL message")
            remaining = remaining[written:]
        os.lseek(descriptor, 0, os.SEEK_SET)
        return (
            "/proc/self/fd/{}".format(descriptor),
            {"pass_fds": (descriptor,)},
            descriptor,
        )
    except Exception:
        os.close(descriptor)
        raise


def _openssl_sign(private_key_path, message, executable="/usr/bin/openssl"):
    private_key_path = pathlib.Path(private_key_path)
    _read_root_only_file(private_key_path, "private key")
    message_descriptor = None
    try:
        message_path, message_options, message_descriptor = _openssl_message_input(
            message
        )
        completed = subprocess.run(  # nosec B603 -- fixed argv, no shell.
            [
                executable,
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(private_key_path),
                "-in",
                message_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
            **message_options,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HeartbeatError("cannot sign the node heartbeat") from exc
    finally:
        if message_descriptor is not None:
            os.close(message_descriptor)
    if completed.returncode != 0 or len(completed.stdout) != 64:
        raise HeartbeatError("cannot sign the node heartbeat")
    return completed.stdout


def register(
    panel_url,
    token,
    public_key_path,
    state_path,
    opener=urllib.request.urlopen,
    hostname=None,
    architecture=None,
    agent_version=AGENT_VERSION,
):
    """Register one public node identity and persist only non-secret state."""
    panel_url = _panel_url(panel_url)
    token = str(token or "")
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("the node enrollment token is invalid")
    payload = {
        "enrollmentToken": token,
        "publicKey": _public_key(public_key_path),
        "hostname": _hostname(hostname),
        "platform": "linux",
        "architecture": _architecture(architecture),
        "agentVersion": str(agent_version),
    }
    request = urllib.request.Request(
        panel_url + "/api/v1/node-registrations",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=10) as response:
            status = getattr(response, "status", response.getcode() if hasattr(response, "getcode") else 0)
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        raise RegistrationError("the panel rejected or could not receive node registration") from exc
    if status != 201 or len(body) > MAX_RESPONSE_BYTES:
        raise RegistrationError("the panel returned an invalid node registration response")
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistrationError("the panel returned an invalid node registration response") from exc
    if (
        not isinstance(result, dict)
        or not NODE_ID_PATTERN.fullmatch(str(result.get("nodeId", "")))
        or result.get("status") != "PENDING_VERIFICATION"
        or set(result) != {"nodeId", "status"}
    ):
        raise RegistrationError("the panel returned an invalid node registration response")
    state = {
        "nodeId": result["nodeId"],
        "panelUrl": panel_url,
        "registeredAt": int(time.time()),
        "status": result["status"],
    }
    _write_state(state_path, state)
    return result


def heartbeat(
    state_path,
    private_key_path,
    opener=urllib.request.urlopen,
    signer=_openssl_sign,
    hostname=None,
    clock=time.time,
    nonce_factory=None,
    agent_version=AGENT_VERSION,
):
    """Sign and send one bounded heartbeat using the enrolled node identity."""
    state = _registration_state(state_path)
    nonce_factory = nonce_factory or secrets.token_urlsafe
    nonce = str(nonce_factory(32))
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", nonce):
        raise HeartbeatError("secure heartbeat nonce generation failed")
    payload = {
        "nodeId": state["nodeId"],
        "sentAt": int(clock()),
        "nonce": nonce,
        "hostname": _hostname(hostname),
        "agentVersion": str(agent_version),
    }
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", payload["agentVersion"]):
        raise HeartbeatError("the node agent version is invalid")
    signature = signer(pathlib.Path(private_key_path), _canonical_heartbeat(payload))
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise HeartbeatError("cannot sign the node heartbeat")
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    request = urllib.request.Request(
        state["panelUrl"] + "/api/v1/node-heartbeats",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=10) as response:
            status = getattr(
                response,
                "status",
                response.getcode() if hasattr(response, "getcode") else 0,
            )
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        raise HeartbeatError("the panel rejected or could not receive node heartbeat") from exc
    if status != 200 or len(body) > MAX_RESPONSE_BYTES:
        raise HeartbeatError("the panel returned an invalid node heartbeat response")
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HeartbeatError("the panel returned an invalid node heartbeat response") from exc
    if (
        not isinstance(result, dict)
        or set(result) != {"status", "acceptedAt", "nextHeartbeatSeconds"}
        or result.get("status") != "ONLINE"
        or isinstance(result.get("acceptedAt"), bool)
        or not isinstance(result.get("acceptedAt"), int)
        or result.get("nextHeartbeatSeconds") != 60
    ):
        raise HeartbeatError("the panel returned an invalid node heartbeat response")
    return result


def _canonical_node_request(purpose, payload):
    if purpose not in {
        "auth",
        "online",
        "traffic",
        "command-poll",
        "command-ack",
        "control-cycle",
    }:
        raise ProtocolError("node request purpose is invalid")
    return "hy2panel-node-{}-v1\n".format(purpose).encode("ascii") + json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_data_plane_request(purpose, payload):
    if purpose not in {"claim", "bootstrap", "ack"}:
        raise ProtocolError("data-plane request purpose is invalid")
    return "hy2panel-data-plane-{}-v1\n".format(purpose).encode(
        "ascii"
    ) + json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _openssl_filter(arguments, value, executable="/usr/bin/openssl"):
    try:
        completed = subprocess.run(  # nosec B603 -- fixed executable and argv.
            [executable] + list(arguments),
            input=value,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProtocolError("data-plane identity validation failed") from exc
    if completed.returncode != 0 or not completed.stdout:
        raise ProtocolError("data-plane identity validation failed")
    return completed.stdout


def validate_data_plane_identity(response, architecture):
    expected_fields = {
        "grantId",
        "expiresAt",
        "fetchAttempt",
        "maxFetchAttempts",
        "configProtocolVersion",
        "hysteriaVersion",
        "hysteriaSha256",
        "ports",
        "certificatePem",
        "privateKeyPem",
        "certificateFileSha256",
        "certificateDerSha256",
        "privateKeyPublicSha256",
        "egressPolicy",
    }
    digest_fields = (
        "certificateFileSha256",
        "certificateDerSha256",
        "privateKeyPublicSha256",
    )
    if (
        not isinstance(response, dict)
        or set(response) != expected_fields
        or not NODE_ID_PATTERN.fullmatch(str(response.get("grantId", "")))
        or isinstance(response.get("expiresAt"), bool)
        or not isinstance(response.get("expiresAt"), int)
        or isinstance(response.get("fetchAttempt"), bool)
        or not isinstance(response.get("fetchAttempt"), int)
        or not 1 <= response["fetchAttempt"] <= 3
        or response.get("maxFetchAttempts") != 3
        or response.get("configProtocolVersion") != 1
        or response.get("hysteriaVersion") != "2.12.1"
        or not isinstance(response.get("ports"), dict)
        or set(response["ports"]) != {"main", "udp443"}
        or isinstance(response["ports"].get("main"), bool)
        or not isinstance(response["ports"].get("main"), int)
        or not 1 <= response["ports"]["main"] <= 65535
        or response["ports"]["main"] in {443, 19995, 19996, 19997}
        or response["ports"].get("udp443") != 443
        or response.get("egressPolicy") not in {"web", "full"}
        or any(
            not isinstance(response.get(field), str)
            or re.fullmatch(r"[0-9a-f]{64}", response[field]) is None
            for field in digest_fields
        )
    ):
        raise ProtocolError("the panel returned an invalid data-plane identity")
    try:
        architecture = _architecture(architecture)
    except ValueError as exc:
        raise ProtocolError("the local architecture is not supported") from exc
    hysteria_hashes = response.get("hysteriaSha256")
    if (
        not isinstance(hysteria_hashes, dict)
        or set(hysteria_hashes) != {"amd64", "arm64"}
        or any(
            not isinstance(value, str)
            or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in hysteria_hashes.values()
        )
    ):
        raise ProtocolError("the panel returned invalid Hysteria release metadata")
    certificate_text = response.get("certificatePem")
    private_key_text = response.get("privateKeyPem")
    if (
        not isinstance(certificate_text, str)
        or not certificate_text.startswith("-----BEGIN CERTIFICATE-----\n")
        or not isinstance(private_key_text, str)
        or re.match(
            r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----\n", private_key_text
        )
        is None
    ):
        raise ProtocolError("the panel returned an invalid data-plane identity")
    try:
        certificate = certificate_text.encode("ascii")
        private_key = private_key_text.encode("ascii")
        certificate_der = ssl.PEM_cert_to_DER_cert(certificate_text)
    except (UnicodeError, ValueError) as exc:
        raise ProtocolError("the panel returned an invalid data-plane identity") from exc
    if not 1 <= len(certificate) <= 16 * 1024 or not 1 <= len(private_key) <= 16 * 1024:
        raise ProtocolError("the panel returned an invalid data-plane identity")
    certificate_public_pem = _openssl_filter(
        ["x509", "-pubkey", "-noout"], certificate
    )
    certificate_public_der = _openssl_filter(
        ["pkey", "-pubin", "-outform", "DER"], certificate_public_pem
    )
    private_key_public_der = _openssl_filter(
        ["pkey", "-pubout", "-outform", "DER"], private_key
    )
    if not secrets.compare_digest(certificate_public_der, private_key_public_der):
        raise ProtocolError("the Hysteria certificate and private key do not match")
    actual = {
        "certificateFileSha256": hashlib.sha256(certificate).hexdigest(),
        "certificateDerSha256": hashlib.sha256(certificate_der).hexdigest(),
        "privateKeyPublicSha256": hashlib.sha256(private_key_public_der).hexdigest(),
    }
    if any(
        not secrets.compare_digest(actual[field], response[field])
        for field in digest_fields
    ):
        raise ProtocolError("the Hysteria identity digest does not match")
    return {
        "certificate": certificate,
        "private_key": private_key,
        "certificate_file_sha256": actual["certificateFileSha256"],
        "certificate_der_sha256": actual["certificateDerSha256"],
        "private_key_public_sha256": actual["privateKeyPublicSha256"],
        "hysteria_version": response["hysteriaVersion"],
        "hysteria_sha256": hysteria_hashes[architecture],
        "egress_policy": response["egressPolicy"],
        "main_port": response["ports"]["main"],
    }


def render_data_plane_configs(identity, stats_secret):
    expected_identity = {
        "certificate",
        "private_key",
        "certificate_file_sha256",
        "certificate_der_sha256",
        "private_key_public_sha256",
        "hysteria_version",
        "hysteria_sha256",
        "egress_policy",
        "main_port",
    }
    if (
        not isinstance(identity, dict)
        or set(identity) != expected_identity
        or identity.get("egress_policy") not in {"web", "full"}
        or not isinstance(stats_secret, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{32,128}", stats_secret) is None
    ):
        raise ProtocolError("data-plane configuration input is invalid")
    blocked = (
        "0.0.0.0/8",
        "127.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
    acl = ['    - "reject({})"'.format(network) for network in blocked]
    if identity["egress_policy"] == "web":
        acl.extend(
            '    - "{}"'.format(rule)
            for rule in (
                "direct(all, tcp/22)",
                "direct(all, tcp/19998)",
                "direct(all, tcp/53)",
                "direct(all, udp/53)",
                "direct(all, tcp/80)",
                "direct(all, tcp/443)",
                "direct(all, udp/443)",
                "direct(all, udp/123)",
                "reject(all)",
            )
        )
    else:
        acl.append('    - "direct(all)"')

    def render(port, auth_path, stats_port):
        return """listen: :{port}
tls:
  cert: /etc/hysteria2-panel-node/server.crt
  key: /etc/hysteria2-panel-node/server.key
auth:
  type: http
  http:
    url: http://127.0.0.1:19996/{auth_path}
    insecure: false
congestion:
  type: bbr
  bbrProfile: standard
ignoreClientBandwidth: true
trafficStats:
  listen: 127.0.0.1:{stats_port}
  secret: __HY2PANEL_STATS_SECRET__
acl:
  inline:
{acl}
masquerade:
  type: string
  string:
    content: "404 page not found"
    statusCode: 404
""".format(
            port=port,
            auth_path=auth_path,
            stats_port=stats_port,
            acl="\n".join(acl),
        )

    return {
        "main": render(identity["main_port"], "auth/main", 19997),
        "udp443": render(443, "auth/udp443", 19995),
    }


class DataPlaneBootstrapClient:
    """Fetch and acknowledge a bounded identity response over signed HTTPS."""

    PATHS = {
        "claim": ("/api/v1/node-data-plane/claim", 8 * 1024),
        "bootstrap": ("/api/v1/node-data-plane/bootstrap", 32 * 1024),
        "ack": ("/api/v1/node-data-plane/ack", 8 * 1024),
    }

    def __init__(
        self,
        state_path,
        private_key_path,
        opener=urllib.request.urlopen,
        signer=_openssl_sign,
        clock=time.time,
        nonce_factory=None,
    ):
        self.state_path = pathlib.Path(state_path)
        self.private_key_path = pathlib.Path(private_key_path)
        self.opener = opener
        self.signer = signer
        self.clock = clock
        self.nonce_factory = nonce_factory or secrets.token_urlsafe

    def _post(self, purpose, token, fields):
        if purpose != "claim" and (
            not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token)
        ):
            raise ProtocolError("the data-plane bootstrap credential is invalid")
        state = _registration_state(self.state_path)
        nonce = str(self.nonce_factory(32))
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", nonce):
            raise ProtocolError("secure node request nonce generation failed")
        payload = {
            "nodeId": state["nodeId"],
            "sentAt": int(self.clock()),
            "nonce": nonce,
            "requestId": uuid.uuid4().hex,
        }
        if purpose != "claim":
            payload["bootstrapToken"] = token
        payload.update(fields)
        signature = self.signer(
            self.private_key_path, _canonical_data_plane_request(purpose, payload)
        )
        if not isinstance(signature, bytes) or len(signature) != 64:
            raise ProtocolError("cannot sign the data-plane request")
        payload["signature"] = base64.b64encode(signature).decode("ascii")
        path, maximum = self.PATHS[purpose]
        request = urllib.request.Request(
            state["panelUrl"] + path,
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            ),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            request_timeout = (
                75 if purpose == "ack" else CONTROL_REQUEST_TIMEOUT_SECONDS
            )
            with self.opener(request, timeout=request_timeout) as response:
                status = getattr(
                    response,
                    "status",
                    response.getcode() if hasattr(response, "getcode") else 0,
                )
                body = response.read(maximum + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            raise ProtocolError(
                "the panel rejected or could not receive the data-plane request"
            ) from exc
        if status != 200 or len(body) > maximum:
            raise ProtocolError("the panel returned an invalid data-plane response")
        try:
            result = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError("the panel returned an invalid data-plane response") from exc
        if not isinstance(result, dict):
            raise ProtocolError("the panel returned an invalid data-plane response")
        return result

    def claim(self):
        result = self._post("claim", None, {})
        state = _registration_state(self.state_path)
        if (
            set(result)
            != {
                "nodeId",
                "grantId",
                "expiresAt",
                "maxFetchAttempts",
                "status",
                "bootstrapToken",
            }
            or result.get("nodeId") != state["nodeId"]
            or not NODE_ID_PATTERN.fullmatch(str(result.get("grantId", "")))
            or isinstance(result.get("expiresAt"), bool)
            or not isinstance(result.get("expiresAt"), int)
            or result["expiresAt"] <= int(self.clock())
            or result.get("maxFetchAttempts") != 3
            or result.get("status") != "AUTO_BOOTSTRAP_ISSUED"
            or not isinstance(result.get("bootstrapToken"), str)
            or not TOKEN_PATTERN.fullmatch(result["bootstrapToken"])
        ):
            raise ProtocolError("the panel returned an invalid bootstrap claim")
        return result

    def fetch(self, token):
        return self._post("bootstrap", token, {})

    def ack(self, token, attestation):
        if not isinstance(attestation, dict):
            raise ProtocolError("data-plane attestation is invalid")
        result = self._post("ack", token, attestation)
        state = _registration_state(self.state_path)
        if (
            not isinstance(result, dict)
            or set(result) != {"nodeId", "status"}
            or result.get("nodeId") != state["nodeId"]
            or result.get("status")
            not in {"DATA_PLANE_INSTALLED", "DIRECT_CANARY_PASSED"}
        ):
            raise ProtocolError("the panel returned an invalid data-plane ACK")
        return result


def write_bootstrap_claim(client, output_path):
    """Persist one claimed credential without exposing it on stdout or argv."""
    output_path = pathlib.Path(output_path)
    parent = output_path.parent
    try:
        parent_metadata = parent.stat()
    except OSError as exc:
        raise ProtocolError("the bootstrap claim directory is unavailable") from exc
    if (
        parent.is_symlink()
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) & 0o077
        or output_path.exists()
        or output_path.is_symlink()
    ):
        raise ProtocolError("the bootstrap claim path is unsafe")
    result = client.claim()
    token = result["bootstrapToken"]
    descriptor = None
    staged_name = None
    try:
        descriptor, staged_name = tempfile.mkstemp(prefix=".bootstrap-", dir=str(parent))
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(token.encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged_name, str(output_path))
        staged_name = None
        _fsync_directory(parent)
    except OSError as exc:
        raise ProtocolError("cannot persist the bootstrap claim") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if staged_name is not None:
            try:
                os.unlink(staged_name)
            except FileNotFoundError:
                pass


def _write_private_bundle_file(directory, name, value):
    if name not in {
        "server.crt",
        "server.key",
        "hysteria-main.yaml",
        "hysteria-udp443.yaml",
        "stats.env",
        "bootstrap.json",
    }:
        raise ProtocolError("data-plane bundle filename is invalid")
    descriptor = os.open(
        str(directory / name),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def prepare_data_plane_bundle(
    client,
    token,
    destination,
    architecture=None,
    secret_factory=secrets.token_urlsafe,
):
    """Atomically prepare a root-only bundle without persisting the grant token."""

    destination = pathlib.Path(destination)
    parent = destination.parent
    if (
        destination.exists()
        or destination.is_symlink()
        or not parent.is_dir()
        or parent.is_symlink()
    ):
        raise ProtocolError("data-plane bundle destination is unsafe")
    staged = pathlib.Path(
        tempfile.mkdtemp(prefix=".{}-".format(destination.name), dir=str(parent))
    )
    try:
        os.chmod(str(staged), 0o700)
        response = client.fetch(token)
        identity = validate_data_plane_identity(response, architecture)
        stats_secret = str(secret_factory(36))
        configs = render_data_plane_configs(identity, stats_secret)
        metadata = {
            "certificateFileSha256": identity["certificate_file_sha256"],
            "certificateDerSha256": identity["certificate_der_sha256"],
            "privateKeyPublicSha256": identity["private_key_public_sha256"],
            "hysteriaVersion": identity["hysteria_version"],
            "hysteriaSha256": identity["hysteria_sha256"],
            "egressPolicy": identity["egress_policy"],
            "mainPort": identity["main_port"],
            "configProtocolVersion": 1,
        }
        files = {
            "server.crt": identity["certificate"],
            "server.key": identity["private_key"],
            "hysteria-main.yaml": configs["main"].encode("utf-8"),
            "hysteria-udp443.yaml": configs["udp443"].encode("utf-8"),
            "stats.env": "HY2PANEL_STATS_SECRET={}\n".format(stats_secret).encode(
                "ascii"
            ),
            "bootstrap.json": json.dumps(
                metadata, sort_keys=True, separators=(",", ":")
            ).encode("ascii")
            + b"\n",
        }
        for name, value in files.items():
            _write_private_bundle_file(staged, name, value)
        _fsync_directory(staged)
        os.replace(str(staged), str(destination))
        _fsync_directory(parent)
        return destination
    except Exception as exc:
        shutil.rmtree(str(staged), ignore_errors=True)
        if isinstance(exc, ProtocolError):
            raise
        raise ProtocolError("data-plane bundle preparation failed") from exc


def _linux_memfd():
    if not hasattr(os, "memfd_create"):
        raise ProtocolError("anonymous Hysteria configuration is unavailable")
    try:
        return os.memfd_create("hy2panel-hysteria-config", flags=0)
    except OSError as exc:
        raise ProtocolError("anonymous Hysteria configuration is unavailable") from exc


def run_hysteria_from_template(
    binary,
    template_path,
    runtime_config_path,
    *,
    environment=None,
    execve=os.execve,
    memfd_factory=_linux_memfd,
    lstat=os.lstat,
    symlink=os.symlink,
    unlink=os.unlink,
):
    """Exec Hysteria with the stats secret substituted only in anonymous memory."""

    if str(binary) != "/opt/hysteria2-panel-node/bin/hysteria":
        raise ProtocolError("data-plane Hysteria binary path is invalid")
    runtime_config_path = pathlib.Path(runtime_config_path)
    allowed_runtime_paths = {
        pathlib.Path("/run/hysteria2-panel-node-main/config.yaml"),
        pathlib.Path("/run/hysteria2-panel-node-udp443/config.yaml"),
    }
    if runtime_config_path not in allowed_runtime_paths:
        raise ProtocolError("runtime Hysteria configuration path is invalid")
    try:
        runtime_directory = lstat(runtime_config_path.parent)
    except OSError as exc:
        raise ProtocolError("runtime Hysteria configuration directory is unavailable") from exc
    if (
        not stat.S_ISDIR(runtime_directory.st_mode)
        or runtime_directory.st_uid != 0
        or stat.S_IMODE(runtime_directory.st_mode) != 0o700
    ):
        raise ProtocolError("runtime Hysteria configuration directory is unsafe")
    try:
        lstat(runtime_config_path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ProtocolError("runtime Hysteria configuration path is unavailable") from exc
    else:
        raise ProtocolError("runtime Hysteria configuration path is already occupied")
    environment = dict(os.environ if environment is None else environment)
    secret = environment.pop("HY2PANEL_STATS_SECRET", "")
    if not isinstance(secret, str) or TOKEN_PATTERN.fullmatch(secret) is None:
        raise ProtocolError("local traffic stats secret is invalid")
    template_path = pathlib.Path(template_path)
    try:
        descriptor = os.open(str(template_path), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 64 * 1024:
                raise ProtocolError("Hysteria configuration template is invalid")
            template = os.read(descriptor, 64 * 1024 + 1)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ProtocolError("Hysteria configuration template is unavailable") from exc
    placeholder = b"__HY2PANEL_STATS_SECRET__"
    if len(template) > 64 * 1024 or template.count(placeholder) != 1:
        raise ProtocolError("Hysteria configuration template is invalid")
    try:
        rendered = template.replace(placeholder, secret.encode("ascii"))
    except UnicodeError as exc:
        raise ProtocolError("local traffic stats secret is invalid") from exc
    anonymous = memfd_factory()
    runtime_link_created = False
    try:
        if not isinstance(anonymous, int) or anonymous < 0:
            raise ProtocolError("anonymous Hysteria configuration is unavailable")
        os.set_inheritable(anonymous, True)
        offset = 0
        while offset < len(rendered):
            written = os.write(anonymous, rendered[offset:])
            if written <= 0:
                raise OSError("short anonymous configuration write")
            offset += written
        os.lseek(anonymous, 0, os.SEEK_SET)
        anonymous_path = "/proc/self/fd/{}".format(anonymous)
        symlink(anonymous_path, runtime_config_path)
        runtime_link_created = True
        runtime_link = lstat(runtime_config_path)
        if not stat.S_ISLNK(runtime_link.st_mode) or runtime_link.st_uid != 0:
            raise ProtocolError("runtime Hysteria configuration link is unsafe")
        arguments = [str(binary), "server", "-c", str(runtime_config_path)]
        execve(str(binary), arguments, environment)
        raise ProtocolError("Hysteria execution returned unexpectedly")
    except OSError as exc:
        raise ProtocolError("cannot execute the data-plane Hysteria service") from exc
    finally:
        if runtime_link_created:
            try:
                unlink(runtime_config_path)
            except OSError:
                pass
        if isinstance(anonymous, int) and anonymous >= 0:
            try:
                os.close(anonymous)
            except OSError:
                pass


def _read_private_regular_file(path, maximum):
    try:
        descriptor = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size < 1
                or metadata.st_size > maximum
            ):
                raise ProtocolError("data-plane identity file is unsafe")
            value = os.read(descriptor, maximum + 1)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ProtocolError("data-plane identity file is unavailable") from exc
    if len(value) > maximum:
        raise ProtocolError("data-plane identity file is unsafe")
    return value


def _systemd_service_active(unit):
    if unit not in {
        "hysteria2-panel-node-auth.service",
        "hysteria2-panel-node-control.service",
        "hysteria2-panel-node-hysteria-main.service",
        "hysteria2-panel-node-hysteria-udp443.service",
        "hysteria2-panel-node-tcp-probe-main.service",
        "hysteria2-panel-node-tcp-probe-udp443.service",
    }:
        return False
    try:
        completed = subprocess.run(  # nosec B603 -- fixed executable and unit allowlist.
            ["/bin/systemctl", "is-active", "--quiet", unit],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


DATA_PLANE_UNITS = (
    "hysteria2-panel-node-hysteria-main.service",
    "hysteria2-panel-node-hysteria-udp443.service",
    "hysteria2-panel-node-tcp-probe-main.service",
    "hysteria2-panel-node-tcp-probe-udp443.service",
)


def _set_fixed_data_plane_running(running):
    if not isinstance(running, bool):
        raise ProtocolError("data-plane action is invalid")
    environment = os.environ.copy()
    for name in ("NOTIFY_SOCKET", "WATCHDOG_PID", "WATCHDOG_USEC"):
        environment.pop(name, None)
    action = "start" if running else "stop"
    try:
        completed = subprocess.run(  # nosec B603 -- fixed executable and unit allowlist.
            ["/bin/systemctl", action] + list(DATA_PLANE_UNITS),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProtocolError("fixed data-plane action failed") from exc
    if completed.returncode != 0:
        raise ProtocolError("fixed data-plane action failed")
    states = [_systemd_service_active(unit) for unit in DATA_PLANE_UNITS]
    if (running and not all(states)) or (not running and any(states)):
        raise ProtocolError("fixed data-plane state did not converge")


def stop_node_data_plane():
    _set_fixed_data_plane_running(False)


def start_node_data_plane():
    _set_fixed_data_plane_running(True)


def _socket_is_listening(kind, port):
    if kind not in {"tcp", "udp"} or port not in {443, 19999}:
        return False
    flag = "-ltn" if kind == "tcp" else "-lun"
    try:
        completed = subprocess.run(  # nosec B603 -- fixed executable and argv.
            ["/usr/bin/ss", "-H", flag, "sport", "=", ":{}".format(port)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _stats_endpoint_healthy(url, secret):
    try:
        return isinstance(LocalStatsClient(url, secret).online(), dict)
    except (OSError, ProtocolError, ValueError):
        return False


def collect_data_plane_attestation(
    metadata_path,
    certificate_path,
    private_key_path,
    stats_secret,
    *,
    service_checker=_systemd_service_active,
    listener_checker=_socket_is_listening,
    stats_checker=_stats_endpoint_healthy,
):
    """Recompute local identity and require every fixed health signal."""

    if not isinstance(stats_secret, str) or TOKEN_PATTERN.fullmatch(stats_secret) is None:
        raise ProtocolError("local traffic stats secret is invalid")
    try:
        metadata = json.loads(
            _read_private_regular_file(metadata_path, 8 * 1024).decode("ascii")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("data-plane metadata is invalid") from exc
    expected_fields = {
        "certificateFileSha256",
        "certificateDerSha256",
        "privateKeyPublicSha256",
        "hysteriaVersion",
        "hysteriaSha256",
        "egressPolicy",
        "mainPort",
        "configProtocolVersion",
    }
    if (
        not isinstance(metadata, dict)
        or set(metadata) != expected_fields
        or metadata.get("hysteriaVersion") != "2.12.1"
        or metadata.get("configProtocolVersion") != 1
        or metadata.get("egressPolicy") not in {"web", "full"}
        or isinstance(metadata.get("mainPort"), bool)
        or not isinstance(metadata.get("mainPort"), int)
        or not 1 <= metadata["mainPort"] <= 65535
        or metadata["mainPort"] in {443, 19995, 19996, 19997}
        or any(
            not isinstance(metadata.get(field), str)
            or re.fullmatch(r"[0-9a-f]{64}", metadata[field]) is None
            for field in (
                "certificateFileSha256",
                "certificateDerSha256",
                "privateKeyPublicSha256",
                "hysteriaSha256",
            )
        )
    ):
        raise ProtocolError("data-plane metadata is invalid")
    certificate = _read_private_regular_file(certificate_path, 16 * 1024)
    private_key = _read_private_regular_file(private_key_path, 16 * 1024)
    response = {
        "grantId": "0" * 32,
        "expiresAt": 1,
        "fetchAttempt": 1,
        "maxFetchAttempts": 3,
        "configProtocolVersion": 1,
        "hysteriaVersion": metadata["hysteriaVersion"],
        "hysteriaSha256": {
            "amd64": metadata["hysteriaSha256"],
            "arm64": metadata["hysteriaSha256"],
        },
        "ports": {"main": metadata["mainPort"], "udp443": 443},
        "certificatePem": certificate.decode("ascii"),
        "privateKeyPem": private_key.decode("ascii"),
        "certificateFileSha256": metadata["certificateFileSha256"],
        "certificateDerSha256": metadata["certificateDerSha256"],
        "privateKeyPublicSha256": metadata["privateKeyPublicSha256"],
        "egressPolicy": metadata["egressPolicy"],
    }
    identity = validate_data_plane_identity(response, "amd64")
    units = (
        "hysteria2-panel-node-auth.service",
        "hysteria2-panel-node-control.service",
        "hysteria2-panel-node-hysteria-main.service",
        "hysteria2-panel-node-hysteria-udp443.service",
        "hysteria2-panel-node-tcp-probe-main.service",
        "hysteria2-panel-node-tcp-probe-udp443.service",
    )
    services_healthy = all(service_checker(unit) is True for unit in units)
    stats_healthy = all(
        stats_checker(url, stats_secret) is True
        for url in ("http://127.0.0.1:19997", "http://127.0.0.1:19995")
    )
    listener_results = {
        "udp19999Listening": listener_checker("udp", metadata["mainPort"]) is True,
        "udp443Listening": listener_checker("udp", 443) is True,
        "tcp19999Listening": listener_checker("tcp", metadata["mainPort"]) is True,
        "tcp443Listening": listener_checker("tcp", 443) is True,
    }
    if not services_healthy or not stats_healthy or not all(listener_results.values()):
        raise ProtocolError("data-plane health attestation failed")
    attestation = {
        "certificateFileSha256": identity["certificate_file_sha256"],
        "certificateDerSha256": identity["certificate_der_sha256"],
        "privateKeyPublicSha256": identity["private_key_public_sha256"],
        "hysteriaVersion": identity["hysteria_version"],
        "egressPolicy": metadata["egressPolicy"],
        "configProtocolVersion": 1,
        "servicesHealthy": True,
        "statsHealthy": True,
    }
    attestation.update(listener_results)
    return attestation


class NodeProtocolClient:
    """Sign bounded node protocol requests using the enrolled Ed25519 key."""

    PATHS = {
        "auth": ("/api/v1/node-auth-decisions", 16 * 1024),
        "online": ("/api/v1/node-online-snapshots", 8 * 1024),
        "traffic": ("/api/v1/node-traffic-batches", 8 * 1024),
        "control-cycle": ("/api/v1/node-control-cycles", 128 * 1024),
        "command-poll": ("/api/v1/node-commands/poll", 64 * 1024),
        "command-ack": ("/api/v1/node-commands/ack", 8 * 1024),
    }

    def __init__(
        self,
        state_path,
        private_key_path,
        opener=urllib.request.urlopen,
        signer=_openssl_sign,
        clock=time.time,
        nonce_factory=None,
    ):
        self.state_path = pathlib.Path(state_path)
        self.private_key_path = pathlib.Path(private_key_path)
        self.opener = opener
        self.signer = signer
        self.clock = clock
        self.nonce_factory = nonce_factory or secrets.token_urlsafe

    def _post(self, purpose, fields):
        state = _registration_state(self.state_path)
        nonce = str(self.nonce_factory(32))
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", nonce):
            raise ProtocolError("secure node request nonce generation failed")
        payload = {
            "nodeId": state["nodeId"],
            "sentAt": int(self.clock()),
            "nonce": nonce,
        }
        payload.update(fields)
        signature = self.signer(
            self.private_key_path, _canonical_node_request(purpose, payload)
        )
        if not isinstance(signature, bytes) or len(signature) != 64:
            raise ProtocolError("cannot sign the node request")
        payload["signature"] = base64.b64encode(signature).decode("ascii")
        path, maximum = self.PATHS[purpose]
        request = urllib.request.Request(
            state["panelUrl"] + path,
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            ),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(
                request, timeout=NODE_PROTOCOL_REQUEST_TIMEOUT_SECONDS
            ) as response:
                status = getattr(
                    response,
                    "status",
                    response.getcode() if hasattr(response, "getcode") else 0,
                )
                body = response.read(maximum + 1)
        except urllib.error.HTTPError as exc:
            if purpose == "control-cycle" and exc.code == 404:
                raise ProtocolNotSupported(
                    "the panel does not support combined node control cycles"
                ) from exc
            raise ProtocolError("the panel rejected or could not receive the node request") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ProtocolError("the panel rejected or could not receive the node request") from exc
        if status != 200 or len(body) > maximum:
            raise ProtocolError("the panel returned an invalid node response")
        try:
            result = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError("the panel returned an invalid node response") from exc
        if not isinstance(result, dict):
            raise ProtocolError("the panel returned an invalid node response")
        return result

    def authorize(self, request):
        if not isinstance(request, dict) or set(request) != {"entrypoint", "auth", "tx"}:
            raise ProtocolError("local authentication request is invalid")
        result = self._post(
            "auth",
            {
                "requestId": uuid.uuid4().hex,
                "entrypoint": request["entrypoint"],
                "auth": request["auth"],
                "tx": request["tx"],
            },
        )
        if (
            set(result) != {"ok", "id", "decisionId", "expiresAt"}
            or not isinstance(result.get("ok"), bool)
            or not isinstance(result.get("id"), str)
            or not NODE_ID_PATTERN.fullmatch(str(result.get("decisionId", "")))
            or isinstance(result.get("expiresAt"), bool)
            or not isinstance(result.get("expiresAt"), int)
        ):
            raise ProtocolError("the panel returned an invalid authorization decision")
        return result

    def send_online(self, sequence, online, traffic_acked_at):
        return self._post(
            "online",
            {
                "snapshotId": uuid.uuid4().hex,
                "sequence": int(sequence),
                "observedAt": int(self.clock()),
                "trafficAckedAt": int(traffic_acked_at),
                "online": online,
            },
        )

    def send_traffic(self, batch):
        if not isinstance(batch, dict) or set(batch) != {"batchId", "observedAt", "traffic"}:
            raise ProtocolError("traffic batch is invalid")
        return self._post("traffic", batch)

    def send_control_cycle(self, traffic_batches, online_snapshot):
        if (
            not isinstance(traffic_batches, list)
            or len(traffic_batches) > 8
            or any(
                not isinstance(batch, dict)
                or set(batch) != {"batchId", "observedAt", "traffic"}
                for batch in traffic_batches
            )
            or (
                online_snapshot is not None
                and (
                    not isinstance(online_snapshot, dict)
                    or set(online_snapshot)
                    != {
                        "snapshotId",
                        "sequence",
                        "observedAt",
                        "trafficAckedAt",
                        "online",
                    }
                )
            )
        ):
            raise ProtocolError("combined node control cycle is invalid")
        cycle_id = uuid.uuid4().hex
        result = self._post(
            "control-cycle",
            {
                "cycleId": cycle_id,
                "trafficBatches": traffic_batches,
                "onlineSnapshot": online_snapshot,
                "commandPoll": {"requestId": uuid.uuid4().hex},
            },
        )
        expected_fields = {
            "cycleId",
            "acceptedAt",
            "traffic",
            "online",
            "commands",
            "polledAt",
        }
        traffic_results = result.get("traffic")
        commands = result.get("commands")
        online_result = result.get("online")
        if (
            set(result) != expected_fields
            or result.get("cycleId") != cycle_id
            or isinstance(result.get("acceptedAt"), bool)
            or not isinstance(result.get("acceptedAt"), int)
            or not isinstance(traffic_results, list)
            or len(traffic_results) != len(traffic_batches)
            or not isinstance(commands, list)
            or len(commands) > 32
            or isinstance(result.get("polledAt"), bool)
            or not isinstance(result.get("polledAt"), int)
        ):
            raise ProtocolError("the panel returned an invalid combined control cycle")
        for batch, acknowledgement in zip(traffic_batches, traffic_results):
            if (
                not isinstance(acknowledgement, dict)
                or acknowledgement.get("batchId") != batch["batchId"]
                or acknowledgement.get("committed") is not True
            ):
                raise ProtocolError("central traffic ACK is invalid")
        if online_snapshot is None:
            if online_result is not None:
                raise ProtocolError("central online snapshot ACK is invalid")
        elif (
            not isinstance(online_result, dict)
            or online_result.get("snapshotId") != online_snapshot["snapshotId"]
            or online_result.get("sequence") != online_snapshot["sequence"]
        ):
            raise ProtocolError("central online snapshot ACK is invalid")
        return result

    def poll_commands(self):
        result = self._post("command-poll", {"requestId": uuid.uuid4().hex})
        if (
            set(result) != {"commands", "polledAt"}
            or not isinstance(result.get("commands"), list)
            or len(result["commands"]) > 32
        ):
            raise ProtocolError("the panel returned invalid node commands")
        return result["commands"]

    def ack_command(self, command_id, ok, error_code=""):
        return self._post(
            "command-ack",
            {
                "commandId": command_id,
                "ok": bool(ok),
                "errorCode": str(error_code),
            },
        )


class LocalStatsClient:
    """Bounded client for a loopback-only Hysteria Traffic Stats API."""

    def __init__(self, base_url, secret, opener=urllib.request.urlopen):
        parsed = urllib.parse.urlsplit(str(base_url or ""))
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("traffic stats URL must be loopback HTTP")
        try:
            if parsed.port is None:
                raise ValueError
        except ValueError as exc:
            raise ValueError("traffic stats URL requires a valid port") from exc
        if not isinstance(secret, str) or not 16 <= len(secret) <= 512:
            raise ValueError("traffic stats secret is invalid")
        self.base_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        self.secret = secret
        self.opener = opener

    def _request(self, path, payload=None):
        if path not in {"/online", "/traffic?clear=1", "/kick"}:
            raise ProtocolError("traffic stats path is invalid")
        data = None
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Authorization": self.secret, "Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        try:
            with self.opener(request, timeout=5) as response:
                status = getattr(
                    response,
                    "status",
                    response.getcode() if hasattr(response, "getcode") else 0,
                )
                body = response.read(LOCAL_TRAFFIC_RESPONSE_MAX_BYTES + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            raise ProtocolError("local traffic stats request failed") from exc
        if status != 200 or len(body) > LOCAL_TRAFFIC_RESPONSE_MAX_BYTES:
            raise ProtocolError("local traffic stats response is invalid")
        if path == "/kick":
            return None
        try:
            result = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError("local traffic stats response is invalid") from exc
        return result

    def online(self):
        result = self._request("/online")
        if not isinstance(result, dict) or not all(
            isinstance(name, str)
            and not isinstance(count, bool)
            and isinstance(count, int)
            and count >= 0
            for name, count in result.items()
        ):
            raise ProtocolError("local online response is invalid")
        return result

    def collect_and_clear(self):
        result = self._request("/traffic?clear=1")
        DurableTrafficSpool._validate_traffic(result)
        return result

    def kick(self, users):
        users = list(users)
        if not users or len(users) > 100 or not all(
            isinstance(user, str) and 1 <= len(user) <= 64 for user in users
        ):
            raise ProtocolError("kick user list is invalid")
        self._request("/kick", users)


class CombinedLocalStatsClient:
    """Treat the fixed main and UDP-443 stats APIs as one local data plane."""

    def __init__(self, primary, secondary):
        self.clients = (primary, secondary)

    def online(self):
        combined = {}
        for client in self.clients:
            current = client.online()
            if not isinstance(current, dict):
                raise ProtocolError("local online response is invalid")
            for name, count in current.items():
                value = combined.get(name, 0) + count
                if value > 2**63 - 1:
                    raise ProtocolError("local online response is invalid")
                combined[name] = value
        return combined

    def collect_and_clear_batches(self):
        collected = []
        failure = None
        for client in self.clients:
            try:
                current = client.collect_and_clear()
                DurableTrafficSpool._validate_traffic(current)
                if current:
                    collected.append(current)
            except Exception as exc:
                if failure is None:
                    failure = exc
        if failure is not None:
            raise PartialLocalTrafficCollectionError(collected) from failure
        return collected or [{}]

    def collect_and_clear(self):
        combined = {}
        for current in self.collect_and_clear_batches():
            for name, counters in current.items():
                target = combined.setdefault(name, {"tx": 0, "rx": 0})
                for field in ("tx", "rx"):
                    value = target[field] + counters[field]
                    if value > 2**63 - 1:
                        raise ProtocolError("traffic batch is invalid")
                    target[field] = value
        DurableTrafficSpool._validate_traffic(combined)
        return combined

    def kick(self, users):
        error = None
        for client in self.clients:
            try:
                client.kick(users)
            except Exception as exc:
                error = exc
        if error is not None:
            raise ProtocolError("local traffic stats request failed") from error


def execute_control_command(
    command,
    stats_client,
    refresh_snapshot=None,
    flush_traffic=None,
    protocol_state=None,
    stop_data_plane=None,
    start_data_plane=None,
):
    """Execute one fixed command without exposing a generic execution surface."""
    if not isinstance(command, dict) or set(command) != {"commandId", "kind", "payload"}:
        raise ProtocolError("node command is invalid")
    if not NODE_ID_PATTERN.fullmatch(str(command["commandId"])):
        raise ProtocolError("node command is invalid")
    kind = command["kind"]
    payload = command["payload"]
    if kind == "KICK_USERS" and isinstance(payload, dict) and set(payload) == {"users"}:
        stats_client.kick(payload["users"])
        return
    if kind == "REFRESH_SNAPSHOT" and payload == {}:
        if refresh_snapshot is None:
            raise ProtocolError("snapshot refresh callback is unavailable")
        refresh_snapshot()
        return
    if kind == "FLUSH_TRAFFIC" and payload == {}:
        if flush_traffic is None:
            raise ProtocolError("durable traffic flush callback is unavailable")
        flush_traffic()
        return
    if kind == "STOP_DATA_PLANE" and payload == {}:
        if protocol_state is None or flush_traffic is None or stop_data_plane is None:
            raise ProtocolError("data-plane stop callbacks are unavailable")
        if not protocol_state.data_plane_stopped():
            flush_traffic()
            protocol_state.set_data_plane_stopped(True)
        stop_data_plane()
        return
    if kind == "START_DATA_PLANE" and payload == {}:
        if protocol_state is None or start_data_plane is None:
            raise ProtocolError("data-plane start callbacks are unavailable")
        start_data_plane()
        protocol_state.set_data_plane_stopped(False)
        return
    raise ProtocolError("node command is invalid")


class ProtocolState:
    """Persist monotonic snapshot sequence and the last committed traffic ACK."""

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self._lock = threading.Lock()
        parent = self.path.parent
        if parent.exists() or parent.is_symlink():
            metadata = parent.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077
            ):
                raise ProtocolError("node protocol state directory is unsafe")
        else:
            parent.mkdir(parents=True, mode=0o700)
            parent.chmod(0o700)
            _fsync_directory(parent.parent)
        if self.path.exists() or self.path.is_symlink():
            self._read()
        else:
            self._write(
                {
                    "sequence": 0,
                    "trafficAckedAt": 0,
                    "completedCommands": [],
                    "dataPlaneStopped": False,
                }
            )

    def _read(self):
        data = _read_root_only_file(self.path, "protocol state")
        if len(data) > 4096:
            raise ProtocolError("node protocol state is invalid")
        try:
            state = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError("node protocol state is invalid") from exc
        if isinstance(state, dict) and set(state) == {"sequence", "trafficAckedAt"}:
            state["completedCommands"] = []
        if isinstance(state, dict) and set(state) == {
            "sequence",
            "trafficAckedAt",
            "completedCommands",
        }:
            state["dataPlaneStopped"] = False
        commands = state.get("completedCommands") if isinstance(state, dict) else None
        if (
            not isinstance(state, dict)
            or set(state)
            != {
                "sequence",
                "trafficAckedAt",
                "completedCommands",
                "dataPlaneStopped",
            }
            or any(
                isinstance(state[key], bool) or not isinstance(state[key], int)
                for key in ("sequence", "trafficAckedAt")
            )
            or state["sequence"] < 0
            or state["trafficAckedAt"] < 0
            or not isinstance(state["dataPlaneStopped"], bool)
            or not isinstance(commands, list)
            or len(commands) > 256
            or not all(
                isinstance(item, dict)
                and set(item) == {"commandId", "completedAt"}
                and NODE_ID_PATTERN.fullmatch(str(item["commandId"]))
                and not isinstance(item["completedAt"], bool)
                and isinstance(item["completedAt"], int)
                and item["completedAt"] >= 0
                for item in commands
            )
            or len({item["commandId"] for item in commands}) != len(commands)
        ):
            raise ProtocolError("node protocol state is invalid")
        return state

    def data_plane_stopped(self):
        with self._lock:
            return self._read()["dataPlaneStopped"]

    def set_data_plane_stopped(self, stopped):
        if not isinstance(stopped, bool):
            raise ProtocolError("data-plane state is invalid")
        with self._lock:
            state = self._read()
            state["dataPlaneStopped"] = stopped
            self._write(state)

    def _write(self, state):
        encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        descriptor, staged_name = tempfile.mkstemp(
            prefix=".protocol-state-", dir=str(self.path.parent)
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged_name, str(self.path))
            _fsync_directory(self.path.parent)
        finally:
            try:
                os.unlink(staged_name)
            except FileNotFoundError:
                pass

    def next_sequence(self):
        with self._lock:
            state = self._read()
            state["sequence"] += 1
            self._write(state)
            return state["sequence"]

    def set_traffic_ack(self, accepted_at):
        if isinstance(accepted_at, bool) or not isinstance(accepted_at, int):
            raise ProtocolError("traffic ACK time is invalid")
        with self._lock:
            state = self._read()
            state["trafficAckedAt"] = max(state["trafficAckedAt"], accepted_at)
            self._write(state)

    def traffic_acked_at(self):
        with self._lock:
            return self._read()["trafficAckedAt"]

    def command_completed(self, command_id):
        if not NODE_ID_PATTERN.fullmatch(str(command_id or "")):
            raise ProtocolError("node command id is invalid")
        with self._lock:
            return any(
                item["commandId"] == command_id
                for item in self._read()["completedCommands"]
            )

    def record_command_completed(self, command_id, completed_at):
        if (
            not NODE_ID_PATTERN.fullmatch(str(command_id or ""))
            or isinstance(completed_at, bool)
            or not isinstance(completed_at, int)
            or completed_at < 0
        ):
            raise ProtocolError("completed node command is invalid")
        with self._lock:
            state = self._read()
            if not any(
                item["commandId"] == command_id
                for item in state["completedCommands"]
            ):
                state["completedCommands"].append(
                    {"commandId": command_id, "completedAt": completed_at}
                )
                state["completedCommands"] = state["completedCommands"][-256:]
                self._write(state)


class NodeControlCycle:
    """One crash-safe traffic, snapshot and fixed-command control cycle."""

    def __init__(
        self,
        protocol_client,
        stats_client,
        spool,
        state,
        clock=time.time,
        stop_data_plane=stop_node_data_plane,
        start_data_plane=start_node_data_plane,
    ):
        self.protocol_client = protocol_client
        self.stats_client = stats_client
        self.spool = spool
        self.state = state
        self.clock = clock
        self.stop_data_plane = stop_data_plane
        self.start_data_plane = start_data_plane
        self._combined_supported = hasattr(protocol_client, "send_control_cycle")

    def _upload_pending(self):
        last_ack = None
        for batch in self.spool.pending():
            result = self.protocol_client.send_traffic(batch)
            if (
                not isinstance(result, dict)
                or result.get("batchId") != batch["batchId"]
                or result.get("committed") is not True
            ):
                raise ProtocolError("central traffic ACK is invalid")
            self.spool.ack(batch["batchId"])
            last_ack = int(self.clock())
            self.state.set_traffic_ack(last_ack)
        return last_ack

    def _collection_capacity(self):
        clients = getattr(self.stats_client, "clients", ())
        endpoint_count = max(1, len(clients))
        return endpoint_count * LOCAL_TRAFFIC_RESPONSE_MAX_BYTES

    def _can_collect(self):
        return self.spool.can_collect(self._collection_capacity())

    def _collect_to_spool(self):
        observed_at = int(self.clock())
        try:
            if hasattr(self.stats_client, "collect_and_clear_batches"):
                batches = self.stats_client.collect_and_clear_batches()
            else:
                batches = [self.stats_client.collect_and_clear()]
        except PartialLocalTrafficCollectionError as exc:
            self.spool.enqueue_collections(exc.batches, observed_at=observed_at)
            raise
        self.spool.enqueue_collections(batches, observed_at=observed_at)

    def flush_traffic(self):
        if not self._can_collect():
            self._upload_pending()
            if not self._can_collect():
                raise ProtocolError("traffic spool has insufficient capacity")
        self._collect_to_spool()
        return self._upload_pending()

    def refresh_snapshot(self):
        traffic_acked_at = self.state.traffic_acked_at()
        if int(self.clock()) - traffic_acked_at > MAX_STATE_AGE_SECONDS:
            raise ProtocolError("traffic checkpoint is stale")
        result = self.protocol_client.send_online(
            self.state.next_sequence(),
            self.stats_client.online(),
            traffic_acked_at,
        )
        if not isinstance(result, dict) or not isinstance(result.get("sequence"), int):
            raise ProtocolError("central online snapshot ACK is invalid")
        return result

    def _run_combined(self, stopped):
        snapshot = None
        selected = []
        if not stopped:
            if self._can_collect():
                self._collect_to_spool()
            pending = self.spool.pending()
            for batch in pending[:8]:
                candidate = selected + [batch]
                encoded_size = len(
                    json.dumps(
                        {"trafficBatches": candidate, "onlineSnapshot": None},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                if encoded_size > CONTROL_CYCLE_PAYLOAD_BUDGET_BYTES:
                    break
                selected = candidate
            if len(selected) == len(pending):
                snapshot = {
                    "snapshotId": uuid.uuid4().hex,
                    "sequence": self.state.next_sequence(),
                    "observedAt": int(self.clock()),
                    "trafficAckedAt": self.state.traffic_acked_at(),
                    "online": self.stats_client.online(),
                }
                encoded_size = len(
                    json.dumps(
                        {
                            "trafficBatches": selected,
                            "onlineSnapshot": snapshot,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                if encoded_size > CONTROL_CYCLE_PAYLOAD_BUDGET_BYTES:
                    snapshot = None
        result = self.protocol_client.send_control_cycle(selected, snapshot)
        for batch, acknowledgement in zip(selected, result["traffic"]):
            if (
                acknowledgement.get("batchId") != batch["batchId"]
                or acknowledgement.get("committed") is not True
            ):
                raise ProtocolError("central traffic ACK is invalid")
            self.spool.ack(batch["batchId"])
        if selected:
            self.state.set_traffic_ack(int(result["acceptedAt"]))
        if snapshot is not None and (
            not isinstance(result.get("online"), dict)
            or result["online"].get("sequence") != snapshot["sequence"]
        ):
            raise ProtocolError("central online snapshot ACK is invalid")
        return result["commands"]

    def _legacy_control(self, stopped, collect=True):
        control_error = None
        if not stopped:
            try:
                if collect:
                    self.flush_traffic()
                else:
                    self._upload_pending()
                self.refresh_snapshot()
            except (OSError, ProtocolError) as exc:
                control_error = exc
        try:
            commands = self.protocol_client.poll_commands()
        except (OSError, ProtocolError):
            if control_error is not None:
                raise control_error
            raise
        return commands, control_error

    def run_once(self):
        stopped = self.state.data_plane_stopped()
        control_error = None
        commands = None
        legacy_collect = True
        if self._combined_supported:
            try:
                commands = self._run_combined(stopped)
            except ProtocolNotSupported:
                self._combined_supported = False
                legacy_collect = False
            except (OSError, ProtocolError) as exc:
                control_error = exc
                try:
                    commands = self.protocol_client.poll_commands()
                except (OSError, ProtocolError):
                    raise control_error
        if commands is None:
            commands, control_error = self._legacy_control(
                stopped, collect=legacy_collect
            )
        for command in commands:
            command_id = command.get("commandId", "")
            if self.state.command_completed(command_id):
                self.protocol_client.ack_command(command_id, True, "")
                continue
            try:
                execute_control_command(
                    command,
                    self.stats_client,
                    refresh_snapshot=self.refresh_snapshot,
                    flush_traffic=self.flush_traffic,
                    protocol_state=self.state,
                    stop_data_plane=self.stop_data_plane,
                    start_data_plane=self.start_data_plane,
                )
            except Exception:
                self.protocol_client.ack_command(
                    command_id, False, "EXECUTION_FAILED"
                )
                continue
            self.state.record_command_completed(command_id, int(self.clock()))
            self.protocol_client.ack_command(command_id, True, "")
        if control_error is not None:
            raise control_error


class NodeRuntimeMetrics:
    """Atomically publish low-cardinality Prometheus textfile metrics."""

    def __init__(self, path, spool=None, clock=time.time):
        self.path = pathlib.Path(path)
        self.spool = spool
        self.clock = clock
        self.cycles_total = 0
        self.failures_total = 0
        self.consecutive_failures = 0
        self.last_success = 0

    def record_cycle(self, failed):
        self.cycles_total += 1
        if failed:
            self.failures_total += 1
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0
            self.last_success = int(self.clock())
        spool_entries = 0
        spool_bytes = 0
        if self.spool is not None:
            try:
                spool_entries, spool_bytes = self.spool._current_usage()
            except (OSError, ProtocolError):
                pass
        body = (
            "# HELP hy2panel_node_control_ready Whether the node control loop has started.\n"
            "# TYPE hy2panel_node_control_ready gauge\n"
            "hy2panel_node_control_ready 1\n"
            "# TYPE hy2panel_node_control_cycles_total counter\n"
            "hy2panel_node_control_cycles_total {}\n"
            "# TYPE hy2panel_node_control_failures_total counter\n"
            "hy2panel_node_control_failures_total {}\n"
            "# TYPE hy2panel_node_control_consecutive_failures gauge\n"
            "hy2panel_node_control_consecutive_failures {}\n"
            "# TYPE hy2panel_node_control_last_success_timestamp_seconds gauge\n"
            "hy2panel_node_control_last_success_timestamp_seconds {}\n"
            "# TYPE hy2panel_node_traffic_spool_entries gauge\n"
            "hy2panel_node_traffic_spool_entries {}\n"
            "# TYPE hy2panel_node_traffic_spool_bytes gauge\n"
            "hy2panel_node_traffic_spool_bytes {}\n"
        ).format(
            self.cycles_total,
            self.failures_total,
            self.consecutive_failures,
            self.last_success,
            spool_entries,
            spool_bytes,
        ).encode("ascii")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, staged_name = tempfile.mkstemp(
            prefix=".node-metrics-", dir=str(self.path.parent)
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged_name, str(self.path))
            _fsync_directory(self.path.parent)
        finally:
            try:
                os.unlink(staged_name)
            except FileNotFoundError:
                pass


def run_control_loop(
    cycle,
    stop_event,
    interval_seconds=CONTROL_LOOP_INTERVAL_SECONDS,
    maximum_backoff_seconds=CONTROL_LOOP_MAX_BACKOFF_SECONDS,
    sleeper=None,
    jitter_source=None,
    notifier=None,
    metrics=None,
):
    """Run short jittered polling while backing off boundedly on failures."""
    interval = max(1, min(CONTROL_LOOP_MAX_INTERVAL_SECONDS, int(interval_seconds)))
    maximum_backoff = max(interval, min(300, int(maximum_backoff_seconds)))
    if jitter_source is None:
        random_source = secrets.SystemRandom()
        jitter_source = random_source.random
    delay = interval
    notifier = notifier or SystemdNotifier()
    notifier.ready("node control loop ready")
    try:
        while not stop_event.is_set():
            failed = False
            try:
                cycle.run_once()
            except (OSError, ProtocolError):
                failed = True
                next_delay = min(maximum_backoff, delay * 2)
            else:
                next_delay = interval
                delay = interval
            if metrics is not None:
                try:
                    metrics.record_cycle(failed=failed)
                except (OSError, ProtocolError):
                    pass
            notifier.watchdog()
            jitter = 0.8 + 0.4 * max(0.0, min(1.0, float(jitter_source())))
            wait_delay = min(float(maximum_backoff), max(1.0, delay * jitter))
            if sleeper is None:
                remaining = wait_delay
                notify_interval = notifier.watchdog_interval or remaining
                while remaining > 0 and not stop_event.is_set():
                    started = time.monotonic()
                    stop_event.wait(min(remaining, notify_interval))
                    remaining -= max(0.0, time.monotonic() - started)
                    notifier.watchdog()
            else:
                sleeper(wait_delay)
            delay = next_delay
    finally:
        notifier.stopping("node control loop stopping")


def _parser():
    parser = argparse.ArgumentParser(description="Hysteria2-panel node enrollment agent")
    subcommands = parser.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("register")
    command.add_argument("--panel-url", required=True)
    command.add_argument("--public-key", required=True)
    command.add_argument("--state-file", required=True)
    command = subcommands.add_parser("heartbeat")
    command.add_argument("--private-key", required=True)
    command.add_argument("--state-file", required=True)
    command = subcommands.add_parser("serve-auth-proxy")
    command.add_argument("--private-key", required=True)
    command.add_argument("--state-file", required=True)
    command.add_argument("--port", type=int, default=19996)
    command.add_argument("--metrics-file")
    command = subcommands.add_parser("prepare-data-plane")
    command.add_argument("--private-key", required=True)
    command.add_argument("--state-file", required=True)
    command.add_argument("--output-dir", required=True)
    command = subcommands.add_parser("claim-data-plane")
    command.add_argument("--private-key", required=True)
    command.add_argument("--state-file", required=True)
    command.add_argument("--output-token", required=True)
    command = subcommands.add_parser("run-hysteria")
    command.add_argument("--template", required=True)
    command.add_argument("--runtime-config", required=True)
    command = subcommands.add_parser("ack-data-plane")
    command.add_argument("--private-key", required=True)
    command.add_argument("--state-file", required=True)
    command.add_argument("--metadata", required=True)
    command.add_argument("--certificate", required=True)
    command.add_argument("--hysteria-key", required=True)
    for name in ("control-once", "control-loop"):
        command = subcommands.add_parser(name)
        command.add_argument("--private-key", required=True)
        command.add_argument("--state-file", required=True)
        command.add_argument("--protocol-state", required=True)
        command.add_argument("--spool-dir", required=True)
        command.add_argument("--stats-url", required=True, action="append")
        command.add_argument("--metrics-file")
    return parser


def _make_control_cycle(options):
    secret = os.environ.pop("HY2PANEL_STATS_SECRET", "")
    if not secret:
        raise ValueError("local traffic stats secret is unavailable")
    protocol_client = NodeProtocolClient(
        pathlib.Path(options.state_file), pathlib.Path(options.private_key)
    )
    stats_urls = options.stats_url
    if isinstance(stats_urls, str):
        stats_urls = [stats_urls]
    if not isinstance(stats_urls, list) or len(stats_urls) not in {1, 2}:
        raise ValueError("one or two traffic stats URLs are required")
    stats_clients = [LocalStatsClient(url, secret) for url in stats_urls]
    stats_client = stats_clients[0]
    if len(stats_clients) == 2:
        stats_client = CombinedLocalStatsClient(*stats_clients)
    spool = DurableTrafficSpool(pathlib.Path(options.spool_dir))
    state = ProtocolState(pathlib.Path(options.protocol_state))
    return NodeControlCycle(protocol_client, stats_client, spool, state)


def main(arguments=None):
    try:
        options = _parser().parse_args(arguments)
    except SystemExit as exc:
        return int(exc.code)
    if options.command == "register":
        token = os.environ.pop("HY2PANEL_ENROLLMENT_TOKEN", "")
        if not token:
            print("错误：缺少一次性节点对接凭据", file=sys.stderr)
            return 2
        try:
            result = register(
                panel_url=options.panel_url,
                token=token,
                public_key_path=options.public_key,
                state_path=options.state_file,
            )
        except (RegistrationError, ValueError) as exc:
            print("错误：{}".format(exc), file=sys.stderr)
            return 1
        print("节点 {} 已注册，状态：待验证".format(result["nodeId"]))
        return 0
    if options.command == "prepare-data-plane":
        token = os.environ.pop("HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN", "")
        if not token:
            print("错误：缺少一次性数据面部署凭据", file=sys.stderr)
            return 2
        try:
            client = DataPlaneBootstrapClient(
                pathlib.Path(options.state_file), pathlib.Path(options.private_key)
            )
            prepare_data_plane_bundle(client, token, pathlib.Path(options.output_dir))
        except (OSError, ProtocolError, ValueError) as exc:
            print("错误：{}".format(exc), file=sys.stderr)
            return 1
        finally:
            del token
        print("数据面身份与配置已验证并准备完成")
        return 0
    if options.command == "claim-data-plane":
        try:
            heartbeat(
                state_path=options.state_file,
                private_key_path=options.private_key,
            )
            client = DataPlaneBootstrapClient(
                pathlib.Path(options.state_file), pathlib.Path(options.private_key)
            )
            write_bootstrap_claim(client, pathlib.Path(options.output_token))
        except (HeartbeatError, OSError, ProtocolError, ValueError) as exc:
            print("节点尚未获准自动部署：{}".format(exc), file=sys.stderr)
            return 1
        print("节点已领取短时数据面部署凭据")
        return 0
    if options.command == "run-hysteria":
        try:
            run_hysteria_from_template(
                "/opt/hysteria2-panel-node/bin/hysteria",
                pathlib.Path(options.template),
                pathlib.Path(options.runtime_config),
            )
        except (OSError, ProtocolError, ValueError) as exc:
            print("错误：{}".format(exc), file=sys.stderr)
            return 1
        return 1
    if options.command == "ack-data-plane":
        token = os.environ.pop("HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN", "")
        stats_secret = os.environ.pop("HY2PANEL_STATS_SECRET", "")
        if not token or not stats_secret:
            print("错误：缺少数据面确认凭据", file=sys.stderr)
            return 2
        try:
            attestation = collect_data_plane_attestation(
                pathlib.Path(options.metadata),
                pathlib.Path(options.certificate),
                pathlib.Path(options.hysteria_key),
                stats_secret,
            )
            client = DataPlaneBootstrapClient(
                pathlib.Path(options.state_file), pathlib.Path(options.private_key)
            )
            client.ack(token, attestation)
        except (OSError, ProtocolError, ValueError) as exc:
            print("错误：{}".format(exc), file=sys.stderr)
            return 1
        finally:
            del token
            del stats_secret
        print("数据面已通过本地健康证明并由中央面板确认")
        return 0
    if options.command == "serve-auth-proxy":
        try:
            client = NodeProtocolClient(
                pathlib.Path(options.state_file), pathlib.Path(options.private_key)
            )
            server = make_node_auth_proxy_server(
                ("127.0.0.1", options.port), client, metrics_file=options.metrics_file
            )
        except (OSError, ValueError, ProtocolError) as exc:
            print("错误：{}".format(exc), file=sys.stderr)
            return 1
        stopped = threading.Event()

        def request_stop(_signum, _frame):
            stopped.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        try:
            serve_node_auth_proxy(server, stopped)
        finally:
            server.server_close()
        return 0
    if options.command in {"control-once", "control-loop"}:
        try:
            cycle = _make_control_cycle(options)
            if options.command == "control-once":
                cycle.run_once()
                return 0
            stopped = threading.Event()

            def request_stop(_signum, _frame):
                stopped.set()

            signal.signal(signal.SIGTERM, request_stop)
            signal.signal(signal.SIGINT, request_stop)
            metrics = None
            if options.metrics_file:
                metrics = NodeRuntimeMetrics(options.metrics_file, spool=cycle.spool)
            run_control_loop(cycle, stopped, metrics=metrics)
            return 0
        except (HeartbeatError, OSError, ProtocolError, ValueError) as exc:
            print("错误：{}".format(exc), file=sys.stderr)
            return 1
    try:
        result = heartbeat(
            state_path=options.state_file,
            private_key_path=options.private_key,
        )
    except (HeartbeatError, ValueError) as exc:
        print("错误：{}".format(exc), file=sys.stderr)
        return 1
    print("节点心跳已确认：{}".format(result["status"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
