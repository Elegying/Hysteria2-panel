"""Cached liveness-adjacent state for readiness and local metrics."""

import ipaddress
import threading
import time


REQUIRED_WORKERS = ("internal-auth", "traffic-collector")


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
        stats_stale_after=30,
    ):
        self.database_probe = database_probe
        self.clock = clock
        self.stats_stale_after = max(1, int(stats_stale_after))
        self.lock = threading.Lock()
        self.workers = {name: False for name in REQUIRED_WORKERS}
        self.database_ok = False
        self.last_stats_success = None
        self.stats_ok = False
        self.stats_failures = 0
        self.refresh_database()

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

    def record_stats_sync(self, success):
        with self.lock:
            self.stats_ok = bool(success)
            if success:
                self.last_stats_success = self.clock()
            else:
                self.stats_failures += 1

    def readiness(self):
        now = self.clock()
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
            }
        return all(checks.values()), checks

    def prometheus_metrics(self):
        ready, checks = self.readiness()
        with self.lock:
            failures = self.stats_failures
        values = [
            ("hy2panel_ready", ready),
            ("hy2panel_database_ready", checks["database"]),
            ("hy2panel_internal_auth_worker_up", checks["internal_auth"]),
            ("hy2panel_traffic_collector_worker_up", checks["traffic_collector"]),
            ("hy2panel_stats_sync_recent", checks["stats_sync"]),
        ]
        lines = ["{} {}".format(name, 1 if value else 0) for name, value in values]
        lines.append("hy2panel_stats_sync_failures_total {}".format(failures))
        return "\n".join(lines) + "\n"
