"""Signed distributed authentication and accounting contracts."""

import base64
import collections
import hashlib
import ipaddress
import json
import re
import secrets
import threading
import time

from .nodes import OpenSSLSignatureVerifier


NODE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
ERROR_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{0,64}$")
PURPOSES = {"auth", "online", "traffic", "command-poll", "command-ack"}
COMMON_FIELDS = {"nodeId", "sentAt", "nonce", "signature"}
AUTH_FIELDS = COMMON_FIELDS | {"requestId", "entrypoint", "auth", "tx"}
ONLINE_FIELDS = COMMON_FIELDS | {
    "snapshotId",
    "sequence",
    "observedAt",
    "trafficAckedAt",
    "online",
}
TRAFFIC_FIELDS = COMMON_FIELDS | {"batchId", "observedAt", "traffic"}
COMMAND_POLL_FIELDS = COMMON_FIELDS | {"requestId"}
COMMAND_ACK_FIELDS = COMMON_FIELDS | {"commandId", "ok", "errorCode"}
MAX_CLOCK_SKEW_SECONDS = 120
MAX_STATE_AGE_SECONDS = 5
MAX_TRAFFIC_BATCH_AGE_SECONDS = 7 * 86400
MAX_USERS_PER_PAYLOAD = 1000
MAX_COUNTER = 2**63 - 1


class NodeRequestRejected(ValueError):
    """A signed node request failed without disclosing node or user state."""


def canonical_node_request(purpose, payload):
    if purpose not in PURPOSES or not isinstance(payload, dict):
        raise ValueError("node request purpose is invalid")
    signed = {key: value for key, value in payload.items() if key != "signature"}
    return "hy2panel-node-{}-v1\n".format(purpose).encode("ascii") + json.dumps(
        signed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _object_id(value):
    return isinstance(value, str) and OBJECT_ID_PATTERN.fullmatch(value) is not None


def _timestamp(value):
    return not isinstance(value, bool) and isinstance(value, int)


def _user_name(value):
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 64
        and all(ord(character) >= 32 for character in value)
    )


def _online_mapping(value):
    return (
        isinstance(value, dict)
        and len(value) <= MAX_USERS_PER_PAYLOAD
        and all(
            _user_name(name)
            and not isinstance(count, bool)
            and isinstance(count, int)
            and 1 <= count <= 100
            for name, count in value.items()
        )
    )


def _traffic_mapping(value):
    return (
        isinstance(value, dict)
        and len(value) <= MAX_USERS_PER_PAYLOAD
        and all(
            _user_name(name)
            and isinstance(counters, dict)
            and set(counters) == {"tx", "rx"}
            and all(
                not isinstance(counter, bool)
                and isinstance(counter, int)
                and 0 <= counter <= MAX_COUNTER
                for counter in counters.values()
            )
            for name, counters in value.items()
        )
    )


