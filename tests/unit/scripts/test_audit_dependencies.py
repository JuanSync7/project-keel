"""
title: Unit — audit_dependencies (npm audit findings judged against the accepted risks in config)
kind: tests
layer: n/a
summary: scripts/audit_dependencies.py driven in process over saved `npm audit --json` reports shaped like a real one, in a project root the test builds from keel's own config/project.json with its own `dependency_audit` block, on a day the test hands in, so no test runs npm or reaches the network. Each failure kind fails on its own and names what failed: a finding at or above `fail_at` no row covers, a covered finding whose row names another package, a row past its review_by day, a row dated more than `max_review_days` after today (exactly that many passes, one more fails), a row whose advisory the report no longer holds, and a row naming an app not audited. A covered finding passes on its review_by day and is listed with its reason; a finding below `fail_at` is listed and does not fail, and lowering `fail_at` fails it. A report with no findings still judges every row. No app and no row exits 0 saying so. A report that is not version 2, one with an unknown severity or a via url with no advisory id, an app with no package.json or package-lock.json, a `--report` name that is not an audited app and a bad flag are USAGE; npm that cannot start, overruns its timeout, exits 2 or answers an error object is BACKEND_ABSENT; a refused `dependency_audit` value is CONFIG.
"""

import copy
import datetime
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import audit_dependencies  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit

_TODAY = datetime.date(2026, 10, 23)
_PARSER = "GHSA-rj75-hqrm-r3gf"
_HIGH = "GHSA-mrhx-c7xc-m3w5"
_LOW = "GHSA-238p-pmpm-9mq7"


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


def _audit(*advisories):
    """An `npm audit --json` version 2 report holding *advisories*, each
    (advisory, package, severity), with the string `via` entry a dependent
    package carries."""
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
    return {
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities,
        "metadata": {"vulnerabilities": {"total": len(advisories)}},
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

    def app(self, name, lockfile=True):
        app = self.root / "src" / "frontend" / name
        app.mkdir(parents=True, exist_ok=True)
        (app / "package.json").write_text("{}")
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


def _judged(project, capsys, doc, accepted, fail_at="high", today=_TODAY, cap=90):
    project.configure(
        accepted=accepted,
        fail_at=fail_at,
        max_review_days=cap,
        timeout_seconds=30,
    )
    app = project.app("astro")
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
        return 1, json.dumps(_audit((_HIGH, "zod", "high"))).encode()

    assert project.main([app], run_audit=run) is ExitCode.FAILURE
    assert seen == [(str(project.root / "src" / "frontend" / "astro"), 30)]


@pytest.mark.parametrize(
    "status, out, why",
    [
        (2, "{}", "npm audit exited 2"),
        (1, json.dumps({"error": {"code": "ENOTFOUND"}}), "answered an error"),
    ],
)
def test_npm_that_does_not_answer_is_backend_absent(project, capsys, status, out, why):
    app = project.app("astro")
    code = project.main([app], run_audit=lambda *_: (status, out))
    assert code is ExitCode.BACKEND_ABSENT
    assert why in capsys.readouterr().err


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
    for app, rows in settings["accepted"].items():
        assert (_ROOT / "src" / "frontend" / app / "package.json").is_file(), app
        assert rows
