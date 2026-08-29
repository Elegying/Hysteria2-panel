"""Secure first-phase node enrollment contracts."""

import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import stat
import subprocess  # nosec B404 -- fixed executable and argv, never a shell.
import tempfile
import threading
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
DATA_PLANE_PURPOSES = {"claim", "bootstrap", "ack"}
DATA_PLANE_COMMON_FIELDS = {"nodeId", "sentAt", "nonce", "signature"}
DATA_PLANE_CLAIM_FIELDS = DATA_PLANE_COMMON_FIELDS | {"requestId"}
DATA_PLANE_BOOTSTRAP_FIELDS = DATA_PLANE_COMMON_FIELDS | {
    "bootstrapToken",
    "requestId",
}
DATA_PLANE_ACK_FIELDS = DATA_PLANE_BOOTSTRAP_FIELDS | {
    "certificateFileSha256",
    "certificateDerSha256",
    "privateKeyPublicSha256",
    "hysteriaVersion",
    "egressPolicy",
    "configProtocolVersion",
    "servicesHealthy",
    "statsHealthy",
    "udp19999Listening",
    "udp443Listening",
    "tcp19999Listening",
    "tcp443Listening",
}
OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DATA_PLANE_RESPONSE_LIMIT = 32 * 1024


class EnrollmentRejected(ValueError):
    """A public enrollment request failed without disclosing token state."""


class HeartbeatRejected(ValueError):
    """A public heartbeat failed without disclosing node state."""


class DataPlaneBootstrapRejected(ValueError):
    """A data-plane bootstrap request failed without exposing grant state."""


