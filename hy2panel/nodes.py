"""Secure first-phase node enrollment contracts."""

import base64
import hashlib
import ipaddress
import json
import re
import secrets
import subprocess  # nosec B404 -- fixed executable and argv, never a shell.
import tempfile
import time
import urllib.parse
from pathlib import Path


ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
ARCHITECTURES = {"amd64", "arm64"}
HEARTBEAT_FIELDS = {
    "nodeId",
    "sentAt",
    "nonce",
    "hostname",
    "agentVersion",
    "signature",
}
HEARTBEAT_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
HEARTBEAT_PREFIX = b"hy2panel-node-heartbeat-v1\n"
HEARTBEAT_CLOCK_SKEW_SECONDS = 120
HEARTBEAT_INTERVAL_SECONDS = 60


class EnrollmentRejected(ValueError):
    """A public enrollment request failed without disclosing token state."""


class HeartbeatRejected(ValueError):
    """A public heartbeat failed without disclosing node state."""


def _single_quote(value):
    return "'{}'".format(str(value).replace("'", "'\"'\"'"))


def _normalize_name(value):
    value = str(value or "").strip()
    if not value or len(value) > 64 or any(ord(character) < 32 for character in value):
        raise ValueError("node name must contain 1 to 64 printable characters")
    return value


def _normalize_ip(value, allow_empty=False):
    value = str(value or "").strip()
    if not value and allow_empty:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise ValueError("node address must be an IPv4 or IPv6 address") from exc


def _validate_panel_url(value):
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
        raise ValueError("node enrollment requires a dedicated HTTPS panel URL")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("panel URL port is invalid") from exc
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _validate_ed25519_public_key(value):
    if not isinstance(value, str) or len(value) > 128:
        raise EnrollmentRejected("node enrollment was rejected")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise EnrollmentRejected("node enrollment was rejected") from exc
    if len(decoded) != 44 or not decoded.startswith(ED25519_SPKI_PREFIX):
        raise EnrollmentRejected("node enrollment was rejected")
    return base64.b64encode(decoded).decode("ascii")


