#!/usr/bin/env python3
"""
title: audit_dependencies — judge each frontend app's npm audit against the accepted risks config records
kind: script
layer: n/a
summary: `make fe-audit`'s doer. It audits each frontend app directory it is given (the Makefile passes FE_APPS) by running `npm audit --json` there under scripts/child_env.py `build_child_env` and config/project.json `dependency_audit.timeout_seconds`, or reads the saved report a `--report NAME=FILE` names instead, so a test never runs npm. A finding is one advisory a report's `via` entry names: its GHSA id (the last part of its `url`), its package and its severity. It judges each app against `dependency_audit.accepted.<app>`, rows of advisory id to package, reason and review_by day, on today's date (scripts/run_date.py `today`, read once at the entry point; a test hands in its own day). It fails (FAILURE) on three things, all listed before the one closing line: a finding at or above `dependency_audit.fail_at` that no row names with the same advisory and package; a row whose review_by day has passed; and a row whose advisory and package the app's report no longer holds, or whose app is not one it audited. A finding below fail_at that no row covers is listed and does not fail; a covered one is listed with its reason and day. A report that is not `npm audit --json` version 2 (an unknown severity, a `via` url with no advisory id) is USAGE, as is an app directory with no package.json or no package-lock.json, a saved report that cannot be read, and a `--report` name that is not an audited app; npm that cannot be started, runs past the timeout, exits other than 0 or 1, or answers an `error` object is BACKEND_ABSENT; a refused `dependency_audit` key, run date or child environment is CONFIG. Given no app and no row it says so and exits 0. It writes nothing.
effect: read-only
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import child_env  # noqa: E402
import config_loader  # noqa: E402
import run_date  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
_BLOCK = ("dependency_audit",)
_FIELDS = ("accepted", "fail_at", "timeout_seconds")
_WHERE = "config/project.json dependency_audit"
# The one argv the audit runs; a test points it at a program it controls.
AUDIT_ARGV = ("npm", "audit", "--json")
_REPORT_VERSION = 2
# npm audit's own statuses: 0 found nothing, 1 found something; any other is
# npm failing, not an answer.
_ANSWERED = (0, 1)
_GUIDE = "docs/guides/deterministic-checks.md, section 16"


class _Refused(Exception):
    """Nothing was judged; carries the report's three parts. Each subclass is
    one exit code, so the entry point names the member itself."""

    def __init__(self, what, on, next_step):
        super().__init__(what)
        self.what, self.on, self.next_step = what, on, next_step


class _Unusable(_Refused):
    """An argument, an app directory or a report cannot be used: USAGE."""


class _Unanswered(_Refused):
    """npm gave no answer to judge: BACKEND_ABSENT."""


class _Misconfigured(_Refused):
    """A setting, the run date or the child environment is refused: CONFIG."""


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="scripts/audit_dependencies.py",
        description="Judge each frontend app's npm audit against config/"
        "project.json dependency_audit.accepted: fail an uncovered finding at "
        "or above dependency_audit.fail_at, a row past its review_by day and a "
        "row whose advisory the audit no longer reports.",
    )
    parser.add_argument(
        "apps",
        nargs="*",
        metavar="APP_DIR",
        help="a frontend app directory, relative to the checkout; its name is "
        "the key under dependency_audit.accepted",
    )
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        metavar="NAME=FILE",
        help="judge app NAME from the saved `npm audit --json` output in FILE "
        "instead of running npm; repeatable",
    )
    return parser.parse_args(argv)


def _settings(root):
    keys = config_loader.rows(*[_BLOCK + (field,) for field in _FIELDS])
    values = config_loader.resolve(
        config_loader.read(root), keys, config_loader.CONFIG_FILE
    )
    return {field: values[_BLOCK + (field,)] for field in _FIELDS}


def _apps(root, dirs):
    """{name: absolute dir} for each app directory given, in name order."""
    apps = {}
    for given in dirs:
        path = os.path.normpath(os.path.join(root, given))
        name = os.path.basename(path)
        if name in apps:
            raise _Unusable(
                "two app directories share the name %s" % name,
                given,
                "name each app directory once; its name is its key under %s.accepted"
                % _WHERE,
            )
        if not os.path.isfile(os.path.join(path, "package.json")):
            raise _Unusable(
                "the app directory has no package.json",
                given,
                "pass a frontend app directory, as the Makefile's FE_APPS does",
            )
        apps[name] = path
    return dict(sorted(apps.items()))


def _saved(pairs, apps):
    """{name: path} of each `--report NAME=FILE`."""
    saved = {}
    for pair in pairs:
        name, sep, path = pair.partition("=")
        if not sep or not name or not path or name not in apps:
            raise _Unusable(
                "--report takes NAME=FILE for an app directory it is given",
                pair,
                "name one of: %s" % (", ".join(apps) or "no app was given"),
            )
        saved[name] = path
    return saved


def npm_audit(app_dir, root, timeout):
    """(status, stdout) of AUDIT_ARGV run in *app_dir* under the allowlisted
    environment, or _Unanswered when it cannot be started or runs
    past *timeout* seconds. The audit reads the lockfile and the registry, so
    the app needs no node_modules."""
    try:
        env = child_env.build_child_env(root=root)
    except child_env.ChildEnvError as exc:
        raise _Misconfigured(
            "the child environment is refused",
            str(exc),
            "fix config/project.json child_env, then rerun",
        ) from exc
    try:
        done = subprocess.run(
            list(AUDIT_ARGV),
            cwd=app_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except OSError as exc:
        raise _Unanswered(
            "%s could not be started (%s)" % (AUDIT_ARGV[0], exc.strerror or exc),
            app_dir,
            "install Node.js so npm is on PATH, then rerun",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise _Unanswered(
            "%s ran past %d seconds" % (" ".join(AUDIT_ARGV), timeout),
            app_dir,
            "check the registry is reachable, or raise %s.timeout_seconds" % _WHERE,
        ) from exc
    return done.returncode, done.stdout


def _report_of(name, app_dir, saved, root, timeout, run_audit):
    """The parsed audit report of one app, from its saved file or a run."""
    if name in saved:
        path = saved[name]
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise _Unusable(
                "the saved report cannot be read (%s)" % exc,
                path,
                "save it with `npm audit --json > FILE` in the app directory",
            ) from exc
        where = path
    else:
        if not os.path.isfile(os.path.join(app_dir, "package-lock.json")):
            raise _Unusable(
                "the app has no package-lock.json, so there is nothing to audit",
                app_dir,
                "run `make fe-install` to write it, then rerun",
            )
        status, out = run_audit(app_dir, root, timeout)
        where = "`%s` in %s" % (" ".join(AUDIT_ARGV), app_dir)
        text = out.decode("utf-8", "replace") if isinstance(out, bytes) else out
        if status not in _ANSWERED:
            raise _Unanswered(
                "npm audit exited %d, which is not an answer" % status,
                where,
                "run it by hand in the app directory to see why, then rerun",
            )
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise _Unusable(
            "the audit report is not JSON (%s)" % exc,
            where,
            "give it the output of `npm audit --json`",
        ) from exc
    if isinstance(doc, dict) and "error" in doc:
        raise _Unanswered(
            "npm audit answered an error, not a report",
            where,
            "check the registry is reachable from this host, then rerun",
        )
    return _findings(doc, where)


def _not_a_report(where, why):
    return _Unusable(
        "the audit report is not npm audit --json version %d (%s)"
        % (_REPORT_VERSION, why),
        where,
        "give it the output of `npm audit --json` from npm 7 or later",
    )


def _findings(doc, where):
    """The sorted set of (advisory, package, severity, title) a report holds."""
    if not isinstance(doc, dict) or doc.get("auditReportVersion") != _REPORT_VERSION:
        raise _not_a_report(where, "auditReportVersion")
    vulnerabilities = doc.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise _not_a_report(where, "vulnerabilities")
    found = set()
    for entry in vulnerabilities.values():
        via = entry.get("via") if isinstance(entry, dict) else None
        if not isinstance(via, list):
            raise _not_a_report(where, "an entry with no via list")
        # A string entry names another vulnerable package, which has its own
        # entry carrying the advisory; only a dict is an advisory.
        for item in via:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            advisory = (
                url.rstrip("/").rsplit("/", 1)[-1] if isinstance(url, str) else None
            )
            if not config_loader.is_advisory_id(advisory):
                raise _not_a_report(where, "a via url with no GHSA id: %r" % (url,))
            severity = item.get("severity")
            if severity not in config_loader.AUDIT_SEVERITIES:
                raise _not_a_report(where, "severity %r" % (severity,))
            package = item.get("name")
            if not isinstance(package, str) or not package:
                raise _not_a_report(where, "a via entry with no package name")
            title = item.get("title")
            found.add(
                (advisory, package, severity, title if isinstance(title, str) else "")
            )
    return sorted(found)


def _judge(apps, reports, accepted, fail_at, today):
    """(failure lines, listed lines) of every app's findings and every row."""
    floor = config_loader.AUDIT_SEVERITIES.index(fail_at)
    failures, listed = [], []
    for name in apps:
        rows = accepted.get(name, {})
        held = set()
        for advisory, package, severity, title in reports[name]:
            held.add((advisory, package))
            row = rows.get(advisory)
            if row is not None and row["package"] == package:
                listed.append(
                    "%s: accepted %s %s (%s) until %s: %s"
                    % (
                        name,
                        advisory,
                        package,
                        severity,
                        row["review_by"],
                        row["reason"],
                    )
                )
            elif config_loader.AUDIT_SEVERITIES.index(severity) >= floor:
                failures.append(
                    "%s: %s %s (%s) is at or above fail_at %s and no accepted row "
                    "covers it: %s"
                    % (name, advisory, package, severity, fail_at, title)
                )
            else:
                listed.append(
                    "%s: %s %s (%s) is below fail_at %s, so it is listed, not "
                    "failed: %s" % (name, advisory, package, severity, fail_at, title)
                )
        for advisory, row in sorted(rows.items()):
            if datetime.date.fromisoformat(row["review_by"]) < today:
                failures.append(
                    "%s: the accepted row for %s %s expired: review_by %s is before "
                    "%s"
                    % (
                        name,
                        advisory,
                        row["package"],
                        row["review_by"],
                        today.isoformat(),
                    )
                )
            if (advisory, row["package"]) not in held:
                failures.append(
                    "%s: the accepted row for %s %s is stale: the audit no longer "
                    "reports it" % (name, advisory, row["package"])
                )
    for name in sorted(set(accepted) - set(apps)):
        for advisory, row in sorted(accepted[name].items()):
            failures.append(
                "%s: the accepted row for %s %s is stale: %s is not an app this "
                "run audits" % (name, advisory, row["package"], name)
            )
    return failures, listed


