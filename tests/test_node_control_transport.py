import http.client
import json
import ssl
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import node_agent


class ControlTransportCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        cls.cert = root / "server.crt"
        cls.key = root / "server.key"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(cls.key), "-out", str(cls.cert), "-days", "1",
             "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self.cert), str(self.key))
        self.requests = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                requests.append((self.path, body, self.connection.session_reused))
                if self.path == "/broken":
                    return
                status = 302 if self.path == "/redirect" else 200
                payload = b"x" * 128 if self.path == "/large" else b'{"ok":true}'
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Location", "/ok")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                pass

        class Server(HTTPServer):
            def get_request(self):
                sock, address = super().get_request()
                try:
                    return context.wrap_socket(sock, server_side=True), address
                except BaseException:
                    sock.close()
                    raise

        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.now = 0
        self.transport = node_agent.NodeControlTransport(
            context_factory=lambda: ssl.create_default_context(cafile=str(self.cert)),
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, path="/ok", host="localhost"):
        return urllib.request.Request(
            "https://{}:{}{}".format(host, self.server.server_port, path),
            data=b'{"signed":"example"}',
            headers={"Content-Type": "application/json"}, method="POST",
        )

    def test_resumes_verified_tls_over_closing_http_and_periodically_revalidates(self):
        for _ in range(2):
            self.assertEqual((200, b'{"ok":true}'), self.transport.post(self.request(), 64, 2))
        self.assertEqual([False, True], [row[2] for row in self.requests])
        self.now = node_agent.CONTROL_TLS_SESSION_SECONDS + 1
        self.transport.post(self.request(), 64, 2)
        self.assertEqual([False, True, False], [row[2] for row in self.requests])

    def test_still_checks_certificate_authority_and_hostname(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            node_agent.NodeControlTransport().post(self.request(), 64, 2)
        self.transport.post(self.request(), 64, 2)
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.transport.post(self.request(host="127.0.0.1"), 64, 2)

    def test_broken_post_is_not_replayed_and_discards_the_session(self):
        self.transport.post(self.request(), 64, 2)
        with self.assertRaises(http.client.RemoteDisconnected):
            self.transport.post(self.request("/broken"), 64, 2)
        self.assertEqual(1, sum(row[0] == "/broken" for row in self.requests))
        self.transport.post(self.request(), 64, 2)
        self.assertFalse(self.requests[-1][2])

    def test_response_size_is_bounded_and_redirects_are_not_followed(self):
        with self.assertRaises(node_agent.ProtocolError):
            self.transport.post(self.request("/large"), 16, 2)
        status, _body = self.transport.post(self.request("/redirect"), 64, 2)
        self.assertEqual(302, status)
        self.assertEqual(["/large", "/redirect"], [row[0] for row in self.requests])


class IdleControlCase(unittest.TestCase):
    def test_idle_cycles_keep_short_freshness_and_resume_fast_after_activity_or_failure(self):
        stopped = threading.Event()
        delays = []

        class Cycle:
            idle = False

            def run_once(self):
                index = len(delays)
                self.idle = index in (0, 3)
                if index == 2:
                    raise node_agent.ProtocolError("temporary outage")

        def sleeper(delay):
            delays.append(delay)
            if len(delays) == 4:
                stopped.set()

        node_agent.run_control_loop(
            Cycle(), stopped, sleeper=sleeper, jitter_source=lambda: 1,
        )
        self.assertEqual(4, len(delays))
        for expected, actual in zip([5, 2.4, 2.4, 5], delays):
            self.assertAlmostEqual(expected, actual)

    def test_only_acknowledged_empty_cycles_use_idle_polling(self):
        now = 2_000_000_000

        class Stats:
            users = {}
            traffic = {}

            def collect_and_clear(self):
                return self.traffic

            def online(self):
                return self.users

        class Protocol:
            commands = []
            fail = False

            def send_control_cycle(self, batches, snapshot):
                if self.fail:
                    raise node_agent.ProtocolError("unacknowledged")
                return {
                    "acceptedAt": now,
                    "traffic": [{"batchId": b["batchId"], "committed": True} for b in batches],
                    "online": {"sequence": snapshot["sequence"]},
                    "commands": self.commands,
                }

            def poll_commands(self):
                raise node_agent.ProtocolError("unreachable")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stats = Stats()
            protocol = Protocol()
            spool = node_agent.DurableTrafficSpool(root / "spool")
            state = node_agent.ProtocolState(root / "state.json")
            cycle = node_agent.NodeControlCycle(protocol, stats, spool, state, clock=lambda: now)
            cycle.run_once()
            self.assertTrue(cycle.idle)
            self.assertEqual(now, state.traffic_acked_at())
            self.assertEqual([], spool.pending())
            stats.users = {"alice": 1}
            cycle.run_once()
            self.assertFalse(cycle.idle)
            stats.users = {}
            stats.traffic = {"alice": {"tx": 1, "rx": 0}}
            cycle.run_once()
            self.assertFalse(cycle.idle)
            stats.traffic = {}
            protocol.commands = [{"commandId": "a" * 32}]
            cycle._run_combined(False)
            self.assertFalse(cycle.idle)
            protocol.commands = []
            cycle.run_once()
            self.assertTrue(cycle.idle)
            protocol.fail = True
            with self.assertRaises(node_agent.ProtocolError):
                cycle.run_once()
            self.assertFalse(cycle.idle)
            self.assertTrue(spool.pending())

    def test_default_transport_preserves_old_panel_protocol_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "registration.json"
            state.write_text(json.dumps({
                "nodeId": "a" * 32, "panelUrl": "https://panel.example.com:19998",
                "registeredAt": 1, "status": "PENDING_VERIFICATION",
            }))
            state.chmod(0o600)
            client = node_agent.NodeProtocolClient(state, root / "unused.key", signer=lambda *_: b"s" * 64)
            with mock.patch.object(client._control_transport, "post", return_value=(404, b"{}")):
                with self.assertRaises(node_agent.ProtocolNotSupported):
                    client.send_control_cycle([], None)


if __name__ == "__main__":
    unittest.main()
