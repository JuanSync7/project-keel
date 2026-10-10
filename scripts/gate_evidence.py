#!/usr/bin/env python3
"""
title: Gate evidence — run a gate's goals and write its evidence record
kind: script
layer: n/a
summary: The driver a gate recipe runs as `gate_evidence.py --gate <token> -- <make> <goal>...`. It runs each goal as its own make, in order, with the allowlisted environment from scripts/child_env.py and the outer make's flags and command-line variables as argv; stops at the first failing goal unless MAKEFLAGS carries k; and writes one canonical JSON record to `<config/project.json evidence.dir>/<gate>.json`, shaped by the JSON Schema `evidence.schema` names, which alone owns `schema_version`. The record names the commit, whether the tree was dirty and a digest of what git lists (scripts/git_tree.py), each goal's result and exit code, the test counts from pytest's own junit report, and every scripts/check_structure.py finding. It holds no clock, duration, host, user or absolute path, so a rerun on the same tree writes the same bytes. It fails closed: a red placeholder is written before the first goal, so an interrupted run never leaves an earlier green record standing; a failing goal's exit code passes through; zero tests, no report, a failed or errored test in pytest's report (a goal that exited 0 anyway, as under `make -i`), a tree changed during the run, checks that could not run and a crash of the writer itself are each a red record and exit 3; zero goals, a malformed gate or goal, a bad evidence block and a record or report path git does not ignore are refused with exit 2 before any goal runs; an interrupt exits 130. Under `make -n`, `-q` or `-t` it runs the goals with that flag and writes nothing. It is not a general gate runner (scripts/run_make_target.py is) and keeps no history: each run replaces the file whole.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_gate_evidence_record.py
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no walrus,
# no evaluated `list[str]` or `X | None` annotations, and only bare scripts/
# siblings that keep the same rule (check_structure, child_env, git_tree). A `make
# verify` whose PY is older than requires-python must still run this writer, so the
# record it leaves is red rather than an earlier green one
# (tests/integration/test_gate_scope.py `_old_python_safe`).

import argparse
import json
import os
import re
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_structure  # noqa: E402 — the one owner of the check list
import child_env  # noqa: E402 — the environment every goal inherits
import git_tree  # noqa: E402 — the one definition of what git lists

_MANIFEST = os.path.join("config", "project.json")
# The gate names the record's file, so it may never climb out of evidence.dir.
_GATE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# A goal names its junit file and reaches make as an argv word: a plain make
# target token, the same shape scripts/run_make_target.py accepts.
_GOAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# The closed vocabulary of why a record is red; the schema's `reason` enum
# mirrors it (tests/unit/scripts/test_gate_evidence.py holds them equal).
REASONS = (
    "checks-unavailable",
    "incomplete",
    "no-test-report",
    "target-failed",
    "tests-failed",
    "tree-changed",
    "writer-error",
    "zero-targets",
    "zero-tests",
)
# MAKEFLAGS' single-letter word: n, q and t make a run that must not write; k
# keeps going after a failing goal.
_DRY_LETTERS = "nqt"
# The jobserver's descriptors name pipes this process does not pass on; a
# sub-make handed them would warn and run serially anyway.
_JOBSERVER = ("--jobserver-auth=", "--jobserver-fds=")
# The record's exit when every goal passed but the evidence is red.
_RED_EVIDENCE = 3
_REFUSED = 2
_INTERRUPTED = 130


class EvidenceConfigError(Exception):
    """config/project.json `evidence` or the schema it names cannot be used."""


def load_policy(root):
    """{dir, schema, schema_version} from config/project.json `evidence`, the
    version read from the schema's `properties.schema_version.const`, its only
    owner. Raises EvidenceConfigError naming the key at fault."""
    try:
        with open(os.path.join(root, _MANIFEST), encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        raise EvidenceConfigError("%s: unreadable (%s)" % (_MANIFEST, exc)) from exc
    block = manifest.get("evidence") if isinstance(manifest, dict) else None
    if not isinstance(block, dict):
        raise EvidenceConfigError(
            "%s: no `evidence` object (keys dir and schema)" % _MANIFEST
        )
    for key in ("dir", "schema"):
        value = block.get(key)
        if not isinstance(value, str) or not value:
            raise EvidenceConfigError(
                "%s: evidence.%s must be a non-empty string" % (_MANIFEST, key)
            )
        parts = value.replace("\\", "/").split("/")
        if os.path.isabs(value) or value.startswith("/") or ".." in parts:
            raise EvidenceConfigError(
                "%s: evidence.%s must be a path inside the repository, got %r"
                % (_MANIFEST, key, value)
            )
    schema_path = os.path.join(root, block["schema"])
    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, ValueError) as exc:
        raise EvidenceConfigError(
            "%s: evidence.schema %s is not a readable JSON file (%s)"
            % (_MANIFEST, block["schema"], exc)
        ) from exc
    try:
        version = schema["properties"]["schema_version"]["const"]
    except (KeyError, TypeError):
        version = None
    if type(version) is not int:
        raise EvidenceConfigError(
            "%s: has no integer properties.schema_version.const, the record "
            "version's only owner" % block["schema"]
        )
    return {
        "dir": block["dir"].replace("\\", "/").rstrip("/"),
        "schema": block["schema"],
        "schema_version": version,
    }


def _words(makeflags):
    """MAKEFLAGS split on unescaped whitespace, each `\\x` unescaped to `x`."""
    words, word, escaped, started = [], [], False, False
    for ch in makeflags:
        if escaped:
            word.append(ch)
            escaped = False
        elif ch == "\\":
            escaped, started = True, True
        elif ch.isspace():
            if started:
                words.append("".join(word))
            word, started = [], False
        else:
            word.append(ch)
            started = True
    if started:
        words.append("".join(word))
    return words


def _flag_word(makeflags):
    """MAKEFLAGS' single-letter word, or "" when it has none (it then opens
    with a space, a long option or the `--` before the variables)."""
    stripped = makeflags.split(None, 1)
    if not makeflags or makeflags[0].isspace() or not stripped:
        return ""
    first = stripped[0]
    return "" if first.startswith("-") else first


def make_mode(makeflags):
    """(dry_run, keep_going) from the single-letter word of *makeflags*: a
    variable named n after `--` is not the flag."""
    letters = _flag_word(makeflags)
    return (
        any(c in letters for c in _DRY_LETTERS),
        "k" in letters,
    )


def make_args(makeflags):
    """What the outer make put in *makeflags*, as argv for a sub-make started
    without it: the single-letter word as one option, every long option except
    the jobserver's, then the command-line variables in the order given (make
    lists them last first)."""
    words = _words(makeflags)
    if "--" in words:
        cut = words.index("--")
        options, variables = words[:cut], words[cut + 1 :]
    else:
        options, variables = words, []
    out = []
    letters = _flag_word(makeflags)
    if letters:
        out.append("-" + letters)
        options = options[1:]
    out.extend(w for w in options if not w.startswith(_JOBSERVER))
    out.extend(reversed(variables))
    return out


def junit_counts(path):
    """{passed, failed, skipped, errors} from the junit report at *path*, each
    testcase counted once (error, else failure, else skipped, else passed), or
    None when there is no readable report. The suite attributes are never read:
    they count a test that fails and then errors in teardown twice."""
    # The stdlib parser, not defusedxml: the gate must stay stdlib at the old
    # floor, and the report is the file this run's own pytest just wrote inside
    # the repository, trusted as much as the tests that produced it.
    try:
        tree = ET.parse(path)  # noqa: S314
    except (OSError, ET.ParseError):
        return None
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for case in tree.getroot().iter("testcase"):
        tags = {child.tag for child in case}
        if "error" in tags:
            counts["errors"] += 1
        elif "failure" in tags:
            counts["failed"] += 1
        elif "skipped" in tags:
            counts["skipped"] += 1
        else:
            counts["passed"] += 1
    return counts


def _junit_path(junit_dir, goal):
    return junit_dir + "/" + goal + ".xml"


def run_goals(
    make, goals, root, junit_dir, keep_going, forward=(), runner=None, dry_run=False
):
    """[{name, result, returncode, tests: None}] for each goal, run in order as
    `make <forward> <goal> JUNIT_XML=<junit_dir>/<goal>.xml` in *root* with the
    allowlisted environment. A stale report is deleted before its goal, so a
    goal that never reaches pytest is never credited with old counts; a
    *dry_run* deletes nothing. Output streams through. After the first failure
    the rest are not-run, unless *keep_going*."""
    targets = []
    stopped = False
    for goal in goals:
        if stopped:
            targets.append(_not_run(goal))
            continue
        junit = _junit_path(junit_dir, goal)
        stale = os.path.join(root, junit)
        if not dry_run and os.path.lexists(stale):
            os.remove(stale)
        # JUNIT_XML last, so a forwarded variable of the same name loses.
        argv = [make] + list(forward) + [goal, "JUNIT_XML=" + junit]
        if runner is None:
            proc = subprocess.run(  # noqa: S603 — argv list, never a shell string
                argv, cwd=root, env=child_env.build_child_env()
            )
        else:
            proc = runner(argv, cwd=root, env=child_env.build_child_env())
        code = proc.returncode
        targets.append(
            {
                "name": goal,
                "result": "pass" if code == 0 else "fail",
                "returncode": code,
                "tests": None,
            }
        )
        if code != 0 and not keep_going:
            stopped = True
    return targets


def _not_run(goal):
    return {"name": goal, "result": "not-run", "returncode": None, "tests": None}


def _relative(message, prefixes):
    for prefix in prefixes:
        message = message.replace(prefix + os.sep, "")
    for prefix in prefixes:
        message = message.replace(prefix, ".")
    return message


def check_findings(root):
    """{letter: {errors, warnings}} for every letter in check_structure.CHECKS
    and each project:<stem> that reported, by check_structure.run_checks in this
    process, each list sorted and each message stripped of the absolute root
    (both its spelling and its real path: an automount path is not its real
    path)."""
    found = check_structure.run_checks(root)
    prefixes = sorted(
        {root, os.path.abspath(root), os.path.realpath(root)},
        key=len,
        reverse=True,
    )
    out = {}
    for letter, _check in check_structure.CHECKS:
        out[letter] = {"errors": [], "warnings": []}
    for letter, tier, message in found:
        slot = out.setdefault(letter, {"errors": [], "warnings": []})
        slot["errors" if tier == "error" else "warnings"].append(
            _relative(message, prefixes)
        )
    for slot in out.values():
        slot["errors"].sort()
        slot["warnings"].sort()
    return out


def overall(targets, tests, tree_changed, checks_ok):
    """(result, sorted reasons). Red for a failing goal, zero goals, no test
    report, zero tests (nothing passed, failed or errored, an all-skipped suite
    included), a failed or errored test (a goal that exited 0 anyway, as under
    `make -i`, included), a tree that changed (None, unknown without git, is
    not a change) and checks that could not run."""
    reasons = set()
    if not targets:
        reasons.add("zero-targets")
    if any(t["result"] == "fail" for t in targets):
        reasons.add("target-failed")
    if tests is None:
        reasons.add("no-test-report")
    elif tests["passed"] + tests["failed"] + tests["errors"] == 0:
        reasons.add("zero-tests")
    elif tests["failed"] + tests["errors"] > 0:
        # The goal's exit is not the only judge: `make -i`, a `-` recipe line or
        # `|| true` can exit 0 over a report that counts failures.
        reasons.add("tests-failed")
    if tree_changed is True:
        reasons.add("tree-changed")
    if not checks_ok:
        reasons.add("checks-unavailable")
    return ("fail" if reasons else "pass", sorted(reasons))


def render(record):
    """The record's canonical text: sorted keys, two-space indent, one newline."""
    return json.dumps(record, indent=2, sort_keys=True) + "\n"


