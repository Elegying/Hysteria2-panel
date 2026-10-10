"""A cached admission reserves capacity but cannot preserve revoked authority."""

import hashlib

from hy2panel.distributed import MAX_STATE_AGE_SECONDS, NodeRequestRejected
from tests.test_distributed_control import DistributedControlCase


class AuthDecisionRevalidationTests(DistributedControlCase):
    def setUp(self):
        super().setUp()
        self.user = self.db.create_proxy_user(
            "cached-admission", allow_udp_443=True, device_limit=10,
            traffic_limit_bytes=100,
        )
        self.accept_empty_snapshots()
        self.sequence = 30
        self.request_id = "f" * 32

    def authorize(self, *, token=None, entrypoint="udp443", request_id=None):
        self.sequence += 1
        payload = self.common(self.nodes[0], self.sequence)
        payload.update(
            requestId=request_id or self.request_id, entrypoint=entrypoint,
            auth=self.user["token"] if token is None else token, tx=0,
        )
        return self.service.authorize(payload, remote_ip="203.0.113.1")

    def assert_cached_denial(self, first, **kwargs):
        result = self.authorize(**kwargs)
        self.assertFalse(result["ok"])
        self.assertEqual("", result["id"])
        self.assertEqual(first["decisionId"], result["decisionId"])
        self.assertEqual(first["expiresAt"], result["expiresAt"])

    def test_identical_retry_reuses_one_reserved_slot_at_the_device_limit(self):
        self.db.update_proxy_user_limits(self.user["id"], 1, 100, allow_udp_443=True)
        first = self.authorize()
        self.assertTrue(first["ok"])
        self.assertEqual(first, self.authorize())
        with self.db._connect() as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM node_auth_decisions").fetchone()[0])
        self.assertFalse(self.authorize(request_id="e" * 32)["ok"])

    def test_udp_permission_revocation_invalidates_a_cached_allow(self):
        first = self.authorize()
        self.assertTrue(first["ok"])
        self.db.update_proxy_user_limits(self.user["id"], 10, 100, allow_udp_443=False)
        self.assert_cached_denial(first)
        self.assertTrue(self.authorize(entrypoint="main", request_id="e" * 32)["ok"])

    def test_a_main_entry_allow_cannot_be_reused_for_a_forbidden_udp_entry(self):
        self.db.update_proxy_user_limits(self.user["id"], 10, 100, allow_udp_443=False)
        first = self.authorize(entrypoint="main")
        self.assertTrue(first["ok"])
        self.assert_cached_denial(first, entrypoint="udp443")

    def test_a_cached_allow_cannot_authenticate_invalid_or_different_credentials(self):
        first = self.authorize()
        self.assertTrue(first["ok"])
        other = self.db.create_proxy_user("other-admission", allow_udp_443=True)
        for token in ("invalid-credential", other["token"]):
            with self.subTest(token_kind="invalid" if token == "invalid-credential" else "other-user"):
                self.assert_cached_denial(first, token=token)

    def test_old_credential_stays_denied_after_security_kick_is_acknowledged(self):
        first = self.authorize()
        self.assertTrue(first["ok"])
        new = self.db.rotate_proxy_token(self.user["id"], drain_local=True)
        self.db.queue_kick_users_on_ready_nodes([self.user["name"]], created_at=self.now[0])
        commands = self.db.poll_node_commands(self.nodes[0], "c" * 64, self.now[0])
        self.assertEqual(1, len(commands))
        self.assert_cached_denial(first)  # The existing security gate already covers this phase.
        self.now[0] += 11
        self.assertTrue(self.db.ack_node_command(
            self.nodes[0], commands[0]["commandId"], True, "", "d" * 64, self.now[0]
        ))
        self.assert_cached_denial(first)
        self.assertTrue(self.authorize(token=new["token"], request_id="e" * 32)["ok"])

    def test_disabled_user_cannot_reuse_an_allowed_decision(self):
        first = self.authorize()
        self.assertTrue(first["ok"])
        self.db.set_proxy_user_enabled(self.user["id"], False)
        self.assert_cached_denial(first)

    def test_exhausted_quota_invalidates_an_allowed_decision(self):
        first = self.authorize()
        self.assertTrue(first["ok"])
        self.db.apply_node_traffic_batch(
            self.nodes[0], "a" * 32, {self.user["name"]: {"tx": 100, "rx": 0}},
            "a" * 64, self.now[0], observed_at=self.now[0],
        )
        self.assert_cached_denial(first)

    def test_reduced_device_limit_is_applied_to_existing_reservations(self):
        first = self.authorize()
        self.assertTrue(first["ok"])
        self.assertTrue(self.authorize(request_id="e" * 32)["ok"])
        self.db.update_proxy_user_limits(self.user["id"], 1, 100, allow_udp_443=True)
        self.assert_cached_denial(first)

    def test_a_cached_denial_stays_denied_when_permission_is_later_granted(self):
        self.db.update_proxy_user_limits(self.user["id"], 10, 100, allow_udp_443=False)
        first = self.authorize()
        self.assertFalse(first["ok"])
        self.db.update_proxy_user_limits(self.user["id"], 10, 100, allow_udp_443=True)
        self.assert_cached_denial(first)
        self.assertTrue(self.authorize(request_id="e" * 32)["ok"])

    def test_cached_allow_cannot_extend_the_snapshot_freshness_window(self):
        self.now[0] += MAX_STATE_AGE_SECONDS - 1
        self.assertTrue(self.authorize()["ok"])
        self.now[0] += 2
        with self.assertRaises(NodeRequestRejected):
            self.authorize()

    def _issue_canary(self, token, nonce):
        digest = hashlib.sha256(token.encode()).hexdigest()
        grant = self.db.create_data_plane_bootstrap_grant(
            self.nodes[0], digest, "203.0.113.1", "audit", self.now[0],
            self.now[0] + 600, auto_enable=True, nonce_digest=nonce,
        )
        self.assertIsNotNone(grant)
        self.assertIsNotNone(self.db.fetch_data_plane_bootstrap(
            self.nodes[0], digest, "203.0.113.1", nonce, self.now[0]
        ))

    def test_reissued_canary_grant_revokes_the_prior_cached_admission(self):
        old_token, new_token = "c" * 43, "d" * 43
        self._issue_canary(old_token, "c" * 64)
        first = self.authorize(token=old_token)
        self.assertTrue(first["ok"])
        self._issue_canary(new_token, "d" * 64)
        self.assert_cached_denial(first, token=old_token)
        self.assertTrue(self.authorize(token=new_token, request_id="e" * 32)["ok"])
