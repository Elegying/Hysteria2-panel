"""Real TLS checks for the auth transport's cancellable total deadline."""
import contextlib
import json
import os
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import node_agent
from tests.test_panel import create_test_certificate


DECISION = {'ok': True, 'id': 'alice', 'decisionId': 'e' * 32, 'expiresAt': 2000000043}


class AuthResponseHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.server.requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        body = json.dumps(DECISION).encode()
        mode = self.server.mode
        try:
            if mode == 'slow_success':
                time.sleep(5.3)
            if mode == 'headers':
                for part in (b'HTTP/1.1 200 OK\r\n', b'Content-Type: application/json\r\n',
                             ('Content-Length: {}\r\n'.format(len(body))).encode(), b'\r\n'):
                    self.wfile.write(part)
                    self.wfile.flush()
                    time.sleep(0.25)
                self.wfile.write(body)
                return
            if mode == 'redirect':
                self.send_response(302)
                self.send_header('Location', self.server.url + '/redirected')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if mode == 'oversize':
                body = b'x' * (node_agent.NodeProtocolClient.PATHS['auth'][1] + 1)
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if mode == 'body':
                for index in range(6):
                    time.sleep(0.2)
                    self.wfile.write(body[index * len(body) // 6:(index + 1) * len(body) // 6])
                    self.wfile.flush()
            else:
                self.wfile.write(body)
        except OSError:
            pass  # A deadline must close the peer while this fixture is writing.


class AuthTransportDeadlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.certificate, cls.key = create_test_certificate(Path(cls.temporary.name), 'localhost')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @contextlib.contextmanager
    def endpoint(self, mode='normal'):
        server = ThreadingHTTPServer(('127.0.0.1', 0), AuthResponseHandler)
        server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self.certificate), str(self.key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.mode = mode
        server.url = 'https://localhost:{}'.format(server.server_port)
        server.requests = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    @contextlib.contextmanager
    def client(self, url, budget=8):
        state = {'nodeId': 'd' * 32, 'panelUrl': url}
        with mock.patch.object(node_agent, '_registration_state', return_value=state), \
                mock.patch.object(node_agent, 'NODE_PROTOCOL_REQUEST_TIMEOUT_SECONDS', budget), \
                mock.patch.dict(os.environ, {'SSL_CERT_FILE': str(self.certificate)}):
            yield node_agent.NodeProtocolClient('unused', 'unused',
                                                signer=lambda *_args: b's' * 64,
                                                clock=lambda: 2000000000)

    @staticmethod
    def authorize(client):
        return client.authorize({'entrypoint': 'main', 'auth': 'fixture-secret', 'tx': 0})

    @contextlib.contextmanager
    def capture_children(self):
        processes = []
        real_popen = subprocess.Popen

        def popen(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process

        with mock.patch.object(node_agent.subprocess, 'Popen', side_effect=popen):
            yield processes

    def assert_reaped(self, processes):
        self.assertEqual(1, len(processes))
        self.assertIsNotNone(processes[0].poll())

    def test_fragmented_headers_and_body_cannot_extend_total_deadline(self):
        for mode in ('headers', 'body'):
            with self.subTest(mode=mode), self.endpoint(mode) as server, \
                    self.client(server.url, budget=0.6) as client, \
                    self.capture_children() as processes:
                started = time.monotonic()
                with self.assertRaises(node_agent.ProtocolError):
                    self.authorize(client)
                self.assertLess(time.monotonic() - started, 0.95)
                self.assert_reaped(processes)
                self.assertEqual(1, len(server.requests))

    def test_blocked_dns_and_tls_handshake_children_are_killed_and_reaped(self):
        # The resolver call is deliberately stuck inside the isolated child,
        # proving the parent does not retain a blocked resolver thread.
        blocked_dns = ('import socket, time\n'
                       'socket.getaddrinfo = lambda *a, **k: time.sleep(60)\n')
        with self.client('https://localhost:1', budget=0.3) as client, \
                self.capture_children() as processes, \
                mock.patch.object(node_agent, '_AUTH_TRANSPORT_WORKER',
                                  blocked_dns + node_agent._AUTH_TRANSPORT_WORKER):
            with self.assertRaises(node_agent.ProtocolError):
                self.authorize(client)
            self.assert_reaped(processes)
            self.assertLess(processes[0].returncode, 0)

        # A TCP listener that never completes TLS exercises a real connection.
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        try:
            with self.client('https://localhost:{}'.format(listener.getsockname()[1]),
                             budget=0.3) as client, self.capture_children() as processes:
                started = time.monotonic()
                with self.assertRaises(node_agent.ProtocolError):
                    self.authorize(client)
                self.assertLess(time.monotonic() - started, 0.7)
                self.assert_reaped(processes)
        finally:
            listener.close()

    def test_default_proxy_returns_failure_and_releases_worker_before_outer_timeout(self):
        with self.endpoint('body') as server, self.client(server.url, budget=0.6) as client, \
                self.capture_children() as processes:
            proxy = node_agent.make_node_auth_proxy_server(
                ('127.0.0.1', 0), client, max_workers=1, request_timeout=0.95,
            )
            thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    'http://127.0.0.1:{}/auth/main'.format(proxy.server_port),
                    data=json.dumps({'addr': '127.0.0.1:1', 'auth': 'fixture-secret', 'tx': 0}).encode(),
                    headers={'Content-Type': 'application/json'},
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    self.assertEqual({'ok': False, 'id': ''}, json.load(response))
                self.assertTrue(proxy._worker_slots.acquire(timeout=0.1))
                proxy._worker_slots.release()
                self.assert_reaped(processes)
            finally:
                proxy.shutdown()
                proxy.server_close()
                thread.join(2)

    def test_five_second_success_retains_tls_signature_and_response_contract(self):
        with self.endpoint('slow_success') as server, self.client(server.url) as client:
            started = time.monotonic()
            self.assertEqual(DECISION, self.authorize(client))
            self.assertLess(time.monotonic() - started, 8)
            self.assertEqual('fixture-secret', server.requests[0]['auth'])
            self.assertIn('signature', server.requests[0])

    def test_wrong_tls_identity_redirect_and_oversized_response_are_rejected(self):
        for mode in ('normal', 'redirect', 'oversize'):
            with self.subTest(mode=mode), self.endpoint(mode) as server:
                url = server.url.replace('localhost', '127.0.0.1') if mode == 'normal' else server.url
                with self.client(url) as client:
                    with self.assertRaises(node_agent.ProtocolError):
                        self.authorize(client)
                self.assertEqual(0 if mode == 'normal' else 1, len(server.requests))

    def test_transport_capacity_is_bounded_without_starting_extra_children(self):
        held = []
        try:
            while node_agent._AUTH_TRANSPORT_SLOTS.acquire(blocking=False):
                held.append(True)
            self.assertEqual(4, len(held))
            with self.client('https://localhost:1') as client, \
                    mock.patch.object(node_agent.subprocess, 'Popen') as popen, \
                    mock.patch.object(client, 'signer') as signer:
                with self.assertRaisesRegex(node_agent.ProtocolError, 'capacity'):
                    self.authorize(client)
                popen.assert_not_called()
                signer.assert_not_called()
        finally:
            for _ in held:
                node_agent._AUTH_TRANSPORT_SLOTS.release()

    def test_four_blocked_transports_reject_overload_then_recover_capacity(self):
        blocked_dns = ('import socket, time\n'
                       'socket.getaddrinfo = lambda *a, **k: time.sleep(60)\n')
        failures = []
        start = threading.Event()
        with self.endpoint() as server, self.client(server.url, budget=1.2) as client, \
                self.capture_children() as processes:
            def authorize():
                start.wait(2)
                try:
                    self.authorize(client)
                except node_agent.ProtocolError as exc:
                    failures.append(exc)

            workers = [threading.Thread(target=authorize) for _ in range(4)]
            with mock.patch.object(node_agent, '_AUTH_TRANSPORT_WORKER',
                                   blocked_dns + node_agent._AUTH_TRANSPORT_WORKER):
                for worker in workers:
                    worker.start()
                start.set()
                try:
                    deadline = time.monotonic() + 0.8
                    while len(processes) < 4 and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertEqual(4, len(processes))
                    with self.assertRaisesRegex(node_agent.ProtocolError, 'capacity'):
                        self.authorize(client)
                    self.assertEqual(4, len(processes))
                finally:
                    for worker in workers:
                        worker.join(3)
                self.assertTrue(all(not worker.is_alive() for worker in workers))
                self.assertEqual(4, len(failures))
                self.assertTrue(all(process.poll() is not None for process in processes))
            self.assertEqual(DECISION, self.authorize(client))
            self.assertEqual(5, len(processes))
            self.assertTrue(all('fixture-secret' not in ' '.join(process.args)
                                for process in processes))


if __name__ == '__main__':
    unittest.main()
