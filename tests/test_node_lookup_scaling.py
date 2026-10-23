"""Small signed reports must not scan unrelated accounts under the write lock."""
import contextlib
from unittest import mock

from test_distributed_control import DistributedControlCase


class NodeLookupScalingTests(DistributedControlCase):
    def test_small_reports_have_bounded_work_as_unrelated_accounts_grow(self):
        self.db.create_proxy_user("active")
        original = self.db._connect
        steps = [0]

        @contextlib.contextmanager
        def counted():
            with original() as connection:
                def progress():
                    steps[0] += 1
                    return 0
                connection.set_progress_handler(progress, 1)
                yield connection

        def measure(sequence):
            results = []
            with mock.patch.object(self.db, "_connect", counted):
                steps[0] = 0
                result = self.db.apply_node_traffic_batch(
                    self.nodes[0], "{:032x}".format(sequence),
                    {"active": {"tx": 1, "rx": 2}}, "{:064x}".format(sequence),
                    self.now[0], observed_at=self.now[0])
                self.assertTrue(result["committed"])
                results.append(steps[0])
                steps[0] = 0
                self.assertTrue(self.db.accept_node_online_snapshot(
                    self.nodes[0], "{:032x}".format(sequence), sequence,
                    self.now[0], self.now[0], {}, "{:064x}".format(sequence + 100), self.now[0]))
                results.append(steps[0])
            return results

        initial = measure(1)
        with self.db._connect() as connection:
            connection.executemany(
                "INSERT INTO proxy_users(name,token_fingerprint,created_at,updated_at) VALUES (?,?,?,?)",
                [("unrelated-{}".format(i), "{:064x}".format(i + 1), self.now[0], self.now[0])
                 for i in range(999)])
        expanded = measure(2)
        for label, before, after in zip(("traffic", "empty snapshot"), initial, expanded):
            with self.subTest(report=label):
                self.assertLess(after, before * 2 + 100, (label, before, after))
        self.assertEqual(6, sum(self.db.get_proxy_user_by_name("active")[field]
                                for field in ("tx_bytes", "rx_bytes")))

    def test_report_names_keep_exact_case_and_retired_identity_rules(self):
        user = self.db.create_proxy_user("Alice")
        result = self.db.apply_node_traffic_batch(
            self.nodes[0], "a" * 32, {"alice": {"tx": 1, "rx": 2}}, "a" * 64,
            self.now[0], observed_at=self.now[0])
        self.assertEqual(1, result["unknownUsers"])
        self.assertEqual(0, self.db.get_proxy_user_by_name("Alice")["tx_bytes"])
        self.assertFalse(self.db.accept_node_online_snapshot(
            self.nodes[0], "b" * 32, 1, self.now[0], self.now[0], {"alice": 1}, "b" * 64, self.now[0]))
        self.assertTrue(self.db.accept_node_online_snapshot(
            self.nodes[0], "c" * 32, 1, self.now[0], self.now[0], {"Alice": 1}, "c" * 64, self.now[0]))
        self.db.delete_proxy_user(user["id"])
        self.assertTrue(self.db.accept_node_online_snapshot(
            self.nodes[0], "d" * 32, 2, self.now[0], self.now[0], {"Alice": 1}, "d" * 64, self.now[0]))
        self.assertEqual({}, self.db.node_online_counts(self.nodes[0]))
