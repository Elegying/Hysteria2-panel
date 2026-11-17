import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

import node_agent
from hy2panel.diagnostics import (
    DiagnosticGrants,
    GlobalpingClient,
    LineMonitor,
    NetworkHistory,
    ProbeUnavailable,
    read_network_sample,
    valid_network_sample,
)
from hy2panel.distributed import NodeRequestRejected
from hysteria2_panel import BOOTSTRAP_CANARY_USER, handle_auth_payload
from tests.test_distributed_control import DistributedControlCase


def sample(t=10000, rx=100, tx=200, epoch="12345678-1234-1234-1234-123456789abc:eth0"):
    return dict(epoch=epoch, elapsedMs=t, rxBytes=rx, txBytes=tx)


class NetworkTests(unittest.TestCase):
    def test_rates_reset_gaps_replay_and_stale_are_not_fabricated_zeroes(self):
        now = [100.0]
        history = NetworkHistory(clock=lambda: now[0])
        history.accept("local:x", sample())
        self.assertIsNone(history.snapshot(["local:x"])["local:x"]["rx"])
        now[0] += 5
        history.accept("local:x", sample(15000, 5100, 2700))
        row = history.snapshot(["local:x"])["local:x"]
        self.assertEqual((1000, 500), (row["rx"], row["tx"]))
        now[0] += 21
        self.assertFalse(history.snapshot(["local:x"])["local:x"]["fresh"])
        history.accept("local:x", sample(15000, 5100, 2700))
        self.assertFalse(history.snapshot(["local:x"])["local:x"]["fresh"])
        history.accept("local:x", sample(40000, 10000, 10000))
        self.assertIsNone(history.snapshot(["local:x"])["local:x"]["rx"])
        now[0] += 5
        history.accept("local:x", sample(45000, 1, 1))
        self.assertIsNone(history.snapshot(["local:x"])["local:x"]["rx"])
        now[0] += 5
        history.accept("local:x", sample(50000, 1, 1))
        self.assertEqual(0, history.snapshot(["local:x"])["local:x"]["rx"])
        history.accept(
            "local:x", sample(1000, 1, 1, "22345678-1234-1234-1234-123456789abc:eth0")
        )
        self.assertIsNone(history.snapshot(["local:x"])["local:x"]["rx"])

    def test_only_default_route_interfaces_and_same_collector_on_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "proc/net/route": "Iface Destination Gateway Flags\neth0 00000000 01010101 0003\neth1 01010101 00000000 0001\n",
                "proc/net/ipv6_route": "",
                "proc/sys/kernel/random/boot_id": "12345678-1234-1234-1234-123456789abc",
                "proc/uptime": "10.00 100.00",
                "sys/class/net/eth0/statistics/rx_bytes": "100",
                "sys/class/net/eth0/statistics/tx_bytes": "200",
            }
            for path, value in files.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(value)
            self.assertEqual(sample(), read_network_sample(root))
            self.assertEqual(sample(), node_agent.read_network_sample(root))
            (root / "sys/class/net/eth0/statistics/rx_bytes").unlink()
            self.assertIsNone(read_network_sample(root))

    def test_telemetry_validation_is_bounded(self):
        for key, value in [
            ("rxBytes", True),
            ("elapsedMs", -1),
            ("txBytes", 2**63),
            ("epoch", "../../etc/passwd"),
        ]:
            invalid = sample()
            invalid[key] = value
            self.assertFalse(valid_network_sample(invalid))
        self.assertFalse(valid_network_sample(None))


class GrantTests(unittest.TestCase):
    def test_scope_expiry_revoke_and_restart(self):
        now = [10]
        grants = DiagnosticGrants(clock=lambda: now[0])
        token = grants.issue("node1")
        self.assertTrue(grants.allows("node1", token))
        self.assertFalse(grants.allows("node2", token))
        self.assertFalse(DiagnosticGrants().allows("node1", token))
        now[0] += 90
        self.assertFalse(grants.allows("node1", token))
        token = grants.issue("local")
        grants.revoke(token)
        self.assertFalse(grants.active("local"))