class HysteriaCanaryRunner:
    """Prove both node entrypoints and their external egress with no user account."""

    TRACE_URL = "https://cloudflare.com/cdn-cgi/trace"

    def __init__(
        self,
        server_name,
        hysteria_path="/opt/hysteria2-panel/bin/hysteria",
        curl_path="/usr/bin/curl",
        port_factory=None,
        sleep=time.sleep,
    ):
        server_name = str(server_name or "").strip().rstrip(".").lower()
        if not HOSTNAME_PATTERN.fullmatch(server_name):
            raise ValueError("canary server name is invalid")
        self.server_name = server_name
        self.hysteria_path = str(hysteria_path)
        self.curl_path = str(curl_path)
        self.port_factory = port_factory or self._allocate_port
        self.sleep = sleep

    @staticmethod
    def _allocate_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    @staticmethod
    def _verify_trace(payload, expected_ip):
        if not isinstance(payload, str) or len(payload.encode("utf-8")) > 8192:
            raise RuntimeError("canary trace response is invalid")
        addresses = [
            line[3:].strip()
            for line in payload.splitlines()
            if line.startswith("ip=")
        ]
        if len(addresses) != 1:
            raise RuntimeError("canary trace response has no unique egress address")
        try:
            observed = str(ipaddress.ip_address(addresses[0]))
        except ValueError as exc:
            raise RuntimeError("canary trace response address is invalid") from exc
        if not secrets.compare_digest(observed, expected_ip):
            raise RuntimeError("canary egress address does not match the node")

    def _check_entrypoint(self, node_ip, port, token, pin_sha256):
        local_port = int(self.port_factory())
        if not 1024 <= local_port <= 65535:
            raise RuntimeError("canary local port is invalid")
        server = "[{}]:{}".format(node_ip, port) if ":" in node_ip else "{}:{}".format(node_ip, port)
        pin = ":".join(
            pin_sha256[index : index + 2].upper()
            for index in range(0, len(pin_sha256), 2)
        )
        config = {
            "server": server,
            "auth": token,
            "tls": {
                "sni": self.server_name,
                "insecure": True,
                "pinSHA256": pin,
            },
            "socks5": {"listen": "127.0.0.1:{}".format(local_port)},
        }
        process = None
        log_handle = None
        log_descriptor = -1
        with tempfile.TemporaryDirectory(prefix="hy2panel-canary-") as directory:
            config_path = Path(directory) / "client.json"
            log_path = Path(directory) / "client.log"
            descriptor = os.open(
                str(config_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    descriptor = -1
                    json.dump(config, handle, ensure_ascii=True, separators=(",", ":"))
                    handle.flush()
                    os.fsync(handle.fileno())
                log_descriptor = os.open(
                    str(log_path),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                log_handle = os.fdopen(log_descriptor, "wb", buffering=0)
                log_descriptor = -1
                process = subprocess.Popen(  # nosec B603 -- fixed binary and argv.
                    [self.hysteria_path, "client", "--config", str(config_path)],
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=log_handle,
                    close_fds=True,
                    start_new_session=True,
                    env={
                        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                        "HYSTERIA_DISABLE_UPDATE_CHECK": "1",
                    },
                )
                ready = False
                for _attempt in range(50):
                    if process.poll() is not None:
                        break
                    try:
                        with socket.create_connection(
                            ("127.0.0.1", local_port), timeout=0.2
                        ):
                            ready = True
                            break
                    except OSError:
                        self.sleep(0.1)
                if not ready:
                    raise RuntimeError("Hysteria canary proxy did not become ready")
                result = subprocess.run(  # nosec B603 -- fixed binary and argv.
                    [
                        self.curl_path,
                        "-q",
                        "-fLsS",
                        "--connect-timeout",
                        "5",
                        "--max-time",
                        "15",
                        "--max-filesize",
                        "8192",
                        "--proxy",
                        "socks5h://127.0.0.1:{}".format(local_port),
                        self.TRACE_URL,
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=20,
                    env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
                )
                if result.returncode != 0:
                    raise RuntimeError("Hysteria canary external request failed")
                self._verify_trace(result.stdout, node_ip)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                if log_descriptor >= 0:
                    os.close(log_descriptor)
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                if log_handle is not None:
                    log_handle.close()

    def __call__(self, *, node_ip, main_port, token, pin_sha256):
        try:
            address = ipaddress.ip_address(node_ip)
        except ValueError as exc:
            raise ValueError("canary node address is invalid") from exc
        if not address.is_global:
            raise ValueError("canary node address must be public")
        node_ip = str(address)
        if (
            isinstance(main_port, bool)
            or not isinstance(main_port, int)
            or not 1 <= main_port <= 65535
            or main_port == 443
        ):
            raise ValueError("canary main port is invalid")
        if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
            raise ValueError("canary token is invalid")
        if not isinstance(pin_sha256, str) or not SHA256_PATTERN.fullmatch(pin_sha256):
            raise ValueError("canary certificate pin is invalid")
        for port in (main_port, 443):
            self._check_entrypoint(node_ip, port, token, pin_sha256)


class NodeDnsAdmissionReconciler:
    """Observe manually managed DNS and admit only fresh, canary-passed nodes."""

    def __init__(self, database, hostname, resolver=socket.getaddrinfo, clock=time.time):
        hostname = str(hostname or "").strip().rstrip(".").lower()
        if not HOSTNAME_PATTERN.fullmatch(hostname):
            raise ValueError("DNS admission hostname is invalid")
        self.database = database
        self.hostname = hostname
        self.resolver = resolver
        self.clock = clock

    def _resolved_public_addresses(self):
        try:
            answers = self.resolver(
                self.hostname, 443, type=socket.SOCK_STREAM
            )
        except (OSError, socket.gaierror):
            return set()
        addresses = set()
        for family, _kind, _protocol, _canonical, socket_address in list(answers)[:64]:
            if family not in {socket.AF_INET, socket.AF_INET6} or not socket_address:
                continue
            try:
                address = ipaddress.ip_address(socket_address[0])
            except (TypeError, ValueError):
                continue
            if address.is_global:
                addresses.add(str(address))
        return addresses

    def reconcile(self):
        candidates = [
            node
            for node in self.database.list_nodes()
            if node.get("data_plane_state") == "direct_canary_passed"
        ]
        addresses = self._resolved_public_addresses()
        now = int(self.clock())
        admitted = 0
        for node in candidates:
            expected = node.get("expected_ip") or node.get("observed_ip")
            try:
                expected = str(ipaddress.ip_address(expected))
            except (TypeError, ValueError):
                continue
            if expected not in addresses:
                continue
            try:
                changed = self.database.mark_node_dns_admitted(
                    node["node_id"], "system:dns-monitor", now
                )
            except ValueError:
                continue
            admitted += int(bool(changed))
        return {"checked": len(candidates), "admitted": admitted}


class HysteriaIdentityProvider:
    """Read and attest the existing Hysteria identity without rewriting it."""

    MAX_IDENTITY_FILE_BYTES = 16 * 1024

    def __init__(
        self,
        certificate_path,
        private_key_path,
        egress_policy_provider,
        openssl_executable="/usr/bin/openssl",
        timeout_seconds=5,
    ):
        self.certificate_path = Path(certificate_path)
        self.private_key_path = Path(private_key_path)
        self.egress_policy_provider = egress_policy_provider
        self.openssl_executable = openssl_executable
        self.timeout_seconds = timeout_seconds

    def _read_regular_file(self, path):
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(str(path), flags)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_size < 1
                or metadata.st_size > self.MAX_IDENTITY_FILE_BYTES
            ):
                raise ValueError("Hysteria identity file is unsafe")
            chunks = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 4096))
                if not chunk:
                    raise ValueError("Hysteria identity changed while reading")
                chunks.append(chunk)
                remaining -= len(chunk)
            value = b"".join(chunks)
        except OSError as exc:
            raise ValueError("Hysteria identity is unavailable") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        return value

    def _openssl(self, arguments, input_bytes=None):
        try:
            completed = subprocess.run(  # nosec B603 -- fixed executable and argv.
                [self.openssl_executable] + list(arguments),
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Hysteria identity validation failed") from exc
        if completed.returncode != 0 or not completed.stdout:
            raise ValueError("Hysteria identity validation failed")
        return completed.stdout

    def __call__(self):
        certificate = self._read_regular_file(self.certificate_path)
        private_key = self._read_regular_file(self.private_key_path)
        try:
            certificate_text = certificate.decode("ascii")
            private_key_text = private_key.decode("ascii")
            certificate_der = ssl.PEM_cert_to_DER_cert(certificate_text)
        except (UnicodeError, ValueError) as exc:
            raise ValueError("Hysteria identity validation failed") from exc
        certificate_public_pem = self._openssl(
            ["x509", "-pubkey", "-noout"], certificate
        )
        certificate_public_der = self._openssl(
            ["pkey", "-pubin", "-outform", "DER"], certificate_public_pem
        )
        private_key_public_der = self._openssl(
            ["pkey", "-pubout", "-outform", "DER"], private_key
        )
        if not secrets.compare_digest(certificate_public_der, private_key_public_der):
            raise ValueError("Hysteria certificate and private key do not match")
        try:
            egress_policy = self.egress_policy_provider()
        except Exception as exc:
            raise ValueError("Hysteria egress policy is unavailable") from exc
        if egress_policy not in {"web", "full"}:
            raise ValueError("Hysteria egress policy is invalid")
        return {
            "certificatePem": certificate_text,
            "privateKeyPem": private_key_text,
            "certificateFileSha256": hashlib.sha256(certificate).hexdigest(),
            "certificateDerSha256": hashlib.sha256(certificate_der).hexdigest(),
            "privateKeyPublicSha256": hashlib.sha256(
                private_key_public_der
            ).hexdigest(),
            "egressPolicy": egress_policy,
        }


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


def canonical_data_plane_request(purpose, payload):
    if purpose not in DATA_PLANE_PURPOSES or not isinstance(payload, dict):
        raise ValueError("data-plane request purpose is invalid")
    signed = {key: value for key, value in payload.items() if key != "signature"}
    return "hy2panel-data-plane-{}-v1\n".format(purpose).encode(
        "ascii"
    ) + json.dumps(
        signed,
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
        message_descriptor = None
        try:
            with tempfile.TemporaryDirectory(prefix="hy2panel-heartbeat-") as directory:
                directory = Path(directory)
                public_path = directory / "public.der"
                signature_path = directory / "signature.bin"
                public_path.write_bytes(public_der)
                signature_path.write_bytes(signature)
                for path in (public_path, signature_path):
                    path.chmod(0o600)
                message_path, message_options, message_descriptor = (
                    _openssl_message_input(message)
                )
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
                        message_path,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.timeout_seconds,
                    check=False,
                    **message_options,
                )
                return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
        finally:
            if message_descriptor is not None:
                os.close(message_descriptor)


class NodeHeartbeatService:
    """Validate signed node heartbeats before committing freshness state."""

    def __init__(
        self,
        database,
        clock=time.time,
        signature_verifier=None,
        verification_slots=8,
    ):
        self.database = database
        self.clock = clock
        self.signature_verifier = signature_verifier or OpenSSLSignatureVerifier()
        self._verification_gate = threading.BoundedSemaphore(verification_slots)

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
        if not self._verification_gate.acquire(blocking=False):
            self._reject()
        try:
            try:
                verified = self.signature_verifier(node["public_key"], message, signature)
            except Exception:
                verified = False
        finally:
            self._verification_gate.release()
        if not verified:
            self._reject()
        accepted = self.database.accept_node_heartbeat(
            node_id,
            nonce_digest=hashlib.sha256(nonce_bytes).hexdigest(),
            sent_at=sent_at,
            accepted_at=now,
            remote_ip=remote_ip,
            agent_version=agent_version,
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

    def _deployment_command(self, token, mode="join"):
        if mode not in {"join", "rebind"}:
            raise ValueError("enrollment mode must be join or rebind")
        installer_mode = "--join-node" if mode == "join" else "--rebind-node"
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
/bin/bash "$join_tmp/install.sh" {installer_mode}
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
            installer_mode=installer_mode,
        )

    def create(self, name, expected_ip, ttl_minutes, actor, mode="join"):
        name = _normalize_name(name)
        expected_ip = _normalize_ip(expected_ip, allow_empty=True)
        mode = str(mode or "join")
        if mode not in {"join", "rebind"}:
            raise ValueError("enrollment mode must be join or rebind")
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
            "status": (
                "PENDING_REGISTRATION"
                if mode == "join"
                else "REBIND_PENDING_REGISTRATION"
            ),
            "mode": mode,
            "deploymentCommand": self._deployment_command(token, mode=mode),
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


class DataPlaneBootstrapService:
    """Issue short-lived, node-bound grants for the phase-four installer."""

    COSIGN_VERSION = NodeEnrollmentService.COSIGN_VERSION
    COSIGN_SHA_AMD64 = NodeEnrollmentService.COSIGN_SHA_AMD64
    COSIGN_SHA_ARM64 = NodeEnrollmentService.COSIGN_SHA_ARM64
    HYSTERIA_VERSION = "2.12.1"
    HYSTERIA_SHA256 = {
        "amd64": "ffc032c7ca6b78676d337097ca7f61bebc3a90a4f3a656693adf368f304cdbc7",
        "arm64": "c9cd1af6395eee13a937f429ea71b290e3cc571eea2b4d7f8bc7c49c1d23a792",
    }

    def __init__(
        self,
        database,
        panel_url,
        panel_version,
        clock=time.time,
        token_factory=None,
        signature_verifier=None,
        identity_provider=None,
        canary_runner=None,
        hysteria_port=19999,
        verification_slots=8,
    ):
        self.database = database
        self.panel_url = _validate_panel_url(panel_url)
        if not VERSION_PATTERN.fullmatch(str(panel_version or "")):
            raise ValueError("panel version is invalid")
        self.panel_version = str(panel_version)
        self.clock = clock
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self.signature_verifier = signature_verifier or OpenSSLSignatureVerifier()
        self.identity_provider = identity_provider
        self.canary_runner = canary_runner
        if (
            isinstance(hysteria_port, bool)
            or not isinstance(hysteria_port, int)
            or not 1 <= hysteria_port <= 65535
            or hysteria_port in {443, 19995, 19996, 19997}
        ):
            raise ValueError("Hysteria main port is invalid")
        self.hysteria_port = hysteria_port
        self._verification_gate = threading.BoundedSemaphore(verification_slots)

    @staticmethod
    def _reject():
        raise DataPlaneBootstrapRejected("data-plane bootstrap was rejected")

    def _verify(self, purpose, payload, expected_fields, remote_ip):
        if not isinstance(payload, dict) or set(payload) != expected_fields:
            self._reject()
        node_id = payload.get("nodeId")
        sent_at = payload.get("sentAt")
        nonce = payload.get("nonce")
        signature_text = payload.get("signature")
        if not isinstance(node_id, str) or not OBJECT_ID_PATTERN.fullmatch(node_id):
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
            signature = base64.b64decode(signature_text, validate=True)
            remote_ip = _normalize_ip(remote_ip)
        except (TypeError, ValueError):
            self._reject()
        if len(nonce_bytes) != 32 or len(signature) != 64:
            self._reject()
        node = self.database.get_node_for_heartbeat(node_id)
        if (
            node is None
            or node["status"] != "pending_verification"
            or node.get("verified_at") is None
            or node.get("policy_state") != "protocol_ready"
            or node.get("data_plane_state")
            not in {
                "bootstrap_issued",
                "data_plane_installed",
                "direct_canary_passed",
                "dns_admitted",
            }
        ):
            self._reject()
        bound_ip = node.get("expected_ip") or node.get("observed_ip")
        if not bound_ip or not secrets.compare_digest(bound_ip, remote_ip):
            self._reject()
        message = canonical_data_plane_request(purpose, payload)
        if not self._verification_gate.acquire(blocking=False):
            self._reject()
        try:
            try:
                verified = self.signature_verifier(
                    node.get("public_key"), message, signature
                )
            except Exception:
                verified = False
        finally:
            self._verification_gate.release()
        if not verified:
            self._reject()
        return node, hashlib.sha256(nonce_bytes).hexdigest(), now, remote_ip

    def _verify_claim(self, payload, remote_ip):
        if (
            not isinstance(payload, dict)
            or set(payload) != DATA_PLANE_CLAIM_FIELDS
            or not isinstance(payload.get("requestId"), str)
            or not OBJECT_ID_PATTERN.fullmatch(payload["requestId"])
        ):
            self._reject()
        node_id = payload.get("nodeId")
        sent_at = payload.get("sentAt")
        nonce = payload.get("nonce")
        signature_text = payload.get("signature")
        if not isinstance(node_id, str) or not OBJECT_ID_PATTERN.fullmatch(node_id):
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
            signature = base64.b64decode(signature_text, validate=True)
            remote_ip = _normalize_ip(remote_ip)
        except (TypeError, ValueError):
            self._reject()
        if len(nonce_bytes) != 32 or len(signature) != 64:
            self._reject()
        node = self.database.get_node_for_heartbeat(node_id)
        if (
            node is None
            or node["status"] != "pending_verification"
            or node.get("verified_at") is None
            or node.get("policy_state") not in {"standby", "protocol_ready"}
            or node.get("last_heartbeat_at") is None
            or int(node["last_heartbeat_at"]) < now - HEARTBEAT_CLOCK_SKEW_SECONDS
            or node.get("data_plane_state")
            not in {
                "not_issued",
                "bootstrap_issued",
                "data_plane_installed",
                "direct_canary_passed",
                "dns_admitted",
            }
        ):
            self._reject()
        bound_ip = node.get("expected_ip") or node.get("observed_ip")
        if not bound_ip or not secrets.compare_digest(bound_ip, remote_ip):
            self._reject()
        message = canonical_data_plane_request("claim", payload)
        if not self._verification_gate.acquire(blocking=False):
            self._reject()
        try:
            try:
                verified = self.signature_verifier(
                    node.get("public_key"), message, signature
                )
            except Exception:
                verified = False
        finally:
            self._verification_gate.release()
        if not verified:
            self._reject()
        return node, hashlib.sha256(nonce_bytes).hexdigest(), now, remote_ip

    def _identity(self):
        if self.identity_provider is None:
            self._reject()
        try:
            identity = self.identity_provider()
        except Exception:
            self._reject()
        expected = {
            "certificatePem",
            "privateKeyPem",
            "certificateFileSha256",
            "certificateDerSha256",
            "privateKeyPublicSha256",
            "egressPolicy",
        }
        if (
            not isinstance(identity, dict)
            or set(identity) != expected
            or not isinstance(identity.get("certificatePem"), str)
            or not identity["certificatePem"].startswith("-----BEGIN CERTIFICATE-----\n")
            or not isinstance(identity.get("privateKeyPem"), str)
            or re.match(
                r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----\n",
                identity["privateKeyPem"],
            )
            is None
            or identity.get("egressPolicy") not in {"web", "full"}
            or any(
                not isinstance(identity.get(field), str)
                or not SHA256_PATTERN.fullmatch(identity[field])
                for field in (
                    "certificateFileSha256",
                    "certificateDerSha256",
                    "privateKeyPublicSha256",
                )
            )
        ):
            self._reject()
        return identity

    def _deployment_command(self, token):
        tag = "v{}".format(self.panel_version)
        repository = "https://github.com/Elegying/Hysteria2-panel"
        installer = (
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
bootstrap_tmp="$(mktemp -d -t hy2panel-data-plane.XXXXXXXX)"
trap 'rm -rf -- "$bootstrap_tmp"' EXIT HUP INT TERM
case "$(uname -m)" in
  x86_64|amd64) cosign_asset=cosign-linux-amd64; cosign_sha={cosign_sha_amd64} ;;
  aarch64|arm64) cosign_asset=cosign-linux-arm64; cosign_sha={cosign_sha_arm64} ;;
  *) echo '仅支持 Linux amd64 和 arm64' >&2; exit 1 ;;
