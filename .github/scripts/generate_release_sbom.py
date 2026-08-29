#!/usr/bin/env python3
"""Generate a deterministic SPDX 2.3 inventory for the tagged source tree."""

import argparse
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import subprocess  # nosec B404


GIT = shutil.which("git")


def git(root, *arguments):
    if GIT is None:
        raise RuntimeError("git is required")
    return subprocess.check_output(
        [GIT, *arguments], cwd=str(root), text=True
    ).strip()  # nosec B603


def build_sbom(root):
    root = pathlib.Path(root).resolve()
    version_source = (root / "hy2panel" / "version.py").read_text()
    version_match = re.search(
        r'^PANEL_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"$',
        version_source,
        re.MULTILINE,
    )
    if not version_match:
        raise ValueError("release version metadata is missing")
    version = version_match.group(1)
    commit = git(root, "rev-parse", "HEAD^{commit}")
    committed_at = git(root, "show", "-s", "--format=%cI", commit)
    created = datetime.datetime.fromisoformat(committed_at.replace("Z", "+00:00"))
    created = created.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    names = git(root, "ls-files", "-z").split("\0")
    files = []
    relationships = []
    for index, name in enumerate(sorted(value for value in names if value), 1):
        path = root / name
        if path.is_symlink():
            raise ValueError("tracked symlinks are not allowed in release inputs")
        if not path.is_file():
            continue
        file_id = "SPDXRef-File-{:04d}".format(index)
        files.append(
            {
                "SPDXID": file_id,
                "fileName": "./" + name,
                "checksums": [
                    {
                        "algorithm": "SHA256",
                        "checksumValue": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                ],
                "licenseConcluded": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Package",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": file_id,
            }
        )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "Hysteria2-panel-v{}".format(version),
        "documentNamespace": (
            "https://github.com/Elegying/Hysteria2-panel/releases/tag/"
            "v{}?commit={}".format(version, commit)
        ),
        "creationInfo": {
            "created": created,
            "creators": ["Tool: Hysteria2-panel-generate-release-sbom"],
        },
        "packages": [
            {
                "name": "Hysteria2-panel",
                "SPDXID": "SPDXRef-Package",
                "versionInfo": version,
                "downloadLocation": (
                    "https://github.com/Elegying/Hysteria2-panel/tree/" + commit
                ),
                "filesAnalyzed": True,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            }
        ],
        "files": files,
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": "SPDXRef-Package",
            },
            *relationships,
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = pathlib.Path(args.output)
    output.write_text(
        json.dumps(build_sbom(args.root), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
