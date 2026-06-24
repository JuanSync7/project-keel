#!/usr/bin/env python3
"""
title: Rebuild index job
kind: script
layer: n/a
summary: Deterministic scheduled job — regenerates a doc index. No LLM.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d != "__pycache__"]
        if "README.md" in filenames:
            p = os.path.join(dirpath, "README.md")
            rows.append("- [%s](%s) — %s" % (
                os.path.relpath(dirpath, root) or ".",
                os.path.relpath(p, root), _title_of(p)))
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
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(index)
        print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
