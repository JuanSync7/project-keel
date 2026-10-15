#!/usr/bin/env python3
"""
title: long_scripts — propose launch keys whose last recorded run was long
kind: script
layer: n/a
summary: Reads the durations file scripts/launch.py writes (config/project.json `launcher.durations_file`) and proposes each launch key whose last measured run took longer than `launcher.long_after_seconds` and that `launcher.long_scripts` does not list, whatever the run's outcome, because the duration is the fact. It never edits config: a proposal is a stdout line naming the key, the seconds, the outcome and the config key to add it under, and a person decides. An entry with no duration (incomplete, no-capacity) or one that is malformed is unjudged and counts neither way, and is printed as an `unjudged:` line. It ends on one of three verdicts: exit 0 when it judged at least one run and none is over and unlisted, exit 1 when it proposes a key, and exit 13 (ExitCode.NOTHING_JUDGED) when it judged nothing, because a pass over zero records is neither "none is long" nor a proposal. It refuses with exit 2 a config block launch.py's loader rejects, a durations file reached through a symlink, one git would list, a git that ran and failed, and a file that is not a JSON object. Stdlib-only and 3.6-safe, for the reason launch.py is.
effect: read-only
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no
# walrus, no dataclass, and only bare scripts/ siblings that keep the same rule
# (launch, exit_codes, git_tree): the shebang runs this under the host python3,
# which may be 3.6 (tests/integration/test_gate_scope.py `_old_python_safe`).

import argparse
import json
import os
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import git_tree  # noqa: E402 — the one definition of what git lists
from exit_codes import ExitCode, finish, report  # noqa: E402
from launch import (  # noqa: E402 — the one reader of the config and a record
    LauncherConfigError,
    load_launcher_config,
    recorded_seconds,
)

__all__ = ["VERDICTS", "Judgement", "judge"]

_MANIFEST = os.path.join("config", "project.json")
_DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# nothing-judged: no record carried a duration, so nothing can be said;
# none: at least one did and none is over the threshold and unlisted;
# proposals: at least one is.
VERDICTS = ("nothing-judged", "none", "proposals")

# proposals: (key, seconds, outcome) sorted by key; unjudged: (key, reason)
# sorted by key.
Judgement = NamedTuple(
    "Judgement",
    [("verdict", str), ("judged", int), ("proposals", tuple), ("unjudged", list)],
)


def _unjudged_reason(record):
    if isinstance(record, dict) and record.get("outcome") in (
        "incomplete",
        "no-capacity",
    ):
        return "outcome %s carries no duration" % record["outcome"]
    return "not a well-formed run record"


def judge(cfg, durations):
    """Judgement of *durations*, the parsed file {launch key: record}, under
    *cfg*: a key is proposed when its record measured more than
    cfg.long_after_seconds and cfg.long_scripts does not list it."""
    proposals, unjudged, judged = [], [], 0
    for key in sorted(durations):
        record = durations[key]
        seconds = recorded_seconds(record)
        if seconds is None:
            unjudged.append((key, _unjudged_reason(record)))
            continue
        judged += 1
        if seconds > cfg.long_after_seconds and key not in cfg.long_scripts:
            proposals.append((key, seconds, record["outcome"]))
    if judged == 0:
        verdict = "nothing-judged"
    elif proposals:
        verdict = "proposals"
    else:
        verdict = "none"
    return Judgement(verdict, judged, tuple(proposals), unjudged)


def _parse(argv):
    ap = argparse.ArgumentParser(
        prog="long_scripts.py",
        description=(
            "Propose the launch keys whose last run recorded by scripts/launch.py "
            "took longer than config/project.json launcher.long_after_seconds and "
            "that launcher.long_scripts does not list. Reads only."
        ),
    )
    ap.add_argument(
        "--root",
        default=None,
        help="the project whose config/project.json and durations file are read "
        "(default: the project this script ships in)",
    )
    return ap.parse_args(argv)


def _refuse(message, next_step):
    return report(
        ExitCode.USAGE, "long_scripts: refused before judging", message, next_step
    )


def _unsafe(root, path):
    """(what is wrong, what to do) for a durations path that is linked, listed
    or unknowable, else None."""
    if git_tree.through_symlink(root, [path]):
        return (
            "config/project.json launcher reaches %s through a symlink, so the "
            "file read may be outside the project" % path,
            "replace the symlink with a real file or directory inside the project",
        )
    try:
        listed = not git_tree.is_ignored(root, path)
    except git_tree.NoGitError:
        # With no repository nothing can commit the file, so nothing to refuse.
        listed = False
    except git_tree.GitFailedError as exc:
        return (
            "git could not say whether %s is ignored, and a failure is not an "
            "answer (%s)" % (path, exc),
            "repair the repository git reads here and run it again",
        )
    if listed:
        return (
            "git would list %s, so the run records could be committed" % path,
            "keep config/project.json launcher.durations_file under a path "
            ".gitignore ignores",
        )
    return None


def main(argv=None):
    """Judge the recorded runs and print the proposals; the exit status."""
    try:
        args = _parse(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        # argparse ends the process itself: status 0 after --help, and a usage
        # error it has already written to stderr otherwise.
        if not exc.code:
            return ExitCode.SUCCESS
        return _refuse(
            "argparse refused the arguments above", "call it as `long_scripts.py`"
        )
    root = os.path.abspath(args.root or _DEFAULT_ROOT)
    try:
        with open(os.path.join(root, _MANIFEST), encoding="utf-8") as fh:
            cfg = load_launcher_config(json.load(fh))
    except LauncherConfigError as exc:
        return _refuse(str(exc), "correct config/project.json `launcher`")
    except (OSError, ValueError) as exc:
        return _refuse(
            "%s is unreadable or not JSON (%s)" % (_MANIFEST, exc.__class__.__name__),
            "restore config/project.json",
        )
    unsafe = _unsafe(root, cfg.durations_file)
    if unsafe is not None:
        return _refuse(unsafe[0], unsafe[1])
    try:
        with open(os.path.join(root, cfg.durations_file), encoding="utf-8") as fh:
            durations = json.load(fh)
    except FileNotFoundError:
        durations = {}
    except (OSError, ValueError) as exc:
        return _refuse(
            "the durations file %s is unreadable or not JSON (%s)"
            % (cfg.durations_file, exc.__class__.__name__),
            "delete it; scripts/launch.py writes a new one on its next run",
        )
    if not isinstance(durations, dict):
        return _refuse(
            "the durations file %s is not a JSON object" % cfg.durations_file,
            "delete it; scripts/launch.py writes a new one on its next run",
        )
    found = judge(cfg, durations)
    for key, reason in found.unjudged:
        sys.stdout.write("unjudged: %s (%s)\n" % (json.dumps(key), reason))
    if found.verdict == "nothing-judged":
        return report(
            ExitCode.NOTHING_JUDGED,
            "long_scripts: no recorded runs, so nothing was judged",
            cfg.durations_file,
            "run a long script through scripts/launch.py, then run this again",
        )
    for key, seconds, outcome in found.proposals:
        sys.stdout.write(
            "propose: %s ran %d s on its last recorded run (outcome %s), over "
            "launcher.long_after_seconds (%d); add it to config/project.json "
            "launcher.long_scripts\n"
            % (json.dumps(key), seconds, outcome, cfg.long_after_seconds)
        )
    if found.verdict == "proposals":
        return report(
            ExitCode.FAILURE,
            "long_scripts: %d script(s) over the threshold are not listed"
            % len(found.proposals),
            cfg.durations_file,
            "add each proposed key to config/project.json launcher.long_scripts "
            "with its farm size, or leave it to be judged by its record",
        )
    sys.stdout.write(
        "judged %d recorded run(s); none over %d s is unlisted\n"
        % (found.judged, cfg.long_after_seconds)
    )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
