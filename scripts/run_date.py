"""
title: run_date — the one date a gate run calls today
kind: script
layer: n/a
summary: The one definition of the date a whole gate run calls today, shared by the driver that fixes it and every check that reads it. config/project.json `evidence.run_date` names the channel: `env`, the environment variable the date travels in, and `max_age_days`, how many days before the clock a supplied date may be. scripts/gate_evidence.py calls `for_run` once, before the first goal, and hands the answer to every goal; scripts/jobs/review_docs.py `resolve_today` calls `today`, so a check started late in a run that crossed midnight judges by the day the run began. `git_dates` gives a git commit made inside the run the run's date, held to the last second of that day once the clock has passed it, for tests/hermetic_git.py, so a tree the test suite commits after midnight is not dated a day past the stamps the run wrote. A date found in the variable is a caller's claim and is checked every time it is read: it must be written YYYY-MM-DD, be a calendar date, be no later than the clock and no more than `max_age_days` days before it, and anything else is a RunDateError that names the variable and the config key and never falls back to the clock. So the variable can move today back by the bound and never forward, which is the most a caller gains by setting it by hand. `policy` refuses a malformed block naming the key at fault, and refuses an `env` that `child_env.names` does not list, since scripts/child_env.py would then drop the variable before any check below the driver saw it. A fault in config/project.json, as opposed to a supplied date, is a RunDateConfigError, a RunDateError that carries `remedy`, the edit that clears it, because no other date would; scripts/jobs/review_docs.py and scripts/jobs/restamp_docs.py report that as their next step, and scripts/check_structure.py check_X reads the same `policy` so a project learns of the fault before a run. An absent `evidence.run_date`, or an absent config/project.json, switches the channel off: every reader reads the clock and no variable is a run date. A config/project.json an update left conflicted is refused as that conflict, with the hunk's line found by scripts/child_env.py `conflict_hunk_line`, never as the JSON error the markers cause. It is never run, starts no process and writes nothing; it does not decide what a date is compared with (scripts/jobs/review_docs.py `stale_findings` does), and it is not the pinned build date (SOURCE_DATE_EPOCH, which `resolve_today` reads first). Stdlib plus scripts/child_env.py, and 3.6-safe, because scripts/gate_evidence.py imports it under the old interpreter.
effect: read-only
"""

# NB: stdlib and child_env only, no `from __future__ import annotations`, no f-strings, no walrus,
# no `list[str]` or `X | None` annotations. scripts/gate_evidence.py imports this
# module, and a `make verify` whose PY is older than requires-python must still run
# that writer so the record it leaves is red rather than an earlier green one
# (tests/integration/test_gate_scope.py `_old_python_safe`).

import collections
import datetime
import json
import os
import string
import time

import child_env

__all__ = [
    "RunDateConfigError",
    "RunDateError",
    "RunDatePolicy",
    "checked",
    "for_run",
    "git_dates",
    "load",
    "policy",
    "today",
]

# The fixed project file this module reads, declared for scripts/jobs/
# conflict_guard.py: a copier job whose imports reach here refuses, naming the
# file, when an update leaves it conflicted. Written out twice because that
# guard reads the declaration from the source without importing it, and
# tests/integration/test_copier_job_conflict_refusal.py holds each declared
# read to a path literal the module uses.
PROJECT_READS = ("config/project.json",)
_MANIFEST = "config/project.json"
_KEY = "evidence.run_date"
_FINISH_DOC = "docs/guides/generate-and-upgrade.md, 'Finish an update that stopped'"
_KEYS = ("env", "max_age_days")
_FORMAT = "%Y-%m-%d"
_GIT_MOMENT = "%Y-%m-%d %H:%M:%S"
_LAST_SECOND = datetime.time(23, 59, 59)
# A date written out is ten characters. A longer value is not a date, and the
# variable is one config names, so a wrong name there could hold anything: past
# this length a refusal counts the value instead of printing it.
_QUOTED_MAX = 32
_NAME_START = string.ascii_letters + "_"
_NAME_REST = _NAME_START + string.digits

RunDatePolicy = collections.namedtuple("RunDatePolicy", ("env", "max_age_days"))


class RunDateError(ValueError):
    """The run date's config block, or a date a caller supplied, cannot be
    used. A ValueError so a caller that only knows the stdlib still catches it."""


