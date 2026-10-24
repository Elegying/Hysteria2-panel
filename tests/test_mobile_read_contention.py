"""A repeated mobile read must not rewrite an unchanged activity timestamp."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from hysteria2_panel import Database


class MobileReadContentionTests(unittest.TestCase):
    def test_same_second_read_works_with_a_competing_writer_and_revocation_is_current(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch('hysteria2_panel.time.time', return_value=1800000000):
            db = Database(Path(directory) / 'panel.db', b'm' * 32)
            db.initialize()
            admin = db.upsert_admin('lab-admin', 'synthetic-password')
            issued = db.create_mobile_session(admin, 'lab-device', 'Lab')
            completed = threading.Event()
            sessions = []

            def read():
                try:
                    sessions.append(db.get_mobile_session(issued['accessToken']))
                finally:
                    completed.set()

            with db._connect() as writer:
                writer.execute('BEGIN IMMEDIATE')
                thread = threading.Thread(target=read)
                thread.start()
                finished_under_lock = completed.wait(2)
                writer.rollback()
            thread.join(6)
            self.assertTrue(finished_under_lock, 'read attempted a redundant SQLite write')
            self.assertEqual(admin, sessions[0]['admin_id'])
            with mock.patch('hysteria2_panel.time.time', return_value=1800000001):
                self.assertIsNotNone(db.get_mobile_session(issued['accessToken']))
                with db._connect() as connection:
                    self.assertEqual(1800000001, connection.execute(
                        'SELECT last_used_at FROM mobile_sessions').fetchone()[0])
            db.revoke_mobile_session(issued['accessToken'])
            self.assertIsNone(db.get_mobile_session(issued['accessToken']))


if __name__ == '__main__':
    unittest.main()
