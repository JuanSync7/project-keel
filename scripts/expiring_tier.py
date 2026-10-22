"""
title: expiring_tier — a generated project's own finding warns until a hard date, from a record that only shrinks
kind: script
layer: n/a
summary: The tier a keel gate test hands its findings to (docs/adr/keel/K-0027-a-project-s-own-code-warns-until-a-hard-date.md). `judge` takes a check id scripts/expiring_tier_data.py `CHECKS` registers and the test's finding lines, each `<file>:<line>: <rule> — <fix>`, and returns a Verdict: the lines that are red, the lines that warn, and the note the warning carries. The policy is loaded first in either place, so a bad or too-late date fails closed in the template too. In the template repository, which holds copier.yml (`TEMPLATE_MARK`), every line is red and nothing warns. In a generated project a finding's identity is its line with the line number dropped, and the identities config/project.json `expiring_tier.baseline` records for the check are counted as a multiset: a finding with an entry left for it warns until `expiring_tier.expires` and is red from that day; a finding with none, a copy over the recorded count included, is red at once and names `make gate-baseline` (`RECORD_TARGET`); an entry no finding matches is red, so the record only shrinks; a line outside the grammar is red whatever the record holds; and with no baseline file every finding is red and names the target. `load_policy` refuses an `expires` that is not a YYYY-MM-DD calendar date or is later than `CEILING`, so a project may end the grace sooner and never later. `apply` is `judge` for a gate test: it issues one ExpiringTierWarning when anything warns and returns the red lines. `read_baseline` reads and checks the file. `baseline_findings` names a baseline check id `CHECKS` does not register. `start_recording` makes every `judge` keep the lines it was handed as a multiset, two identical lines two entries, which tests/conftest.py writes out for scripts/record_gate_baseline.py. The day is scripts/run_date.py `today`, so a run that crossed midnight judges by the day it began. It reads config/project.json and the baseline through scripts/config_loader.py `read` and `resolve`, and any fault in either is a TierError naming the file and the key; it does not stop a hand edit of the baseline or of the data file, which review holds. It starts no process and writes nothing.
effect: read-only
"""

import collections
import datetime
import os
import warnings
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

import config_loader
import expiring_tier_data
import run_date

__all__ = [
    "RECORD_TARGET",
    "TEMPLATE_MARK",
    "ExpiringTierWarning",
    "Policy",
    "TierError",
    "Verdict",
    "apply",
    "baseline_findings",
    "identity",
    "judge",
    "load_policy",
    "read_baseline",
    "recorded",
    "run_today",
    "start_recording",
    "stop_recording",
]

TEMPLATE_MARK = "copier.yml"
RECORD_TARGET = "gate-baseline"

_MANIFEST = config_loader.CONFIG_FILE
_DATA_FILE = "scripts/expiring_tier_data.py"
_EXPIRES = ("expiring_tier", "expires")
_BASELINE = ("expiring_tier", "baseline")


class TierError(Exception):
    """config/project.json `expiring_tier`, the baseline or the check id
    cannot be used; the message names the file and the key at fault."""


class ExpiringTierWarning(UserWarning):
    """A finding the baseline records, still inside its grace."""


class Policy(NamedTuple):
    """config/project.json `expiring_tier`: the day recorded findings turn red
    and the repo path of the baseline that records them."""

    expires: datetime.date
    baseline: str


class Verdict(NamedTuple):
    """One check's judgement: the lines that are red, the lines that warn, and
    the note a warning carries (None when nothing warns)."""

    red: List[str]
    warned: List[str]
    note: Optional[str]


# None while off; while on, the lines each check was handed, as a multiset:
# two byte-identical findings (two calls on one line) are two entries. Calls
# merge by the larger count per line, because a check judged twice in one
# session hands the same lines twice, and a sum would record each copy twice.
_RECORD: Optional[Dict[str, "collections.Counter[str]"]] = None


def start_recording() -> None:
    """From now on every `judge` keeps the lines it was handed."""
    global _RECORD
    _RECORD = {}


def stop_recording() -> None:
    """Stop keeping lines and drop what was kept."""
    global _RECORD
    _RECORD = None


def recorded() -> Optional[Dict[str, List[str]]]:
    """{check: sorted lines} kept since `start_recording`, or None when off."""
    if _RECORD is None:
        return None
    return {check: sorted(lines.elements()) for check, lines in sorted(_RECORD.items())}


def identity(line: str) -> Optional[str]:
    """*line* `<file>:<line>: <rest>` as `<file>: <rest>`, or None for a line
    outside that grammar, which no baseline entry can hold."""
    path, sep, tail = line.partition(":")
    if not sep or not path or path != path.strip():
        return None
    number, sep, rest = tail.partition(":")
    if not sep or not number.isdigit() or not rest.startswith(" "):
        return None
    return "%s:%s" % (path, rest)


def _is_template(root: str) -> bool:
    return os.path.isfile(os.path.join(root, TEMPLATE_MARK))


def load_policy(root: str) -> Policy:
    """The Policy <root>/config/project.json `expiring_tier` declares. Raises
    TierError for a block the loader refuses, an `expires` that is not a
    calendar date, or one later than scripts/expiring_tier_data.py CEILING."""
    try:
        manifest = config_loader.read(root, _MANIFEST)
        values = config_loader.resolve(
            manifest, config_loader.rows(_BASELINE, _EXPIRES), _MANIFEST
        )
    except config_loader.ConfigError as exc:
        raise TierError("; ".join(exc.lines)) from exc
    # The loader's row already holds the spelling to YYYY-MM-DD, so this
    # parse cannot fail on a value resolve handed out.
    expires = datetime.date.fromisoformat(values[_EXPIRES])
    ceiling = datetime.date.fromisoformat(expiring_tier_data.CEILING)
    if expires > ceiling:
        raise TierError(
            "%s: expiring_tier.expires is %s, later than the ceiling %s that "
            "%s CEILING sets; write %s or an earlier date"
            % (_MANIFEST, expires, ceiling, _DATA_FILE, ceiling)
        )
    return Policy(expires=expires, baseline=values[_BASELINE])