def _run(root, args, settings, today, run_audit):
    apps = _apps(root, args.apps)
    saved = _saved(args.report, apps)
    accepted = settings["accepted"]
    if not apps and not accepted:
        sys.stdout.write(
            "no frontend app to audit and no accepted row, so nothing was judged\n"
        )
        return ExitCode.SUCCESS
    reports = {
        name: _report_of(
            name, path, saved, root, settings["timeout_seconds"], run_audit
        )
        for name, path in apps.items()
    }
    failures, listed = _judge(apps, reports, accepted, settings["fail_at"], today)
    for line in listed:
        sys.stdout.write(line + "\n")
    for line in failures:
        sys.stderr.write(line + "\n")
    if failures:
        return report(
            ExitCode.FAILURE,
            "%d dependency audit failure(s), listed above" % len(failures),
            ", ".join(sorted(set(apps) | set(accepted))),
            "fix the package; or accept the finding, or renew or remove the "
            "row, in %s.accepted with a reason and a review_by day (%s)"
            % (_WHERE, _GUIDE),
        )
    sys.stdout.write(
        "dependency audit: %d app(s) judged on %s, no failure\n"
        % (len(apps), today.isoformat())
    )
    return ExitCode.SUCCESS


def _today(root):
    try:
        return run_date.today(os.environ, run_date.load(root))
    except run_date.RunDateError as exc:
        raise _Misconfigured(
            "the run date is refused",
            str(exc),
            "fix config/project.json evidence.run_date or the variable it names",
        ) from exc