esac
curl -q -fL --connect-timeout 10 --max-time 300 \
  "https://github.com/sigstore/cosign/releases/download/v{cosign_version}/$cosign_asset" \
  -o "$bootstrap_tmp/cosign"
printf '%s  %s\\n' "$cosign_sha" "$bootstrap_tmp/cosign" | sha256sum --check --status
chmod 0700 "$bootstrap_tmp/cosign"
curl -q -fL --connect-timeout 10 --max-time 300 {installer} -o "$bootstrap_tmp/install.sh"
curl -q -fL --connect-timeout 10 --max-time 300 {bundle} -o "$bootstrap_tmp/install.sh.sigstore.json"
"$bootstrap_tmp/cosign" verify-blob "$bootstrap_tmp/install.sh" \
  --bundle "$bootstrap_tmp/install.sh.sigstore.json" \
  --certificate-identity {identity} \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
bash -n "$bootstrap_tmp/install.sh"
export HY2PANEL_PANEL_URL={panel_url}
export HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN={token}
export PANEL_REF={tag}
/bin/bash "$bootstrap_tmp/install.sh" --activate-data-plane
unset HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN
""".format(
            cosign_sha_amd64=self.COSIGN_SHA_AMD64,
            cosign_sha_arm64=self.COSIGN_SHA_ARM64,
            cosign_version=self.COSIGN_VERSION,
            installer=_single_quote(installer),
            bundle=_single_quote(bundle),
            identity=_single_quote(identity),
            panel_url=_single_quote(self.panel_url),
            token=_single_quote(token),
            tag=_single_quote(tag),
        )

    def issue(self, node_id, actor):
        node_id = str(node_id or "")
        if not re.fullmatch(r"[0-9a-f]{32}", node_id):
            raise ValueError("node is not eligible for data-plane bootstrap")
        actor = _normalize_name(actor)
        token = str(self.token_factory())
        if not TOKEN_PATTERN.fullmatch(token):
            raise RuntimeError("secure bootstrap token generation failed")
        node = self.database.get_node_for_heartbeat(node_id)
        bound_ip = None if node is None else node.get("expected_ip") or node.get("observed_ip")
        now = int(self.clock())
        record = self.database.create_data_plane_bootstrap_grant(
            node_id=node_id,
            token_digest=hashlib.sha256(token.encode("ascii")).hexdigest(),
            bound_ip=bound_ip,
            actor=actor,
            created_at=now,
            expires_at=now + 600,
        )
        if record is None:
            raise ValueError("node is not eligible for data-plane bootstrap")
        return {
            "nodeId": record["node_id"],
            "grantId": record["grant_id"],
            "expiresAt": record["expires_at"],
            "maxFetchAttempts": 3,
            "status": "BOOTSTRAP_ISSUED",
            "deploymentCommand": self._deployment_command(token),
        }

    def claim(self, payload, remote_ip):
        node, nonce_digest, now, remote_ip = self._verify_claim(payload, remote_ip)
        token = str(self.token_factory())
        if not TOKEN_PATTERN.fullmatch(token):
            raise RuntimeError("secure bootstrap token generation failed")
        record = self.database.create_data_plane_bootstrap_grant(
            node_id=node["node_id"],
            token_digest=hashlib.sha256(token.encode("ascii")).hexdigest(),
            bound_ip=remote_ip,
            actor="system:auto-onboarding",
            created_at=now,
            expires_at=now + 600,
            auto_enable=True,
            nonce_digest=nonce_digest,
        )
        if record is None:
            self._reject()
        return {
            "nodeId": record["node_id"],
            "grantId": record["grant_id"],
            "expiresAt": record["expires_at"],
            "maxFetchAttempts": 3,
            "status": "AUTO_BOOTSTRAP_ISSUED",
            "bootstrapToken": token,
        }

    def fetch(self, payload, remote_ip):
        if (
            not isinstance(payload, dict)
            or set(payload) != DATA_PLANE_BOOTSTRAP_FIELDS
            or not isinstance(payload.get("bootstrapToken"), str)
            or not TOKEN_PATTERN.fullmatch(payload["bootstrapToken"])
            or not isinstance(payload.get("requestId"), str)
            or not OBJECT_ID_PATTERN.fullmatch(payload["requestId"])
        ):
            self._reject()
        node, nonce_digest, now, remote_ip = self._verify(
            "bootstrap", payload, DATA_PLANE_BOOTSTRAP_FIELDS, remote_ip
        )
        grant = self.database.fetch_data_plane_bootstrap(
            node["node_id"],
            hashlib.sha256(payload["bootstrapToken"].encode("ascii")).hexdigest(),
            remote_ip,
            nonce_digest,
            now,
        )
        if grant is None:
            self._reject()
        identity = self._identity()
        result = {
            "grantId": grant["grant_id"],
            "expiresAt": grant["expires_at"],
            "fetchAttempt": grant["fetch_attempts"],
            "maxFetchAttempts": 3,
            "configProtocolVersion": 1,
            "hysteriaVersion": self.HYSTERIA_VERSION,
            "hysteriaSha256": dict(self.HYSTERIA_SHA256),
            "ports": {"main": self.hysteria_port, "udp443": 443},
        }
        result.update(identity)
        if len(
            json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ) > DATA_PLANE_RESPONSE_LIMIT:
            self._reject()
        return result

    def ack(self, payload, remote_ip):
        boolean_fields = (
            "servicesHealthy",
            "statsHealthy",
            "udp19999Listening",
            "udp443Listening",
            "tcp19999Listening",
            "tcp443Listening",
        )
        digest_fields = (
            "certificateFileSha256",
            "certificateDerSha256",
            "privateKeyPublicSha256",
        )
        if (
            not isinstance(payload, dict)
            or set(payload) != DATA_PLANE_ACK_FIELDS
            or not isinstance(payload.get("bootstrapToken"), str)
            or not TOKEN_PATTERN.fullmatch(payload["bootstrapToken"])
            or not isinstance(payload.get("requestId"), str)
            or not OBJECT_ID_PATTERN.fullmatch(payload["requestId"])
            or any(payload.get(field) is not True for field in boolean_fields)
            or any(
                not isinstance(payload.get(field), str)
                or not SHA256_PATTERN.fullmatch(payload[field])
                for field in digest_fields
            )
            or payload.get("hysteriaVersion") != self.HYSTERIA_VERSION
            or payload.get("egressPolicy") not in {"web", "full"}
            or payload.get("configProtocolVersion") != 1
        ):
            self._reject()
        node, nonce_digest, now, remote_ip = self._verify(
            "ack", payload, DATA_PLANE_ACK_FIELDS, remote_ip
        )
        identity = self._identity()
        if any(
            not secrets.compare_digest(payload[field], identity[field])
            for field in digest_fields
        ) or not secrets.compare_digest(
            payload["egressPolicy"], identity["egressPolicy"]
        ):
            self._reject()
        token_digest = hashlib.sha256(
            payload["bootstrapToken"].encode("ascii")
        ).hexdigest()
        automatic_canary = self.database.data_plane_bootstrap_requires_canary(
            node["node_id"], token_digest, remote_ip, now
        )
        if automatic_canary:
            if self.canary_runner is None:
                self._reject()
            try:
                self.canary_runner(
                    node_ip=remote_ip,
                    main_port=self.hysteria_port,
                    token=payload["bootstrapToken"],
                    pin_sha256=identity["certificateDerSha256"],
                )
            except Exception:
                self._reject()
        acknowledged_at = int(self.clock())
        acknowledged = self.database.acknowledge_data_plane_bootstrap(
            node["node_id"],
            token_digest,
            remote_ip,
            nonce_digest,
            acknowledged_at,
            automatic_canary_passed=automatic_canary,
        )
        if not acknowledged:
            self._reject()
        return {
            "nodeId": node["node_id"],
            "status": (
                "DIRECT_CANARY_PASSED"
                if automatic_canary
                else "DATA_PLANE_INSTALLED"
            ),
        }