def read_baseline(root: str, relpath: str) -> Optional[Dict[str, Any]]:
    """The baseline at *relpath*, `{"checks": {check: identities}, "commit":
    commit}`, or None when there is no such file. Raises TierError naming *relpath* for a file that
    is not `{"checks": {id: [str, ...]}, "commit": str}`."""
    if not os.path.lexists(os.path.join(root, relpath)):
        return None
    try:
        doc = config_loader.read(root, relpath)
    except config_loader.ConfigError as exc:
        raise TierError("; ".join(exc.lines)) from exc
    checks = doc.get("checks")
    well_formed = (
        isinstance(checks, dict)
        and isinstance(doc.get("commit"), str)
        and all(
            isinstance(entries, list) and all(isinstance(e, str) for e in entries)
            for entries in checks.values()
        )
    )
    if not well_formed or not isinstance(checks, dict):
        raise TierError(
            '%s: is not {"checks": {<check id>: [<finding>, ...]}, "commit": '
            "<commit>}; rerun `make %s` to rewrite it" % (relpath, RECORD_TARGET)
        )
    return {
        "checks": {str(check): list(entries) for check, entries in checks.items()},
        "commit": doc["commit"],
    }


def run_today(root: str) -> datetime.date:
    """The day this run judges by (scripts/run_date.py `today`)."""
    try:
        return run_date.today(os.environ, run_date.load(root))
    except run_date.RunDateError as exc:
        raise TierError(str(exc)) from exc


def judge(
    check: str,
    lines: Sequence[str],
    root: str,
    today: Optional[datetime.date] = None,
) -> Verdict:
    """The Verdict on the finding *lines* of *check* in the tree at *root*,
    judged on *today* (`run_today` when None). Raises TierError for a check
    `CHECKS` does not register or a policy or baseline that cannot be used."""
    if check not in expiring_tier_data.CHECKS:
        raise TierError(
            "%s is not a check %s CHECKS registers (the checks are %s)"
            % (check, _DATA_FILE, ", ".join(sorted(expiring_tier_data.CHECKS)))
        )
    if _RECORD is not None:
        _RECORD[check] = _RECORD.get(check, collections.Counter()) | (
            collections.Counter(lines)
        )
    # The policy is loaded before the template's early return, so a date past
    # the ceiling fails closed in the template repository too.
    policy = load_policy(root)
    if _is_template(root):
        return Verdict(red=list(lines), warned=[], note=None)
    baseline = read_baseline(root, policy.baseline)
    if today is None:
        today = run_today(root)
    left = collections.Counter(baseline["checks"].get(check, []) if baseline else [])
    red: List[str] = []
    matched: List[str] = []
    for line in lines:
        found = identity(line)
        if found is None:
            red.append(
                "%s — outside the `<file>:<line>: ` grammar, so no baseline entry "
                "can hold it; fix it" % line
            )
        elif baseline is None:
            red.append(
                "%s — no %s records it; run `make %s` once after `copier update`, "
                "or fix it" % (line, policy.baseline, RECORD_TARGET)
            )
        elif left[found] > 0:
            left[found] -= 1
            matched.append(line)
        else:
            red.append(
                "%s — %s does not record it, and `make %s` adds an entry only "
                "when .copier-answers.yml `_commit` moves past the commit the "
                "file records; fix it" % (line, policy.baseline, RECORD_TARGET)
            )
    red.extend(
        "%s: `%s` records `%s`, which no finding matches; delete the entry"
        % (policy.baseline, check, entry)
        for entry in sorted(left.elements())
    )
    if not matched:
        return Verdict(red=red, warned=[], note=None)
    if today >= policy.expires:
        red.extend(
            "%s — its grace in %s ended on %s (%s expiring_tier.expires); fix it"
            % (line, policy.baseline, policy.expires, _MANIFEST)
            for line in matched
        )
        return Verdict(red=red, warned=[], note=None)
    note = (
        "%d finding(s) of `%s` that %s records warn until %s (%s "
        "expiring_tier.expires) and are red from that day"
        % (len(matched), check, policy.baseline, policy.expires, _MANIFEST)
    )
    return Verdict(red=red, warned=matched, note=note)


def apply(
    check: str,
    lines: Sequence[str],
    root: str,
    today: Optional[datetime.date] = None,
) -> List[str]:
    """`judge`'s red lines, after one ExpiringTierWarning naming each line
    that warns, when any does."""
    verdict = judge(check, lines, root, today)
    if verdict.warned:
        warnings.warn(
            "\n".join([str(verdict.note)] + verdict.warned),
            ExpiringTierWarning,
            stacklevel=2,
        )
    return verdict.red


def baseline_findings(root: str) -> List[str]:
    """One line per check id the baseline records that `CHECKS` does not
    register; none when there is no baseline. Raises TierError as `judge`."""
    policy = load_policy(root)
    baseline = read_baseline(root, policy.baseline)
    if baseline is None:
        return []
    return [
        "%s: `%s` is not a check %s CHECKS registers; delete it"
        % (policy.baseline, check, _DATA_FILE)
        for check in sorted(baseline["checks"])
        if check not in expiring_tier_data.CHECKS
    ]
