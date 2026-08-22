import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from hy2panel.systemd import SystemdNotifier
from hysteria2_panel import _probe_local_health, run_supervised_services


class FakeSocket:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def sendto(self, payload, address):
        self.calls.append((payload, address))
        return len(payload)


class SystemdNotifierTests(unittest.TestCase):
    def test_local_watchdog_probe_requires_a_bounded_exact_health_response(self):
        class Handler(BaseHTTPRequestHandler):
            payload = b'{"status":"ok"}'

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(self.payload)))
                self.end_headers()
                self.wfile.write(self.payload)

            def log_message(self, *_args):
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertTrue(_probe_local_health(server, "http", timeout=1))
            Handler.payload = b"x" * 1025
            self.assertFalse(_probe_local_health(server, "http", timeout=1))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_local_watchdog_probe_uses_a_specific_configured_bind_address(self):
        calls = []

        class Response:
            status = 200

            def read(self, _maximum):
                return b'{"status":"ok"}'

        class Connection:
            def __init__(self, host, port, timeout):
                calls.append((host, port, timeout))

            def request(self, method, path, headers):
                calls.append((method, path, headers))

            def getresponse(self):
                return Response()

            def close(self):
                return None

        server = type(
            "SpecificBindServer",
            (),
            {"server_address": ("192.0.2.10", 19998)},
        )()
        with mock.patch(
            "hysteria2_panel.http.client.HTTPConnection", Connection
        ):
            self.assertTrue(_probe_local_health(server, "http", timeout=1))

        self.assertEqual(("192.0.2.10", 19998, 1), calls[0])

    def test_ready_watchdog_and_stopping_use_the_abstract_notify_socket(self):
        calls = []
        environment = {
            "NOTIFY_SOCKET": "@hysteria2-panel",
            "WATCHDOG_USEC": "10000000",
            "WATCHDOG_PID": str(os.getpid()),
        }
        notifier = SystemdNotifier(
            environment=environment,
            socket_factory=lambda *_args: FakeSocket(calls),
        )

        self.assertEqual(5.0, notifier.watchdog_interval)
        self.assertTrue(notifier.ready("panel ready"))
        self.assertTrue(notifier.watchdog())
        self.assertTrue(notifier.stopping("panel stopping"))
        self.assertEqual(
            [
                (b"READY=1\nSTATUS=panel ready", "\0hysteria2-panel"),
                (b"WATCHDOG=1", "\0hysteria2-panel"),
                (b"STOPPING=1\nSTATUS=panel stopping", "\0hysteria2-panel"),
            ],
            calls,
        )

    def test_watchdog_is_disabled_for_another_pid_or_invalid_interval(self):
        for environment in (
            {
                "NOTIFY_SOCKET": "/run/notify.sock",
                "WATCHDOG_USEC": "10000000",
                "WATCHDOG_PID": str(os.getpid() + 1),
            },
            {"NOTIFY_SOCKET": "/run/notify.sock", "WATCHDOG_USEC": "invalid"},
            {"NOTIFY_SOCKET": "/run/notify.sock", "WATCHDOG_USEC": "0"},
        ):
            with self.subTest(environment=environment):
                notifier = SystemdNotifier(environment=environment)
                self.assertIsNone(notifier.watchdog_interval)

    def test_missing_notify_socket_is_a_safe_noop(self):
        notifier = SystemdNotifier(environment={})

        self.assertFalse(notifier.ready())
        self.assertFalse(notifier.watchdog())
        self.assertFalse(notifier.stopping())

    def test_service_supervisor_announces_ready_and_stopping(self):
        class Server:
            application = None

            def __init__(self, exits=False):
                self.exits = exits
                self.stopped = threading.Event()

            def serve_forever(self):
                if not self.exits:
                    self.stopped.wait(5)

            def shutdown(self):
                self.stopped.set()

            def server_close(self):
                return None

        class Usage:
            def run_collector(self, stop_event):
                stop_event.wait(5)

            def collect_once(self):
                return None

        class Notifier:
            watchdog_interval = None

            def __init__(self):
                self.events = []

            def ready(self, status):
                self.events.append(("ready", status))
                return True

            def stopping(self, status):
                self.events.append(("stopping", status))
                return True

            def watchdog(self):
                self.events.append(("watchdog", None))
                return True

        notifier = Notifier()

        with self.assertRaisesRegex(RuntimeError, "panel-http worker exited"):
            run_supervised_services(
                Server(exits=True),
                Server(),
                Usage(),
                "http",
                notifier=notifier,
            )

        self.assertEqual(
            [("ready", "panel workers started"), ("stopping", "panel stopping")],
            notifier.events,
        )

    def test_watchdog_requires_local_probe_and_collector_progress(self):
        class Server:
            application = None

            def __init__(self, exits_after=None):
                self.exits_after = exits_after
                self.stopped = threading.Event()

            def serve_forever(self):
                if self.exits_after is None:
                    self.stopped.wait(2)
                else:
                    self.stopped.wait(self.exits_after)

            def shutdown(self):
                self.stopped.set()

            def server_close(self):
                return None

        class Notifier:
            watchdog_interval = 0.05

            def __init__(self):
                self.pings = 0

            def ready(self, _status):
                return True

            def stopping(self, _status):
                return True

            def watchdog(self):
                self.pings += 1
                return True

        class Usage:
            def __init__(self, reports_progress):
                self.reports_progress = reports_progress

            def run_collector(self, stop_event):
                while not stop_event.is_set():
                    if self.reports_progress:
                        self.collector_heartbeat()
                    stop_event.wait(0.005)

            def collect_once(self):
                return None

        for reports_progress, probe_result, should_ping in (
            (True, True, True),
            (False, True, False),
            (True, False, False),
        ):
            with self.subTest(
                reports_progress=reports_progress, probe_result=probe_result
            ):
                notifier = Notifier()
                with self.assertRaisesRegex(RuntimeError, "panel-http worker exited"):
                    run_supervised_services(
                        Server(exits_after=0.45),
                        Server(),
                        Usage(reports_progress),
                        "http",
                        notifier=notifier,
                        watchdog_probe=lambda: probe_result,
                    )
                self.assertEqual(should_ping, notifier.pings > 0)


if __name__ == "__main__":
    unittest.main()
