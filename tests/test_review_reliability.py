import base64
import io
import json
import threading
import time
import unittest
import urllib.request
import uuid
from pathlib import Path
from unittest import mock

import node_agent
from hy2panel.release import UpdateChecker, UpdateInstaller
from tests.test_distributed_control import DistributedControlCase


class AuthenticationDeadlineTests(unittest.TestCase):
    def test_slow_success_reaches_hysteria_before_its_ten_second_deadline(self):
        fixture = DistributedControlCase()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        user = fixture.db.create_proxy_user("slow-auth", device_limit=1)
        fixture.accept_empty_snapshots()

        class Central:
            def authorize(self, request):
                time.sleep(5.3)
                return fixture.service.authorize(
                    {
                        "nodeId": fixture.nodes[0],
                        "sentAt": fixture.now[0],
                        "nonce": base64.urlsafe_b64encode(
                            uuid.uuid4().bytes + uuid.uuid4().bytes
                        ).rstrip(b"=").decode("ascii"),
                        "signature": base64.b64encode(b"s" * 64).decode("ascii"),
                        "requestId": uuid.uuid4().hex,
                        **request,
                    },
                    remote_ip="203.0.113.1",
                )

        server = node_agent.make_node_auth_proxy_server(("127.0.0.1", 0), Central())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:{}/auth/main".format(server.server_port),
                data=json.dumps(
                    {"addr": "198.51.100.1:1234", "auth": user["token"], "tx": 0}
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                self.assertEqual({"ok": True, "id": "slow-auth"}, json.load(response))
            self.assertLess(server.request_timeout, 10)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_signing_time_is_part_of_the_central_auth_budget(self):
        class Response(io.BytesIO):
            status = 200

        opener = mock.Mock(side_effect=lambda *_args, **_kwargs: Response(
            json.dumps({"ok": False, "id": "", "decisionId": "e" * 32,
                        "expiresAt": 2_000_000_005}).encode()
        ))
        client = node_agent.NodeProtocolClient(
            "unused-registration", "unused-key", opener=opener,
            signer=lambda *_args: b"s" * 64, clock=lambda: 2_000_000_000,
        )
        registration = {"nodeId": "d" * 32, "panelUrl": "https://panel.example.test"}
        with mock.patch.object(node_agent, "_registration_state", return_value=registration):
            with mock.patch.object(node_agent.time, "monotonic", side_effect=[100, 105]):
                client.authorize({"entrypoint": "main", "auth": "invalid", "tx": 0})
            self.assertEqual(3, opener.call_args.kwargs["timeout"])
            opener.reset_mock()
            with mock.patch.object(node_agent.time, "monotonic", side_effect=[100, 108]):
                with self.assertRaises(node_agent.ProtocolError):
                    client.authorize({"entrypoint": "main", "auth": "invalid", "tx": 0})
            opener.assert_not_called()


class ReleaseSizeContractTests(unittest.TestCase):
    def test_valid_large_release_metadata_and_exact_size_boundary(self):
        prefix = json.dumps({"tag_name": "v0.40.0", "body": "x" * 20000}).encode()
        payload = prefix + b" " * (UpdateChecker.MAX_RESPONSE_BYTES - len(prefix))
        checker = UpdateChecker("0.39.16", opener=lambda *_a, **_k: io.BytesIO(payload))
        self.assertTrue(checker.check()["update_available"])
        checker.opener = lambda *_a, **_k: io.BytesIO(payload + b" ")
        with self.assertRaisesRegex(ValueError, "too large"):
            checker.check()

    def test_publication_gates_match_update_download_limits(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("distribution-synthetic.yml", "release-signature.yml"):
            source = (root / ".github/workflows" / name).read_text()
            for asset, maximum in (
                ("install.sh", UpdateInstaller.MAX_INSTALLER_BYTES),
                ("install.sh.sigstore.json", UpdateInstaller.MAX_BUNDLE_BYTES),
            ):
                self.assertIn(
                    'test "$(wc -c <"${asset_dir}/' + asset + '")" -le ' + str(maximum),
                    source,
                )
        source = (root / ".github/workflows/distribution-synthetic.yml").read_text()
        self.assertIn(
            'test "$(wc -c <"${response}")" -le ' + str(UpdateChecker.MAX_RESPONSE_BYTES),
            source,
        )


if __name__ == "__main__":
    unittest.main()
