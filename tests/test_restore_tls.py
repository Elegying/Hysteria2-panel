import ssl
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from hysteria2_panel import _default_restore_health_probe
from test_panel import create_test_certificate


class RestoreTlsTests(unittest.TestCase):
    def test_loopback_connection_verifies_real_hostname_and_rejects_redirect(self):
        class Handler(BaseHTTPRequestHandler):
            redirect = False

            def do_GET(self):
                self.send_response(302 if self.redirect else 200)
                self.end_headers()
                self.wfile.write(b'{"status":"ready"}')

            def log_message(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as directory:
            cert, key = create_test_certificate(directory, 'panel.example.test')
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            settings = SimpleNamespace(
                panel_scheme='https', panel_port=server.server_port,
                panel_public_host='panel.example.test', panel_tls_cert=cert,
                auth_port=18100,
            )
            url = 'https://127.0.0.1:{}/readyz'.format(server.server_port)
            try:
                _default_restore_health_probe(url, settings)
                settings.panel_public_host = 'wrong.example.test'
                with self.assertRaises(ssl.SSLCertVerificationError):
                    _default_restore_health_probe(url, settings)
                settings.panel_public_host = 'panel.example.test'
                Handler.redirect = True
                with self.assertRaises(RuntimeError):
                    _default_restore_health_probe(url, settings)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
