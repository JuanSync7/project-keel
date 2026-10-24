#!/usr/bin/env python3
"""
title: Build llms.txt job
kind: script
layer: n/a
summary: Deterministic: write wiki/llms.txt + wiki/llms-full.txt (the agent front door) from the corpus.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_idempotence.py
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
WHO = "build_llms_txt"
# The rendering logic lives in the domain (src/backend/showcase), reused by both
# the API (live) and this job (static files) — one source of truth.
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import config_loader  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Write the agent-facing llms.txt + llms-full.txt from the corpus "
        "(llms.txt convention). Run after build_corpus + link_corpus."
    )
    ap.add_argument("--root", default=ROOT, help="repo root (default: this repo)")
    ap.add_argument(
        "--out-dir",
        default=os.path.join("wiki"),
        help="output directory (default: wiki/)",
    )
    ap.add_argument(
        "--base-url",
        default="",
        help="absolute site base for links (default: relative)",
    )
    args = ap.parse_args(argv)

    try:
        from backend.showcase import load_showcase
    except ImportError as exc:
        # The showcase domain is product-specific; without it there is nothing to
        # render. Skip gracefully (like the optional contract checks) rather than fail.
        sys.stderr.write(
            "build_llms_txt skipped (backend.showcase unavailable: %s)\n" % exc
        )
        return ExitCode.SUCCESS

    try:
        served = config_loader.served_visibilities(args.root)
    except config_loader.ConfigError as exc:
        # resolve has already written a refused value's own line; a file that
        # cannot be read is named here. Nothing is written either way.
        return report(
            ExitCode.CONFIG,
            "%s: the levels a served node may carry cannot be read" % WHO,
            "; ".join(exc.lines)
            or "corpus.served_visibilities in %s"
            % (exc.path or config_loader.CONFIG_FILE),
            "set corpus.served_visibilities to members of %s, then rerun; nothing was written"
            % ", ".join(config_loader.VISIBILITY_ORDER),
        )
    sc = load_showcase(args.root, served_visibilities=served)
    out_dir = (
        args.out_dir
        if os.path.isabs(args.out_dir)
        else os.path.join(args.root, args.out_dir)
    )
    os.makedirs(out_dir, exist_ok=True)

    index = sc.llms_index(args.base_url)
    full = sc.llms_full()
    for name, text in (("llms.txt", index), ("llms-full.txt", full)):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    rel = os.path.relpath(out_dir, args.root)
    print(
        "wrote %s/llms.txt (%d bytes) + %s/llms-full.txt (%d bytes)"
        % (rel, len(index), rel, len(full))
    )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
