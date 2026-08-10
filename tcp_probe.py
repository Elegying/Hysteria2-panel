#!/usr/bin/env python3
import socket
import sys


def create_listener(port):
    if socket.has_dualstack_ipv6():
        try:
            return socket.create_server(
                ("::", port), family=socket.AF_INET6, dualstack_ipv6=True, backlog=128
            )
        except OSError:
            pass
    return socket.create_server(("0.0.0.0", port), backlog=128)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: tcp_probe.py PORT")
    try:
        port = int(sys.argv[1])
    except ValueError as error:
        raise SystemExit("PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535")

    with create_listener(port) as listener:
        while True:
            connection, _address = listener.accept()
            connection.close()


if __name__ == "__main__":
    main()
