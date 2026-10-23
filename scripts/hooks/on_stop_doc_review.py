#!/usr/bin/env python3
"""
title: on-stop doc review hook
kind: script
layer: n/a
summary: Thin event-hook doer — runs the doc reviewer's dry-run (deterministic; no model) when a session or turn ends, and prints the one-line report. A dry run never blocks the event: exit 0 always, an unavailable model included. `--execute` is first held to config/project.json `agents.max_model_calls` (scripts/model_budget.py): a --max-chunks over the cap, or a negative one that bounds nothing, is refused (exit 2) and a cap the config cannot give is exit 14, both before the review; with no --model it names on stderr the registry default it will use. The run is then held to that bound as it goes: every model call is counted (models.CountedModel), and the call past it is never made, a failure (exit 1) naming the count; a saved run under wiki/.runtime/ that would resume on another model or with more calls left than the bound is refused (exit 2) naming the snapshot to remove.
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)  # make top-level `agents`/`models` importable
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import config_loader  # noqa: E402
import exit_codes  # noqa: E402
import model_budget  # noqa: E402
from agents.doc_reviewer import review  # noqa: E402
from models import CallCapReached, ModelUnavailable, RunNotApproved  # noqa: E402


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
    ap.add_argument(
        "--max-chunks", type=int, default=8, help="chunks to review per run"
    )
    args = ap.parse_args(argv)
    if args.execute:
        # Held to the cap before the agent runs, so a refused run calls no
        # model and writes nothing; a dry run calls none, so it is never held.
        try:
            model_budget.approve(
                args.max_chunks, model_budget.cap(ROOT), "--max-chunks"
            )
        except config_loader.ConfigError:
            return exit_codes.report(
                exit_codes.ExitCode.CONFIG,
                "on_stop_doc_review: the model-call cap cannot be read",
                "config/project.json agents.max_model_calls",
                "set it to a whole number of 0 or more, as the line above says",
            )
        except model_budget.SpendRefused as exc:
            return exit_codes.report(
                exit_codes.ExitCode.USAGE,
                "on_stop_doc_review: " + exc.what,
                exc.on,
                exc.next_step,
            )
        chosen = model_budget.announce("on_stop_doc_review", args.model)
        if chosen is not None:
            sys.stderr.write(chosen + "\n")
    if args.payload == "-" and not sys.stdin.isatty():
        sys.stdin.read()  # the trigger's payload; the review reads the tree, not the event
    try:
        report = review(
            execute=args.execute,
            model=args.model,
            max_chunks=args.max_chunks,
            max_model_calls=args.max_chunks if args.execute else None,
        )
    except RunNotApproved as exc:
        what, on, next_step = exc.parts
        return exit_codes.report(
            exit_codes.ExitCode.USAGE, "on_stop_doc_review: " + what, on, next_step
        )
    except CallCapReached as exc:
        what, on, next_step = model_budget.stopped(exc, "--max-chunks")
        return exit_codes.report(
            exit_codes.ExitCode.FAILURE, "on_stop_doc_review: " + what, on, next_step
        )
    except ModelUnavailable as exc:
        print("on_stop_doc_review: model unavailable (%s); skipping" % exc)
        return exit_codes.ExitCode.SUCCESS
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
    return exit_codes.ExitCode.SUCCESS


if __name__ == "__main__":
    exit_codes.finish(main())
