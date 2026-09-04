import unittest
from pathlib import Path

from hy2panel.mobile_api import match_mobile_route


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCES = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "mobile" / "lib").rglob("*.dart"))
)
SERVER_SOURCE = "\n".join(
    (
        (ROOT / "hysteria2_panel.py").read_text(encoding="utf-8"),
        (ROOT / "hy2panel/mobile_api.py").read_text(encoding="utf-8"),
    )
)
SETTINGS_SOURCE = (ROOT / "mobile/lib/screens/settings_screen.dart").read_text(
    encoding="utf-8"
)


class MobileApiContractTests(unittest.TestCase):
    def test_every_app_panel_call_has_a_server_route(self):
        routes = (
            ("/api/v1/mobile/capabilities", "/api/v1/mobile/capabilities"),
            ("/api/v1/mobile/auth/login", "/api/v1/mobile/auth/login"),
            ("/api/v1/mobile/auth/refresh", "/api/v1/mobile/auth/refresh"),
            ("/api/v1/mobile/auth/logout", "/api/v1/mobile/auth/logout"),
            ("/api/v1/mobile/overview", "/api/v1/mobile/overview"),
            ("/api/v1/mobile/users", "/api/v1/mobile/users"),
            ("/api/v1/mobile/domain-usage", "/api/v1/mobile/domain-usage"),
            (
                "/api/v1/mobile/users/${widget.userId}/domain-usage",
                "users/(\\d+)/domain-usage",
            ),
            ("/api/v1/mobile/nodes", "/api/v1/mobile/nodes"),
            ("/api/v1/mobile/node-enrollments", "/api/v1/mobile/node-enrollments"),
            ("/api/v1/mobile/service/$action", "service/(start|restart|stop)"),
            ("/api/v1/mobile/system/reboot", "/api/v1/mobile/system/reboot"),
            (
                "/api/v1/mobile/nodes/local/${enabled ? 'enable' : 'disable'}",
                "nodes/local/(enable|disable)",
            ),
            (
                "/api/v1/mobile/nodes/${node['nodeId']}/$action",
                "nodes/([0-9a-f]{32})/(disconnect|delete)",
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
            "disconnect",
            "delete",
        ):
            self.assertIn(action, APP_SOURCES)
            self.assertIn(action, SERVER_SOURCE)
        for action in ("start", "restart", "stop"):
            self.assertIn("'{}'".format(action), APP_SOURCES)
            self.assertIn(action, SERVER_SOURCE)

    def test_external_update_check_uses_only_the_public_github_https_api(self):
        self.assertIn("https://api.github.com/repos/", APP_SOURCES)
        self.assertNotIn("http://api.github.com/", APP_SOURCES)

    def test_update_check_uses_installed_version_and_formal_releases_only(self):
        self.assertIn(
            "_packageInfo ?? await PackageInfo.fromPlatform()", SETTINGS_SOURCE
        )
        self.assertIn("release['draft'] == true", SETTINGS_SOURCE)
        self.assertIn("release['prerelease'] == true", SETTINGS_SOURCE)
        self.assertIn("final current = packageInfo.version;", SETTINGS_SOURCE)
        self.assertNotIn("?? '0.2.0'", SETTINGS_SOURCE)

    def test_mobile_route_matching_is_fixed_and_method_specific(self):
        node_id = "a" * 32
        cases = (
            ("GET", "/api/v1/mobile/overview", ("overview", ())),
            ("GET", "/api/v1/mobile/domain-usage", ("domain-usage", ())),
            (
                "GET",
                "/api/v1/mobile/users/42/domain-usage",
                ("user-domain-usage", ("42",)),
            ),
            ("POST", "/api/v1/mobile/service/restart", ("service-action", ("restart",))),
            (
                "POST",
                "/api/v1/mobile/nodes/{}/disconnect".format(node_id),
                ("node-pairing-action", (node_id, "disconnect")),
            ),
            (
                "POST",
                "/api/v1/mobile/nodes/{}/delete".format(node_id),
                ("node-pairing-action", (node_id, "delete")),
            ),
            (
                "POST",
                "/api/v1/mobile/users/42/reset-traffic",
                ("user-action", ("42", "reset-traffic")),
            ),
            ("PATCH", "/api/v1/mobile/users/42", ("update-user", ("42",))),
            ("DELETE", "/api/v1/mobile/users/42", ("delete-user", ("42",))),
        )
        for method, path, expected in cases:
            with self.subTest(method=method, path=path):
                self.assertEqual(expected, match_mobile_route(method, path))

        for method, path in (
            ("GET", "/api/v1/mobile/service/restart"),
            ("POST", "/api/v1/mobile/service/arbitrary"),
            ("POST", "/api/v1/mobile/nodes/../../disable"),
            ("DELETE", "/api/v1/mobile/users/not-a-number"),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual((None, ()), match_mobile_route(method, path))


if __name__ == "__main__":
    unittest.main()
