import base64
import hashlib
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from hy2panel.nodes import (
    HeartbeatRejected,
    NodeEnrollmentService,
    NodeHeartbeatService,
    OpenSSLSignatureVerifier,
    canonical_heartbeat,
)
from hysteria2_panel import Database


def ed25519_public_key(value=7):
    der = bytes.fromhex("302a300506032b6570032100") + bytes([value]) * 32
    return base64.b64encode(der).decode("ascii")


def token_from_command(command):
    marker = "HY2PANEL_ENROLLMENT_TOKEN='"
    start = command.index(marker) + len(marker)
    return command[start : command.index("'", start)]


class NodeControlDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "panel.db"
        self.db = Database(self.db_path, b"c" * 32)
        self.db.initialize()
        self.now = 2_000_000_000
        service = NodeEnrollmentService(
            self.db,
            panel_url="https://panel.example.com:19998",
            panel_version="0.24.0",
            clock=lambda: self.now,
            token_factory=lambda: "a" * 43,
        )
        issued = service.create(
            name="US9929",
            expected_ip="8.8.8.8",
            ttl_minutes=10,
            actor="admin",
        )
        token = token_from_command(issued["deploymentCommand"])
        service.register(
            {
                "enrollmentToken": token,
                "publicKey": ed25519_public_key(),
                "hostname": "US9929",
                "platform": "linux",
                "architecture": "amd64",
                "agentVersion": "0.24.0",
            },
            remote_ip="8.8.8.8",
        )
        self.node_id = issued["nodeId"]
        self.fingerprint = hashlib.sha256(
            base64.b64decode(ed25519_public_key())
        ).hexdigest()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initialize_adds_node_control_schema_idempotently(self):
        self.db.initialize()
        with sqlite3.connect(str(self.db_path)) as connection:
            node_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(nodes)")
            }
            nonce_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(node_heartbeat_nonces)"
                )
            }
        self.assertTrue(
            {
                "verified_at",
                "verified_by",
                "last_heartbeat_at",
                "last_heartbeat_ip",
            }.issubset(node_columns)
        )
        self.assertEqual(
            {"node_id", "nonce_digest", "accepted_at"}, nonce_columns
        )

    def test_verify_requires_the_exact_public_key_fingerprint(self):
        self.assertFalse(
            self.db.verify_node(
                self.node_id, "0" * 64, actor="admin", verified_at=self.now + 1
            )
        )
        self.assertTrue(
            self.db.verify_node(
                self.node_id,
                self.fingerprint,
                actor="admin",
                verified_at=self.now + 1,
            )
        )
        node = self.db.get_node_for_heartbeat(self.node_id)
        self.assertEqual(self.now + 1, node["verified_at"])
        self.assertEqual("admin", node["verified_by"])
        self.assertEqual("pending_verification", node["status"])

    def test_heartbeat_acceptance_is_atomic_and_replay_safe(self):
        self.assertTrue(
            self.db.verify_node(
                self.node_id,
                self.fingerprint,
                actor="admin",
                verified_at=self.now + 1,
            )
        )
        nonce_digest = hashlib.sha256(b"one-time nonce").hexdigest()
        self.assertTrue(
            self.db.accept_node_heartbeat(
                self.node_id,
                nonce_digest=nonce_digest,
                sent_at=self.now + 2,
                accepted_at=self.now + 3,
                remote_ip="8.8.8.8",
                agent_version="0.25.0",
            )
        )
        self.assertFalse(
            self.db.accept_node_heartbeat(
                self.node_id,
                nonce_digest=nonce_digest,
                sent_at=self.now + 4,
                accepted_at=self.now + 5,
                remote_ip="8.8.8.8",
                agent_version="0.26.0",
            )
        )
        node = self.db.get_node_for_heartbeat(self.node_id)
        self.assertEqual(self.now + 3, node["last_heartbeat_at"])
        self.assertEqual("8.8.8.8", node["last_heartbeat_ip"])
        self.assertEqual("0.25.0", node["agent_version"])

    def test_revoked_node_cannot_be_verified_or_accept_heartbeats(self):
        self.assertTrue(self.db.revoke_node(self.node_id, revoked_at=self.now + 1))
        self.assertFalse(
            self.db.verify_node(
                self.node_id,
                self.fingerprint,
                actor="admin",
                verified_at=self.now + 2,
            )
        )
        self.assertFalse(
            self.db.accept_node_heartbeat(
                self.node_id,
                nonce_digest=hashlib.sha256(b"nonce").hexdigest(),
                sent_at=self.now + 2,
                accepted_at=self.now + 2,
                remote_ip="8.8.8.8",
                agent_version="0.25.0",
            )
        )


