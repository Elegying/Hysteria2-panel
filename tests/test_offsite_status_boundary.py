import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from offsite_backup import OffsiteBackupConfig, OffsiteBackupRunner


class OffsiteStatusBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.status = self.root / "status.json"
        self.config = self.root / "config.json"
        self.deep = "[" * 1800 + "0" + "]" * 1800
        self.status.write_text(self.deep, encoding="utf-8")
        self.status.chmod(0o640)
        self.factory = mock.Mock(side_effect=RuntimeError("archive-fixture-failure"))
        self.runner = OffsiteBackupRunner(
            self.config, self.status, self.factory,
            expected_uid=os.geteuid(), status_gid=os.getegid(),
        )

    def test_invalid_previous_state_does_not_block_unconfigured_status(self):
        result = self.runner.run()
        self.assertEqual("not_configured", result["state"])
        self.assertIsNone(result["lastSuccessAt"])
        self.factory.assert_not_called()
        self.assertEqual(result, json.loads(self.status.read_text(encoding="utf-8")))

    def test_invalid_previous_state_does_not_block_backup_or_failure_status(self):
        self.config.write_text(json.dumps({
            "endpoint": "https://backup.example.test/hy2panel/",
            "username": "backup-user", "password": "fixture-password",
        }), encoding="utf-8")
        self.config.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, "archive-fixture-failure"):
            self.runner.run()
        self.factory.assert_called_once_with()
        state = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertEqual("failed", state["state"])
        self.assertEqual("BACKUP_FAILED", state["errorCode"])
        self.assertIsNone(state["lastSuccessAt"])
        self.assertNotIn("fixture-password", self.status.read_text(encoding="utf-8"))

    def test_deep_configuration_has_the_normal_validation_error(self):
        self.config.write_text(self.deep, encoding="utf-8")
        self.config.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "offsite backup config is invalid"):
            OffsiteBackupConfig.load(self.config, expected_uid=os.geteuid())
