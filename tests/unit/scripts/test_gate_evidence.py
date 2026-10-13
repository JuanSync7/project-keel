"""
title: Unit — gate_evidence (the gate's evidence record writer)
kind: tests
layer: n/a
summary: The driver's parts and its fail-closed main. junit_counts classifies each testcase once (error before failure before skipped) and ignores the suite attributes; a missing or unparseable report is null, never 0; zero tests and an all-skipped suite are red; a failed or errored test is red even when every goal exited 0; every project-check stem check_structure runs is a checks key the schema admits; render is canonical. run_goals runs each goal in order with the allowlisted environment and the outer make's flags and command-line variables as argv, stops at the first failure unless MAKEFLAGS carries k, and make_mode reads only MAKEFLAGS' single-letter word. main passes a failing goal's code through, never returns 0 when the writer crashes, refuses zero goals, a record path git does not ignore and a bad evidence block with exit 2, leaves a red placeholder when interrupted, writes nothing on a dry run, and strips the absolute root from check messages. The writer and git_tree parse and import at the old-python floor.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import gate_evidence as ge  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit

_SCHEMA_REL = "config/evidence/gate-record.schema.json"

_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="99" failures="0" errors="0" skipped="0">
<testcase classname="t" name="p1"/>
<testcase classname="t" name="p2"/>
<testcase classname="t" name="p3"><system-out>noise</system-out></testcase>
<testcase classname="t" name="f1"><failure message="x"/></testcase>
<testcase classname="t" name="s1"><skipped message="y"/></testcase>
<testcase classname="t" name="e1"><error message="z"/></testcase>
<testcase classname="t" name="fe"><failure message="a"/><error message="teardown"/></testcase>
</testsuite></testsuites>
"""

_PASSING = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest"><testcase classname="t" name="ok"/></testsuite></testsuites>
"""


def _counts(passed=0, failed=0, skipped=0, errors=0):
    return {"passed": passed, "failed": failed, "skipped": skipped, "errors": errors}


def _target(name, result="pass", returncode=0, tests=None):
    return {"name": name, "result": result, "returncode": returncode, "tests": tests}


class _Done:
    def __init__(self, returncode):
        self.returncode = returncode


class _Runner:
    """A stand-in for subprocess.run: each goal's exit code from *codes*, a
    passing junit report written for each goal named in *reports*, and every
    call recorded."""

    def __init__(self, codes=None, reports=("test",), raises=None, report=_PASSING):
        self.codes = codes or {}
        self.reports = reports
        self.raises = raises or {}
        self.report = report
        self.calls = []

    def __call__(self, argv, cwd=None, env=None):
        self.calls.append({"argv": list(argv), "cwd": cwd, "env": env})
        goal = [a for a in argv[1:] if not a.startswith("-") and "=" not in a][0]
        if goal in self.raises:
            raise self.raises[goal]
        junit = [a for a in argv if a.startswith("JUNIT_XML=")][0].split("=", 1)[1]
        if goal in self.reports:
            path = os.path.join(cwd, junit)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.report)
        return _Done(self.codes.get(goal, 0))


def _git(repo, env, *argv):
    return subprocess.run(
        ["git", *argv], cwd=str(repo), env=env, check=True, capture_output=True
    )


def _evidence_block(**override):
    block = {"dir": ".evidence", "schema": _SCHEMA_REL}
    block.update(override)
    return block


def _write_manifest(proj, block):
    manifest = {} if block is None else {"evidence": block}
    (proj / "config").mkdir(exist_ok=True)
    (proj / "config" / "project.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A committed repository with the evidence block, keel's schema and an
    ignore rule for the evidence directory, as the working directory, with
    MAKEFLAGS cleared and run_checks stubbed to one warning per letter."""
    work = tmp_path / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("MAKEFLAGS", raising=False)
    proj = tmp_path / "proj"
    (proj / "config" / "evidence").mkdir(parents=True)
    shutil.copy(str(_ROOT / _SCHEMA_REL), str(proj / _SCHEMA_REL))
    _write_manifest(proj, _evidence_block())
    (proj / ".gitignore").write_text(".evidence/\n", encoding="utf-8")
    _git(proj, env, "init", "-q")
    _git(proj, env, "add", "-A")
    _git(proj, env, "commit", "-q", "-m", "init")
    monkeypatch.chdir(proj)
    monkeypatch.setattr(ge.check_structure, "run_checks", lambda root: [])
    return proj


def _record(proj, gate="verify"):
    return json.loads((proj / ".evidence" / (gate + ".json")).read_text("utf-8"))


# --- junit_counts -------------------------------------------------------------


def test_junit_counts_classify_each_testcase_once(tmp_path):
    report = tmp_path / "r.xml"
    report.write_text(_JUNIT, encoding="utf-8")
    assert ge.junit_counts(str(report)) == _counts(3, 1, 1, 2)


