import hashlib
import unittest
from unittest import mock

from hysteria2_panel import sqlite_connection
from hy2panel.nodes import DataPlaneBootstrapRejected
from tests import test_data_plane_bootstrap as fixtures


class BootstrapLifecycleBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DataPlaneBootstrapContractTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.f = self.fixture
        self.digest = hashlib.sha256(self.f.token.encode("ascii")).hexdigest()

    def stop(self):
        command = self.f.db.request_node_stop(
            self.f.node_id, "admin", self.f.now[0], emergency=True
        )
        self.assertTrue(self.f.db.ack_node_command(
            self.f.node_id, command["commandId"], True, "", "a" * 64, self.f.now[0]
        ))

    def test_stopped_and_archived_nodes_cannot_fetch_or_reissue_bootstrap(self):
        self.stop()
        self.f.service.token_factory = lambda: "replacement_" + "C" * 40
        for state in ("stopped", "archived"):
            if state == "archived":
                self.assertTrue(self.f.db.archive_stopped_node(
                    self.f.node_id, "admin", self.f.now[0]
                ))
            with self.subTest(state=state):
                with self.assertRaises(DataPlaneBootstrapRejected):
                    self.f.service.fetch(self.f._bootstrap_payload(), self.f.remote_ip)
                with self.assertRaises(ValueError):
                    self.f.service.issue(self.f.node_id, "admin")
                self.assertIsNone(self.f.db.fetch_data_plane_bootstrap(
                    self.f.node_id, self.digest, self.f.remote_ip, "b" * 64, self.f.now[0]
                ))
        with sqlite_connection(str(self.f.db_path)) as connection:
            grant = connection.execute(
                "SELECT fetch_attempts, revoked_at FROM node_data_plane_bootstrap_grants"
            ).fetchone()
            self.assertEqual((0, None), grant)
            self.assertEqual(0, connection.execute(
                "SELECT COUNT(*) FROM node_request_nonces WHERE purpose IN ('bootstrap-claim', 'data-plane-bootstrap', 'data-plane-ack')"
            ).fetchone()[0])

    def test_non_active_claim_and_ack_are_atomic_and_resume_restores_eligibility(self):
        self.f.service.fetch(self.f._bootstrap_payload(), self.f.remote_ip)
        for state in ("draining", "stopping", "stopped", "starting", "disconnecting", "archived"):
            with self.subTest(state=state):
                with sqlite_connection(str(self.f.db_path)) as connection:
                    connection.execute(
                        "UPDATE nodes SET lifecycle_state = ? WHERE node_id = ?",
                        (state, self.f.node_id),
                    )
                self.assertIsNone(self.f.db.create_data_plane_bootstrap_grant(
                    self.f.node_id, "d" * 64, self.f.remote_ip, "admin",
                    self.f.now[0], self.f.now[0] + 600,
                    auto_enable=True, nonce_digest="e" * 64,
                ))
                self.assertFalse(self.f.db.acknowledge_data_plane_bootstrap(
                    self.f.node_id, self.digest, self.f.remote_ip, "f" * 64,
                    self.f.now[0],
                ))
        with sqlite_connection(str(self.f.db_path)) as connection:
            grant = connection.execute(
                "SELECT fetch_attempts, acknowledged_at, revoked_at FROM node_data_plane_bootstrap_grants"
            ).fetchone()
            self.assertEqual((1, None, None), grant)
            self.assertEqual(1, connection.execute(
                "SELECT COUNT(*) FROM node_request_nonces"
            ).fetchone()[0])
            connection.execute("UPDATE nodes SET lifecycle_state = 'active'")
        self.stop()
        resume = self.f.db.request_node_resume(self.f.node_id, "admin", self.f.now[0])
        with self.assertRaises(DataPlaneBootstrapRejected):
            self.f.service.fetch(self.f._bootstrap_payload(value=3), self.f.remote_ip)
        self.assertTrue(self.f.db.ack_node_command(
            self.f.node_id, resume["commandId"], True, "", "c" * 64, self.f.now[0]
        ))
        self.assertEqual(2, self.f.service.fetch(
            self.f._bootstrap_payload(value=3), self.f.remote_ip
        )["fetchAttempt"])
        self.assertEqual("DATA_PLANE_INSTALLED", self.f.service.ack(
            self.f._ack_payload(value=4), self.f.remote_ip
        )["status"])

    def test_stop_during_signature_verification_blocks_identity_release(self):
        def verify(*_args):
            self.stop()
            return True

        self.f.service.signature_verifier = verify
        with mock.patch.object(self.f.service, "_identity") as identity:
            with self.assertRaises(DataPlaneBootstrapRejected):
                self.f.service.fetch(self.f._bootstrap_payload(), self.f.remote_ip)
            identity.assert_not_called()
