"""Minimal systemd readiness and watchdog notification support."""

import os
import socket


class SystemdNotifier:
    def __init__(self, environment=None, socket_factory=socket.socket):
        self._environment = os.environ if environment is None else environment
        self._socket_factory = socket_factory

    @property
    def watchdog_interval(self):
        configured_pid = self._environment.get("WATCHDOG_PID")
        if configured_pid:
            try:
                if int(configured_pid) != os.getpid():
                    return None
            except ValueError:
                return None
        try:
            microseconds = int(self._environment.get("WATCHDOG_USEC", "0"))
        except ValueError:
            return None
        if microseconds <= 0 or not self._environment.get("NOTIFY_SOCKET"):
            return None
        return microseconds / 2_000_000

    def _notify(self, fields):
        address = self._environment.get("NOTIFY_SOCKET")
        if not address:
            return False
        if address.startswith("@"):
            address = "\0" + address[1:]
        payload = "\n".join(fields).encode("utf-8")
        try:
            with self._socket_factory(socket.AF_UNIX, socket.SOCK_DGRAM) as notifier:
                notifier.sendto(payload, address)
        except OSError:
            return False
        return True

    @staticmethod
    def _status(value):
        return str(value).replace("\r", " ").replace("\n", " ")

    def ready(self, status="ready"):
        return self._notify(("READY=1", "STATUS={}".format(self._status(status))))

    def watchdog(self):
        if self.watchdog_interval is None:
            return False
        return self._notify(("WATCHDOG=1",))

    def stopping(self, status="stopping"):
        return self._notify(
            ("STOPPING=1", "STATUS={}".format(self._status(status)))
        )
