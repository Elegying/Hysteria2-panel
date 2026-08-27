import base64
import hashlib
import re
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from hy2panel.nodes import EnrollmentRejected, NodeEnrollmentService
from hysteria2_panel import Database


def ed25519_public_key(value=7):
    der = bytes.fromhex("302a300506032b6570032100") + bytes([value]) * 32
    return base64.b64encode(der).decode("ascii")


def registration_payload(token, public_key=None):
    return {
        "enrollmentToken": token,
        "publicKey": public_key or ed25519_public_key(),
        "hostname": "edge-02.example.test",
        "platform": "linux",
        "architecture": "amd64",
        "agentVersion": "0.24.0",
    }


def token_from_command(command):
    match = re.search(r"HY2PANEL_ENROLLMENT_TOKEN='([^']+)'", command)
    if not match:
        raise AssertionError("deployment command does not contain the one-time token")
    return match.group(1)


class NodeEnrollmentDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "panel.db"
        self.db = Database(self.db_path, b"n" * 32)
        self.db.initialize()
        self.now = [2_000_000_000]
        self.service = NodeEnrollmentService(
            self.db,
            panel_url="https://panel.ssrvpn.vip:19998",
            panel_version="0.24.0",
            clock=lambda: self.now[0],
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def create(self, **changes):
        values = {
            "name": "香港分流-02",
            "expected_ip": "203.0.113.10",
            "ttl_minutes": 10,
            "actor": "admin",
        }
        values.update(changes)
        return self.service.create(**values)

    def test_create_stores_only_a_digest_and_generates_a_signed_fixed_release_command(self):
        issued = self.create()
        token = token_from_command(issued["deploymentCommand"])

        with sqlite3.connect(str(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            enrollment = connection.execute(
                "SELECT * FROM node_enrollments WHERE enrollment_id = ?",
                (issued["enrollmentId"],),
            ).fetchone()
            node = connection.execute(
                "SELECT * FROM nodes WHERE node_id = ?", (issued["nodeId"],)
            ).fetchone()

        self.assertEqual(hashlib.sha256(token.encode("ascii")).hexdigest(), enrollment["token_digest"])
        self.assertNotEqual(token, enrollment["token_digest"])
        self.assertNotIn(token.encode("ascii"), self.db_path.read_bytes())
        self.assertEqual("pending_registration", node["status"])
        self.assertEqual("203.0.113.10", node["expected_ip"])
        self.assertEqual(self.now[0] + 600, issued["expiresAt"])
        command = issued["deploymentCommand"]
        self.assertIn("v0.24.0", command)
        self.assertIn("install.sh.sigstore.json", command)
        self.assertIn("verify-blob", command)
        self.assertIn("release-signature.yml@refs/tags/v0.24.0", command)
        self.assertIn("--join-node", command)
        self.assertNotIn("vpn.ssrvpn.vip", command)
        self.assertNotIn("server.crt", command)
        self.assertNotIn("HY2PANEL_HMAC_KEY", command)

    def test_registration_consumes_the_token_once_and_moves_the_node_to_pending_verification(self):
        issued = self.create()
        token = token_from_command(issued["deploymentCommand"])

        result = self.service.register(
            registration_payload(token), remote_ip="203.0.113.10"
        )

        self.assertEqual(issued["nodeId"], result["nodeId"])
        self.assertEqual("PENDING_VERIFICATION", result["status"])
        node = self.db.list_nodes()[0]
        self.assertEqual("pending_verification", node["status"])
        self.assertEqual("203.0.113.10", node["observed_ip"])
        self.assertEqual(ed25519_public_key(), node["public_key"])
        with self.assertRaises(EnrollmentRejected):
            self.service.register(
                registration_payload(token), remote_ip="203.0.113.10"
            )

    def test_expired_revoked_wrong_ip_and_malformed_public_keys_fail_closed(self):
        expired = self.create(name="expired", expected_ip="", ttl_minutes=5)
        expired_token = token_from_command(expired["deploymentCommand"])
        self.now[0] += 301
        with self.assertRaises(EnrollmentRejected):
            self.service.register(
                registration_payload(expired_token), remote_ip="198.51.100.20"
            )

        self.now[0] += 1
        revoked = self.create(name="revoked", expected_ip="")
        revoked_token = token_from_command(revoked["deploymentCommand"])
        self.assertTrue(self.service.revoke(revoked["enrollmentId"]))
        self.assertTrue(self.service.revoke(revoked["enrollmentId"]))
        with self.assertRaises(EnrollmentRejected):
            self.service.register(
                registration_payload(revoked_token), remote_ip="198.51.100.20"
            )

        wrong_ip = self.create(name="wrong-ip")
        wrong_ip_token = token_from_command(wrong_ip["deploymentCommand"])
        with self.assertRaises(EnrollmentRejected):
            self.service.register(
                registration_payload(wrong_ip_token), remote_ip="203.0.113.11"
            )

        malformed = self.create(name="bad-key", expected_ip="")
        malformed_token = token_from_command(malformed["deploymentCommand"])
        for public_key in ("not-base64", base64.b64encode(b"wrong").decode("ascii")):
            with self.subTest(public_key=public_key):
                with self.assertRaises(EnrollmentRejected):
                    self.service.register(
                        registration_payload(malformed_token, public_key),
                        remote_ip="198.51.100.20",
                    )

    def test_concurrent_registration_has_exactly_one_success(self):
        issued = self.create(expected_ip="")
        token = token_from_command(issued["deploymentCommand"])
        barrier = threading.Barrier(3)
        outcomes = []

        def register(value):
            barrier.wait()
            try:
                self.service.register(
                    registration_payload(token, ed25519_public_key(value)),
                    remote_ip="198.51.100.20",
                )
                outcomes.append("success")
            except EnrollmentRejected:
                outcomes.append("rejected")

        threads = [threading.Thread(target=register, args=(value,)) for value in (3, 4)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(2)

        self.assertEqual(["rejected", "success"], sorted(outcomes))

    def test_creation_validates_name_ip_ttl_and_https_panel_url(self):
        for changes in (
            {"name": ""},
            {"name": "bad\nname"},
            {"expected_ip": "not-an-ip"},
            {"ttl_minutes": 4},
            {"ttl_minutes": 31},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.create(**changes)

        with self.assertRaises(ValueError):
            NodeEnrollmentService(
                self.db,
                panel_url="http://panel.ssrvpn.vip:19998",
                panel_version="0.24.0",
            )


if __name__ == "__main__":
    unittest.main()
