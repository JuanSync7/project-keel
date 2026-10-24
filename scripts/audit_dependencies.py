#!/usr/bin/env python3
"""
title: audit_dependencies — judge each frontend app's npm audit against the accepted risks config records
kind: script
layer: n/a
summary: `make fe-audit`'s doer. It audits each frontend app directory it is given (the Makefile passes FE_APPS) by running `npm audit --json` there, with `--include` naming dev, optional and peer so an .npmrc `omit=` cannot narrow it, under scripts/child_env.py `build_child_env` and config/project.json `dependency_audit.timeout_seconds`, or reads the saved report a `--report NAME=FILE` names instead, so a test never runs npm. A finding is one advisory a report's `via` entry names: its GHSA id (the last part of its `url`), its package and its severity. It judges each app against `dependency_audit.accepted.<app>`, rows of advisory id to package, reason and review_by day, on today's date (scripts/run_date.py `today`, read once at the entry point; a test hands in its own day). It fails (FAILURE) on four things, all listed before the one closing line: a finding at or above `dependency_audit.fail_at` that no row names with the same advisory and package; a row whose review_by day has passed; a row whose review_by is more than `dependency_audit.max_review_days` days after today, so an acceptance is renewed rather than parked; and a row whose advisory and package the app's report no longer holds, or whose app is not one it audited. A finding below fail_at that no row covers is listed and does not fail; a covered one is listed with its reason and day. It refuses a report it cannot trust rather than pass it: one that is not JSON, not `npm audit --json` version 2 (an unknown severity, a `via` url with no advisory id, a `via` item that is neither an advisory nor the name of another entry), whose `metadata.vulnerabilities` counts disagree with its entries, or whose `metadata.dependencies.total` is 0 or missing while the app's package.json declares a dependency, which is what an empty or root-only lockfile audits as. Such a report is USAGE from a saved file and BACKEND_ABSENT from a run, as is npm exiting 1 with no finding. An app directory with no package.json, one that is not a JSON object, no package-lock.json, a saved report that cannot be read and a `--report` name that is not an audited app are USAGE; npm that cannot be started, runs past the timeout, exits other than 0 or 1, or answers an `error` object is BACKEND_ABSENT, and the line carries npm's own diagnostic: the error's `message` (npm 11 writes `summary`) or npm's last stderr line, never all of stderr, and `<hidden>` in place of any text that names `_authToken` or a `//host/:_auth` key. A refused `dependency_audit` key, run date or child environment is CONFIG. Given no app and no row it says so and exits 0. It writes nothing in the tree; npm writes its own per-user log and cache.
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
_FIELDS = ("accepted", "fail_at", "max_review_days", "timeout_seconds")
_WHERE = "config/project.json dependency_audit"
_KEY_PREFIX = "dependency_audit"
# The one argv the audit runs; a test points it at a program it controls. Each
# --include names a dependency type `npm audit --omit` accepts, so a user or
# project .npmrc `omit=` cannot narrow the audit: npm lets include win.
AUDIT_ARGV = (
    "npm",
    "audit",
    "--json",
    "--include=dev",
    "--include=optional",
    "--include=peer",
)
# The package.json fields whose packages npm puts in the tree it audits.
_DECLARING_FIELDS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
# Text that can carry a registry credential, from .npmrc's `_authToken` and
# `//host/:_auth` keys; a diagnostic holding one is shown as _HIDDEN.
_TOKEN_MARK = "_authToken"
_AUTH_KEY = ":_auth"
_HIDDEN = "<hidden>"
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
    """(status, stdout, stderr) of AUDIT_ARGV run in *app_dir* under the allowlisted
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
    return done.returncode, done.stdout, done.stderr


def _text(data):
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else data


def _shown(text):
    """*text* on one line, or _HIDDEN when it could carry a registry token."""
    line = " ".join(text.split())
    if _TOKEN_MARK in line:
        return _HIDDEN
    for word in line.split():
        head, sep, _ = word.partition(_AUTH_KEY)
        if sep and "//" in head:
            return _HIDDEN
    return line


