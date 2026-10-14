#!/usr/bin/env python3
"""Independent OSS backup adapter; no changes to the panel's WebDAV backend."""
import argparse
import datetime as dt
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

UTC = dt.timezone.utc
CONFIG = Path('/etc/hysteria2-panel/oss-backup.json')
WORK = Path('/var/backups/hysteria2-panel/oss-staging')
STATUS = Path('/var/lib/hysteria2-panel/oss-backup-status.json')
PATTERN = re.compile(r'hy2-backup-(\d{8}T\d{6}Z)-[0-9a-f]{16}\.zip')
PREFIXES = {'私家车备份/', '私家车专线备份/'}


def config_load(path=CONFIG):
    flags = os.O_RDONLY | os.O_NOFOLLOW
    fd = os.open(path, flags)
    with os.fdopen(fd) as f:
        st = os.fstat(f.fileno())
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0
                or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1
                or st.st_size > 16384):
            raise ValueError('unsafe_config')
        c = json.load(f)
    if (c.get('bucket') != 'nikuaimobi' or c.get('region') != 'cn-qingdao'
            or c.get('prefix') not in PREFIXES or c.get('retention_days') != 30
            or not c.get('access_key_id') or not c.get('access_key_secret')):
        raise ValueError('invalid_config')
    return c


def write_status(value):
    fd, tmp = tempfile.mkstemp(dir=STATUS.parent, prefix='.oss-backup-')
    try:
        os.fchmod(fd, 0o640)
        os.fchown(fd, 0, grp.getgrnam('hy2panel').gr_gid)
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, STATUS)
    finally:
        Path(tmp).unlink(missing_ok=True)


def create_archive():
    sys.path.insert(0, '/opt/hysteria2-panel')
    from hysteria2_panel import Settings, Database, BackupManager
    values = {}
    for line in Path('/etc/hysteria2-panel/panel.env').read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, sep, raw = line.partition('=')
        if sep:
            parts = shlex.split(raw)
            values[key] = parts[0] if parts else ''
    s = Settings.from_mapping(values)
    # Snapshot before constructing Database: never initialize/migrate the live DB.
    with tempfile.TemporaryDirectory(dir=WORK) as td:
        snapshot = Path(td) / 'snapshot.db'
        source = sqlite3.connect('file:' + str(s.database_path) + '?mode=ro', uri=True)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        manager = BackupManager(
            database=Database(snapshot, s.hmac_key), hmac_key=s.hmac_key,
            tls_cert=s.tls_cert, tls_key=s.tls_key, public_host=s.public_host,
            hysteria_port=s.hysteria_port, node_name=s.node_name,
            local_origin_id=s.local_origin_id, work_dir=WORK)
        archive = manager.create_archive()
        try:
            manifest = manager.validate_archive(archive, require_compatible_endpoint=True)
        except Exception:
            archive.unlink(missing_ok=True)
            raise
    return archive, manifest['proxyUserCount']


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_download(client, sdk, c, key, digest, size):
    acl = client.get_object_acl(sdk.GetObjectAclRequest(bucket=c['bucket'], key=key))
    if acl.acl != 'private':
        raise RuntimeError('object_not_private')
    result = client.get_object(sdk.GetObjectRequest(bucket=c['bucket'], key=key))
    h, count = hashlib.sha256(), 0
    try:
        for chunk in result.body.iter_bytes():
            count += len(chunk)
            if count > size:
                raise RuntimeError('download_size_mismatch')
            h.update(chunk)
    finally:
        result.body.close()
    if count != size or h.hexdigest() != digest:
        raise RuntimeError('download_hash_mismatch')


def assert_not_public(c, key):
    url = ('https://' + c['bucket'] + '.oss-cn-qingdao.aliyuncs.com/'
           + urllib.parse.quote(key, safe='/'))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=30):
            raise RuntimeError('anonymous_access_allowed')
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise RuntimeError('anonymous_access_unverified') from None