class ProbeTests(unittest.TestCase):
    def client(self, country="CN", rcv=3):
        client = GlobalpingClient(sleeper=lambda _: None)
        rows = [
            {
                "probe": {"country": country, "asn": asn, "city": "test"},
                "result": {
                    "status": "finished",
                    "resolvedAddress": "8.8.8.8",
                    "stats": {
                        "total": 3,
                        "rcv": rcv,
                        "loss": 0 if rcv else 100,
                        "avg": 18,
                    },
                },
            }
            for asn in (4134, 4837, 56048)
        ]
        document = {
            "type": "ping",
            "status": "finished",
            "target": "8.8.8.8",
            "measurementOptions": {"protocol": "TCP", "port": 443},
            "results": rows,
        }

        def request(path, body=None, etag=None):
            if path == "probes":
                return [
                    {"location": {"country": "CN", "asn": asn}}
                    for asn in (4134, 4837, 56048)
                ], None
            if path == "measurements":
                self.assertEqual("8.8.8.8", body["target"])
                self.assertNotIn("auth", json.dumps(body))
                return {"id": "test-id"}, None
            return document, "etag"

        client.request = mock.Mock(side_effect=request)
        return client, document

    def test_three_domestic_operators_with_raw_evidence(self):
        client, _ = self.client()
        result = client.tcp("8.8.8.8", 443)
        self.assertEqual(["pass"] * 3, [r["state"] for r in result["rows"]])
        self.assertEqual("test-id", result["measurementId"])

    def test_non_mainland_failed_wrong_target_and_quota(self):
        client, document = self.client(country="HK")
        self.assertEqual(
            ["unknown"] * 3, [r["state"] for r in client.tcp("8.8.8.8", 443)["rows"]]
        )
        client, document = self.client(rcv=0)
        self.assertEqual(
            ["fail"] * 3, [r["state"] for r in client.tcp("8.8.8.8", 443)["rows"]]
        )
        document["target"] = "1.1.1.1"
        with self.assertRaises(ProbeUnavailable):
            client.tcp("8.8.8.8", 443)
        client, _ = self.client()
        client.spent.extend([client.clock()] * 180)
        with self.assertRaises(ProbeUnavailable):
            client.tcp("8.8.8.8", 443)
        with self.assertRaises(ValueError):
            client.tcp("127.0.0.1", 443)
        self.assertFalse(
            any(c.args[0] == "measurements" for c in client.request.call_args_list)
        )

    def test_monitor_never_retains_credentials_or_claims_domestic_udp_passed(self):
        grants = DiagnosticGrants()
        app = SimpleNamespace(database=SimpleNamespace(diagnostic_grants=grants))
        client, _ = self.client()
        monitor = LineMonitor(app, client)
        target = dict(
            ip="8.8.8.8",
            scope="node1",
            host="dns.google",
            pin="a" * 64,
            port=19999,
            hopping=True,
        )

        def check(ip, port, token, pin, trace):
            self.assertTrue(grants.allows("node1", token))
            self.assertFalse(grants.allows("local", token))
            self.assertEqual("https://www.cloudflare.com/cdn-cgi/trace", trace)

        with (
            mock.patch(
                "hy2panel.nodes.HysteriaCanaryRunner._check_entrypoint",
                side_effect=check,
            ),
            mock.patch(
                "socket.getaddrinfo",
                return_value=[(None, None, None, None, ("8.8.8.8", 443))],
            ),
            mock.patch("socket.create_connection"),
        ):
            monitor._check("node:1", target)
        result = monitor.snapshot(["node:1"])["checks"]["node:1"]
        self.assertEqual("unverified", result["domesticUdp"])
        self.assertEqual(3, len(result["proxy"]))
        self.assertFalse(grants.active("node1"))
        self.assertNotIn("token", json.dumps(result))


