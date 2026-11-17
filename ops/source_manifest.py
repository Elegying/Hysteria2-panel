#!/usr/bin/env python3
"""Check/update local source pins without changing release refs or binary trust roots."""
import argparse
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = re.compile(
    r'^([A-Z0-9_]+)_SOURCE_URL="https://raw\.githubusercontent\.com/'
    r'Elegying/Hysteria2-panel/\$\{PANEL_REF\}/([^"\n]+)"$', re.MULTILINE,
)


def synchronize(root, write=False):
    installer = root / 'install.sh'
    source = installer.read_text()
    entries = SOURCE.findall(source)
    paths = [path for _, path in entries]
    if not entries or len(paths) != len(set(paths)):
        raise ValueError('source manifest is empty or duplicated')
    missing = {p.relative_to(root).as_posix() for p in (root / 'hy2panel').glob('*.py')} - set(paths)
    if missing:
        raise ValueError('modules absent from installer: ' + ', '.join(sorted(missing)))
    changed = []
    for prefix, relative in entries:
        path = (root / relative).resolve()
        if root.resolve() not in path.parents:
            raise ValueError('source escapes repository')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        pattern = re.compile(r'^' + re.escape(prefix) + r'_SHA256="([a-f0-9]{64})"$', re.MULTILINE)
        matches = list(pattern.finditer(source))
        if len(matches) != 1:
            raise ValueError('expected exactly one SHA256 for ' + prefix)
        if matches[0][1] != digest:
            changed.append(relative)
            source = pattern.sub(prefix + '_SHA256="' + digest + '"', source)
    if write and changed:
        installer.write_text(source)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='update local source hashes before release')
    args = parser.parse_args()
    try:
        changed = synchronize(ROOT, args.write)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
    if changed:
        print(('Updated: ' if args.write else 'Mismatched: ') + ', '.join(changed))
    else:
        print('Installer source hashes match the working tree.')
    return 1 if changed and not args.write else 0


if __name__ == '__main__':
    raise SystemExit(main())
