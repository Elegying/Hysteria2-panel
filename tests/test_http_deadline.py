import socket
import threading
import unittest
from unittest import mock

from hysteria2_panel import BoundedThreadingHTTPServer


class RequestDeadlineTests(unittest.TestCase):
    def test_replaced_deadline_cannot_expire_the_current_request(self):
        class Request:
            def __init__(self):
                self.shutdowns = []

            def shutdown(self, how):
                self.shutdowns.append(how)

        server = object.__new__(BoundedThreadingHTTPServer)
        server._active_requests_lock = threading.Lock()
        server._deadline_condition = threading.Condition(
            server._active_requests_lock
        )
        server._active_requests = set()
        server._request_deadlines = {}
        server._deadline_heap = []
        server._deadline_sequence = 0
        server._deadline_shutdown = False
        request = Request()
        server._active_requests.add(request)

        with mock.patch(
            "hysteria2_panel.threading.Timer",
            side_effect=AssertionError("request deadlines must share one scheduler"),
        ):
            self.assertTrue(server._arm_request_deadline(request, 30))
            first_generation = server._request_deadlines[request]
            self.assertTrue(server._arm_request_deadline(request, 900))
            second_generation = server._request_deadlines[request]

        self.assertNotEqual(first_generation, second_generation)
        self.assertFalse(
            server._expire_deadline_if_current(request, first_generation)
        )
        self.assertEqual([], request.shutdowns)
        self.assertTrue(
            server._expire_deadline_if_current(request, second_generation)
        )
        self.assertEqual([socket.SHUT_RDWR], request.shutdowns)


if __name__ == "__main__":
    unittest.main()
