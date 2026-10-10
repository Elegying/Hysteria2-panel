import copy
import json
from pathlib import Path
import shlex
import unittest

import test_installer


class HostGuardFirewallTests(unittest.TestCase):
    run_firewall_function = test_installer.InstallerContractTests.run_firewall_function

    def setUp(self):
        self.payload = json.loads(
            (Path(__file__).parent / "fixtures" / "host_guard.json").read_text()
        )

    def run_guard(self, payload, settings=""):
        mocks = """
ufw() { printf 'Status: inactive\\n'; }
firewall-cmd() { printf 'not running\\n'; return 1; }
iptables-save() { printf '%s\\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
ip6tables-save() { printf '%s\\n' '*filter' ':INPUT ACCEPT [0:0]' 'COMMIT'; }
"""
        mocks += "\nnft() {{ printf '%s\\n' {}; }}\n{}\n".format(
            shlex.quote(json.dumps(payload)), settings
        )
        return self.run_firewall_function(mocks)

    def test_default_guard_preserves_all_rules_and_accepts_live_counters(self):
        for with_live_counters in [False, True]:
            with self.subTest(with_live_counters=with_live_counters):
                payload = copy.deepcopy(self.payload)
                if with_live_counters:
                    for entry in payload["nftables"]:
                        for kind, row in entry.items():
                            if kind != "metainfo":
                                row["handle"] = 25
                            for expression in row.get("expr", []):
                                if "counter" in expression:
                                    expression["counter"] = {"packets": 153, "bytes": 23500}
                result, calls = self.run_guard(payload)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual([], calls)
                self.assertIn("入站策略已核验", result.stdout)

    def test_missing_changed_reordered_or_extra_guard_rules_fail_closed(self):
        rules = [entry["rule"] for entry in self.payload["nftables"] if "rule" in entry]
        for index in range(len(rules)):
            with self.subTest(missing_rule=index):
                payload = copy.deepcopy(self.payload)
                payload["nftables"].remove(next(
                    entry for entry in payload["nftables"] if entry.get("rule") == rules[index]
                ))
                result, calls = self.run_guard(payload)
                self.assertEqual(97, result.returncode)
                self.assertEqual([], calls)
        mutations = {
            "wrong_interface": lambda rows: rows[0]["expr"][0]["match"].update(right="eth0"),
            "missing_udp_port": lambda rows: rows[8]["expr"][0]["match"].update(right=443),
            "inverted_port": lambda rows: rows[8]["expr"][0]["match"].update(op="!="),
            "lower_rate": lambda rows: rows[9]["expr"][1]["meter"]["stmt"]["limit"].update(rate=1),
            "extra_counter_action": lambda rows: rows[-1]["expr"][0].update(drop=None),
            "invalid_counter": lambda rows: rows[-1]["expr"][0]["counter"].update(packets=True),
            "jump": lambda rows: rows[7]["expr"].__setitem__(1, {"jump": {"target": "hidden"}}),
            "extra_drop": lambda rows: rows[7]["expr"].insert(0, {"drop": None}),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                payload = copy.deepcopy(self.payload)
                mutate([entry["rule"] for entry in payload["nftables"] if "rule" in entry])
                result, calls = self.run_guard(payload)
                self.assertEqual(97, result.returncode)
                self.assertEqual([], calls)
        for change in ["duplicate", "reordered"]:
            with self.subTest(change=change):
                payload = copy.deepcopy(self.payload)
                if change == "duplicate":
                    payload["nftables"].append(copy.deepcopy(payload["nftables"][-1]))
                else:
                    payload["nftables"][-1], payload["nftables"][-2] = (
                        payload["nftables"][-2], payload["nftables"][-1]
                    )
                result, calls = self.run_guard(payload)
                self.assertEqual(97, result.returncode)
                self.assertEqual([], calls)

    def test_changed_chain_or_uncovered_service_port_is_rejected(self):
        for field, value in [("policy", "accept"), ("prio", -10),
                             ("hook", "prerouting"), ("type", "nat")]:
            with self.subTest(field=field):
                payload = copy.deepcopy(self.payload)
                next(entry["chain"] for entry in payload["nftables"] if "chain" in entry)[field] = value
                result, calls = self.run_guard(payload)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual([], calls)
        for settings in ["HYSTERIA_PORT=29999", "PANEL_PORT=29998", "DATA_PLANE_MAIN_PORT=22"]:
            with self.subTest(settings=settings):
                result, calls = self.run_guard(self.payload, settings)
                self.assertEqual(97, result.returncode)
                self.assertEqual([], calls)

    def test_recognized_guard_does_not_hide_another_inbound_chain(self):
        for table in ["hy2_host_guard", "another_table"]:
            with self.subTest(table=table):
                payload = copy.deepcopy(self.payload)
                payload["nftables"].append({"chain": {
                    "family": "inet", "table": table, "name": "early",
                    "type": "filter", "hook": "input", "prio": -100, "policy": "drop",
                }})
                result, calls = self.run_guard(payload)
                self.assertEqual(97, result.returncode)
                self.assertEqual([], calls)

    def test_guard_can_coexist_with_the_verified_ssh_ban_rule(self):
        payload = copy.deepcopy(self.payload)
        payload["nftables"].extend([
            {"chain": {"family": "inet", "table": "f2b-table", "name": "f2b-chain",
                       "type": "filter", "hook": "input", "prio": -1, "policy": "accept"}},
            {"rule": {"family": "inet", "table": "f2b-table", "chain": "f2b-chain", "expr": [
                {"match": {"op": "==", "left": {"payload": {"protocol": "tcp", "field": "dport"}}, "right": 22}},
                {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "saddr"}}, "right": "@addr-set-sshd"}},
                {"counter": {"packets": 33, "bytes": 1980}}, {"drop": None},
            ]}},
        ])
        result, calls = self.run_guard(payload)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], calls)
