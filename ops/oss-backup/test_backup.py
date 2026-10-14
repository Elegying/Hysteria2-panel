import datetime as dt
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
import hashlib

spec = importlib.util.spec_from_file_location('oss_backup', Path(__file__).with_name('backup.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
NOW = dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc)
PREFIX = '私家车备份/'


class BackupTests(unittest.TestCase):
    def obj(self, key, days):
        return N(key=key, last_modified=NOW - dt.timedelta(days=days))

    def test_retention_only_own_generated_archives(self):
        name = 'hy2-backup-20260901T000000Z-0123456789abcdef.zip'
        entries = [self.obj(PREFIX + name, 39), self.obj('私家车专线备份/' + name, 39),
                   self.obj(PREFIX + 'manual.zip', 39), self.obj(PREFIX + 'sub/' + name, 39)]
        self.assertEqual(b.retention_candidates(entries, PREFIX, NOW), [PREFIX + name])

    def test_retention_requires_filename_and_remote_age(self):
        entries = [self.obj(PREFIX + 'hy2-backup-20260901T000000Z-0123456789abcdef.zip', 1),
                   self.obj(PREFIX + 'hy2-backup-20261009T000000Z-0123456789abcdef.zip', 40),
                   self.obj(PREFIX + 'hy2-backup-20269999T000000Z-0123456789abcdef.zip', 40)]
        self.assertEqual(b.retention_candidates(entries, PREFIX, NOW), [])

    def test_exact_30_days_is_not_deleted(self):
        e = self.obj(PREFIX + 'hy2-backup-20260910T000000Z-0123456789abcdef.zip', 30)
        self.assertEqual(b.retention_candidates([e], PREFIX, NOW), [])

    def test_no_recent_verified_backup_prevents_cleanup(self):
        for state in [{}, {'bucket': 'nikuaimobi', 'prefix': PREFIX, 'key': 'x',
                           'lastSuccessAt': (NOW - dt.timedelta(days=9)).isoformat()}]:
            with self.assertRaises(RuntimeError):
                b.prune(None, None, {'bucket': 'nikuaimobi', 'prefix': PREFIX}, NOW, state)

    def test_public_acl_fails_before_downloading(self):
        sdk = N(GetObjectAclRequest=lambda **k: k)
        client = N(get_object_acl=lambda r: N(acl='public-read'))
        with self.assertRaisesRegex(RuntimeError, 'not_private'):
            b.verify_download(client, sdk, {'bucket': 'nikuaimobi'}, 'key', 'hash', 4)

    def test_corrupt_download_rejected_and_closed(self):
        class Stream(io.BytesIO):
            def iter_bytes(self):
                yield self.read()
        body = Stream(b'wrong')
        sdk = N(GetObjectAclRequest=lambda **k: k, GetObjectRequest=lambda **k: k)
        client = N(get_object_acl=lambda r: N(acl='private'), get_object=lambda r: N(body=body))
        with self.assertRaisesRegex(RuntimeError, 'hash_mismatch'):
            b.verify_download(client, sdk, {'bucket': 'nikuaimobi'}, 'key', hashlib.sha256(b'right').hexdigest(), 5)
        self.assertTrue(body.closed)

    def test_failed_verification_prevents_delete(self):
        state = {'bucket': 'nikuaimobi', 'prefix': PREFIX, 'key': 'key', 'sha256': 'h',
                 'size': 4, 'lastSuccessAt': NOW.isoformat()}
        with patch.object(b, 'verify_download', side_effect=RuntimeError('corrupt')):
            with self.assertRaisesRegex(RuntimeError, 'corrupt'):
                b.prune(None, None, {'bucket': 'nikuaimobi', 'prefix': PREFIX}, NOW, state)


if __name__ == '__main__':
    unittest.main()
