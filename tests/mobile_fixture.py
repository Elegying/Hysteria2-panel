#!/usr/bin/env python3
"""Two temporary HTTPS panels for the independent Android test package only."""

import argparse
import base64
import json
from pathlib import Path
import signal
import ssl
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hysteria2_panel import make_panel_server  # noqa: E402
from tests.test_panel import PanelHttpTests  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--defines", type=Path, required=True)
    args = parser.parse_args()
    fixtures = []
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    with tempfile.TemporaryDirectory(prefix="hy2-mobile-tls-") as temporary:
        root = Path(temporary)
        certificate, key = root / "fixture.crt", root / "fixture.key"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout", str(key), "-out", str(certificate),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        key.chmod(0o600)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        try:
            for index, port in enumerate((31888, 31889)):
                fixture = PanelHttpTests("runTest")
                fixture.setUp()
                fixtures.append(fixture)
                fixture.server.shutdown()
                fixture.server.server_close()
                fixture.thread.join(timeout=5)
                fixture.application.node_name = "acceptance-panel-{}".format(index + 1)
                fixture.db.create_proxy_user("acceptance-user-{}".format(index + 1))
                fixture.server = make_panel_server(("127.0.0.1", port), fixture.application)
                fixture.server.socket = context.wrap_socket(fixture.server.socket, server_side=True)
                fixture.thread = threading.Thread(target=fixture.server.serve_forever, daemon=True)
                fixture.thread.start()
            args.defines.write_text(json.dumps({
                "ACCEPTANCE_CA": base64.b64encode(certificate.read_bytes()).decode("ascii"),
                "ACCEPTANCE_PORT": 31888, "ACCEPTANCE_PORT_2": 31889,
            }))
            args.defines.chmod(0o600)
            print("Two isolated HTTPS fixtures ready on loopback ports 31888/31889", flush=True)
            stop.wait()
        finally:
            for fixture in reversed(fixtures):
                fixture.tearDown()


if __name__ == "__main__":
    main()