def write_record(root, rel, text):
    """Replace <root>/<rel> whole with *text*: written beside it, then renamed,
    so a reader never sees half a record."""
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _sum_counts(targets):
    reported = [t["tests"] for t in targets if t["tests"] is not None]
    if not reported:
        return None
    return {
        key: sum(c[key] for c in reported)
        for key in ("passed", "failed", "skipped", "errors")
    }


def _exit_status(code):
    # A goal killed by a signal reports -N; the shell's spelling is 128+N, and a
    # negative status would wrap to a value that hides the signal.
    return 128 - code if code < 0 else code


def _exit_code(targets, result):
    for target in targets or ():
        if target["result"] == "fail":
            return _exit_status(target["returncode"])
    return 0 if result == "pass" else _RED_EVIDENCE


def _source(root):
    """(snapshot or None, source block before the goals run)."""
    try:
        snap = git_tree.tree_snapshot(root)
    except git_tree.NoGitError:
        return None, {
            "commit": None,
            "dirty": None,
            "tree_changed": None,
            "tree_digest": None,
        }
    commit = git_tree.head_commit(root)
    return snap, {
        "commit": commit,
        # No commit yet: everything in the tree is uncommitted.
        "dirty": bool(snap) or commit is None,
        "tree_changed": None,
        "tree_digest": git_tree.snapshot_digest(snap),
    }


