"""
title: Unit — audit_dependencies (npm audit findings judged against the accepted risks in config)
kind: tests
layer: n/a
summary: scripts/audit_dependencies.py driven in process over saved `npm audit --json` reports shaped like a real one, in a project root the test builds from keel's own config/project.json with its own `dependency_audit` block, on a day the test hands in, so no test runs npm or reaches the network. Each failure kind fails on its own and names what failed: a finding at or above `fail_at` no row covers, a covered finding whose row names another package, a row past its review_by day, a row dated more than `max_review_days` after today (exactly that many passes, one more fails), a row whose advisory the report no longer holds, and a row naming an app not audited. A covered finding passes on its review_by day and is listed with its reason; a finding below `fail_at` is listed and does not fail, and lowering `fail_at` fails it. A report with no findings still judges every row. No app and no row exits 0 saying so. A report that is not version 2, one with an unknown severity, a via url with no advisory id, a via item that is neither an advisory nor an entry's name, counts that disagree with its entries, or no audited dependency while package.json declares one is USAGE from a saved file and BACKEND_ABSENT from a run; so is a run's output that is not JSON, and npm exiting 1 with no finding. An app with no package.json, an unreadable one or no package-lock.json, a `--report` name that is not an audited app and a bad flag are USAGE; npm that cannot start, overruns its timeout, exits 2, is killed by a signal or answers an error object is BACKEND_ABSENT, showing the error's message or summary, else the top-level message npm 11 writes for an unreachable registry (its real shape, with a placeholder host), else npm's last stderr line other than its log pointer and no other, and `<hidden>` for a line holding any of the credential shapes, each tested with its secret absent from the output. Each dependency field and both forms of `workspaces` count as declaring a dependency, and an empty one does not. The argv includes every dependency type an .npmrc could omit. A refused `dependency_audit` value is CONFIG.
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


@pytest.mark.parametrize(
    "out, stderr",
    [
        ("{}", b"npm error //registry.example.invalid/:_password=s3cr3t\n"),
        ("{}", b"npm error _auth=s3cr3t\n"),
        ("{}", b"npm error Authorization: Bearer s3cr3t\n"),
        ("{}", b"npm error token npm_" + b"s3cr3t" + b"A" * 30 + b" refused\n"),
        ("{}", b"npm error GET https://someone:s3cr3t@registry.example.invalid/x\n"),
        ("{}", b"npm error //registry.example.invalid/:_authToken=s3cr3t\n"),
        ("{}", b"npm error //registry.example.invalid/:_auth=s3cr3t\n"),
        (json.dumps({"error": {"summary": "bad _authToken s3cr3t"}}), b""),
        (json.dumps({"error": {"message": "//host.invalid/:_auth s3cr3t"}}), b""),
    ],
)
def test_a_diagnostic_carrying_an_auth_token_is_hidden(project, capsys, out, stderr):
    app = project.app("astro")
    status = 1 if "error" in out else 2
    code = project.main([app], run_audit=lambda *_: (status, out, stderr))
    err = capsys.readouterr().err
    assert code is ExitCode.BACKEND_ABSENT
    assert "<hidden>" in err
    assert "s3cr3t" not in err


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


def test_a_live_run_auditing_no_dependency_is_backend_absent(project, capsys):
    app = project.app("astro", manifest=_DECLARED)
    out = json.dumps(_audit(dependencies=0))
    code = project.main([app], run_audit=lambda *_: (0, out, b""))
    err = capsys.readouterr().err
    assert code is ExitCode.BACKEND_ABSENT, err
    assert "metadata.dependencies.total" in err


@pytest.mark.parametrize(
    "declared",
    [{"workspaces": []}, {"workspaces": {"packages": []}}, {"dependencies": {}}],
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
