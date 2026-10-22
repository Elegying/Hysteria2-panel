import socket
import threading
import unittest

from tests.stability_soak import Echo, EchoServer, receive


class SoakDiagnosticsTests(unittest.TestCase):
    def test_partial_receive_retains_the_byte_boundary(self):
        reader, writer = socket.socketpair()
        with reader, writer:
            writer.sendall(b"ab")
            writer.shutdown(socket.SHUT_WR)
            with self.assertRaisesRegex(RuntimeError, "stream close after 2/4 bytes"):
                receive(reader, 4)

    def exercise_echo_close(self, idle_timeout):
        records = []
        recorded = threading.Event()

        def record(**event):
            records.append(event)
            recorded.set()

        with EchoServer(("127.0.0.1", 0), Echo, record) as server:
            server.read_timeout = .1 if idle_timeout else 5
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01})
            thread.start()
            try:
                with socket.create_connection(server.server_address, timeout=2) as client:
                    client.sendall(b"live-data")
                    self.assertEqual(receive(client, 9), b"live-data")
                    if not idle_timeout:
                        client.shutdown(socket.SHUT_WR)
                    self.assertTrue(recorded.wait(2), "The echo close cause was lost")
                    self.assertEqual(client.recv(1), b"")
                    self.assertEqual(records[0]["peerPort"], client.getsockname()[1])
            finally:
                server.shutdown()
                thread.join(timeout=2)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["receivedBytes"], 9)
        return records[0]

    def test_peer_eof_is_distinct_from_idle_timeout(self):
        result = self.exercise_echo_close(False)
        self.assertEqual(result["reason"], "eof")
        self.assertIsNone(result["errorType"])

    def test_actual_echo_timeout_is_reported_before_stream_close(self):
        result = self.exercise_echo_close(True)
        self.assertEqual(result["reason"], "socket-error")
        self.assertIn(result["errorType"], ("TimeoutError", "timeout"))
        self.assertGreaterEqual(result["idleSeconds"], .1)