def _changed(root, before):
    if before is None:
        return None
    try:
        return git_tree.tree_snapshot(root) != before
    except git_tree.NoGitError:
        # Readable before and not after: what the goals did cannot be shown
        # harmless, so it counts as a change.
        return True


def _unignored(root, paths):
    """The paths git would list, or None when root is not in a git work tree
    (nothing is listed there, so nothing needs ignoring)."""
    try:
        return [p for p in paths if not git_tree.is_ignored(root, p)]
    except git_tree.NoGitError:
        return None


def _parse(argv):
    argv = list(argv)
    command = []
    if "--" in argv:
        cut = argv.index("--")
        argv, command = argv[:cut], argv[cut + 1 :]
    ap = argparse.ArgumentParser(
        prog="gate_evidence.py",
        description=(
            "Run a gate's make goals in order and write its evidence record to "
            "config/project.json evidence.dir as <gate>.json. Usage: "
            "gate_evidence.py --gate <token> -- <make> <goal>..."
        ),
    )
    ap.add_argument(
        "--gate",
        required=True,
        help="the gate's name: the record's file name and its `gate` field "
        "(lower-case letters, digits and '-')",
    )
    return ap.parse_args(argv), command


def _refuse(message):
    sys.stderr.write("gate_evidence: %s\n" % message)
    return _REFUSED


