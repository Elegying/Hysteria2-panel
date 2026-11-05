"""Verify certificate-derived SNI uses the actual persisted certificate."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from hysteria2_panel import Database, build_connection_uri


@unittest.skipUnless(shutil.which('openssl'), 'OpenSSL required')
class CertificateSniTests(unittest.TestCase):
    def test_replacement_host_uses_original_certificate_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            certificate = Path(directory) / 'cert.pem'
            key = Path(directory) / 'key.pem'
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-days', '1', '-subj', '/CN=old.example.test',
                '-addext', 'subjectAltName=DNS:old.example.test',
                '-keyout', str(key), '-out', str(certificate),
            ], check=True, capture_output=True, timeout=15)
            sni = Database._certificate_server_name(certificate.read_text())
        self.assertEqual('old.example.test', sni)
        uri = build_connection_uri('new.example.test', 443, 'test', 'ab' * 32,
                                   'replacement', sni=sni)
        self.assertIn('@new.example.test:443/', uri)
        self.assertIn('sni=old.example.test', uri)

    def test_invalid_certificate_fails_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            Database._certificate_server_name('not a certificate')


if __name__ == '__main__':
    unittest.main()
