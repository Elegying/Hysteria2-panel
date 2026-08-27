"""Secure first-phase node enrollment contracts."""

import base64
import hashlib
import ipaddress
import re
import secrets
import time
import urllib.parse


ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
ARCHITECTURES = {"amd64", "arm64"}


class EnrollmentRejected(ValueError):
    """A public enrollment request failed without disclosing token state."""


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
printf '%s  %s\n' "$cosign_sha" "$join_tmp/cosign" | sha256sum --check --status
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