def main(argv=None, runner=None):
    """Run the gate and write its record; the exit status, which the record's
    `result` always agrees with. *runner* stands in for subprocess.run."""
    try:
        args, command = _parse(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        # argparse's own exit: 2 for a usage error, 0 for --help.
        return exc.code
    root = os.getcwd()
    if not _GATE.match(args.gate):
        return _refuse("--gate %r is not a gate token ([a-z0-9][a-z0-9-]*)" % args.gate)
    make, goals = (command[0], command[1:]) if command else (None, [])
    bad = [g for g in goals if not _GOAL.match(g)]
    if bad:
        return _refuse("goal(s) %s are not make target tokens" % ", ".join(bad))
    try:
        policy = load_policy(root)
    except EvidenceConfigError as exc:
        return _refuse(str(exc))
    rel = policy["dir"] + "/" + args.gate + ".json"
    junit_dir = policy["dir"] + "/junit"
    makeflags = os.environ.get("MAKEFLAGS", "")
    dry_run, keep_going = make_mode(makeflags)
    forward = make_args(makeflags)
    if dry_run:
        # make -n/-q/-t still runs a `$(MAKE)` recipe line: run each goal under
        # the same flag, so it only prints, and write nothing.
        if not goals:
            return _refuse("no goal to run after `-- <make>`")
        done = run_goals(
            make, goals, root, junit_dir, keep_going, forward, runner, dry_run=True
        )
        return _exit_code(done, "pass")
    listed = _unignored(
        root, [rel, rel + ".tmp"] + [_junit_path(junit_dir, g) for g in goals]
    )
    if listed:
        return _refuse(
            "git would list %s: add config/project.json evidence.dir (%s) to "
            ".gitignore, so a gate run never changes what git lists"
            % (", ".join(listed), policy["dir"])
        )
    before, source = _source(root)

    def record(targets, tests, checks, result, reasons):
        return {
            "checks": checks,
            "gate": args.gate,
            "reasons": reasons,
            "result": result,
            "schema": policy["schema"],
            "schema_version": policy["schema_version"],
            "source": source,
            "targets": targets,
            "tests": tests,
        }

    if not goals:
        write_record(
            root, rel, render(record([], None, None, "fail", ["zero-targets"]))
        )
        return _refuse("no goal to run after `-- <make>`: the record is red")
    targets = None
    try:
        placeholder = [_not_run(g) for g in goals]
        write_record(
            root, rel, render(record(placeholder, None, None, "fail", ["incomplete"]))
        )
        targets = run_goals(make, goals, root, junit_dir, keep_going, forward, runner)
        for target in targets:
            if target["result"] != "not-run":
                target["tests"] = junit_counts(
                    os.path.join(root, _junit_path(junit_dir, target["name"]))
                )
        tests = _sum_counts(targets)
        try:
            checks, checks_ok = check_findings(root), True
        except Exception:  # noqa: BLE001 — any failure of a check is "unavailable"
            traceback.print_exc()
            checks, checks_ok = None, False
        source["tree_changed"] = _changed(root, before)
        result, reasons = overall(targets, tests, source["tree_changed"], checks_ok)
        write_record(root, rel, render(record(targets, tests, checks, result, reasons)))
        if reasons:
            sys.stderr.write(
                "gate_evidence: %s is red: %s\n" % (rel, ", ".join(reasons))
            )
        return _exit_code(targets, result)
    except KeyboardInterrupt:
        sys.stderr.write(
            "gate_evidence: interrupted; %s stays red (incomplete)\n" % rel
        )
        return _INTERRUPTED
    except Exception:  # noqa: BLE001 — the writer failing must never read as a pass
        traceback.print_exc()
        done = targets or [_not_run(g) for g in goals]
        # json.dumps, not render: render may be the very thing that failed.
        try:
            write_record(
                root,
                rel,
                json.dumps(
                    record(done, None, None, "fail", ["writer-error"]),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
        except Exception:  # noqa: BLE001 — the placeholder on disk is already red
            traceback.print_exc()
        return _exit_code(targets, "fail")


if __name__ == "__main__":
    sys.exit(main())
