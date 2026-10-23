#!/usr/bin/env python3
"""
title: Apply a gated refactor (refactor doer)
kind: script
layer: n/a
summary: Deterministic doer — apply a proposed set of file edits ATOMICALLY, run a gate (a make target, through scripts/run_make_target.py, so only a target labelled read-only runs and a gate run that changes the tree is red), and ROLL BACK every file if the gate fails or is refused. The refactor loop (agents/practice_refactor) proposes one bounded, named-practice edit at a time; this doer is the safety net that keeps the tree green — a chunk is accepted only if the gate stays green, else the change is reverted. An edit may never reach the code that judges it: before any write, so a dry run sees every refusal, plan_edits refuses an edit to a path the root's config/project.json `agents` block protects (read through scripts/config_loader.py: `protected_paths` covers a path and everything under it, `protected_names` a file name or a glob over one in any directory, `editable_names` carves a name or glob back out of a protected path; a protected name refuses, else an editable name allows, else a protected path refuses), judged on case-folded path parts both as written and after resolving symlinks, and refuses outright an absolute path, a `..` part, a path outside the root and a file with more than one hard link; beneath the list it refuses a file git does not track (scripts/git_tree.py `tracked`), so git's own state, an ignored file and the toolchain the gate runs stay out of reach where no entry names them, and a root where git cannot say is refused too; edits are planned by the resolved path, so two spellings of one file compose as one; each refusal names the edit, the path and the protecting key with its reason. A policy it cannot use (absent, malformed, empty, or not protecting config/project.json itself) is a config fault, ExitCode.CONFIG, and nothing is written. The model never chooses the gate: the gate is the caller's `--gate` (default `verify`; `none`, no gate, is a human caller's flag, which the agents' own baseline run_make_target refuses), and a spec is a closed vocabulary (`practice`, `edits`; an edit's `file`, `find`, `replace`, `content`), so a spec naming a `gate` or any other key is refused before any write. Repeated `--allow <file>` binds the run to those files, judged on realpath, so an agent that passes the chunk it asked about cannot have the model edit another. Vendor-neutral, stdlib.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_idempotence.py
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePosixPath
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config_loader  # noqa: E402 — the one reader of config/project.json
import git_tree  # noqa: E402 — the one definition of what git tracks
import run_make_target  # noqa: E402 — the read-only gate runner; tests patch it here
from exit_codes import ExitCode, finish, report  # noqa: E402

# gate_runner(gate, cwd, timeout) -> (ok, combined_output); a timeout of None
# leaves the limit to config/project.json make_targets.gate_timeout_seconds.
GateRunner = Callable[[str, str, "int | None"], "tuple[bool, str]"]


class RefactorError(Exception):
    """A refactor could not be applied as specified (bad spec / non-unique match).

    Raised BEFORE any file is written, so a malformed spec never leaves a
    half-applied tree.
    """


# A spec is model-written, so its shape is a closed vocabulary: a key outside
# it is refused rather than ignored, because an ignored key is one the model
# may believe took effect. `gate` is refused by name: see _GATE_KEY.
_SPEC_KEYS = frozenset({"practice", "edits"})
_EDIT_KEYS = frozenset({"file", "find", "replace", "content"})
# The gate is the caller's --gate, never the spec's: a spec that chose its own
# gate would let the model choose its own judge, and `"gate": "none"` once
# applied with no gate at all.
_GATE_KEY = "gate"

_PATHS_KEY = ("agents", "protected_paths")
_NAMES_KEY = ("agents", "protected_names")
_EDITABLE_KEY = ("agents", "editable_names")

# One rule: (case-folded parts, or a case-folded name as a 1-tuple; the key as
# config/project.json spells it; its reason).
Rule = tuple[tuple[str, ...], str, str]


class EditPolicy(NamedTuple):
    """What an agent edit may not reach, read from config/project.json `agents`.

    Each field is a tuple of rules sorted by key, so the rule a refusal names
    does not depend on the order the file lists them in."""

    protected_paths: tuple[Rule, ...]
    protected_names: tuple[Rule, ...]
    editable_names: tuple[Rule, ...]


def _fold(parts: Sequence[str]) -> tuple[str, ...]:
    # Case-folded because make reads makefile as well as Makefile, and a
    # case-insensitive filesystem opens scripts/x.py as SCRIPTS/x.py: on a
    # case-sensitive one this over-protects a distinct name, the fail-closed side.
    return tuple(part.casefold() for part in parts)


def _rules(mapping: Mapping[str, str], split: bool) -> tuple[Rule, ...]:
    return tuple(
        (_fold(PurePosixPath(key).parts) if split else (key.casefold(),), key, reason)
        for key, reason in sorted(mapping.items())
    )


def _covers(rule_parts: tuple[str, ...], parts: tuple[str, ...]) -> bool:
    return parts[: len(rule_parts)] == rule_parts


def load_policy(root: str) -> EditPolicy:
    """The edit policy of the project at *root*, from its config/project.json
    `agents` block through scripts/config_loader.py.

    Raises config_loader.ConfigError when the file or block cannot be used, and
    WrongValue when `protected_paths` leaves config/project.json uncovered: a
    policy that does not protect itself could be edited away by the edit it
    is meant to refuse."""
    loaded = config_loader.read(root)
    values = config_loader.resolve(
        loaded,
        config_loader.rows(_EDITABLE_KEY, _NAMES_KEY, _PATHS_KEY),
        config_loader.CONFIG_FILE,
    )
    policy = EditPolicy(
        protected_paths=_rules(values[_PATHS_KEY], split=True),
        protected_names=_rules(values[_NAMES_KEY], split=False),
        editable_names=_rules(values[_EDITABLE_KEY], split=False),
    )
    own = _fold(PurePosixPath(config_loader.CONFIG_FILE.replace(os.sep, "/")).parts)
    if not any(_covers(parts, own) for parts, _key, _why in policy.protected_paths):
        where = config_loader.CONFIG_FILE
        raise config_loader.WrongValue(
            where,
            [
                "%s: agents.protected_paths covers no path holding %s; accepted: "
                "a map with an entry covering it (such as `config`), so an agent "
                "edit cannot remove the policy itself" % (where, where)
            ],
        )
    return policy


def _named(rules: tuple[Rule, ...], name: str) -> Rule | None:
    """The rule for file *name*: the one spelled exactly as *name* when there
    is one, else the first by key among those whose key, a name or a glob over
    one (`*.test.*`), matches it case-folded."""
    folded = name.casefold()
    # fnmatchcase on folded text, never fnmatch: fnmatch folds case only on a
    # case-insensitive OS, so one policy would protect differently per host.
    matches = [rule for rule in rules if fnmatch.fnmatchcase(folded, rule[0][0])]
    exact = [rule for rule in matches if rule[1] == name]
    return (exact or matches or [None])[0]


def protected_by(relparts: Sequence[str], policy: EditPolicy) -> tuple[str, str] | None:
    """(the rule key, its reason) that protects the repo-relative path whose
    parts are *relparts*, or None when an agent may edit it.

    A protected name refuses, else an editable name allows, else a protected
    path refuses; the comparison is on case-folded parts only."""
    parts = tuple(relparts)
    if not parts:
        return None
    name = _named(policy.protected_names, parts[-1])
    if name is not None:
        return "agents.protected_names.%s" % name[1], name[2]
    if _named(policy.editable_names, parts[-1]) is not None:
        return None
    folded = _fold(parts)
    for rule_parts, key, reason in policy.protected_paths:
        if _covers(rule_parts, folded):
            return "agents.protected_paths.%s" % key, reason
    return None


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


def _refuse_protected(
    index: int, shown: object, parts: Sequence[str], policy: EditPolicy
) -> None:
    rule = protected_by(parts, policy)
    if rule is not None:
        raise RefactorError(
            "edit %d: %s is protected by %s (%s); an agent edit may not reach "
            "the code that judges it" % (index, shown, rule[0], rule[1])
        )


def _refuse_spec_keys(spec: Mapping[str, object]) -> None:
    if _GATE_KEY in spec:
        raise RefactorError(
            "spec names a gate (%r); the gate is the caller's --gate, never the "
            "spec's" % (spec[_GATE_KEY],)
        )
    unknown = sorted(set(spec) - _SPEC_KEYS)
    if unknown:
        raise RefactorError(
            "spec has unknown key(s) %s; accepted: %s"
            % (", ".join(repr(k) for k in unknown), ", ".join(sorted(_SPEC_KEYS)))
        )


def _refuse_untracked(index: int, shown: str, real_root: str, resolved: str) -> None:
    """Refuse an edit to a file git does not track. The deny list names the
    judges a project ships; what git does not track is judge-shaped by default:
    git's own state (`.git/config` sets core.fsmonitor, which runs inside the
    gate's own `git status`), the toolchain the gate runs (.venv, node_modules)
    and any ignored file. An agent refactors tracked source and nothing else."""
    try:
        known = git_tree.tracked(real_root, [resolved])
    except (git_tree.NoGitError, git_tree.GitFailedError) as exc:
        raise RefactorError(
            "edit %d: %s: git cannot say whether it is tracked (%s); an agent "
            "edits only a file git tracks" % (index, shown, exc)
        ) from exc
    if not known:
        raise RefactorError(
            "edit %d: %s is not a file git tracks; an agent edits only tracked "
            "source, never git's own state, an ignored file or the toolchain "
            "the gate runs" % (index, shown)
        )


def _bound(root: str, allow: Sequence[str] | None) -> frozenset[str] | None:
    """The realpaths of the files *allow* binds the run to, or None for no
    binding (the deny floor alone)."""
    if allow is None:
        return None
    return frozenset(os.path.realpath(os.path.join(root, a)) for a in allow)


def plan_edits(
    spec: dict[str, object],
    root: str,
    allow: Sequence[str] | None = None,
    policy: EditPolicy | None = None,
) -> list[tuple[str, str, str]]:
    """Validate the spec against the tree WITHOUT writing. Returns
    ``[(path, original_text, new_text)]``. Multiple edits to one file compose in
    order. Raises RefactorError on any problem (so callers can dry-run safely),
    and config_loader.ConfigError when *policy* is None and the root's edit
    policy cannot be loaded.

    *allow*, when given, binds the run to those repo-relative files: an edit
    whose realpath is none of theirs is refused, and an empty list refuses
    every edit."""
    _refuse_spec_keys(spec)
    edits = spec.get("edits")
    if not isinstance(edits, list) or not edits:
        raise RefactorError("spec has no 'edits' list")
    if policy is None:
        policy = load_policy(root)
    bound = _bound(root, allow)
    real_root = os.path.realpath(root)
    # Keyed on the resolved path, so `src/m.py` and `./src/m.py` are one file
    # whose edits compose, not two planned from one original, the second
    # write dropping the first.
    originals: dict[str, str] = {}
    working: dict[str, str] = {}
    order: list[str] = []
    for i, e in enumerate(edits):
        if not isinstance(e, dict) or "file" not in e:
            raise RefactorError("edit %d missing 'file'" % i)
        unknown = sorted(set(e) - _EDIT_KEYS)
        if unknown:
            raise RefactorError(
                "edit %d: unknown key %s; accepted: %s"
                % (
                    i,
                    ", ".join(repr(k) for k in unknown),
                    ", ".join(sorted(_EDIT_KEYS)),
                )
            )
        rel = e["file"]
        if not isinstance(rel, str) or not rel:
            raise RefactorError("edit %d: 'file' must be a non-empty string" % i)
        # A spelling, not a location, is judged first: `src/../scripts/x.py`
        # and an absolute path inside the root reach the same files as a plain
        # relative path, so they buy an agent nothing but a way round a rule.
        written = PurePosixPath(rel)
        if os.path.isabs(rel) or ".." in written.parts or not written.parts:
            raise RefactorError(
                "edit %d: %s: a path with '..' or an absolute path is refused"
                % (i, rel)
            )
        # Never write outside the repo root — a spec path must not escape it.
        real_path = os.path.realpath(os.path.join(root, rel))
        if real_path != real_root and not real_path.startswith(real_root + os.sep):
            raise RefactorError("edit %d: path escapes root: %s" % (i, rel))
        resolved = os.path.relpath(real_path, real_root)
        path = os.path.join(root, resolved)
        # Judged as written and again after resolving links, and both must
        # pass: CLAUDE.md is a symlink to AGENT.md, so a link is how an
        # editable name reaches a protected file. Before the existence check,
        # so a new file under a protected directory names its rule.
        _refuse_protected(i, rel, written.parts, policy)
        _refuse_protected(i, rel, PurePosixPath(resolved).parts, policy)
        # The model writes edits[].file, so a caller that names the one chunk
        # it asked about (--allow) takes the choice of file away from it.
        if bound is not None and real_path not in bound:
            raise RefactorError(
                "edit %d: %s is not a file this run was bound to (%s)"
                % (
                    i,
                    rel,
                    " ".join("--allow %s" % a for a in allow or ())
                    or "no --allow file",
                )
            )
        if path not in working:
            if not os.path.isfile(path):
                raise RefactorError("edit %d: file does not exist: %s" % (i, rel))
            # A hard link shares one inode under two names, and realpath sees
            # neither name as the other, so an editable name linked to a
            # protected file would pass both judgements above.
            links = os.stat(path).st_nlink
            if links > 1:
                raise RefactorError(
                    "edit %d: %s has %d hard links; one may be a protected file"
                    % (i, rel, links)
                )
            _refuse_untracked(i, rel, real_root, resolved)
            originals[path] = working[path] = _read(path)
            order.append(path)
        if "content" in e:  # full-file replacement
            working[path] = str(e["content"])
        elif "find" in e and "replace" in e:
            working[path] = apply_one(working[path], str(e["find"]), str(e["replace"]))
        else:
            raise RefactorError("edit %d needs 'find'+'replace' or 'content'" % i)
    return [(p, originals[p], working[p]) for p in order]


def _read_only_gate(gate: str, cwd: str, timeout: int | None) -> tuple[bool, str]:
    """The default gate: scripts/run_make_target.py, as (ok, output).

    A refusal (a target labelled wider than a gate may run, no git, no policy)
    and a green run that changed the tree are both red, so the caller rolls the
    edit back; the changed paths are appended so the reader sees why."""
    res = run_make_target.run_target(gate, cwd, timeout)
    output = str(res["output"])
    changed = list(res.get("changed") or [])  # type: ignore[call-overload]
    if changed:
        output += "".join("\nchanged: %s" % path for path in changed)
    return bool(res["ok"]), output


def apply_and_gate(
    spec: dict[str, object],
    root: str,
    gate: str = "verify",
    timeout: int | None = None,
    gate_runner: GateRunner | None = None,
    allow: Sequence[str] | None = None,
    policy: EditPolicy | None = None,
) -> dict[str, object]:
    """Apply the planned edits, run the gate, and roll back ALL files if it fails.

    ``gate`` is the caller's and only the caller's (default ``"verify"``); a
    spec naming one is refused, and an empty gate raises RefactorError.
    ``"none"`` skips the gate (apply only) and is for a human caller: the
    agents' baseline run_make_target refuses it. ``allow`` binds the run to
    those files (see plan_edits). ``timeout`` is the gate's limit in seconds; None
    leaves it to config/project.json ``make_targets.gate_timeout_seconds``.
    ``gate_runner`` is injected for testing. A gate that
    RAISES -- any exception: a timeout, a hang, a killed ``make`` subprocess, an
    allowlist that cannot be built -- is treated as red, so
    the rollback still fires -- a non-returning gate must never leave an ungated
    write behind. Returns a result dict describing what happened; the tree is left
    green either way (accepted, or reverted to the originals). The one window it
    cannot itself undo is a hard external kill (SIGKILL/OOM) of *this* process
    mid-write -- that partial edit is surfaced by the next gate run, never
    silently kept as done.
    """
    if not gate:
        raise RefactorError("no gate given")
    planned = plan_edits(spec, root, allow, policy)  # may raise before any write

    for path, _old, new in planned:  # apply
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)

    if gate == "none":
        ok, output = True, "(no gate requested)"
    else:
        # A gate that times out / hangs / is killed / cannot build its child
        # environment never returns a verdict; treat ANY raise as RED so the
        # rollback below still fires -- a list of expected types once let a
        # ChildEnvError skip it and keep an ungated write. The cause is kept in
        # the reported output (and the result says rolled_back), not swallowed.
        try:
            ok, output = (gate_runner or _read_only_gate)(gate, root, timeout)
        except Exception as exc:  # noqa: BLE001 — any raise is red; cause reported
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
        default="verify",
        help="Make target to gate on (default: verify); none skips the gate and "
        "is for a human caller only, never an agent",
    )
    ap.add_argument(
        "--allow",
        action="append",
        help="A file this run may edit, repeatable; an edit to any other file is "
        "refused before any write",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        help="gate timeout in seconds (default: config/project.json "
        "make_targets.gate_timeout_seconds)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="validate + show the planned files, write nothing",
    )
    ap.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = ap.parse_args(argv)
    fault = (
        None
        if args.timeout is None
        else run_make_target.limit_fault(run_make_target.LIMIT_KEYS[0], args.timeout)
    )
    if fault is not None:
        return report(
            ExitCode.USAGE,
            "apply_refactor: --timeout must be %s seconds" % fault,
            "--timeout %s" % run_make_target.shown_value(args.timeout),
            "give a whole number of seconds in that range, or leave --timeout out "
            "to use config/project.json make_targets.gate_timeout_seconds",
        )

    try:
        spec = _load_spec(args.spec)
        if args.dry_run:
            planned = plan_edits(spec, args.root, allow=args.allow)
            result: dict[str, object] = {
                "practice": spec.get("practice", ""),
                "dry_run": True,
                "files": [os.path.relpath(p, args.root) for p, _o, _n in planned],
            }
        else:
            result = apply_and_gate(
                spec, args.root, gate=args.gate, timeout=args.timeout, allow=args.allow
            )
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "apply_refactor: the edit policy in config/project.json `agents` "
            "could not be used",
            str(exc),
            "fix the key the message names; nothing was changed",
        )
    except (RefactorError, ValueError, OSError, json.JSONDecodeError) as exc:
        if args.json:
            json.dump({"error": str(exc)}, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        return report(
            ExitCode.USAGE,
            "apply_refactor: the edit spec was refused and nothing was changed",
            str(exc),
            "correct the spec and run it again",
        )

    # Joined once so the pragma sits ON the line it silences: `ruff format`
    # carried both of these off their expressions during the corpus
    # reformat, and RUF100 is deferred, so nothing reported the orphans.
    files = ", ".join(result["files"])  # type: ignore[arg-type]
    if args.json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif result.get("dry_run"):
        sys.stdout.write("apply_refactor: would edit %s\n" % files)
    else:
        verb = "applied" if result["applied"] else "ROLLED BACK (gate failed)"
        sys.stdout.write(
            "apply_refactor: %s [%s] gate=%s -> %s\n"
            % (files, result["practice"], result["gate"], verb)
        )
    if result.get("dry_run") or result["applied"]:
        return ExitCode.SUCCESS
    return report(
        ExitCode.FAILURE,
        "apply_refactor: the gate failed and every edit was rolled back",
        "`make %s` after editing %s" % (result["gate"], files),
        "read the gate's output, correct the spec and run it again",
    )


if __name__ == "__main__":
    finish(main())
