import base64
import hashlib
import json
import os
import sqlite3
import socket
import stat
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

import node_agent
from hysteria2_panel import Database, PanelApplication, make_panel_server
from node_agent import (
    collect_data_plane_attestation,
    DataPlaneBootstrapClient,
    ProtocolError,
    prepare_data_plane_bundle,
    render_data_plane_configs,
    run_hysteria_from_template,
    validate_data_plane_identity,
)
from hy2panel.nodes import (
    DataPlaneBootstrapRejected,
    DataPlaneBootstrapService,
    HysteriaCanaryRunner,
    HysteriaIdentityProvider,
    NodeDnsAdmissionReconciler,
    canonical_data_plane_request,
)


class HysteriaCanaryRunnerTests(unittest.TestCase):
    def test_tests_both_entrypoints_through_real_hysteria_and_matches_egress_ip(self):
        configs = []
        processes = []

        class Process:
            def __init__(self):
                self.returncode = None
                processes.append(self)

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 0

            def wait(self, timeout=None):
                return self.returncode

            def kill(self):
                self.returncode = -9

        def popen(argv, **kwargs):
            self.assertEqual(
                ["/opt/hysteria2-panel/bin/hysteria", "client", "--config"],
                argv[:3],
            )
            config_path = Path(argv[3])
            self.assertEqual(0o600, stat.S_IMODE(config_path.stat().st_mode))
            configs.append(json.loads(config_path.read_text()))
            self.assertNotIn("shell", kwargs)
            self.assertIs(kwargs["stdout"], kwargs["stderr"])
            log_stat = os.fstat(kwargs["stdout"].fileno())
            self.assertTrue(stat.S_ISREG(log_stat.st_mode))
            self.assertEqual(0o600, stat.S_IMODE(log_stat.st_mode))
            return Process()

        curl_calls = []
        ipv4_trace = "https://1.1.1.1/cdn-cgi/trace"
        ipv6_trace = "https://[2606:4700:4700::1111]/cdn-cgi/trace"

        def run(argv, **kwargs):
            curl_calls.append(argv)
            if argv[-1] == ipv4_trace:
                observed_ip = "8.8.8.8"
            elif argv[-1] == ipv6_trace:
                observed_ip = "2001:4860:4860::8888"
            else:
                self.fail("canary trace target did not match the node address family")
            return subprocess.CompletedProcess(
                argv, 0, "ip={}\nwarp=off\n".format(observed_ip), ""
            )

        with mock.patch("hy2panel.nodes.subprocess.Popen", side_effect=popen), mock.patch(
            "hy2panel.nodes.subprocess.run", side_effect=run
        ), mock.patch("hy2panel.nodes.socket.create_connection"):
            runner = HysteriaCanaryRunner(
                server_name="vpn.example.test",
                port_factory=iter((39001, 39002, 39003, 39004)).__next__,
                sleep=lambda _seconds: None,
            )
            runner(
                node_ip="8.8.8.8",
                main_port=24443,
                token="canary_" + "T" * 40,
                pin_sha256="ab" * 32,
            )
            runner(
                node_ip="2001:4860:4860::8888",
                main_port=24443,
                token="canary_" + "T" * 40,
                pin_sha256="ab" * 32,
            )

        self.assertEqual(
            [24443, 443, 24443, 443],
            [int(c["server"].rsplit(":", 1)[1]) for c in configs],
        )
        self.assertTrue(all("--max-filesize" in command for command in curl_calls))
        self.assertTrue(all(c["auth"].startswith("canary_") for c in configs))
        self.assertTrue(all(c["tls"]["insecure"] is True for c in configs))
        self.assertTrue(
            all(c["tls"]["pinSHA256"] == ":".join(["AB"] * 32) for c in configs)
        )
        self.assertEqual(
            [ipv4_trace, ipv4_trace, ipv6_trace, ipv6_trace],
            [command[-1] for command in curl_calls],
        )
        self.assertTrue(all("socks5h://127.0.0.1:" in " ".join(c) for c in curl_calls))
        self.assertTrue(all(process.returncode == 0 for process in processes))

    def test_rejects_non_public_target_and_wrong_egress(self):
        runner = HysteriaCanaryRunner(server_name="vpn.example.test")
        with self.assertRaises(ValueError):
            runner(
                node_ip="127.0.0.1",
                main_port=19999,
                token="canary_" + "T" * 40,
                pin_sha256="ab" * 32,
            )
        for invalid_port in (0, 443, 65536, True, "19999"):
            with self.subTest(invalid_port=invalid_port), self.assertRaises(ValueError):
                runner(
                    node_ip="8.8.8.8",
                    main_port=invalid_port,
                    token="canary_" + "T" * 40,
                    pin_sha256="ab" * 32,
                )

        with mock.patch("hy2panel.nodes.subprocess.Popen") as popen:
            with self.assertRaises(RuntimeError):
                runner._verify_trace("ip=1.1.1.1\n", "8.8.8.8")
        popen.assert_not_called()


class NodeDnsAdmissionReconcilerTests(unittest.TestCase):
    def _insert_node(self, node_id, *, policy_state):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """INSERT INTO nodes(
                    node_id, name, expected_ip, observed_ip, status, public_key,
                    hostname, platform, architecture, agent_version, created_at,
                    registered_at, last_seen_at, verified_at, verified_by,
                    last_heartbeat_at, last_heartbeat_ip, policy_state,
                    policy_enabled_at, policy_enabled_by
                ) VALUES (?, 'dns-node', ?, ?, 'pending_verification', ?,
                    'node.example.test', 'linux', 'amd64', '0.30.0', ?, ?, ?,
                    ?, 'admin', ?, ?, ?, ?, 'admin')""",
                (
                    node_id,
                    self.remote_ip,
                    self.remote_ip,
                    base64.b64encode(
                        bytes.fromhex("302a300506032b6570032100") + b"a" * 32
                    ).decode("ascii"),
                    self.now[0],
                    self.now[0],
                    self.now[0],
                    self.now[0],
                    self.now[0],
                    self.remote_ip,
                    policy_state,
                    self.now[0],
                ),
            )

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "panel.db"
        self.db = Database(self.db_path, b"d" * 32)
        self.db.initialize()
        self.now = [2_000_000_000]
        self.node_id = "a" * 32
        self.remote_ip = "8.8.8.8"
        self._insert_node(self.node_id, policy_state="protocol_ready")
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """UPDATE nodes SET data_plane_state = 'direct_canary_passed',
                    data_plane_installed_at = ?, direct_canary_passed_at = ?,
                    last_heartbeat_at = ?, last_snapshot_at = ?,
                    last_traffic_ack_at = ? WHERE node_id = ?""",
                (
                    self.now[0] - 10,
                    self.now[0] - 5,
                    self.now[0],
                    self.now[0],
                    self.now[0],
                    self.node_id,
                ),
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _resolver(addresses):
        def resolve(_host, _port, *, type):
            if type != socket.SOCK_STREAM:
                raise AssertionError("resolver type was not bounded")
            return [
                (
                    socket.AF_INET6 if ":" in address else socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    (address, 443, 0, 0)
                    if ":" in address
                    else (address, 443),
                )
                for address in addresses
            ]

        return resolve

    def test_exact_manual_dns_and_fresh_state_are_admitted_read_only(self):
        reconciler = NodeDnsAdmissionReconciler(
            self.db,
            "vpn.example.test",
            resolver=self._resolver(["1.1.1.1", self.remote_ip]),
            clock=lambda: self.now[0],
        )

        result = reconciler.reconcile()

        self.assertEqual({"checked": 1, "admitted": 1}, result)
        node = next(
            item for item in self.db.list_nodes() if item["node_id"] == self.node_id
        )
        self.assertEqual("dns_admitted", node["data_plane_state"])
        self.assertEqual("system:dns-monitor", node["dns_admitted_by"])

    def test_wrong_missing_private_or_stale_dns_never_changes_state(self):
        cases = (
            self._resolver([]),
            self._resolver(["1.1.1.1"]),
            self._resolver(["127.0.0.1", "10.0.0.1"]),
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("dns failed")),
        )
        for resolver in cases:
            with self.subTest(resolver=resolver):
                result = NodeDnsAdmissionReconciler(
                    self.db,
                    "vpn.example.test",
                    resolver=resolver,
                    clock=lambda: self.now[0],
                ).reconcile()
                self.assertEqual(0, result["admitted"])
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE nodes SET last_snapshot_at = ? WHERE node_id = ?",
                (self.now[0] - 46, self.node_id),
            )
        result = NodeDnsAdmissionReconciler(
            self.db,
            "vpn.example.test",
            resolver=self._resolver([self.remote_ip]),
            clock=lambda: self.now[0],
        ).reconcile()
        self.assertEqual(0, result["admitted"])
        node = next(
            item for item in self.db.list_nodes() if item["node_id"] == self.node_id
        )
        self.assertEqual("direct_canary_passed", node["data_plane_state"])

    def test_reconciliation_never_removes_an_existing_admission(self):
        self.assertTrue(
            self.db.mark_node_dns_admitted(
                self.node_id, "admin", self.now[0]
            )
        )
        result = NodeDnsAdmissionReconciler(
            self.db,
            "vpn.example.test",
            resolver=self._resolver([]),
            clock=lambda: self.now[0] + 60,
        ).reconcile()
        self.assertEqual({"checked": 0, "admitted": 0}, result)
        node = next(
            item for item in self.db.list_nodes() if item["node_id"] == self.node_id
        )
        self.assertEqual("dns_admitted", node["data_plane_state"])
        self.assertIsNone(node["dns_removed_at"])


class DataPlaneBootstrapStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "panel.db"
        self.db = Database(self.db_path, b"b" * 32)
        self.db.initialize()
        self.now = [2_000_000_000]
        self.token = "bootstrap_" + "B" * 40
        self.node_id = "1" * 32
        self.remote_ip = "203.0.113.10"
        self._insert_node(self.node_id, policy_state="protocol_ready")
        self.service = DataPlaneBootstrapService(
            self.db,
            panel_url="https://panel.example.com:19998",
            panel_version="0.27.0",
            clock=lambda: self.now[0],
            token_factory=lambda: self.token,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _insert_node(
        self,
        node_id,
        *,
        status="pending_verification",
        verified=True,
        policy_state="standby",
        address=None,
    ):
        address = address or self.remote_ip
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """INSERT INTO nodes(
                    node_id, name, expected_ip, observed_ip, status, public_key,
                    hostname, platform, architecture, agent_version, created_at,
                    registered_at, last_seen_at, verified_at, verified_by,
                    last_heartbeat_at, last_heartbeat_ip, policy_state,
                    policy_enabled_at, policy_enabled_by
                ) VALUES (?, ?, ?, ?, ?, ?, 'node.example.test', 'linux',
                    'amd64', '0.26.0', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    node_id,
                    "node-{}".format(node_id[:4]),
                    address,
                    address,
                    status,
                    base64.b64encode(
                        bytes.fromhex("302a300506032b6570032100")
                        + bytes([int(node_id[0], 16)]) * 32
                    ).decode("ascii"),
                    self.now[0],
                    self.now[0],
                    self.now[0],
                    self.now[0] if verified else None,
                    "admin" if verified else None,
                    self.now[0],
                    address,
                    policy_state,
                    self.now[0] if policy_state == "protocol_ready" else None,
                    "admin" if policy_state == "protocol_ready" else None,
                ),
            )

    @staticmethod
    def _digest(value):
        return hashlib.sha256(value.encode("ascii")).hexdigest()

    def test_initialize_adds_bootstrap_schema_idempotently(self):
        self.db.initialize()

        with sqlite3.connect(str(self.db_path)) as connection:
            node_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(nodes)")
            }
            grant_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(node_data_plane_bootstrap_grants)"
                )
            }

        self.assertTrue(
            {
                "data_plane_state",
                "data_plane_installed_at",
                "direct_canary_passed_at",
                "dns_admitted_at",
                "dns_admitted_by",
                "dns_removed_at",
                "dns_removed_by",
            }.issubset(node_columns)
        )
        self.assertEqual(
            {
                "grant_id",
                "node_id",
                "token_digest",
                "bound_ip",
                "created_by",
                "created_at",
                "expires_at",
                "fetch_attempts",
                "last_fetched_at",
                "acknowledged_at",
                "revoked_at",
                "automatic_canary",
            },
            grant_columns,
        )

    def test_issue_stores_only_digest_and_generates_fixed_signed_command(self):
        issued = self.service.issue(self.node_id, actor="admin")

        with sqlite3.connect(str(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            grant = connection.execute(
                "SELECT * FROM node_data_plane_bootstrap_grants WHERE grant_id = ?",
                (issued["grantId"],),
            ).fetchone()
            node_state = connection.execute(
                "SELECT data_plane_state FROM nodes WHERE node_id = ?",
                (self.node_id,),
            ).fetchone()[0]

        self.assertEqual(self._digest(self.token), grant["token_digest"])
        self.assertEqual(self.remote_ip, grant["bound_ip"])
        self.assertEqual(self.now[0] + 600, grant["expires_at"])
        self.assertEqual(0, grant["fetch_attempts"])
        self.assertEqual("bootstrap_issued", node_state)
        self.assertNotIn(self.token.encode("ascii"), self.db_path.read_bytes())
        self.assertEqual("BOOTSTRAP_ISSUED", issued["status"])
        self.assertEqual(3, issued["maxFetchAttempts"])
        command = issued["deploymentCommand"]
        self.assertIn("v0.27.0", command)
        self.assertIn("verify-blob", command)
        self.assertIn("--activate-data-plane", command)
        self.assertIn("HY2PANEL_DATA_PLANE_BOOTSTRAP_TOKEN", command)
        self.assertNotIn("server.crt", command)
        self.assertNotIn("server.key", command)
        self.assertNotIn("HY2PANEL_HMAC_KEY", command)
        self.assertNotIn("vpn.example.com", command)
        syntax = subprocess.run(
            ["bash", "-n"],
            input=command,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, syntax.returncode, syntax.stderr)

    def test_only_verified_protocol_ready_active_node_can_issue(self):
        cases = (
            ("2" * 32, "pending_verification", False, "protocol_ready"),
            ("3" * 32, "pending_verification", True, "standby"),
            ("4" * 32, "revoked", True, "protocol_ready"),
        )
        for node_id, status, verified, policy_state in cases:
            with self.subTest(node_id=node_id):
                self._insert_node(
                    node_id,
                    status=status,
                    verified=verified,
                    policy_state=policy_state,
                )
                with self.assertRaises(ValueError):
                    self.service.issue(node_id, actor="admin")

    def test_reissue_revokes_the_previous_grant_atomically(self):
        first = self.service.issue(self.node_id, actor="admin")
        self.service.token_factory = lambda: "replacement_" + "C" * 40

        second = self.service.issue(self.node_id, actor="admin")

        with sqlite3.connect(str(self.db_path)) as connection:
            rows = connection.execute(
                """SELECT grant_id, revoked_at
                FROM node_data_plane_bootstrap_grants
                WHERE node_id = ? ORDER BY created_at, grant_id""",
                (self.node_id,),
            ).fetchall()
        grants = {row[0]: row[1] for row in rows}
        self.assertEqual(self.now[0], grants[first["grantId"]])
        self.assertIsNone(grants[second["grantId"]])

    def test_installed_node_can_reissue_without_losing_canary_or_dns_state(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """UPDATE nodes SET data_plane_state = 'direct_canary_passed',
                    data_plane_installed_at = ?, direct_canary_passed_at = ?,
                    dns_admitted_at = ? WHERE node_id = ?""",
                (
                    self.now[0] - 300,
                    self.now[0] - 200,
                    self.now[0] - 100,
                    self.node_id,
                ),
            )

        issued = self.service.issue(self.node_id, actor="admin")
        digest = self._digest(self.token)
        fetched = self.db.fetch_data_plane_bootstrap(
            self.node_id, digest, self.remote_ip, "6" * 64, self.now[0]
        )
        self.assertIsNotNone(fetched)
        self.assertTrue(
            self.db.acknowledge_data_plane_bootstrap(
                self.node_id,
                digest,
                self.remote_ip,
                "7" * 64,
                self.now[0],
            )
        )

        with sqlite3.connect(str(self.db_path)) as connection:
            node = connection.execute(
                """SELECT data_plane_state, data_plane_installed_at,
                    direct_canary_passed_at, dns_admitted_at
                FROM nodes WHERE node_id = ?""",
                (self.node_id,),
            ).fetchone()
        self.assertEqual(
            (
                "direct_canary_passed",
                self.now[0],
                self.now[0] - 200,
                self.now[0] - 100,
            ),
            node,
        )
        self.assertEqual("BOOTSTRAP_ISSUED", issued["status"])

    def test_fetch_is_bound_replay_safe_and_limited_to_three_attempts(self):
        self.service.issue(self.node_id, actor="admin")
        digest = self._digest(self.token)

        self.assertIsNone(
            self.db.fetch_data_plane_bootstrap(
                self.node_id, digest, "203.0.113.11", "a" * 64, self.now[0]
            )
        )
        first = self.db.fetch_data_plane_bootstrap(
            self.node_id, digest, self.remote_ip, "1" * 64, self.now[0]
        )
        self.assertEqual(1, first["fetch_attempts"])
        self.assertIsNone(
            self.db.fetch_data_plane_bootstrap(
                self.node_id, digest, self.remote_ip, "1" * 64, self.now[0]
            )
        )
        for attempt in (2, 3):
            fetched = self.db.fetch_data_plane_bootstrap(
                self.node_id,
                digest,
                self.remote_ip,
                "{}".format(attempt) * 64,
                self.now[0],
            )
            self.assertEqual(attempt, fetched["fetch_attempts"])
        self.assertIsNone(
            self.db.fetch_data_plane_bootstrap(
                self.node_id, digest, self.remote_ip, "4" * 64, self.now[0]
            )
        )

    def test_expired_grant_fails_without_consuming_an_attempt(self):
        issued = self.service.issue(self.node_id, actor="admin")
        self.now[0] = issued["expiresAt"]

        self.assertIsNone(
            self.db.fetch_data_plane_bootstrap(
                self.node_id,
                self._digest(self.token),
                self.remote_ip,
                "e" * 64,
                self.now[0],
            )
        )
        with sqlite3.connect(str(self.db_path)) as connection:
            attempts = connection.execute(
                """SELECT fetch_attempts
                FROM node_data_plane_bootstrap_grants WHERE grant_id = ?""",
                (issued["grantId"],),
            ).fetchone()[0]
        self.assertEqual(0, attempts)

    def test_ack_burns_grant_and_installs_node_in_one_transaction(self):
        issued = self.service.issue(self.node_id, actor="admin")
        digest = self._digest(self.token)
        self.db.fetch_data_plane_bootstrap(
            self.node_id, digest, self.remote_ip, "f" * 64, self.now[0]
        )

        self.assertTrue(
            self.db.acknowledge_data_plane_bootstrap(
                self.node_id,
                digest,
                self.remote_ip,
                "9" * 64,
                self.now[0],
            )
        )
        self.assertFalse(
            self.db.acknowledge_data_plane_bootstrap(
                self.node_id,
                digest,
                self.remote_ip,
                "8" * 64,
                self.now[0],
            )
        )
        with sqlite3.connect(str(self.db_path)) as connection:
            grant = connection.execute(
                """SELECT acknowledged_at FROM node_data_plane_bootstrap_grants
                WHERE grant_id = ?""",
                (issued["grantId"],),
            ).fetchone()
            node = connection.execute(
                """SELECT data_plane_state, data_plane_installed_at
                FROM nodes WHERE node_id = ?""",
                (self.node_id,),
            ).fetchone()
        self.assertEqual(self.now[0], grant[0])
        self.assertEqual(("data_plane_installed", self.now[0]), node)
        self.assertIsNone(
            self.db.fetch_data_plane_bootstrap(
                self.node_id, digest, self.remote_ip, "7" * 64, self.now[0]
            )
        )

    def test_direct_canary_is_a_separate_manual_transition_and_never_admits_dns(self):
        with self.assertRaises(ValueError):
            self.db.mark_node_direct_canary_passed(
                self.node_id, "admin", self.now[0]
            )
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """UPDATE nodes SET data_plane_state = 'data_plane_installed',
                    data_plane_installed_at = ? WHERE node_id = ?""",
                (self.now[0] - 1, self.node_id),
            )

        self.assertTrue(
            self.db.mark_node_direct_canary_passed(
                self.node_id, "admin", self.now[0]
            )
        )
        node = next(
            item for item in self.db.list_nodes() if item["node_id"] == self.node_id
        )
        self.assertEqual("direct_canary_passed", node["data_plane_state"])
        self.assertEqual(self.now[0], node["direct_canary_passed_at"])
        self.assertIsNone(node["dns_admitted_at"])
        self.assertFalse(
            self.db.mark_node_direct_canary_passed(
                self.node_id, "admin", self.now[0] + 1
            )
        )

    def test_dns_admission_requires_fresh_control_state_and_is_reversible(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """UPDATE nodes SET data_plane_state = 'data_plane_installed',
                    data_plane_installed_at = ? WHERE node_id = ?""",
                (self.now[0] - 10, self.node_id),
            )
        self.assertTrue(
            self.db.mark_node_direct_canary_passed(
                self.node_id, "admin", self.now[0] - 5
            )
        )

        with self.assertRaises(ValueError):
            self.db.mark_node_dns_admitted(self.node_id, "admin", self.now[0])
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """UPDATE nodes SET last_heartbeat_at = ?, last_snapshot_at = ?,
                    last_traffic_ack_at = ? WHERE node_id = ?""",
                (self.now[0], self.now[0], self.now[0], self.node_id),
            )

        self.assertTrue(
            self.db.mark_node_dns_admitted(self.node_id, "admin", self.now[0])
        )
        node = next(
            item for item in self.db.list_nodes() if item["node_id"] == self.node_id
        )
        self.assertEqual("dns_admitted", node["data_plane_state"])
        self.assertEqual(self.now[0], node["dns_admitted_at"])
        self.assertEqual("admin", node["dns_admitted_by"])
        self.assertIsNone(node["dns_removed_at"])
        self.assertFalse(
            self.db.mark_node_dns_admitted(self.node_id, "admin", self.now[0] + 1)
        )
        with self.assertRaises(ValueError):
            self.db.set_node_policy_state(
                self.node_id, "standby", "admin", self.now[0] + 1
            )
        with self.assertRaises(ValueError):
            self.db.revoke_node(self.node_id, self.now[0] + 1)

        self.assertTrue(
            self.db.remove_node_dns_admission(
                self.node_id, "rollback-admin", self.now[0] + 2
            )
        )
        node = next(
            item for item in self.db.list_nodes() if item["node_id"] == self.node_id
        )
        self.assertEqual("direct_canary_passed", node["data_plane_state"])
        self.assertEqual(self.now[0] + 2, node["dns_removed_at"])
        self.assertEqual("rollback-admin", node["dns_removed_by"])
        self.assertFalse(
            self.db.remove_node_dns_admission(
                self.node_id, "rollback-admin", self.now[0] + 3
            )
        )

    def test_dns_admission_rejects_stale_state_without_partial_writes(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """UPDATE nodes SET data_plane_state = 'direct_canary_passed',
                    data_plane_installed_at = ?, direct_canary_passed_at = ?,
                    last_heartbeat_at = ?, last_snapshot_at = ?,
                    last_traffic_ack_at = ? WHERE node_id = ?""",
                (
                    self.now[0] - 100,
                    self.now[0] - 90,
                    self.now[0],
                    self.now[0] - 46,
                    self.now[0],
                    self.node_id,
                ),
            )
        with self.assertRaises(ValueError):
            self.db.mark_node_dns_admitted(self.node_id, "admin", self.now[0])
        node = next(
            item for item in self.db.list_nodes() if item["node_id"] == self.node_id
        )
        self.assertEqual("direct_canary_passed", node["data_plane_state"])
        self.assertIsNone(node["dns_admitted_at"])


class AutoBootstrapClaimTests(unittest.TestCase):
    _insert_node = DataPlaneBootstrapStateTests._insert_node
    _digest = DataPlaneBootstrapStateTests._digest

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "panel.db"
        self.db = Database(self.db_path, b"c" * 32)
        self.db.initialize()
        self.now = [2_000_000_000]
        self.node_id = "5" * 32
        self.remote_ip = "203.0.113.50"
        self.tokens = iter(("claim_" + "A" * 40, "claim_" + "B" * 40))
        self._insert_node(self.node_id, policy_state="standby")
        self.signed_messages = []
        self.service = DataPlaneBootstrapService(
            self.db,
            panel_url="https://panel.example.com:19998",
            panel_version="0.30.0",
            clock=lambda: self.now[0],
            token_factory=lambda: next(self.tokens),
            signature_verifier=self._verify_signature,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _verify_signature(self, _public_key, message, _signature):
        self.signed_messages.append(message)
        return True

    def _payload(self, value=1, **changes):
        payload = {
            "nodeId": self.node_id,
            "sentAt": self.now[0],
            "nonce": base64.urlsafe_b64encode(bytes([value]) * 32)
            .decode("ascii")
            .rstrip("="),
            "requestId": "{:032x}".format(value),
            "signature": base64.b64encode(b"s" * 64).decode("ascii"),
        }
        payload.update(changes)
        return payload

    def test_verified_online_node_claim_enables_protocol_and_returns_only_token(self):
        result = self.service.claim(self._payload(), remote_ip=self.remote_ip)

        self.assertEqual("AUTO_BOOTSTRAP_ISSUED", result["status"])
        self.assertEqual(self.node_id, result["nodeId"])
        self.assertEqual("claim_" + "A" * 40, result["bootstrapToken"])
        self.assertNotIn("deploymentCommand", result)
        self.assertTrue(
            self.signed_messages[-1].startswith(
                b"hy2panel-data-plane-claim-v1\n"
            )
        )
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            node = connection.execute(
                "SELECT policy_state, policy_enabled_by, data_plane_state "
                "FROM nodes WHERE node_id = ?",
                (self.node_id,),
            ).fetchone()
            grant = connection.execute(
                "SELECT token_digest, created_by, revoked_at "
                "FROM node_data_plane_bootstrap_grants WHERE grant_id = ?",
                (result["grantId"],),
            ).fetchone()
        self.assertEqual(
            ("protocol_ready", "system:auto-onboarding", "bootstrap_issued"),
            tuple(node),
        )
        self.assertEqual(
            hashlib.sha256(result["bootstrapToken"].encode("ascii")).hexdigest(),
            grant["token_digest"],
        )
        self.assertEqual("system:auto-onboarding", grant["created_by"])
        self.assertIsNone(grant["revoked_at"])
        self.assertNotIn(result["bootstrapToken"].encode("ascii"), self.db_path.read_bytes())

    def test_claim_reissues_atomically_after_a_lost_response(self):
        first = self.service.claim(self._payload(1), remote_ip=self.remote_ip)
        second = self.service.claim(self._payload(2), remote_ip=self.remote_ip)

        with sqlite3.connect(str(self.db_path)) as connection:
            grants = {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT grant_id, revoked_at FROM node_data_plane_bootstrap_grants "
                    "WHERE node_id = ?",
                    (self.node_id,),
                )
            }
        self.assertEqual(self.now[0], grants[first["grantId"]])
        self.assertIsNone(grants[second["grantId"]])

    def test_claim_fails_closed_before_verification_or_without_fresh_heartbeat(self):
        cases = (
            ("6" * 32, False, self.now[0], self.remote_ip),
            ("7" * 32, True, self.now[0] - 121, self.remote_ip),
            ("8" * 32, True, self.now[0], "203.0.113.81"),
        )
        for node_id, verified, heartbeat_at, remote_ip in cases:
            with self.subTest(node_id=node_id):
                self._insert_node(
                    node_id,
                    verified=verified,
                    policy_state="standby",
                    address="203.0.113.80",
                )
                with sqlite3.connect(str(self.db_path)) as connection:
                    connection.execute(
                        "UPDATE nodes SET last_heartbeat_at = ? WHERE node_id = ?",
                        (heartbeat_at, node_id),
                    )
                payload = self._payload(nodeId=node_id)
                with self.assertRaises(DataPlaneBootstrapRejected):
                    self.service.claim(payload, remote_ip=remote_ip)

        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE nodes SET data_plane_state = 'direct_canary_passed' "
                "WHERE node_id = ?",
                (self.node_id,),
            )
        recovered = self.service.claim(
            self._payload(9), remote_ip=self.remote_ip
        )
        self.assertEqual("AUTO_BOOTSTRAP_ISSUED", recovered["status"])
        node = self.db.get_node_for_heartbeat(self.node_id)
        self.assertEqual("direct_canary_passed", node["data_plane_state"])

    def test_claim_token_is_a_reserved_node_bound_canary_not_a_user(self):
        result = self.service.claim(self._payload(), remote_ip=self.remote_ip)
        digest = hashlib.sha256(
            result["bootstrapToken"].encode("ascii")
        ).hexdigest()
        self.assertIsNotNone(
            self.db.fetch_data_plane_bootstrap(
                self.node_id, digest, self.remote_ip, "a" * 64, self.now[0]
            )
        )

        decision = self.db.authorize_distributed_node(
            self.node_id,
            "b" * 32,
            result["bootstrapToken"],
            True,
            {},
            "c" * 64,
            self.now[0],
            5,
        )
        self.assertTrue(decision["ok"])
        self.assertEqual("__hy2panel_bootstrap_canary__", decision["id"])
        with sqlite3.connect(str(self.db_path)) as connection:
            self.assertEqual(
                0, connection.execute("SELECT COUNT(*) FROM proxy_users").fetchone()[0]
            )

        self.assertTrue(
            self.db.acknowledge_data_plane_bootstrap(
                self.node_id,
                digest,
                self.remote_ip,
                "d" * 64,
                self.now[0],
                automatic_canary_passed=True,
            )
        )
        self.assertIsNone(
            self.db.authorize_distributed_node(
                self.node_id,
                "e" * 32,
                result["bootstrapToken"],
                False,
                {},
                "f" * 64,
                self.now[0],
                5,
            )
        )
        node = next(
            item for item in self.db.list_nodes() if item["node_id"] == self.node_id
        )
        self.assertEqual("direct_canary_passed", node["data_plane_state"])
        self.assertEqual(self.now[0], node["direct_canary_passed_at"])


class AutoBootstrapClaimClientTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = Path(self.temp_dir.name) / "bootstrap.token"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_claim_token_is_written_atomically_without_printing_the_secret(self):
        client = mock.Mock()
        client.claim.return_value = {
            "nodeId": "5" * 32,
            "grantId": "6" * 32,
            "expiresAt": 2_000_000_600,
            "maxFetchAttempts": 3,
            "status": "AUTO_BOOTSTRAP_ISSUED",
            "bootstrapToken": "claim_" + "C" * 40,
        }

        node_agent.write_bootstrap_claim(client, self.output)

        self.assertEqual("claim_" + "C" * 40, self.output.read_text("ascii"))
        self.assertEqual(0o600, stat.S_IMODE(self.output.stat().st_mode))
        with self.assertRaises(ProtocolError):
            node_agent.write_bootstrap_claim(client, self.output)

    def test_claim_file_is_consumable_by_installer_with_errexit(self):
        token = "claim_" + "C" * 40
        client = mock.Mock()
        client.claim.return_value = {
            "nodeId": "5" * 32,
            "grantId": "6" * 32,
            "expiresAt": 2_000_000_600,
            "maxFetchAttempts": 3,
            "status": "AUTO_BOOTSTRAP_ISSUED",
            "bootstrapToken": token,
        }
        node_agent.write_bootstrap_claim(client, self.output)

        source = (Path(__file__).resolve().parents[1] / "install.sh").read_text()
        start = source.index("complete_node_onboarding()")
        end = source.index("\n}\n", start) + 2
        completion = source[start:end]
        read_command = next(
            line.strip()
            for line in completion.splitlines()
            if "bootstrap_token" in line and "NODE_ONBOARDING_TOKEN_FILE" in line
        )
        script = "\n".join(
            (
                "set -Eeuo pipefail",
                'NODE_ONBOARDING_TOKEN_FILE="$1"',
                'bootstrap_token=""',
                read_command,
                'printf "%s" "$bootstrap_token"',
            )
        )
        result = subprocess.run(
            ["bash", "-c", script, "bash", str(self.output)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(token, result.stdout)

    def test_claim_cli_heartbeats_before_requesting_the_secret(self):
        state = Path(self.temp_dir.name) / "registration.json"
        private_key = Path(self.temp_dir.name) / "node.key"
        arguments = [
            "claim-data-plane",
            "--private-key",
            str(private_key),
            "--state-file",
            str(state),
            "--output-token",
            str(self.output),
        ]
        order = []

        class Client:
            def __init__(self, state_path, private_key_path):
                self.state_path = state_path
                self.private_key_path = private_key_path

        def fake_heartbeat(**_kwargs):
            order.append("heartbeat")
            return {"nodeId": "5" * 32, "status": "ONLINE"}

        def fake_write(client, output):
            self.assertIsInstance(client, Client)
            self.assertEqual(self.output, output)
            order.append("claim")

        with mock.patch.object(node_agent, "heartbeat", side_effect=fake_heartbeat), mock.patch.object(
            node_agent, "DataPlaneBootstrapClient", Client
        ), mock.patch.object(
            node_agent, "write_bootstrap_claim", side_effect=fake_write
        ):
            self.assertEqual(0, node_agent.main(arguments))
        self.assertEqual(["heartbeat", "claim"], order)


class DataPlaneBootstrapContractTests(unittest.TestCase):
    _insert_node = DataPlaneBootstrapStateTests._insert_node
    _digest = DataPlaneBootstrapStateTests._digest

    def setUp(self):
        DataPlaneBootstrapStateTests.setUp(self)
        self.identity = {
            "certificatePem": "-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----\n",
            "privateKeyPem": "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n",
            "certificateFileSha256": "a" * 64,
            "certificateDerSha256": "b" * 64,
            "privateKeyPublicSha256": "c" * 64,
            "egressPolicy": "web",
        }
        self.service = DataPlaneBootstrapService(
            self.db,
            panel_url="https://panel.example.com:19998",
            panel_version="0.27.0",
            clock=lambda: self.now[0],
            token_factory=lambda: self.token,
            signature_verifier=lambda _key, _message, _signature: True,
            identity_provider=lambda: dict(self.identity),
            hysteria_port=24443,
        )
        self.service.issue(self.node_id, actor="admin")

    def tearDown(self):
        DataPlaneBootstrapStateTests.tearDown(self)

    def _common(self, value):
        return {
            "nodeId": self.node_id,
            "sentAt": self.now[0],
            "nonce": base64.urlsafe_b64encode(bytes([value]) * 32)
            .decode("ascii")
            .rstrip("="),
            "signature": base64.b64encode(b"s" * 64).decode("ascii"),
        }

    def _bootstrap_payload(self, value=1, **changes):
        payload = self._common(value)
        payload.update(
            {
                "bootstrapToken": self.token,
                "requestId": "{:032x}".format(value),
            }
        )
        payload.update(changes)
        return payload

    def _ack_payload(self, value=2, **changes):
        payload = self._common(value)
        payload.update(
            {
                "bootstrapToken": self.token,
                "requestId": "{:032x}".format(value),
                "certificateFileSha256": self.identity[
                    "certificateFileSha256"
                ],
                "certificateDerSha256": self.identity[
                    "certificateDerSha256"
                ],
                "privateKeyPublicSha256": self.identity[
                    "privateKeyPublicSha256"
                ],
                "hysteriaVersion": "2.12.1",
                "egressPolicy": "web",
                "configProtocolVersion": 1,
                "servicesHealthy": True,
                "statsHealthy": True,
                "udp19999Listening": True,
                "udp443Listening": True,
                "tcp19999Listening": True,
                "tcp443Listening": True,
            }
        )
        payload.update(changes)
        return payload

    def test_canonical_contract_is_domain_separated_and_excludes_signature(self):
        payload = self._bootstrap_payload()

        canonical = canonical_data_plane_request("bootstrap", payload)

        self.assertTrue(canonical.startswith(b"hy2panel-data-plane-bootstrap-v1\n"))
        self.assertNotIn(b"signature", canonical)
        self.assertIn(
            json.dumps(
                {key: value for key, value in payload.items() if key != "signature"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            canonical,
        )

    def test_signed_fetch_returns_fixed_identity_contract_without_persisting_secrets(self):
        result = self.service.fetch(
            self._bootstrap_payload(), remote_ip=self.remote_ip
        )

        self.assertEqual(1, result["fetchAttempt"])
        self.assertEqual(3, result["maxFetchAttempts"])
        self.assertEqual(1, result["configProtocolVersion"])
        self.assertEqual("2.12.1", result["hysteriaVersion"])
        self.assertEqual({"main": 24443, "udp443": 443}, result["ports"])
        self.assertEqual(self.identity["certificatePem"], result["certificatePem"])
        self.assertEqual(self.identity["privateKeyPem"], result["privateKeyPem"])
        self.assertEqual("web", result["egressPolicy"])
        self.assertEqual(
            {
                "amd64": "ffc032c7ca6b78676d337097ca7f61bebc3a90a4f3a656693adf368f304cdbc7",
                "arm64": "c9cd1af6395eee13a937f429ea71b290e3cc571eea2b4d7f8bc7c49c1d23a792",
            },
            result["hysteriaSha256"],
        )
        database_bytes = self.db_path.read_bytes()
        self.assertNotIn(self.token.encode("ascii"), database_bytes)
        self.assertNotIn(self.identity["privateKeyPem"].encode("ascii"), database_bytes)

    def test_stale_wrong_ip_bad_signature_unknown_field_and_replay_fail_closed(self):
        cases = (
            (self._bootstrap_payload(sentAt=self.now[0] - 121), self.remote_ip),
            (self._bootstrap_payload(), "203.0.113.11"),
            (self._bootstrap_payload(signature="bad"), self.remote_ip),
            (self._bootstrap_payload(unexpected=True), self.remote_ip),
        )
        for payload, remote_ip in cases:
            with self.subTest(payload=payload, remote_ip=remote_ip):
                with self.assertRaises(DataPlaneBootstrapRejected):
                    self.service.fetch(payload, remote_ip=remote_ip)

        payload = self._bootstrap_payload(value=9)
        self.service.fetch(payload, remote_ip=self.remote_ip)
        with self.assertRaises(DataPlaneBootstrapRejected):
            self.service.fetch(payload, remote_ip=self.remote_ip)

    def test_ack_requires_fresh_matching_identity_and_complete_healthy_attestation(self):
        self.service.fetch(self._bootstrap_payload(), remote_ip=self.remote_ip)
        invalid = (
            {"certificateDerSha256": "d" * 64},
            {"hysteriaVersion": "2.12.0"},
            {"egressPolicy": "full"},
            {"statsHealthy": False},
            {"udp443Listening": False},
            {"configProtocolVersion": 2},
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises(DataPlaneBootstrapRejected):
                    self.service.ack(
                        self._ack_payload(**changes), remote_ip=self.remote_ip
                    )

        result = self.service.ack(
            self._ack_payload(value=20), remote_ip=self.remote_ip
        )
        self.assertEqual(
            {"nodeId": self.node_id, "status": "DATA_PLANE_INSTALLED"}, result
        )
        with self.assertRaises(DataPlaneBootstrapRejected):
            self.service.ack(
                self._ack_payload(value=21), remote_ip=self.remote_ip
            )

    def test_automatic_ack_requires_real_canary_before_consuming_the_grant(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE node_data_plane_bootstrap_grants SET automatic_canary = 1 "
                "WHERE node_id = ?",
                (self.node_id,),
            )
        self.service.fetch(self._bootstrap_payload(), remote_ip=self.remote_ip)
        calls = []

        def failed_canary(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("external egress failed")

        self.service.canary_runner = failed_canary
        with self.assertRaises(DataPlaneBootstrapRejected):
            self.service.ack(
                self._ack_payload(value=30), remote_ip=self.remote_ip
            )
        with sqlite3.connect(str(self.db_path)) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT acknowledged_at FROM node_data_plane_bootstrap_grants "
                    "WHERE node_id = ?",
                    (self.node_id,),
                ).fetchone()[0]
            )
        self.assertEqual(self.remote_ip, calls[0]["node_ip"])
        self.assertEqual(self.token, calls[0]["token"])
        self.assertEqual(self.identity["certificateDerSha256"], calls[0]["pin_sha256"])
        self.assertEqual(24443, calls[0]["main_port"])

        self.service.canary_runner = lambda **kwargs: calls.append(kwargs)
        result = self.service.ack(
            self._ack_payload(value=31), remote_ip=self.remote_ip
        )
        self.assertEqual(
            {"nodeId": self.node_id, "status": "DIRECT_CANARY_PASSED"}, result
        )


class HysteriaIdentityProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.cert_path = root / "server.crt"
        self.key_path = root / "server.key"
        completed = subprocess.run(
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(self.key_path),
                "-out",
                str(self.cert_path),
                "-nodes",
                "-days",
                "30",
                "-subj",
                "/CN=vpn.example.com",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            self.skipTest(completed.stderr)
        os.chmod(self.cert_path, 0o640)
        os.chmod(self.key_path, 0o640)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reads_byte_identical_identity_and_computes_three_digests(self):
        provider = HysteriaIdentityProvider(
            self.cert_path,
            self.key_path,
            egress_policy_provider=lambda: "web",
        )

        identity = provider()

        cert_bytes = self.cert_path.read_bytes()
        key_bytes = self.key_path.read_bytes()
        self.assertEqual(cert_bytes, identity["certificatePem"].encode("ascii"))
        self.assertEqual(key_bytes, identity["privateKeyPem"].encode("ascii"))
        self.assertEqual(
            hashlib.sha256(cert_bytes).hexdigest(),
            identity["certificateFileSha256"],
        )
        self.assertRegex(identity["certificateDerSha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(identity["privateKeyPublicSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("web", identity["egressPolicy"])

    def test_mismatched_key_symlink_oversize_and_invalid_policy_fail_closed(self):
        other_key = self.key_path.with_name("other.key")
        subprocess.run(
            [
                "/usr/bin/openssl",
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                str(other_key),
            ],
            capture_output=True,
            check=True,
        )
        cases = (
            (self.cert_path, other_key, lambda: "web"),
            (self.cert_path.with_name("link.crt"), self.key_path, lambda: "web"),
            (self.cert_path, self.key_path, lambda: "invalid"),
        )
        self.cert_path.with_name("link.crt").symlink_to(self.cert_path)
        for cert_path, key_path, policy in cases:
            with self.subTest(cert_path=cert_path, key_path=key_path):
                provider = HysteriaIdentityProvider(
                    cert_path, key_path, egress_policy_provider=policy
                )
                with self.assertRaises(ValueError):
                    provider()

        oversized = self.cert_path.with_name("oversized.crt")
        oversized.write_bytes(b"x" * (16 * 1024 + 1))
        with self.assertRaises(ValueError):
            HysteriaIdentityProvider(
                oversized, self.key_path, egress_policy_provider=lambda: "web"
            )()


class DataPlaneBootstrapHttpTests(unittest.TestCase):
    _insert_node = DataPlaneBootstrapStateTests._insert_node

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "panel.db"
        self.db = Database(self.db_path, b"h" * 32)
        self.db.initialize()
        self.admin_id = self.db.upsert_admin("admin", "password")
        self.now = [int(time.time())]
        self.remote_ip = "127.0.0.1"
        self.node_id = "6" * 32
        self.token = "http_bootstrap_" + "H" * 40
        self._insert_node(self.node_id, policy_state="protocol_ready")
        self.identity = {
            "certificatePem": "-----BEGIN CERTIFICATE-----\nHTTP\n-----END CERTIFICATE-----\n",
            "privateKeyPem": "-----BEGIN PRIVATE KEY-----\nHTTP\n-----END PRIVATE KEY-----\n",
            "certificateFileSha256": "a" * 64,
            "certificateDerSha256": "b" * 64,
            "privateKeyPublicSha256": "c" * 64,
            "egressPolicy": "web",
        }
        self.service = DataPlaneBootstrapService(
            self.db,
            panel_url="https://panel.example.com:19998",
            panel_version="0.27.0",
            clock=lambda: self.now[0],
            token_factory=lambda: self.token,
            signature_verifier=lambda _key, _message, _signature: True,
            identity_provider=lambda: dict(self.identity),
        )
        self.application = PanelApplication(
            database=self.db,
            public_host="vpn.example.com",
            hysteria_port=19999,
            pin_sha256="AA:BB",
            stats_client=object(),
            secure_cookies=True,
            data_plane_bootstrap_service=self.service,
        )
        self.server = make_panel_server(("127.0.0.1", 0), self.application)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{}".format(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def _common(self, value):
        return {
            "nodeId": self.node_id,
            "sentAt": self.now[0],
            "nonce": base64.urlsafe_b64encode(bytes([value]) * 32)
            .decode("ascii")
            .rstrip("="),
            "signature": base64.b64encode(b"s" * 64).decode("ascii"),
        }

    def _bootstrap_payload(self, value=1, token=None):
        payload = self._common(value)
        payload.update(
            {
                "bootstrapToken": token or self.token,
                "requestId": "{:032x}".format(value),
            }
        )
        return payload

    def _post_json(self, path, payload):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=2)

    def test_admin_issue_requires_session_csrf_and_returns_only_ephemeral_command(self):
        raw_session, csrf = self.db.create_session(self.admin_id)
        body = urllib.parse.urlencode({"csrf": csrf}).encode("ascii")
        request = urllib.request.Request(
            self.base_url
            + "/nodes/{}/data-plane/bootstrap".format(self.node_id),
            data=body,
            headers={"Cookie": "hy2panel_session={}".format(raw_session)},
            method="POST",
        )

        response = urllib.request.urlopen(request, timeout=2)
        result = json.loads(response.read().decode("utf-8"))

        self.assertEqual("BOOTSTRAP_ISSUED", result["status"])
        self.assertIn("--activate-data-plane", result["deploymentCommand"])
        with sqlite3.connect(str(self.db_path)) as connection:
            audit = connection.execute(
                "SELECT action, target FROM audit_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(("node_data_plane_bootstrap_issued", self.node_id), audit)
        self.assertNotIn(self.token, "{} {}".format(*audit))

    def test_public_bootstrap_is_https_only_bounded_and_has_stable_errors(self):
        self.service.issue(self.node_id, actor="admin")
        self.application.secure_cookies = False
        with self.assertRaises(urllib.error.HTTPError) as insecure:
            self._post_json(
                "/api/v1/node-data-plane/bootstrap", self._bootstrap_payload()
            )
        self.assertEqual(404, insecure.exception.code)
        self.application.secure_cookies = True

        request = urllib.request.Request(
            self.base_url + "/api/v1/node-data-plane/bootstrap",
            data=b"x" * (16 * 1024 + 1),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as oversized:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(413, oversized.exception.code)

        with self.assertRaises(urllib.error.HTTPError) as rejected:
            self._post_json(
                "/api/v1/node-data-plane/bootstrap",
                self._bootstrap_payload(token="wrong_" + "W" * 40),
            )
        self.assertEqual(403, rejected.exception.code)
        error = json.loads(rejected.exception.read().decode("utf-8"))
        self.assertEqual("DATA_PLANE_BOOTSTRAP_REJECTED", error["error"]["code"])
        self.assertNotIn(self.token, json.dumps(error))

    def test_public_fetch_and_ack_return_the_fixed_contract(self):
        self.service.issue(self.node_id, actor="admin")
        extended_requests = []
        original_begin_canary = self.server.begin_node_canary_request

        def begin_canary(request):
            extended_requests.append(request)
            return original_begin_canary(request)

        self.server.begin_node_canary_request = begin_canary

        fetched = json.loads(
            self._post_json(
                "/api/v1/node-data-plane/bootstrap", self._bootstrap_payload()
            )
            .read()
            .decode("utf-8")
        )
        self.assertEqual(self.identity["privateKeyPem"], fetched["privateKeyPem"])
        self.assertEqual([], extended_requests)

        ack = self._common(2)
        ack.update(
            {
                "bootstrapToken": self.token,
                "requestId": "2" * 32,
                "certificateFileSha256": "a" * 64,
                "certificateDerSha256": "b" * 64,
                "privateKeyPublicSha256": "c" * 64,
                "hysteriaVersion": "2.12.1",
                "egressPolicy": "web",
                "configProtocolVersion": 1,
                "servicesHealthy": True,
                "statsHealthy": True,
                "udp19999Listening": True,
                "udp443Listening": True,
                "tcp19999Listening": True,
                "tcp443Listening": True,
            }
        )
        result = json.loads(
            self._post_json("/api/v1/node-data-plane/ack", ack)
            .read()
            .decode("utf-8")
        )
        self.assertEqual("DATA_PLANE_INSTALLED", result["status"])
        self.assertEqual(1, len(extended_requests))

    def test_public_auto_claim_uses_the_same_https_and_signature_boundary(self):
        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                "UPDATE nodes SET policy_state = 'standby' WHERE node_id = ?",
                (self.node_id,),
            )
        payload = self._common(30)
        payload["requestId"] = "3" * 32

        result = json.loads(
            self._post_json("/api/v1/node-data-plane/claim", payload)
            .read()
            .decode("utf-8")
        )

        self.assertEqual("AUTO_BOOTSTRAP_ISSUED", result["status"])
        self.assertEqual(self.node_id, result["nodeId"])
        self.assertEqual(self.token, result["bootstrapToken"])
        self.assertNotIn("deploymentCommand", result)
        raw_session, _csrf = self.db.create_session(self.admin_id)
        dashboard = urllib.request.urlopen(
            urllib.request.Request(
                self.base_url + "/",
                headers={"Cookie": "hy2panel_session={}".format(raw_session)},
            ),
            timeout=2,
        ).read().decode("utf-8")
        self.assertIn("自动部署中", dashboard)
        self.assertNotIn(
            "/nodes/{}/data-plane/bootstrap".format(self.node_id), dashboard
        )

    def test_dashboard_exposes_only_eligible_deploy_and_separate_canary_controls(self):
        raw_session, csrf = self.db.create_session(self.admin_id)
        headers = {"Cookie": "hy2panel_session={}".format(raw_session)}
        request = urllib.request.Request(self.base_url + "/", headers=headers)

        body = urllib.request.urlopen(request, timeout=2).read().decode("utf-8")

        self.assertIn(
            '/nodes/{}/data-plane/bootstrap'.format(self.node_id), body
        )
        self.assertIn("旧节点手动部署", body)
        self.assertIn("等待节点自动领取部署凭据", body)
        self.assertIn("data-data-plane-bootstrap-form", body)
        self.assertNotIn("data-plane/canary/pass", body)
        self.assertNotIn("dns/admit", body)

        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """UPDATE nodes SET data_plane_state = 'data_plane_installed',
                    data_plane_installed_at = ? WHERE node_id = ?""",
                (self.now[0], self.node_id),
            )
        body = urllib.request.urlopen(request, timeout=2).read().decode("utf-8")
        self.assertIn("数据面已安装 · 待直连灰度", body)
        self.assertIn(
            '/nodes/{}/data-plane/canary/pass'.format(self.node_id), body
        )
        self.assertIn("data-data-plane-canary-form", body)
        self.assertIn(
            '/nodes/{}/data-plane/bootstrap'.format(self.node_id), body
        )
        self.assertIn("生成数据面升级码", body)

        canary_request = urllib.request.Request(
            self.base_url
            + "/nodes/{}/data-plane/canary/pass".format(self.node_id),
            data=urllib.parse.urlencode({"csrf": csrf}).encode("ascii"),
            headers={**headers, "Accept": "application/json"},
            method="POST",
        )
        result = json.loads(
            urllib.request.urlopen(canary_request, timeout=2).read().decode("utf-8")
        )
        self.assertEqual({"directCanaryPassed": True}, result)
        node = next(
            item for item in self.db.list_nodes() if item["node_id"] == self.node_id
        )
        self.assertIsNotNone(node["direct_canary_passed_at"])
        self.assertIsNone(node["dns_admitted_at"])

        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute(
                """UPDATE nodes SET last_heartbeat_at = ?, last_snapshot_at = ?,
                    last_traffic_ack_at = ? WHERE node_id = ?""",
                (self.now[0], self.now[0], self.now[0], self.node_id),
            )
        body = urllib.request.urlopen(request, timeout=2).read().decode("utf-8")
        self.assertNotIn(
            '/nodes/{}/data-plane/dns/admit'.format(self.node_id), body
        )
        self.assertIn("请手工添加 DNS", body)

        admit_request = urllib.request.Request(
            self.base_url + "/nodes/{}/data-plane/dns/admit".format(self.node_id),
            data=urllib.parse.urlencode({"csrf": csrf}).encode("ascii"),
            headers={**headers, "Accept": "application/json"},
            method="POST",
        )
        result = json.loads(
            urllib.request.urlopen(admit_request, timeout=2).read().decode("utf-8")
        )
        self.assertEqual({"dnsAdmitted": True}, result)
        body = urllib.request.urlopen(request, timeout=2).read().decode("utf-8")
        self.assertIn("DNS 已检测并自动准入", body)
        self.assertIn(
            '/nodes/{}/lifecycle/drain'.format(self.node_id), body
        )

        remove_request = urllib.request.Request(
            self.base_url + "/nodes/{}/data-plane/dns/remove".format(self.node_id),
            data=urllib.parse.urlencode({"csrf": csrf}).encode("ascii"),
            headers={**headers, "Accept": "application/json"},
            method="POST",
        )
        result = json.loads(
            urllib.request.urlopen(remove_request, timeout=2).read().decode("utf-8")
        )
        self.assertEqual({"dnsRemoved": True}, result)


class NodeDataPlaneConfigTests(unittest.TestCase):
    def setUp(self):
        HysteriaIdentityProviderTests.setUp(self)
        provider = HysteriaIdentityProvider(
            self.cert_path,
            self.key_path,
            egress_policy_provider=lambda: "web",
        )
        self.response = {
            "grantId": "7" * 32,
            "expiresAt": 2_000_000_600,
            "fetchAttempt": 1,
            "maxFetchAttempts": 3,
            "configProtocolVersion": 1,
            "hysteriaVersion": "2.12.1",
            "hysteriaSha256": {
                "amd64": "ffc032c7ca6b78676d337097ca7f61bebc3a90a4f3a656693adf368f304cdbc7",
                "arm64": "c9cd1af6395eee13a937f429ea71b290e3cc571eea2b4d7f8bc7c49c1d23a792",
            },
            "ports": {"main": 24443, "udp443": 443},
        }
        self.response.update(provider())

    def tearDown(self):
        HysteriaIdentityProviderTests.tearDown(self)

    def test_identity_validation_preserves_bytes_and_verifies_all_digests(self):
        identity = validate_data_plane_identity(self.response, architecture="amd64")

        self.assertEqual(self.cert_path.read_bytes(), identity["certificate"])
        self.assertEqual(self.key_path.read_bytes(), identity["private_key"])
        self.assertEqual(
            self.response["hysteriaSha256"]["amd64"],
            identity["hysteria_sha256"],
        )
        self.assertEqual("web", identity["egress_policy"])

    def test_identity_validation_rejects_tampering_and_unknown_contract_values(self):
        cases = (
            {"certificateFileSha256": "0" * 64},
            {"certificateDerSha256": "0" * 64},
            {"privateKeyPublicSha256": "0" * 64},
            {"hysteriaVersion": "2.12.0"},
            {"configProtocolVersion": 2},
            {"ports": {"main": 0, "udp443": 443}},
            {"ports": {"main": 443, "udp443": 443}},
            {"ports": {"main": 19996, "udp443": 443}},
            {"ports": {"main": 65536, "udp443": 443}},
            {"ports": {"main": True, "udp443": 443}},
            {"egressPolicy": "unknown"},
            {"unexpected": True},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                response = dict(self.response)
                response.update(changes)
                with self.assertRaises(ProtocolError):
                    validate_data_plane_identity(response, architecture="amd64")

        response = dict(self.response)
        response["privateKeyPem"] = response["privateKeyPem"].replace("A", "B", 1)
        with self.assertRaises(ProtocolError):
            validate_data_plane_identity(response, architecture="amd64")

    def test_config_renderer_emits_only_fixed_two_entrypoint_contracts(self):
        identity = validate_data_plane_identity(self.response, architecture="arm64")

        configs = render_data_plane_configs(identity, "S" * 48)

        self.assertEqual({"main", "udp443"}, set(configs))
        main = configs["main"]
        udp443 = configs["udp443"]
        self.assertIn("listen: :24443", main)
        self.assertIn("url: http://127.0.0.1:19996/auth/main", main)
        self.assertIn("listen: 127.0.0.1:19997", main)
        self.assertIn("listen: :443", udp443)
        self.assertIn("url: http://127.0.0.1:19996/auth/udp443", udp443)
        self.assertIn("listen: 127.0.0.1:19995", udp443)
        for config in configs.values():
            self.assertIn("cert: /etc/hysteria2-panel-node/server.crt", config)
            self.assertIn("key: /etc/hysteria2-panel-node/server.key", config)
            self.assertIn("secret: __HY2PANEL_STATS_SECRET__", config)
            self.assertNotIn("S" * 48, config)
            self.assertIn('    - "reject(10.0.0.0/8)"', config)
            self.assertIn('    - "direct(all, tcp/443)"', config)
            self.assertTrue(config.endswith('    statusCode: 404\n'))
            self.assertNotIn("vpn.example.com", config)
            self.assertNotIn("panel.example.com", config)

    def test_full_policy_is_applied_to_both_data_node_entrypoints(self):
        response = dict(self.response)
        response["egressPolicy"] = "full"
        identity = validate_data_plane_identity(response, architecture="amd64")

        configs = render_data_plane_configs(identity, "S" * 48)

        self.assertEqual({"main", "udp443"}, set(configs))
        for config in configs.values():
            self.assertIn('    - "direct(all)"', config)
            self.assertNotIn('    - "reject(all)"', config)
            self.assertIn("type: bbr", config)
            self.assertIn("bbrProfile: standard", config)

    def test_config_renderer_rejects_short_secret_and_invalid_identity(self):
        identity = validate_data_plane_identity(self.response, architecture="amd64")
        for secret in ("short", "bad\nsecret", "x" * 129):
            with self.subTest(secret=secret):
                with self.assertRaises(ProtocolError):
                    render_data_plane_configs(identity, secret)
        identity["egress_policy"] = "invalid"
        with self.assertRaises(ProtocolError):
            render_data_plane_configs(identity, "S" * 48)

    def test_bootstrap_client_signs_domain_separated_request_and_bounds_response(self):
        state_path = Path(self.temp_dir.name) / "registration.json"
        state_path.write_text(
            json.dumps(
                {
                    "nodeId": "8" * 32,
                    "panelUrl": "https://panel.example.test:19998",
                    "registeredAt": 1,
                    "status": "PENDING_VERIFICATION",
                }
            ),
            encoding="utf-8",
        )
        os.chmod(state_path, 0o600)
        captured = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, maximum):
                captured["maximum"] = maximum
                return json.dumps(self.response).encode("utf-8")

        Response.response = self.response

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

        def signer(_private_key, message):
            captured["message"] = message
            return b"s" * 64

        client = DataPlaneBootstrapClient(
            state_path,
            Path(self.temp_dir.name) / "private.pem",
            opener=opener,
            signer=signer,
            clock=lambda: 2_000_000_000,
            nonce_factory=lambda _size: "N" * 43,
        )

        claim_response = {
            "nodeId": "8" * 32,
            "grantId": "7" * 32,
            "expiresAt": 2_000_000_600,
            "maxFetchAttempts": 3,
            "status": "AUTO_BOOTSTRAP_ISSUED",
            "bootstrapToken": "bootstrap_" + "C" * 40,
        }
        Response.response = claim_response

        self.assertEqual(claim_response, client.claim())
        self.assertTrue(
            captured["message"].startswith(b"hy2panel-data-plane-claim-v1\n")
        )
        self.assertEqual(
            "https://panel.example.test:19998/api/v1/node-data-plane/claim",
            captured["request"].full_url,
        )
        self.assertEqual(8 * 1024 + 1, captured["maximum"])

        Response.response = self.response
        result = client.fetch("bootstrap_" + "T" * 40)

        self.assertEqual(self.response, result)
        self.assertTrue(
            captured["message"].startswith(b"hy2panel-data-plane-bootstrap-v1\n")
        )
        self.assertEqual(
            "https://panel.example.test:19998/api/v1/node-data-plane/bootstrap",
            captured["request"].full_url,
        )
        self.assertEqual(32 * 1024 + 1, captured["maximum"])
        self.assertEqual(10, captured["timeout"])

        expected_ack = {
            "nodeId": "8" * 32,
            "status": "DATA_PLANE_INSTALLED",
        }
        Response.response = expected_ack
        self.assertEqual(expected_ack, client.ack("bootstrap_" + "T" * 40, {}))
        self.assertEqual(8 * 1024 + 1, captured["maximum"])
        self.assertEqual(75, captured["timeout"])
        automatic_ack = {
            "nodeId": "8" * 32,
            "status": "DIRECT_CANARY_PASSED",
        }
        Response.response = automatic_ack
        self.assertEqual(automatic_ack, client.ack("bootstrap_" + "T" * 40, {}))

        for invalid_ack in (
            {"status": "DATA_PLANE_INSTALLED"},
            {"nodeId": "9" * 32, "status": "DATA_PLANE_INSTALLED"},
            {"nodeId": "8" * 32, "status": "BOOTSTRAP_ISSUED"},
            {
                "nodeId": "8" * 32,
                "status": "DATA_PLANE_INSTALLED",
                "unexpected": True,
            },
        ):
            with self.subTest(invalid_ack=invalid_ack):
                Response.response = invalid_ack
                with self.assertRaises(ProtocolError):
                    client.ack("bootstrap_" + "T" * 40, {})

    def test_prepare_bundle_is_atomic_root_only_and_never_persists_token(self):
        destination = Path(self.temp_dir.name) / "data-plane"
        token = "bootstrap_" + "T" * 40

        class Client:
            def fetch(_self, actual_token):
                self.assertEqual(token, actual_token)
                return dict(self.response)

        result = prepare_data_plane_bundle(
            Client(),
            token,
            destination,
            architecture="amd64",
            secret_factory=lambda _size: "S" * 48,
        )

        self.assertEqual(destination, result)
        self.assertEqual(0o700, destination.stat().st_mode & 0o777)
        expected_modes = {
            "server.crt": 0o600,
            "server.key": 0o600,
            "hysteria-main.yaml": 0o600,
            "hysteria-udp443.yaml": 0o600,
            "stats.env": 0o600,
            "bootstrap.json": 0o600,
        }
        self.assertEqual(expected_modes, {
            path.name: path.stat().st_mode & 0o777
            for path in destination.iterdir()
        })
        self.assertEqual(self.cert_path.read_bytes(), (destination / "server.crt").read_bytes())
        self.assertEqual(self.key_path.read_bytes(), (destination / "server.key").read_bytes())
        self.assertEqual(
            "HY2PANEL_STATS_SECRET={}\n".format("S" * 48),
            (destination / "stats.env").read_text(encoding="ascii"),
        )
        metadata = json.loads((destination / "bootstrap.json").read_text())
        self.assertEqual(
            {
                "certificateDerSha256",
                "certificateFileSha256",
                "configProtocolVersion",
                "egressPolicy",
                "hysteriaSha256",
                "hysteriaVersion",
                "mainPort",
                "privateKeyPublicSha256",
            },
            set(metadata),
        )
        self.assertEqual(24443, metadata["mainPort"])
        persisted = b"".join(path.read_bytes() for path in destination.iterdir())
        self.assertNotIn(token.encode("ascii"), persisted)
        self.assertNotIn(b"vpn.example.com", persisted)

    def test_prepare_bundle_rejects_unsafe_destination_and_leaves_no_partial_files(self):
        token = "bootstrap_" + "T" * 40

        class InvalidClient:
            def fetch(_self, _token):
                response = dict(self.response)
                response["certificateFileSha256"] = "0" * 64
                return response

        destination = Path(self.temp_dir.name) / "data-plane"
        with self.assertRaises(ProtocolError):
            prepare_data_plane_bundle(
                InvalidClient(), token, destination, architecture="amd64"
            )
        self.assertFalse(destination.exists())
        self.assertEqual([], list(Path(self.temp_dir.name).glob(".data-plane-*")))

        destination.mkdir(mode=0o700)
        with self.assertRaises(ProtocolError):
            prepare_data_plane_bundle(
                InvalidClient(), token, destination, architecture="amd64"
            )

    def test_hysteria_wrapper_substitutes_stats_secret_only_in_anonymous_memory(self):
        template = Path(self.temp_dir.name) / "hysteria.yaml"
        template.write_text(
            "trafficStats:\n  secret: __HY2PANEL_STATS_SECRET__\n",
            encoding="ascii",
        )
        captured = {}

        class Executed(Exception):
            pass

        def execve(path, arguments, environment):
            captured["path"] = path
            captured["arguments"] = arguments
            captured["environment"] = environment
            descriptor = int(captured["link_target"].rsplit("/", 1)[1])
            captured["config"] = os.pread(descriptor, 65536, 0).decode("ascii")
            raise Executed

        runtime_config = "/run/hysteria2-panel-node-main/config.yaml"
        link_exists = [False]

        class Metadata:
            st_uid = 0

            def __init__(self, mode):
                self.st_mode = mode

        def lstat(path):
            if str(path) == "/run/hysteria2-panel-node-main":
                return Metadata(stat.S_IFDIR | 0o700)
            if str(path) == runtime_config and link_exists[0]:
                return Metadata(stat.S_IFLNK | 0o777)
            raise FileNotFoundError(path)

        def symlink(target, path):
            self.assertEqual(runtime_config, str(path))
            captured["link_target"] = target
            link_exists[0] = True

        def unlink(path):
            self.assertEqual(runtime_config, str(path))
            captured["unlinked"] = True
            link_exists[0] = False

        anonymous = Path(self.temp_dir.name) / "anonymous-memory-test"

        environment = {
            "HY2PANEL_STATS_SECRET": "S" * 48,
            "HYSTERIA_DISABLE_UPDATE_CHECK": "1",
        }
        with self.assertRaises(Executed):
            run_hysteria_from_template(
                "/opt/hysteria2-panel-node/bin/hysteria",
                template,
                runtime_config,
                environment=environment,
                execve=execve,
                memfd_factory=lambda: os.open(
                    anonymous, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600
                ),
                lstat=lstat,
                symlink=symlink,
                unlink=unlink,
            )

        self.assertEqual(
            "/opt/hysteria2-panel-node/bin/hysteria", captured["path"]
        )
        self.assertEqual(
            [
                "/opt/hysteria2-panel-node/bin/hysteria",
                "server",
                "-c",
                captured["arguments"][-1],
            ],
            captured["arguments"],
        )
        self.assertEqual(runtime_config, captured["arguments"][-1])
        self.assertTrue(captured["link_target"].startswith("/proc/self/fd/"))
        self.assertTrue(captured["unlinked"])
        self.assertIn("secret: {}".format("S" * 48), captured["config"])
        self.assertNotIn("HY2PANEL_STATS_SECRET", captured["environment"])
        self.assertNotIn("S" * 48, template.read_text(encoding="ascii"))

    def test_hysteria_wrapper_rejects_missing_duplicate_or_unsafe_templates(self):
        template = Path(self.temp_dir.name) / "hysteria.yaml"
        for content in (
            "listen: :19999\n",
            "__HY2PANEL_STATS_SECRET__\n__HY2PANEL_STATS_SECRET__\n",
        ):
            template.write_text(content, encoding="ascii")
            with self.assertRaises(ProtocolError):
                run_hysteria_from_template(
                    "/opt/hysteria2-panel-node/bin/hysteria",
                    template,
                    "/run/hysteria2-panel-node-main/config.yaml",
                    environment={"HY2PANEL_STATS_SECRET": "S" * 48},
                    execve=lambda *_args: None,
                    memfd_factory=lambda: -1,
                )

    def test_hysteria_wrapper_rejects_unsafe_or_occupied_runtime_paths(self):
        template = Path(self.temp_dir.name) / "hysteria.yaml"
        template.write_text(
            "trafficStats:\n  secret: __HY2PANEL_STATS_SECRET__\n",
            encoding="ascii",
        )

        class Metadata:
            st_uid = 0

            def __init__(self, mode):
                self.st_mode = mode

        common = {
            "environment": {"HY2PANEL_STATS_SECRET": "S" * 48},
            "execve": lambda *_args: None,
            "memfd_factory": lambda: -1,
        }
        with self.assertRaises(ProtocolError):
            run_hysteria_from_template(
                "/opt/hysteria2-panel-node/bin/hysteria",
                template,
                "/tmp/config.yaml",
                **common,
            )

        with self.assertRaises(ProtocolError):
            run_hysteria_from_template(
                "/opt/hysteria2-panel-node/bin/hysteria",
                template,
                "/run/hysteria2-panel-node-main/config.yaml",
                lstat=lambda _path: Metadata(stat.S_IFDIR | 0o755),
                **common,
            )

        def occupied_lstat(path):
            if str(path) == "/run/hysteria2-panel-node-main":
                return Metadata(stat.S_IFDIR | 0o700)
            return Metadata(stat.S_IFREG | 0o600)

        with self.assertRaises(ProtocolError):
            run_hysteria_from_template(
                "/opt/hysteria2-panel-node/bin/hysteria",
                template,
                "/run/hysteria2-panel-node-main/config.yaml",
                lstat=occupied_lstat,
                **common,
            )


class DataPlaneAttestationTests(unittest.TestCase):
    def setUp(self):
        HysteriaIdentityProviderTests.setUp(self)
        provider = HysteriaIdentityProvider(
            self.cert_path,
            self.key_path,
            egress_policy_provider=lambda: "web",
        )
        identity = provider()
        self.root = Path(self.temp_dir.name)
        self.metadata_path = self.root / "bootstrap.json"
        self.metadata_path.write_text(
            json.dumps(
                {
                    "certificateFileSha256": identity["certificateFileSha256"],
                    "certificateDerSha256": identity["certificateDerSha256"],
                    "privateKeyPublicSha256": identity["privateKeyPublicSha256"],
                    "hysteriaVersion": "2.12.1",
                    "hysteriaSha256": "f" * 64,
                    "egressPolicy": "web",
                    "mainPort": 24443,
                    "configProtocolVersion": 1,
                }
            ),
            encoding="ascii",
        )
        os.chmod(self.metadata_path, 0o600)
        os.chmod(self.cert_path, 0o600)
        os.chmod(self.key_path, 0o600)

    def tearDown(self):
        HysteriaIdentityProviderTests.tearDown(self)

    def test_attestation_requires_every_fixed_service_listener_and_stats_endpoint(self):
        services = []
        listeners = []
        stats = []

        result = collect_data_plane_attestation(
            self.metadata_path,
            self.cert_path,
            self.key_path,
            "S" * 48,
            service_checker=lambda unit: services.append(unit) or True,
            listener_checker=lambda kind, port: listeners.append((kind, port)) or True,
            stats_checker=lambda url, secret: stats.append((url, secret)) or True,
        )

        self.assertEqual(
            {
                "certificateFileSha256",
                "certificateDerSha256",
                "privateKeyPublicSha256",
                "hysteriaVersion",
                "egressPolicy",
                "configProtocolVersion",
                "servicesHealthy",
                "statsHealthy",
                "udp19999Listening",
                "udp443Listening",
                "tcp19999Listening",
                "tcp443Listening",
            },
            set(result),
        )
        self.assertTrue(all(value is True for key, value in result.items() if key.endswith("Healthy") or key.endswith("Listening")))
        self.assertEqual(6, len(services))
        self.assertEqual(
            [("udp", 24443), ("udp", 443), ("tcp", 24443), ("tcp", 443)],
            listeners,
        )
        self.assertEqual(
            [
                ("http://127.0.0.1:19997", "S" * 48),
                ("http://127.0.0.1:19995", "S" * 48),
            ],
            stats,
        )

    def test_attestation_fails_closed_before_ack_on_identity_or_health_failure(self):
        cases = (
            {"service_checker": lambda _unit: False},
            {"listener_checker": lambda _kind, _port: False},
            {"stats_checker": lambda _url, _secret: False},
        )
        for overrides in cases:
            with self.subTest(overrides=tuple(overrides)):
                arguments = {
                    "service_checker": lambda _unit: True,
                    "listener_checker": lambda _kind, _port: True,
                    "stats_checker": lambda _url, _secret: True,
                }
                arguments.update(overrides)
                with self.assertRaises(ProtocolError):
                    collect_data_plane_attestation(
                        self.metadata_path,
                        self.cert_path,
                        self.key_path,
                        "S" * 48,
                        **arguments
                    )

        metadata = json.loads(self.metadata_path.read_text())
        metadata["certificateFileSha256"] = "0" * 64
        self.metadata_path.write_text(json.dumps(metadata), encoding="ascii")
        with self.assertRaises(ProtocolError):
            collect_data_plane_attestation(
                self.metadata_path,
                self.cert_path,
                self.key_path,
                "S" * 48,
                service_checker=lambda _unit: True,
                listener_checker=lambda _kind, _port: True,
                stats_checker=lambda _url, _secret: True,
            )


if __name__ == "__main__":
    unittest.main()
