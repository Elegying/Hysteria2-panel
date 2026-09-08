"""Ed25519 input must have its complete length before OpenSSL can inspect it."""

import base64
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import node_agent
from hy2panel import nodes


class OpenSSLInputTests(unittest.TestCase):
    def test_fallback_unlinks_before_write_and_exposes_a_complete_seekable_input(self):
        for helper in (nodes._openssl_message_input, node_agent._openssl_message_input):
            with self.subTest(helper=helper.__module__):
                real_write = os.write
                writes = []

                def write(descriptor, value):
                    metadata = os.fstat(descriptor)
                    self.assertEqual(0, metadata.st_nlink)
                    self.assertEqual(0o600, stat.S_IMODE(metadata.st_mode))
                    writes.append(len(value))
                    return real_write(descriptor, value)

                message = b'auth-secret-fixture' * 10000
                with mock.patch.object(os, "memfd_create", None, create=True), \
                        mock.patch.object(os, "write", side_effect=write):
                    path, options, descriptor = helper(message)
                try:
                    self.assertEqual("/dev/fd/{}".format(descriptor), path)
                    self.assertEqual({"pass_fds": (descriptor,)}, options)
                    self.assertEqual(len(message), os.fstat(descriptor).st_size)
                    self.assertEqual(message, os.read(descriptor, len(message)))
                    self.assertTrue(writes)
                finally:
                    os.close(descriptor)

    def test_delayed_parent_communicate_cannot_break_real_signing_or_verification(self):
        homebrew = Path("/opt/homebrew/opt/openssl@3/bin/openssl")
        openssl = str(homebrew) if homebrew.exists() else shutil.which("openssl")
        self.assertIsNotNone(openssl)
        real_run = subprocess.run
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "private.pem"
            real_run([openssl, "genpkey", "-algorithm", "ED25519", "-out", str(key)],
                     check=True, capture_output=True)
            key.chmod(0o600)
            public = real_run([openssl, "pkey", "-in", str(key), "-pubout", "-outform", "DER"],
                              check=True, capture_output=True).stdout
            message = b"signed heartbeat"

            def delayed_run(argv, **kwargs):
                payload = kwargs.pop("input", None)
                timeout = kwargs.pop("timeout")
                kwargs.pop("check")
                with subprocess.Popen(argv, stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
                                      **kwargs) as child:
                    # A pipe input lets OpenSSL stat length=0 during this pause.
                    time.sleep(0.2)
                    stdout, stderr = child.communicate(payload, timeout=timeout)
                    return subprocess.CompletedProcess(argv, child.returncode, stdout, stderr)

            with mock.patch.object(os, "memfd_create", None, create=True), \
                    mock.patch.object(subprocess, "run", side_effect=delayed_run):
                signature = node_agent._openssl_sign(key, message, executable=openssl)
                verifier = nodes.OpenSSLSignatureVerifier(executable=openssl)
                self.assertTrue(verifier(base64.b64encode(public).decode(), message, signature))
                self.assertFalse(verifier(base64.b64encode(public).decode(), message + b"!", signature))

    def test_failed_fallback_write_closes_the_unlinked_descriptor(self):
        for helper in (nodes._openssl_message_input, node_agent._openssl_message_input):
            with self.subTest(helper=helper.__module__):
                descriptors = []

                def write(descriptor, _value):
                    descriptors.append(descriptor)
                    raise OSError("injected write failure")

                with mock.patch.object(os, "memfd_create", None, create=True), \
                        mock.patch.object(os, "write", side_effect=write):
                    with self.assertRaisesRegex(OSError, "injected"):
                        helper(b"secret-fixture")
                with self.assertRaises(OSError):
                    os.fstat(descriptors[0])


if __name__ == "__main__":
    unittest.main()