def canonical_heartbeat(payload):
    signed_fields = {
        key: payload[key]
        for key in ("nodeId", "sentAt", "nonce", "hostname", "agentVersion")
    }
    return HEARTBEAT_PREFIX + json.dumps(
        signed_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class OpenSSLSignatureVerifier:
    """Verify Ed25519 signatures using the platform OpenSSL binary."""

    def __init__(self, executable="/usr/bin/openssl", timeout_seconds=5):
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def __call__(self, public_key, message, signature):
        try:
            public_der = base64.b64decode(public_key, validate=True)
        except (TypeError, ValueError):
            return False
        if (
            len(public_der) != 44
            or not public_der.startswith(ED25519_SPKI_PREFIX)
            or not isinstance(message, bytes)
            or not isinstance(signature, bytes)
            or len(signature) != 64
        ):
            return False
        try:
            with tempfile.TemporaryDirectory(prefix="hy2panel-heartbeat-") as directory:
                directory = Path(directory)
                public_path = directory / "public.der"
                message_path = directory / "message.bin"
                signature_path = directory / "signature.bin"
                public_path.write_bytes(public_der)
                message_path.write_bytes(message)
                signature_path.write_bytes(signature)
                for path in (public_path, message_path, signature_path):
                    path.chmod(0o600)
                completed = subprocess.run(  # nosec B603 -- fixed argv, no shell.
                    [
                        self.executable,
                        "pkeyutl",
                        "-verify",
                        "-pubin",
                        "-inkey",
                        str(public_path),
                        "-keyform",
                        "DER",
                        "-sigfile",
                        str(signature_path),
                        "-rawin",
                        "-in",
                        str(message_path),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False


class NodeHeartbeatService:
    """Validate signed node heartbeats before committing freshness state."""

    def __init__(self, database, clock=time.time, signature_verifier=None):
        self.database = database
        self.clock = clock
        self.signature_verifier = signature_verifier or OpenSSLSignatureVerifier()

    @staticmethod
    def _reject():
        raise HeartbeatRejected("node heartbeat was rejected")

    def accept(self, payload, remote_ip):
        if not isinstance(payload, dict) or set(payload) != HEARTBEAT_FIELDS:
            self._reject()
        node_id = payload.get("nodeId")
        sent_at = payload.get("sentAt")
        nonce = payload.get("nonce")
        hostname = payload.get("hostname")
        agent_version = payload.get("agentVersion")
        signature_text = payload.get("signature")
        if not isinstance(node_id, str) or not re.fullmatch(r"[0-9a-f]{32}", node_id):
            self._reject()
        if isinstance(sent_at, bool) or not isinstance(sent_at, int):
            self._reject()
        now = int(self.clock())
        if abs(now - sent_at) > HEARTBEAT_CLOCK_SKEW_SECONDS:
            self._reject()
        if not isinstance(nonce, str) or not HEARTBEAT_NONCE_PATTERN.fullmatch(nonce):
            self._reject()
        try:
            nonce_bytes = base64.urlsafe_b64decode(nonce + "=")
        except (ValueError, TypeError):
            self._reject()
        if len(nonce_bytes) != 32:
            self._reject()
        if not isinstance(hostname, str) or not HOSTNAME_PATTERN.fullmatch(hostname):
            self._reject()
        if not isinstance(agent_version, str) or not VERSION_PATTERN.fullmatch(agent_version):
            self._reject()
        if not isinstance(signature_text, str) or len(signature_text) > 128:
            self._reject()
        try:
            signature = base64.b64decode(signature_text, validate=True)
            remote_ip = _normalize_ip(remote_ip)
        except (ValueError, TypeError):
            self._reject()
        if len(signature) != 64:
            self._reject()
        node = self.database.get_node_for_heartbeat(node_id)
        if (
            node is None
            or node["status"] != "pending_verification"
            or node["verified_at"] is None
            or node["hostname"] != hostname
        ):
            self._reject()
        bound_ip = node["expected_ip"] or node["observed_ip"]
        if bound_ip is None or not secrets.compare_digest(bound_ip, remote_ip):
            self._reject()
        message = canonical_heartbeat(payload)
        try:
            verified = self.signature_verifier(node["public_key"], message, signature)
        except Exception:
            verified = False
        if not verified:
            self._reject()
        accepted = self.database.accept_node_heartbeat(
            node_id,
            nonce_digest=hashlib.sha256(nonce_bytes).hexdigest(),
            sent_at=sent_at,
            accepted_at=now,
            remote_ip=remote_ip,
        )
        if not accepted:
            self._reject()
        return {
            "status": "ONLINE",
            "acceptedAt": now,
            "nextHeartbeatSeconds": HEARTBEAT_INTERVAL_SECONDS,
        }


class NodeEnrollmentService:
    """Issues short-lived tokens and atomically registers pending nodes."""

    COSIGN_VERSION = "3.1.3"
    COSIGN_SHA_AMD64 = "4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71"
    COSIGN_SHA_ARM64 = "c5d324e091826b0d7a78eb16fef316450b4eb9aaec045611c08ba06f5e73220a"

    def __init__(
        self,
        database,
        panel_url,
        panel_version,
        clock=time.time,
        token_factory=None,
    ):
        self.database = database
        self.panel_url = _validate_panel_url(panel_url)
        if not VERSION_PATTERN.fullmatch(str(panel_version or "")):
            raise ValueError("panel version is invalid")
        self.panel_version = str(panel_version)
        self.clock = clock
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    def _deployment_command(self, token):
        tag = "v{}".format(self.panel_version)
        repository = "https://github.com/Elegying/Hysteria2-panel"
        raw_installer = (
            "https://raw.githubusercontent.com/Elegying/Hysteria2-panel/"
            "{}/install.sh".format(tag)
        )
        bundle = "{}/releases/download/{}/install.sh.sigstore.json".format(
            repository, tag
        )
        identity = (
            "{}/.github/workflows/release-signature.yml@refs/tags/{}".format(
                repository, tag
            )
        )
        return """set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo '请切换到 root 后重新粘贴此代码' >&2; exit 1; fi
join_tmp="$(mktemp -d -t hy2panel-node-join.XXXXXXXX)"
trap 'rm -rf -- "$join_tmp"' EXIT HUP INT TERM
case "$(uname -m)" in
  x86_64|amd64) cosign_asset=cosign-linux-amd64; cosign_sha={cosign_sha_amd64} ;;
  aarch64|arm64) cosign_asset=cosign-linux-arm64; cosign_sha={cosign_sha_arm64} ;;
  *) echo '仅支持 Linux amd64 和 arm64' >&2; exit 1 ;;
esac
curl -q -fL --connect-timeout 10 --max-time 300 \
  "https://github.com/sigstore/cosign/releases/download/v{cosign_version}/$cosign_asset" \
  -o "$join_tmp/cosign"
printf '%s  %s\\n' "$cosign_sha" "$join_tmp/cosign" | sha256sum --check --status
chmod 0700 "$join_tmp/cosign"
curl -q -fL --connect-timeout 10 --max-time 300 {installer} -o "$join_tmp/install.sh"
curl -q -fL --connect-timeout 10 --max-time 300 {bundle} -o "$join_tmp/install.sh.sigstore.json"
"$join_tmp/cosign" verify-blob "$join_tmp/install.sh" \
  --bundle "$join_tmp/install.sh.sigstore.json" \
  --certificate-identity {identity} \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
bash -n "$join_tmp/install.sh"
export HY2PANEL_PANEL_URL={panel_url}
export HY2PANEL_ENROLLMENT_TOKEN={token}
export PANEL_REF={tag}
/bin/bash "$join_tmp/install.sh" --join-node
unset HY2PANEL_ENROLLMENT_TOKEN
""".format(
            cosign_sha_amd64=self.COSIGN_SHA_AMD64,
            cosign_sha_arm64=self.COSIGN_SHA_ARM64,
            cosign_version=self.COSIGN_VERSION,
            installer=_single_quote(raw_installer),
            bundle=_single_quote(bundle),
            identity=_single_quote(identity),
            panel_url=_single_quote(self.panel_url),
            token=_single_quote(token),
            tag=_single_quote(tag),
        )

    def create(self, name, expected_ip, ttl_minutes, actor):
        name = _normalize_name(name)
        expected_ip = _normalize_ip(expected_ip, allow_empty=True)
        try:
            ttl_minutes = int(ttl_minutes)
        except (TypeError, ValueError) as exc:
            raise ValueError("enrollment lifetime must be between 5 and 30 minutes") from exc
        if ttl_minutes < 5 or ttl_minutes > 30:
            raise ValueError("enrollment lifetime must be between 5 and 30 minutes")
        actor = _normalize_name(actor)
        token = str(self.token_factory())
        if not TOKEN_PATTERN.fullmatch(token):
            raise RuntimeError("secure enrollment token generation failed")
        now = int(self.clock())
        record = self.database.create_node_enrollment(
            name=name,
            expected_ip=expected_ip,
            actor=actor,
            token_digest=hashlib.sha256(token.encode("ascii")).hexdigest(),
            created_at=now,
            expires_at=now + ttl_minutes * 60,
        )
        return {
            "nodeId": record["node_id"],
            "enrollmentId": record["enrollment_id"],
            "expiresAt": record["expires_at"],
            "status": "PENDING_REGISTRATION",
            "deploymentCommand": self._deployment_command(token),
        }

    def revoke(self, enrollment_id):
        enrollment_id = str(enrollment_id or "")
        if not re.fullmatch(r"[0-9a-f]{32}", enrollment_id):
            return False
        return self.database.revoke_node_enrollment(
            enrollment_id, revoked_at=int(self.clock())
        )

    def register(self, payload, remote_ip):
        if not isinstance(payload, dict):
            raise EnrollmentRejected("node enrollment was rejected")
        expected_fields = {
            "enrollmentToken",
            "publicKey",
            "hostname",
            "platform",
            "architecture",
            "agentVersion",
        }
        if set(payload) != expected_fields:
            raise EnrollmentRejected("node enrollment was rejected")
        token = payload.get("enrollmentToken")
        if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
            raise EnrollmentRejected("node enrollment was rejected")
        public_key = _validate_ed25519_public_key(payload.get("publicKey"))
        hostname = payload.get("hostname")
        platform = payload.get("platform")
        architecture = payload.get("architecture")
        agent_version = payload.get("agentVersion")
        if not isinstance(hostname, str) or not HOSTNAME_PATTERN.fullmatch(hostname):
            raise EnrollmentRejected("node enrollment was rejected")
        if platform != "linux" or architecture not in ARCHITECTURES:
            raise EnrollmentRejected("node enrollment was rejected")
        if not isinstance(agent_version, str) or not VERSION_PATTERN.fullmatch(agent_version):
            raise EnrollmentRejected("node enrollment was rejected")
        try:
            remote_ip = _normalize_ip(remote_ip)
        except ValueError as exc:
            raise EnrollmentRejected("node enrollment was rejected") from exc
        record = self.database.consume_node_enrollment(
            token_digest=hashlib.sha256(token.encode("ascii")).hexdigest(),
            public_key=public_key,
            observed_ip=remote_ip,
            hostname=hostname,
            platform=platform,
            architecture=architecture,
            agent_version=agent_version,
            registered_at=int(self.clock()),
        )
        if record is None:
            raise EnrollmentRejected("node enrollment was rejected")
        return {"nodeId": record["node_id"], "status": "PENDING_VERIFICATION"}
