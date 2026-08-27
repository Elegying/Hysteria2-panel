import base64
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hy2panel.nodes import NodeEnrollmentService
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
            panel_url="https://panel.ssrvpn.vip:19998",
            panel_version="0.24.0",
            clock=lambda: self.now,
            token_factory=lambda: "a" * 43,
        )
        issued = service.create(
            name="US9929",
            expected_ip="154.9.234.210",
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
            remote_ip="154.9.234.210",
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
                remote_ip="154.9.234.210",
            )
        )
        self.assertFalse(
            self.db.accept_node_heartbeat(
                self.node_id,
                nonce_digest=nonce_digest,
                sent_at=self.now + 4,
                accepted_at=self.now + 5,
                remote_ip="154.9.234.210",
            )
        )
        node = self.db.get_node_for_heartbeat(self.node_id)
        self.assertEqual(self.now + 3, node["last_heartbeat_at"])
        self.assertEqual("154.9.234.210", node["last_heartbeat_ip"])

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
                remote_ip="154.9.234.210",
            )
        )


if __name__ == "__main__":
    unittest.main()
