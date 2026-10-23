"""Exercise WebDAV on a private HTTPS server, including lost acknowledgements."""

import base64
import datetime
import hashlib
import html
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import unittest
import urllib.parse
from unittest import mock

from offsite_backup import HttpsWebDavClient, OffsiteBackupConfig, WebDavBackupStore


class WebDavHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        state = self.server
        state.calls.append((self.command, self.path))
        if self.headers.get("Authorization") != state.authorization:
            self.send_error(401)
            return
        if not self.path.startswith(state.prefix):
            self.send_error(404)
            return
        name = urllib.parse.unquote(self.path[len(state.prefix):])
        status, body = 200, b""
        if self.command == "PUT":
            data = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("X-Checksum-SHA256") != hashlib.sha256(data).hexdigest():
                self.send_error(400)
                return
            if state.fault == "redirect":
                self.send_response(302)
                self.send_header("Location", "/must-not-follow")
                self.end_headers()
                return
            state.objects[name] = data
            status = 201
        elif self.command == "MOVE":
            target = urllib.parse.urlsplit(self.headers["Destination"])
            if (target.netloc != self.headers["Host"] or not target.path.startswith(state.prefix)
                    or self.headers.get("Overwrite") != "F"):
                self.send_error(400)
                return
            destination = urllib.parse.unquote(target.path[len(state.prefix):])
            if destination in state.objects:
                self.send_error(412)
                return
            state.objects[destination] = state.objects.pop(name)
            status = 201
        elif self.command in ("GET", "HEAD"):
            if name not in state.objects:
                self.send_error(404)
                return
            body = state.objects[name]
            if self.command == "GET" and (
                state.fault == "corrupt-temporary" and name.startswith(".upload-")
                or state.fault == "corrupt-published" and name.startswith("hysteria2-")
            ):
                body = bytes([body[0] ^ 1]) + body[1:]
        elif self.command == "PROPFIND":
            if self.headers.get("Depth") != "1":
                self.send_error(400)
                return
            body = ('<d:multistatus xmlns:d="DAV:">' + ''.join(
                '<d:response><d:href>' + html.escape(state.prefix + urllib.parse.quote(key))
                + '</d:href></d:response>' for key in state.objects
            ) + '</d:multistatus>').encode()
            status = 207
        elif self.command == "DELETE":
            if name not in state.objects:
                self.send_error(404)
                return
            del state.objects[name]
            status = 204
        if state.fault == "reset-after-" + self.command.lower():
            # Complete the write, then lose its ACK at the real socket boundary.
            self.close_connection = True
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            self.connection.close()
            return
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_PUT = do_MOVE = do_GET = do_HEAD = do_PROPFIND = do_DELETE = handle_request


@unittest.skipUnless(shutil.which("openssl"), "openssl is required for the isolated TLS fixture")
class WebDavHttpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="hy2-webdav-tls-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        cls.certificate, key = cls.root / "ca.crt", cls.root / "ca.key"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout", str(key), "-out", str(cls.certificate),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        key.chmod(0o600)
        cls.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.context.load_cert_chain(cls.certificate, key)

    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), WebDavHandler)
        self.server.socket = self.context.wrap_socket(self.server.socket, server_side=True)
        self.server.objects, self.server.calls, self.server.fault = {}, [], None
        self.server.authorization = "Basic " + base64.b64encode(b"fixture:fixture-only").decode()
        self.server.prefix = "/%E4%B8%AD%E6%96%87%20%E7%9B%AE%E5%BD%95/escaped%20path/"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        # Trust only this disposable CA via OpenSSL's normal trust-file mechanism.
        trust = mock.patch.dict(os.environ, {"SSL_CERT_FILE": str(self.certificate)})
        trust.start()
        self.addCleanup(trust.stop)
        self.config = OffsiteBackupConfig(
            "https://127.0.0.1:{}/中文 目录/escaped%20path/".format(self.server.server_port),
            "fixture", "fixture-only",
        )
        self.store = WebDavBackupStore(HttpsWebDavClient(self.config, timeout=5))
        self.archive = self.root / "fixture.zip"
        self.archive.write_bytes(b"isolated-backup-content" * 4096)
        self.archive.chmod(0o600)
        self.old = "hysteria2-panel-offsite-20000101T000000Z-aaaaaaaa.zip"
        self.server.objects.update({self.old: b"old-backup", "unrelated.zip": b"keep"})
        self.now = datetime.datetime(2033, 5, 18, tzinfo=datetime.timezone.utc)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_https_upload_readbacks_paths_and_retention(self):
        result = self.store.upload(self.archive, now=self.now)
        self.assertEqual(self.archive.read_bytes(), self.server.objects[result["name"]])
        self.assertEqual([self.old], result["deleted"])
        self.assertIn("unrelated.zip", self.server.objects)
        methods = [method for method, _path in self.server.calls]
        self.assertEqual(["PUT", "HEAD", "GET", "MOVE", "HEAD", "GET", "PROPFIND", "DELETE"], methods)

    def test_corrupt_readback_never_prunes_existing_backups(self):
        for fault in ("corrupt-temporary", "corrupt-published"):
            with self.subTest(fault=fault):
                self.server.fault = fault
                self.server.calls.clear()
                with self.assertRaisesRegex(RuntimeError, "content does not match"):
                    self.store.upload(self.archive, now=self.now)
                self.assertIn(self.old, self.server.objects)
                self.assertFalse(any(method == "PROPFIND" for method, _ in self.server.calls))

    def test_lost_put_or_move_ack_preserves_evidence_and_recovers(self):
        for offset, operation in enumerate(("put", "move")):
            with self.subTest(operation=operation):
                self.server.objects = {self.old: b"old-backup"}
                self.server.fault = "reset-after-" + operation
                self.server.calls.clear()
                with self.assertRaises((OSError, http.client.HTTPException)):
                    self.store.upload(self.archive, now=self.now)
                self.assertIn(self.old, self.server.objects)
                self.assertFalse(any(method == "PROPFIND" for method, _ in self.server.calls))
                if operation == "move":
                    published = [key for key in self.server.objects if key != self.old]
                    self.assertEqual(1, len(published))
                    self.assertEqual(self.archive.read_bytes(), self.server.objects[published[0]])
                self.server.fault = None
                result = self.store.upload(self.archive, now=self.now + datetime.timedelta(seconds=offset + 1))
                self.assertEqual(self.archive.read_bytes(), self.server.objects[result["name"]])

    def test_redirect_does_not_forward_credentials_or_prune(self):
        self.server.fault = "redirect"
        with self.assertRaisesRegex(RuntimeError, "status 302"):
            self.store.upload(self.archive, now=self.now)
        self.assertIn(self.old, self.server.objects)
        self.assertFalse(any(path == "/must-not-follow" for _method, path in self.server.calls))

    def test_untrusted_certificate_and_wrong_password_are_rejected(self):
        with mock.patch.dict(os.environ, {"SSL_CERT_FILE": str(self.root / "absent-ca")}):
            with self.assertRaises(ssl.SSLCertVerificationError):
                self.store.client.list_names()
        self.assertEqual([], self.server.calls)
        bad = HttpsWebDavClient(OffsiteBackupConfig(self.config.endpoint, "fixture", "wrong"))
        with self.assertRaisesRegex(RuntimeError, "status 401"):
            bad.list_names()


if __name__ == "__main__":
    unittest.main()
