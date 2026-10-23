#!/usr/bin/env python3
"""Two temporary HTTPS panels for the independent Android test package only."""

import argparse
import base64
import ipaddress
import json
from pathlib import Path
import secrets
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
    parser.add_argument("--listen-host", default="127.0.0.1",
                        help="An explicit loopback or private LAN IPv4 address, never all interfaces")
    parser.add_argument("--base-port", type=int, default=31888)
    args = parser.parse_args()
    address = ipaddress.IPv4Address(args.listen_host)
    private_lan = any(address in ipaddress.ip_network(network)
                      for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    if not (address.is_loopback or private_lan) or not 1024 <= args.base_port < 65535:
        parser.error("Use a specific loopback/private LAN address and two unprivileged ports")
    # A LAN fixture must not expose the unit fixture's well-known password.
    password = "admin-password" if address.is_loopback else secrets.token_urlsafe(32)
    fixtures = []
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    with tempfile.TemporaryDirectory(prefix="hy2-mobile-tls-") as temporary:
        root = Path(temporary)
        certificate, key = root / "fixture.crt", root / "fixture.key"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
            "-subj", "/CN=localhost", "-addext",
            "subjectAltName=DNS:localhost,IP:{}".format(address),
            "-keyout", str(key), "-out", str(certificate),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        key.chmod(0o600)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        try:
            for index, port in enumerate((args.base_port, args.base_port + 1)):
                fixture = PanelHttpTests("runTest")
                fixture.setUp()
                fixtures.append(fixture)
                fixture.server.shutdown()
                fixture.server.server_close()
                fixture.thread.join(timeout=5)
                fixture.db.upsert_admin("Elegy", password)
                fixture.application.node_name = "acceptance-panel-{}".format(index + 1)
                fixture.db.create_proxy_user("acceptance-user-{}".format(index + 1))
                fixture.server = make_panel_server((str(address), port), fixture.application)
                fixture.server.socket = context.wrap_socket(fixture.server.socket, server_side=True)
                fixture.thread = threading.Thread(target=fixture.server.serve_forever, daemon=True)
                fixture.thread.start()
            args.defines.write_text(json.dumps({
                "ACCEPTANCE_CA": base64.b64encode(certificate.read_bytes()).decode("ascii"),
                "ACCEPTANCE_PORT": args.base_port, "ACCEPTANCE_PORT_2": args.base_port + 1,
                "ACCEPTANCE_HOST": str(address), "ACCEPTANCE_USERNAME": "Elegy",
                "ACCEPTANCE_PASSWORD": password,
            }))
            args.defines.chmod(0o600)
            print("Two isolated HTTPS fixtures ready; private connection details saved", flush=True)
            stop.wait()
        finally:
            for fixture in reversed(fixtures):
                fixture.tearDown()


if __name__ == "__main__":
    main()
