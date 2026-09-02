#!/usr/bin/env python3
"""
title: on-stop doc review hook
kind: script
layer: n/a
summary: Thin event-hook doer — runs the doc reviewer's dry-run (deterministic; no model) when a session or turn ends, and prints the one-line report. Never blocks the event: exit 0 always, an unavailable model included.
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)  # make top-level `agents`/`models` importable

from agents.doc_reviewer import review  # noqa: E402
from models import ModelUnavailable  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[-1])
    ap.add_argument(
        "payload",
        nargs="?",
        default="-",
        help="event payload, or '-' to read stdin (ignored: the review is of the tree)",
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="also propose + apply gated edits (default: dry-run)",
    )
    ap.add_argument(
        "--model", default=None, help="model name from the models/ registry"
    )
    args = ap.parse_args(argv)
    if args.payload == "-" and not sys.stdin.isatty():
        sys.stdin.read()  # the trigger's payload; the review reads the tree, not the event
    try:
        report = review(execute=args.execute, model=args.model)
    except ModelUnavailable as exc:
        print("on_stop_doc_review: model unavailable (%s); skipping" % exc)
        return 0
    print(
        "on_stop_doc_review: %d stale stamp(s), %d unresolved mention(s), %d roster row(s); "
        "%d chunk(s) queued%s"
        % (
            report.stale,
            report.unresolved,
            report.rosters,
            len(report.candidates),
            "" if report.dry_run else "; %d applied" % len(report.applied),
        )
    )
    if report.dry_run and (report.stale or report.unresolved):
        print(
            "  next: `make doc-review` for the list, `make advise` for every advisory"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