def main(argv=None, root=None, today=None, run_audit=None):
    """Audit and judge; *today* (a date) and *run_audit* (npm_audit's shape)
    are a test's own, else the run date and npm."""
    try:
        args = _parse(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        # argparse ends the process itself: status 0 after --help, and a usage
        # error it has already written to stderr otherwise.
        if not exc.code:
            return ExitCode.SUCCESS
        return report(
            ExitCode.USAGE,
            "argparse refused the arguments above",
            "the command line",
            "pass app directories and any --report NAME=FILE, as `make fe-audit` does",
        )
    root = os.path.abspath(ROOT if root is None else root)
    try:
        settings = _settings(root)
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the dependency audit settings are refused",
            "; ".join(exc.lines),
            "fix the dependency_audit block of config/project.json, then rerun",
        )
    try:
        if today is None:
            today = _today(root)
        return _run(root, args, settings, today, run_audit or npm_audit)
    except _Unusable as exc:
        return report(ExitCode.USAGE, exc.what, exc.on, exc.next_step)
    except _Unanswered as exc:
        return report(ExitCode.BACKEND_ABSENT, exc.what, exc.on, exc.next_step)
    except _Misconfigured as exc:
        return report(ExitCode.CONFIG, exc.what, exc.on, exc.next_step)


if __name__ == "__main__":
    finish(main())