class RunDateConfigError(RunDateError):
    """config/project.json, not a date a caller supplied, is at fault. Another
    date does not clear it, so it carries *remedy*: the edit that does, for a
    caller to report as its next step."""

    def __init__(self, message, remedy):
        RunDateError.__init__(self, message)
        self.remedy = remedy


_NOT_JSON_REMEDY = "correct %s where the parser points, then rerun" % _MANIFEST
# The next step for a malformed block. The message names the key at fault.
_BLOCK_REMEDY = (
    "correct %s `evidence.run_date`: an object with `env`, a variable name "
    "`child_env.names` lists, and `max_age_days`, a whole number of days, 0 or "
    "more; or remove the block to switch the run date off" % _MANIFEST
)


def _is_variable_name(value):
    return (
        isinstance(value, str)
        and value != ""
        and value[0] in _NAME_START
        and all(ch in _NAME_REST for ch in value)
    )


def policy(manifest):
    """The RunDatePolicy *manifest* (config/project.json, parsed) declares, or
    None when it has no `evidence.run_date`: the channel is off. Raises
    RunDateConfigError naming the key at fault and the edit that clears it."""
    if not isinstance(manifest, dict):
        raise RunDateConfigError(
            "%s: is not a JSON object" % _MANIFEST,
            "rewrite %s as one JSON object" % _MANIFEST,
        )
    evidence = manifest.get("evidence", {})
    if not isinstance(evidence, dict):
        raise RunDateConfigError(
            "%s: `evidence` must be an object" % _MANIFEST,
            "rewrite %s `evidence` as an object" % _MANIFEST,
        )
    if "run_date" not in evidence:
        return None
    block = evidence["run_date"]
    if not isinstance(block, dict):
        raise RunDateConfigError(
            "%s: %s must be an object with the keys %s"
            % (_MANIFEST, _KEY, " and ".join(_KEYS)),
            _BLOCK_REMEDY,
        )
    for key in sorted(block):
        if key not in _KEYS:
            raise RunDateConfigError(
                "%s: %s.%s is not a key (the keys are %s)"
                % (_MANIFEST, _KEY, key, " and ".join(_KEYS)),
                _BLOCK_REMEDY,
            )
    name = block.get("env")
    if not _is_variable_name(name):
        raise RunDateConfigError(
            "%s: %s.env must be an environment variable name (letters, digits "
            "and '_', not starting with a digit)" % (_MANIFEST, _KEY),
            _BLOCK_REMEDY,
        )
    bound = block.get("max_age_days")
    # type(), not isinstance: True is an int to isinstance, and a bound of
    # "true" days is a typo, not one day.
    if type(bound) is not int or bound < 0:
        raise RunDateConfigError(
            "%s: %s.max_age_days must be a whole number of days, 0 or more"
            % (_MANIFEST, _KEY),
            _BLOCK_REMEDY,
        )
    allowlist = manifest.get("child_env", {})
    names = allowlist.get("names") if isinstance(allowlist, dict) else None
    if not isinstance(names, list) or name not in names:
        raise RunDateConfigError(
            "%s: %s.env names %s, which `child_env.names` does not list, so no "
            "process below the gate's driver would receive the run's date"
            % (_MANIFEST, _KEY, name),
            "add %s to %s `child_env.names`, or remove `%s` to switch the run "
            "date off" % (name, _MANIFEST, _KEY),
        )
    return RunDatePolicy(env=name, max_age_days=bound)


def load(root):
    """`policy` of <root>/config/project.json. A root with no such file has no
    channel (None): its readers read the clock, which is the strict side.
    A file that is there and cannot be read or parsed is a RunDateConfigError,
    and one an update left conflicted is named as that conflict, with its
    line."""
    path = os.path.join(root, *_MANIFEST.split("/"))
    if not os.path.lexists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except OSError as exc:
        raise RunDateConfigError(
            "%s: unreadable (%s)" % (_MANIFEST, exc),
            "make %s readable, then rerun" % _MANIFEST,
        ) from exc
    except ValueError as exc:
        message, remedy = _unparsed(path, exc)
        raise RunDateConfigError(message, remedy) from exc
    return policy(manifest)


