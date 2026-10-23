#!/usr/bin/env python3
"""
title: Refactor toward a named practice (LLM-doer entrypoint)
kind: script
layer: n/a
summary: Thin CLI over the agents/practice_refactor brain — walk the corpus KG and refactor each chunk toward a named coding practice, gating every edit on make verify. The vendor-agnostic doer behind the practice-refactor skill (trigger). `--execute` is first held to config/project.json `agents.max_model_calls` (scripts/model_budget.py): a --max-nodes over the cap, or a negative one that bounds nothing, is refused (exit 2) and a cap the config cannot give is exit 14, both before the agent runs; with no --model it names on stderr the registry default it will use. The run is then held to that bound as it goes: every model call is counted (models.CountedModel), and the call past it is never made, a failure (exit 1) naming the count; a saved run under wiki/.runtime/ that would resume on another model or with more calls left than the bound is refused (exit 2) naming the snapshot to remove. A setting the model or the runtime reads once the agent starts (models.timeout_seconds, models.max_reply_bytes, runtimes.max_steps, agents.tool_timeout_seconds, agents.tool_max_output_bytes) that scripts/config_loader.py refuses is exit 14 naming the key, in either mode, never a traceback; a tool child the agent runs that is ended at agents.tool_timeout_seconds or agents.tool_max_output_bytes (scripts/resource_limits.py run_tool) is a failure (exit 1) naming the key.
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
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import config_loader  # noqa: E402
import exit_codes  # noqa: E402
import model_budget  # noqa: E402
from agents.practice_refactor import refactor  # noqa: E402  (after sys.path setup)
from models import CallCapReached, ModelUnavailable, RunNotApproved  # noqa: E402
from scripts.resource_limits import (  # noqa: E402
    ChildOutputTooLarge,
    ChildTimedOut,
)


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
    if args.execute:
        # Held to the cap before the agent runs, so a refused run calls no
        # model and writes nothing; a dry run calls none, so it is never held.
        try:
            model_budget.approve(
                args.max_nodes, model_budget.cap(args.root or ROOT), "--max-nodes"
            )
        except config_loader.ConfigError:
            return exit_codes.report(
                exit_codes.ExitCode.CONFIG,
                "refactor_practice: the model-call cap cannot be read",
                "config/project.json agents.max_model_calls",
                "set it to a whole number of 0 or more, as the line above says",
            )
        except model_budget.SpendRefused as exc:
            return exit_codes.report(
                exit_codes.ExitCode.USAGE,
                "refactor_practice: " + exc.what,
                exc.on,
                exc.next_step,
            )
        chosen = model_budget.announce("refactor_practice", args.model)
        if chosen is not None:
            sys.stderr.write(chosen + "\n")

    try:
        report = refactor(
            args.practice,
            execute=args.execute,
            model=args.model,
            gate=args.gate,
            max_nodes=args.max_nodes,
            corpus=args.corpus,
            root=args.root,
            runtime=args.runtime,
            max_model_calls=args.max_nodes if args.execute else None,
        )
    except RunNotApproved as exc:
        what, on, next_step = exc.parts
        return exit_codes.report(
            exit_codes.ExitCode.USAGE, "refactor_practice: " + what, on, next_step
        )
    except CallCapReached as exc:
        what, on, next_step = model_budget.stopped(exc, "--max-nodes")
        return exit_codes.report(
            exit_codes.ExitCode.FAILURE, "refactor_practice: " + what, on, next_step
        )
    except (ChildTimedOut, ChildOutputTooLarge) as exc:
        # A tool the agent runs (a gate, a corpus query, the gated apply) was
        # ended at its configured limit; the message names the key.
        return exit_codes.report(
            exit_codes.ExitCode.FAILURE,
            "refactor_practice: a tool the agent runs was ended at its limit",
            str(exc),
            "find why the tool hung or flooded its output, or raise the key the "
            "message names",
        )
    except config_loader.ConfigError as exc:
        # A limit the model, the runtime or a tool child reads once the
        # agent starts (models.timeout_seconds, models.max_reply_bytes,
        # runtimes.max_steps, agents.tool_timeout_seconds,
        # agents.tool_max_output_bytes): refused before that call starts.
        return exit_codes.report(
            exit_codes.ExitCode.CONFIG,
            "refactor_practice: a setting the model or the runtime reads is refused",
            "; ".join(exc.lines),
            "set each key the line names inside its bound",
        )
    except ModelUnavailable as exc:
        # Absent, not broken: say so, write nothing, exit 0. A present model
        # that fails still raises -- that is a defect, not a missing tool.
        sys.stdout.write("refactor_practice: model unavailable (%s); skipping\n" % exc)
        return exit_codes.ExitCode.SUCCESS

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
    return exit_codes.ExitCode.SUCCESS


if __name__ == "__main__":
    exit_codes.finish(main())
