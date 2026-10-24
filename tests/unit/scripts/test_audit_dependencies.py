"""
title: Unit — audit_dependencies (npm audit findings judged against the accepted risks in config)
kind: tests
layer: n/a
summary: scripts/audit_dependencies.py driven in process over saved `npm audit --json` reports shaped like a real one, in a project root the test builds from keel's own config/project.json with its own `dependency_audit` block, on a day the test hands in, so no test runs npm or reaches the network. Each failure kind fails on its own and names what failed: a finding at or above `fail_at` no row covers, a covered finding whose row names another package, a row past its review_by day, a row dated more than `max_review_days` after today (exactly that many passes, one more fails), a row whose advisory the report no longer holds, and a row naming an app not audited. A covered finding passes on its review_by day and is listed with its reason; a finding below `fail_at` is listed and does not fail, and lowering `fail_at` fails it. A report with no findings still judges every row. No app and no row exits 0 saying so. A report that is not version 2, one with an unknown severity, a via url with no advisory id, a via item that is neither an advisory nor an entry's name, counts that disagree with its entries, or no audited dependency while package.json declares one is USAGE from a saved file and BACKEND_ABSENT from a run; so is a run's output that is not JSON, and npm exiting 1 with no finding. An app with no package.json, an unreadable one or no package-lock.json, a `--report` name that is not an audited app and a bad flag are USAGE; npm that cannot start, overruns its timeout, exits 2, is killed by a signal or answers an error object is BACKEND_ABSENT, showing the error's message or summary, else the top-level message npm 11 writes for an unreachable registry (its real shape, with a placeholder host), else npm's last stderr line other than its log pointer and no other, and `<hidden>` for a line holding any of the credential shapes, each tested with its secret absent from the output. A 16 000-character line, "token" * 2000 and one hostile line per newer pattern (a prose key, a URL userinfo, a bare userinfo, an assigned value of several words, a scheme-less path, a dotted run, a word-number label) are redacted in under a second, timed in a child the test can kill; a diagnostic longer than `max_shown_chars` is cut, its advice still chosen from an E401 past the cut, dropping the word the cut lands in, and marked, and a shorter one is not; a quoted value the cut splits, bare or in JSON, is hidden from its quote. A secret word in prose keeps each word of its clause that scripts/audit_dependencies_data.py lists, in any case (`password required`, `PASSWORD REQUIRED`, `token is self-signed`, `"token expired` with its open quote, npm's own lines), and hides every other word, a cause word it does not list included, each listed word being tried beside a value, up to the sentence's end and past the clause bound; a value after `=` or `:` or a quoted one is hidden, an assigned one to the line's end or the next `name=` through any quote, comma, `;` or `name:` in it, and the cut marker follows it. A userinfo with a raw `@`, several `@`, no password or no scheme, a bare `user@` before a host included, is hidden up to its last `@`, while a package's `name@version` is kept. A scheme-less host (a dotted name, an IPv4 address, a name with a port, after `//` or `@` too) loses its path, a token as that host is hidden, and a file path or a host with nothing after its `/` is kept. The advice for `ERR_INVALID_URL` or `Invalid URL` names the registry URL, ahead of a 401 in the same text. The rule for a run of 20 or more characters keeps a URL's scheme, host and port, a bracketed IPv6 host among them, and the dotted host after ENOTFOUND or getaddrinfo, such as an AWS CodeArtifact host, with one trailing dot or none, a long mixed label with a word part such as `my-domain`, short runs between word parts, a word then a number (`acme2024-111122223333`) and a dotless label such as `nexus3`; a dotless token operand, a hyphenated one and a token beside a kept host are still hidden, and so is a token used as a URL's host, as one of its labels (a UUID included, a long label cut by hyphens into short token parts, hex ones too, and a token behind or between word parts), glued on past a `)`, or as the resolver's operand, and a mixed run that turns back to letters or opens with digits or one letter, and a host split at `=`, `+` or `%2B` is hidden whole in a URL and after ENOTFOUND, while `localhost` stays. A path after an IPv6 zone id or after a six-digit number where a port goes is hidden, and a zone id longer than 15 characters once a leading `%25` is dropped, raw escapes undecoded and at any length with the host kept, is `%<hidden>` while an interface name or number is kept. Each secret word the credential rule names hides the value of a key that holds only that word, so dropping any one word from the rule fails its own case. Each dependency field and both forms of `workspaces` count as declaring a dependency, and an empty one does not. The argv includes every dependency type an .npmrc could omit. A refused `dependency_audit` value is CONFIG.
"""

import copy
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import audit_dependencies  # noqa: E402
import audit_dependencies_data  # noqa: E402
from child_env import build_child_env  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit

_TODAY = datetime.date(2026, 10, 23)
_PARSER = "GHSA-rj75-hqrm-r3gf"
_HIGH = "GHSA-mrhx-c7xc-m3w5"
_LOW = "GHSA-238p-pmpm-9mq7"
# Stand-in secrets, built here so no file holds a password-shaped literal:
# one mixing letters and a digit, and one of capitalised letters only, the
# shape an open "plain word" rule would show.
_VALUE = "q7" + "zxwv"
_WORD_VALUE = "Qz" + "xwv"


def _via(advisory, package, severity, title):
    return {
        "source": 1,
        "name": package,
        "dependency": package,
        "title": title,
        "url": "https://github.com/advisories/" + advisory,
        "severity": severity,
        "cwe": ["CWE-400"],
        "cvss": {"score": 5.9, "vectorString": "CVSS:3.1/AV:N"},
        "range": "<9.9.9",
    }


def _audit(*advisories, dependencies=5):
    """An `npm audit --json` version 2 report holding *advisories*, each
    (advisory, package, severity), with the string `via` entry a dependent
    package carries, and the metadata npm derives from them: one count per
    entry's severity and the number of dependencies it audited."""
    vulnerabilities = {}
    for advisory, package, severity in advisories:
        entry = vulnerabilities.setdefault(
            package,
            {
                "name": package,
                "severity": severity,
                "isDirect": False,
                "via": [],
                "effects": ["parent-pkg"],
                "range": "<9.9.9",
                "nodes": ["node_modules/" + package],
                "fixAvailable": True,
            },
        )
        entry["via"].append(_via(advisory, package, severity, "title of " + advisory))
    if vulnerabilities:
        vulnerabilities["parent-pkg"] = {
            "name": "parent-pkg",
            "severity": "moderate",
            "isDirect": True,
            "via": sorted({a[1] for a in advisories}),
            "effects": [],
            "range": "*",
            "nodes": ["node_modules/parent-pkg"],
            "fixAvailable": False,
        }
    counts = dict.fromkeys(("info", "low", "moderate", "high", "critical"), 0)
    for entry in vulnerabilities.values():
        counts[entry["severity"]] += 1
    counts["total"] = len(vulnerabilities)
    return {
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities,
        "metadata": {
            "vulnerabilities": counts,
            "dependencies": {"prod": dependencies, "total": dependencies},
        },
    }


def _row(package, review_by="2027-01-21", reason="the fix is a breaking downgrade"):
    return {"package": package, "reason": reason, "review_by": review_by}


class _Project:
    def __init__(self, root):
        self.root = root

    def configure(self, **block):
        manifest = copy.deepcopy(_MANIFEST)
        manifest["dependency_audit"] = block
        (self.root / "config" / "project.json").write_text(json.dumps(manifest))

    def app(self, name, lockfile=True, manifest=None):
        app = self.root / "src" / "frontend" / name
        app.mkdir(parents=True, exist_ok=True)
        (app / "package.json").write_text(json.dumps(manifest or {}))
        if lockfile:
            (app / "package-lock.json").write_text("{}")
        return "src/frontend/" + name

    def saved(self, name, doc):
        path = self.root / ("%s-audit.json" % name)
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc))
        return "%s=%s" % (name, path)

    def main(self, argv, today=_TODAY, run_audit=None):
        return audit_dependencies.main(
            list(argv), root=str(self.root), today=today, run_audit=run_audit
        )


_MANIFEST = json.loads((_ROOT / "config" / "project.json").read_text())


@pytest.fixture
def project(tmp_path):
    (tmp_path / "config").mkdir()
    proj = _Project(tmp_path)
    proj.configure(accepted={}, fail_at="high", max_review_days=90, timeout_seconds=30)
    return proj


def _judged(
    project, capsys, doc, accepted, fail_at="high", today=_TODAY, cap=90, manifest=None
):
    project.configure(
        accepted=accepted,
        fail_at=fail_at,
        max_review_days=cap,
        timeout_seconds=30,
    )
    app = project.app("astro", manifest=manifest)
    code = project.main([app, "--report", project.saved("astro", doc)], today=today)
    out, err = capsys.readouterr()
    return code, out, err


def test_an_uncovered_high_finding_fails(project, capsys):
    doc = _audit((_HIGH, "zod", "high"))
    code, _, err = _judged(project, capsys, doc, {})
    assert code is ExitCode.FAILURE
    assert "astro: %s zod (high) is at or above fail_at high" % _HIGH in err
    assert "1 dependency audit failure(s)" in err


def test_an_uncovered_critical_finding_fails(project, capsys):
    doc = _audit(("GHSA-26w7-cxv4-gfx2", "astro", "critical"))
    code, _, err = _judged(project, capsys, doc, {})
    assert code is ExitCode.FAILURE
    assert "GHSA-26w7-cxv4-gfx2 astro (critical) is at or above" in err


def test_a_covered_finding_passes_on_its_review_day_and_is_listed(project, capsys):
    doc = _audit((_HIGH, "zod", "high"))
    accepted = {"astro": {_HIGH: _row("zod", review_by="2026-10-23")}}
    code, out, err = _judged(project, capsys, doc, accepted)
    assert code is ExitCode.SUCCESS, err
    assert (
        "astro: accepted %s zod (high) until 2026-10-23: the fix is a breaking "
        "downgrade" % _HIGH
    ) in out
    assert "1 app(s) judged on 2026-10-23, no failure" in out


