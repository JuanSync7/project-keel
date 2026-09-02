#!/usr/bin/env python3
"""
title: doc_review — thin CLI over the doc reviewer agent
kind: script
layer: n/a
summary: Runs agents.doc_reviewer.review(): dry-run by default (gathers findings, retrieves the rules, gates the baseline, writes nothing), `--execute` proposes and applies gated edits. An unavailable model is a stated skip at exit 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # make top-level `agents`/`models` importable

from agents.doc_reviewer import review  # noqa: E402
from models import ModelUnavailable  # noqa: E402


def _as_dict(report):
    return {
        "baseline_green": report.baseline_green,
        "stale": report.stale,
        "unresolved": report.unresolved,
        "rosters": report.rosters,
        "candidates": list(report.candidates),
        "applied": list(report.applied),
        "skipped": list(report.skipped),
        "preview": report.preview,
        "dry_run": report.dry_run,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[-1])
    ap.add_argument(
        "--execute",
        action="store_true",
        help="propose + apply gated edits (default: dry-run)",
    )
    ap.add_argument(
        "--model", default=None, help="model name from the models/ registry"
    )
    ap.add_argument(
        "--gate",
        default="check-docs",
        help="make target every edit is gated on (default: check-docs)",
    )
    ap.add_argument(
        "--max-chunks", type=int, default=8, help="chunks to review per run"
    )
    ap.add_argument(
        "--root", default=None, help="repo root to review (default: this repo)"
    )
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args(argv)
    try:
        report = review(
            execute=args.execute,
            model=args.model,
            gate=args.gate,
            max_chunks=args.max_chunks,
            root=args.root,
        )
    except ModelUnavailable as exc:
        # Absent, not broken: say so, write nothing, exit 0.
        sys.stdout.write("doc_review: model unavailable (%s); skipping\n" % exc)
        return 0
    if args.json:
        json.dump(_as_dict(report), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        mode = "dry-run" if report.dry_run else "executed"
        sys.stdout.write(
            "doc_review: [%s] baseline %s | %d stale, %d unresolved mention(s), %d roster row(s) | "
            "%d chunk(s) queued, %d applied, %d skipped\n"
            % (
                mode,
                "green" if report.baseline_green else "red",
                report.stale,
                report.unresolved,
                report.rosters,
                len(report.candidates),
                len(report.applied),
                len(report.skipped),
            )
        )
        if report.dry_run and report.candidates:
            sys.stdout.write(
                "  next: `make doc-review-apply` (or `--execute`) to propose and apply gated edits\n"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
