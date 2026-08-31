import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCES = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "mobile" / "lib").rglob("*.dart"))
)
SERVER_SOURCE = (ROOT / "hysteria2_panel.py").read_text(encoding="utf-8")


class MobileApiContractTests(unittest.TestCase):
    def test_every_app_panel_call_has_a_server_route(self):
        routes = (
            ("/api/v1/mobile/capabilities", "/api/v1/mobile/capabilities"),
            ("/api/v1/mobile/auth/login", "/api/v1/mobile/auth/login"),
            ("/api/v1/mobile/auth/refresh", "/api/v1/mobile/auth/refresh"),
            ("/api/v1/mobile/auth/logout", "/api/v1/mobile/auth/logout"),
            ("/api/v1/mobile/overview", "/api/v1/mobile/overview"),
            ("/api/v1/mobile/users", "/api/v1/mobile/users"),
            ("/api/v1/mobile/nodes", "/api/v1/mobile/nodes"),
            ("/api/v1/mobile/node-enrollments", "/api/v1/mobile/node-enrollments"),
            ("/api/v1/mobile/service/$action", "service/(start|restart|stop)"),
            ("/api/v1/mobile/system/reboot", "/api/v1/mobile/system/reboot"),
            (
                "/api/v1/mobile/nodes/$nodeId/${enabled ? 'enable' : 'disable'}",
                "nodes/local/(enable|disable)",
            ),
            (
                "/api/v1/mobile/nodes/$nodeId/${enabled ? 'enable' : 'disable'}",
                "nodes/([0-9a-f]{32})/(enable|disable)",
            ),
            (
                "/api/v1/mobile/nodes/${node['nodeId']}/verify",
                "nodes/([0-9a-f]{32})/verify",
            ),
            (
                "/api/v1/mobile/users/$userId/$endpoint",
                "users/(\\d+)/(enable|disable|share|rotate-secret|reset-traffic)",
            ),
            ("/api/v1/mobile/users/${user['id']}", "users/(\\d+)"),
        )
        for app_marker, server_marker in routes:
            with self.subTest(route=app_marker):
                self.assertIn(app_marker, APP_SOURCES)
                self.assertIn(server_marker, SERVER_SOURCE)

    def test_dynamic_app_actions_are_all_in_the_server_allowlists(self):
        for action in (
            "enable",
            "disable",
            "share",
            "rotate-secret",
            "reset-traffic",
        ):
            self.assertIn(action, APP_SOURCES)
            self.assertIn(action, SERVER_SOURCE)
        for action in ("start", "restart", "stop"):
            self.assertIn("'{}'".format(action), APP_SOURCES)
            self.assertIn(action, SERVER_SOURCE)

    def test_external_update_check_uses_only_the_public_github_https_api(self):
        self.assertIn("https://api.github.com/repos/", APP_SOURCES)
        self.assertNotIn("http://api.github.com/", APP_SOURCES)


if __name__ == "__main__":
    unittest.main()
