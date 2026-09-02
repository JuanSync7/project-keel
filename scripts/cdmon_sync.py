#!/usr/bin/env python3
"""
title: cdmon adapter
kind: script
layer: n/a
summary: Thin wrapper that invokes cdmon — no tool logic lives here.
"""

# NB: no `from __future__ import annotations` here on purpose, and annotations
# stay 3.x-safe — .pre-commit-config.yaml runs this as a bare `python3`, which
# on a `language: system` hook is whatever the committing shell has (this host's
# is 3.6.8). The file must PARSE there so the graceful skips below can fire.
# Same rule and same reason as generate_aad_schema.py / export_openapi.py; see
# docs/guides/deterministic-checks.md ("Adding a new deterministic check").
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join("config", "cdmon", "cdmon.yaml")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run cdmon over the repo (thin adapter).")
    ap.add_argument(
        "mode",
        nargs="?",
        default="lint",
        choices=["lint", "heal", "build"],
        help="cdmon subcommand to run",
    )
    ap.add_argument(
        "--check", action="store_true", help="alias for `lint` (used by pre-commit)"
    )
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args(argv)

    if shutil.which("cdmon") is None:
        # No-op so the hook/CI stays green where cdmon isn't installed.
        print("cdmon not installed; skipping (install it to enable drift checks).")
        return 0
    if not os.path.exists(os.path.join(ROOT, args.config)):
        print(f"no cdmon config at {args.config}; skipping.")
        return 0

    mode = "lint" if args.check else args.mode
    return subprocess.run(["cdmon", mode, "--config", args.config], cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
