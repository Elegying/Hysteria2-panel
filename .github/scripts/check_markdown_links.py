#!/usr/bin/env python3
"""Reject broken relative links in tracked Markdown files."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
LINK_RE = re.compile(r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^\s)]+)")
EXTERNAL_SCHEMES = {"data", "ftp", "http", "https", "mailto", "tel"}


def markdown_files() -> list[Path]:
    ignored_parts = {".git", ".ruff_cache", ".venv-audit", "__pycache__"}
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if path.is_file() and not ignored_parts.intersection(path.relative_to(ROOT).parts)
    )


def relative_target(raw_target: str) -> str | None:
    target = raw_target[1:-1] if raw_target.startswith("<") else raw_target
    parsed = urlsplit(target)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES or parsed.netloc or not parsed.path:
        return None
    return unquote(parsed.path)


def main() -> int:
    failures: list[str] = []
    for document in markdown_files():
        source = document.read_text(encoding="utf-8")
        for line_number, line in enumerate(source.splitlines(), start=1):
            for match in LINK_RE.finditer(line):
                target = relative_target(match.group("target"))
                if target is None:
                    continue
                resolved = (document.parent / target).resolve()
                try:
                    resolved.relative_to(ROOT)
                except ValueError:
                    failures.append(
                        f"{document.relative_to(ROOT)}:{line_number}: 链接越出仓库: {target}"
                    )
                    continue
                if not resolved.exists():
                    failures.append(
                        f"{document.relative_to(ROOT)}:{line_number}: 目标不存在: {target}"
                    )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Markdown 相对链接检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
