import datetime
import tempfile
import unittest
from pathlib import Path

import node_agent
from hysteria2_panel import Database
from hy2panel.domain_usage import DomainStreamAccumulator, normalize_destination


class DomainUsageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "panel.db", b"d" * 32)
        self.database.initialize()
        self.alice = self.database.create_proxy_user("alice")
        self.bob = self.database.create_proxy_user("bob")
        self.observed_at = int(
            datetime.datetime(
                2026, 9, 1, 12, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
            ).timestamp()
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_monthly_user_and_global_top_are_sorted_and_idempotent(self):
        first = [
            {"user": "alice", "domain": "video.example", "tx": 10, "rx": 90},
            {"user": "bob", "domain": "docs.example", "tx": 20, "rx": 180},
        ]
        self.assertTrue(
            self.database.apply_traffic_batch(
                "1" * 32,
                {},
                domain_usage=first,
                observed_at=self.observed_at,
            )
        )
        self.assertFalse(
            self.database.apply_traffic_batch(
                "1" * 32,
                {},
                domain_usage=first,
                observed_at=self.observed_at,
            )
        )
        self.database.apply_traffic_batch(
            "2" * 32,
            {},
            domain_usage=[
                {"user": "alice", "domain": "video.example", "tx": 5, "rx": 5},
                {"user": "alice", "domain": "docs.example", "tx": 1, "rx": 1},
            ],
            observed_at=self.observed_at,
        )

        alice = self.database.domain_usage_top(
            self.alice["id"], now=self.observed_at
        )
        global_top = self.database.domain_usage_top(now=self.observed_at)

        self.assertEqual("2026-09", alice["month"])
        self.assertEqual("alice", alice["user"])
        self.assertEqual(
            [("video.example", 110), ("docs.example", 2)],
            [(item["domain"], item["usedBytes"]) for item in alice["items"]],
        )
        self.assertEqual(
            [("docs.example", 202), ("video.example", 110)],
            [(item["domain"], item["usedBytes"]) for item in global_top["items"]],
        )

    def test_user_reset_and_delete_clear_domain_usage(self):
        for user, batch_id in (("alice", "3" * 32), ("bob", "4" * 32)):
            self.database.apply_traffic_batch(
                batch_id,
                {},
                domain_usage=[
                    {"user": user, "domain": "example.test", "tx": 1, "rx": 2}
                ],
                observed_at=self.observed_at,
            )
        self.database.reset_proxy_user_traffic(self.alice["id"])
        self.assertEqual(
            [],
            self.database.domain_usage_top(
                self.alice["id"], now=self.observed_at
            )["items"],
        )
        self.database.delete_proxy_user(self.bob["id"])
        self.assertEqual(
            [], self.database.domain_usage_top(now=self.observed_at)["items"]
        )

    def test_stream_accumulator_uses_deltas_and_ignores_ip_destinations(self):
        class Client:
            streams = []

            def dump_streams(self):
                return self.streams

        client = Client()
        accumulator = DomainStreamAccumulator()
        client.streams = [
            {
                "auth": "alice",
                "connection": 1,
                "stream": 2,
                "initial_at": "2026-09-01T00:00:00Z",
                "req_addr": "Example.COM.:443",
                "hooked_req_addr": "",
                "tx": 10,
                "rx": 20,
            }
        ]
        self.assertEqual([], accumulator.collect(client))
        client.streams[0]["tx"] = 15
        client.streams[0]["rx"] = 35
        client.streams.append(
            {
                "auth": "alice",
                "connection": 1,
                "stream": 3,
                "initial_at": "2026-09-01T00:00:01Z",
                "req_addr": "192.0.2.1:443",
                "hooked_req_addr": "",
                "tx": 50,
                "rx": 50,
            }
        )
        self.assertEqual(
            [{"user": "alice", "domain": "example.com", "tx": 5, "rx": 15}],
            accumulator.collect(client),
        )
        self.assertEqual("example.com", normalize_destination("Example.COM.:443"))
        self.assertIsNone(normalize_destination("192.0.2.1:443"))

    def test_node_spool_persists_domain_only_batches_until_ack(self):
        spool = node_agent.DurableTrafficSpool(Path(self.temporary.name) / "spool")
        batches = spool.enqueue_collections(
            [],
            observed_at=self.observed_at,
            domains=[
                {"user": "alice", "domain": "example.test", "tx": 3, "rx": 7}
            ],
        )
        self.assertEqual(1, len(batches))
        self.assertEqual({}, batches[0]["traffic"])
        self.assertEqual(10, sum(batches[0]["domains"][0][key] for key in ("tx", "rx")))
        self.assertEqual(batches, spool.pending())
        self.assertTrue(spool.ack(batches[0]["batchId"]))
        self.assertEqual([], spool.pending())


if __name__ == "__main__":
    unittest.main()
