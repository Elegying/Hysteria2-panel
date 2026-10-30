#!/usr/bin/env python3
"""Build the pinned Hysteria server with the managed adaptive exit extension."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
COMMIT = '14e9fff1d972ab0187ac7fcf75b9514dc8664065'
GO_VERSION = 'go1.26.5'


def build(go, architecture, output):
    if subprocess.check_output([go, 'version'], text=True).split()[2] != GO_VERSION:
        raise ValueError('Go toolchain must match ' + GO_VERSION)
    with tempfile.TemporaryDirectory(prefix='panel-adaptive-core-') as folder:
        checkout = Path(folder) / 'source'
        subprocess.run(['git', 'clone', '--quiet', '--depth=1', '--branch=app/v2.12.1',
                        'https://github.com/apernet/hysteria.git', str(checkout)], check=True)
        if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() != COMMIT:
            raise ValueError('Pinned source identity mismatch')
        subprocess.run(['git', 'apply', '--check', str(ROOT / 'server.patch')], cwd=checkout, check=True)
        subprocess.run(['git', 'apply', str(ROOT / 'server.patch')], cwd=checkout, check=True)
        shutil.copytree(ROOT / 'adaptive', checkout / 'extras/adaptive')
        for name in ('server.go', 'server_test.go'):
            shutil.copyfile(ROOT / name, checkout / 'extras/outbounds' / ('panel_' + name))
        environment = dict(os.environ, GOTOOLCHAIN='local', GOMAXPROCS='2', GOFLAGS='-trimpath')
        subprocess.run([go, 'test', '-race', '-count=1', './extras/adaptive', './extras/outbounds'],
                       cwd=checkout, env=environment, check=True)
        environment.update(GOOS='linux', GOARCH=architecture, CGO_ENABLED='0')
        prefix = 'github.com/apernet/hysteria/app/v2/cmd.'
        flags = '-s -w -buildid= ' + ' '.join('-X ' + prefix + key + '=' + value for key, value in {
            'appVersion': 'v2.12.1-panel.3', 'appType': 'managed', 'appDate': '2026-10-30',
            'appToolchain': GO_VERSION, 'appCommit': COMMIT, 'appPlatform': 'linux', 'appArch': architecture,
        }.items())
        subprocess.run([go, 'build', '-buildvcs=false', '-ldflags=' + flags, '-o', str(output), './app'],
                       cwd=checkout, env=environment, check=True)
        digest = hashlib.sha256()
        for path in sorted(ROOT.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                digest.update(str(path.relative_to(ROOT)).encode() + b'\0' + path.read_bytes() + b'\0')
        output.with_suffix('.provenance.json').write_text(json.dumps({
            'source_commit': COMMIT, 'go': GO_VERSION, 'architecture': architecture,
            'extension_sha256': digest.hexdigest(),
            'binary_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        }, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--go', required=True)
    parser.add_argument('--arch', choices=['amd64', 'arm64'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.go, args.arch, args.output.resolve())
