import base64
import json
import unittest
from unittest import mock
from tests import test_panel as fixtures
import hysteria2_panel as panel


class FakeHopping:
    enabled = False
    fail = False

    def status(self):
        return {"enabled": self.enabled, "ports": "20000-50000", "target": 443}

    def set_enabled(self, enabled):
        if self.fail:
            raise RuntimeError("failed")
        self.enabled = enabled
        return self.status()


class HoppingTests(unittest.TestCase):
    setUp = fixtures.PanelHttpTests.setUp
    tearDown = fixtures.PanelHttpTests.tearDown
    request = fixtures.PanelHttpTests.request
    authenticated_headers = fixtures.PanelHttpTests.authenticated_headers

    def test_toggle_updates_original_subscription_and_preserves_identity(self):
        self.application.port_hopping_controller = FakeHopping()
        user = self.db.create_proxy_user("hopping", allow_udp_443=False)
        sub = self.db.ensure_subscription(user["id"])
        self.assertEqual(
            "hopping", self.db.authenticate_token(user["token"], require_udp_443=True)
        )
        path = "/sub/" + sub["token"]
        headers, csrf = self.authenticated_headers()
        for action in ("enable", "disable"):
            with self.request(
                "/port-hopping/" + action, {"csrf": csrf}, headers=headers
            ) as response:
                self.assertEqual(action == "enable", json.load(response)["enabled"])
            with self.request(path) as response:
                uri = base64.b64decode(response.read()).decode()
                self.assertIn(":20000-50000/" if action == "enable" else ":443/", uri)
                self.assertIn(user["token"], uri)
            with self.request(path + "?format=clash") as response:
                proxy = json.load(response)["proxies"][0]
                self.assertEqual(action == "enable", "ports" in proxy)
                if action == "enable":
                    self.assertEqual("20000-50000", proxy["ports"])
                    self.assertEqual(30, proxy["hop-interval"])
            self.assertEqual(sub, self.db.ensure_subscription(user["id"]))
        with self.request("/", headers=headers) as response:
            html = response.read().decode()
        for removed in (
            "create-allow-udp-443",
            "edit-allow-udp-443",
            'class="egress-control"',
        ):
            self.assertNotIn(removed, html)

    def test_ssrvpn_keeps_usage_binding_and_hopping_in_default_format(self):
        hopping = FakeHopping()
        hopping.enabled = True
        self.application.port_hopping_controller = hopping
        user = self.db.create_proxy_user("ssrvpn-client")
        sub = self.db.ensure_subscription(user["id"])
        path = "/sub/" + sub["token"]
        for agent in (
            "SSRVPN/1.0",
            "clash-verge/v2.5.2 SSRVPN/1.0",
            "Shadowrocket/2.2.91 SSRVPN/1.0",
        ):
            with self.subTest(agent=agent), \
                 self.request(path, headers={'User-Agent': agent}) as response:
                proxy = json.load(response)["proxies"][0]
                self.assertEqual(443, proxy["port"])
                self.assertEqual("20000-50000", proxy["ports"])
                self.assertEqual(30, proxy["hop-interval"])
                self.assertEqual(user["token"], proxy["password"])
                self.assertIn(
                    "total=268435456000", response.headers["Subscription-Userinfo"]
                )
        with self.request(
            path + "?format=raw", headers={"User-Agent": "SSRVPN/1.0"}
        ) as response:
            self.assertTrue(response.read().startswith(b"hysteria2://"))

    def test_shadowrocket_gets_readable_status_and_compatible_hopping(self):
        hopping = FakeHopping()
        hopping.enabled = True
        self.application.port_hopping_controller = hopping
        user = self.db.create_proxy_user("shadowrocket")
        sub = self.db.ensure_subscription(user["id"])
        self.db.add_traffic({"shadowrocket": {"tx": 1024**3, "rx": 2 * 1024**3}})
        with self.request(
            "/sub/" + sub["token"], headers={"User-Agent": "Shadowrocket/3000"}
        ) as response:
            text = base64.b64decode(response.read()).decode()
            self.assertIsNone(response.headers.get("Subscription-Userinfo"))
            self.assertIn("STATUS=剩余 247.00 / 250 GiB · 已用 3.00 GiB · 永久", text)
            self.assertIn(":443/", text)
            self.assertIn("mport=20000-50000", text)
            self.assertIn("keepalive=30", text)

    def test_hopping_only_applies_to_matching_local_endpoint(self):
        hopping = FakeHopping()
        hopping.enabled = True
        self.application.port_hopping_controller = hopping
        user = self.db.create_proxy_user("remote")
        sub = self.db.ensure_subscription(user["id"])
        self.db.set_subscription_defaults(
            [
                {
                    "label": "remote",
                    "host": "elsewhere.example.com",
                    "port": 443,
                    "pin_sha256": "ab" * 32,
                }
            ]
        )
        with self.request("/sub/" + sub["token"] + "?format=clash") as response:
            self.assertNotIn("ports", json.load(response)["proxies"][0])

    def test_toggle_failure_and_csrf_do_not_claim_success(self):
        hopping = FakeHopping()
        hopping.fail = True
        self.application.port_hopping_controller = hopping
        headers, csrf = self.authenticated_headers()
        import urllib.error

        for token, status in [("bad", 403), (csrf, 503)]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request("/port-hopping/enable", {"csrf": token}, headers=headers)
            self.assertEqual(status, error.exception.code)
        self.assertFalse(hopping.enabled)

    def test_privileged_controller_uses_fixed_commands(self):
        runner = mock.Mock(return_value=mock.Mock(returncode=0))
        controller = panel.PortHoppingController(runner=runner)
        with mock.patch.object(controller, "status", return_value={"enabled": True}):
            controller.set_enabled(True)
        self.assertEqual(
            [
                "/usr/bin/sudo",
                "-n",
                "/bin/systemctl",
                "enable",
                "--now",
                controller.UNIT,
            ],
            runner.call_args.args[0],
        )


class HoppingFirewallTests(unittest.TestCase):
    def test_fixed_firewall_program_and_state_commit(self):
        import contextlib
        import os
        import stat
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            calls = []

            def run(command, **kwargs):
                calls.append((command, kwargs))
                return SimpleNamespace(
                    returncode=1 if "list" in command else 0, stdout=""
                )

            real_lstat = Path.lstat

            def metadata(path):
                if path == state.parent:
                    return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0)
                return real_lstat(path)

            with mock.patch.object(panel.PortHoppingController, 'STATE', state), \
                 mock.patch.object(os, 'geteuid', return_value=0), \
                 mock.patch.object(Path, 'lstat', metadata), \
                 mock.patch.object(panel.Settings, 'from_mapping', return_value=SimpleNamespace(hysteria_port=443)), \
                 mock.patch.object(panel, 'exclusive_maintenance_lock', return_value=contextlib.nullcontext()), \
                 mock.patch.object(panel.subprocess, 'run', side_effect=run):
                panel.apply_port_hopping(True)
            self.assertEqual(
                {"enabled": True, "target": 443}, json.loads(state.read_text())
            )
            script = calls[-1][1]["input"]
            self.assertIn("udp dport 20000-50000 redirect to :443", script)
            self.assertIn("tcp dport 20000-50000 redirect to :443", script)
            self.assertIn("fib daddr type local", script)
            self.assertNotIn("flush ruleset", script)
            self.assertIn("-c", calls[-2][0])
