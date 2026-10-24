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
