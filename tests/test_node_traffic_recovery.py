"""Accounting survives collection-size boundaries and transient spool failures."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import node_agent


class TrafficRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.spool = node_agent.DurableTrafficSpool(self.root / "spool")
        self.state = node_agent.ProtocolState(self.root / "state" / "protocol.json")
        self.stats = mock.Mock(spec=node_agent.LocalStatsClient)
        self.stats.dump_streams.return_value = []
        self.stats.online.return_value = {}
        self.protocol = mock.Mock()
        self.cycle = node_agent.NodeControlCycle(
            self.protocol, self.stats, self.spool, self.state, clock=lambda: 100
        )

    def test_large_cleared_responses_partition_without_losing_users(self):
        for count in (999, 1000, 1001, 2400):
            with self.subTest(count=count):
                traffic = {"user-{}".format(i): {"tx": i, "rx": i + 1} for i in range(count)}
                client = node_agent.LocalStatsClient("http://127.0.0.1:19997", "f" * 32)
                with mock.patch.object(client, "_request", return_value=traffic):
                    collected = client.collect_and_clear()
                batches = self.spool.enqueue_many(collected, 100)
                recovered = {}
                for batch in batches:
                    node_agent.DurableTrafficSpool._validate_batch(batch)
                    self.assertLessEqual(len(batch["traffic"]), 1000)
                    self.assertLessEqual(len(self.spool._encode_batch(batch)), node_agent.TRAFFIC_SPOOL_ENTRY_MAX_BYTES)
                    recovered.update(batch["traffic"])
                    self.spool.ack(batch["batchId"])
                self.assertEqual(traffic, recovered)
        combined = node_agent.CombinedLocalStatsClient(client, client)
        with mock.patch.object(client, "_request", return_value=traffic):
            self.assertEqual([traffic, traffic], combined.collect_and_clear_batches())

    def test_write_retries_retain_collection_and_ids_without_clearing_again(self):
        traffic = {"user-{}".format(i): {"tx": 7, "rx": 11} for i in range(1001)}
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at):
                self.stats.collect_and_clear.reset_mock()
                self.stats.collect_and_clear.return_value = traffic
                real_open = os.open
                writes = 0

                def failing_open(path, flags, mode=0o600, **kwargs):
                    nonlocal writes
                    if Path(path).name.startswith(".traffic-"):
                        writes += 1
                        if writes == fail_at:
                            raise OSError("temporary storage failure")
                    return real_open(path, flags, mode, **kwargs)

                with mock.patch("node_agent.os.open", side_effect=failing_open):
                    with self.assertRaises(OSError):
                        self.cycle._collect_to_spool()
                ids = [batch["batchId"] for batch, _ in self.cycle._prepared_collection]
                with self.assertRaisesRegex(node_agent.ProtocolError, "not been persisted"):
                    self.cycle.refresh_snapshot()
                self.assertEqual(18018, self.cycle._collect_to_spool())
                self.stats.collect_and_clear.assert_called_once()
                batches = self.spool.pending()
                self.assertCountEqual(ids, [batch["batchId"] for batch in batches])
                self.assertEqual(1001, sum(len(batch["traffic"]) for batch in batches))
                for batch in batches:
                    self.spool.ack(batch["batchId"])

    def test_retry_after_partial_commit_keeps_ids_and_never_duplicates_bytes(self):
        traffic = {"user-{}".format(i): {"tx": 3, "rx": 5} for i in range(1001)}
        self.stats.collect_and_clear.return_value = traffic
        replace = os.replace
        commits = 0

        def fail_second_commit(source, destination):
            nonlocal commits
            commits += 1
            if commits == 2:
                raise OSError("rename interrupted")
            return replace(source, destination)

        with mock.patch("node_agent.os.replace", side_effect=fail_second_commit):
            with self.assertRaises(OSError):
                self.cycle._collect_to_spool()
        before = self.spool.pending()
        self.cycle._collect_to_spool()
        after = self.spool.pending()
        self.assertEqual(before, after)
        self.stats.collect_and_clear.assert_called_once()
        self.assertEqual(8008, sum(c["tx"] + c["rx"] for b in after for c in b["traffic"].values()))

    def test_partial_endpoint_and_disk_failure_retries_the_cleared_endpoint(self):
        primary = self.stats
        primary.collect_and_clear.return_value = {"alice": {"tx": 9, "rx": 2}}
        secondary = mock.Mock(spec=node_agent.LocalStatsClient)
        secondary.collect_and_clear.side_effect = OSError("endpoint unavailable")
        self.cycle.stats_client = node_agent.CombinedLocalStatsClient(primary, secondary)
        self.cycle._next_domain_collection_at = 1000
        with mock.patch.object(self.spool, "persist_collections", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.cycle._collect_to_spool()
        self.assertEqual(11, self.cycle._collect_to_spool())
        primary.collect_and_clear.assert_called_once()
        secondary.collect_and_clear.assert_called_once()
        self.assertEqual({"alice": {"tx": 9, "rx": 2}}, self.spool.pending()[0]["traffic"])

    def test_quiesce_kicks_more_than_one_hundred_users_in_bounded_batches(self):
        users = {"user-{:03}".format(i): 1 for i in range(205)}
        self.stats.online.side_effect = [users, {}, {}, {}]
        self.stats.collect_and_clear.return_value = {}

        def kick(names):
            self.assertLessEqual(len(names), 100)

        self.stats.kick.side_effect = kick
        self.cycle.quiesce_traffic(sleeper=lambda _: None)
        calls = self.stats.kick.call_args_list
        self.assertEqual([100, 100, 5], [len(call.args[0]) for call in calls])
        self.assertEqual(sorted(users), [name for call in calls for name in call.args[0]])

    def test_spool_rejects_conflicting_content_for_retried_id(self):
        prepared = self.spool.prepare_collections([{"alice": {"tx": 1, "rx": 2}}], 100)
        self.spool.persist_collections(prepared)
        batch = json.loads(prepared[0][1])
        batch["traffic"]["alice"]["tx"] = 99
        with self.assertRaisesRegex(node_agent.ProtocolError, "already exists"):
            self.spool.persist_collections([(batch, self.spool._encode_batch(batch))])

    def test_retained_response_can_free_backlog_when_capacity_is_exhausted(self):
        old = self.spool.enqueue({"alice": {"tx": 1, "rx": 2}}, 90)
        self.spool.max_entries = 1
        self.stats.collect_and_clear.return_value = {"alice": {"tx": 3, "rx": 4}}
        self.protocol.send_traffic.side_effect = lambda batch: {
            "batchId": batch["batchId"], "committed": True,
        }
        self.assertEqual(7, self.cycle._collect_to_spool())
        self.protocol.send_traffic.assert_called_once_with(old)
        self.assertEqual({"alice": {"tx": 3, "rx": 4}}, self.spool.pending()[0]["traffic"])
        self.assertIsNone(self.cycle._unpersisted_collection)


if __name__ == "__main__":
    unittest.main()
