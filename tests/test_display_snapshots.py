"""Display reads do no accounting writes and share data without stale mutations."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import hysteria2_panel as panel
from hy2panel import mobile_api


class Stats:
    def __init__(self):
        self.collect_and_clear = mock.Mock(return_value={})
        self.online = mock.Mock(return_value={"alice": 1})
        self.dump_streams = mock.Mock(return_value=[])
        self.kick_many = mock.Mock()
        self.kick = mock.Mock()


class DisplaySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = panel.Database(Path(self.temp.name) / "panel.db", b"s" * 32)
        self.db.initialize()
        self.user = self.db.create_proxy_user("alice")
        self.clock = [100.0]
        self.stats = Stats()
        self.usage = panel.UsageManager(self.db, self.stats, clock=lambda: self.clock[0])
        self.app = SimpleNamespace(
            database=self.db, usage_manager=self.usage,
            service_controller=SimpleNamespace(status=mock.Mock(return_value="active")),
            system_metrics=SimpleNamespace(snapshot=lambda: {}, server_ips=lambda: ()),
            node_name="fixture", public_host="example.test", hysteria_port=19999,
        )

    def test_repeated_users_and_overview_reads_never_collect_or_fsync(self):
        self.usage.collect_once()
        self.stats.collect_and_clear.reset_mock()
        self.stats.dump_streams.reset_mock()
        before = self.db.get_proxy_user(self.user["id"])
        with mock.patch.object(panel.os, "fsync", side_effect=AssertionError("display wrote to disk")):
            for _ in range(10):
                users = mobile_api.users_payload(self.app)
                overview = mobile_api.overview_payload(self.app, "0.39.40")
                self.assertTrue(users["available"])
                self.assertEqual(1, overview["users"]["total"])
        self.stats.collect_and_clear.assert_not_called()
        self.stats.dump_streams.assert_not_called()
        self.assertEqual(before, self.db.get_proxy_user(self.user["id"]))
        self.assertIsInstance(users["trafficObservedAt"], int)
        self.assertNotIn("_users", json.dumps(users))
        self.assertNotIn("_node_states", json.dumps(overview))

    def test_overview_queries_each_data_source_and_service_status_once(self):
        with mock.patch.object(self.db, "list_proxy_users_for_usage", wraps=self.db.list_proxy_users_for_usage) as users, \
                mock.patch.object(self.db, "list_nodes", wraps=self.db.list_nodes) as nodes, \
                mock.patch.object(self.db, "list_node_online_states", wraps=self.db.list_node_online_states) as states:
            mobile_api.overview_payload(self.app, "0.39.40")
        self.assertEqual((1, 1, 1), (users.call_count, nodes.call_count, states.call_count))
        self.app.service_controller.status.assert_called_once_with()

    def test_uninitialized_failed_and_stale_accounting_is_not_reported_fresh(self):
        self.assertFalse(self.usage.snapshot()["available"])
        self.usage.collect_once()
        self.assertTrue(self.usage.snapshot()["available"])
        self.clock[0] += 31
        self.assertFalse(self.usage.snapshot()["available"])
        self.usage.collect_once()
        self.assertTrue(self.usage.snapshot()["available"])
        self.stats.collect_and_clear.side_effect = OSError("temporarily unavailable")
        with self.assertRaises(OSError):
            self.usage.collect_once()
        self.assertFalse(self.usage.snapshot()["available"])
        self.assertTrue(self.usage.snapshot()["online_complete"])

    def test_user_mutations_are_visible_without_waiting_for_a_cached_page(self):
        first = mobile_api.users_payload(self.app)
        self.assertEqual(1, first["total"])
        self.db.create_proxy_user("bob")
        self.assertEqual(2, mobile_api.users_payload(self.app)["total"])
        self.db.set_proxy_user_enabled(self.user["id"], False)
        user = next(item for item in mobile_api.users_payload(self.app)["items"] if item["name"] == "alice")
        self.assertFalse(user["enabled"])

    def test_mutations_and_authorization_retain_mandatory_settlement(self):
        self.stats.collect_and_clear.return_value = {"alice": {"tx": 11, "rx": 13}}
        observed = []
        self.usage.run_after_collect(lambda: observed.append(self.db.get_proxy_user(self.user["id"])["tx_bytes"]))
        self.assertEqual([11], observed)
        self.stats.collect_and_clear.assert_called_once_with()
        self.stats.collect_and_clear.reset_mock()
        self.assertTrue(self.usage.authorize("alice"))
        self.stats.collect_and_clear.assert_called_once_with()

    def test_mobile_reprojects_existing_management_freshness_without_requery(self):
        now = int(time.time())
        state = {"node_id": "a" * 32, "name": "node", "status": "pending_verification",
                 "policy_state": "protocol_ready", "data_plane_state": "dns_admitted",
                 "lifecycle_state": "active", "observed_at": now - 80,
                 "traffic_acked_at": now - 80, "accepted_at": now - 80,
                 "online": {"alice": 2}}
        strict = self.db.project_node_online_states([state], now, 43)
        self.assertEqual("stale", strict[0]["online_state"])
        snapshot = {"_node_states": strict, "machine_stats": {"origins": []}}
        node = {**state, "created_at": now - 100, "last_heartbeat_at": now,
                "verified_at": now - 90, "public_key": ""}
        with mock.patch.object(self.db, "list_node_online_states", side_effect=AssertionError("duplicate query")):
            payload = mobile_api.nodes_payload(self.app, snapshot=snapshot, nodes=[node], service_status="active")
        remote = next(item for item in payload["items"] if item["nodeId"] == state["node_id"])
        self.assertEqual("fresh", remote["onlineState"])
        self.assertEqual(2, remote["onlineDevices"])
        self.assertEqual("stale", strict[0]["online_state"])


if __name__ == "__main__":
    unittest.main()