def test_a_row_naming_another_package_does_not_cover_the_finding(project, capsys):
    doc = _audit((_HIGH, "zod", "high"))
    accepted = {"astro": {_HIGH: _row("not-zod")}}
    code, _, err = _judged(project, capsys, doc, accepted)
    assert code is ExitCode.FAILURE
    assert "%s zod (high) is at or above" % _HIGH in err
    assert "the accepted row for %s not-zod is stale" % _HIGH in err


def test_a_row_past_its_review_day_fails(project, capsys):
    doc = _audit((_PARSER, "postcss-selector-parser", "moderate"))
    accepted = {"astro": {_PARSER: _row("postcss-selector-parser", "2026-10-22")}}
    code, _, err = _judged(project, capsys, doc, accepted)
    assert code is ExitCode.FAILURE
    assert (
        "astro: the accepted row for %s postcss-selector-parser expired: review_by "
        "2026-10-22 is before 2026-10-23" % _PARSER
    ) in err


def test_a_review_day_exactly_max_review_days_out_passes(project, capsys):
    doc = _audit((_PARSER, "postcss-selector-parser", "moderate"))
    accepted = {"astro": {_PARSER: _row("postcss-selector-parser", "2027-01-21")}}
    code, out, err = _judged(project, capsys, doc, accepted, today=_TODAY, cap=90)
    assert code is ExitCode.SUCCESS, err
    assert (
        "accepted %s postcss-selector-parser (moderate) until 2027-01-21" % _PARSER
        in out
    )


def test_a_review_day_past_max_review_days_fails(project, capsys):
    doc = _audit((_PARSER, "postcss-selector-parser", "moderate"))
    accepted = {"astro": {_PARSER: _row("postcss-selector-parser", "2027-01-21")}}
    today = datetime.date(2026, 10, 22)
    code, _, err = _judged(project, capsys, doc, accepted, today=today, cap=90)
    assert code is ExitCode.FAILURE
    assert (
        "astro: the accepted row for %s postcss-selector-parser is parked: review_by "
        "2027-01-21 is 91 days after 2026-10-22, more than "
        "dependency_audit.max_review_days (90)" % _PARSER
    ) in err
    assert "1 dependency audit failure(s)" in err


def test_a_row_whose_advisory_is_gone_fails(project, capsys):
    doc = _audit((_LOW, "katex", "low"))
    accepted = {"astro": {_PARSER: _row("postcss-selector-parser")}}
    code, _, err = _judged(project, capsys, doc, accepted)
    assert code is ExitCode.FAILURE
    assert (
        "astro: the accepted row for %s postcss-selector-parser is stale: the audit "
        "no longer reports it" % _PARSER
    ) in err


def test_a_report_with_no_findings_still_judges_every_row(project, capsys):
    accepted = {"astro": {_PARSER: _row("postcss-selector-parser", "2026-01-01")}}
    code, _, err = _judged(project, capsys, _audit(), accepted)
    assert code is ExitCode.FAILURE
    assert "expired: review_by 2026-01-01" in err
    assert "is stale: the audit no longer reports it" in err
    assert "2 dependency audit failure(s)" in err


def test_a_report_with_no_findings_and_no_row_passes(project, capsys):
    code, out, err = _judged(project, capsys, _audit(), {})
    assert code is ExitCode.SUCCESS, err
    assert "1 app(s) judged" in out


def test_a_row_naming_an_app_not_audited_is_stale(project, capsys):
    accepted = {"react-vite": {_PARSER: _row("postcss-selector-parser")}}
    code, _, err = _judged(project, capsys, _audit(), accepted)
    assert code is ExitCode.FAILURE
    assert "react-vite is not an app this run audits" in err


def test_a_finding_below_fail_at_is_listed_not_failed(project, capsys):
    doc = _audit(
        (_PARSER, "postcss-selector-parser", "moderate"), (_LOW, "katex", "low")
    )
    code, out, err = _judged(project, capsys, doc, {})
    assert code is ExitCode.SUCCESS, err
    assert (
        "%s postcss-selector-parser (moderate) is below fail_at high" % _PARSER in out
    )
    assert "%s katex (low) is below fail_at high" % _LOW in out


def test_lowering_fail_at_fails_the_same_finding(project, capsys):
    doc = _audit(
        (_PARSER, "postcss-selector-parser", "moderate"), (_LOW, "katex", "low")
    )
    code, _, err = _judged(project, capsys, doc, {}, fail_at="moderate")
    assert code is ExitCode.FAILURE
    assert "(moderate) is at or above fail_at moderate" in err
    assert "katex" not in err


def test_every_failure_is_listed_before_the_closing_line(project, capsys):
    doc = _audit((_HIGH, "zod", "high"))
    accepted = {"astro": {_PARSER: _row("postcss-selector-parser", "2026-01-01")}}
    code, _, err = _judged(project, capsys, doc, accepted)
    assert code is ExitCode.FAILURE
    lines = err.strip().splitlines()
    assert len(lines) == 4
    assert lines[-1].startswith("3 dependency audit failure(s), listed above: astro;")


def test_no_app_and_no_row_says_nothing_was_judged(project, capsys):
    assert project.main([]) is ExitCode.SUCCESS
    assert "no frontend app to audit and no accepted row" in capsys.readouterr().out


def test_rows_with_no_app_are_stale(project, capsys):
    project.configure(
        accepted={"astro": {_PARSER: _row("postcss-selector-parser")}},
        fail_at="high",
        max_review_days=90,
        timeout_seconds=30,
    )
    assert project.main([]) is ExitCode.FAILURE
    assert "astro is not an app this run audits" in capsys.readouterr().err


@pytest.mark.parametrize(
    "doc, why",
    [
        ({"auditReportVersion": 1, "vulnerabilities": {}}, "auditReportVersion"),
        ([], "auditReportVersion"),
        ({"auditReportVersion": 2}, "vulnerabilities"),
        ({"auditReportVersion": 2, "vulnerabilities": {"x": {}}}, "no via list"),
        (
            {
                "auditReportVersion": 2,
                "vulnerabilities": {
                    "x": {
                        "via": [dict(_via(_HIGH, "x", "high", "t"), severity="severe")]
                    }
                },
            },
            "severity 'severe'",
        ),
        (
            {
                "auditReportVersion": 2,
                "vulnerabilities": {
                    "x": {
                        "via": [
                            dict(
                                _via(_HIGH, "x", "high", "t"),
                                url="https://example.invalid/1",
                            )
                        ]
                    }
                },
            },
            "no GHSA id",
        ),
        ("not json", "not JSON"),
    ],
)
def test_a_report_that_is_not_npm_audit_v2_is_usage(project, capsys, doc, why):
    code, _, err = _judged(project, capsys, doc, {})
    assert code is ExitCode.USAGE
    assert why in err


def test_an_app_with_no_package_json_is_usage(project, capsys):
    (project.root / "src" / "frontend" / "astro").mkdir(parents=True)
    assert project.main(["src/frontend/astro"]) is ExitCode.USAGE
    assert "no package.json" in capsys.readouterr().err


def test_an_app_with_no_lockfile_is_usage_naming_fe_install(project, capsys):
    app = project.app("astro", lockfile=False)
    assert project.main([app], run_audit=_never) is ExitCode.USAGE
    assert "make fe-install" in capsys.readouterr().err


def test_a_report_for_an_app_not_given_is_usage(project, capsys):
    app = project.app("astro")
    argv = [app, "--report", project.saved("react-vite", _audit())]
    assert project.main(argv) is ExitCode.USAGE
    assert "name one of: astro" in capsys.readouterr().err


def test_a_saved_report_that_cannot_be_read_is_usage(project, capsys):
    app = project.app("astro")
    argv = [app, "--report", "astro=%s" % (project.root / "absent.json")]
    assert project.main(argv) is ExitCode.USAGE
    assert "cannot be read" in capsys.readouterr().err


def test_a_bad_flag_is_usage(project, capsys):
    assert project.main(["--no-such-flag"]) is ExitCode.USAGE


def _never(app_dir, root, timeout):
    raise AssertionError("npm must not run")


def test_a_run_judges_npm_output_with_the_configured_timeout(project, capsys):
    app = project.app("astro")
    seen = []

    def run(app_dir, root, timeout):
        seen.append((app_dir, timeout))
        return 1, json.dumps(_audit((_HIGH, "zod", "high"))).encode(), b""

    assert project.main([app], run_audit=run) is ExitCode.FAILURE
    assert seen == [(str(project.root / "src" / "frontend" / "astro"), 30)]


@pytest.mark.parametrize(
    "status, out, why",
    [
        (2, "{}", "npm audit exited 2"),
        (-9, "{}", "npm audit exited -9"),
        (1, json.dumps({"error": {"code": "ENOTFOUND"}}), "answered an error"),
        (1, json.dumps(_audit()), "exited 1, which says it found something"),
        (0, "", "is not JSON"),
        (1, "npm warn config this is not json\n" + json.dumps(_audit()), "not JSON"),
        (0, json.dumps({"auditReportVersion": 1}), "auditReportVersion"),
    ],
)
def test_npm_that_does_not_answer_is_backend_absent(project, capsys, status, out, why):
    app = project.app("astro")
    code = project.main([app], run_audit=lambda *_: (status, out, b""))
    err = capsys.readouterr().err
    assert code is ExitCode.BACKEND_ABSENT, err
    assert why in err
    assert "npm audit --json --include=dev" in err


@pytest.mark.parametrize(
    "status, out, stderr, shown",
    [
        (2, "{}", b"npm error first line\nnpm error the last line\n", "the last line"),
        (-9, "", b"npm error killed\n", "npm error killed"),
        (0, "", b"npm warn one\nnpm warn unreadable\n", "npm warn unreadable"),
        (
            1,
            json.dumps({"error": {"code": "ENOLOCK", "summary": "needs a lockfile"}}),
            b"",
            "needs a lockfile",
        ),
        (
            1,
            json.dumps({"error": {"code": "E401", "message": "the registry said 401"}}),
            b"",
            "the registry said 401",
        ),
    ],
)
def test_npm_diagnostic_is_shown(project, capsys, status, out, stderr, shown):
    app = project.app("astro")
    code = project.main([app], run_audit=lambda *_: (status, out, stderr))
    err = capsys.readouterr().err
    assert code is ExitCode.BACKEND_ABSENT
    assert shown in err
    assert "first line" not in err
    assert "npm warn one" not in err