class SignedDiagnosticTests(DistributedControlCase):
    def test_dedicated_identity_is_read_from_profile_without_mutation(self):
        from hysteria2_panel import sqlite_connection

        node_id = self.nodes[0]
        with sqlite_connection(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE nodes SET tier='premium', identity_json=NULL WHERE node_id=?",
                (node_id,),
            )
            connection.execute(
                "INSERT INTO premium_node_profiles(node_id,region,label,host,port,identity_json) VALUES (?,?,?,?,?,?)",
                (
                    node_id,
                    "us",
                    "dedicated",
                    "dedicated.example.com",
                    443,
                    json.dumps(
                        {
                            "certificateDerSha256": "b" * 64,
                            "certificatePem": "certificate",
                            "privateKeyPem": "never-return-this",
                        }
                    ),
                ),
            )
        with mock.patch.object(
            self.db, "_certificate_server_name", return_value="cert.example.com"
        ):
            identity = self.db.node_diagnostic_identity(node_id)
            self.assertEqual({"pin": "b" * 64, "sni": "cert.example.com"}, identity)
            app = SimpleNamespace(
                database=self.db,
                usage_manager=SimpleNamespace(local_origin_id="local:test"),
                system_metrics=SimpleNamespace(server_ips=lambda: ()),
                pin_sha256="a" * 64,
                public_host="normal.example.com",
            )
            monitor = LineMonitor(app)
            with mock.patch.object(monitor, "_public", return_value=True):
                targets = monitor.targets()
            self.assertEqual("b" * 64, targets["node:" + node_id]["pin"])
            self.assertEqual("cert.example.com", targets["node:" + node_id]["sni"])
            self.assertEqual("a" * 64, targets["node:" + self.nodes[1]]["pin"])
            self.assertEqual(20000, targets["node:" + self.nodes[1]]["hopStart"])
        self.assertNotIn("privateKey", json.dumps(identity))

    def test_internal_auth_is_target_scoped_and_does_not_create_users(self):
        self.accept_empty_snapshots()
        token = self.db.diagnostic_grants.issue(self.nodes[0])

        def auth(index, value):
            data = self.common(self.nodes[index], value)
            data.update(
                requestId=format(value, "032x"), entrypoint="main", auth=token, tx=0
            )
            return self.service.authorize(data, "203.0.113." + str(index + 1))

        self.assertTrue(auth(0, 21)["ok"])
        self.assertFalse(auth(1, 22)["ok"])
        self.db.diagnostic_grants.revoke(token)
        self.assertFalse(auth(0, 23)["ok"])
        self.assertEqual([], self.db.list_proxy_users_for_usage())

    def test_local_internal_auth_respects_quiesce(self):
        token = self.db.diagnostic_grants.issue("local")
        manager = SimpleNamespace(_quiescing=threading.Event())
        body = json.dumps({"auth": token}).encode()
        self.assertEqual(
            BOOTSTRAP_CANARY_USER, handle_auth_payload(self.db, body, manager)[1]["id"]
        )
        manager._quiescing.set()
        self.assertFalse(handle_auth_payload(self.db, body, manager)[1]["ok"])

    def test_signed_telemetry_only_after_snapshot_commit_and_replay_rejected(self):
        self.db.network_history = NetworkHistory(clock=lambda: self.now[0])
        data = self.common(self.nodes[0], 31)
        data.update(
            cycleId="a" * 32,
            trafficBatches=[],
            commandPoll={"requestId": "b" * 32},
            onlineSnapshot={
                "snapshotId": "c" * 32,
                "sequence": 1,
                "observedAt": self.now[0],
                "trafficAckedAt": self.now[0],
                "online": {},
                "networkSample": sample(),
            },
        )
        self.service.control_cycle(data, "203.0.113.1")
        rows = self.db.network_history.snapshot(["node:" + self.nodes[0]])
        self.assertTrue(rows["node:" + self.nodes[0]]["fresh"])
        with self.assertRaises(NodeRequestRejected):
            self.service.control_cycle(data, "203.0.113.1")
        self.assertEqual(
            1,
            len(
                self.db.network_history.snapshot(["node:" + self.nodes[0]])[
                    "node:" + self.nodes[0]
                ]["points"]
            ),
        )
        data["onlineSnapshot"]["networkSample"]["rxBytes"] = True
        with self.assertRaises(NodeRequestRejected):
            self.service.control_cycle(data, "203.0.113.1")
