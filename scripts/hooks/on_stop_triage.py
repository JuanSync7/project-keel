#!/usr/bin/env python3
"""
title: on-stop triage hook
kind: script
layer: n/a
summary: Thin event-hook entrypoint — hands a payload to the triage agent. `--execute` is first held to config/project.json `agents.max_model_calls` (scripts/model_budget.py): triage makes one model call, so a cap of 0 refuses the run (exit 2) and a cap the config cannot give is exit 14, both before the agent runs; with no --model it names on stderr the registry default it will use. The one call goes through a models.CountedModel of 1, and a second is never made but is a failure (exit 1) naming the count. An unavailable model is a stated skip at exit 0.
"""

from __future__ import annotations

import argparse
import os
import sys

# A *doer* invoked by some trigger (git hook, CI step, agent-tool hook).
# The trigger is a thin adapter that only says "run this on event X".
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)  # make top-level `agents`/`models` importable
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import config_loader  # noqa: E402
import model_budget  # noqa: E402
from agents.triage import triage  # noqa: E402  (after sys.path setup)
from exit_codes import ExitCode, finish, report  # noqa: E402
from models import CallCapReached, ModelUnavailable  # noqa: E402

# triage sends exactly one prompt per run (evals/_doers.py prompt_sha256 holds
# its doer to one), so one call is the run's whole bound.
_CALLS = 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[-1])
    ap.add_argument(
        "payload", nargs="?", default="-", help="event payload, or '-' to read stdin"
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="actually run the model (default: dry-run preview)",
    )
    ap.add_argument("--model", default=None, help="model name from models/ registry")
    args = ap.parse_args(argv)
    if args.execute:
        # Held to the cap before the agent runs, so a refused run calls no
        # model and writes nothing; a dry run calls none, so it is never held.
        try:
            model_budget.approve(_CALLS, model_budget.cap(ROOT), None)
        except config_loader.ConfigError:
            return report(
                ExitCode.CONFIG,
                "on_stop_triage: the model-call cap cannot be read",
                "config/project.json agents.max_model_calls",
                "set it to a whole number of 0 or more, as the line above says",
            )
        except model_budget.SpendRefused as exc:
            return report(
                ExitCode.USAGE,
                "on_stop_triage: " + exc.what,
                exc.on,
                exc.next_step,
            )
        chosen = model_budget.announce("on_stop_triage", args.model)
        if chosen is not None:
            sys.stderr.write(chosen + "\n")
    payload = sys.stdin.read() if args.payload == "-" else args.payload
    try:
        print(
            triage(
                payload,
                execute=args.execute,
                model=args.model,
                max_model_calls=_CALLS if args.execute else None,
            )
        )
    except CallCapReached as exc:
        what, on, next_step = model_budget.stopped(exc, None)
        return report(ExitCode.FAILURE, "on_stop_triage: " + what, on, next_step)
    except ModelUnavailable as exc:
        # Absent, not broken: a hook that fires where no model runs must say so
        # and step aside (exit 0), never fail the event it was attached to.
        print(f"on_stop_triage: model unavailable ({exc}); skipping")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
