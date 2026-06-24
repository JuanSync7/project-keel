#!/usr/bin/env python3
"""
title: on-stop triage hook
kind: script
layer: n/a
summary: Thin event-hook entrypoint — hands a payload to the triage agent.
"""
from __future__ import annotations

import argparse
import os
import sys

# A *doer* invoked by some trigger (git hook, CI step, agent-tool hook).
# The trigger is a thin adapter that only says "run this on event X".
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)  # make top-level `agents`/`models` importable

from agents.triage import triage  # noqa: E402  (after sys.path setup)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[-1])
    ap.add_argument("payload", nargs="?", default="-",
                    help="event payload, or '-' to read stdin")
    ap.add_argument("--execute", action="store_true",
                    help="actually run the model (default: dry-run preview)")
    ap.add_argument("--model", default=None, help="model name from models/ registry")
    args = ap.parse_args(argv)
    payload = sys.stdin.read() if args.payload == "-" else args.payload
    print(triage(payload, execute=args.execute, model=args.model))
    return 0


if __name__ == "__main__":
    sys.exit(main())
