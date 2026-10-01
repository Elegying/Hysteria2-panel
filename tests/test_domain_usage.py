import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import node_agent
from hysteria2_panel import Database, HysteriaStatsClient, UsageManager
from tests.test_distributed_control import DistributedControlCase
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
        clock = mock.patch("hysteria2_panel.time.time", return_value=self.observed_at)
        clock.start()
        self.addCleanup(clock.stop)

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

    def test_observed_at_includes_domains_outside_top_and_empty_result(self):
        with mock.patch("hysteria2_panel.time.time", return_value=self.observed_at):
            self.database.apply_traffic_batch(
                "5" * 32, {},
                domain_usage=[{"user": "alice", "domain": "large.example", "tx": 100, "rx": 0}],
                observed_at=self.observed_at,
            )
        with mock.patch("hysteria2_panel.time.time", return_value=self.observed_at + 60):
            self.database.apply_traffic_batch(
                "6" * 32, {},
                domain_usage=[{"user": "alice", "domain": "recent.example", "tx": 1, "rx": 0}],
                observed_at=self.observed_at + 60,
            )
        for user_id in (None, self.alice["id"]):
            result = self.database.domain_usage_top(user_id, limit=1, now=self.observed_at)
            self.assertEqual("large.example", result["items"][0]["domain"])
            self.assertEqual(self.observed_at + 60, result["observedAt"])
        self.database.reset_proxy_user_traffic(self.alice["id"])
        result = self.database.domain_usage_top(now=self.observed_at)
        self.assertEqual([], result["items"])
        self.assertEqual(0, result["observedAt"])

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

    def test_reset_cutoff_filters_old_domains_but_not_quota_only_adjustments(self):
        records = [{"user": "alice", "domain": "example.test", "tx": 0, "rx": 100}]
        self.database.reset_proxy_user_traffic(self.alice["id"])
        for index, observed_at in enumerate((self.observed_at - 1, self.observed_at)):
            self.database.apply_traffic_batch(
                format(index + 1, "032x"), {}, domain_usage=records,
                observed_at=observed_at,
            )
        self.assertEqual([], self.database.domain_usage_top(self.alice["id"], now=self.observed_at)["items"])
        self.database.apply_traffic_batch(
            "3" * 32, {}, domain_usage=records, observed_at=self.observed_at,
            origin_id="local:" + "a" * 32, origin_kind="local", fresh_local_collection=True,
        )
        user = self.database.get_proxy_user(self.alice["id"])
        with mock.patch("hysteria2_panel.time.time", return_value=self.observed_at + 10):
            self.database.update_proxy_user_limits(
                user["id"], user["device_limit"], user["traffic_limit_bytes"],
                used_traffic_bytes=0,
            )
        self.database.apply_traffic_batch(
            "4" * 32, {}, domain_usage=records, observed_at=self.observed_at + 1,
        )
        self.assertEqual(200, self.database.domain_usage_top(self.alice["id"], now=self.observed_at)["items"][0]["usedBytes"])
        self.database.reset_all_traffic()
        self.database.apply_traffic_batch(
            "5" * 32, {}, domain_usage=records, observed_at=self.observed_at,
        )
        self.assertEqual([], self.database.domain_usage_top(now=self.observed_at)["items"])

    def test_domain_reset_cutoff_migrates_an_existing_database(self):
        with self.database._connect() as connection:
            schema = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'proxy_users'").fetchone()[0]
            columns = [row["name"] for row in connection.execute("PRAGMA table_info(proxy_users)")
                       if row["name"] != "domain_usage_reset_at"]
            rows = connection.execute("SELECT " + ",".join(columns) + " FROM proxy_users").fetchall()
        legacy = Database(Path(self.temporary.name) / "legacy.db", b"d" * 32)
        with legacy._connect() as connection:
            connection.execute(schema.replace("domain_usage_reset_at INTEGER,", ""))
            connection.executemany("INSERT INTO proxy_users (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")", rows)
        legacy.initialize()
        legacy.initialize()
        with legacy._connect() as connection:
            self.assertEqual([(self.alice["id"], "alice", None), (self.bob["id"], "bob", None)],
                             [tuple(row) for row in connection.execute("SELECT id, name, domain_usage_reset_at FROM proxy_users ORDER BY id")])


