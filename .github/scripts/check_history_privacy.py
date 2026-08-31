#!/usr/bin/env python3
"""Reject high-confidence secrets and retired identifiers before publication."""

import argparse
import hashlib
import pathlib
import re
import shutil
import subprocess  # nosec B404


DENIED_IDENTIFIER_HASHES = frozenset(
    {
        "05f20e113aeeb1585f47b7d035f0b7858f4d680244b3723220c97cd5653c23a3",
        "2d850007d81bc735c70e30249ed3a664e68865a25de5e45ead7ebb3cc2552cbd",
        "2eb97697e93d983ad58c634021fdaee5906c422a03108c766fbea53b4078f0fd",
        "c1e27bd903ec8a8ff92cf37856c3a225ddddb43a111e11847c4069b075b64e48",
        "c511547d23047d49bcdb92c401e6cd361651334e6f9780488e0b69484a694087",
        "d8e7981d904e9d246c9c5ebe7794fe462ebaf1dfba283fd58aaf6e61ec5d6a47",
    }
)
IPV4_PATTERN = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
DOMAIN_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9-])(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}(?![A-Za-z0-9-])"
)
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"[\r\nA-Za-z0-9+/=]{128,}"
    r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
TOKEN_PATTERNS = (
    re.compile("(?:" + "ghp|gho|ghu|ghs|ghr" + ")_[A-Za-z0-9]{36,}"),
    re.compile("github" + r"_pat_[A-Za-z0-9_]{60,}"),
    re.compile("AK" + r"IA[0-9A-Z]{16}"),
    re.compile("xox" + r"[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(r"[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@", re.IGNORECASE),
)
GIT = shutil.which("git")


def scan_text(source):
    findings = []
    for pattern, label in (
        (PRIVATE_KEY_PATTERN, "private-key"),
        *((pattern, "access-token") for pattern in TOKEN_PATTERNS),
    ):
        for match in pattern.finditer(source):
            findings.append((source.count("\n", 0, match.start()) + 1, label))
    for line_number, line in enumerate(source.splitlines(), 1):
        candidates = set(IPV4_PATTERN.findall(line)) | set(DOMAIN_PATTERN.findall(line))
        for candidate in candidates:
            digest = hashlib.sha256(candidate.lower().encode("utf-8")).hexdigest()
            if digest in DENIED_IDENTIFIER_HASHES:
                findings.append((line_number, "retired-identifier"))
    return sorted(set(findings))


def tracked_sources(root):
    if GIT is None:
        raise RuntimeError("git is required")
    output = subprocess.check_output(
        [GIT, "ls-files", "-z"], cwd=str(root)
    )  # nosec B603
    for name in output.decode("utf-8").split("\0"):
        if not name:
            continue
        path = root / name
        if path.is_symlink():
            raise ValueError("tracked symlinks are not allowed in publication inputs")
        if path.is_file():
            yield name, path.read_text(encoding="utf-8", errors="replace")


def added_history(root, base, head):
    if GIT is None:
        raise RuntimeError("git is required")
    for revision in (base, head):
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("history revision must be a full commit SHA")
        subprocess.run(
            [GIT, "rev-parse", "--verify", "{}^{{commit}}".format(revision)],
            cwd=str(root),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )  # nosec B603
    output = subprocess.check_output(
        [
            GIT,
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--unified=0",
            base,
            head,
            "--",
        ],
        cwd=str(root),
    ).decode("utf-8", errors="replace")  # nosec B603
    current_path = "history-diff"
    added = []
    for line in output.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            added.append((current_path, line[1:]))
    return added


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--current-tree", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    findings = []
    if args.current_tree:
        for name, source in tracked_sources(root):
            findings.extend((name, line, label) for line, label in scan_text(source))
    if bool(args.base) != bool(args.head):
        parser.error("--base and --head must be provided together")
    if args.base and args.head:
        for name, source in added_history(root, args.base, args.head):
            findings.extend((name, line, label) for line, label in scan_text(source))
    if not args.current_tree and not args.base:
        parser.error("select --current-tree and/or a --base/--head range")
    if findings:
        for name, line, label in sorted(set(findings)):
            print("{}:{}: {}".format(name, line, label))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
