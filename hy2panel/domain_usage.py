"""Bounded destination-domain accounting from Hysteria stream snapshots."""

import ipaddress
import urllib.parse


MAX_DOMAIN_RECORDS = 1000


def normalize_destination(value):
    """Return one canonical DNS name from a Hysteria host:port value."""
    value = str(value or "").strip()
    if not value or len(value) > 320:
        return None
    try:
        host = urllib.parse.urlsplit("//" + value).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.rstrip(".").lower()
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    labels = host.split(".")
    if (
        len(host) > 253
        or len(labels) < 2
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or any(not (character.isalnum() or character == "-") for character in label)
            for label in labels
        )
    ):
        return None
    return host


def validate_domain_records(records):
    if (
        not isinstance(records, list)
        or len(records) > MAX_DOMAIN_RECORDS
        or any(
            not isinstance(record, dict)
            or set(record) != {"user", "domain", "tx", "rx"}
            or not isinstance(record["user"], str)
            or not 1 <= len(record["user"]) <= 64
            or normalize_destination(record["domain"]) != record["domain"]
            or any(
                isinstance(record[field], bool)
                or not isinstance(record[field], int)
                or not 0 <= record[field] <= 2**63 - 1
                for field in ("tx", "rx")
            )
            for record in records
        )
    ):
        raise ValueError("domain usage records are invalid")
    return records


class DomainStreamAccumulator:
    """Convert live stream counters into bounded per-user/domain deltas."""

    def __init__(self, maximum_records=MAX_DOMAIN_RECORDS):
        self.maximum_records = max(1, min(MAX_DOMAIN_RECORDS, int(maximum_records)))
        self._previous = {}
        self._initialized = set()

    @staticmethod
    def _dump_safely(client):
        try:
            return client.dump_streams()
        except Exception:
            return None

    def collect(self, stats_client):
        clients = getattr(stats_client, "clients", (stats_client,))
        totals = {}
        for endpoint, client in enumerate(clients):
            streams = self._dump_safely(client)
            if streams is None:
                continue
            current = {}
            initialized = endpoint in self._initialized
            for stream in streams:
                key = (
                    endpoint,
                    stream["connection"],
                    stream["stream"],
                    stream["initial_at"],
                )
                tx = stream["tx"]
                rx = stream["rx"]
                current[key] = (tx, rx)
                if not initialized:
                    continue
                previous = self._previous.get(key)
                delta_tx = tx if previous is None else max(0, tx - previous[0])
                delta_rx = rx if previous is None else max(0, rx - previous[1])
                if not delta_tx and not delta_rx:
                    continue
                domain = normalize_destination(
                    stream.get("hooked_req_addr") or stream.get("req_addr")
                )
                if domain is None:
                    continue
                aggregate = totals.setdefault(
                    (stream["auth"], domain), {"tx": 0, "rx": 0}
                )
                aggregate["tx"] += delta_tx
                aggregate["rx"] += delta_rx
            self._previous = {
                key: value
                for key, value in self._previous.items()
                if key[0] != endpoint
            }
            self._previous.update(current)
            self._initialized.add(endpoint)
        records = [
            {"user": user, "domain": domain, "tx": value["tx"], "rx": value["rx"]}
            for (user, domain), value in totals.items()
        ]
        records.sort(key=lambda item: (-(item["tx"] + item["rx"]), item["user"], item["domain"]))
        return records[: self.maximum_records]