def retention_candidates(objects, prefix, now):
    cutoff = now - dt.timedelta(days=30)
    candidates = []
    for obj in objects:
        if not obj.key.startswith(prefix):
            continue
        match = PATTERN.fullmatch(obj.key[len(prefix):])
        if not match or obj.last_modified is None:
            continue
        try:
            stamped = dt.datetime.strptime(match[1], '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)
        except ValueError:
            continue
        # Both filename and actual object age must exceed the retention period.
        if stamped < cutoff and obj.last_modified < cutoff:
            candidates.append(obj.key)
    return candidates


def prune(client, sdk, c, now, previous):
    # A failed backup must never cause all remaining recovery points to disappear.
    if (previous.get('bucket') != c['bucket'] or previous.get('prefix') != c['prefix']
            or not previous.get('lastSuccessAt') or not previous.get('key')):
        raise RuntimeError('no_verified_backup_for_retention')
    last = dt.datetime.fromisoformat(previous['lastSuccessAt'])
    if not dt.timedelta(0) <= now - last <= dt.timedelta(days=8):
        raise RuntimeError('verified_backup_too_old_for_retention')
    verify_download(client, sdk, c, previous['key'], previous['sha256'], previous['size'])
    token, objects = None, []
    for _ in range(100):
        result = client.list_objects_v2(sdk.ListObjectsV2Request(
            bucket=c['bucket'], prefix=c['prefix'] + 'hy2-backup-',
            continuation_token=token, max_keys=1000))
        objects.extend(result.contents or [])
        if not result.is_truncated:
            break
        next_token = result.next_continuation_token
        if not next_token or next_token == token:
            raise RuntimeError('invalid_pagination')
        token = next_token
    else:
        raise RuntimeError('retention_listing_limit')
    keys = retention_candidates(objects, c['prefix'], now)
    for key in keys:
        if key == previous['key']:
            continue
        client.delete_object(sdk.DeleteObjectRequest(bucket=c['bucket'], key=key))
    return len(keys)


def run(prune_only=False):
    import alibabacloud_oss_v2 as sdk
    now = dt.datetime.now(UTC)
    previous = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    archive = None
    try:
        c = config_load()
        config = sdk.Config(region=c['region'],
            endpoint='https://oss-cn-qingdao.aliyuncs.com',
            credentials_provider=sdk.credentials.StaticCredentialsProvider(
                c['access_key_id'], c['access_key_secret']),
            retry_max_attempts=3, connect_timeout=15, readwrite_timeout=60,
            enabled_redirect=False, insecure_skip_verify=False)
        client = sdk.Client(config)
        if prune_only:
            deleted = prune(client, sdk, c, now, previous)
            previous.update(retentionCheckedAt=now.isoformat(), deleted=deleted,
                            retentionState='success')
            write_status(previous)
            print(json.dumps({'retention': 'success', 'deleted': deleted}))
            return
        archive, users = create_archive()
        digest, size = digest_file(archive), archive.stat().st_size
        key = c['prefix'] + 'hy2-backup-' + now.strftime('%Y%m%dT%H%M%SZ') + '-' + digest[:16] + '.zip'
        client.put_object_from_file(sdk.PutObjectRequest(
            bucket=c['bucket'], key=key, acl='private', storage_class='Standard',
            server_side_encryption='AES256', forbid_overwrite=True,
            cache_control='no-store', metadata={'sha256': digest}), str(archive))
        verify_download(client, sdk, c, key, digest, size)
        assert_not_public(c, key)
        result = dict(state='success', checkedAt=now.isoformat(), lastSuccessAt=now.isoformat(),
                      bucket=c['bucket'], prefix=c['prefix'], key=key,
                      sha256=digest, size=size, users=users, errorCode=None)
        write_status(result)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        if prune_only:
            previous.update(retentionState='failed', retentionCheckedAt=now.isoformat())
        else:
            previous.update(state='failed', checkedAt=now.isoformat(), errorCode='OSS_BACKUP_FAILED')
        write_status(previous)
        # Do not expose SDK request/signature/credential details in journal output.
        print(json.dumps({'state': 'failed', 'phase': 'retention' if prune_only else 'backup',
                          'errorType': type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if archive is not None:
            archive.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prune-only', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    WORK.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (WORK / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.prune_only)
