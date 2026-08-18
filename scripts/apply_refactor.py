#!/usr/bin/env python3
"""
title: Apply a gated refactor (refactor doer)
kind: script
layer: n/a
summary: Deterministic doer — apply a proposed set of file edits ATOMICALLY, run a gate (a make target), and ROLL BACK every file if the gate fails. The refactor loop (agents/practice_refactor) proposes one bounded, named-practice edit at a time; this doer is the safety net that keeps the tree green — a chunk is accepted only if the gate stays green, else the change is reverted. Vendor-neutral, stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence

# gate_runner(gate, cwd, timeout) -> (ok, combined_output)
GateRunner = Callable[[str, str, int], "tuple[bool, str]"]


class RefactorError(Exception):
    """A refactor could not be applied as specified (bad spec / non-unique match).

    Raised BEFORE any file is written, so a malformed spec never leaves a
    half-applied tree.
    """


def apply_one(text: str, find: str, replace: str) -> str:
    """Apply a single search/replace to ``text``. ``find`` must occur EXACTLY once
    so a refactor edit is unambiguous; raises RefactorError on zero or many."""
    count = text.count(find)
    if count == 0:
        raise RefactorError("find text not present")
    if count > 1:
        raise RefactorError("find text is ambiguous (%d matches)" % count)
    return text.replace(find, replace, 1)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def plan_edits(spec: dict[str, object], root: str) -> list[tuple[str, str, str]]:
    """Validate the spec against the tree WITHOUT writing. Returns
    ``[(path, original_text, new_text)]``. Multiple edits to one file compose in
    order. Raises RefactorError on any problem (so callers can dry-run safely)."""
    edits = spec.get("edits")
    if not isinstance(edits, list) or not edits:
        raise RefactorError("spec has no 'edits' list")
    originals: dict[str, str] = {}
    working: dict[str, str] = {}
    order: list[str] = []
    for i, e in enumerate(edits):
        if not isinstance(e, dict) or "file" not in e:
            raise RefactorError("edit %d missing 'file'" % i)
        path = os.path.join(root, str(e["file"]))
        # Never write outside the repo root — a spec path must not escape it.
        real_root = os.path.realpath(root)
        real_path = os.path.realpath(path)
        if real_path != real_root and not real_path.startswith(real_root + os.sep):
            raise RefactorError("edit %d: path escapes root: %s" % (i, e["file"]))
        if path not in working:
            if not os.path.isfile(path):
                raise RefactorError("edit %d: file does not exist: %s" % (i, e["file"]))
            originals[path] = working[path] = _read(path)
            order.append(path)
        if "content" in e:  # full-file replacement
            working[path] = str(e["content"])
        elif "find" in e and "replace" in e:
            working[path] = apply_one(working[path], str(e["find"]), str(e["replace"]))
        else:
            raise RefactorError("edit %d needs 'find'+'replace' or 'content'" % i)
    return [(p, originals[p], working[p]) for p in order]


def _make_gate(gate: str, cwd: str, timeout: int) -> tuple[bool, str]:
    proc = subprocess.run(  # noqa: S603 — argv list, never a shell string
        ["make", gate],
        cwd=cwd,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    return proc.returncode == 0, proc.stdout


def apply_and_gate(
    spec: dict[str, object],
    root: str,
    gate: str | None = None,
    timeout: int = 1800,
    gate_runner: GateRunner | None = None,
) -> dict[str, object]:
    """Apply the planned edits, run the gate, and roll back ALL files if it fails.

    ``gate`` defaults to the spec's ``gate`` then ``"verify"``; ``"none"`` skips
    the gate (apply only). ``gate_runner`` is injected for testing. A gate that
    RAISES (a timeout, a hang, a killed ``make`` subprocess) is treated as red, so
    the rollback still fires -- a non-returning gate must never leave an ungated
    write behind. Returns a result dict describing what happened; the tree is left
    green either way (accepted, or reverted to the originals). The one window it
    cannot itself undo is a hard external kill (SIGKILL/OOM) of *this* process
    mid-write -- that partial edit is surfaced by the next gate run, never
    silently kept as done.
    """
    planned = plan_edits(spec, root)  # may raise before any write
    gate = gate or str(spec.get("gate") or "verify")

    for path, _old, new in planned:  # apply
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)

    if gate == "none":
        ok, output = True, "(no gate requested)"
    else:
        # A gate that times out / hangs / is killed never returns a verdict; treat
        # any such failure as RED so the rollback below still fires. Preserve the
        # cause in the reported output rather than swallowing it.
        try:
            ok, output = (gate_runner or _make_gate)(gate, root, timeout)
        except (subprocess.SubprocessError, OSError) as exc:
            ok, output = False, "gate did not complete: %r" % exc

    if not ok:
        for path, old, _new in planned:  # ROLL BACK on failure
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(old)

    return {
        "practice": spec.get("practice", ""),
        "gate": gate,
        "applied": ok,
        "rolled_back": not ok,
        "files": [os.path.relpath(p, root) for p, _o, _n in planned],
        "gate_output": output,
    }


def _load_spec(path: str | None) -> dict[str, object]:
    text = sys.stdin.read() if path in (None, "-") else _read(path)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise RefactorError("spec must be a JSON object")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Apply a proposed refactor and roll it back unless a make gate stays green."
    )
    ap.add_argument(
        "--spec",
        default="-",
        help="path to the JSON edit spec, or '-' for stdin (default)",
    )
    ap.add_argument(
        "--root", default=".", help="repo root the edit paths are relative to"
    )
    ap.add_argument(
        "--gate",
        default=None,
        help="make target to gate on (default: spec.gate or 'verify'; 'none' to skip)",
    )
    ap.add_argument("--timeout", type=int, default=1800, help="gate timeout in seconds")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="validate + show the planned files, write nothing",
    )
    ap.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = ap.parse_args(argv)

    try:
        spec = _load_spec(args.spec)
        if args.dry_run:
            planned = plan_edits(spec, args.root)
            result: dict[str, object] = {
                "practice": spec.get("practice", ""),
                "dry_run": True,
                "files": [os.path.relpath(p, args.root) for p, _o, _n in planned],
            }
        else:
            result = apply_and_gate(
                spec, args.root, gate=args.gate, timeout=args.timeout
            )
    except (RefactorError, ValueError, OSError, json.JSONDecodeError) as exc:
        if args.json:
            json.dump({"error": str(exc)}, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            sys.stderr.write("apply_refactor: %s\n" % exc)
        return 2

    if args.json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        if result.get("dry_run"):
            sys.stdout.write(
                "apply_refactor: would edit %s\n" % ", ".join(result["files"])
            )  # type: ignore[arg-type]
        else:
            verb = "applied" if result["applied"] else "ROLLED BACK (gate failed)"
            sys.stdout.write(
                "apply_refactor: %s [%s] gate=%s -> %s\n"
                % (
                    ", ".join(result["files"]),
                    result["practice"],  # type: ignore[arg-type]
                    result["gate"],
                    verb,
                )
            )
    if result.get("dry_run"):
        return 0
    return 0 if result["applied"] else 1


if __name__ == "__main__":
    sys.exit(main())
