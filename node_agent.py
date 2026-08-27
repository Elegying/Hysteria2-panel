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
import socket
import stat
import subprocess  # nosec B404 -- fixed executable and argv, never a shell.
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


AGENT_VERSION = "0.25.0"
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


def _openssl_sign(private_key_path, message, executable="/usr/bin/openssl"):
    private_key_path = pathlib.Path(private_key_path)
    _read_root_only_file(private_key_path, "private key")
    try:
        with tempfile.NamedTemporaryFile(prefix="hy2panel-heartbeat-", mode="wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(message)
            handle.flush()
            os.fsync(handle.fileno())
            completed = subprocess.run(  # nosec B603 -- fixed argv, no shell.
                [
                    executable,
                    "pkeyutl",
                    "-sign",
                    "-rawin",
                    "-inkey",
                    str(private_key_path),
                    "-in",
                    handle.name,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HeartbeatError("cannot sign the node heartbeat") from exc
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
    return parser


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
