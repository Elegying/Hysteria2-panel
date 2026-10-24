"""Run isolated Linux installer candidates; invoke explicitly on a Docker host.

The archive must contain release_lab_curl.sh. It redirects only lab-candidate
source URLs to the snapshot, retaining the installer's production SHA-256 checks.
No release signing or GitHub publication is performed. ARM may be emulated.
"""
import argparse
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess
import time

IMAGES = {
    'ubuntu': 'ubuntu:24.04@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517',
    'debian': 'debian:stable@sha256:7fa362f5e7c036d7f45621a6c721c03493cdcb5889adfcd65587759e34fe4c6f',
    'rocky': 'rockylinux:9@sha256:d7be1c094cc5845ee815d4632fe377514ee6ebcf8efaed6892889657e5ddaaa6',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--architectures', nargs='+', choices=('amd64', 'arm64'), default=['amd64', 'arm64'])
    parser.add_argument('--prefix', default='hy2-release-lab')
    parser.add_argument('--isolated-vm-host-network', action='store_true',
                        help='Only on a dedicated disposable VM; run sequentially and stop each container')
    args = parser.parse_args()
    if not re.fullmatch(r'hy2-release-[a-z0-9-]+', args.prefix):
        parser.error('Use a disposable hy2-release-* container prefix')
    directory = args.directory.resolve()
    if not (directory / 'candidate.tar').is_file() or not (directory / 'Dockerfile').is_file():
        parser.error('Provide candidate.tar and installer_e2e.Dockerfile as Dockerfile')

    def execute(item):
        distribution, arch = item
        name = args.prefix + '-' + distribution + '-' + arch
        started = time.monotonic()
        created = False
        result = {'distribution': distribution, 'architecture': arch, 'container': name,
                  'base_image': IMAGES[distribution], 'transport': 'local candidate source, real hash validation'}
        with (directory / (name + '.log')).open('w') as log:
            def run(*command, timeout=1800):
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            try:
                run('docker', 'buildx', 'build', '--load', '--platform', 'linux/' + arch, '--build-arg',
                    'BASE_IMAGE=' + IMAGES[distribution], '-t', name, str(directory))
                actual = subprocess.check_output(
                    ['docker', 'image', 'inspect', name, '--format', '{{.Architecture}}'], text=True,
                ).strip()
                if actual != arch:
                    raise RuntimeError('Built architecture differs from requested target: ' + actual)
                run('docker', 'run', '-d', '--platform', 'linux/' + arch,
                    '--privileged', '--cgroupns=host', '--name', name,
                    '--label', 'org.hy2panel.disposable-release=true',
                    *(['--network', 'host'] if args.isolated_vm_host_network else []),
                    '--tmpfs', '/run', '--tmpfs', '/run/lock',
                    '-v', '/sys/fs/cgroup:/sys/fs/cgroup:rw', name)
                created = True
                deadline = time.monotonic() + 120
                state = ''
                while time.monotonic() < deadline:
                    state = subprocess.run(
                        ['docker', 'exec', name, 'systemctl', 'is-system-running'],
                        capture_output=True, text=True, timeout=10,
                    ).stdout.strip()
                    if state in ('running', 'degraded'):
                        break
                    time.sleep(1)
                result['initial_systemd_state'] = state
                # Disposable containers can have unsupported host-only units.
                # The installer contract separately verifies every project unit.
                if state not in ('running', 'degraded'):
                    raise RuntimeError('systemd initialization did not finish: ' + state)
                run('docker', 'cp', str(directory / 'candidate.tar'), name + ':/candidate.tar')
                run('docker', 'exec', name, 'bash', '-c',
                    'mkdir /workspace && tar xf /candidate.tar -C /workspace && '
                    'touch /workspace/.release-lab && '
                    'install -m 0755 /workspace/tests/release_lab_curl.sh /usr/local/bin/curl')
                run('docker', 'exec', '-e', 'PANEL_REF=lab-candidate', name,
                    'bash', '/workspace/tests/installer_e2e.sh')
                result['status'] = 'passed'
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as error:
                result.update(status='failed', error=str(error))
        result['seconds'] = round(time.monotonic() - started, 3)
        if args.isolated_vm_host_network and created:
            subprocess.run(['docker', 'stop', name], capture_output=True, timeout=60, check=False)
        (directory / (name + '.json')).write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=1 if args.isolated_vm_host_network else 3) as pool:
        results = list(pool.map(execute, [(d, a) for a in args.architectures for d in IMAGES]))
    (directory / 'matrix.json').write_text(json.dumps(results, indent=2) + '\n')
    return 0 if all(result['status'] == 'passed' for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
