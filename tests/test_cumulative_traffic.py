"""Bounded, non-destructive accounting through HTTP and durable restart boundaries."""

import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import node_agent


class CumulativeTrafficTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spool = node_agent.DurableTrafficSpool(self.root / "spool")
        self.traffic = {"alice": {"tx": 100, "rx": 200}}
        self.epoch = "a" * 32
        self.paths = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fixture.paths.append(self.path)
                body = json.dumps(fixture.traffic, ensure_ascii=False, separators=(",", ":")).encode()
                if "clear=1" in self.path:
                    fixture.traffic = {}
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

        def opener(request, **options):
            parsed = urllib.parse.urlsplit(request.full_url)
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
            return urllib.request.urlopen(
                "http://127.0.0.1:{}{}".format(self.server.server_port, path), **options
            )

        self.client = node_agent.LocalStatsClient("http://127.0.0.1:19997", "x" * 32, opener=opener)
        self.collector = self.restart()

    def restart(self, clients=None):
        return node_agent.CumulativeTrafficCollector(
            clients or [self.client], self.spool, epoch_reader=lambda _: self.epoch
        )

    def total(self):
        return sum(c["tx"] + c["rx"] for b in self.spool.pending() for c in b["traffic"].values())

    def test_original_oversize_case_is_preserved_and_partitioned(self):
        self.traffic = {"测" * 60 + format(i, "04d"): {"tx": 100, "rx": 200}
                        for i in range(2550)}
        original = copy.deepcopy(self.traffic)
        self.assertEqual(765000, self.collector.collect(100, []))
        self.assertEqual(765000, self.total())
        self.assertEqual(original, self.traffic)
        self.assertEqual(["/traffic"], self.paths)
        self.assertEqual(0, self.restart().collect(101, []))
        self.assertEqual(765000, self.total())

    def test_oversize_or_invalid_read_never_clears_the_core(self):
        with mock.patch("node_agent.LOCAL_CUMULATIVE_RESPONSE_MAX_BYTES", 10):
            with self.assertRaises(node_agent.ProtocolError):
                self.collector.collect(100, [])
        self.assertEqual(300, sum(self.traffic["alice"].values()))
        self.assertEqual([], self.spool.pending())
        self.assertEqual(300, self.collector.collect(101, []))
        self.assertEqual(["/traffic", "/traffic"], self.paths)

    def test_agent_restart_counts_only_new_bytes_and_core_restart_starts_new_epoch(self):
        self.collector.collect(100, [])
        self.traffic["alice"]["tx"] += 7
        self.assertEqual(7, self.restart().collect(101, []))
        self.epoch = "b" * 32
        self.traffic = {"alice": {"tx": 1000, "rx": 2000}}
        self.assertEqual(3000, self.restart().collect(102, []))
        self.assertEqual(3307, self.total())

    def test_unexpected_external_clear_is_rejected_without_advancing_cursor(self):
        self.collector.collect(100, [])
        before = self.collector.path.read_bytes()
        self.traffic = {}
        with self.assertRaisesRegex(node_agent.ProtocolError, "outside the collector"):
            self.collector.collect(101, [])
        self.assertEqual(before, self.collector.path.read_bytes())
        self.assertEqual(300, self.total())

    def test_restart_after_spool_commit_reuses_ids_without_counting_twice(self):
        persist = self.spool.persist_collections

        def committed_then_interrupted(batches):
            persist(batches)
            raise OSError("process interrupted after spool commit")

        with mock.patch.object(self.spool, "persist_collections", side_effect=committed_then_interrupted):
            with self.assertRaises(OSError):
                self.collector.collect(100, [])
        original = self.spool.pending()
        self.assertTrue(self.restart().document["pending"])
        self.restart().recover()
        self.assertEqual(original, self.spool.pending())
        self.assertEqual(0, self.restart().collect(101, []))
        self.assertEqual(300, self.total())

    def test_disk_full_preserves_journal_and_source_then_recovers(self):
        with mock.patch.object(self.spool, "persist_collections", side_effect=node_agent.TrafficSpoolFullError("full")):
            with self.assertRaises(node_agent.TrafficSpoolFullError):
                self.collector.collect(100, [])
        self.traffic["alice"]["rx"] += 50
        self.assertEqual(300, self.restart().recover())
        self.assertEqual(50, self.restart().collect(102, []))
        self.assertEqual(350, self.total())

    def test_one_endpoint_failure_preserves_other_and_single_endpoint_maintenance(self):
        secondary = mock.Mock(base_url="http://127.0.0.1:19995")
        secondary.cumulative_traffic.side_effect = node_agent.ProtocolError("offline")
        collector = self.restart([self.client, secondary])
        with self.assertRaises(node_agent.ProtocolError):
            collector.collect(100, [])
        self.assertEqual(300, self.total())
        secondary.cumulative_traffic.side_effect = None
        secondary.cumulative_traffic.return_value = {"alice": {"tx": 10, "rx": 20}}
        self.assertEqual(30, self.restart([self.client, secondary]).collect(101, []))
        self.assertEqual(0, self.restart().collect(102, []))
        self.assertEqual(330, self.total())

    def test_service_identity_must_stay_stable_during_the_read(self):
        collector = self.restart()
        collector.epoch_reader = mock.Mock(side_effect=["a" * 32, "b" * 32])
        with self.assertRaisesRegex(node_agent.ProtocolError, "restarted during"):
            collector.collect(100, [])
        self.assertEqual([], self.spool.pending())
        self.assertFalse(collector.path.exists())

    def test_service_epoch_uses_only_fixed_units_and_rejects_unavailable_identity(self):
        with mock.patch("node_agent.subprocess.run", return_value=mock.Mock(returncode=0, stdout=b"a" * 32 + b"\n")) as run:
            self.assertEqual("a" * 32, node_agent._stats_service_epoch(self.client))
            self.assertEqual("hysteria2-panel-node-hysteria-main.service", run.call_args.args[0][-1])
        with mock.patch("node_agent.subprocess.run", return_value=mock.Mock(returncode=0, stdout=b"\n")):
            with self.assertRaises(node_agent.ProtocolError):
                node_agent._stats_service_epoch(self.client)

    def test_full_spool_still_uploads_backlog_and_recovers_on_next_cycle(self):
        self.spool.max_entries = 1
        self.spool.enqueue({"old": {"tx": 1, "rx": 2}}, 90)
        protocol = mock.Mock()
        protocol.poll_commands.return_value = []
        uploaded = []

        def acknowledge(batch):
            uploaded.append(batch)
            return {"batchId": batch["batchId"], "committed": True}

        protocol.send_traffic.side_effect = acknowledge
        state = node_agent.ProtocolState(self.root / "state" / "protocol.json")
        cycle = node_agent.NodeControlCycle(
            protocol, self.client, self.spool, state, clock=lambda: 100,
            traffic_collector=self.collector,
        )
        cycle._next_domain_collection_at = 1000
        with self.assertRaises(node_agent.TrafficSpoolFullError):
            cycle.run_once()
        self.assertEqual(1, len(uploaded))
        self.assertEqual([], self.spool.pending())
        self.assertEqual(300, cycle._collect_to_spool())
        self.assertEqual(300, self.total())

    def test_cli_factory_uploads_non_destructive_http_samples(self):
        options = node_agent._parser().parse_args([
            "control-once", "--private-key", str(self.root / "node.key"),
            "--state-file", str(self.root / "registration.json"),
            "--protocol-state", str(self.root / "protocol.json"),
            "--spool-dir", str(self.spool.path),
            "--stats-url", self.client.base_url,
        ])
        protocol = mock.Mock()
        uploaded = []

        def acknowledge(batches, snapshot):
            uploaded.extend(batches)
            return {"acceptedAt": 100, "commands": [],
                    "traffic": [{"batchId": b["batchId"], "committed": True} for b in batches],
                    "online": {"sequence": snapshot["sequence"]}}

        protocol.send_control_cycle.side_effect = acknowledge
        with mock.patch.dict(node_agent.os.environ, {"HY2PANEL_STATS_SECRET": "x" * 32}), \
                mock.patch.object(node_agent, "NodeProtocolClient", return_value=protocol), \
                mock.patch.object(node_agent, "LocalStatsClient", return_value=self.client):
            cycle = node_agent._make_control_cycle(options)
        cycle.traffic_collector.epoch_reader = lambda _: self.epoch
        cycle.clock = lambda: 100
        cycle._next_domain_collection_at = 1000
        with mock.patch.object(self.client, "online", return_value={}):
            cycle.run_once()
        self.assertEqual(["/traffic"], self.paths)
        self.assertEqual(300, sum(sum(c.values()) for b in uploaded for c in b["traffic"].values()))
        self.assertEqual(300, sum(self.traffic["alice"].values()))
        self.assertEqual([], self.spool.pending())

    def test_failed_write_keeps_domain_time_without_backdating_new_traffic(self):
        now = [100]
        domains = [{"user": "alice", "domain": "example.test", "tx": 3, "rx": 7}]
        cycle = node_agent.NodeControlCycle(
            mock.Mock(), self.client, self.spool,
            node_agent.ProtocolState(self.root / "protocol.json"), clock=lambda: now[0],
            traffic_collector=self.collector,
        )
        cycle.domain_usage_collector = mock.Mock()
        cycle.domain_usage_collector.collect.return_value = domains
        with mock.patch.object(self.collector, "_save", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                cycle._collect_to_spool()
        now[0] = 200
        self.traffic["alice"]["tx"] += 50
        self.assertEqual(350, cycle._collect_to_spool())
        batches = self.spool.pending()
        self.assertEqual([200], [b["observedAt"] for b in batches if b["traffic"]])
        self.assertEqual([100], [b["observedAt"] for b in batches if b.get("domains")])
        self.assertEqual(350, self.total())
        cycle.domain_usage_collector.collect.assert_called_once()
