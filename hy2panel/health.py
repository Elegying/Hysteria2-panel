"""Cached liveness-adjacent state for readiness and local metrics."""

import ipaddress
import threading
import time


REQUIRED_WORKERS = ("internal-auth", "traffic-collector")


def _signed_whole_seconds(value):
    whole = int(value)
    if value > 0:
        return max(1, whole)
    if value < 0:
        return min(-1, whole)
    return 0


def is_loopback_address(value):
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


class RuntimeHealth:
    def __init__(
        self,
        database_probe,
        clock=time.monotonic,
        wall_clock=time.time,
        stats_stale_after=30,
        certificate_expiry_probe=None,
        certificate_validity_probe=None,
    ):
        self.database_probe = database_probe
        self.clock = clock
        self.wall_clock = wall_clock
        self.stats_stale_after = max(1, int(stats_stale_after))
        self.certificate_expiry_probe = certificate_expiry_probe
        self.certificate_validity_probe = certificate_validity_probe
        self.lock = threading.Lock()
        self.workers = {name: False for name in REQUIRED_WORKERS}
        self.database_ok = False
        self.last_stats_success = None
        self.stats_ok = False
        self.stats_failures = 0
        self.certificate_expires_at = None
        self.certificate_not_before = None
        self.refresh_database()
        self.refresh_certificate()

    def refresh_database(self):
        try:
            available = bool(self.database_probe())
        except Exception:
            available = False
        with self.lock:
            self.database_ok = available
        return available

    def mark_worker(self, name, running):
        if name not in REQUIRED_WORKERS:
            return
        with self.lock:
            self.workers[name] = bool(running)

    def refresh_certificate(self):
        if (
            self.certificate_expiry_probe is None
            and self.certificate_validity_probe is None
        ):
            return True
        try:
            if self.certificate_validity_probe is not None:
                not_before, expires_at = self.certificate_validity_probe()
                not_before = float(not_before)
            else:
                not_before = None
                expires_at = self.certificate_expiry_probe()
            expires_at = float(expires_at)
            available = expires_at > 0 and (
                not_before is None or 0 < not_before < expires_at
            )
        except Exception:
            not_before = None
            expires_at = None
            available = False
        with self.lock:
            self.certificate_not_before = not_before if available else None
            self.certificate_expires_at = expires_at if available else None
        return available

    def certificate_status(self):
        with self.lock:
            expires_at = self.certificate_expires_at
            not_before = self.certificate_not_before
            configured = (
                self.certificate_expiry_probe is not None
                or self.certificate_validity_probe is not None
            )
        if expires_at is None:
            return {
                "configured": configured,
                "expires_at": None,
                "not_before": None,
                "seconds_remaining": None,
                "seconds_until_valid": None,
                "level": "unknown" if configured else "unmonitored",
            }
        now = self.wall_clock()
        remaining_delta = expires_at - now
        until_valid_delta = (
            None if not_before is None else not_before - now
        )
        remaining = _signed_whole_seconds(remaining_delta)
        until_valid = (
            None
            if until_valid_delta is None
            else _signed_whole_seconds(until_valid_delta)
        )
        if until_valid_delta is not None and until_valid_delta > 0:
            level = "not-yet-valid"
        elif remaining_delta <= 0:
            level = "expired"
        elif remaining_delta <= 30 * 86400:
            level = "critical"
        elif remaining_delta <= 90 * 86400:
            level = "warning"
        elif remaining_delta <= 180 * 86400:
            level = "notice"
        else:
            level = "ok"
        return {
            "configured": True,
            "expires_at": expires_at,
            "not_before": not_before,
            "seconds_remaining": remaining,
            "seconds_until_valid": until_valid,
            "level": level,
        }

    def record_stats_sync(self, success):
        with self.lock:
            self.stats_ok = bool(success)
            if success:
                self.last_stats_success = self.clock()
            else:
                self.stats_failures += 1

    def readiness(self):
        now = self.clock()
        certificate = self.certificate_status()
        with self.lock:
            stats_recent = (
                self.stats_ok
                and self.last_stats_success is not None
                and now - self.last_stats_success <= self.stats_stale_after
            )
            checks = {
                "database": self.database_ok,
                "internal_auth": self.workers["internal-auth"],
                "traffic_collector": self.workers["traffic-collector"],
                "stats_sync": stats_recent,
                "certificate": (
                    not certificate["configured"]
                    or certificate["level"]
                    not in {"unknown", "not-yet-valid", "expired"}
                ),
            }
        return all(checks.values()), checks

    def prometheus_metrics(self):
        ready, checks = self.readiness()
        with self.lock:
            failures = self.stats_failures
        certificate = self.certificate_status()
        values = [
            ("hy2panel_ready", ready),
            ("hy2panel_database_ready", checks["database"]),
            ("hy2panel_internal_auth_worker_up", checks["internal_auth"]),
            ("hy2panel_traffic_collector_worker_up", checks["traffic_collector"]),
            ("hy2panel_stats_sync_recent", checks["stats_sync"]),
            ("hy2panel_certificate_valid", checks["certificate"]),
        ]
        lines = ["{} {}".format(name, 1 if value else 0) for name, value in values]
        lines.append("hy2panel_stats_sync_failures_total {}".format(failures))
        if certificate["seconds_remaining"] is not None:
            lines.append(
                "hy2panel_certificate_expiry_seconds {}".format(
                    certificate["seconds_remaining"]
                )
            )
        if certificate["seconds_until_valid"] is not None:
            lines.append(
                "hy2panel_certificate_valid_from_seconds {}".format(
                    certificate["seconds_until_valid"]
                )
            )
        return "\n".join(lines) + "\n"
