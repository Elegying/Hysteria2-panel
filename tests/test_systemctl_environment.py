"""A child systemctl must not notify systemd as the long-running parent."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from hy2panel import accounting
import node_agent


class SystemctlEnvironmentTests(unittest.TestCase):
    def test_accounting_and_node_probes_keep_notifications_owned_by_parent(self):
        notification = {"NOTIFY_SOCKET": "/run/test-notify", "WATCHDOG_PID": "42",
                        "WATCHDOG_USEC": "30000000"}
        probes = (
            lambda: accounting.service_epoch(accounting.LOCAL_STATS_UNITS[0]),
            lambda: node_agent._stats_service_epoch(SimpleNamespace(base_url="http://127.0.0.1:19997")),
            lambda: node_agent._systemd_service_active(node_agent.DATA_PLANE_UNITS[0]),
        )
        with mock.patch.dict(os.environ, dict(notification, HY2PANEL_TEST_ENV="preserved")):
            for index, probe in enumerate(probes):
                with self.subTest(probe=index), mock.patch(
                    "subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=b"a" * 32)
                ) as run:
                    probe()
                    environment = run.call_args.kwargs.get("env", os.environ)
                    self.assertEqual("preserved", environment["HY2PANEL_TEST_ENV"])
                    self.assertTrue(all(name not in environment for name in notification))
                    self.assertTrue(all(os.environ[name] == value for name, value in notification.items()))


if __name__ == "__main__":
    unittest.main()
