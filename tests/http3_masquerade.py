#!/usr/bin/env python3
"""Exercise an installed node with a real HTTP/3 client (test-only aioquic).

Trust the supplied, existing node certificate. No users or server settings are
created or changed. Run this after installation and after upgrade/rollback.
"""

import argparse
import asyncio
import socket

from aioquic.asyncio import QuicConnectionProtocol, connect
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ConnectionTerminated


class Client(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http = H3Connection(self._quic)
        self.requests = {}

    async def request(self, authority, path, method="GET", headers=()):
        stream = self._quic.get_next_available_stream_id()
        future = asyncio.get_running_loop().create_future()
        self.requests[stream] = (future, [], bytearray())
        self.http.send_headers(stream, [
            (b":method", method.encode()), (b":scheme", b"https"),
            (b":authority", authority.encode()), (b":path", path.encode()),
            *headers,
        ], end_stream=True)
        self.transmit()
        try:
            return await asyncio.wait_for(future, 10)
        finally:
            self.requests.pop(stream, None)

    def quic_event_received(self, event):
        if isinstance(event, ConnectionTerminated):
            for future, _, _ in self.requests.values():
                if not future.done():
                    future.set_exception(ConnectionError("HTTP/3 connection ended"))
            return
        for received in self.http.handle_event(event):
            if not isinstance(received, (HeadersReceived, DataReceived)):
                continue
            request = self.requests.get(received.stream_id)
            if request is None:
                continue
            future, headers, body = request
            if future.done():
                continue
            if isinstance(received, HeadersReceived):
                headers.extend(received.headers)
            else:
                body.extend(received.data)
            if len(body) > 65536:
                future.set_exception(ValueError("HTTP/3 response exceeds test bound"))
            elif received.stream_ended:
                future.set_result((dict(headers), bytes(body)))


async def check(args, port):
    config = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN,
                               server_name=args.server_name, idle_timeout=10)
    config.load_verify_locations(cafile=args.certificate)
    async with connect(args.host, port, configuration=config, create_protocol=Client) as client:
        headers, body = await client.request(args.server_name, "/")
        assert headers[b":status"] == b"200", headers
        assert b"text/html" in headers[b"content-type"], headers
        assert b"<title>Field Notes</title>" in body
        for marker in (b"Hysteria", b"hy2panel", b"PRIVATE KEY", b"pinSHA256"):
            assert marker not in body, marker
        headers, body = await client.request(args.server_name, "/", "HEAD")
        assert headers[b":status"] == b"200" and not body
        for path in ("/missing-page", "/server.key", "/panel.env", "/bootstrap.json"):
            headers, _ = await client.request(args.server_name, path)
            assert headers[b":status"] == b"404", (path, headers)
        for path in ("/../server.key", "/%2e%2e/server.key"):
            headers, body = await client.request(args.server_name, path)
            assert headers[b":status"] != b"200", (path, headers)
            assert b"PRIVATE KEY" not in body
        headers, _ = await client.request("hysteria", "/auth", "POST", (
            (b"hysteria-auth", b"invalid-camouflage-test-credential"),
            (b"hysteria-cc-rx", b"0"),
        ))
        assert headers[b":status"] == b"404", headers
    # The legacy TCP-only latency test must still complete its handshake.
    with socket.create_connection((args.host, port), timeout=5):
        pass
    print("HTTP/3 website, missing paths, key isolation, rejected auth and TCP {}: PASS".format(port))


async def run(args):
    for port in args.ports:
        await asyncio.wait_for(check(args, port), 45)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--ports", type=int, nargs="+", default=[19999, 443])
    asyncio.run(run(parser.parse_args()))
