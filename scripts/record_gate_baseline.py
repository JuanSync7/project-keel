"""
title: record_gate_baseline — write a generated project's gate baseline from what the checks see
kind: script
layer: n/a
summary: `make gate-baseline`, run in a generated project once after `copier update`. It runs the gate test of every check scripts/expiring_tier_data.py `CHECKS` registers under pytest, as a child process with an allowlisted environment (scripts/child_env.py `build_child_env`) killed after config/project.json `tests.child_timeout_seconds`, with tests/conftest.py's `--expiring-tier-record` option, so each check's findings come from the gate itself and never from a second reading of the tree. Each finding becomes its identity (scripts/expiring_tier.py `identity`), and the file config/project.json `expiring_tier.baseline` names is rewritten as `{"checks": {<check id>: [<identity>, ...]}, "commit": <_commit>}`, every registered check present and a retired one dropped. When the file already records the commit .copier-answers.yml `_commit` names, the new record may only shrink: an entry over the old count is refused by name and nothing is written, because the file grows only when an update brought new keel code. Exit 0 when it wrote the file or found it current; 1 (FAILURE) for refused growth; 2 (USAGE) in the template repository, which holds copier.yml and has no tier, or when .copier-answers.yml has no single `_commit`; 13 (NOTHING_JUDGED) when the run wrote no record or left out a registered check, so a gate test that stopped before it judged never records an empty baseline; 14 (CONFIG) for an `expiring_tier` block or a baseline scripts/expiring_tier.py refuses; any other pytest status is handed through. It does not stop a hand edit of the file, which review holds (docs/adr/keel/K-0027-a-project-s-own-code-warns-until-a-hard-date.md).
effect: writes
rerun: fixed-point
rerun_proof: test:tests/unit/scripts/test_record_gate_baseline.py
"""

import argparse
import collections
import json
import os
import subprocess
import sys
import tempfile

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_SCRIPTS)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import child_env  # noqa: E402
import config_loader  # noqa: E402
import expiring_tier  # noqa: E402
import expiring_tier_data  # noqa: E402
from exit_codes import ExitCode, finish, passthrough, report  # noqa: E402

__all__ = [
    "ANSWERS",
    "BaselineError",
    "answers_commit",
    "main",
    "next_baseline",
    "render",
    "run_checks",
]

ANSWERS = ".copier-answers.yml"
_COMMIT_KEY = "_commit:"
_TIMEOUT = ("tests", "child_timeout_seconds")
_TOOL = "record_gate_baseline"
# pytest's own statuses for a run that judged: every test passed, or some
# failed, which is what a project with unrecorded findings gives.
_JUDGED = (0, 1)


class BaselineError(Exception):
    """The project's answers file cannot name the commit to stamp."""


def answers_commit(root):
    """The one top-level `_commit` value of <root>/.copier-answers.yml, quotes
    stripped. Read by line: the default install carries no YAML parser, and
    copier writes the key as one `_commit: <value>` line."""
    path = os.path.join(root, ANSWERS)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        raise BaselineError("%s cannot be read (%s)" % (ANSWERS, exc)) from exc
    values = [
        line[len(_COMMIT_KEY) :].strip()
        for line in lines
        if line.startswith(_COMMIT_KEY)
    ]
    if len(values) != 1:
        raise BaselineError(
            "%s holds %d top-level `_commit` lines, not one" % (ANSWERS, len(values))
        )
    value = values[0]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    if not value:
        raise BaselineError("%s: `_commit` is empty" % ANSWERS)
    return value


def _identities(lines):
    found = (expiring_tier.identity(line) for line in lines)
    return sorted(i for i in found if i is not None)


def next_baseline(old, commit, record):
    """(doc, refused): the baseline to write from *record* ({check: lines})
    stamped *commit*, or (None, lines) naming each entry over *old*'s count
    when *old* is already stamped *commit*. A line outside the finding grammar
    is left out: the tier holds it red whatever the file records."""
    checks = {
        check: _identities(record[check]) for check in sorted(expiring_tier_data.CHECKS)
    }
    doc = {"checks": checks, "commit": commit}
    if old is None or old.get("commit") != commit:
        return doc, []
    refused = []
    for check, entries in sorted(checks.items()):
        over = collections.Counter(entries) - collections.Counter(
            old["checks"].get(check, [])
        )
        refused.extend(
            "%s: `%s` would gain `%s`, but the file already records "
            ".copier-answers.yml `_commit` %s, so it may only shrink; fix "
            "the finding" % (_TOOL, check, entry, commit)
            for entry in sorted(over.elements())
        )
    if refused:
        return None, refused
    return doc, []