# What npm 11.12.1 writes when the registry cannot be reached, its host made a
# placeholder: the cause is a top-level `message`, and `error` is blank.
_UNREACHABLE_OUT = json.dumps(
    {
        "message": "request to http://registry.example.invalid/-/npm/v1/security/"
        "advisories/bulk failed, reason: getaddrinfo ENOTFOUND "
        "registry.example.invalid",
        "error": {"summary": "", "detail": ""},
    },
    indent=2,
)
_UNREACHABLE_ERR = (
    b"npm warn audit request to http://registry.example.invalid/-/npm/v1/security/"
    b"advisories/bulk failed, reason: getaddrinfo ENOTFOUND registry.example.invalid\n"
    b"npm error audit endpoint returned an error\n"
    b"npm error A complete log of this run can be found in: "
    b"/home/someone/.npm/_logs/2026-10-24T00_50_26_999Z-debug-0.log\n"
)


def test_an_unreachable_registry_shows_npm_top_level_message(project, capsys):
    app = project.app("astro")
    run = lambda *_: (1, _UNREACHABLE_OUT, _UNREACHABLE_ERR)  # noqa: E731
    assert project.main([app], run_audit=run) is ExitCode.BACKEND_ABSENT
    err = capsys.readouterr().err
    assert "getaddrinfo ENOTFOUND registry.example.invalid" in err
    assert "no message" not in err


def test_a_blank_error_falls_back_to_the_last_stderr_line(project, capsys):
    app = project.app("astro")
    out = json.dumps({"error": {"summary": "", "detail": ""}})
    run = lambda *_: (1, out, _UNREACHABLE_ERR)  # noqa: E731
    assert project.main([app], run_audit=run) is ExitCode.BACKEND_ABSENT
    err = capsys.readouterr().err
    assert "npm error audit endpoint returned an error" in err
    assert "no message" not in err


@pytest.mark.parametrize(
    "stderr",
    [
        _UNREACHABLE_ERR,
        b"npm error the cause\nnpm error A complete log of this run can be found "
        b"in:\nnpm error     /home/someone/.npm/_logs/x-debug-0.log\n",
    ],
)
def test_the_last_stderr_line_skips_npm_log_path(project, capsys, stderr):
    app = project.app("astro")
    run = lambda *_: (2, "{}", stderr)  # noqa: E731
    assert project.main([app], run_audit=run) is ExitCode.BACKEND_ABSENT
    err = capsys.readouterr().err
    assert "A complete log" not in err
    assert "_logs" not in err
    assert ("endpoint returned an error" in err) or ("the cause" in err)


# npm 11.12.1's answer to a registry that refuses the audit with 401, captured
# against a loopback server and its host made a placeholder: the cause is the
# top-level `message`, with no E401 code, and `error` is blank.
_UNAUTHORISED_OUT = json.dumps(
    {
        "message": 'Unable to authenticate, need: Bearer realm="https://registry'
        '.example.invalid/auth"',
        "method": "POST",
        "uri": "http://FAKEtok@registry.example.invalid/-/npm/v1/security/"
        "advisories/bulk",
        "statusCode": 401,
        "body": {"error": "Unable to authenticate"},
        "error": {"summary": "", "detail": ""},
    },
    indent=2,
)
# npm 11.12.1's answer when `.npmrc` gives the registry a `user:pass@`: npm
# masks the password itself, and the cause is still ENOTFOUND.
_MASKED_OUT = json.dumps(
    {
        "message": "request to http://someone:***@registry.example.invalid/-/npm/"
        "v1/security/advisories/bulk failed, reason: getaddrinfo ENOTFOUND "
        "registry.example.invalid",
        "error": {"summary": "", "detail": ""},
    },
    indent=2,
)


def test_a_401_shows_its_cause_and_names_the_credentials(project, capsys):
    app = project.app("astro")
    run = lambda *_: (1, _UNAUTHORISED_OUT, _UNREACHABLE_ERR)  # noqa: E731
    assert project.main([app], run_audit=run) is ExitCode.BACKEND_ABSENT
    err = capsys.readouterr().err
    assert 'Unable to authenticate, need: Bearer realm="' in err
    assert "check the registry credentials in .npmrc (values not shown)" in err
    assert "reachable" not in err
    assert "FAKEtok" not in err


@pytest.mark.parametrize("status_code", [401, 403])
def test_a_refusing_status_code_names_the_credentials(project, capsys, status_code):
    app = project.app("astro")
    out = json.dumps(
        {
            "message": "request refused",
            "statusCode": status_code,
            "error": {"summary": "", "detail": ""},
        }
    )
    assert project.main([app], run_audit=lambda *_: (1, out, b"")) is (
        ExitCode.BACKEND_ABSENT
    )
    err = capsys.readouterr().err
    assert "request refused" in err
    assert "check the registry credentials in .npmrc (values not shown)" in err


def test_a_masked_userinfo_keeps_the_cause(project, capsys):
    app = project.app("astro")
    run = lambda *_: (1, _MASKED_OUT, b"")  # noqa: E731
    assert project.main([app], run_audit=run) is ExitCode.BACKEND_ABSENT
    err = capsys.readouterr().err
    assert (
        "request to http://registry.example.invalid/<path hidden> failed, reason: "
        "getaddrinfo ENOTFOUND registry.example.invalid"
    ) in err
    assert "someone" not in err
    assert "check the registry is reachable" in err


@pytest.mark.parametrize(
    "said, advice",
    [
        ("npm error code E401", "check the registry credentials in .npmrc"),
        ("npm error code E403", "check the registry credentials in .npmrc"),
        ("npm error Unable to authenticate", "check the registry credentials"),
        ("npm error getaddrinfo ENOTFOUND host.invalid", "check the registry is"),
        ("npm error connect ECONNREFUSED 127.0.0.1:9", "check the registry is"),
        ("npm error ETIMEDOUT while asking", "check the registry is reachable"),
        ("npm error ESOMETHINGELSE", "run it by hand in the app directory"),
        # npm's words for a registry setting it cannot parse as a URL: no
        # request was made, so neither credentials nor reach is the cause.
        ("npm error code ERR_INVALID_URL", "check the registry URL in .npmrc"),
        ("npm error Invalid URL", "check the registry URL in .npmrc"),
        ("npm error code ERR_INVALID_URL npm error 401", "check the registry URL"),
    ],
)
def test_the_advice_follows_the_cause(project, capsys, said, advice):
    app = project.app("astro")
    run = lambda *_: (2, "{}", said.encode() + b"\n")  # noqa: E731
    assert project.main([app], run_audit=run) is ExitCode.BACKEND_ABSENT
    err = capsys.readouterr().err
    assert said.split()[-1] in err
    assert advice in err


@pytest.mark.parametrize(
    "error, top, shown, not_shown",
    [
        ({"message": "M-cause", "summary": "S-other"}, "T-other", "M-cause", "S-other"),
        ({"summary": "S-cause"}, "T-other", "S-cause", "T-other"),
        ({"summary": ""}, "T-cause", "T-cause", "nothing on stderr"),
    ],
)
def test_the_diagnostic_reads_message_then_summary_then_top_level(
    project, capsys, error, top, shown, not_shown
):
    app = project.app("astro")
    out = json.dumps({"message": top, "error": error})
    assert project.main([app], run_audit=lambda *_: (1, out, b"")) is (
        ExitCode.BACKEND_ABSENT
    )
    err = capsys.readouterr().err
    assert shown in err
    assert not_shown not in err


_UUID = "1b2c3d4e-0000-4abc-8def-123456789abc"
_GHP = "ghp_" + "FAKE0123456789abcdefghijABCDEFGHIJ0123"
_NPM = "npm_" + "FAKE0123456789abcdefghijABCDEFGHIJ"


@pytest.mark.parametrize(
    "line, secret",
    [
        # H1: a bare token as URL userinfo, and a token in a URL path.
        (
            "request to http://FAKEtok@registry.example.invalid/-/npm/v1/security/"
            "advisories/bulk failed, reason: getaddrinfo ENOTFOUND x.invalid",
            "FAKEtok",
        ),
        (
            "request to https://npm.fury.example.invalid/FAKEfurytok/-/npm/v1/x "
            "failed, reason: getaddrinfo ENOTFOUND npm.fury.example.invalid",
            "FAKEfurytok",
        ),
        (
            "GET https://someone:FAKEpass@registry.example.invalid/x ENOTFOUND",
            "FAKEpass",
        ),
        # M1: key and value with any separator, quoted or not.
        ("ENOTFOUND _auth = FAKEval", "FAKEval"),
        ('ENOTFOUND "_auth": "FAKEval"', "FAKEval"),
        ("ENOTFOUND _auth: FAKEval", "FAKEval"),
        ("ENOTFOUND _auth\tFAKEval", "FAKEval"),
        ("ENOTFOUND _auth=FAKEval", "FAKEval"),
        ("ENOTFOUND //registry.example.invalid/:_password=FAKEval", "FAKEval"),
        ("ENOTFOUND //registry.example.invalid/:_authToken=FAKEval", "FAKEval"),
        ("ENOTFOUND //registry.example.invalid/:_auth FAKEval", "FAKEval"),
        ("ENOTFOUND keyfile=FAKEval", "FAKEval"),
        ("ENOTFOUND _AUTHTOKEN=FAKEval", "FAKEval"),
        ("ENOTFOUND bad _authToken FAKEval", "FAKEval"),
        # M1: an authorization scheme and its value.
        ("ENOTFOUND Authorization: Basic FAKEval", "FAKEval"),
        ("ENOTFOUND Authorization: Bearer FAKEval", "FAKEval"),
        ('ENOTFOUND Bearer="FAKEval"', "FAKEval"),
        ("ENOTFOUND bearer:FAKEval", "FAKEval"),
        ("ENOTFOUND BEARER FAKEval", "FAKEval"),
        # M1: userinfo with no scheme.
        ("ENOTFOUND someone:FAKEval@registry.example.invalid", "FAKEval"),
        # M1: the generic token shape.
        ("ENOTFOUND legacy token " + _UUID + " refused", _UUID),
        ("ENOTFOUND " + _GHP + " refused", _GHP),
        ("ENOTFOUND " + _NPM + " refused", _NPM),
    ],
)
def test_a_credential_is_hidden_and_the_cause_kept(project, capsys, line, secret):
    app = project.app("astro")
    stderr = ("npm error " + line + "\n").encode()
    code = project.main([app], run_audit=lambda *_: (2, "{}", stderr))
    err = capsys.readouterr().err
    assert code is ExitCode.BACKEND_ABSENT
    assert secret not in err
    # A URL's rule writes "<path hidden>"; every other rule writes "<hidden>".
    assert "hidden>" in err
    assert "ENOTFOUND" in err


