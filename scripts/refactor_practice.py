#!/usr/bin/env python3
"""
title: Refactor toward a named practice (LLM-doer entrypoint)
kind: script
layer: n/a
summary: Thin CLI over the agents/practice_refactor brain — walk the corpus KG and refactor each chunk toward a named coding practice, gating every edit on make verify. The vendor-agnostic doer behind the practice-refactor skill (trigger).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# A *doer* invoked by some trigger (the practice-refactor skill, a CI step, a
# hook). The trigger is a thin adapter that only says "run this"; the reasoning
# lives in agents/, the model in models/ — no provider name here.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # make top-level `agents`/`models`/`runtimes` importable

from agents.practice_refactor import refactor  # noqa: E402  (after sys.path setup)


def _as_dict(report):
    return {
        "practice": report.practice,
        "baseline_green": report.baseline_green,
        "candidates": list(report.candidates),
        "refactored": list(report.refactored),
        "skipped": list(report.skipped),
        "dry_run": report.dry_run,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[-1])
    ap.add_argument("practice", help="the config/practices.json practice id to apply")
    ap.add_argument(
        "--execute",
        action="store_true",
        help="actually propose + apply gated edits (default: dry-run preview)",
    )
    ap.add_argument(
        "--model", default=None, help="model name from the models/ registry"
    )
    ap.add_argument(
        "--gate",
        default="verify",
        help="make target every edit is gated on (default: verify)",
    )
    ap.add_argument(
        "--max-nodes",
        type=int,
        default=8,
        help="KG neighbourhood budget (chunks to walk)",
    )
    ap.add_argument(
        "--corpus", default=None, help="corpus path (default: <root>/wiki/corpus.json)"
    )
    ap.add_argument(
        "--root", default=None, help="repo root to refactor (default: this repo)"
    )
    ap.add_argument(
        "--runtime", default=None, help="runtime engine name (default: inprocess)"
    )
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args(argv)

    report = refactor(
        args.practice,
        execute=args.execute,
        model=args.model,
        gate=args.gate,
        max_nodes=args.max_nodes,
        corpus=args.corpus,
        root=args.root,
        runtime=args.runtime,
    )

    if args.json:
        json.dump(_as_dict(report), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        mode = "dry-run" if report.dry_run else "executed"
        sys.stdout.write(
            "refactor_practice: [%s] %s | baseline %s | %d candidate(s), "
            "%d refactored, %d skipped\n"
            % (
                report.practice,
                mode,
                "green" if report.baseline_green else "red",
                len(report.candidates),
                len(report.refactored),
                len(report.skipped),
            )
        )
        if not report.candidates:
            sys.stdout.write(
                "  (no corpus nodes matched — is the practice id right and the "
                "corpus built? try `make site-data`)\n"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
