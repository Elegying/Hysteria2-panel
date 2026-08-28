import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

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
    HysteriaIdentityProvider,
    canonical_data_plane_request,
)


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
            panel_url="https://panel.ssrvpn.vip:19998",
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
        self.assertNotIn("vpn.ssrvpn.vip", command)
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
            panel_url="https://panel.ssrvpn.vip:19998",
            panel_version="0.27.0",
            clock=lambda: self.now[0],
            token_factory=lambda: self.token,
            signature_verifier=lambda _key, _message, _signature: True,
            identity_provider=lambda: dict(self.identity),
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
        self.assertEqual({"main": 19999, "udp443": 443}, result["ports"])
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
                "/CN=vpn.ssrvpn.vip",
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
            panel_url="https://panel.ssrvpn.vip:19998",
            panel_version="0.27.0",
            clock=lambda: self.now[0],
            token_factory=lambda: self.token,
            signature_verifier=lambda _key, _message, _signature: True,
            identity_provider=lambda: dict(self.identity),
        )
        self.application = PanelApplication(
            database=self.db,
            public_host="vpn.ssrvpn.vip",
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

        fetched = json.loads(
            self._post_json(
                "/api/v1/node-data-plane/bootstrap", self._bootstrap_payload()
            )
            .read()
            .decode("utf-8")
        )
        self.assertEqual(self.identity["privateKeyPem"], fetched["privateKeyPem"])

        ack = self._common(2)
        ack.update(
            {
                "bootstrapToken": self.token,
                "requestId": "2" * 32,
                "certificateFileSha256": "a" * 64,
                "certificateDerSha256": "b" * 64,
                "privateKeyPublicSha256": "c" * 64,
                "hysteriaVersion": "2.12.1",
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
            "ports": {"main": 19999, "udp443": 443},
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
            {"ports": {"main": 19998, "udp443": 443}},
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
        self.assertIn("listen: :19999", main)
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
            self.assertNotIn("vpn.ssrvpn.vip", config)
            self.assertNotIn("panel.ssrvpn.vip", config)

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
                "privateKeyPublicSha256",
            },
            set(metadata),
        )
        persisted = b"".join(path.read_bytes() for path in destination.iterdir())
        self.assertNotIn(token.encode("ascii"), persisted)
        self.assertNotIn(b"vpn.ssrvpn.vip", persisted)

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
            descriptor = int(arguments[-1].rsplit("/", 1)[1])
            captured["config"] = os.pread(descriptor, 65536, 0).decode("ascii")
            raise Executed

        anonymous = Path(self.temp_dir.name) / "anonymous-memory-test"

        environment = {
            "HY2PANEL_STATS_SECRET": "S" * 48,
            "HYSTERIA_DISABLE_UPDATE_CHECK": "1",
        }
        with self.assertRaises(Executed):
            run_hysteria_from_template(
                "/opt/hysteria2-panel-node/bin/hysteria",
                template,
                environment=environment,
                execve=execve,
                memfd_factory=lambda: os.open(
                    anonymous, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600
                ),
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
        self.assertTrue(captured["arguments"][-1].startswith("/proc/self/fd/"))
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
                    environment={"HY2PANEL_STATS_SECRET": "S" * 48},
                    execve=lambda *_args: None,
                    memfd_factory=lambda: -1,
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
            [("udp", 19999), ("udp", 443), ("tcp", 19999), ("tcp", 443)],
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
