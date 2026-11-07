#!/usr/bin/env python3
"""
title: Rebuild index job
kind: script
layer: n/a
summary: Deterministic scheduled job — regenerates a doc index. No LLM. An explicit absolute output file authorizes its parent directory; relative outputs stay under the project root. Escapes exit USAGE before writing. Internal links are allowed; checks judge paths at call time.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_idempotence.py
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from exit_codes import ExitCode, finish, report  # noqa: E402
from git_tree import PathEscape, confined_path  # noqa: E402


def _title_of(md_path: str) -> str:
    """Pull the frontmatter `title:` from a markdown file (best-effort)."""
    with open(md_path, encoding="utf-8") as fh:
        if not fh.readline().startswith("---"):
            return os.path.relpath(md_path, ROOT)
        for line in fh:
            if line.strip() == "---":
                break
            if line.startswith("title:"):
                return line.split(":", 1)[1].strip()
    return os.path.relpath(md_path, ROOT)


def build_index(root: str) -> str:
    """Markdown index of every README.md under `root`. Pure + idempotent."""
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and d != "__pycache__"
        ]
        if "README.md" in filenames:
            p = os.path.join(dirpath, "README.md")
            rows.append(
                "- [%s](%s) — %s"
                % (
                    os.path.relpath(dirpath, root) or ".",
                    os.path.relpath(p, root),
                    _title_of(p),
                )
            )
    rows.sort()
    return "# Doc index\n\n" + "\n".join(rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[-1])
    ap.add_argument("--root", default=ROOT, help="tree to index (default: repo root)")
    ap.add_argument("--out", default="-", help="output file, or '-' for stdout")
    args = ap.parse_args(argv)
    index = build_index(args.root)
    if args.out == "-":
        sys.stdout.write(index)
    else:
        try:
            boundary = (
                os.path.dirname(args.out) if os.path.isabs(args.out) else args.root
            )
            out = confined_path(boundary, args.out)
        except PathEscape as exc:
            return report(
                ExitCode.USAGE,
                "rebuild_index: output escapes its root",
                str(exc),
                "keep relative --out inside --root or choose an explicit absolute output",
            )
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(index)
        print("wrote %s" % args.out)
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