class DistributedControlService:
    """Validate node requests before applying central policy transactions."""

    def __init__(
        self,
        database,
        clock=time.time,
        signature_verifier=None,
        local_state_provider=None,
        verification_slots=8,
        requests_per_minute=480,
    ):
        self.database = database
        self.clock = clock
        self.signature_verifier = signature_verifier or OpenSSLSignatureVerifier()
        self.local_state_provider = local_state_provider
        self._verification_gate = threading.BoundedSemaphore(verification_slots)
        self.requests_per_minute = max(1, int(requests_per_minute))
        self._rate_lock = threading.Lock()
        self._request_times = {}

    @staticmethod
    def _reject():
        raise NodeRequestRejected("node request was rejected")

    def _allow_rate(self, node_id, now):
        with self._rate_lock:
            recent = self._request_times.setdefault(node_id, collections.deque())
            while recent and now - recent[0] >= 60:
                recent.popleft()
            if len(recent) >= self.requests_per_minute:
                return False
            recent.append(now)
            return True

    def _verify(self, purpose, payload, expected_fields, remote_ip):
        if not isinstance(payload, dict) or set(payload) != expected_fields:
            self._reject()
        node_id = payload.get("nodeId")
        sent_at = payload.get("sentAt")
        nonce = payload.get("nonce")
        signature_text = payload.get("signature")
        if not isinstance(node_id, str) or not NODE_ID_PATTERN.fullmatch(node_id):
            self._reject()
        if not _timestamp(sent_at):
            self._reject()
        now = int(self.clock())
        if abs(now - sent_at) > MAX_CLOCK_SKEW_SECONDS:
            self._reject()
        if not isinstance(nonce, str) or not NONCE_PATTERN.fullmatch(nonce):
            self._reject()
        try:
            nonce_bytes = base64.urlsafe_b64decode(nonce + "=")
            signature = base64.b64decode(signature_text, validate=True)
            remote_ip = str(ipaddress.ip_address(remote_ip))
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
        ):
            self._reject()
        bound_ip = node.get("expected_ip") or node.get("observed_ip")
        if not bound_ip or not secrets.compare_digest(bound_ip, remote_ip):
            self._reject()
        if not self._allow_rate(node_id, now):
            self._reject()
        message = canonical_node_request(purpose, payload)
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

    def accept_online_snapshot(self, payload, remote_ip):
        if not isinstance(payload, dict) or set(payload) != ONLINE_FIELDS:
            self._reject()
        if (
            not _object_id(payload.get("snapshotId"))
            or not _timestamp(payload.get("sequence"))
            or payload["sequence"] < 1
            or not _timestamp(payload.get("observedAt"))
            or not _timestamp(payload.get("trafficAckedAt"))
            or not _online_mapping(payload.get("online"))
        ):
            self._reject()
        node, nonce_digest, now, _remote_ip = self._verify(
            "online", payload, ONLINE_FIELDS, remote_ip
        )
        if (
            abs(now - payload["observedAt"]) > MAX_STATE_AGE_SECONDS
            or abs(now - payload["trafficAckedAt"]) > MAX_STATE_AGE_SECONDS
        ):
            self._reject()
        accepted = self.database.accept_node_online_snapshot(
            node["node_id"],
            payload["snapshotId"],
            payload["sequence"],
            payload["observedAt"],
            payload["trafficAckedAt"],
            payload["online"],
            nonce_digest,
            accepted_at=now,
        )
        if not accepted:
            self._reject()
        return {
            "snapshotId": payload["snapshotId"],
            "sequence": payload["sequence"],
            "acceptedAt": now,
        }

    def _local_state(self, now):
        if self.local_state_provider is None:
            self._reject()
        try:
            state = self.local_state_provider()
        except Exception:
            self._reject()
        if (
            not isinstance(state, dict)
            or set(state) != {"online", "observedAt", "trafficAckedAt"}
            or not isinstance(state["online"], dict)
            or not all(
                _user_name(name)
                and not isinstance(count, bool)
                and isinstance(count, int)
                and 0 <= count <= 100
                for name, count in state["online"].items()
            )
            or not _timestamp(state["observedAt"])
            or not _timestamp(state["trafficAckedAt"])
            or abs(now - state["observedAt"]) > MAX_STATE_AGE_SECONDS
            or abs(now - state["trafficAckedAt"]) > MAX_STATE_AGE_SECONDS
        ):
            self._reject()
        return state

    def authorize(self, payload, remote_ip):
        if not isinstance(payload, dict) or set(payload) != AUTH_FIELDS:
            self._reject()
        if (
            not _object_id(payload.get("requestId"))
            or payload.get("entrypoint") not in {"main", "udp443"}
            or not isinstance(payload.get("auth"), str)
            or not 1 <= len(payload["auth"]) <= 512
            or isinstance(payload.get("tx"), bool)
            or not isinstance(payload.get("tx"), int)
            or not 0 <= payload["tx"] <= MAX_COUNTER
        ):
            self._reject()
        node, nonce_digest, now, _remote_ip = self._verify(
            "auth", payload, AUTH_FIELDS, remote_ip
        )
        local_state = self._local_state(now)
        result = self.database.authorize_distributed_node(
            node["node_id"],
            payload["requestId"],
            payload["auth"],
            require_udp_443=payload["entrypoint"] == "udp443",
            local_online=local_state["online"],
            nonce_digest=nonce_digest,
            now=now,
            freshness_seconds=MAX_STATE_AGE_SECONDS,
        )
        if result is None:
            self._reject()
        return result

    def apply_traffic_batch(self, payload, remote_ip):
        if not isinstance(payload, dict) or set(payload) != TRAFFIC_FIELDS:
            self._reject()
        if (
            not _object_id(payload.get("batchId"))
            or not _timestamp(payload.get("observedAt"))
            or payload["observedAt"] > int(self.clock()) + MAX_CLOCK_SKEW_SECONDS
            or payload["observedAt"] < int(self.clock()) - MAX_TRAFFIC_BATCH_AGE_SECONDS
            or not _traffic_mapping(payload.get("traffic"))
        ):
            self._reject()
        node, nonce_digest, now, _remote_ip = self._verify(
            "traffic", payload, TRAFFIC_FIELDS, remote_ip
        )
        result = self.database.apply_node_traffic_batch(
            node["node_id"],
            payload["batchId"],
            payload["traffic"],
            nonce_digest,
            accepted_at=now,
        )
        if result is None:
            self._reject()
        return result

    def poll_commands(self, payload, remote_ip):
        if (
            not isinstance(payload, dict)
            or set(payload) != COMMAND_POLL_FIELDS
            or not _object_id(payload.get("requestId"))
        ):
            self._reject()
        node, nonce_digest, now, _remote_ip = self._verify(
            "command-poll", payload, COMMAND_POLL_FIELDS, remote_ip
        )
        commands = self.database.poll_node_commands(
            node["node_id"], nonce_digest, now
        )
        if commands is None:
            self._reject()
        return {"commands": commands, "polledAt": now}

    def ack_command(self, payload, remote_ip):
        if (
            not isinstance(payload, dict)
            or set(payload) != COMMAND_ACK_FIELDS
            or not _object_id(payload.get("commandId"))
            or not isinstance(payload.get("ok"), bool)
            or not isinstance(payload.get("errorCode"), str)
            or not ERROR_CODE_PATTERN.fullmatch(payload["errorCode"])
            or (payload["ok"] and payload["errorCode"])
        ):
            self._reject()
        node, nonce_digest, now, _remote_ip = self._verify(
            "command-ack", payload, COMMAND_ACK_FIELDS, remote_ip
        )
        acked = self.database.ack_node_command(
            node["node_id"],
            payload["commandId"],
            payload["ok"],
            payload["errorCode"],
            nonce_digest,
            now,
        )
        if acked is None:
            self._reject()
        return {"acked": acked, "commandId": payload["commandId"]}
