"""Exercise configured WebDAV paths through real HTTP serialization and TLS."""

import datetime
import html
import json
import os
import ssl
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from offsite_backup import HttpsWebDavClient, OffsiteBackupConfig, WebDavBackupStore
from test_panel import create_test_certificate


class WebDavHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _record(self):
        self.server.calls.append((self.command, self.path, self.headers.get("Destination")))
        return self.path.startswith(self.server.directory)

    def _reply(self, status, body=b"", size=None):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body) if size is None else size))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_PUT(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if not self._record():
            return self._reply(404)
        self.server.objects[self.path] = body
        self._reply(201)

    def do_HEAD(self):
        if not self._record() or self.path not in self.server.objects:
            return self._reply(404)
        self._reply(200, size=len(self.server.objects[self.path]))

    def do_GET(self):
        if not self._record() or self.path not in self.server.objects:
            return self._reply(404)
        self._reply(200, self.server.objects[self.path])

    def do_MOVE(self):
        destination = urllib.parse.urlsplit(self.headers["Destination"])
        if (not self._record() or self.path not in self.server.objects
                or destination.netloc != "localhost:{}".format(self.server.server_port)
                or not destination.path.startswith(self.server.directory)):
            return self._reply(404)
        if self.headers.get("Overwrite") != "F" or destination.path in self.server.objects:
            return self._reply(412)
        self.server.objects[destination.path] = self.server.objects.pop(self.path)
        self._reply(201)

    def do_PROPFIND(self):
        if not self._record() or self.path != self.server.directory:
            return self._reply(404)
        paths = [self.server.directory] + sorted(self.server.objects)
        body = '<d:multistatus xmlns:d="DAV:">' + "".join(
            "<d:response><d:href>{}</d:href></d:response>".format(html.escape(path))
            for path in paths
        ) + "</d:multistatus>"
        self._reply(207, body.encode("utf-8"))

    def do_DELETE(self):
        if not self._record() or self.path not in self.server.objects:
            return self._reply(404)
        del self.server.objects[self.path]
        self._reply(204)


class WebDavPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.certificate, cls.key = create_test_certificate(cls.root, "localhost")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def _config(self, endpoint):
        path = self.root / "offsite.json"
        path.write_text(json.dumps({
            "endpoint": endpoint, "username": "fixture-user", "password": "fixture-password",
        }), encoding="utf-8")
        path.chmod(0o600)
        return OffsiteBackupConfig.load(path, expected_uid=os.geteuid())

    def _upload(self, directory, encoded_directory):
        server = ThreadingHTTPServer(("127.0.0.1", 0), WebDavHandler)
        server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(self.certificate), str(self.key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.directory = encoded_directory
        server.calls = []
        old_name = "hysteria2-panel-offsite-20300101T000000Z-aaaaaaaa.zip"
        server.objects = {encoded_directory + old_name: b"previous-backup"}
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        archive = self.root / "backup.zip"
        archive.write_bytes(b"verified-backup")
        archive.chmod(0o600)
        try:
            client = HttpsWebDavClient(self._config(
                "https://localhost:{}{}".format(server.server_port, directory)
            ))
            # Trust only this fixture's certificate; hostname verification stays enabled.
            with mock.patch.dict(os.environ, {"SSL_CERT_FILE": str(self.certificate)}):
                result = WebDavBackupStore(client).upload(
                    archive, now=datetime.datetime(2033, 5, 18, tzinfo=datetime.timezone.utc)
                )
            self.assertEqual(["PUT", "HEAD", "GET", "MOVE", "HEAD", "GET", "PROPFIND", "DELETE"],
                             [call[0] for call in server.calls])
            self.assertEqual({encoded_directory + result["name"]: b"verified-backup"},
                             server.objects)
            self.assertEqual([old_name], result["deleted"])
            self.assertTrue(all(path.startswith(encoded_directory) for _, path, _ in server.calls))
            self.assertEqual("https://localhost:{}{}{}".format(
                server.server_port, encoded_directory, result["name"]
            ), server.calls[3][2])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)

    def test_unicode_directory_upload_readback_move_and_retention(self):
        self._upload("/备份/", "/%E5%A4%87%E4%BB%BD/")

    def test_space_directory_upload_readback_move_and_retention(self):
        self._upload("/backup files/", "/backup%20files/")

    def test_escaped_directory_keeps_escaped_slashes_and_percent_signs(self):
        self._upload("/备份/%2F%25%20/", "/%E5%A4%87%E4%BB%BD/%2F%25%20/")

    def test_destination_preserves_ipv6_and_encodes_international_hostname(self):
        for endpoint, expected in (
            ("https://备份.example.test:8443/存档/",
             "https://xn--doqp8v.example.test:8443/%E5%AD%98%E6%A1%A3/backup.zip"),
            ("https://[::1]:8443/存档/", "https://[::1]:8443/%E5%AD%98%E6%A1%A3/backup.zip"),
        ):
            with self.subTest(endpoint=endpoint):
                client = HttpsWebDavClient(self._config(endpoint))
                self.assertEqual(expected, client._remote_url("backup.zip"))

    def test_invalid_endpoint_is_rejected_during_configuration(self):
        for endpoint in (
            "https://backup.example.test:invalid/files/",
            "https://backup.example.test:65536/files/",
            "https://backup.example.test:0/files/",
            "https://backup.example.test/secret\nfiles/",
            "https://backup.example.test/secret\tfiles/",
            "https://backup.example.test/secret\x00files/",
            "https://backup.example.test/\ud800/",
        ):
            with self.subTest(endpoint=ascii(endpoint)), self.assertRaises(ValueError):
                self._config(endpoint)
