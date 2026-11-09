#!/usr/bin/env python3
"""
title: Build llms.txt job
kind: script
layer: n/a
summary: Deterministically write wiki/llms.txt + wiki/llms-full.txt from the corpus, each published atomically through a sibling temporary file; a refused manifest writes neither, exiting 2 for a hunk and 14 otherwise. An explicit absolute --out-dir authorizes that directory; relative outputs are confined to --root. Escapes exit USAGE before either file is written. Internal links and missing targets are allowed; checks judge paths at call time.
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
# The root too: the domain reads the served levels through the package
# `scripts`, whose config_loader is the one served-or-not decision.
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import config_loader  # noqa: E402
from atomic_write import write_if_changed  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402
from git_tree import PathEscape, confined_path  # noqa: E402


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
    args.root = os.path.abspath(args.root)

    if not os.path.isdir(args.root):
        return report(
            ExitCode.USAGE,
            "build_llms_txt: the root is not an existing directory",
            config_loader.checkout_name(args.root),
            "pass --root a checkout directory that exists, then rerun",
        )
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
            ExitCode.USAGE if config_loader.is_conflict(exc) else ExitCode.CONFIG,
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
    boundary = out_dir if os.path.isabs(args.out_dir) else args.root
    try:
        outputs = [
            confined_path(boundary, os.path.join(out_dir, name))
            for name in ("llms.txt", "llms-full.txt")
        ]
    except PathEscape as exc:
        return report(
            ExitCode.USAGE,
            "build_llms_txt: output escapes its root",
            config_loader.shown(str(exc), bare=True),
            "keep relative outputs inside --root or choose an explicit absolute --out-dir",
        )
    for path in outputs:
        os.makedirs(os.path.dirname(path), exist_ok=True)

    index = sc.llms_index(args.base_url)
    full = sc.llms_full()
    for path, text in zip(outputs, (index, full), strict=True):
        write_if_changed(path, text.encode("utf-8"))
    rel = os.path.relpath(out_dir, args.root)
    print(
        "wrote %s/llms.txt (%d bytes) + %s/llms-full.txt (%d bytes)"
        % (rel, len(index), rel, len(full))
    )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
