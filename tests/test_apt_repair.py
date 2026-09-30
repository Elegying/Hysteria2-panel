import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'install.sh').read_text()
FUNCTION = SOURCE[SOURCE.index('repair_debian_apt_sources() {'):SOURCE.index('retry_package_command() {')]


class AptRepairTests(unittest.TestCase):
    def run_repair(self, text, *, fail=False, distro='11', symlink=False):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            apt = base / 'apt'
            apt.mkdir()
            source = apt / 'sources.list'
            source.write_text(text)
            if symlink:
                source.rename(base / 'target')
                source.symlink_to(base / 'target')
            release = base / 'os-release'
            release.write_text('ID=debian\nVERSION_ID="' + distro + '"\n')
            executable = base / 'apt-get'
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$APT_CAPTURE"\nexit ' + ('1' if fail else '0') + '\n')
            executable.chmod(0o700)
            capture = base / 'capture'
            args = [str(apt), str(release), str(base / 'backup')]
            result = subprocess.run(['bash', '-c', FUNCTION + '\nrepair_debian_apt_sources "$@"', 'test'] + args,
                                    env={**os.environ, 'PATH': str(base) + ':' + os.environ['PATH'], 'APT_CAPTURE': str(capture)},
                                    capture_output=True, text=True)
            reports = [json.loads(p.read_text()) for p in (base / 'backup').glob('*/report.json')]
            backups = [p.read_bytes() for p in (base / 'backup').glob('*/0')]
            return result, source.read_text(), reports, backups, capture.read_text() if capture.exists() else ''

    def test_repairs_official_sources_and_preserves_third_party(self):
        text = ('deb http://security.debian.org/ bullseye/updates main\n'
                'deb-src https://deb.debian.org/debian-security bullseye-security main\n'
                'deb http://deb.debian.org/debian bullseye-backports main\n'
                'deb https://example.org/debian bullseye-backports main\n'
                'deb http://deb.debian.org/debian bullseye main\n')
        result, after, reports, backups, command = self.run_repair(text)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(2, after.count('[check-valid-until=no]'))
        self.assertIn('# deb http://deb.debian.org/debian bullseye-backports main', after)
        self.assertIn('deb https://example.org/debian bullseye-backports main', after)
        self.assertIn('deb http://deb.debian.org/debian bullseye main', after)
        self.assertEqual([text.encode()], backups)
        self.assertEqual('verified', reports[0]['status'])
        self.assertIn('APT::Update::Error-Mode=any', command)
        self.assertNotIn('trusted=yes', after)
        self.assertNotIn('AllowUnauthenticated', command)
        again = self.run_repair(after)
        self.assertEqual(1, again[0].returncode)
        self.assertEqual(after, again[1])
        self.assertEqual([], again[2])

    def test_validation_failure_restores_original_bytes(self):
        text = 'deb http://security.debian.org/ bullseye/updates main\n'
        result, after, reports, backups, _ = self.run_repair(text, fail=True)
        self.assertEqual(1, result.returncode)
        self.assertEqual(text, after)
        self.assertEqual('rolled_back', reports[0]['status'])
        self.assertEqual([text.encode()], backups)

    def test_other_distribution_custom_options_and_symlinks_are_untouched(self):
        original = 'deb http://security.debian.org/ bullseye/updates main\n'
        for text, kwargs in [(original, {'distro': '12'}), (original, {'symlink': True}),
                             ('deb [signed-by=/custom/key] http://security.debian.org/ bullseye/updates main\n', {}),
                             ('deb https://security.debian.org.evil.test/ bullseye/updates main\n', {})]:
            with self.subTest(text=text, kwargs=kwargs):
                result, after, reports, _, command = self.run_repair(text, **kwargs)
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertEqual(text, after)
                self.assertEqual([], reports)
                self.assertEqual('', command)

    def test_retry_repairs_once_and_reexecutes_failed_command(self):
        helper = SOURCE[SOURCE.index('repair_package_failure() {'):SOURCE.index('\ninstall_system_dependencies() {')]
        for succeeds in (True, False):
            script = helper + '\nattempts=0\nrepairs=0\nsleep() { :; }\n'
            script += 'repair_debian_apt_sources() { repairs=$((repairs+1)); return 0; }\n'
            script += 'apt-get() { attempts=$((attempts+1)); ' + ('(( attempts >= 4 ));' if succeeds else 'return 1;') + ' }\n'
            script += 'retry_package_command apt-get update\nresult=$?\nprintf "%s %s" "$attempts" "$repairs"\nexit "$result"\n'
            r = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
            self.assertEqual(0 if succeeds else 1, r.returncode)
            self.assertTrue(r.stdout.endswith('4 1'), r.stdout)

    def test_package_repair_classifies_failures_and_runs_once(self):
        helper = SOURCE[SOURCE.index('repair_package_failure() {'):SOURCE.index('retry_package_command() {')]
        cases = [('apt-get', 'dpkg was interrupted', 'dpkg --force-confdef --force-confold --configure -a'),
                 ('apt-get', 'Hash Sum mismatch', 'apt-get -o'),
                 ('dnf', 'Failed to download repomd.xml', 'clean metadata'),
                 ('yum', 'incorrect checksum', 'clean metadata'),
                 ('apt-get', 'NO_PUBKEY untrusted key', None),
                 ('apt-get', 'Could not get lock', None),
                 ('dnf', 'GPG check FAILED', None)]
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'failure.log'
            for manager, error, expected in cases:
                with self.subTest(manager=manager, error=error):
                    log.write_text(error)
                    script = helper + '\ndpkg() { echo "dpkg $*"; }; apt-get() { echo "apt-get $*"; }; dnf() { echo "dnf $*"; }; yum() { echo "yum $*"; }\n'
                    script += 'repair_package_failure "$1" "$2"; repair_package_failure "$1" "$2"\n'
                    result = subprocess.run(['bash', '-c', script, 'test', manager, str(log)], capture_output=True, text=True)
                    self.assertEqual(1, result.returncode)
                    self.assertEqual('', result.stderr)
                    if expected:
                        self.assertEqual(1, result.stdout.count(expected))
                    else:
                        self.assertEqual('', result.stdout)

    def test_retries_use_native_lock_and_network_limits(self):
        helper = SOURCE[SOURCE.index('repair_package_failure() {'):SOURCE.index('\ninstall_system_dependencies() {')]
        for manager in ('apt-get', 'dnf', 'yum'):
            script = helper + '\n' + manager + '() { printf "%s\\n" "$*"; }\nretry_package_command ' + manager + ' install -y demo\n'
            result = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('DPkg::Lock::Timeout=120' if manager == 'apt-get' else '--setopt=timeout=30', result.stdout)
            self.assertNotIn('force-yes', result.stdout)
            self.assertNotIn('allowerasing', result.stdout)
