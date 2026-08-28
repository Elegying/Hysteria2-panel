#!/usr/bin/env python3
"""Minimal first-phase agent used to enroll a new node for verification."""

import argparse
import base64
import json
import os
import pathlib
import platform
import re
import secrets
import shutil
import signal
import socket
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


AGENT_VERSION = "0.26.0"
MAX_RESPONSE_BYTES = 8192
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

    def do_GET(self):
        if self.path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        entrypoint = {"/auth": "main", "/auth/udp-443": "udp443"}.get(self.path)
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
    allow_reuse_address = False
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
    address, protocol_client, max_workers=32, request_timeout=5.0
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
    return server


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

    def can_collect(self, maximum_response_bytes=256 * 1024):
        maximum_response_bytes = max(1, int(maximum_response_bytes))
        required_bytes = maximum_response_bytes + 4096
        free = shutil.disk_usage(str(self.path)).free
        count, current_size = self._current_usage()
        return (
            count < self.max_entries
            and current_size + required_bytes <= self.max_bytes
            and free >= required_bytes + self.reserve_bytes
        )

    def enqueue(self, traffic, observed_at):
        self._validate_traffic(traffic)
        if isinstance(observed_at, bool) or not isinstance(observed_at, int):
            raise ProtocolError("traffic observation time is invalid")
        batch = {
            "batchId": uuid.uuid4().hex,
            "observedAt": observed_at,
            "traffic": traffic,
        }
        encoded = json.dumps(
            batch, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8") + b"\n"
        count, current_size = self._current_usage()
        if count >= self.max_entries or current_size + len(encoded) > self.max_bytes:
            raise ProtocolError("traffic spool is full")
        descriptor, staged_name = tempfile.mkstemp(prefix=".traffic-", dir=str(self.path))
        destination = self.path / (batch["batchId"] + ".json")
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged_name, str(destination))
            _fsync_directory(self.path)
        finally:
            try:
                os.unlink(staged_name)
            except FileNotFoundError:
                pass
        return batch

    def pending(self):
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
                or metadata.st_size > 256 * 1024 + 4096
            ):
                raise ProtocolError("traffic spool entry is invalid")
            try:
                batch = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProtocolError("traffic spool entry is invalid") from exc
            if (
                not isinstance(batch, dict)
                or set(batch) != {"batchId", "observedAt", "traffic"}
                or not NODE_ID_PATTERN.fullmatch(str(batch["batchId"]))
                or isinstance(batch["observedAt"], bool)
                or not isinstance(batch["observedAt"], int)
            ):
                raise ProtocolError("traffic spool entry is invalid")
            self._validate_traffic(batch["traffic"])
            batches.append(batch)
        return batches

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
    if purpose not in {"auth", "online", "traffic", "command-poll", "command-ack"}:
        raise ProtocolError("node request purpose is invalid")
    return "hy2panel-node-{}-v1\n".format(purpose).encode("ascii") + json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class NodeProtocolClient:
    """Sign bounded node protocol requests using the enrolled Ed25519 key."""

    PATHS = {
        "auth": ("/api/v1/node-auth-decisions", 16 * 1024),
        "online": ("/api/v1/node-online-snapshots", 8 * 1024),
        "traffic": ("/api/v1/node-traffic-batches", 8 * 1024),
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
            with self.opener(request, timeout=10) as response:
                status = getattr(
                    response,
                    "status",
                    response.getcode() if hasattr(response, "getcode") else 0,
                )
                body = response.read(maximum + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
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
                body = response.read(256 * 1024 + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            raise ProtocolError("local traffic stats request failed") from exc
        if status != 200 or len(body) > 256 * 1024:
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


def execute_control_command(
    command, stats_client, refresh_snapshot=None, flush_traffic=None
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
                {"sequence": 0, "trafficAckedAt": 0, "completedCommands": []}
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
        commands = state.get("completedCommands") if isinstance(state, dict) else None
        if (
            not isinstance(state, dict)
            or set(state) != {"sequence", "trafficAckedAt", "completedCommands"}
            or any(
                isinstance(state[key], bool) or not isinstance(state[key], int)
                for key in ("sequence", "trafficAckedAt")
            )
            or state["sequence"] < 0
            or state["trafficAckedAt"] < 0
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

    def __init__(self, protocol_client, stats_client, spool, state, clock=time.time):
        self.protocol_client = protocol_client
        self.stats_client = stats_client
        self.spool = spool
        self.state = state
        self.clock = clock

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

    def flush_traffic(self):
        self._upload_pending()
        if not self.spool.can_collect():
            raise ProtocolError("traffic spool has insufficient capacity")
        traffic = self.stats_client.collect_and_clear()
        batch = self.spool.enqueue(traffic, observed_at=int(self.clock()))
        result = self.protocol_client.send_traffic(batch)
        if (
            not isinstance(result, dict)
            or result.get("batchId") != batch["batchId"]
            or result.get("committed") is not True
        ):
            raise ProtocolError("central traffic ACK is invalid")
        self.spool.ack(batch["batchId"])
        accepted_at = int(self.clock())
        self.state.set_traffic_ack(accepted_at)
        return accepted_at

    def refresh_snapshot(self):
        traffic_acked_at = self.state.traffic_acked_at()
        if int(self.clock()) - traffic_acked_at > 5:
            raise ProtocolError("traffic checkpoint is stale")
        result = self.protocol_client.send_online(
            self.state.next_sequence(),
            self.stats_client.online(),
            traffic_acked_at,
        )
        if not isinstance(result, dict) or not isinstance(result.get("sequence"), int):
            raise ProtocolError("central online snapshot ACK is invalid")
        return result

    def run_once(self):
        self.flush_traffic()
        self.refresh_snapshot()
        commands = self.protocol_client.poll_commands()
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
                )
            except Exception:
                self.protocol_client.ack_command(
                    command_id, False, "EXECUTION_FAILED"
                )
                continue
            self.state.record_command_completed(command_id, int(self.clock()))
            self.protocol_client.ack_command(command_id, True, "")


def run_control_loop(
    cycle,
    stop_event,
    interval_seconds=2,
    maximum_backoff_seconds=30,
    sleeper=None,
):
    """Run fixed short polling while backing off boundedly on control failures."""
    interval = max(1, min(5, int(interval_seconds)))
    maximum_backoff = max(interval, min(300, int(maximum_backoff_seconds)))
    delay = interval
    while not stop_event.is_set():
        try:
            cycle.run_once()
        except (OSError, ProtocolError):
            next_delay = min(maximum_backoff, delay * 2)
        else:
            next_delay = interval
            delay = interval
        if sleeper is None:
            stop_event.wait(delay)
        else:
            sleeper(delay)
        delay = next_delay


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
    for name in ("control-once", "control-loop"):
        command = subcommands.add_parser(name)
        command.add_argument("--private-key", required=True)
        command.add_argument("--state-file", required=True)
        command.add_argument("--protocol-state", required=True)
        command.add_argument("--spool-dir", required=True)
        command.add_argument("--stats-url", required=True)
    return parser


def _make_control_cycle(options):
    secret = os.environ.pop("HY2PANEL_STATS_SECRET", "")
    if not secret:
        raise ValueError("local traffic stats secret is unavailable")
    protocol_client = NodeProtocolClient(
        pathlib.Path(options.state_file), pathlib.Path(options.private_key)
    )
    stats_client = LocalStatsClient(options.stats_url, secret)
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
    if options.command == "serve-auth-proxy":
        try:
            client = NodeProtocolClient(
                pathlib.Path(options.state_file), pathlib.Path(options.private_key)
            )
            server = make_node_auth_proxy_server(
                ("127.0.0.1", options.port), client
            )
        except (OSError, ValueError, ProtocolError) as exc:
            print("错误：{}".format(exc), file=sys.stderr)
            return 1
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
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
            run_control_loop(cycle, stopped)
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
