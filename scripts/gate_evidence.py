#!/usr/bin/env python3
"""
title: Gate evidence — run a gate's goals and write its evidence record
kind: script
layer: n/a
summary: The driver a gate recipe runs as `gate_evidence.py --gate <token> -- <make> <goal>...`. It runs each goal as its own make, in order, with the allowlisted environment from scripts/child_env.py and the outer make's flags and command-line variables as argv; when config/project.json `evidence.run_date` is present it reads the clock once before the first goal (or keeps a valid date an outer run already set) and hands that one date to every goal in the variable the block names, through scripts/run_date.py, so a check late in a run that crossed midnight judges by the day the run began; stops at the first failing goal unless MAKEFLAGS carries k; and writes one canonical JSON record to `<config/project.json evidence.dir>/<gate>.json`, shaped by the JSON Schema `evidence.schema` names, which alone owns `schema_version`. The record names the commit, whether the tree was dirty and a digest of what git lists (scripts/git_tree.py), each goal's result and exit code, the test counts from pytest's own junit report, and every scripts/check_structure.py finding. The record holds no clock, date, duration, host, user or absolute path, so a rerun on the same tree writes the same bytes. It fails closed: a red placeholder is written before the first goal, so an interrupted run never leaves an earlier green record standing; a failing goal's exit code passes through; zero tests, no report, a failed or errored test in pytest's report (a goal that exited 0 anyway, as under `make -i`), a tree changed during the run, checks that could not run and a crash of the writer itself are each a red record and exit RED_RECORD (scripts/exit_codes.py); a config/project.json value it reads that cannot be used (the manifest, `evidence.dir`, `evidence.schema` or `evidence.run_date`, each read through scripts/config_loader.py, which names every key at fault in one run) is refused with exit CONFIG before any goal runs; zero goals, a malformed gate or goal, an `evidence.schema` file that cannot be read or has no integer version, a supplied run date that is not a date or is further from the clock than `evidence.run_date.max_age_days` allows, a record, temporary or report path that reaches its file through a symlink (scripts/git_tree.py `through_symlink`, asked once before the first write or removal and not again during the run), a record or report path git does not ignore, and a git that ran and failed when asked (an unreadable repository is unknown, not absent) are refused with exit 2 before any goal runs; an interrupt exits 130. Under `make -n`, `-q` or `-t` it runs the goals with that flag and writes nothing. It is not a general gate runner (scripts/run_make_target.py is) and keeps no history: each run replaces the file whole.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_gate_evidence_record.py
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no walrus,
# no evaluated `list[str]` or `X | None` annotations, and only bare scripts/
# siblings that keep the same rule (check_structure, child_env, git_tree, run_date).
# A `make
# verify` whose PY is older than requires-python must still run this writer, so
# the record it leaves is red rather than an earlier green one
# (tests/integration/test_gate_scope.py `_old_python_safe`).

import argparse
import datetime
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
import config_loader  # noqa: E402 — the one reader of config/project.json
import git_tree  # noqa: E402 — the one definition of what git lists
import run_date  # noqa: E402 — the one date a whole run calls today
from exit_codes import ExitCode, finish, passthrough, report  # noqa: E402

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


class EvidenceConfigError(Exception):
    """A config/project.json value `evidence` reads cannot be used: the
    manifest itself, `evidence.dir`, `evidence.schema` or the run date block.
    An edit to config/project.json clears it."""


class EvidenceSchemaError(Exception):
    """The JSON Schema `evidence.schema` names cannot be read, or has no
    integer `properties.schema_version.const`. The schema file, not a config
    value, is at fault."""


_PATHS = (("evidence", "dir"), ("evidence", "schema"))


def load_policy(root):
    """{dir, schema, schema_version, run_date} from config/project.json
    `evidence`, read through scripts/config_loader.py, the version read from
    the schema's `properties.schema_version.const`, its only owner, and
    run_date the scripts/run_date.py policy or None when the block has no
    `run_date`. Raises EvidenceConfigError carrying the loader's lines for a
    config value, and EvidenceSchemaError for the schema file."""
    try:
        manifest = config_loader.read(root)
        declared = config_loader.resolve(
            manifest, config_loader.rows(*_PATHS), _MANIFEST
        )
    except config_loader.ConfigError as exc:
        raise EvidenceConfigError("; ".join(exc.lines)) from exc
    schema_rel = declared[("evidence", "schema")]
    schema_path = os.path.join(root, schema_rel)
    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, ValueError) as exc:
        raise EvidenceSchemaError(
            "%s: evidence.schema %s is not a readable JSON file (%s)"
            % (_MANIFEST, schema_rel, exc)
        ) from exc
    try:
        version = schema["properties"]["schema_version"]["const"]
    except (KeyError, TypeError):
        version = None
    if type(version) is not int:
        raise EvidenceSchemaError(
            "%s: has no integer properties.schema_version.const, the record "
            "version's only owner" % schema_rel
        )
    try:
        date_policy = run_date.policy(manifest)
    except run_date.RunDateError as exc:
        raise EvidenceConfigError(str(exc)) from exc
    return {
        "run_date": date_policy,
        "dir": declared[("evidence", "dir")].replace("\\", "/").rstrip("/"),
        "schema": schema_rel,
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
    make,
    goals,
    root,
    junit_dir,
    keep_going,
    forward=(),
    runner=None,
    dry_run=False,
    extra=None,
):
    """[{name, result, returncode, tests: None}] for each goal, run in order as
    `make <forward> <goal> JUNIT_XML=<junit_dir>/<goal>.xml` in *root* with the
    allowlisted environment plus *extra* (the run's date, under the name config
    gives it). A stale report is deleted before its goal, so a
    goal that never reaches pytest is never credited with old counts; a
    *dry_run* deletes nothing. Output streams through. After the first failure
    the rest are not-run, unless *keep_going*."""
    targets = []
    stopped = False
    # No `extra=` at all when there is nothing to add: the helper then states,
    # at this call, that the child gets the allowlist and nothing else.
    added = {"extra": extra} if extra else {}
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
                argv, cwd=root, env=child_env.build_child_env(**added)
            )
        else:
            proc = runner(argv, cwd=root, env=child_env.build_child_env(**added))
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


def _exit_code(targets, result, where):
    """The status the run ends with: the first failing goal's own, else
    SUCCESS for a green record, else RED_RECORD, with *where* naming the
    record that is red."""
    for target in targets or ():
        if target["result"] == "fail":
            return passthrough(target["returncode"])
    if result == "pass":
        return ExitCode.SUCCESS
    return report(
        ExitCode.RED_RECORD,
        "gate_evidence: the evidence record is red though no goal failed",
        where,
        "read the record's `reasons`, fix what they name and run the gate again",
    )


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
    except (git_tree.NoGitError, git_tree.GitFailedError):
        # Readable before and not after, whether the repository is gone or git
        # now fails on it: what the goals did cannot be shown harmless, so it
        # counts as a change.
        return True


def _unignored(root, paths):
    """The paths git would list, or None when there is no git or no repository
    (nothing is listed there, so nothing needs ignoring). A git that ran and
    failed raises git_tree.GitFailedError: it has not said the paths are safe."""
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


def _refuse(message, next_step):
    return report(
        ExitCode.USAGE, "gate_evidence: refused before any goal ran", message, next_step
    )


def _git_refusal(policy, exc):
    return _refuse(
        "git could not say whether config/project.json evidence.dir %r is ignored "
        "or what the tree holds, and a failure is not an answer, so nothing was "
        "written (%s)" % (policy["dir"], exc),
        "repair the repository git reads here and run the gate again",
    )


def main(argv=None, runner=None, clock=None):
    """Run the gate and write its record; the exit status, which the record's
    `result` always agrees with. *runner* stands in for subprocess.run and
    *clock* for datetime.date.today."""
    usage = "call it as `gate_evidence.py --gate <token> -- <make> <goal>...`"
    try:
        args, command = _parse(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        # argparse ends the process itself: status 0 after --help, and a
        # usage error it has already written to stderr otherwise.
        if not exc.code:
            return ExitCode.SUCCESS
        return _refuse("argparse refused the arguments above", usage)
    root = os.getcwd()
    if not _GATE.match(args.gate):
        return _refuse(
            "--gate %r is not a gate token ([a-z0-9][a-z0-9-]*)" % args.gate, usage
        )
    make, goals = (command[0], command[1:]) if command else (None, [])
    bad = [g for g in goals if not _GOAL.match(g)]
    if bad:
        return _refuse("goal(s) %s are not make target tokens" % ", ".join(bad), usage)
    try:
        policy = load_policy(root)
    except EvidenceConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "gate_evidence: refused before any goal ran",
            str(exc),
            "correct config/project.json `evidence`",
        )
    except EvidenceSchemaError as exc:
        return _refuse(str(exc), "correct the schema config/project.json names")
    rel = policy["dir"] + "/" + args.gate + ".json"
    junit_dir = policy["dir"] + "/junit"
    makeflags = os.environ.get("MAKEFLAGS", "")
    dry_run, keep_going = make_mode(makeflags)
    forward = make_args(makeflags)
    dated = None
    if policy["run_date"] is not None:
        # Read here, before the dry-run branch and before any goal: one answer
        # for the whole run, a dry run's goals included.
        try:
            name, value = run_date.for_run(
                os.environ, policy["run_date"], clock or datetime.date.today
            )
        except run_date.RunDateError as exc:
            return _refuse(
                str(exc),
                "unset %s, or set it to the date this run began"
                % policy["run_date"].env,
            )
        dated = {name: value}
    if dry_run:
        # make -n/-q/-t still runs a `$(MAKE)` recipe line: run each goal under
        # the same flag, so it only prints, and write nothing.
        if not goals:
            return _refuse("no goal to run after `-- <make>`", usage)
        done = run_goals(
            make,
            goals,
            root,
            junit_dir,
            keep_going,
            forward,
            runner,
            dry_run=True,
            extra=dated,
        )
        return _exit_code(done, "pass", rel)
    # Every path this run writes or removes: the record, the file it is written
    # beside, and each goal's report, whose stale copy is deleted before the goal.
    guarded = [rel, rel + ".tmp"] + [_junit_path(junit_dir, g) for g in goals]
    # Before the ignore rule, which like the config check judges the path as
    # text: a symlinked component leads somewhere neither of them looked.
    linked = git_tree.through_symlink(root, guarded)
    if linked:
        return _refuse(
            "config/project.json evidence.dir %r reaches %s through a symlink, "
            "and a record written or a report removed there could land outside "
            "the project, so nothing was written or removed and an earlier "
            "record may still stand" % (policy["dir"], ", ".join(linked)),
            "replace the symlink with a real directory inside the project, or "
            "point config/project.json evidence.dir at one",
        )
    try:
        listed = _unignored(root, guarded)
    except git_tree.GitFailedError as exc:
        return _git_refusal(policy, exc)
    if listed:
        return _refuse(
            "git would list %s" % ", ".join(listed),
            "add config/project.json evidence.dir (%s) to .gitignore, so a gate "
            "run never changes what git lists" % policy["dir"],
        )
    try:
        before, source = _source(root)
    except git_tree.GitFailedError as exc:
        return _git_refusal(policy, exc)

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
        return _refuse("no goal to run after `-- <make>`: the record is red", usage)
    targets = None
    try:
        placeholder = [_not_run(g) for g in goals]
        write_record(
            root, rel, render(record(placeholder, None, None, "fail", ["incomplete"]))
        )
        targets = run_goals(
            make, goals, root, junit_dir, keep_going, forward, runner, extra=dated
        )
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
        return _exit_code(targets, result, "%s (%s)" % (rel, ", ".join(reasons)))
    except KeyboardInterrupt:
        return report(
            ExitCode.INTERRUPTED,
            "gate_evidence: interrupted",
            "%s stays red (incomplete)" % rel,
            "run the gate again",
        )
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
        return _exit_code(targets, "fail", "%s (writer-error)" % rel)


if __name__ == "__main__":
    finish(main())
