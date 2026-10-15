import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "android_signing_recovery", ROOT / ".github/scripts/android_signing_recovery.py"
)
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


class RecoveryValidationTests(unittest.TestCase):
    def test_recipient_rejects_shell_input_options_and_non_age_keys(self):
        for value in ("", "--help", "$(id)", "age1" + "a" * 57, "ssh-ed25519 AAAA", "age1" + "a" * 58 + "\n"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recovery.recipient_value(value)

    def test_property_values_escape_separators_newlines_and_unicode(self):
        self.assertEqual(recovery.property_value(" a:=\\\n中"), "\\ a\\:\\=\\\\\\u000a\\u4e2d")

    def test_file_write_preserves_existing_files_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            recovery.write_private(target, b"existing")
            with self.assertRaises(ValueError):
                recovery.write_private(target, b"replacement")
            self.assertEqual(target.read_bytes(), b"existing")
            link = Path(directory) / "link"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                recovery.write_private(link, b"existing")

    def test_recovery_workflow_is_manual_owner_only_and_never_uploads_plaintext(self):
        workflow = (ROOT / ".github/workflows/android-signing-recovery.yml").read_text()
        for condition in ("github.actor == github.repository_owner", "github.triggering_actor == github.repository_owner",
                          "github.ref == 'refs/heads/main'", "github.repository == 'Elegying/Hysteria2-panel'"):
            self.assertIn(condition, workflow)
        self.assertNotIn("pull_request", workflow)
        self.assertIn("retention-days: 1", workflow)
        self.assertIn("path: ${{ runner.temp }}/backup.json.age", workflow)
        self.assertIn("contents: read", workflow)


@unittest.skipUnless(all(shutil.which(tool) for tool in ("keytool", "age", "age-keygen")),
                     "real encryption tests require age and a JDK")
class RecoveryCryptographicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="h2-recovery-test-")
        cls.directory = Path(cls.temporary.name)
        cls.key = cls.directory / "fixture.jks"
        cls.identity = cls.directory / "identity.txt"
        env = dict(os.environ, TEST_STORE_PASSWORD="fixture-store-only", TEST_KEY_PASSWORD="fixture-key-only")
        recovery.run([
            "keytool", "-genkeypair", "-noprompt", "-keystore", str(cls.key), "-storetype", "JKS",
            "-storepass:env", "TEST_STORE_PASSWORD", "-keypass:env", "TEST_KEY_PASSWORD",
            "-alias", "fixture", "-keyalg", "RSA", "-keysize", "2048", "-validity", "2", "-dname", "CN=Recovery Test",
        ], env=env)
        certificate = recovery.run([
            "keytool", "-exportcert", "-keystore", str(cls.key), "-storepass:env", "TEST_STORE_PASSWORD", "-alias", "fixture",
        ], env=env)
        cls.fingerprint = hashlib.sha256(certificate).hexdigest()
        recovery.run(["age-keygen", "-o", str(cls.identity)])
        cls.recipient = recovery.run(["age-keygen", "-y", str(cls.identity)]).decode().strip()
        cls.bundle = {
            "format_version": 1, "repository": recovery.REPOSITORY, "application_id": recovery.APPLICATION_ID,
            "keystore_base64": base64.b64encode(cls.key.read_bytes()).decode(),
            "store_password": "fixture-store-only", "key_password": "fixture-key-only", "key_alias": "fixture",
        }

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.fingerprint_patch = patch.object(recovery, "expected_certificate", return_value=self.fingerprint)
        self.fingerprint_patch.start()
        self.addCleanup(self.fingerprint_patch.stop)

    def test_encrypt_restore_and_idempotent_install_use_original_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            archive = directory / "backup.age"
            recovery.encrypt(self.bundle, self.recipient, archive)
            self.assertNotIn(self.bundle["store_password"].encode(), archive.read_bytes())
            bundle = recovery.decrypt(archive, self.identity)
            self.assertEqual(bundle, self.bundle)
            project = directory / "project"
            android = project / "mobile/android"
            android.mkdir(parents=True)
            (android / "signing.properties.example").touch()
            signing = directory / "private"
            for _ in range(2):
                recovery.install_bundle(bundle, project, signing)
            self.assertEqual((signing / "hysteria2-manager-release.jks").read_bytes(), self.key.read_bytes())
            properties = android / "signing.properties"
            self.assertEqual(properties.stat().st_mode & 0o777, 0o600)
            properties.write_text("existing configuration\n")
            with self.assertRaises(ValueError):
                recovery.install_bundle(bundle, project, signing)
            self.assertEqual(properties.read_text(), "existing configuration\n")

    def test_tampered_ciphertext_is_rejected_before_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "backup.age"
            recovery.encrypt(self.bundle, self.recipient, archive)
            data = bytearray(archive.read_bytes())
            data[-1] ^= 1
            archive.write_bytes(data)
            with self.assertRaises(RuntimeError):
                recovery.decrypt(archive, self.identity)

    def test_wrong_private_key_password_is_rejected(self):
        bundle = dict(self.bundle, key_password="incorrect-fixture-password")
        with self.assertRaises(RuntimeError):
            recovery.check_key(bundle)

    def test_other_release_certificate_is_rejected(self):
        with patch.object(recovery, "expected_certificate", return_value="0" * 64):
            with self.assertRaises(ValueError):
                recovery.check_key(self.bundle)

    def test_durable_backup_recovers_without_original_signing_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            archive = directory / "backup.json.age"
            recovery.encrypt(self.bundle, self.recipient, archive)
            archive.with_suffix(".age.sha256").write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "\n")
            identity = next(line for line in self.identity.read_text().splitlines() if line.startswith("AGE-SECRET-KEY-1"))
            # Preserve tool discovery, but remove all original signing secrets.
            env = {"PATH": os.environ["PATH"], "ANDROID_SIGNING_BACKUP_AGE_IDENTITY": identity}
            if "JAVA_HOME" in os.environ:
                env["JAVA_HOME"] = os.environ["JAVA_HOME"]
            with patch.object(recovery, "BACKUP", archive), patch.dict(os.environ, env, clear=True):
                restored = directory / "restored.age"
                recovery.rewrap_backup(self.recipient, restored)
            self.assertEqual(recovery.decrypt(restored, self.identity), self.bundle)
            self.assertIsInstance(json.loads(recovery.run(["age", "-d", "-i", str(self.identity), str(restored)])), dict)


if __name__ == "__main__":
    unittest.main()
