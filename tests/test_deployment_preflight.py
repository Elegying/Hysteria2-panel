"""Run the documented entrypoint and DNS failures without touching the host."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'install.sh').read_text()


def function(name):
    start = SOURCE.index('\n' + name + '() {') + 1
    return SOURCE[start:SOURCE.index('\n}\n', start) + 3]


class DeploymentPreflightTests(unittest.TestCase):
    def test_disk_budget_sums_shared_filesystems_and_checks_separate_staging(self):
        for separate, root_space, stage_space, expected in (
            ('0', '900000', '900000', 0),
            ('0', '700000', '800000', 97),
            ('1', '700000', '300000', 0),
            ('1', '700000', '250000', 97),
            ('1', '500000', '300000', 97),
            ('1', 'invalid', '300000', 97),
        ):
            with self.subTest(separate=separate, root=root_space, stage=stage_space):
                with tempfile.TemporaryDirectory() as directory:
                    source = function('preflight_panel_disk_space').replace('/opt/hysteria2-panel', directory, 1)
                    script = source + '''
fail() { printf '%s\\n' "$*" >&2; exit 97; }
panel_workspace_directory() { printf '%s' "$WORK"; }
du() { printf '1024\\tfixture\\n'; }
stat() { if [[ "$SEPARATE" == 1 && "${@: -1}" == "$WORK" ]]; then echo 2; else echo 1; fi; }
df() {
  printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\n'
  if [[ "$SEPARATE" == 1 && "${@: -1}" == "$WORK" ]]; then
    printf 'fixture 999999 0 %s 0%% /stage\\n' "$STAGE_SPACE"
  else
    printf 'fixture 999999 0 %s 0%% /\\n' "$ROOT_SPACE"
  fi
}
preflight_panel_disk_space
'''
                    result = subprocess.run(['bash', '-eu', '-o', 'pipefail', '-c', script],
                        capture_output=True, text=True, env=dict(os.environ, WORK=directory,
                        SEPARATE=separate, ROOT_SPACE=root_space, STAGE_SPACE=stage_space))
                    self.assertEqual(expected, result.returncode, result.stderr)

    def test_disk_preflight_precedes_dependencies_payload_and_service_drain(self):
        main = SOURCE[SOURCE.index('\npreflight_download_dns\n'):]
        self.assertLess(main.index('preflight_panel_disk_space'), main.index('install_system_dependencies'))
        self.assertLess(main.index('\npreflight_panel_disk_space\n'), main.index('TMP_DIR="$(create_panel_workspace)"'))

    def test_panel_workspace_avoids_memory_filesystems(self):
        for first, second, expected, directory in (
            ('ext2/ext3', 'tmpfs', 0, '/tmp'),
            ('tmpfs', 'ext2/ext3', 0, '/var/tmp'),
            ('ramfs', 'overlayfs', 0, '/var/tmp'),
            ('tmpfs', 'tmpfs', 97, ''),
        ):
            with self.subTest(first=first, second=second):
                script = function('panel_workspace_directory') + function('create_panel_workspace') + '''
fail() { printf '%s\\n' "$*" >&2; exit 97; }
stat() { if [[ "$4" == /tmp ]]; then printf '%s' "$FIRST"; else printf '%s' "$SECOND"; fi; }
mktemp() { printf '%s' "$TMPDIR"; }
create_panel_workspace
'''
                result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                                        env=dict(os.environ, FIRST=first, SECOND=second))
                self.assertEqual(expected, result.returncode, result.stderr)
                self.assertEqual(directory, result.stdout)

    def test_disk_workspace_is_removed_by_finalizer_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='hysteria2-panel.', dir='/var/tmp') as directory:
            (Path(directory) / 'payload').write_text('fixture')
            result = subprocess.run(['bash', '-c', function('cleanup') + '\ncleanup'],
                                    env=dict(os.environ, TMP_DIR=directory), capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse(Path(directory).exists())

    def test_sh_invocation_reports_bash_requirement_before_mutation(self):
        result = subprocess.run(['sh', str(ROOT / 'install.sh')], capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('Alpine/OpenRC', result.stderr)
        self.assertNotIn('Illegal option', result.stderr)

    def test_documented_entrypoint_rejects_prerequisites_and_cleans_downloads(self):
        command = (ROOT / 'README.md').read_text().split('```bash\n', 1)[1].split('```', 1)[0]
        for mode, expected, message in (
            ('no-bash', 1, '缺少 Bash'), ('no-systemd', 1, 'systemd'),
            ('dns', 6, 'DNS'), ('proxy', 5, 'DNS'), ('tls', 60, 'TLS'),
            ('timeout', 28, '网络'), ('success', 23, ''),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                systemd = root / 'systemd'
                if mode != 'no-systemd':
                    systemd.mkdir()
                scripts = {
                    'mktemp': '#!/bin/sh\nexec /usr/bin/mktemp "' + directory + '/installer.XXXXXX"\n',
                    'rm': '#!/bin/sh\nexec /bin/rm "$@"\n',
                    'bash': '#!/bin/sh\n[ "$(/usr/bin/stat -c %a "$1")" = 600 ] || exit 98\nexit 23\n',
                    'curl': '#!/bin/sh\nwhile [ "$1" != -o ]; do shift; done\nprintf partial > "$2"\nexit '
                            + str({'dns': 6, 'proxy': 5, 'tls': 60, 'timeout': 28}.get(mode, 0)) + '\n',
                }
                for name, contents in scripts.items():
                    if name == 'bash' and mode == 'no-bash':
                        continue
                    path = root / name
                    path.write_text(contents)
                    path.chmod(0o700)
                result = subprocess.run(
                    ['/bin/sh', '-c', command.replace('/run/systemd/system', str(systemd))],
                    env=dict(os.environ, PATH=directory), capture_output=True, text=True,
                )
                self.assertEqual(expected, result.returncode, result.stderr)
                self.assertIn(message, result.stderr)
                self.assertEqual([], list(root.glob('installer.*')))

    def test_download_dns_errors_stop_without_retry_and_remove_partial_file(self):
        for status in (5, 6):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                script = function('download_file') + '''
attempts=0
curl() { attempts=$((attempts + 1)); printf partial > "$DEST"; return "$STATUS"; }
sleep() { exit 98; }
download_file https://example.invalid/file "$DEST"
rc=$?
test "$rc" = "$STATUS" && test "$attempts" = 1 && test ! -e "$DEST"
'''
                result = subprocess.run(
                    ['bash', '-c', script], capture_output=True, text=True,
                    env=dict(os.environ, DEST=directory + '/partial', STATUS=str(status)),
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn('/etc/resolv.conf', result.stderr)

    def test_dns_preflight_is_bounded_and_proxy_aware(self):
        for proxy, expected in (('', 97), ('http://proxy.invalid:8080', 0)):
            with self.subTest(proxy=bool(proxy)):
                script = function('preflight_download_dns') + '''
fail() { printf '%s\\n' "$*" >&2; exit 97; }
timeout() { [[ "$*" == "15 getent ahosts raw.githubusercontent.com" ]] || exit 98; return 124; }
PANEL_SOURCE_URL=https://raw.githubusercontent.com/example/repo/v1/app.py
preflight_download_dns
'''
                env = {key: value for key, value in os.environ.items() if key.lower() not in ('https_proxy', 'all_proxy')}
                env['HTTPS_PROXY'] = proxy
                result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
                self.assertEqual(expected, result.returncode, result.stderr)

    def test_architecture_and_dns_precede_dependency_install(self):
        main = SOURCE[SOURCE.index('[[ $# -eq 0 ]] || fail'):]
        self.assertLess(main.index('当前架构'), main.index('install_system_dependencies'))
        self.assertLess(main.index('\npreflight_download_dns\n'), main.index('install_system_dependencies'))
        self.assertLess(main.index('recover_interrupted_upgrade'), main.index('\npreflight_download_dns\n'))