# Each secret word section 16 names, in a key that holds that word and no
# other, so rule (b) alone hides the value: dropping a word shows its value.
# Each value is shorter than rule (d)'s 20 characters, so (d) cannot hide it.
_KEY_OF_WORD = {
    "auth": "_auth",
    "token": "npmToken",
    "password": "password",
    "passwd": "passwd",
    "secret": "client_secret",
    "key": "apikey",
    "credential": "credentials",
    "cookie": "Cookie",
}


@pytest.mark.parametrize("word", sorted(_KEY_OF_WORD))
def test_each_documented_secret_word_hides_its_value(word):
    key = _KEY_OF_WORD[word]
    others = [w for w in _KEY_OF_WORD if w != word and w in key.lower()]
    assert word in key.lower() and not others, (key, others)
    assert audit_dependencies._redacted("ENOTFOUND %s=FAKEval" % key) == (
        "ENOTFOUND %s=<hidden>" % key
    )


@pytest.mark.parametrize(
    "text, shown",
    [
        (
            'Unable to authenticate, need: Bearer realm="https://r.example.invalid/a"',
            'Unable to authenticate, need: Bearer realm="https://r.example.invalid/'
            '<path hidden>"',
        ),
        (
            "http://registry.example.invalid:8080",
            "http://registry.example.invalid:8080",
        ),
        ("npm error audit endpoint returned an error", None),
    ],
)
def test_only_the_credential_span_is_rewritten(text, shown):
    assert audit_dependencies._redacted(text) == (text if shown is None else shown)


# A secret word, then linking words, then the value: the value is what a
# reader must not see, so the linking word is never the span hidden in its
# place. Each value is shorter than rule (d)'s 20 characters.
@pytest.mark.parametrize(
    "text, shown",
    [
        ("ENOTFOUND password is FAKEval9", "ENOTFOUND password is <hidden>"),
        ("ENOTFOUND the password was FAKEval9", "ENOTFOUND the password was <hidden>"),
        ("ENOTFOUND token: FAKEval9", "ENOTFOUND token: <hidden>"),
        ("ENOTFOUND the token is now FAKEval9", "ENOTFOUND the token is now <hidden>"),
        (
            "ENOTFOUND secret set to FAKEval9 here",
            "ENOTFOUND secret set to <hidden>",
        ),
        ("ENOTFOUND password is: FAKEval9", "ENOTFOUND password is: <hidden>"),
        ("ENOTFOUND PASSWORD WAS FAKEval9", "ENOTFOUND PASSWORD WAS <hidden>"),
        # A third linking word, a capitalised word with a mark, and a word
        # between the secret word and its value: each is a word no rule names.
        (
            "npm error the password was set to " + _VALUE,
            "npm error the password was set to <hidden>",
        ),
        ("npm error password is %s!" % _WORD_VALUE, "npm error password is <hidden>"),
        (
            "npm error the password for bob is " + _VALUE,
            "npm error the password for <hidden> is <hidden>",
        ),
        # The clause ends with its sentence, and a word past its end is kept.
        (
            "npm error password %s. Then npm stopped" % _WORD_VALUE,
            "npm error password <hidden> Then npm stopped",
        ),
        # A clause past CLAUSE_WORDS has the rest of its sentence hidden whole.
        (
            "npm error password " + "is " * 20 + _VALUE + ". Then npm stopped",
            "npm error password " + "is " * 16 + "<hidden> Then npm stopped",
        ),
    ],
    ids=[
        "is",
        "was",
        "colon",
        "is-now",
        "set-to",
        "is-colon",
        "upper",
        "third-linking-word",
        "capitalised-mark",
        "word-between",
        "sentence-end",
        "clause-bound",
    ],
)
def test_a_secret_word_in_prose_hides_its_value(text, shown):
    assert audit_dependencies._redacted(text) == shown


# A clause opens right after the secret word whatever follows it: a comma, a
# possessive, a bracket, a slash or a dash. A second secret word in
# any wrapping opens its own clause. Each form is "{}" around the value.
@pytest.mark.parametrize(
    "form, kept",
    [
        ("npm error the password, {}, was rejected", ["the password", "was rejected"]),
        ("npm error the password's value {}", ["the password"]),
        ("npm error [token]: {}", ["[token"]),
        ("npm error (password) {}", ["(password"]),
        ("npm error password/ {}", ["password"]),
        ("npm error the password\u2014{}", ["the password"]),
        ("npm error the password is (token) {} here", ["the password is", "(token"]),
    ],
    ids=[
        "comma",
        "possessive",
        "bracket-colon",
        "parenthesis",
        "slash",
        "dash",
        "second-secret-word",
    ],
)
def test_a_mark_after_a_secret_word_still_opens_its_clause(form, kept):
    shown = audit_dependencies._redacted(form.format(_VALUE))
    assert _VALUE not in shown and "<hidden>" in shown, shown
    for words in kept:
        assert words in shown, shown


# A clause keeps a word that opens with a URL (a) rewrote; text glued in
# front of the URL is a word of its own and is judged, and a word after the
# URL is still in the clause.
@pytest.mark.parametrize(
    "glue",
    [",", "(", "", "-", "="],
    ids=["comma", "parenthesis", "letters", "hyphen", "equals"],
)
def test_a_value_glued_to_a_url_is_hidden(glue):
    text = "npm error token %s%shttps://r.example.invalid/x %s" % (_VALUE, glue, _VALUE)
    shown = audit_dependencies._redacted(text)
    assert _VALUE not in shown, shown
    assert "https://r.example.invalid/<path hidden>" in shown, shown


# A URL opens with a scheme npm uses: http and https for a registry or a
# proxy, the socks schemes @npmcli/agent hands to socks-proxy-agent, and the
# git, ssh and file schemes npm-package-arg reads in a dependency spec. No
# other letters run into the scheme, so text before it is no part of it.
@pytest.mark.parametrize(
    "scheme",
    [
        "http",
        "https",
        "HTTPS",
        "socks",
        "socks4",
        "socks4a",
        "socks5",
        "socks5h",
        "git",
        "git+http",
        "git+https",
        "git+ssh",
        "git+file",
        "ssh",
        "file",
    ],
)
def test_a_url_opens_with_a_scheme_npm_uses(scheme):
    text = "request to %s%s://registry.example.invalid/x failed" % (_VALUE, scheme)
    assert audit_dependencies._redacted(text) == (
        "request to %s%s://registry.example.invalid/<path hidden> failed"
        % (_VALUE, scheme)
    )


# Bounding the scheme must show no userinfo or path: after any other `://`
# both are lost as in a URL npm reaches.
@pytest.mark.parametrize(
    "userinfo", ["u:%s@" % _VALUE, _VALUE + "@", ""], ids=["pair", "user", "none"]
)
def test_a_scheme_npm_does_not_use_loses_its_userinfo_and_path(userinfo):
    text = "request to gopher://%sregistry.example.invalid/%s failed" % (
        userinfo,
        _VALUE,
    )
    assert audit_dependencies._redacted(text) == (
        "request to gopher://registry.example.invalid/<path hidden> failed"
    )


def test_a_value_glued_to_a_scheme_npm_does_not_use_is_hidden_in_a_clause():
    text = "token %sgopher://registry.example.invalid/x" % _VALUE
    assert audit_dependencies._redacted(text) == "token <hidden>"


# A URL's userinfo is everything before the last `@` of its authority, so a
# raw `@` in a password shows no part of it, and the host after it stays.
@pytest.mark.parametrize(
    "text, shown",
    [
        (
            "request to https://someone:FAKE@pass@registry.example.invalid/x failed",
            "request to https://registry.example.invalid/<path hidden> failed",
        ),
        (
            "request to https://so@meone:FA@KE@pass@registry.example.invalid:8080/x",
            "request to https://registry.example.invalid:8080/<path hidden>",
        ),
        (
            "request to https://FAKEtok@@registry.example.invalid failed",
            "request to https://registry.example.invalid failed",
        ),
        (
            "request to https://someone@registry.example.invalid/x failed",
            "request to https://registry.example.invalid/<path hidden> failed",
        ),
        (
            "ENOTFOUND someone:FAKE@pass@registry.example.invalid",
            "ENOTFOUND <hidden>@registry.example.invalid",
        ),
        # With no scheme and no password, as in a URL: before a host.
        (
            "request to %s@registry.example/pkg failed" % _VALUE,
            "request to <hidden>@registry.example/<path hidden> failed",
        ),
        (
            "ENOTFOUND %s@registry.example.invalid" % _VALUE,
            "ENOTFOUND <hidden>@registry.example.invalid",
        ),
        (
            "fetch %s@%s@localhost:4873/pkg" % (_VALUE[:2], _VALUE[2:]),
            "fetch <hidden>@localhost:4873/<path hidden>",
        ),
        (
            "fetch %s!%s@10.0.0.5/pkg" % (_VALUE[:2], _VALUE[2:]),
            "fetch <hidden>@10.0.0.5/<path hidden>",
        ),
    ],
    ids=[
        "raw-at",
        "many-ats-port",
        "double-at",
        "no-password",
        "scheme-less",
        "scheme-less-no-password",
        "scheme-less-no-path",
        "scheme-less-raw-at-port",
        "scheme-less-ipv4",
    ],
)
def test_a_raw_at_in_userinfo_hides_up_to_the_last_at(text, shown):
    assert audit_dependencies._redacted(text) == shown


