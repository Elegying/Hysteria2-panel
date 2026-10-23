"""Non-destructive local accounting, with restartable samples and stable batch IDs."""

import json
import os
from pathlib import Path
import re
import stat
import subprocess  # nosec B404 -- fixed systemctl executable, property and units.
import tempfile
import uuid

from .operations import _systemctl_environment


LOCAL_STATS_UNITS = (
    "hysteria2-panel-server.service",
    "hysteria2-panel-server-443.service",
)


def service_epoch(unit):
    if unit not in LOCAL_STATS_UNITS:
        raise ValueError("unknown local traffic service")
    result = subprocess.run(  # nosec B603 -- unit is restricted to the fixed allowlist.
        ["/bin/systemctl", "show", "--property=InvocationID", "--value", unit],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=2, check=False, env=_systemctl_environment(),
    )
    value = result.stdout.strip()
    if result.returncode or not re.fullmatch(rb"[0-9a-f]{32}", value):
        raise RuntimeError("local traffic service identity unavailable")
    return value.decode("ascii")


def validate_counters(traffic):
    if not isinstance(traffic, dict) or any(
        not isinstance(name, str) or not 1 <= len(name) <= 64
        or not isinstance(counters, dict) or set(counters) != {"tx", "rx"}
        or any(type(value) is not int or not 0 <= value <= 2**63 - 1
               for value in counters.values())
        for name, counters in traffic.items()
    ):
        raise ValueError("invalid cumulative traffic counters")


class LocalCumulativeCollector:
    """The caller holds the existing process and maintenance collection locks.

    Reload the journal for every operation: a root maintenance helper can have
    advanced it while the panel stayed alive. Only the current sample is replayed.
    """

    def __init__(self, database_path, clients, apply_batch, maximum_bytes):
        self.database_path = Path(database_path)
        self.path = self.database_path.with_name("local-traffic.cumulative.json")
        self.clients = clients
        self.apply_batch = apply_batch
        self.maximum_bytes = maximum_bytes
        self._fresh_batch_id = None

    def _validate(self, document):
        if (not isinstance(document, dict)
                or set(document) != {"version", "endpoints", "pending"}
                or type(document["version"]) is not int or document["version"] != 1
                or not isinstance(document["endpoints"], dict)
                or not set(document["endpoints"]).issubset(LOCAL_STATS_UNITS)):
            raise ValueError("invalid local cumulative journal")
        for state in document["endpoints"].values():
            if (not isinstance(state, dict) or set(state) != {"epoch", "traffic"}
                    or not isinstance(state["epoch"], str)
                    or not re.fullmatch(r"[0-9a-f]{32}", state["epoch"])):
                raise ValueError("invalid local cumulative checkpoint")
            validate_counters(state["traffic"])
        pending = document["pending"]
        if pending is not None:
            if (not isinstance(pending, dict)
                    or set(pending) != {"batch_id", "traffic", "observed_at"}
                    or not isinstance(pending["batch_id"], str)
                    or not re.fullmatch(r"[0-9a-f]{32}", pending["batch_id"])
                    or type(pending["observed_at"]) is not int or pending["observed_at"] < 0):
                raise ValueError("invalid local cumulative sample")
            validate_counters(pending["traffic"])

    def _load(self):
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return {"version": 1, "endpoints": {}, "pending": None}
        with os.fdopen(descriptor, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_uid != self.database_path.stat().st_uid
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_size > self.maximum_bytes):
                raise ValueError("unsafe local cumulative journal")
            raw = handle.read(self.maximum_bytes + 1)
        if len(raw) > self.maximum_bytes:
            raise ValueError("local cumulative journal too large")
        document = json.loads(raw.decode("utf-8"))
        self._validate(document)
        return document

    def _save(self, document):
        encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
        if len(encoded) > self.maximum_bytes:
            raise ValueError("local cumulative journal too large")
        owner = self.database_path.stat()
        descriptor, staged = tempfile.mkstemp(prefix=".local-traffic-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                if os.geteuid() == 0:
                    os.fchown(handle.fileno(), owner.st_uid, owner.st_gid)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged, self.path)
            descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)

    def recover(self, document=None):
        document = self._load() if document is None else document
        pending = document["pending"]
        if pending is not None:
            self.apply_batch(
                pending["batch_id"], pending["traffic"],
                observed_at=pending["observed_at"],
                fresh_local_collection=pending["batch_id"] == self._fresh_batch_id,
            )
            document = dict(document, pending=None)
            self._save(document)
            self._fresh_batch_id = None
        return document

    def collect(self, observed_at, document=None):
        document = self.recover(document)
        endpoints = dict(document["endpoints"])
        merged = {}
        failure = None
        for client in self.clients:
            try:
                epoch = client.service_epoch()
                traffic = client.cumulative_traffic()
                validate_counters(traffic)
                if epoch != client.service_epoch():
                    raise RuntimeError("local traffic service restarted during sampling")
                previous = endpoints.get(client.service_unit, {})
                baseline = previous.get("traffic", {}) if previous.get("epoch") == epoch else {}
                if any(name not in traffic or any(traffic[name][key] < old[key] for key in ("tx", "rx"))
                       for name, old in baseline.items()):
                    raise RuntimeError("local traffic counters were cleared outside the collector")
                for name, counters in traffic.items():
                    delta = {key: counters[key] - baseline.get(name, {}).get(key, 0)
                             for key in ("tx", "rx")}
                    if delta["tx"] or delta["rx"]:
                        total = merged.setdefault(name, {"tx": 0, "rx": 0})
                        for key in ("tx", "rx"):
                            total[key] += delta[key]
                endpoints[client.service_unit] = {"epoch": epoch, "traffic": traffic}
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
                failure = exc
        validate_counters(merged)
        pending = None
        if merged:
            pending = {"batch_id": uuid.uuid4().hex, "traffic": merged, "observed_at": observed_at}
            self._fresh_batch_id = pending["batch_id"]
        if pending is not None or endpoints != document["endpoints"]:
            document = {"version": 1, "endpoints": endpoints, "pending": pending}
            self._save(document)
            self.recover(document)
        if failure is not None:
            raise failure
        return merged
