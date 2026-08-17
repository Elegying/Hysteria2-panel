import unittest

from hy2panel.health import RuntimeHealth


class RuntimeHealthTests(unittest.TestCase):
    def test_readiness_requires_database_workers_and_recent_stats_sync(self):
        now = [100.0]
        health = RuntimeHealth(
            database_probe=lambda: True,
            clock=lambda: now[0],
            stats_stale_after=30,
        )

        self.assertFalse(health.readiness()[0])
        health.mark_worker("internal-auth", True)
        health.mark_worker("traffic-collector", True)
        health.record_stats_sync(True)
        self.assertTrue(health.readiness()[0])

        now[0] = 131.0
        ready, checks = health.readiness()
        self.assertFalse(ready)
        self.assertFalse(checks["stats_sync"])

    def test_failed_probe_is_not_ready_and_metrics_are_bounded(self):
        health = RuntimeHealth(database_probe=lambda: False, clock=lambda: 10.0)
        health.mark_worker("internal-auth", True)
        health.mark_worker("traffic-collector", True)
        health.record_stats_sync(False)

        ready, checks = health.readiness()
        metrics = health.prometheus_metrics()

        self.assertFalse(ready)
        self.assertFalse(checks["database"])
        self.assertIn("hy2panel_ready 0\n", metrics)
        self.assertIn("hy2panel_stats_sync_failures_total 1\n", metrics)
        self.assertNotIn("exception", metrics.lower())
        self.assertLess(len(metrics), 4096)


if __name__ == "__main__":
    unittest.main()