def _last_line(stderr):
    """npm's last stderr line, shown; never the whole stream, which carries
    its log path and every warning."""
    lines = [line for line in _text(stderr or "").splitlines() if line.strip()]
    return _shown(lines[-1]) if lines else "nothing on stderr"


def _error_text(error):
    """What npm's `error` object says: its `message`, else the `summary` npm
    11 writes, shown."""
    if isinstance(error, dict):
        for key in ("message", "summary"):
            if isinstance(error.get(key), str) and error[key].strip():
                return _shown(error[key])
    return "no message"


def _declares_dependencies(app_dir):
    """Whether the app's package.json names any package npm would audit."""
    path = os.path.join(app_dir, "package.json")
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        raise _Unusable(
            "the app's package.json cannot be read as JSON (%s)" % exc,
            path,
            "fix the app's package.json, then rerun",
        ) from exc
    if not isinstance(manifest, dict):
        raise _Unusable(
            "the app's package.json is not a JSON object",
            path,
            "fix the app's package.json, then rerun",
        )
    return any(manifest.get(field) for field in _DECLARING_FIELDS)


def _report_of(name, app_dir, saved, root, timeout, run_audit):
    """The findings of one app, from its saved file or a run. A report that
    cannot be judged is USAGE from a saved file, which the caller chose, and
    BACKEND_ABSENT from a run, where npm gave no usable answer."""
    declares = _declares_dependencies(app_dir)
    status, err = None, b""
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
        where = "app %s, the saved report %s" % (name, path)
        refuse, redo = _Unusable, "save it again with `npm audit --json > FILE`"
    else:
        if not os.path.isfile(os.path.join(app_dir, "package-lock.json")):
            raise _Unusable(
                "the app has no package-lock.json, so there is nothing to audit",
                app_dir,
                "run `make fe-install` to write it, then rerun",
            )
        status, out, err = run_audit(app_dir, root, timeout)
        where = "app %s, `%s` in %s" % (name, " ".join(AUDIT_ARGV), app_dir)
        refuse, redo = _Unanswered, "run it by hand in the app directory to see why"
        text = _text(out)
        if status not in _ANSWERED:
            raise _Unanswered(
                "npm audit exited %d, which is not an answer; npm's last stderr "
                "line: %s" % (status, _last_line(err)),
                where,
                "run it by hand in the app directory to see why, then rerun",
            )
    try:
        doc = json.loads(text)
    except ValueError as exc:
        why = "the audit report is not JSON (%s)" % exc
        if status is not None:
            why += "; npm's last stderr line: %s" % _last_line(err)
        raise refuse(why, where, redo + ", then rerun") from exc
    if isinstance(doc, dict) and "error" in doc:
        raise _Unanswered(
            "npm audit answered an error, not a report: %s" % _error_text(doc["error"]),
            where,
            "check the registry is reachable from this host, then rerun",
        )
    found = _findings(doc, where, refuse)
    _check_dependencies(doc, declares, where, refuse)
    if status == 1 and not found:
        raise _Unanswered(
            "npm audit exited 1, which says it found something, and its report "
            "holds no finding",
            where,
            "run it by hand in the app directory to see why, then rerun",
        )
    return found


def _not_a_report(where, why, refuse):
    return refuse(
        "the audit report is not npm audit --json version %d (%s)"
        % (_REPORT_VERSION, why),
        where,
        "give it the output of `npm audit --json` from npm 7 or later",
    )


def _check_dependencies(doc, declares, where, refuse):
    """Refuse a report that audited nothing while package.json declares a
    dependency: an empty or root-only lockfile audits as clean."""
    # _check_counts has already refused a report whose metadata is not an object.
    counted = doc["metadata"].get("dependencies")
    total = counted.get("total") if isinstance(counted, dict) else None
    if declares and (type(total) is not int or total < 1):
        raise refuse(
            "the report audited no dependency (metadata.dependencies.total is %r) "
            "and the app's package.json declares some" % (total,),
            where,
            "run `make fe-install` so package-lock.json holds the tree, then audit "
            "again",
        )


