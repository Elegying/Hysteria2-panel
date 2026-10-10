"""Recheck entrypoint permission when an in-flight local admission commits."""

import concurrent.futures
import contextlib
import json
import threading
import unittest
from unittest import mock
import urllib.request

import hysteria2_panel as panel
from tests import test_panel


class LocalAuthBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_panel.PanelHttpTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.database = self.fixture.db
        self.user = self.database.create_proxy_user(
            "entry-permission", allow_udp_443=True, device_limit=10
        )
        self.web_headers, self.csrf = self.fixture.authenticated_headers()
        self.mobile_token = self.database.create_mobile_session(
            self.fixture.admin_id, "permission-device", "Audit"
        )["accessToken"]
        self.stats = test_panel.PolicyStatsClient()
        self.manager = panel.UsageManager(self.database, self.stats, auth_stats_ttl=60)
        self.fixture.application.usage_manager = self.manager
        self.fixture.application.stats_client = self.stats
        self.server = panel.make_internal_server(
            ("127.0.0.1", 0), self.database, self.manager
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.addCleanup(self._close_auth_server)
        self.base_url = "http://127.0.0.1:{}".format(self.server.server_address[1])

    def _close_auth_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def _authenticate(self, entrypoint):
        request = urllib.request.Request(
            self.base_url + entrypoint,
            data=json.dumps({"auth": self.user["token"]}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(200, response.status)
            return json.load(response)

    def _set_permission(self, interface, allowed):
        user = self.database.get_proxy_user(self.user["id"])
        if interface == "mobile":
            status, _payload = self.fixture.mobile_json_request(
                "PATCH", "/api/v1/mobile/users/{}".format(user["id"]),
                {"generation": user["generation"], "deviceLimit": 10,
                 "trafficLimitGb": 250, "allowUdp443": allowed},
                access_token=self.mobile_token,
            )
            self.assertEqual(200, status)
        else:
            form = {"csrf": self.csrf, "generation": str(user["generation"]),
                    "device_limit": "10", "traffic_limit_gb": "250", "inline": "1"}
            if allowed:
                form["allow_udp_443"] = "1"
            with self.fixture.request(
                "/users/{}/edit".format(user["id"]), form, headers=self.web_headers
            ) as response:
                self.assertEqual(200, response.status)
        current = self.database.get_proxy_user(user["id"])
        self.assertEqual(allowed, bool(current["allow_udp_443"]))

    def _lease_count(self):
        with self.database._connect() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM local_auth_leases WHERE user_name = ?",
                (self.user["name"],),
            ).fetchone()[0]

    def _revocation_during_admission(self, interface, cached):
        if cached:
            self.assertTrue(self._authenticate("/auth")["ok"])
        leases_before = self._lease_count()
        entered, release = threading.Event(), threading.Event()

        def wait_before(call):
            def paused(*args, **kwargs):
                entered.set()
                if not release.wait(4):
                    raise TimeoutError("admission fixture was not released")
                return call(*args, **kwargs)
            return paused

        with contextlib.ExitStack() as stack:
            if cached:
                stack.enter_context(mock.patch.object(
                    self.database, "authorize_local_participant",
                    side_effect=wait_before(self.database.authorize_local_participant),
                ))
                collect = stack.enter_context(mock.patch.object(
                    self.stats, "collect_and_clear", wraps=self.stats.collect_and_clear,
                ))
            else:
                stack.enter_context(mock.patch.object(
                    self.stats, "collect_and_clear",
                    side_effect=wait_before(self.stats.collect_and_clear),
                ))
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self._authenticate, "/auth/udp-443")
                try:
                    self.assertTrue(entered.wait(3), "auth did not reach the pause")
                    self._set_permission(interface, False)
                finally:
                    release.set()
                response = pending.result(timeout=5)
            if cached:
                collect.assert_not_called()

        self.assertEqual({"ok": False, "id": ""}, response)
        self.assertEqual(leases_before, self._lease_count())
        self.assertFalse(self._authenticate("/auth/udp-443")["ok"])
        self.assertTrue(self._authenticate("/auth")["ok"])
        self._set_permission(interface, True)
        self.assertTrue(self._authenticate("/auth/udp-443")["ok"])

    def test_web_revocation_during_stats_wait_rejects_inflight_udp_admission(self):
        self._revocation_during_admission("web", cached=False)

    def test_mobile_revocation_during_stats_wait_rejects_inflight_udp_admission(self):
        self._revocation_during_admission("mobile", cached=False)

    def test_web_revocation_is_rechecked_even_when_auth_stats_are_cached(self):
        self._revocation_during_admission("web", cached=True)

    def test_mobile_revocation_is_rechecked_even_when_auth_stats_are_cached(self):
        self._revocation_during_admission("mobile", cached=True)
