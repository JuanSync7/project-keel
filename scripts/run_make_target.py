#!/usr/bin/env python3
"""
title: Run make target (refactor gate doer)
kind: script
layer: n/a
summary: Deterministic doer — run a make target and report a structured pass/fail. The refactor loop (agents/practice_refactor) calls it to GATE every step on `make verify` (or the smallest sufficient target) before accepting a change, so a chunk is only "done" when the gate is green. Vendor-neutral, stdlib, safe to run twice.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence

# A make target is a plain token — reject anything that could be a shell
# injection (the target reaches `make` as an argv element, never a shell string,
# but validating keeps callers honest and the intent auditable).
_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# (returncode, combined_output) — the shape a runner returns.
Runner = Callable[[Sequence[str], "str | None", int], "tuple[int, str]"]


def is_safe_target(name: str) -> bool:
    """True when `name` is a plain make-target token (no shell metacharacters)."""
    return bool(_TARGET_RE.match(name or ""))


def _default_runner(cmd: Sequence[str], cwd: str | None, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 — argv list, never a shell string
        list(cmd), cwd=cwd, timeout=timeout,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return proc.returncode, proc.stdout


def run_target(target: str, cwd: str | None = None, timeout: int = 1800,
               extra: Sequence[str] | None = None,
               runner: Runner | None = None) -> dict[str, object]:
    """Run ``make <target>`` and return a structured result.

    ``extra`` are additional make args/variables (e.g. ``["PY=.venv/bin/python"]``).
    ``runner`` is injected for testing — it defaults to a real subprocess; a test
    passes a fake that returns a canned ``(returncode, output)``.
    """
    if not is_safe_target(target):
        raise ValueError("unsafe make target: %r" % target)
    run = runner or _default_runner
    cmd = ["make", target, *(extra or [])]
    code, output = run(cmd, cwd, timeout)
    return {"target": target, "ok": code == 0, "returncode": code, "output": output}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Run a make target and report pass/fail — the refactor loop's gate.")
    ap.add_argument("target", help="make target (e.g. verify, check, lint, typecheck, test)")
    ap.add_argument("--json", action="store_true", help="emit the result as JSON")
    ap.add_argument("--dir", default=None, help="run in this directory (default: cwd)")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds before giving up")
    ap.add_argument("--make-arg", action="append", default=[], dest="make_args",
                    metavar="ARG", help="extra make arg/var, repeatable (e.g. PY=.venv/bin/python)")
    args = ap.parse_args(argv)

    if not is_safe_target(args.target):
        sys.stderr.write("run_make_target: unsafe target %r\n" % args.target)
        return 2
    try:
        result = run_target(args.target, cwd=args.dir, timeout=args.timeout,
                            extra=args.make_args)
    except subprocess.TimeoutExpired:
        result = {"target": args.target, "ok": False, "returncode": None,
                  "output": "timed out after %ss" % args.timeout}

    if args.json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(str(result["output"]))
        sys.stdout.write("\nrun_make_target: `make %s` -> %s (rc=%s)\n"
                         % (result["target"], "PASS" if result["ok"] else "FAIL",
                            result["returncode"]))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