def render(doc):
    """*doc* as canonical JSON: sorted keys, two-space indent, one newline."""
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def run_checks(root, record_path):
    """pytest's status after it ran every registered check's gate test in
    *root* and wrote what each was handed to *record_path*."""
    timeout = config_loader.resolve(
        config_loader.read(root),
        config_loader.rows(_TIMEOUT),
        config_loader.CONFIG_FILE,
    )[_TIMEOUT]
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--expiring-tier-record",
        record_path,
    ] + [expiring_tier_data.CHECKS[c] for c in sorted(expiring_tier_data.CHECKS)]
    done = subprocess.run(
        argv, cwd=root, env=child_env.build_child_env(root=root), timeout=timeout
    )
    return done.returncode


def _read_record(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    return record if isinstance(record, dict) else None


def main(argv=None, root=None, runner=run_checks):
    """Write the baseline of the project at *root*, the checks run by
    *runner* (root, record path) -> pytest status."""
    argparse.ArgumentParser(
        description="Record a generated project's gate findings in its "
        "expiring_tier.baseline after `copier update`"
    ).parse_args(argv)
    root = ROOT if root is None else str(root)
    if os.path.isfile(os.path.join(root, expiring_tier.TEMPLATE_MARK)):
        return report(
            ExitCode.USAGE,
            "%s: the template repository has no tier, every finding is red" % _TOOL,
            os.path.join(root, expiring_tier.TEMPLATE_MARK),
            "fix the finding; run `make %s` in a generated project"
            % expiring_tier.RECORD_TARGET,
        )
    try:
        commit = answers_commit(root)
    except BaselineError as exc:
        return report(
            ExitCode.USAGE,
            "%s: %s" % (_TOOL, exc),
            os.path.join(root, ANSWERS),
            "run it in a project copier generated, with its answers file intact",
        )
    try:
        policy = expiring_tier.load_policy(root)
        old = expiring_tier.read_baseline(root, policy.baseline)
    except expiring_tier.TierError as exc:
        return report(
            ExitCode.CONFIG,
            "%s: %s" % (_TOOL, exc),
            config_loader.CONFIG_FILE,
            "correct the named key or file, then rerun `make %s`"
            % expiring_tier.RECORD_TARGET,
        )
    with tempfile.TemporaryDirectory(prefix="keel-gate-baseline-") as scratch:
        record_path = os.path.join(scratch, "record.json")
        try:
            status = runner(root, record_path)
        except config_loader.ConfigError as exc:
            return report(
                ExitCode.CONFIG,
                "%s: %s" % (_TOOL, "; ".join(exc.lines)),
                config_loader.CONFIG_FILE,
                "set tests.child_timeout_seconds, then rerun `make %s`"
                % expiring_tier.RECORD_TARGET,
            )
        except subprocess.TimeoutExpired as exc:
            return report(
                ExitCode.FAILURE,
                "%s: the gate tests ran past %s seconds" % (_TOOL, exc.timeout),
                " ".join(exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd),
                "raise config/project.json tests.child_timeout_seconds or find "
                "what hangs, then rerun `make %s`" % expiring_tier.RECORD_TARGET,
            )
        if status not in _JUDGED:
            sys.stderr.write("%s: pytest ended with status %d\n" % (_TOOL, status))
            return passthrough(status)
        record = _read_record(record_path)
    missing = sorted(set(expiring_tier_data.CHECKS) - set(record or {}))
    if missing:
        return report(
            ExitCode.NOTHING_JUDGED,
            "%s: the run judged no finding for %s" % (_TOOL, ", ".join(missing)),
            ", ".join(expiring_tier_data.CHECKS[c] for c in missing),
            "run those tests and fix what stops them before they judge, then "
            "rerun `make %s`" % expiring_tier.RECORD_TARGET,
        )
    doc, refused = next_baseline(old, commit, record)
    if doc is None:
        for line in refused:
            sys.stderr.write(line + "\n")
        return report(
            ExitCode.FAILURE,
            "%s: %d finding(s) are new since the commit the file records"
            % (_TOOL, len(refused)),
            policy.baseline,
            "fix them; the file grows only after `copier update` moves `_commit`",
        )
    path = os.path.join(root, policy.baseline)
    text = render(doc)
    if old is not None and render(old) == text:
        print("gate baseline unchanged: %s" % policy.baseline)
        return ExitCode.SUCCESS
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote the gate baseline: %s" % policy.baseline)
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
