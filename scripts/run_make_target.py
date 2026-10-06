#!/usr/bin/env python3
"""
title: Run make target (the read-only gate runner)
kind: script
layer: n/a
summary: Deterministic doer — run a make target as a gate and report a structured pass/fail, but only a target whose effect label, closed over what it runs, falls inside config/project.json `make_targets.gate_effects`. It refuses an unknown, unlabelled or wider target, an extra argument that is not a NAME=VALUE variable named in `make_targets.gate_vars` with a one-word path-like value, a tree without git, and an allowlist scripts/child_env.py cannot build, all before make runs; it forwards a `make_targets.gate_vars` variable found in its own environment onto make's command line under the same one-word rule (an explicit one wins), because make and git get the allowlisted environment from scripts/child_env.py, never this one; it sets the gate-runner variable last so WRITE_GUARD refuses a [write] target; and it snapshots what git lists before and after (each path's porcelain status and content), failing a green run that changed it and naming the paths, and one whose tree cannot be re-read afterwards. The refactor loop (agents/practice_refactor, scripts/apply_refactor.py) and tests/integration/test_make_target_effects.py gate through it. Vendor-neutral, stdlib; it writes nothing itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_structure  # noqa: E402 — the one owner of the label grammar and policy
import child_env  # noqa: E402 — the environment make and git inherit

# A make target is a plain token — reject anything that could be a shell
# injection (the target reaches `make` as an argv element, never a shell string,
# but validating keeps callers honest and the intent auditable).
_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# The only extra argument a gate run accepts: a make variable. A flag could point
# make at another makefile (`-f`, `-C`) or add a goal whose label nobody read.
_VARIABLE_ARG = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
# ...and only one config/project.json `make_targets.gate_vars` names, with a value
# that is one path-like word. A recipe expands the value into a shell line, so a
# space, `;`, `$` or a quote would let a [local] target run a [write] one with the
# guard unset (measured: `PY=make deploy-apply RALPH= ; true` did). A leading
# `-`/`+`/`@` would become a make recipe prefix. The value still names a program
# the recipe runs; choosing it is the caller's, and the tree snapshot is the
# backstop for what that program does.
_GATE_VALUE = re.compile(r"^(?:[A-Za-z0-9_./~][A-Za-z0-9_./+,:@%~-]*)?$")
_MANIFEST = os.path.join("config", "project.json")

# (returncode, combined_output) — the shape a runner returns.
Runner = Callable[[Sequence[str], "str | None", int], "tuple[int, str]"]
# root -> {repo-relative path: digest} — what git lists, and each entry's content.
Snapshot = Callable[[str], "dict[str, str]"]


class NoGitError(Exception):
    """The directory is not inside a git work tree, so no before/after
    comparison of what git lists is possible and a read-only claim is unproven."""


def is_safe_target(name: str) -> bool:
    """True when `name` is a plain make-target token (no shell metacharacters).

    SAFE means well-formed, NOT read-only: `fmt` is a plain token and rewrites
    the tree. Read-only-ness is the effect label's claim (check_W), which
    run_target checks and then tests by snapshotting the tree.
    """
    return bool(_TARGET_RE.match(name or ""))


def _default_runner(
    cmd: Sequence[str], cwd: str | None, timeout: int
) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 — argv list, never a shell string
        list(cmd),
        cwd=cwd,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        env=child_env.build_child_env(),
    )
    return proc.returncode, proc.stdout


def _git(root: str, *argv: str) -> bytes:
    # The developer's global excludes file is ignored ON PURPOSE: a stray file a
    # personal ignore hides is still a change this machine's checkout would carry.
    try:
        proc = subprocess.run(  # noqa: S603 — argv list, never a shell string
            ["git", "-c", "core.excludesFile=" + os.devnull, *argv],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env.build_child_env(),
        )
    except OSError as exc:
        raise NoGitError("git is not runnable here (%s)" % exc) from exc
    if proc.returncode != 0:
        raise NoGitError(
            proc.stderr.decode("utf-8", "replace").strip()
            or "git exited %d" % proc.returncode
        )
    return proc.stdout


def _digest(path: str) -> str:
    if os.path.islink(path):
        return "link:" + os.readlink(path)
    if os.path.isfile(path):
        sha = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                sha.update(chunk)
        return "sha:" + sha.hexdigest()
    if os.path.isdir(path):
        return "dir"  # a nested repository git lists as one entry
    return "absent"


def tree_snapshot(root: str) -> dict[str, str]:
    """{repo-relative path: state} for every path `git status` lists under root
    (modified, staged, deleted, untracked — never ignored). The state is the
    two-letter porcelain status joined to the sha256 of the content, so a second
    edit to an already-dirty file and a change to the index alone both show.

    Raises NoGitError when root is not inside a git work tree."""
    top = _git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    raw = _git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = raw.decode("utf-8", "surrogateescape").split("\0")
    codes: dict[str, str] = {}
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        codes[path] = code
        # A rename/copy carries its source as the next field, in either column:
        # ` R` is a worktree rename (an intent-to-add file), `R ` a staged one.
        if "R" in code or "C" in code:
            codes[fields[i]] = code + "<"
            i += 1
    return {
        p: "%s|%s" % (codes[p], _digest(os.path.join(top, p))) for p in sorted(codes)
    }


def _refusal(target: str, why: str, effects: Sequence[str] = ()) -> dict[str, object]:
    return {
        "target": target,
        "ok": False,
        "returncode": None,
        "output": "run_make_target: refused `make %s`: %s\n" % (target, why),
        "effects": list(effects),
        "changed": [],
        "refused": why,
    }


def _policy(root: str) -> tuple[dict[str, object] | None, str | None]:
    path = os.path.join(root, _MANIFEST)
    if not os.path.isfile(path):
        return None, "%s is absent, so the make_targets policy is unknown" % _MANIFEST
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, "%s is unreadable (%s), so the make_targets policy is unknown" % (
            _MANIFEST,
            exc,
        )
    policy, errs = check_structure.make_targets_policy(manifest)
    if errs:
        return None, "%s: %s" % (_MANIFEST, "; ".join(errs))
    return policy, None


def run_target(
    target: str,
    cwd: str | None = None,
    timeout: int = 1800,
    extra: Sequence[str] | None = None,
    runner: Runner | None = None,
    snapshot: Snapshot | None = None,
) -> dict[str, object]:
    """Run ``make <target>`` as a read-only gate and return a structured result.

    The result holds target, ok, returncode, output, effects (the target's
    closed-over label), changed (sorted paths whose git-listed state differs
    after the run) and refused (None, or why the run never started). A refusal
    never calls the runner. ``extra`` are NAME=VALUE make variables, each named
    in ``make_targets.gate_vars`` with a one-word path-like value; a gate
    variable set in this process's environment and not in ``extra`` is
    forwarded the same way (make itself gets the allowlisted environment from
    scripts/child_env.py, never this one). The gate-runner variable is appended
    last, so a caller cannot unset it.
    ``runner`` and ``snapshot`` are injected for testing.
    Raises ValueError on a target name that is not a plain token.
    """
    if not is_safe_target(target):
        raise ValueError("unsafe make target: %r" % target)
    root = os.path.abspath(cwd or os.getcwd())
    extra = list(extra or [])
    for arg in extra:
        if not _VARIABLE_ARG.match(arg):
            return _refusal(
                target,
                "`%s` is not a NAME=VALUE make variable -- a gate run passes only "
                "variables, never a flag (`-f`/`-C` would run a makefile whose "
                "labels were never read) or another goal" % arg,
            )
    policy, why = _policy(root)
    if policy is None:
        return _refusal(target, str(why))
    allowed = list(policy["gate_vars"])  # type: ignore[call-overload]
    # A gate variable the caller's make set reaches this process only through the
    # environment; make's own child gets the allowlist, so it is forwarded here,
    # on the command line, under the same one-word rule. An explicit one wins.
    given = {arg.split("=", 1)[0] for arg in extra}
    for name in sorted(allowed):
        if name in given or name not in os.environ:
            continue
        if not _GATE_VALUE.match(os.environ[name]):
            return _refusal(
                target,
                "the environment variable %s=%r is not one path-like word -- "
                "forwarded to make it would be expanded into a shell line, where "
                "spaces, `;`, `$` or quotes could run a target whose label nobody "
                "read" % (name, os.environ[name]),
            )
        extra.append("%s=%s" % (name, os.environ[name]))
    for arg in extra:
        name, value = arg.split("=", 1)
        if name not in allowed:
            return _refusal(
                target,
                "`%s` is not one of make_targets.gate_vars [%s] -- a gate run sets "
                "no make control variable, guard or unattended variable, which could "
                "run what no label declares" % (name, ",".join(allowed)),
            )
        if not _GATE_VALUE.match(value):
            return _refusal(
                target,
                "`%s`'s value %r is not one path-like word -- a recipe expands it "
                "into a shell line, where spaces, `;`, `$` or quotes could run a "
                "target whose label nobody read" % (name, value),
            )
    effects = check_structure.target_effects(root)
    if target not in effects:
        return _refusal(
            target, "no rule named `%s` in this project's makefiles" % target
        )
    labels, why = effects[target]
    if labels is None:
        return _refusal(target, "cannot prove `make %s` read-only: %s" % (target, why))
    gate = list(policy["gate_effects"])  # type: ignore[call-overload]
    wider = [w for w in labels if w not in gate]
    if wider:
        return _refusal(
            target,
            "`make %s` is labelled [%s] (closed over what it runs), outside "
            "make_targets.gate_effects [%s] -- a gate run only runs what leaves the "
            "tree and shared state alone" % (target, ",".join(labels), ",".join(gate)),
            labels,
        )
    # Built once here so a malformed allowlist is a refusal before the tree is
    # touched; make and git rebuild it from the same file a moment later.
    try:
        child_env.build_child_env()
    except child_env.ChildEnvError as exc:
        return _refusal(
            target,
            "cannot start make or git without an allowlisted environment -- %s" % exc,
            labels,
        )
    snap = snapshot or tree_snapshot
    try:
        before = snap(root)
    except NoGitError as exc:
        return _refusal(
            target,
            "cannot prove a read-only run without git -- %s is not a git work tree "
            "(%s)" % (root, exc),
            labels,
        )
    cmd = ["make", target, *extra, "%s=1" % policy["gate_runner_var"]]
    try:
        code, output = (runner or _default_runner)(cmd, root, timeout)
    except subprocess.TimeoutExpired:
        code, output = (
            None,
            "run_make_target: `make %s` did not complete within %ss\n"
            % (
                target,
                timeout,
            ),
        )
    except (OSError, child_env.ChildEnvError) as exc:
        code, output = (
            None,
            "run_make_target: `make %s` did not complete: %s\n"
            % (
                target,
                exc,
            ),
        )
    try:
        after = snap(root)
    except (NoGitError, child_env.ChildEnvError) as exc:
        # The run may have broken git or the allowlist itself; either way its
        # read-only claim is unproven, so the verdict is red, never a crash.
        return {
            "target": target,
            "ok": False,
            "returncode": code,
            "output": "%s\nrun_make_target: cannot re-read the tree after `make %s`, "
            "so the run is not proven read-only: %s\n" % (output, target, exc),
            "effects": list(labels),
            "changed": [],
            "refused": None,
        }
    changed = sorted(
        p for p in set(before) | set(after) if before.get(p) != after.get(p)
    )
    if changed:
        output = (
            "%s\nrun_make_target: `make %s` changed the tree (what git lists): %s\n"
            % (
                output,
                target,
                ", ".join(changed),
            )
        )
    return {
        "target": target,
        "ok": code == 0 and not changed,
        "returncode": code,
        "output": output,
        "effects": list(labels),
        "changed": changed,
        "refused": None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: exit 0 green, 1 red or the tree changed, 2 refused (never run)."""
    ap = argparse.ArgumentParser(
        description="Run a read-only make target as a gate and report pass/fail."
    )
    ap.add_argument("target", help="make target (e.g. verify, check, lint, test)")
    ap.add_argument("--json", action="store_true", help="emit the result as JSON")
    ap.add_argument("--dir", default=None, help="run in this directory (default: cwd)")
    ap.add_argument(
        "--timeout", type=int, default=1800, help="seconds before giving up"
    )
    ap.add_argument(
        "--make-arg",
        action="append",
        default=[],
        dest="make_args",
        metavar="NAME=VALUE",
        help="extra make variable, repeatable (e.g. PY=.venv/bin/python)",
    )
    args = ap.parse_args(argv)

    if not is_safe_target(args.target):
        sys.stderr.write("run_make_target: unsafe target %r\n" % args.target)
        return 2
    result = run_target(
        args.target, cwd=args.dir, timeout=args.timeout, extra=args.make_args
    )
    if args.json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(str(result["output"]))
        verdict = (
            "REFUSED" if result["refused"] else ("PASS" if result["ok"] else "FAIL")
        )
        sys.stdout.write(
            "\nrun_make_target: `make %s` [%s] -> %s (rc=%s)\n"
            % (
                result["target"],
                ",".join(result["effects"]),  # type: ignore[arg-type]
                verdict,
                result["returncode"],
            )
        )
    if result["refused"]:
        return 2
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