def _check_counts(doc, entries, where, refuse):
    """Refuse a report whose metadata.vulnerabilities disagrees with the
    entries it holds: npm counts one per entry, by the entry's severity."""
    metadata = doc.get("metadata")
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if not isinstance(counts, dict):
        raise _not_a_report(where, "no metadata.vulnerabilities", refuse)
    tally = dict.fromkeys(config_loader.AUDIT_SEVERITIES, 0)
    for severity in entries:
        tally[severity] += 1
    tally["total"] = len(entries)
    for key, want in tally.items():
        # type() and not isinstance: a JSON true is not a count of 1.
        if type(counts.get(key)) is not int or counts[key] != want:
            raise _not_a_report(
                where,
                "metadata.vulnerabilities.%s is %r and the report holds %d such "
                "entries" % (key, counts.get(key), want),
                refuse,
            )


def _findings(doc, where, refuse=_Unusable):
    """The sorted set of (advisory, package, severity, title) a report holds."""
    if not isinstance(doc, dict) or doc.get("auditReportVersion") != _REPORT_VERSION:
        raise _not_a_report(where, "auditReportVersion", refuse)
    vulnerabilities = doc.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise _not_a_report(where, "vulnerabilities", refuse)
    found = set()
    entries = []
    for entry in vulnerabilities.values():
        via = entry.get("via") if isinstance(entry, dict) else None
        if not isinstance(via, list):
            raise _not_a_report(where, "an entry with no via list", refuse)
        # A string item names another vulnerable package, which has its own
        # entry carrying the advisory; a dict is an advisory.
        for item in via:
            if isinstance(item, str):
                if item not in vulnerabilities:
                    raise _not_a_report(
                        where, "a via item naming no entry: %r" % (item,), refuse
                    )
                continue
            if not isinstance(item, dict):
                raise _not_a_report(
                    where,
                    "a via item that is neither an advisory nor a package: %r"
                    % (item,),
                    refuse,
                )
            url = item.get("url")
            advisory = (
                url.rstrip("/").rsplit("/", 1)[-1] if isinstance(url, str) else None
            )
            if not config_loader.is_advisory_id(advisory):
                raise _not_a_report(
                    where, "a via url with no GHSA id: %r" % (url,), refuse
                )
            severity = item.get("severity")
            if severity not in config_loader.AUDIT_SEVERITIES:
                raise _not_a_report(where, "severity %r" % (severity,), refuse)
            package = item.get("name")
            if not isinstance(package, str) or not package:
                raise _not_a_report(where, "a via entry with no package name", refuse)
            title = item.get("title")
            found.add(
                (advisory, package, severity, title if isinstance(title, str) else "")
            )
        severity = entry.get("severity")
        if severity not in config_loader.AUDIT_SEVERITIES:
            raise _not_a_report(where, "entry severity %r" % (severity,), refuse)
        entries.append(severity)
    _check_counts(doc, entries, where, refuse)
    return sorted(found)


def _judge(apps, reports, accepted, fail_at, max_review_days, today):
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
            review_by = datetime.date.fromisoformat(row["review_by"])
            ahead = (review_by - today).days
            if ahead > max_review_days:
                failures.append(
                    "%s: the accepted row for %s %s is parked: review_by %s is %d "
                    "days after %s, more than %s.max_review_days (%d)"
                    % (
                        name,
                        advisory,
                        row["package"],
                        row["review_by"],
                        ahead,
                        today.isoformat(),
                        _KEY_PREFIX,
                        max_review_days,
                    )
                )
            if review_by < today:
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
    failures, listed = _judge(
        apps,
        reports,
        accepted,
        settings["fail_at"],
        settings["max_review_days"],
        today,
    )
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