class DomainFailureRecoveryTests(unittest.TestCase):
    @staticmethod
    def stream(rx):
        return {"auth": "alice", "connection": 1, "stream": 1, "initial_at": "stable",
                "req_addr": "example.test:443", "hooked_req_addr": "", "tx": 0, "rx": rx}

    def test_failed_traffic_collection_preserves_domains_even_if_stream_disappears(self):
        for last_streams, expected in (([self.stream(150)], 150), ([], 100)):
            with self.subTest(stream_disappears=not last_streams), tempfile.TemporaryDirectory() as directory:
                db = Database(Path(directory) / "panel.db", b"f" * 32)
                db.initialize()
                user = db.create_proxy_user("alice")
                stats = mock.Mock(spec=HysteriaStatsClient)
                stats.online.return_value = {}
                stats.dump_streams.side_effect = [[self.stream(0)], [self.stream(100)], last_streams]
                stats.collect_and_clear.side_effect = [{}, OSError("traffic offline"), {"alice": {"tx": 0, "rx": 150}}]
                manager = UsageManager(db, stats)
                manager.collect_once()
                with self.assertRaisesRegex(OSError, "traffic offline"):
                    manager.collect_once()
                manager.collect_once()
                self.assertEqual(expected, db.domain_usage_top(user["id"])["items"][0]["usedBytes"])
                self.assertEqual(150, db.get_proxy_user(user["id"])["rx_bytes"])

    def test_failed_domain_commit_replays_its_journal_after_restart_once(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "panel.db", b"f" * 32)
            db.initialize()
            user = db.create_proxy_user("alice")
            stats = mock.Mock(spec=HysteriaStatsClient)
            stats.online.return_value = {}
            stats.dump_streams.side_effect = [[self.stream(0)], [self.stream(100)]]
            stats.collect_and_clear.side_effect = [{}, OSError("traffic offline")]
            manager = UsageManager(db, stats)
            manager.collect_once()
            with mock.patch.object(db, "apply_traffic_batch", side_effect=OSError("database unavailable")):
                with self.assertRaises(OSError):
                    manager.collect_once()
            self.assertTrue(manager.pending_traffic_path.exists())
            restarted = UsageManager(db, stats)
            with restarted.lock:
                restarted._flush_pending_traffic_locked()
                restarted._flush_pending_traffic_locked()
            self.assertEqual(100, db.domain_usage_top(user["id"])["items"][0]["usedBytes"])
            self.assertFalse(manager.pending_traffic_path.exists())

    def test_late_ready_node_batch_cannot_restore_reset_domain_history(self):
        fixture = DistributedControlCase("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        now = int(datetime.datetime.now().timestamp())
        with mock.patch("hysteria2_panel.time.time", return_value=now):
            user = fixture.db.create_proxy_user("alice")
            records = [{"user": "alice", "domain": "example.test", "tx": 0, "rx": 100}]
            fixture.db.apply_node_traffic_batch(
                fixture.nodes[0], "a" * 32, {"alice": {"tx": 0, "rx": 100}},
                b"a" * 32, now, domain_usage=records, observed_at=now - 10,
            )
            fixture.db.reset_proxy_user_traffic(user["id"])
            for index, observed_at in enumerate((now - 5, now, now + 1)):
                result = fixture.db.apply_node_traffic_batch(
                    fixture.nodes[0], format(index + 1, "032x"),
                    {"alice": {"tx": 0, "rx": 100}}, bytes([index]) * 32,
                    now + 1, domain_usage=records, observed_at=observed_at,
                )
                self.assertTrue(result["committed"])
                items = fixture.db.domain_usage_top(user["id"], now=now)["items"]
                self.assertEqual([] if observed_at <= now else [100], [item["usedBytes"] for item in items])
            self.assertEqual(100, fixture.db.get_proxy_user(user["id"])["rx_bytes"])


if __name__ == "__main__":
    unittest.main()