def test_a_missing_or_unparseable_report_is_null_not_zero(tmp_path):
    assert ge.junit_counts(str(tmp_path / "absent.xml")) is None
    cut = tmp_path / "cut.xml"
    cut.write_text(_JUNIT[: len(_JUNIT) // 2], encoding="utf-8")
    assert ge.junit_counts(str(cut)) is None
    assert ge.overall([_target("test")], None, False, True) == (
        "fail",
        ["no-test-report"],
    )


def test_zero_tests_is_red_and_all_skipped_is_zero_tests():
    ok = [_target("test")]
    assert ge.overall(ok, _counts(), False, True) == ("fail", ["zero-tests"])
    assert ge.overall(ok, _counts(skipped=4), False, True) == ("fail", ["zero-tests"])
    assert ge.overall(ok, _counts(passed=1, skipped=4), False, True) == ("pass", [])


def test_overall_names_every_red_condition_sorted():
    """Each condition alone is red with its own reason; together they are all
    named, sorted; an unknown tree (None, no git) is not a change."""
    ok, tests = [_target("test")], _counts(passed=1)
    assert ge.overall(ok, tests, None, True) == ("pass", [])
    assert ge.overall(ok, tests, True, True) == ("fail", ["tree-changed"])
    assert ge.overall(ok, tests, False, False) == ("fail", ["checks-unavailable"])
    assert ge.overall([], tests, False, True) == ("fail", ["zero-targets"])
    bad = [_target("a", "fail", 2), _target("b", "not-run", None)]
    assert ge.overall(bad, None, True, False) == (
        "fail",
        ["checks-unavailable", "no-test-report", "target-failed", "tree-changed"],
    )


def test_a_failed_or_errored_test_is_red_even_when_every_goal_passed():
    """A goal can exit 0 over a report that counts failures (`make -i`, a
    `-`-prefixed or `|| true` test recipe). The record judges the counts it
    holds, so it never says pass beside a failure or an error."""
    ok = [_target("test")]
    assert ge.overall(ok, _counts(passed=1, failed=1), False, True) == (
        "fail",
        ["tests-failed"],
    )
    assert ge.overall(ok, _counts(passed=1, errors=1), False, True) == (
        "fail",
        ["tests-failed"],
    )
    assert ge.overall(ok, _counts(failed=2), False, True) == ("fail", ["tests-failed"])
    bad = [_target("test", "fail", 1)]
    assert ge.overall(bad, _counts(passed=1, failed=1), False, True) == (
        "fail",
        ["target-failed", "tests-failed"],
    )


def test_the_reasons_are_the_schemas_closed_vocabulary():
    schema = json.loads((_ROOT / _SCHEMA_REL).read_text("utf-8"))
    assert sorted(ge.REASONS) == sorted(schema["$defs"]["reason"]["enum"])


# --- render -------------------------------------------------------------------


def test_render_is_canonical():
    one = {"b": 1, "a": {"y": [1, 2], "x": None}}
    two = {"a": {"x": None, "y": [1, 2]}, "b": 1}
    text = ge.render(one)
    assert text == ge.render(two)
    assert text == json.dumps(one, indent=2, sort_keys=True) + "\n"
    assert text.endswith("}\n") and not text.endswith("\n\n")


# --- make_mode and the forwarded make arguments ------------------------------


def test_make_mode_reads_only_the_single_letter_word():
    assert ge.make_mode("kn -- PY=x") == (True, True)
    assert ge.make_mode(" --jobserver-auth=3,4 -- RALPH=1") == (False, False)
    assert ge.make_mode("") == (False, False)
    assert ge.make_mode("-- n=1") == (False, False)
    for letter in "nqt":
        assert ge.make_mode(letter) == (True, False), letter
    assert ge.make_mode("ks") == (False, True)


def test_make_args_forward_the_flags_and_the_command_line_variables():
    """What the outer make put in MAKEFLAGS, as argv for a sub-make started
    without it: the single-letter word as one option, long options verbatim
    except the jobserver's descriptors (meaningless in a fresh process), and the
    command-line variables unescaped, in the order they were given."""
    flags = r"ks -I/a\ b -j4 --jobserver-auth=3,4 -- X=c\\d FOO=a\ b PY=x"
    assert ge.make_args(flags) == ["-ks", "-I/a b", "-j4", "PY=x", "FOO=a b", r"X=c\d"]
    assert ge.make_args(" -- RALPH=1 PY=.venv/bin/python") == [
        "PY=.venv/bin/python",
        "RALPH=1",
    ]
    assert ge.make_args("") == []
    assert ge.make_args(" --jobserver-fds=3,4 -j") == ["-j"]


# --- run_goals ----------------------------------------------------------------


def test_run_goals_stops_at_the_first_failure_and_marks_the_rest_not_run(
    tmp_path, monkeypatch
):
    env = {"PATH": "/bin"}
    seen = []

    def fake_env(**kw):
        seen.append(kw)
        return env

    monkeypatch.setattr(ge.child_env, "build_child_env", fake_env)
    runner = _Runner(codes={"b": 2}, reports=())
    targets = ge.run_goals(
        "make", ["a", "b", "c"], str(tmp_path), ".evidence/junit", False, [], runner
    )
    assert targets == [
        _target("a", "pass", 0),
        _target("b", "fail", 2),
        _target("c", "not-run", None),
    ]
    assert [c["argv"] for c in runner.calls] == [
        ["make", "a", "JUNIT_XML=.evidence/junit/a.xml"],
        ["make", "b", "JUNIT_XML=.evidence/junit/b.xml"],
    ]
    assert all(c["env"] is env and c["cwd"] == str(tmp_path) for c in runner.calls)
    # The make control variables never reach a child through the environment
    # (build_child_env refuses them in extra=); they travel as argv instead.
    assert seen and all("extra" not in kw for kw in seen), seen


def test_run_goals_forwards_make_args_before_the_goal_and_junit_last(tmp_path):
    runner = _Runner(reports=())
    ge.run_goals(
        "make", ["a"], str(tmp_path), "e/junit", False, ["-k", "JUNIT_XML=x"], runner
    )
    assert runner.calls[0]["argv"] == [
        "make",
        "-k",
        "JUNIT_XML=x",
        "a",
        "JUNIT_XML=e/junit/a.xml",
    ]


def test_run_goals_deletes_a_stale_report_before_its_goal(tmp_path):
    stale = tmp_path / "e" / "junit" / "a.xml"
    stale.parent.mkdir(parents=True)
    stale.write_text(_PASSING, encoding="utf-8")
    ge.run_goals("make", ["a"], str(tmp_path), "e/junit", False, [], _Runner({}, ()))
    assert not stale.exists()


def test_keep_going_runs_every_goal(repo, monkeypatch):
    monkeypatch.setenv("MAKEFLAGS", "k")
    runner = _Runner(codes={"b": 2, "c": 5})
    assert ge.main(["--gate", "verify", "--", "make", "a", "b", "c"], runner) == 2
    assert len(runner.calls) == 3
    rec = _record(repo)
    assert [(t["name"], t["result"], t["returncode"]) for t in rec["targets"]] == [
        ("a", "pass", 0),
        ("b", "fail", 2),
        ("c", "fail", 5),
    ]


# --- main ---------------------------------------------------------------------


def test_a_green_run_writes_a_complete_record(repo):
    runner = _Runner()
    assert ge.main(["--gate", "verify", "--", "make", "lint", "test"], runner) == 0
    rec = _record(repo)
    head = _git(repo, None, "rev-parse", "HEAD").stdout.decode().strip()
    assert rec["result"] == "pass" and rec["reasons"] == []
    assert rec["schema"] == _SCHEMA_REL and rec["schema_version"] == 1
    assert rec["source"] == {
        "commit": head,
        "dirty": False,
        "tree_changed": False,
        "tree_digest": rec["source"]["tree_digest"],
    }
    assert rec["tests"] == _counts(passed=1)
    assert rec["targets"][0]["tests"] is None
    assert rec["targets"][1]["tests"] == _counts(passed=1)
    assert sorted(rec["checks"]) == sorted(c[0] for c in ge.check_structure.CHECKS)
    assert not (repo / ".evidence" / "verify.json.tmp").exists()


def test_main_passes_a_failing_goal_code_through_and_writes_a_red_record(repo):
    runner = _Runner(codes={"b": 7})
    assert ge.main(["--gate", "verify", "--", "make", "a", "b", "test"], runner) == 7
    rec = _record(repo)
    assert rec["result"] == "fail" and "target-failed" in rec["reasons"]
    assert rec["targets"][1]["returncode"] == 7
    assert rec["targets"][2]["result"] == "not-run"


def test_a_goal_that_exits_0_over_failing_tests_writes_a_red_record(repo):
    """Every goal exits 0, yet its own junit report counts a failure and an
    error: the record is red and the driver exits RED_RECORD, never 0."""
    runner = _Runner(report=_JUNIT)
    code = ge.main(["--gate", "verify", "--", "make", "test"], runner)
    assert code is ge.ExitCode.RED_RECORD
    rec = _record(repo)
    assert rec["result"] == "fail" and rec["reasons"] == ["tests-failed"], rec
    assert rec["targets"][0]["result"] == "pass"
    assert rec["tests"] == _counts(3, 1, 1, 2)


def test_main_never_returns_zero_when_the_writer_crashes(repo, monkeypatch, capsys):
    def boom(root):
        raise RuntimeError("planted check failure")

    monkeypatch.setattr(ge, "check_findings", boom)
    code = ge.main(["--gate", "verify", "--", "make", "test"], _Runner())
    assert code is ge.ExitCode.RED_RECORD
    assert "planted check failure" in capsys.readouterr().err
    rec = _record(repo)
    assert rec["result"] == "fail"
    assert {"writer-error", "checks-unavailable"} & set(rec["reasons"])


def test_a_writer_crash_after_a_failing_goal_keeps_that_goals_code(
    repo, monkeypatch, capsys
):
    real, calls = ge.render, []

    def render_once(record):
        # The placeholder renders; the final record does not.
        calls.append(record)
        if len(calls) > 1:
            raise RuntimeError("planted render failure")
        return real(record)

    monkeypatch.setattr(ge, "render", render_once)
    runner = _Runner(codes={"b": 7})
    assert ge.main(["--gate", "verify", "--", "make", "b"], runner) == 7
    assert "planted render failure" in capsys.readouterr().err
    assert _record(repo)["result"] == "fail"


def test_zero_goals_is_refused_with_a_red_record(repo):
    runner = _Runner()
    assert ge.main(["--gate", "verify", "--", "make"], runner) == 2
    assert runner.calls == []
    rec = _record(repo)
    assert rec["result"] == "fail" and rec["reasons"] == ["zero-targets"]
    assert rec["targets"] == []


def test_a_record_path_git_does_not_ignore_is_refused_before_any_goal(repo, capsys):
    (repo / ".gitignore").write_text("", encoding="utf-8")
    runner = _Runner()
    assert ge.main(["--gate", "verify", "--", "make", "test"], runner) == 2
    err = capsys.readouterr().err
    assert ".gitignore" in err and "evidence.dir" in err
    assert runner.calls == []
    assert not (repo / ".evidence").exists()


def test_a_report_path_git_does_not_ignore_is_refused(repo, capsys):
    """An ignore rule that covers the record but not the junit reports would
    let a goal write a file git lists."""
    (repo / ".gitignore").write_text(".evidence/*.json\n", encoding="utf-8")
    runner = _Runner()
    assert ge.main(["--gate", "verify", "--", "make", "test"], runner) == 2
    assert ".evidence/junit/test.xml" in capsys.readouterr().err
    assert runner.calls == []


def test_an_interrupted_run_leaves_a_red_placeholder_not_a_stale_green(repo):
    assert ge.main(["--gate", "verify", "--", "make", "a", "test"], _Runner()) == 0
    assert _record(repo)["result"] == "pass"
    runner = _Runner(raises={"a": KeyboardInterrupt()})
    assert ge.main(["--gate", "verify", "--", "make", "a", "test"], runner) == 130
    rec = _record(repo)
    assert rec["result"] == "fail" and rec["reasons"] == ["incomplete"]
    assert [t["result"] for t in rec["targets"]] == ["not-run", "not-run"]


def test_a_dry_run_runs_the_goals_and_writes_nothing(repo, monkeypatch):
    monkeypatch.setenv("MAKEFLAGS", "n -- PY=x")
    runner = _Runner(reports=())
    assert ge.main(["--gate", "verify", "--", "make", "a", "test"], runner) == 0
    assert [c["argv"][:3] for c in runner.calls] == [
        ["make", "-n", "PY=x"],
        ["make", "-n", "PY=x"],
    ]
    assert not (repo / ".evidence").exists()


def test_check_messages_carry_no_absolute_root(repo, monkeypatch):
    root = os.getcwd()

    def found(where):
        return [
            ("C", "error", where + os.sep + "docs/x.md: bad"),
            ("C", "warning", os.path.realpath(where) + os.sep + "docs/y.md: odd"),
            ("project:local", "error", "config/z.py: mine"),
        ]

    monkeypatch.setattr(ge.check_structure, "run_checks", found)
    assert ge.main(["--gate", "verify", "--", "make", "test"], _Runner()) == 0
    text = (repo / ".evidence" / "verify.json").read_text("utf-8")
    assert root not in text and os.path.realpath(root) not in text
    rec = json.loads(text)
    assert rec["checks"]["C"] == {
        "errors": ["docs/x.md: bad"],
        "warnings": ["docs/y.md: odd"],
    }
    assert rec["checks"]["project:local"]["errors"] == ["config/z.py: mine"]


def test_every_project_check_stem_is_a_checks_key_the_schema_admits(
    tmp_path, monkeypatch
):
    """check_structure runs any non-dot `*.py` in the project-checks directory
    and names it `project:<stem>`; the record carries that key unchanged, so the
    schema's `checks.propertyNames` must admit every stem check_structure does,
    or the writer publishes a record its own schema rejects."""
    schema = json.loads((_ROOT / _SCHEMA_REL).read_text("utf-8"))
    branch = schema["properties"]["checks"]["oneOf"][0]
    pattern = re.compile(branch["propertyNames"]["pattern"])
    where = tmp_path / "checks"
    where.mkdir()
    for name in ("no-todo.py", "a.b.py", "with space.py", "x+1.py", "plain_1.py"):
        (where / name).write_text("def check(root):\n    return []\n", "utf-8")
    monkeypatch.setattr(ge.check_structure, "ROOT", str(tmp_path))
    names = ge.check_structure._project_check_files("checks")
    assert len(names) == 5, names
    for name in names:
        key = "project:" + name[: -len(".py")]
        assert pattern.search(key), key
    for letter, _check in ge.check_structure.CHECKS:
        assert pattern.search(letter), letter
    for wrong in ("project:", "project:a/b", "lower", "AB"):
        assert not pattern.search(wrong), wrong


def test_outside_git_provenance_is_null_and_the_goals_decide(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.delenv("MAKEFLAGS", raising=False)
    proj = tmp_path / "lone"
    (proj / "config" / "evidence").mkdir(parents=True)
    shutil.copy(str(_ROOT / _SCHEMA_REL), str(proj / _SCHEMA_REL))
    _write_manifest(proj, _evidence_block())
    monkeypatch.chdir(proj)
    monkeypatch.setattr(ge.check_structure, "run_checks", lambda root: [])
    assert ge.main(["--gate", "verify", "--", "make", "test"], _Runner()) == 0
    assert _record(proj)["source"] == {
        "commit": None,
        "dirty": None,
        "tree_changed": None,
        "tree_digest": None,
    }


def test_a_goal_that_changes_what_git_lists_is_red(repo):
    class Writes(_Runner):
        def __call__(self, argv, cwd=None, env=None):
            (Path(cwd) / "stray.txt").write_text("x\n", encoding="utf-8")
            return _Runner.__call__(self, argv, cwd, env)

    code = ge.main(["--gate", "verify", "--", "make", "test"], Writes())
    assert code is ge.ExitCode.RED_RECORD
    rec = _record(repo)
    assert rec["reasons"] == ["tree-changed"]
    assert rec["source"]["tree_changed"] is True


@pytest.mark.parametrize(
    "block, names",
    [
        (None, "evidence"),
        (_evidence_block(dir="/abs/evidence"), "evidence.dir"),
        (_evidence_block(dir="a/../../up"), "evidence.dir"),
        (_evidence_block(dir=3), "evidence.dir"),
        (_evidence_block(schema="config/evidence/absent.json"), "evidence.schema"),
        ("no-const", "schema_version"),
    ],
    ids=["missing", "absolute", "dotdot", "not-a-string", "schema-absent", "no-const"],
)
def test_a_bad_evidence_block_is_refused(repo, capsys, block, names):
    if block == "no-const":
        schema = json.loads((repo / _SCHEMA_REL).read_text("utf-8"))
        del schema["properties"]["schema_version"]["const"]
        (repo / _SCHEMA_REL).write_text(json.dumps(schema), encoding="utf-8")
    else:
        _write_manifest(repo, block)
    runner = _Runner()
    assert ge.main(["--gate", "verify", "--", "make", "test"], runner) == 2
    assert names in capsys.readouterr().err
    assert runner.calls == []
    assert not (repo / ".evidence").exists()


@pytest.mark.parametrize("gate", ["Verify", "../x", "a/b", "", "-v"])
def test_a_malformed_gate_token_is_refused(repo, gate):
    runner = _Runner()
    assert ge.main(["--gate", gate, "--", "make", "test"], runner) == 2
    assert runner.calls == [] and not (repo / ".evidence").exists()


def test_a_malformed_goal_is_refused(repo):
    runner = _Runner()
    assert ge.main(["--gate", "verify", "--", "make", "../x"], runner) == 2
    assert runner.calls == [] and not (repo / ".evidence").exists()


def test_a_rerun_writes_identical_bytes(repo):
    argv = ["--gate", "verify", "--", "make", "lint", "test"]
    assert ge.main(argv, _Runner()) == 0
    first = (repo / ".evidence" / "verify.json").read_bytes()
    assert ge.main(argv, _Runner()) == 0
    assert (repo / ".evidence" / "verify.json").read_bytes() == first


# --- a record or report path through a symlink ----------------------------------


def _snapshot(path):
    """{relative name: bytes, or the link's target} for everything under *path*."""
    out = {}
    for item in sorted(Path(str(path)).rglob("*")):
        rel = str(item.relative_to(path))
        if rel.split(os.sep)[0] == ".git":
            continue
        if item.is_symlink():
            out[rel] = "link:" + os.readlink(str(item))
        elif item.is_file():
            out[rel] = item.read_bytes()
        else:
            out[rel] = "dir"
    return out


def _victim(tmp_path, name="victim"):
    """A directory beside the project holding an earlier green record and a
    stale report, neither of which a refused run may change."""
    victim = tmp_path / name
    (victim / "junit").mkdir(parents=True)
    (victim / "verify.json").write_text('{"result": "pass"}\n', encoding="utf-8")
    (victim / "verify.json.tmp").write_text("precious\n", encoding="utf-8")
    (victim / "junit" / "test.xml").write_text(_PASSING, encoding="utf-8")
    return victim


def _dir_is_a_symlink(repo, victim):
    (repo / ".evidence").symlink_to(victim, target_is_directory=True)
    return ".evidence"


def _parent_is_a_symlink(repo, victim):
    _write_manifest(repo, _evidence_block(dir="out/evidence"))
    (repo / ".gitignore").write_text("out\n", encoding="utf-8")
    (victim / "evidence").mkdir()
    (repo / "out").symlink_to(victim, target_is_directory=True)
    return "out/evidence"


def _record_file_is_a_symlink(repo, victim):
    (repo / ".evidence").mkdir()
    (repo / ".evidence" / "verify.json").symlink_to(victim / "verify.json")
    return ".evidence/verify.json"


def _tmp_file_is_a_symlink(repo, victim):
    (repo / ".evidence").mkdir()
    (repo / ".evidence" / "verify.json.tmp").symlink_to(victim / "verify.json.tmp")
    return ".evidence/verify.json.tmp"


def _report_file_is_a_symlink(repo, victim):
    (repo / ".evidence" / "junit").mkdir(parents=True)
    (repo / ".evidence" / "junit" / "test.xml").symlink_to(
        victim / "junit" / "test.xml"
    )
    return ".evidence/junit/test.xml"


def _report_dir_is_a_symlink(repo, victim):
    (repo / ".evidence").mkdir()
    (repo / ".evidence" / "junit").symlink_to(
        victim / "junit", target_is_directory=True
    )
    return ".evidence/junit/test.xml"


def _a_link_that_stays_inside_the_tree(repo, victim):
    """Where the link points is not asked: git's ignore rule judged the path as
    text, so a link to a tracked directory is as wrong as one that leaves."""
    inside = repo / "docs"
    inside.mkdir()
    (inside / "kept.txt").write_text("tracked\n", encoding="utf-8")
    (repo / ".evidence").symlink_to(inside, target_is_directory=True)
    return ".evidence"


_LINKS = {
    "dir-is-a-symlink": _dir_is_a_symlink,
    "parent-is-a-symlink": _parent_is_a_symlink,
    "record-file-is-a-symlink": _record_file_is_a_symlink,
    "tmp-file-is-a-symlink": _tmp_file_is_a_symlink,
    "report-file-is-a-symlink": _report_file_is_a_symlink,
    "report-dir-is-a-symlink": _report_dir_is_a_symlink,
    "link-inside-the-tree": _a_link_that_stays_inside_the_tree,
}


def _refusal(capsys):
    """The helper's line, the last on stderr: what failed, on which input,
    and after the last `; ` what to do next."""
    line = capsys.readouterr().err.strip().splitlines()[-1]
    assert line.startswith("gate_evidence: refused before any goal ran: "), line
    assert line.count("; ") == 1, line
    return line


# A report path exists only for a goal, so with no goal the two report plants
# guard nothing and are left out rather than run to no purpose.
_LINK_CASES = [(plant, ["test"]) for plant in sorted(_LINKS)] + [
    (plant, []) for plant in sorted(_LINKS) if not plant.startswith("report-")
]


@pytest.mark.parametrize(
    "plant, goals",
    _LINK_CASES,
    ids=["%s-%d-goal" % (plant, len(goals)) for plant, goals in _LINK_CASES],
)
def test_a_record_or_report_path_through_a_symlink_is_refused_before_any_write(
    repo, tmp_path, capsys, plant, goals
):
    """`evidence.dir` is judged as text by the config check and by git's ignore
    rule; a symlinked component points the record, its temporary file and the
    report a goal's stale copy is deleted from somewhere neither looked."""
    victim = _victim(tmp_path)
    named = _LINKS[plant](repo, victim)
    outside, inside = _snapshot(victim), _snapshot(repo)
    runner = _Runner()
    code = ge.main(["--gate", "verify", "--", "make"] + goals, runner)
    assert code is ge.ExitCode.USAGE
    line = _refusal(capsys)
    assert "evidence.dir" in line and "symlink" in line and named in line, line
    assert "config/project.json" in line.rsplit("; ", 1)[1], line
    assert runner.calls == []
    assert _snapshot(victim) == outside
    assert _snapshot(repo) == inside


def test_a_real_evidence_dir_is_not_refused_as_a_symlink(repo, tmp_path):
    """The guard is not vacuous the other way: the same tree with a real
    directory in the link's place runs and writes."""
    (repo / ".evidence" / "junit").mkdir(parents=True)
    assert ge.main(["--gate", "verify", "--", "make", "test"], _Runner()) == 0
    assert _record(repo)["result"] == "pass"


def test_a_project_reached_through_a_symlink_is_not_refused(
    repo, tmp_path, monkeypatch
):
    """Only a link below the project root is asked about: a checkout that is
    itself reached through one (an automount, say) is where the user put it."""
    alias = tmp_path / "alias"
    alias.symlink_to(repo, target_is_directory=True)
    monkeypatch.chdir(alias)
    assert ge.main(["--gate", "verify", "--", "make", "test"], _Runner()) == 0
    assert _record(repo)["result"] == "pass"


def test_a_dry_run_through_a_symlink_writes_and_removes_nothing(
    repo, tmp_path, monkeypatch
):
    victim = _victim(tmp_path)
    _dir_is_a_symlink(repo, victim)
    before = _snapshot(victim)
    monkeypatch.setenv("MAKEFLAGS", "n")
    runner = _Runner(reports=())
    assert ge.main(["--gate", "verify", "--", "make", "test"], runner) == 0
    assert len(runner.calls) == 1
    assert _snapshot(victim) == before


# --- git ran and failed ---------------------------------------------------------


def test_a_git_that_fails_before_the_goals_is_refused_naming_its_status(
    repo, tmp_path, monkeypatch, capsys
):
    """A repository git cannot read is unknown, not absent: the ignore rule
    cannot be asked, so no path is known safe to write."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    (repo / ".git" / "HEAD").write_text("garbage\n", encoding="utf-8")
    runner = _Runner()
    code = ge.main(["--gate", "verify", "--", "make", "test"], runner)
    assert code is ge.ExitCode.USAGE
    line = _refusal(capsys)
    assert "git exited " in line and "evidence.dir" in line, line
    assert runner.calls == []
    assert not (repo / ".evidence").exists()


def test_a_repository_broken_during_the_run_is_a_red_record_not_a_crash(
    repo, tmp_path, monkeypatch
):
    """Readable before the goals and not after: what they did cannot be shown
    harmless, so it counts as a change and the test counts stay in the record."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    class Breaks(_Runner):
        def __call__(self, argv, cwd=None, env=None):
            (Path(cwd) / ".git" / "HEAD").write_text("garbage\n", encoding="utf-8")
            return _Runner.__call__(self, argv, cwd, env)

    code = ge.main(["--gate", "verify", "--", "make", "test"], Breaks())
    assert code is ge.ExitCode.RED_RECORD
    rec = _record(repo)
    assert rec["reasons"] == ["tree-changed"]
    assert rec["source"]["tree_changed"] is True
    assert rec["tests"] == _counts(passed=1)


# --- one date for the whole run -------------------------------------------------

_RUN_DATE = "A_GATE_RUN_DATE"
_TODAY = datetime.date(2031, 3, 1)
_ONE_DAY = datetime.timedelta(days=1)


def _with_run_date(proj, block=None, names=(_RUN_DATE,)):
    """Rewrite the scratch manifest with an `evidence.run_date` block and the
    `child_env.names` list it is checked against."""
    if block is None:
        block = {"env": _RUN_DATE, "max_age_days": 1}
    manifest = {
        "evidence": _evidence_block(run_date=block),
        "child_env": {"names": list(names)},
    }
    (proj / "config" / "project.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


class _Clock:
    """A clock that moves on one day every time it is read."""

    def __init__(self, start=_TODAY):
        self.now = start
        self.reads = 0

    def __call__(self):
        self.reads += 1
        now = self.now
        self.now = now + _ONE_DAY
        return now


def test_every_goal_is_handed_the_one_date_the_driver_read(repo, monkeypatch):
    monkeypatch.delenv(_RUN_DATE, raising=False)
    _with_run_date(repo)
    clock, runner = _Clock(), _Runner()
    argv = ["--gate", "verify", "--", "make", "lint", "check-docs", "test"]
    assert ge.main(argv, runner, clock) == 0
    assert clock.reads == 1
    assert [c["env"].get(_RUN_DATE) for c in runner.calls] == [_TODAY.isoformat()] * 3


def test_a_dry_run_hands_the_date_on_too(repo, monkeypatch):
    monkeypatch.delenv(_RUN_DATE, raising=False)
    monkeypatch.setenv("MAKEFLAGS", "n")
    _with_run_date(repo)
    runner = _Runner(reports=())
    assert ge.main(["--gate", "verify", "--", "make", "test"], runner, _Clock()) == 0
    assert runner.calls[0]["env"].get(_RUN_DATE) == _TODAY.isoformat()


def test_without_the_block_no_goal_is_handed_a_date(repo, monkeypatch):
    """The channel is opt-in: a project whose config has no `evidence.run_date`
    gets today's behaviour, and the driver reads no clock."""
    monkeypatch.setenv(_RUN_DATE, "not-a-date")
    clock, runner = _Clock(), _Runner()
    assert ge.main(["--gate", "verify", "--", "make", "test"], runner, clock) == 0
    assert clock.reads == 0
    assert runner.calls[0]["env"].get(_RUN_DATE) is None


@pytest.mark.parametrize("age", [0, 1])
def test_an_outer_runs_date_is_kept_by_a_nested_driver(repo, monkeypatch, age):
    """A gate goal that itself starts a gate (a test of the driver, say) is
    still inside the outer run: the outer date stands."""
    outer = (_TODAY - age * _ONE_DAY).isoformat()
    monkeypatch.setenv(_RUN_DATE, outer)
    _with_run_date(repo)
    clock, runner = _Clock(), _Runner()
    assert ge.main(["--gate", "verify", "--", "make", "test"], runner, clock) == 0
    assert clock.reads == 1
    assert runner.calls[0]["env"].get(_RUN_DATE) == outer


@pytest.mark.parametrize(
    "supplied, names",
    [
        ((_TODAY - 2 * _ONE_DAY).isoformat(), "evidence.run_date.max_age_days"),
        ((_TODAY + _ONE_DAY).isoformat(), "later"),
        ("not-a-date", "YYYY-MM-DD"),
        ("", "YYYY-MM-DD"),
    ],
    ids=["two-days-old", "tomorrow", "not-a-date", "empty"],
)
def test_a_supplied_date_the_run_could_not_have_is_refused_before_any_goal(
    repo, monkeypatch, capsys, supplied, names
):
    monkeypatch.setenv(_RUN_DATE, supplied)
    _with_run_date(repo)
    runner = _Runner()
    code = ge.main(["--gate", "verify", "--", "make", "test"], runner, _Clock())
    assert code is ge.ExitCode.USAGE
    line = _refusal(capsys)
    assert _RUN_DATE in line and names in line, line
    assert _RUN_DATE in line.rsplit("; ", 1)[1], line
    assert runner.calls == []
    assert not (repo / ".evidence").exists()


@pytest.mark.parametrize(
    "block, names, key",
    [
        ([], (_RUN_DATE,), "evidence.run_date"),
        ({"env": _RUN_DATE}, (_RUN_DATE,), "evidence.run_date.max_age_days"),
        ({"env": _RUN_DATE, "max_age_days": -1}, (_RUN_DATE,), "max_age_days"),
        ({"env": _RUN_DATE, "max_age_days": 1}, ("PATH",), "child_env.names"),
    ],
    ids=["not-an-object", "no-bound", "negative-bound", "not-allowlisted"],
)
def test_a_bad_run_date_block_is_refused(repo, capsys, block, names, key):
    _with_run_date(repo, block, names)
    runner = _Runner()
    assert ge.main(["--gate", "verify", "--", "make", "test"], runner) == 2
    assert key in capsys.readouterr().err
    assert runner.calls == []
    assert not (repo / ".evidence").exists()


def test_the_record_holds_no_date_so_two_days_write_the_same_bytes(repo, monkeypatch):
    monkeypatch.delenv(_RUN_DATE, raising=False)
    _with_run_date(repo)
    argv = ["--gate", "verify", "--", "make", "lint", "test"]
    assert ge.main(argv, _Runner(), _Clock(_TODAY)) == 0
    first = (repo / ".evidence" / "verify.json").read_bytes()
    assert ge.main(argv, _Runner(), _Clock(_TODAY + 40 * _ONE_DAY)) == 0
    assert (repo / ".evidence" / "verify.json").read_bytes() == first
    assert _TODAY.isoformat().encode("ascii") not in first


# --- the old-python floor -------------------------------------------------------


def test_the_writer_is_3_6_safe():
    """The writer must run under an interpreter older than requires-python, so a
    too-old PY still leaves a red record instead of a stale green one."""
    sys.path.insert(0, str(_ROOT / "tests" / "integration"))
    import test_gate_scope as scope

    for name in ("gate_evidence.py", "git_tree.py", "run_date.py"):
        path = _ROOT / "scripts" / name
        assert scope._too_new_syntax(path) == [], name
        assert scope._old_python_safe(path), name
