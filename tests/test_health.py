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

    def test_certificate_expiry_has_thresholds_and_expires_readiness(self):
        now = [1_000_000.0]
        expiry = [now[0] + 181 * 86400]
        health = RuntimeHealth(
            database_probe=lambda: True,
            certificate_expiry_probe=lambda: expiry[0],
            clock=lambda: 10.0,
            wall_clock=lambda: now[0],
        )
        health.mark_worker("internal-auth", True)
        health.mark_worker("traffic-collector", True)
        health.record_stats_sync(True)

        self.assertEqual("ok", health.certificate_status()["level"])
        expiry[0] = now[0] + 180 * 86400
        health.refresh_certificate()
        self.assertEqual("notice", health.certificate_status()["level"])
        expiry[0] = now[0] + 90 * 86400
        health.refresh_certificate()
        self.assertEqual("warning", health.certificate_status()["level"])
        expiry[0] = now[0] + 30 * 86400
        health.refresh_certificate()
        self.assertEqual("critical", health.certificate_status()["level"])
        expiry[0] = now[0] - 1
        health.refresh_certificate()

        ready, checks = health.readiness()
        metrics = health.prometheus_metrics()
        self.assertFalse(ready)
        self.assertFalse(checks["certificate"])
        self.assertEqual("expired", health.certificate_status()["level"])
        self.assertIn("hy2panel_certificate_expiry_seconds -1\n", metrics)

    def test_certificate_not_yet_valid_is_not_ready(self):
        now = [1_000_000.0]
        validity = [now[0] + 3600, now[0] + 365 * 86400]
        health = RuntimeHealth(
            database_probe=lambda: True,
            certificate_validity_probe=lambda: tuple(validity),
            clock=lambda: 10.0,
            wall_clock=lambda: now[0],
        )
        health.mark_worker("internal-auth", True)
        health.mark_worker("traffic-collector", True)
        health.record_stats_sync(True)

        ready, checks = health.readiness()

        self.assertFalse(ready)
        self.assertFalse(checks["certificate"])
        self.assertEqual("not-yet-valid", health.certificate_status()["level"])
        self.assertIn(
            "hy2panel_certificate_valid_from_seconds 3600\n",
            health.prometheus_metrics(),
        )

    def test_certificate_subsecond_boundaries_preserve_validity_state(self):
        now = [1_000_000.0]
        validity = [now[0] + 0.5, now[0] + 100]
        health = RuntimeHealth(
            database_probe=lambda: True,
            certificate_validity_probe=lambda: tuple(validity),
            clock=lambda: 10.0,
            wall_clock=lambda: now[0],
        )
        health.mark_worker("internal-auth", True)
        health.mark_worker("traffic-collector", True)
        health.record_stats_sync(True)

        self.assertEqual("not-yet-valid", health.certificate_status()["level"])
        self.assertEqual(
            1, health.certificate_status()["seconds_until_valid"]
        )
        self.assertFalse(health.readiness()[0])

        validity[:] = [now[0] - 100, now[0] + 0.5]
        health.refresh_certificate()
        self.assertEqual("critical", health.certificate_status()["level"])
        self.assertEqual(1, health.certificate_status()["seconds_remaining"])
        self.assertTrue(health.readiness()[0])

        now[0] += 1
        self.assertEqual("expired", health.certificate_status()["level"])
        self.assertEqual(-1, health.certificate_status()["seconds_remaining"])
        self.assertFalse(health.readiness()[0])


if __name__ == "__main__":
    unittest.main()
