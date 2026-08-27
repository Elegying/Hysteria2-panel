#!/usr/bin/env python3
"""Minimal first-phase agent used to enroll a new node for verification."""

import argparse
import base64
import json
import os
import pathlib
import platform
import re
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


AGENT_VERSION = "0.24.0"
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


def _parser():
    parser = argparse.ArgumentParser(description="Hysteria2-panel node enrollment agent")
    subcommands = parser.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("register")
    command.add_argument("--panel-url", required=True)
    command.add_argument("--public-key", required=True)
    command.add_argument("--state-file", required=True)
    return parser


def main(arguments=None):
    try:
        options = _parser().parse_args(arguments)
    except SystemExit as exc:
        return int(exc.code)
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


if __name__ == "__main__":
    raise SystemExit(main())
