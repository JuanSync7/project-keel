#!/usr/bin/env python3
"""
title: Build llms.txt job
kind: script
layer: n/a
summary: Deterministic: write wiki/llms.txt + wiki/llms-full.txt (the agent front door) from the corpus.
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
# The rendering logic lives in the domain (src/backend/showcase), reused by both
# the API (live) and this job (static files) — one source of truth.
sys.path.insert(0, os.path.join(ROOT, "src"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Write the agent-facing llms.txt + llms-full.txt from the corpus "
                    "(llms.txt convention). Run after build_corpus + link_corpus.")
    ap.add_argument("--root", default=ROOT, help="repo root (default: this repo)")
    ap.add_argument("--out-dir", default=os.path.join("wiki"),
                    help="output directory (default: wiki/)")
    ap.add_argument("--base-url", default="",
                    help="absolute site base for links (default: relative)")
    args = ap.parse_args(argv)

    try:
        from backend.showcase import load_showcase
    except ImportError as exc:
        # The showcase domain is product-specific; without it there is nothing to
        # render. Skip gracefully (like the optional contract checks) rather than fail.
        sys.stderr.write("build_llms_txt skipped (backend.showcase unavailable: %s)\n" % exc)
        return 0

    sc = load_showcase(args.root)
    out_dir = args.out_dir if os.path.isabs(args.out_dir) \
        else os.path.join(args.root, args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    index = sc.llms_index(args.base_url)
    full = sc.llms_full()
    for name, text in (("llms.txt", index), ("llms-full.txt", full)):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    rel = os.path.relpath(out_dir, args.root)
    print("wrote %s/llms.txt (%d bytes) + %s/llms-full.txt (%d bytes)"
          % (rel, len(index), rel, len(full)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
