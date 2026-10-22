#!/usr/bin/env python3
"""
title: doc_review — thin CLI over the doc reviewer agent
kind: script
layer: n/a
summary: Runs agents.doc_reviewer.review(): dry-run by default (gathers findings, retrieves the rules, gates the baseline, writes nothing), `--execute` proposes and applies gated edits, first held to config/project.json `agents.max_model_calls` (scripts/model_budget.py): a --max-chunks over the cap, or a negative one that bounds nothing, is refused (exit 2) and a cap the config cannot give is exit 14, both before the agent runs; with no --model it names on stderr the registry default it will use. An unavailable model is a stated skip at exit 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # make top-level `agents`/`models` importable
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import config_loader  # noqa: E402
import exit_codes  # noqa: E402
import model_budget  # noqa: E402
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
    if args.execute:
        # Held to the cap before the agent runs, so a refused run calls no
        # model and writes nothing; a dry run calls none, so it is never held.
        try:
            model_budget.approve(
                args.max_chunks, model_budget.cap(args.root or ROOT), "--max-chunks"
            )
        except config_loader.ConfigError:
            return exit_codes.report(
                exit_codes.ExitCode.CONFIG,
                "doc_review: the model-call cap cannot be read",
                "config/project.json agents.max_model_calls",
                "set it to a whole number of 0 or more, as the line above says",
            )
        except model_budget.SpendRefused as exc:
            return exit_codes.report(
                exit_codes.ExitCode.USAGE,
                "doc_review: " + exc.what,
                exc.on,
                exc.next_step,
            )
        chosen = model_budget.announce("doc_review", args.model)
        if chosen is not None:
            sys.stderr.write(chosen + "\n")
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
        return exit_codes.ExitCode.SUCCESS
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
    return exit_codes.ExitCode.SUCCESS


if __name__ == "__main__":
    exit_codes.finish(main())
