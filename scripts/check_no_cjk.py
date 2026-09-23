#!/usr/bin/env python3
"""Fail if any tracked text file contains CJK characters.

The repository is English-only by policy, including docs, comments, and
user-facing strings. Binary assets (the hero GIF, images) are skipped because
their bytes match CJK ranges by accident.

    python3 scripts/check_no_cjk.py

Exits 0 when clean, 1 when a CJK character is found.
"""
from __future__ import annotations

import re
import subprocess
import sys

CJK = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")


def is_binary(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return b"\x00" in fh.read(8192)
    except OSError:
        return True


def main() -> int:
    try:
        files = subprocess.check_output(
            ["git", "ls-files"], text=True, stderr=subprocess.DEVNULL
        ).split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("not a git repository", file=sys.stderr)
        return 2

    offenders: list[tuple[str, int, int, str]] = []
    for path in files:
        if is_binary(path):
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            hits = CJK.findall(line)
            if hits:
                offenders.append((path, lineno, len(hits), line.strip()[:100]))

    if not offenders:
        print(f"ok: no CJK in {len(files)} tracked files")
        return 0

    total = sum(n for _, _, n, _ in offenders)
    print(f"FAIL: {total} CJK characters in {len(offenders)} lines\n")
    for path, lineno, n, snippet in offenders:
        print(f"  {path}:{lineno}  ({n} chars)  {snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