def _unparsed(path, exc):
    """(message, remedy) for a manifest that is not JSON."""
    # Markers are what an update leaves, and the JSON error they cause
    # ("Expecting property name") names neither the file's real state nor the
    # step that clears it.
    try:
        line = child_env.conflict_hunk_line(path)
    except Exception as why:  # noqa: BLE001 -- any failure keeps the parse error
        return (
            "%s: unreadable (%s; conflict markers not checked: %s)"
            % (_MANIFEST, exc, why),
            _NOT_JSON_REMEDY,
        )
    if line is None:
        return "%s: unreadable (%s)" % (_MANIFEST, exc), _NOT_JSON_REMEDY
    finish = "resolve it, then finish the update (%s)" % _FINISH_DOC
    return (
        "%s holds a merge-conflict hunk at line %d, so the gate run's date "
        "cannot be read: %s" % (_MANIFEST, line, finish),
        finish,
    )


def _shown(raw):
    if len(raw) > _QUOTED_MAX:
        return "a value %d characters long" % len(raw)
    return repr(raw)


def checked(raw, policy, clock_today):
    """The date *raw* names, when a run that the clock says is at *clock_today*
    could have begun on it: written YYYY-MM-DD, a calendar date, not later than
    *clock_today* and not more than `policy.max_age_days` days before it.
    Raises RunDateError naming `policy.env` otherwise."""
    try:
        parsed = datetime.datetime.strptime(raw, _FORMAT).date()
    except ValueError:
        parsed = None
    # strptime takes "2031-3-1" and surrounding digits of other widths; the
    # round trip holds the value to the one spelling a reader compares as text.
    if parsed is None or parsed.isoformat() != raw:
        raise RunDateError(
            "%s holds %s, which is not a calendar date written YYYY-MM-DD"
            % (policy.env, _shown(raw))
        )
    if parsed > clock_today:
        raise RunDateError(
            "%s holds %s, which is later than the clock's date (%s): a run "
            "cannot begin after it is read" % (policy.env, raw, clock_today.isoformat())
        )
    age = (clock_today - parsed).days
    if age > policy.max_age_days:
        raise RunDateError(
            "%s holds %s, which is %d day(s) before the clock's date (%s), more "
            "than %s %s.max_age_days (%d) allows a run to last"
            % (
                policy.env,
                raw,
                age,
                clock_today.isoformat(),
                _MANIFEST,
                _KEY,
                policy.max_age_days,
            )
        )
    return parsed


def today(environ, policy, clock=datetime.date.today):
    """The date a check calls today: the run's date from *environ* when
    *policy* names a variable and the variable is set, checked against one read
    of *clock*, else that one read. A set variable that fails the check is a
    RunDateError, never a fall back to the clock."""
    now = clock()
    if policy is None or policy.env not in environ:
        return now
    return checked(environ[policy.env], policy, now)


def for_run(environ, policy, clock=datetime.date.today):
    """(variable name, ISO date) the driver hands every goal of one run: an
    outer run's date when *environ* already carries a valid one (a gate started
    inside a gate is still that run), else one read of *clock*."""
    return policy.env, today(environ, policy, clock).isoformat()


def git_dates(environ, policy, clock=datetime.datetime.now):
    """GIT_AUTHOR_DATE and GIT_COMMITTER_DATE, one value for both, for a git
    commit made inside the run *environ* carries, or {} when *policy* is None
    or *environ* does not carry the run's date. The value is one read of
    *clock* (a naive local datetime) to the second, held back to the last
    second of the run's date when the clock has passed that day, written with
    the local UTC offset so git records the run's date as the commit's. A set
    variable that fails `checked` is a RunDateError."""
    if policy is None or policy.env not in environ:
        return {}
    now = clock().replace(microsecond=0)
    day = checked(environ[policy.env], policy, now.date())
    # A commit's date is what scripts/jobs/review_docs.py reads as a committed
    # document's floor, so one dated by the clock after midnight would sit a
    # day past every stamp the run wrote.
    moment = min(now, datetime.datetime.combine(day, _LAST_SECOND))
    # The offset in force at *moment*, not now: a DST change between the two
    # would otherwise shift the recorded date across midnight.
    offset = time.strftime("%z", time.localtime(time.mktime(moment.timetuple())))
    stamp = "%s %s" % (moment.strftime(_GIT_MOMENT), offset)
    return {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
