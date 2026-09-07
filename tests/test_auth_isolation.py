import threading
import unittest

from hy2panel.distributed import DistributedControlService, NodeRequestRejected
from tests.test_distributed_control import DistributedControlCase


class AuthenticationIsolationTests(DistributedControlCase):
    def setUp(self):
        super().setUp()
        self.user = self.db.create_proxy_user("alice")
        self.accept_empty_snapshots()

    def authorize(self, value, node_index=0, token="invalid-token"):
        payload = self.common(self.nodes[node_index], value)
        payload.update(
            requestId="{:032x}".format(value),
            entrypoint="main",
            auth=token,
            tx=0,
        )
        return self.service.authorize(
            payload, remote_ip="203.0.113.{}".format(node_index + 1)
        )

    def poll(self, value):
        payload = self.common(self.nodes[0], value)
        payload["requestId"] = "{:032x}".format(value)
        return self.service.poll_commands(payload, remote_ip="203.0.113.1")

    def test_invalid_auth_burst_keeps_control_and_other_node_auth_available(self):
        self.service.requests_per_minute = 3
        for value in (30, 31, 32):
            self.assertFalse(self.authorize(value)["ok"])
        with self.assertRaises(NodeRequestRejected):
            self.authorize(33)

        cycle = self.common(self.nodes[0], 40)
        cycle.update(
            cycleId="4" * 32,
            trafficBatches=[
                {
                    "batchId": "5" * 32,
                    "observedAt": self.now[0],
                    "traffic": {"alice": {"tx": 3, "rx": 7}},
                }
            ],
            onlineSnapshot=None,
            commandPoll={"requestId": "6" * 32},
        )
        result = self.service.control_cycle(cycle, remote_ip="203.0.113.1")
        self.assertTrue(result["traffic"][0]["committed"])

        self.now[0] += 44
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[1], 41, sequence=2),
            remote_ip="203.0.113.2",
        )
        # The isolation must not relax the existing global freshness requirement.
        with self.assertRaises(NodeRequestRejected):
            self.authorize(42, node_index=1, token=self.user["token"])
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[0], 43, sequence=2),
            remote_ip="203.0.113.1",
        )
        self.assertTrue(
            self.authorize(44, node_index=1, token=self.user["token"])["ok"]
        )

    def test_auth_and_control_rates_remain_bounded_and_recover_independently(self):
        self.service.requests_per_minute = 3
        for value in (30, 31, 32):
            self.assertFalse(self.authorize(value)["ok"])
        with self.assertRaises(NodeRequestRejected):
            self.authorize(33)
        # The initial online snapshot and two polls fill the control-class budget.
        self.poll(34)
        self.poll(35)
        with self.assertRaises(NodeRequestRejected):
            self.poll(36)

        self.now[0] += 60
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[0], 40, sequence=2),
            remote_ip="203.0.113.1",
        )
        self.service.accept_online_snapshot(
            self.snapshot(self.nodes[1], 41, sequence=2),
            remote_ip="203.0.113.2",
        )
        self.assertTrue(self.authorize(42, token=self.user["token"])["ok"])
        self.assertEqual([], self.poll(43)["commands"])

    def test_verification_capacity_is_bounded_and_isolated_in_both_directions(self):
        for blocked_class in ("auth", "control"):
            with self.subTest(blocked_class=blocked_class):
                entered = threading.Event()
                release = threading.Event()
                failures = []

                def verify(_key, message, _signature):
                    is_auth = message.startswith(b"hy2panel-node-auth-v1\n")
                    if is_auth == (blocked_class == "auth"):
                        entered.set()
                        if not release.wait(5):
                            raise TimeoutError("verification test was not released")
                    return True

                self.service = DistributedControlService(
                    self.db,
                    clock=lambda: self.now[0],
                    signature_verifier=verify,
                    local_state_provider=self.local_state,
                    verification_slots=1,
                )
                blocked = self.authorize if blocked_class == "auth" else self.poll
                unblocked = self.poll if blocked_class == "auth" else self.authorize
                value = 50 if blocked_class == "auth" else 60

                def request():
                    try:
                        blocked(value)
                    except Exception as exc:
                        failures.append(exc)

                worker = threading.Thread(target=request)
                worker.start()
                try:
                    self.assertTrue(entered.wait(5))
                    with self.assertRaises(NodeRequestRejected):
                        blocked(value + 1)
                    unblocked(value + 2)
                finally:
                    release.set()
                    worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertEqual([], failures)
                # Completion releases the correct pool for the next request.
                blocked(value + 3)


if __name__ == "__main__":
    unittest.main()