class NodeHeartbeatServiceTests(NodeControlDatabaseTests):
    def setUp(self):
        super().setUp()
        self.assertTrue(
            self.db.verify_node(
                self.node_id,
                self.fingerprint,
                actor="admin",
                verified_at=self.now,
            )
        )
        self.verifications = []

        def verifier(public_key, message, signature):
            self.verifications.append((public_key, message, signature))
            return signature == b"s" * 64

        self.service = NodeHeartbeatService(
            self.db,
            clock=lambda: self.now,
            signature_verifier=verifier,
            verification_slots=1,
        )

    def payload(self, **changes):
        values = {
            "nodeId": self.node_id,
            "sentAt": self.now,
            "nonce": base64.urlsafe_b64encode(b"n" * 32).rstrip(b"=").decode("ascii"),
            "hostname": "US9929",
            "agentVersion": "0.25.0",
            "signature": base64.b64encode(b"s" * 64).decode("ascii"),
        }
        values.update(changes)
        return values

    def test_canonical_message_is_versioned_sorted_compact_utf8(self):
        payload = self.payload()
        expected = (
            "hy2panel-node-heartbeat-v1\n"
            '{"agentVersion":"0.25.0","hostname":"US9929",'
            '"nodeId":"' + self.node_id + '","nonce":"' + payload["nonce"]
            + '","sentAt":2000000000}'
        ).encode("utf-8")
        self.assertEqual(expected, canonical_heartbeat(payload))
        self.assertNotIn(b"signature", canonical_heartbeat(payload))

    def test_valid_signed_heartbeat_becomes_online_and_replay_fails(self):
        payload = self.payload()
        result = self.service.accept(payload, remote_ip="8.8.8.8")
        self.assertEqual(
            {
                "status": "ONLINE",
                "acceptedAt": self.now,
                "nextHeartbeatSeconds": 60,
            },
            result,
        )
        self.assertEqual(ed25519_public_key(), self.verifications[0][0])
        self.assertEqual(canonical_heartbeat(payload), self.verifications[0][1])
        self.assertEqual(
            "0.25.0", self.db.get_node_for_heartbeat(self.node_id)["agent_version"]
        )
        with self.assertRaises(HeartbeatRejected):
            self.service.accept(payload, remote_ip="8.8.8.8")

    def test_stale_wrong_ip_bad_signature_and_unknown_fields_fail_closed(self):
        cases = (
            self.payload(sentAt=self.now - 121),
            self.payload(signature=base64.b64encode(b"x" * 64).decode("ascii")),
            self.payload(extra="field"),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(HeartbeatRejected):
                    self.service.accept(payload, remote_ip="8.8.8.8")
        with self.assertRaises(HeartbeatRejected):
            self.service.accept(self.payload(), remote_ip="8.8.4.4")

    def test_malformed_values_fail_before_signature_verification(self):
        cases = (
            self.payload(nodeId="not-a-node"),
            self.payload(sentAt=True),
            self.payload(nonce="short"),
            self.payload(hostname="bad host"),
            self.payload(agentVersion="latest"),
            self.payload(signature="not-base64"),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                before = len(self.verifications)
                with self.assertRaises(HeartbeatRejected):
                    self.service.accept(payload, remote_ip="8.8.8.8")
                self.assertEqual(before, len(self.verifications))

    def test_signature_verification_capacity_fails_closed(self):
        self.assertTrue(self.service._verification_gate.acquire(blocking=False))
        try:
            with self.assertRaises(HeartbeatRejected):
                self.service.accept(self.payload(), remote_ip="8.8.8.8")
        finally:
            self.service._verification_gate.release()
        self.assertEqual([], self.verifications)


class OpenSSLSignatureVerifierTests(unittest.TestCase):
    def test_verifies_real_ed25519_signature_and_rejects_tampering(self):
        homebrew_openssl = Path("/opt/homebrew/opt/openssl@3/bin/openssl")
        openssl = str(homebrew_openssl) if homebrew_openssl.exists() else shutil.which("openssl")
        self.assertIsNotNone(openssl)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            private_key = directory / "private.pem"
            public_der = directory / "public.der"
            signature = directory / "signature.bin"
            message_path = directory / "message.bin"
            message = b"signed heartbeat"
            message_path.write_bytes(message)
            subprocess.run(
                [openssl, "genpkey", "-algorithm", "ED25519", "-out", private_key],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    openssl,
                    "pkey",
                    "-in",
                    private_key,
                    "-pubout",
                    "-outform",
                    "DER",
                    "-out",
                    public_der,
                ],
                check=True,
                capture_output=True,
            )
            signed = subprocess.run(
                [
                    openssl,
                    "pkeyutl",
                    "-sign",
                    "-rawin",
                    "-inkey",
                    private_key,
                    "-in",
                    message_path,
                ],
                check=True,
                capture_output=True,
            )
            signature.write_bytes(signed.stdout)
            verifier = OpenSSLSignatureVerifier(executable=openssl)
            public_key = base64.b64encode(public_der.read_bytes()).decode("ascii")
            self.assertTrue(verifier(public_key, message, signature.read_bytes()))
            self.assertFalse(verifier(public_key, message + b"!", signature.read_bytes()))


if __name__ == "__main__":
    unittest.main()