# After whitespace or a linking word alone, a secret word is prose: a word of
# audit_dependencies_data's closed vocabulary, in any case, is kept. A quote
# before the secret word opens no value. The last three are npm's own lines.
@pytest.mark.parametrize(
    "text",
    [
        'npm error "token expired',
        "npm error password required",
        "npm error Password Required.",
        "npm error PASSWORD REQUIRED",
        "npm error token expired",
        "npm error token is self-signed",
        "npm error the token is invalid",
        "npm error the token has expired, please try logging in again",
        "npm error Unable to authenticate, your authentication token seems to be "
        "invalid.",
        "npm error Incorrect or missing password.",
        "npm error This operation requires a one-time password from your "
        "authenticator.",
    ],
    ids=[
        "open-quote",
        "required",
        "capitalised",
        "upper",
        "expired",
        "self-signed",
        "is-invalid",
        "has",
        "npm-bearer",
        "npm-basic",
        "npm-otp",
    ],
)
def test_a_vocabulary_word_after_a_secret_word_is_kept(text):
    assert audit_dependencies._redacted(text) == text


# npm-registry-fetch writes an HTTP error as `status statusText - METHOD uri`,
# and the secret word `auth` inside `Unauthorized` opens a clause there, so
# the method is a vocabulary word and stays; a value later in the line is
# still hidden.
@pytest.mark.parametrize("method", ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
def test_an_http_error_line_keeps_its_method(method):
    value = "FAKE" + "val" + "42"
    text = (
        "401 Unauthorized - %s http://127.0.0.1:4873/-/npm/v1/security - "
        "the password was set to %s" % (method, value)
    )
    assert audit_dependencies._redacted(text) == (
        "401 Unauthorized - %s http://127.0.0.1:4873/<path hidden> - "
        "the password was set to <hidden>" % method
    )


# A word of one to three marks and nothing else, such as npm-registry-fetch's
# ` - ` separator, is kept; a fourth mark makes it a value like any other.
@pytest.mark.parametrize(
    "marks, kept",
    [
        ("-", True),
        ("--", True),
        ("-/-", True),
        ("|", True),
        ("----", False),
        ("!#%&", False),
    ],
    ids=["one", "two", "three", "bar", "four", "four-mixed"],
)
def test_a_word_of_three_marks_or_fewer_is_kept(marks, kept):
    shown = audit_dependencies._redacted("npm error token %s %s" % (marks, _VALUE))
    hidden = marks + " <hidden>" if kept else "<hidden>"
    assert shown == "npm error token " + hidden


# A sentence ends at `.`, `!` or `?` only when the next word opens with a
# capital or the text ends, and a period after a single letter (`e.g.`) ends
# none; a word of marks alone ends none either. Each case's clause runs on.
# A value that opens with a capital after a real end is the next sentence,
# the rule's stated cost, so the last two cases try only a lower-case one.
@pytest.mark.parametrize(
    "form, values",
    [
        ("the password e.g. %s was rejected", (_VALUE, _WORD_VALUE)),
        ("the password, i.e. %s", (_VALUE, _WORD_VALUE)),
        ("the password set at 9 a.m. %s", (_VALUE, _WORD_VALUE)),
        ("the password . %s", (_VALUE, _WORD_VALUE)),
        ("the password is required. %s next", (_VALUE,)),
        ("the password is required? %s", (_VALUE,)),
    ],
    ids=["e-g", "i-e", "a-m", "lone-period", "lower-case-next", "question-lower"],
)
def test_a_period_that_ends_no_sentence_leaves_the_clause_open(form, values):
    for value in values:
        shown = audit_dependencies._redacted(form % value)
        assert value not in shown
        assert "<hidden>" in shown


@pytest.mark.parametrize(
    "line",
    [
        "the password is required. Run npm login",
        "the password is required.",
        "the password is required! Run npm login",
    ],
    ids=["capital-next", "text-end", "exclamation"],
)
def test_a_sentence_end_closes_the_clause(line):
    assert audit_dependencies._redacted(line) == line


# The cost of a closed vocabulary: a cause word it does not hold is hidden.
# The advice reads npm's raw text, so it is the same either way.
def test_a_cause_word_outside_the_vocabulary_is_hidden():
    assert audit_dependencies._redacted("npm error the keyboard is broken") == (
        "npm error the keyboard is <hidden>"
    )


@pytest.mark.parametrize(
    "word",
    sorted(audit_dependencies_data.LINKING_WORDS)
    + sorted(audit_dependencies_data.CAUSE_WORDS),
)
def test_each_vocabulary_word_is_kept_and_a_value_beside_it_hidden(word):
    assert audit_dependencies._redacted("npm error token %s FAKEval" % word) == (
        "npm error token %s <hidden>" % word
    )


# The same places still hide a value: after `=` or `:` whatever it is, since
# an assignment states one, and after prose any value that is no plain word
# or that is quoted.
@pytest.mark.parametrize(
    "text, shown",
    [
        ("npm error token: expired", "npm error token: <hidden>"),
        ("npm error password=required", "npm error password=<hidden>"),
        ("npm error password " + _VALUE, "npm error password <hidden>"),
        ("npm error password is FAKEval", "npm error password is <hidden>"),
        ('npm error password "hunter"', "npm error password <hidden>"),
        ('npm error password "correct horse', "npm error password <hidden>"),
        ("npm error password Hunter-two", "npm error password <hidden>"),
        # A quoted vocabulary word is still a value.
        ('npm error password "required"', "npm error password <hidden>"),
    ],
    ids=[
        "colon",
        "equals",
        "digit",
        "mixed-case",
        "quoted",
        "open-quote",
        "hyphen",
        "quoted-word",
    ],
)
def test_a_value_that_is_no_plain_word_is_still_hidden(text, shown):
    assert audit_dependencies._redacted(text) == shown


# After `=` or `:` a value runs to the line's end or to the next `name=`
# after a space, and all of it is hidden: a passphrase has spaces in it, and
# a quote, comma, `;` or `name:` can sit inside one. A `name=` after `; ` or
# `, ` is a cookie's next pair, so it is hidden too. A quoted value hides at
# least to its closing quote.
@pytest.mark.parametrize(
    "text, shown",
    [
        ("npm error password=my secret phrase", "npm error password=<hidden>"),
        ("npm error token: correct horse battery", "npm error token: <hidden>"),
        ("password=my secret phrase, then npm stopped", "password=<hidden>"),
        ("password=my secret; retry", "password=<hidden>"),
        ("password=my secret user=bob", "password=<hidden> user=bob"),
        ("password=my secret username: bob", "password=<hidden>"),
        ("password=my secret token=other words", "password=<hidden> token=<hidden>"),
        ('password=my secret "quoted"', "password=<hidden>"),
        ("password=pa'ss word", "password=<hidden>"),
        ("password=ab," + _VALUE, "password=<hidden>"),
        ("password=abc %s:x" % _VALUE, "password=<hidden>"),
        ("cookie=a=b; " + _VALUE, "cookie=<hidden>"),
        ("cookie=a=b; session=FAKEval", "cookie=<hidden>"),
        ('password="a b" user=bob', "password=<hidden> user=bob"),
        ('password="a user=b" c', "password=<hidden>"),
        # Prose keeps the word after its value: only an assignment runs on.
        (
            "npm error password %s was refused" % _VALUE,
            "npm error password <hidden> was refused",
        ),
    ],
    ids=[
        "equals",
        "colon",
        "comma",
        "semicolon",
        "next-key",
        "next-key-colon",
        "next-secret",
        "quote",
        "inner-quote",
        "inner-comma",
        "inner-colon-key",
        "cookie-pair",
        "cookie-next-pair",
        "quoted-then-key",
        "quoted-key-inside",
        "prose",
    ],
)
def test_an_assigned_value_runs_to_the_line_end_or_the_next_key(text, shown):
    assert audit_dependencies._redacted(text) == shown


# The cut marker is written after the redaction, so the value's run never
# reaches it.
def test_the_cut_marker_follows_a_hidden_value():
    assert audit_dependencies._shown("password=my secret phrase", 18) == (
        "password=<hidden> <cut to 18 characters>"
    )


# An AWS CodeArtifact registry's host: its first label mixes letters and
# digits over 20 characters, the shape rule (d) hides elsewhere.
_ARTIFACT_HOST = "my-domain-111122223333.d.codeartifact.invalid"


# A host with no scheme loses its path as a URL does: a dotted name ending in
# a letter label, an IPv4 address, or any name with a port, at the start of
# a word, after `//` or after a userinfo's `@`.
@pytest.mark.parametrize(
    "text, shown",
    [
        (
            "request to registry.example/s3cr3t/pkg failed",
            "request to registry.example/<path hidden> failed",
        ),
        (
            "GET registry.npmjs.org/-/npm/v1/security/advisories/bulk",
            "GET registry.npmjs.org/<path hidden>",
        ),
        ("fetch 10.0.0.5:4873/s3cr3t/pkg", "fetch 10.0.0.5:4873/<path hidden>"),
        ("fetch 10.0.0.5/s3cr3t", "fetch 10.0.0.5/<path hidden>"),
        ("fetch localhost:4873/s3cr3t", "fetch localhost:4873/<path hidden>"),
        (
            "//registry.example/s3cr3t/:_authToken=x",
            "//registry.example/<path hidden>",
        ),
        (
            "user:pw@registry.example/s3cr3t/pkg",
            "<hidden>@registry.example/<path hidden>",
        ),
        (
            "fetch %s/npm/repo/s3cr3t" % _ARTIFACT_HOST,
            "fetch %s/<path hidden>" % _ARTIFACT_HOST,
        ),
        # A token as the host is still hidden, by rule (d).
        (
            "fetch FAKE0123456789abcdefghij.example/s3cr3t",
            "fetch <hidden>/<path hidden>",
        ),
    ],
    ids=[
        "name",
        "registry",
        "ipv4-port",
        "ipv4",
        "name-port",
        "npmrc-key",
        "userinfo",
        "artifact",
        "token-host",
    ],
)
def test_a_host_with_no_scheme_loses_its_path(text, shown):
    assert audit_dependencies._redacted(text) == shown


# A file path is no host: its first part has no dot, or the dotted part sits
# inside the path, so it is kept, as is a host with nothing after its `/`. A
# package's `name@version` is no userinfo, since a version is no host.
@pytest.mark.parametrize(
    "text",
    [
        "npm error path /work/app/package.json",
        "npm error lodash@4.17.21 and @types/node@20.1.0 are vulnerable",
        "npm error react@latest",
        "reading src/frontend/astro/package-lock.json",
        "see node_modules/foo/bar.js/x",
        "npm@10.2.4 /usr/bin",
        "request to registry.example/ failed",
        "at ./lib/x.js",
    ],
    ids=[
        "absolute",
        "package-versions",
        "dist-tag",
        "relative",
        "dotted-inside",
        "version",
        "bare-slash",
        "dot-slash",
    ],
)
def test_a_file_path_is_no_host(text):
    assert audit_dependencies._redacted(text) == text


@pytest.mark.parametrize(
    "text, shown",
    [
        # The URL rule keeps scheme, host and port, so rule (d) leaves them.
        (
            "request to https://%s/npm/repo/-/npm/v1/security/advisories/bulk "
            "failed" % _ARTIFACT_HOST,
            "request to https://%s/<path hidden> failed" % _ARTIFACT_HOST,
        ),
        (
            "request to https://%s:443/npm/repo failed" % _ARTIFACT_HOST,
            "request to https://%s:443/<path hidden> failed" % _ARTIFACT_HOST,
        ),
        # The operand of ENOTFOUND and of getaddrinfo names the host.
        (
            "reason: getaddrinfo ENOTFOUND %s" % _ARTIFACT_HOST,
            None,
        ),
        ("npm error ENOTFOUND %s" % _ARTIFACT_HOST, None),
        ("getaddrinfo EAI_AGAIN %s" % _ARTIFACT_HOST, None),
        # A fully qualified name keeps its one trailing dot, in both places.
        ("npm error ENOTFOUND %s." % _ARTIFACT_HOST, None),
        (
            "request to https://%s./npm/repo failed" % _ARTIFACT_HOST,
            "request to https://%s./<path hidden> failed" % _ARTIFACT_HOST,
        ),
        # A host that is no DNS name and mixes no digit in, such as a local
        # registry's, is no token and stays.
        (
            "request to http://localhost:4873/npm/repo failed",
            "request to http://localhost:4873/<path hidden> failed",
        ),
        # L1: a bracketed IPv6 host keeps host and port and loses its path.
        (
            "request to http://[::1]:8080/s3cr3t/pkg failed",
            "request to http://[::1]:8080/<path hidden> failed",
        ),
        # Only those spans are exempt: a token beside them is still hidden.
        (
            "ENOTFOUND %s refused %s"
            % (_ARTIFACT_HOST, "npm_FAKE0123456789abcdefghij"),
            "ENOTFOUND %s refused <hidden>" % _ARTIFACT_HOST,
        ),
        # An operand with no dot is no DNS name, so a bare token there is hidden.
        (
            "npm error ENOTFOUND FAKE0123456789abcdefghij",
            "npm error ENOTFOUND <hidden>",
        ),
        # Only one trailing dot makes a name fully qualified.
        (
            "npm error ENOTFOUND %s.." % _ARTIFACT_HOST,
            "npm error ENOTFOUND <hidden>",
        ),
        # Nor is a hyphenated run whose parts are each too short for (d).
        (
            "npm error ENOTFOUND FAKE1234-abcd5678-WXYZ9012",
            "npm error ENOTFOUND <hidden>",
        ),
    ],
    ids=[
        "url",
        "url-port",
        "getaddrinfo-enotfound",
        "enotfound",
        "getaddrinfo-eai-again",
        "fqdn-operand",
        "fqdn-url",
        "dotless-word-host",
        "ipv6",
        "token-beside",
        "dotless-operand",
        "two-trailing-dots",
        "dotless-hyphenated-operand",
    ],
)
def test_a_host_rule_d_would_hide_is_kept(text, shown):
    assert audit_dependencies._redacted(text) == (text if shown is None else shown)


# A token npm was handed as a registry: it has the run shape (d) hides and no
# hyphen to split it, so it is no host label however it is placed.
_TOKEN_HOST = "npmFAKEAbCdEf1234567890abcdEFGH"


@pytest.mark.parametrize(
    "text, kept",
    [
        ("request to https://%s/ failed" % _TOKEN_HOST, "request to https://"),
        ("request to https://%s@/repo failed" % _TOKEN_HOST, "request to https://"),
        (
            "request to https://%s.registry.example.com/x failed" % _TOKEN_HOST,
            "request to https://<hidden>/<path hidden> failed",
        ),
        ("getaddrinfo ENOTFOUND %s.x" % _TOKEN_HOST, "getaddrinfo ENOTFOUND "),
        (
            "request to (https://registry.example.com)%s failed" % _TOKEN_HOST,
            "(https://registry.example.com/<path hidden> failed",
        ),
        ("request to HTTPS://%s failed" % _TOKEN_HOST, "request to HTTPS://"),
        # npm's legacy token is a UUID, whose hyphens split it into short
        # parts, so its shape is named rather than left to the hyphen rule.
        (
            "request to https://%s.registry.example.com/ failed" % _UUID,
            "request to https://<hidden>/<path hidden> failed",
        ),
    ],
    ids=[
        "token-host",
        "token-userinfo-no-host",
        "token-label",
        "token-label-operand",
        "token-after-paren",
        "upper-scheme",
        "uuid-label",
    ],
)
def test_a_token_shaped_host_is_hidden(text, kept):
    shown = audit_dependencies._redacted(text)
    assert _TOKEN_HOST not in shown and _UUID not in shown, shown
    assert kept in shown, shown


@pytest.mark.parametrize(
    "text, shown",
    [
        (
            "request to http://[fe80::1%25eth0]:8080/s3cr3t/pkg failed",
            "request to http://[fe80::1%25eth0]:8080/<path hidden> failed",
        ),
        (
            "request to http://reg.example:123456/s3cr3t failed",
            "request to http://reg.example/<path hidden> failed",
        ),
    ],
    ids=["ipv6-zone", "six-digit-port"],
)
def test_a_path_after_an_odd_host_or_port_is_hidden(text, shown):
    assert audit_dependencies._redacted(text) == shown


# An IPv6 zone id names an interface, and no interface name is longer than 15
# characters (Linux's IFNAMSIZ less its NUL), so a longer zone id is hidden;
# an interface name or number is kept. Only the `%25` that opens a zone id is
# decoded, since that is the escape RFC 6874 puts there: any other `%XY` is
# three characters of the id, so an escape cannot shrink a token under 16.
@pytest.mark.parametrize(
    "zone, shown",
    [
        ("%25eth0", "%25eth0"),
        ("%eth0", "%eth0"),
        ("%25enp0s31f6", "%25enp0s31f6"),
        ("%2", "%2"),
        ("%25abcdefghijklmno", "%25abcdefghijklmno"),
        ("%25FAKE0123456789abcdefghij", "%<hidden>"),
        ("%FAKE0123456789abcdefghij", "%<hidden>"),
        ("%25abcdefghijklmnop", "%<hidden>"),
        ("%25ab%2Dcd%2Def%2Dgh", "%<hidden>"),
        ("%A1A1A1A1A1A1A1A1", "%<hidden>"),
        ("%25" + "a" * 40, "%<hidden>"),
        ("%25" + "a" * 300, "%<hidden>"),
    ],
    ids=[
        "escaped",
        "raw",
        "long-name",
        "number",
        "fifteen",
        "escaped-token",
        "raw-token",
        "sixteen",
        "escaped-dashes",
        "raw-escapes",
        "longer-than-a-host-run",
        "longer-than-a-host",
    ],
)
def test_an_ipv6_zone_id_longer_than_an_interface_name_is_hidden(zone, shown):
    text = "request to http://[fe80::1%s]:8080/x failed" % zone
    assert audit_dependencies._redacted(text) == (
        "request to http://[fe80::1%s]:8080/<path hidden> failed" % shown
    )


# A label of 20 or more characters that mixes letters and digits is a name
# only when one part between its hyphens is a word: two or more letters, one
# outside a to f, so a hex fragment is no word. A token cut into short parts
# by hyphens has none.
@pytest.mark.parametrize(
    "label",
    [
        "FAKE1234-abcd5678-WXYZ9012",
        "0123456789abcdef-0123456789abcdef",
        "0123456789-abcdef-0123456789",
        # One letter alone is no word, even outside a to f.
        "Q-0123456789abcdef-0123456789",
    ],
    ids=["mixed-parts", "hex-parts", "hex-word", "one-letter-part"],
)
@pytest.mark.parametrize(
    "form", ["npm error ENOTFOUND %s.registry.example", "request to https://%s.x/p"]
)
def test_a_label_of_short_token_parts_is_hidden(form, label):
    shown = audit_dependencies._redacted(form % label)
    assert label not in shown and "<hidden>" in shown, shown


@pytest.mark.parametrize(
    "host",
    [_ARTIFACT_HOST, "npm-registry-1234567890ab.example", "a1-my-0123456789abcdef.x"],
)
def test_a_long_label_with_a_word_part_is_kept(host):
    line = "npm error ENOTFOUND %s" % host
    assert audit_dependencies._redacted(line) == line


_GITLAB_PREFIX = "gl" + "pat-"


# A word part does not excuse the rest of its label: every part that is no
# word, joined by hyphens, is judged as one run, so a token behind a word
# prefix, such as GitLab's personal-token prefix, is hidden however its own
# hyphens or a short word inside it cut it. GitHub's and npm's tokens hold `_`, which no
# label holds. Each is built at run time so no file holds a scanner's shape.
@pytest.mark.parametrize(
    "label",
    [
        _GITLAB_PREFIX + "ab12cd34ef-56ab78cd90xy",
        _GITLAB_PREFIX + "ab12-cd34-ef56-ab78-cd90",
        "ab12cd34ef-56ab78cd90xy-registry",
        "my-ab12cd34ef-56ab78cd90xy-mirror",
        _GITLAB_PREFIX + "Ab12Cd34-Qx-Ef56Gh78Ij99",
        "Ab12Cd34-Qx-Ef56Gh78Ij99",
        "ghp" + "_FAKE0123456789abcdefghij",
        "npm" + "_FAKE0123456789abcdefghij",
    ],
    ids=[
        "gitlab-cut",
        "gitlab-short-parts",
        "word-suffix",
        "word-both-sides",
        "gitlab-word-inside",
        "word-inside",
        "ghp",
        "npm",
    ],
)
@pytest.mark.parametrize(
    "form", ["npm error ENOTFOUND %s.registry.example", "request to https://%s.x/p"]
)
def test_a_token_behind_a_word_prefix_is_hidden(form, label):
    shown = audit_dependencies._redacted(form % label)
    assert label not in shown and "<hidden>" in shown, shown
    for piece in label.replace("_", "-").split("-")[1:]:
        if len(piece) > 3:
            assert piece not in shown, shown


# The parts that are no word, taken together, are under 20 characters or
# hold no letter, so these names are kept.
@pytest.mark.parametrize(
    "host",
    ["ip-10-0-0-1-eu-west-1.example", "ab12cd-eu-0123456789ab.example"],
)
def test_short_runs_between_words_are_kept(host):
    line = "npm error ENOTFOUND %s" % host
    assert audit_dependencies._redacted(line) == line


# A run that is one word and then a number, its digits and hyphens only, is a
# name's shape and no token's: it turns from letters to digits once, where a
# random token turns many times. So a CodeArtifact domain named with digits
# is kept, and so is a dotless host that is a valid label, such as a
# registry's short name.
@pytest.mark.parametrize(
    "line",
    [
        "npm error ENOTFOUND acme2024-111122223333.d.codeartifact.eu-west-1.example",
        "request to https://acme2024-111122223333.d.codeartifact.x/<path hidden> failed",
        "npm error ENOTFOUND nexus3",
        "npm error ENOTFOUND artifactory2",
        "request to http://nexus3:8081/<path hidden> failed",
        "request to https://artifactory2/<path hidden> failed",
        # The cost of the line: a word and then a long number is kept.
        "npm error ENOTFOUND mirror12345678901234567890.example",
    ],
    ids=[
        "artifact-operand",
        "artifact-url",
        "nexus3",
        "artifactory2",
        "nexus3-url",
        "artifactory2-url",
        "word-number",
    ],
)
def test_a_word_then_a_number_is_a_name(line):
    said = line.replace("<path hidden>", "s3cr3t/pkg")
    assert audit_dependencies._redacted(said) == line


# Any other run of 20 or more that mixes letters and digits is still hidden,
# dotted or not: one that turns back to letters, or opens with digits or with
# a letter that is no word.
@pytest.mark.parametrize(
    "host",
    [
        "acme2024-111122223333x.d.codeartifact.example",
        "FAKE0123456789abcdefghij",
        "FAKE0123456789abcdefghij.example",
        "2024acme-111122223333.example",
        "Q0123456789012345678901.example",
        "ab12cd34ef56ab78cd90xy",
    ],
    ids=["back-to-letters", "dotless", "dotted", "digits-first", "one-letter", "hex"],
)
def test_a_mixed_run_that_turns_more_than_once_is_hidden(host):
    shown = audit_dependencies._redacted("npm error ENOTFOUND %s" % host)
    assert shown.startswith("npm error ENOTFOUND <hidden>"), shown


# A token holding `=`, `+` or a `%`-escape: split there, each piece is under
# rule (d)'s 20 characters, so only a judgement of the whole run hides it.
_SPLIT_TOKENS = {
    "equals": "AbCdEf1234567=890abcdEFGHijklm",
    "plus": "AbCdEf1234567+890abcdEFGHijklm",
    "escape": "AbCdEf1234567%2B890abcdEFG.example",
    # A first piece with no digit is no token on its own, so only the whole
    # run, `=` included, shows it is one.
    "word-first": "abcdefghijklm=1234567890ABCDEFG",
    # The same with `+`: a URL host that stops at the `+` keeps the digitless
    # first piece and shows 13 of the token's characters.
    "word-first-plus": "abcdefghijklm+1234567890ABCDEFG",
}


@pytest.mark.parametrize(
    "form", ["getaddrinfo ENOTFOUND %s", "request to https://%s/x"]
)
@pytest.mark.parametrize("token", sorted(_SPLIT_TOKENS))
def test_a_host_split_by_a_symbol_is_hidden_whole(form, token):
    shown = audit_dependencies._redacted((form % _SPLIT_TOKENS[token]) + " failed")
    # npm lowercases a host, so no piece may show in either case.
    for piece in re.split(r"[=+]|%2B|\.example", _SPLIT_TOKENS[token]):
        assert not piece or piece.lower() not in shown.lower(), shown
    assert shown.startswith(form.split("%s")[0] + "<hidden>"), shown


def test_a_codeartifact_host_is_kept_end_to_end(project, capsys):
    app = project.app("astro")
    said = (
        "request to https://%s/npm/repo/-/npm/v1/security/advisories/bulk failed, "
        "reason: getaddrinfo ENOTFOUND %s" % (_ARTIFACT_HOST, _ARTIFACT_HOST)
    )
    out = json.dumps({"message": said, "error": {"summary": "", "detail": ""}})
    code = project.main([app], run_audit=lambda *_: (1, out, b""))
    err = capsys.readouterr().err
    assert code is ExitCode.BACKEND_ABSENT, err
    assert (
        "request to https://%s/<path hidden> failed, reason: getaddrinfo ENOTFOUND %s"
        % (_ARTIFACT_HOST, _ARTIFACT_HOST)
    ) in err
    assert "check the registry is reachable" in err


# A registry's 403 body reaches the redaction through npm's `message`, so a
# proxy chooses this text. Before the patterns were bounded, "token" * 300 took
# 7 s and "a" * 16000 took 9 s; bounded, each takes milliseconds, so 1 s is a
# wide margin that a pattern which backtracks again still overruns.
# The redaction runs in a child the test can kill, because a regex holds the
# interpreter until it returns: the old "token" pattern on this line runs for
# hours, and a test that hangs is no red run.
_TIMED_REDACTION = (
    "import sys, time\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import audit_dependencies\n"
    "line = sys.argv[2] * int(sys.argv[3])\n"
    "started = time.perf_counter()\n"
    "shown = audit_dependencies._redacted(line)\n"
    "print(time.perf_counter() - started, shown == line)\n"
)


# Each row after the first two repeats the shape a newer pattern reads, so a
# pattern that backtracks on its own input overruns. `unchanged` says whether
# the line holds a span some rule rewrites.
@pytest.mark.parametrize(
    "unit, times, unchanged",
    [
        ("a", 16000, True),
        ("token", 2000, True),
        ("token was x1 ", 1600, False),
        ("https://a@", 1600, False),
        ("a:", 8000, True),
        ("token=x y z ", 1600, False),
        ("a.bc/x ", 1600, False),
        (" a.a.a.a.a.a.a.a", 1000, True),
        ("ENOTFOUND acme2024-111122223333.d.x ", 600, True),
        ("password the is ", 1600, True),
        ("token " + "x " * 20, 200, False),
        ("password=a,b;c'd e=f ", 1600, False),
        ("http://[::1%25" + "a" * 60 + "]/x ", 300, False),
        ("a@b.cd/x a@1.2.3 ", 1000, False),
        # 50 000 characters each, one row per pattern fix round 2 changed.
        ("token - x ", 5000, False),
        ("token, x1 ", 5000, False),
        ("token's x ", 5000, False),
        ("token x,https://a.b/c ", 2273, False),
        ("gopher://u:v@h/ ", 3125, False),
        ("x://", 12500, False),
        ("token e.g. x ", 3847, False),
        ("token" + " x" * 17 + " a. b ", 1087, False),
    ],
    ids=[
        "a",
        "token",
        "token-was",
        "url-userinfo",
        "bare-userinfo",
        "value-words",
        "bare-path",
        "dotted",
        "word-number",
        "clause-words",
        "clause-bound",
        "assigned-run",
        "zone-id",
        "bare-user",
        "marks-word",
        "mark-opens-clause",
        "possessive",
        "glued-url",
        "other-scheme",
        "other-scheme-run",
        "abbreviation",
        "sentence-bound",
    ],
)
def test_a_hostile_line_is_redacted_within_a_second(unit, times, unchanged):
    argv = [sys.executable, "-c", _TIMED_REDACTION, str(_ROOT / "scripts")]
    try:
        done = subprocess.run(
            argv + [unit, str(times)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=build_child_env(),
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("redacting %r * %d ran past 10 s" % (unit, times))
    assert done.returncode == 0, done.stderr
    took = done.stdout.split()[0]
    assert float(took) < 1.0, "redacting %r * %d took %s s" % (unit, times, took)
    assert done.stdout.split()[1] == str(unchanged)


def _cut_run(project, capsys, said, limit):
    project.configure(
        accepted={},
        fail_at="high",
        max_review_days=90,
        timeout_seconds=30,
        max_shown_chars=limit,
    )
    app = project.app("astro")
    out = json.dumps({"message": said, "error": {"summary": "", "detail": ""}})
    code = project.main([app], run_audit=lambda *_: (1, out, b""))
    err = capsys.readouterr().err
    assert code is ExitCode.BACKEND_ABSENT, err
    return err


def test_a_long_diagnostic_is_cut_to_max_shown_chars_and_says_so(project, capsys):
    said = "getaddrinfo ENOTFOUND registry.example.invalid " + "word " * 4000
    err = _cut_run(project, capsys, said, 60)
    assert "getaddrinfo ENOTFOUND registry.example.invalid word" in err
    assert "<cut to 60 characters>" in err
    assert "word " * 20 not in err


def test_a_cause_past_the_cut_still_picks_the_advice(project, capsys):
    # Only the uncut text names E401, and without it the advice would be
    # reachability, so the credentials advice can come from nowhere else.
    said = "request to https://registry.example.invalid/x failed " + "word " * 40
    err = _cut_run(project, capsys, said + "E401 Unable to authenticate", 60)
    assert "<cut to 60 characters>" in err
    assert "E401" not in err
    assert "check the registry credentials" in err


@pytest.mark.parametrize(
    "said, shown",
    [
        (
            'ENOTFOUND x.invalid password="correct horse battery staple"',
            "ENOTFOUND x.invalid password=<hidden> <cut to 45 characters>",
        ),
        (
            "ENOTFOUND x.invalid password='correct horse battery staple'",
            "ENOTFOUND x.invalid password=<hidden> <cut to 45 characters>",
        ),
        (
            'ENOTFOUND x.invalid {"password": "correct horse battery staple"}',
            'ENOTFOUND x.invalid {"password": <hidden> <cut to 45 characters>',
        ),
    ],
    ids=["quoted", "single-quoted", "json"],
)
def test_a_quoted_value_the_cut_splits_is_hidden_from_its_start(said, shown):
    # The cut at 45 lands inside the value, after "correct" and before its
    # closing quote, so no quote pair is left for the key-value rule to find.
    assert audit_dependencies._shown(said, 45) == shown


def test_a_token_the_cut_splits_is_not_shown_in_part(project, capsys):
    # The cut lands inside the token, leaving a 16-character fragment, too
    # short for rule (d); the cut drops the partial word instead.
    said = "ENOTFOUND x.invalid refused " + _GHP
    err = _cut_run(project, capsys, said, len("ENOTFOUND x.invalid refused ") + 16)
    assert _GHP[:16] not in err
    assert "ENOTFOUND x.invalid refused <cut to" in err


def test_a_line_within_max_shown_chars_is_not_marked(project, capsys):
    err = _cut_run(project, capsys, "getaddrinfo ENOTFOUND r.invalid", 500)
    assert "getaddrinfo ENOTFOUND r.invalid" in err
    assert "<cut to" not in err


_DECLARED = {"dependencies": {"zod": "^3.0.0"}}


@pytest.mark.parametrize(
    "declared",
    [
        {"dependencies": {"zod": "^3.0.0"}},
        {"devDependencies": {"zod": "^3.0.0"}},
        {"optionalDependencies": {"zod": "^3.0.0"}},
        {"peerDependencies": {"zod": "^3.0.0"}},
        {"workspaces": ["packages/*"]},
        {"workspaces": {"packages": ["packages/*"]}},
    ],
)
@pytest.mark.parametrize("total", [0, None])
def test_a_saved_report_auditing_no_dependency_is_usage(
    project, capsys, declared, total
):
    doc = _audit(dependencies=total)
    if total is None:
        del doc["metadata"]["dependencies"]
    code, _, err = _judged(project, capsys, doc, {}, manifest=declared)
    assert code is ExitCode.USAGE, err
    assert "astro" in err
    assert "metadata.dependencies.total" in err
    assert "make fe-install" in err


def test_a_required_peer_beside_an_optional_one_declares(project, capsys):
    declared = {
        "peerDependencies": {"react": "*", "vue": "*"},
        "peerDependenciesMeta": {"react": {"optional": True}},
    }
    code, _, err = _judged(
        project, capsys, _audit(dependencies=0), {}, manifest=declared
    )
    assert code is ExitCode.USAGE, err
    assert "metadata.dependencies.total" in err


@pytest.mark.parametrize(
    "declared, named",
    [
        ({"workspaces": ["packages/*"]}, True),
        ({"workspaces": {"packages": ["packages/*"]}}, True),
        ({"dependencies": {"zod": "^3.0.0"}}, False),
    ],
)
def test_a_workspaces_root_names_an_unmatched_pattern(project, capsys, declared, named):
    code, _, err = _judged(
        project, capsys, _audit(dependencies=0), {}, manifest=declared
    )
    assert code is ExitCode.USAGE, err
    assert "make fe-install" in err
    assert ("a workspaces pattern that matches no directory" in err) is named


def test_a_live_run_auditing_no_dependency_is_backend_absent(project, capsys):
    app = project.app("astro", manifest=_DECLARED)
    out = json.dumps(_audit(dependencies=0))
    code = project.main([app], run_audit=lambda *_: (0, out, b""))
    err = capsys.readouterr().err
    assert code is ExitCode.BACKEND_ABSENT, err
    assert "metadata.dependencies.total" in err


@pytest.mark.parametrize(
    "declared",
    [
        {"workspaces": []},
        {"workspaces": {"packages": []}},
        {"dependencies": {}},
        {
            "peerDependencies": {"react": "*", "vue": "*"},
            "peerDependenciesMeta": {
                "react": {"optional": True},
                "vue": {"optional": True},
            },
        },
    ],
)
def test_an_empty_declaration_with_no_audited_dependency_passes(
    project, capsys, declared
):
    doc = _audit(dependencies=0)
    code, out, err = _judged(project, capsys, doc, {}, manifest=declared)
    assert code is ExitCode.SUCCESS, err
    assert "1 app(s) judged" in out


def test_a_report_auditing_dependencies_the_manifest_declares_passes(project, capsys):
    code, out, err = _judged(project, capsys, _audit(), {}, manifest=_DECLARED)
    assert code is ExitCode.SUCCESS, err
    assert "1 app(s) judged" in out


def test_an_unreadable_package_json_is_usage(project, capsys):
    app = project.app("astro")
    (project.root / app / "package.json").write_text("[]")
    assert project.main([app], run_audit=_never) is ExitCode.USAGE
    assert "package.json" in capsys.readouterr().err


def _miscounted(**counts):
    doc = _audit((_HIGH, "zod", "high"))
    doc["metadata"]["vulnerabilities"].update(counts)
    return doc


@pytest.mark.parametrize(
    "doc, why",
    [
        (_miscounted(high=0), "high"),
        (_miscounted(moderate=2), "moderate"),
        (_miscounted(total=1), "total"),
        (_miscounted(high=True), "high"),
        (dict(_audit(), metadata={}), "metadata.vulnerabilities"),
    ],
)
def test_counts_that_disagree_with_the_entries_are_refused(project, capsys, doc, why):
    code, _, err = _judged(project, capsys, doc, {})
    assert code is ExitCode.USAGE, err
    assert why in err
    app = "src/frontend/astro"
    code = project.main([app], run_audit=lambda *_: (1, json.dumps(doc), b""))
    assert code is ExitCode.BACKEND_ABSENT
    assert why in capsys.readouterr().err


def test_a_via_item_that_is_neither_advisory_nor_package_is_refused(project, capsys):
    doc = _audit((_HIGH, "zod", "high"))
    doc["vulnerabilities"]["parent-pkg"]["via"].append(7)
    code, _, err = _judged(project, capsys, doc, {})
    assert code is ExitCode.USAGE
    assert "a via item that is neither" in err


def test_a_via_string_naming_no_entry_is_refused(project, capsys):
    doc = _audit((_HIGH, "zod", "high"))
    doc["vulnerabilities"]["parent-pkg"]["via"].append("not-in-the-report")
    code, _, err = _judged(project, capsys, doc, {})
    assert code is ExitCode.USAGE
    assert "'not-in-the-report'" in err


def test_npm_audits_every_dependency_type_an_npmrc_could_omit():
    assert audit_dependencies.AUDIT_ARGV[:3] == ("npm", "audit", "--json")
    for kind in ("dev", "optional", "peer"):
        assert "--include=" + kind in audit_dependencies.AUDIT_ARGV


def test_npm_that_cannot_start_is_backend_absent(project, capsys, monkeypatch):
    monkeypatch.setattr(audit_dependencies, "AUDIT_ARGV", ("no-such-npm-program",))
    app = project.app("astro")
    assert project.main([app]) is ExitCode.BACKEND_ABSENT
    assert "could not be started" in capsys.readouterr().err


def test_npm_past_its_timeout_is_backend_absent(project, capsys, monkeypatch):
    sleeper = (sys.executable, "-c", "import time; time.sleep(30)")
    monkeypatch.setattr(audit_dependencies, "AUDIT_ARGV", sleeper)
    project.configure(
        accepted={}, fail_at="high", max_review_days=90, timeout_seconds=1
    )
    app = project.app("astro")
    assert project.main([app]) is ExitCode.BACKEND_ABSENT
    assert "ran past 1 seconds" in capsys.readouterr().err


def test_the_real_runner_judges_what_the_program_prints(project, capsys, monkeypatch):
    printer = (sys.executable, "-c", "print(%r)" % json.dumps(_audit()))
    monkeypatch.setattr(audit_dependencies, "AUDIT_ARGV", printer)
    app = project.app("astro")
    assert project.main([app]) is ExitCode.SUCCESS
    assert "1 app(s) judged" in capsys.readouterr().out


@pytest.mark.parametrize(
    "block",
    [
        {"fail_at": "severe"},
        {"timeout_seconds": 0},
        {"max_review_days": 0},
        {"max_review_days": True},
        {"max_shown_chars": 0},
        {"max_shown_chars": True},
        {"accepted": {"astro": {}}},
        {"accepted": {"astro": {"CVE-2026-0001": _row("zod")}}},
        {"accepted": {"astro": {_HIGH: {"package": "zod", "reason": "r"}}}},
        {"accepted": {"astro": {_HIGH: dict(_row("zod"), extra="x")}}},
        {"accepted": {"astro": {_HIGH: _row("zod", review_by="2027-1-21")}}},
        {"accepted": {"astro": {_HIGH: _row("zod", reason=" ")}}},
        {"accepted": {"astro": {_HIGH: _row("z od")}}},
        {"accepted": {"src/frontend/astro": {_HIGH: _row("zod")}}},
    ],
)
def test_a_refused_setting_is_config(project, capsys, block):
    project.configure(**block)
    assert project.main([]) is ExitCode.CONFIG
    assert "dependency_audit" in capsys.readouterr().err


def test_keel_config_reads_and_its_rows_are_well_formed(capsys):
    settings = audit_dependencies._settings(str(_ROOT))
    assert settings["max_review_days"] == 90
    assert settings["max_shown_chars"] == 500
    for app, rows in settings["accepted"].items():
        assert (_ROOT / "src" / "frontend" / app / "package.json").is_file(), app
        assert rows
