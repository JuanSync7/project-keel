"""
title: Integration — the gate's evidence record, written by a real gate run
kind: tests
layer: n/a
summary: A scratch git repository carrying the evidence writer, its siblings, keel's own config/project.json, schema and `test` recipe runs a real reduced gate through scripts/gate_evidence.py with real make, pytest and git. Two runs on the same tree exit 0 and write byte-identical records naming HEAD, a clean tree and pytest's own counts, with no absolute path, host or user in them, and leave what git lists unchanged (the writer's rerun_proof). A planted failing test keeps make's real exit code and leaves a red record naming the dirty tree; under `make -i` the exit is 0, as -i asks, and the record is still red (tests-failed). `make -n` runs nothing and writes nothing. The record validates against config/evidence/gate-record.schema.json and each fault twin (missing field, wrong type, extra field, unknown version) is rejected. keel and its template both ignore config/project.json `evidence.dir`; a generated project, which has no template twin, judges its own tree only. docs/guides/deterministic-checks.md's section on the record names the schema's fields and reasons and the verify recipe's goals, read back and held equal to those owners.
@covers scripts/gate_evidence.py
"""

import getpass
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import check_structure as cs  # noqa: E402
import gate_evidence  # noqa: E402
import git_tree  # noqa: E402

import hermetic_git  # noqa: E402
import optional_deps  # noqa: E402

pytestmark = pytest.mark.integration

_MANIFEST = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
_EVIDENCE = _MANIFEST["evidence"]
# The writer and the stdlib siblings it imports: what a generated project runs.
_SCRIPTS = (
    "gate_evidence.py",
    "git_tree.py",
    "child_env.py",
    "check_structure.py",
    "exit_codes.py",
)
# A test run under the gate runner carries the outer make's state; a scratch make
# must start from none of it.
_MAKE_INHERITANCE = ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES", "RALPH")

_TEST_OK = """def test_one():
    assert 1 + 1 == 2


def test_two():
    assert "a".upper() == "A"
"""


def _keel_rule(name):
    """keel's own rule for *name*, as makefile text: the line make reads, so the
    scratch gate runs the recipe keel ships, not a retyped copy."""
    text = (_ROOT / "Makefile").read_text("utf-8")
    (rule,) = [r for r in cs.make_target_rules(text) if r.target == name]
    return "%s: %s\n%s\n" % (
        name,
        " ".join(rule.prereqs),
        "".join("\t%s\n" % line for line in rule.recipe),
    )


# The goals the scratch gate runs in place of keel's: one that passes without a
# test report, and keel's real `test` recipe.
_SCRATCH_GOALS = ("ok", "test")


def _keel_verify():
    """keel's `verify` rule and the goals its one `$(MAKE)` line names."""
    text = (_ROOT / "Makefile").read_text("utf-8")
    (rule,) = [r for r in cs.make_target_rules(text) if r.target == "verify"]
    return rule


def _scratch_verify():
    """keel's own verify recipe with its `$(MAKE)` goals swapped for the scratch
    goals, so the scratch gate runs the driver line keel ships."""
    rule = _keel_verify()
    (cmd,) = rule.recipe
    goals, unresolved = cs._recursions(cmd)
    assert goals and not unresolved, (cmd, unresolved)
    tail = " ".join(goals)
    assert cmd.endswith(tail), cmd
    return "verify:\n\t%s%s\n" % (cmd[: -len(tail)], " ".join(_SCRATCH_GOALS))


def _makefile():
    return (
        "PY ?= python3\n"
        "PYTHONPATH ?= src:.\n"
        ".PHONY: verify test check-python ok\n"
        + _scratch_verify()
        + "check-python: ; @true\n"
        "ok: ; @true\n" + _keel_rule("test")
    )


def _env(work):
    env = {k: v for k, v in os.environ.items() if k not in _MAKE_INHERITANCE}
    env.update(hermetic_git.git_env_vars(work))
    return env


def _run(cwd, env, *argv):
    return subprocess.run(
        list(argv),
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def _build(base):
    """A committed scratch repository holding a reduced gate; (repo, env)."""
    work = base / "work"
    work.mkdir()
    env = _env(work)
    repo = base / "repo"
    (repo / "scripts").mkdir(parents=True)
    for name in _SCRIPTS:
        shutil.copy(str(_ROOT / "scripts" / name), str(repo / "scripts" / name))
    (repo / "config").mkdir()
    shutil.copy(
        str(_ROOT / "config" / "project.json"), str(repo / "config" / "project.json")
    )
    schema = repo / _EVIDENCE["schema"]
    schema.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(str(_ROOT / _EVIDENCE["schema"]), str(schema))
    (repo / ".gitignore").write_text(
        "%s/\n.pytest_cache/\n__pycache__/\n" % _EVIDENCE["dir"], encoding="utf-8"
    )
    (repo / "Makefile").write_text(_makefile(), encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ok.py").write_text(_TEST_OK, encoding="utf-8")
    for argv in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "init")):
        out = _run(repo, env, "git", *argv)
        assert out.returncode == 0, out.stdout
    return repo, env


def _verify(repo, env, *flags):
    return _run(repo, env, "make", *flags, "PY=" + sys.executable, "verify")


def _record_path(repo):
    return repo / _EVIDENCE["dir"] / "verify.json"


@pytest.fixture(scope="module")
def gate(tmp_path_factory):
    """The scratch gate run twice on one committed tree."""
    repo, env = _build(tmp_path_factory.mktemp("gate"))
    runs = []
    for _ in range(2):
        out = _verify(repo, env)
        status = _run(repo, env, "git", "status", "--porcelain").stdout
        runs.append((out, _record_path(repo).read_bytes(), status))
    return repo, env, runs


def test_a_real_gate_writes_byte_identical_records_on_a_rerun(gate):
    repo, env, runs = gate
    for out, _data, status in runs:
        assert out.returncode == 0, out.stdout
        assert status == "", status
    (_o1, first, _s1), (_o2, second, _s2) = runs
    assert first and first == second
    text = first.decode("utf-8")
    rec = json.loads(text)
    head = _run(repo, env, "git", "rev-parse", "HEAD").stdout.strip()
    assert rec["result"] == "pass" and rec["reasons"] == [], rec
    assert rec["tests"] == {"passed": 2, "failed": 0, "skipped": 0, "errors": 0}
    assert rec["source"]["commit"] == head
    assert rec["source"]["dirty"] is False
    assert rec["source"]["tree_changed"] is False
    assert [t["name"] for t in rec["targets"]] == list(_SCRATCH_GOALS)
    assert sorted(c[0] for c in cs.CHECKS) == sorted(
        k for k in rec["checks"] if not k.startswith("project:")
    )
    for leak in (str(repo), os.path.realpath(str(repo)), socket.gethostname()):
        assert leak not in text, leak
    assert '"%s"' % getpass.getuser() not in text
    assert text == json.dumps(rec, indent=2, sort_keys=True) + "\n"


def test_a_planted_failing_test_keeps_the_real_exit_and_writes_a_red_record(
    tmp_path,
):
    repo, env = _build(tmp_path)
    assert _verify(repo, env).returncode == 0
    clean = json.loads(_record_path(repo).read_text("utf-8"))
    (repo / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    out = _verify(repo, env)
    # make's own code for a failed recipe, passed through the driver and the
    # outer make unchanged.
    assert out.returncode == 2, out.stdout
    rec = json.loads(_record_path(repo).read_text("utf-8"))
    assert rec["result"] == "fail" and "target-failed" in rec["reasons"], rec
    test = [t for t in rec["targets"] if t["name"] == "test"][0]
    assert test["result"] == "fail" and test["returncode"] == 2
    assert rec["tests"]["failed"] == 1 and rec["tests"]["passed"] == 2
    assert rec["source"]["dirty"] is True
    assert rec["source"]["tree_digest"] != clean["source"]["tree_digest"]


def test_make_i_verify_over_a_failing_test_still_writes_a_red_record(tmp_path):
    """`make -i` ignores every recipe's exit, so the `test` goal exits 0 over a
    failing test and the outer make exits 0 too: make's own semantics, no greener
    than before the record. The record judges pytest's counts, not only the goal's
    exit, so it is red and names the failure."""
    repo, env = _build(tmp_path)
    (repo / "tests" / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    out = _verify(repo, env, "-i")
    assert "(ignored)" in out.stdout, out.stdout
    rec = json.loads(_record_path(repo).read_text("utf-8"))
    assert rec["result"] == "fail", rec
    assert rec["reasons"] == ["tests-failed"], rec
    test = [t for t in rec["targets"] if t["name"] == "test"][0]
    assert test["result"] == "pass" and test["returncode"] == 0, test
    assert rec["tests"]["failed"] == 1, rec


def test_make_n_verify_runs_nothing_and_writes_nothing(tmp_path):
    repo, env = _build(tmp_path)
    out = _verify(repo, env, "-n")
    assert out.returncode == 0, out.stdout
    assert "--junitxml=" in out.stdout, out.stdout
    assert not (repo / _EVIDENCE["dir"]).exists()
    assert not (repo / ".pytest_cache").exists()


def test_the_record_validates_and_each_fault_twin_is_rejected(gate):
    jsonschema = optional_deps.importorskip("jsonschema", extra="dev")
    schema = json.loads((_ROOT / _EVIDENCE["schema"]).read_text("utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    _repo, _env, runs = gate
    rec = json.loads(runs[0][1].decode("utf-8"))
    validator.validate(rec)

    def twin(edit):
        bad = json.loads(json.dumps(rec))
        edit(bad)
        return bad

    twins = {
        "missing field": twin(lambda r: r.pop("gate")),
        "wrong type": twin(lambda r: r["tests"].__setitem__("passed", "2")),
        "extra field": twin(lambda r: r.__setitem__("host", "box")),
        "unknown version": twin(lambda r: r.__setitem__("schema_version", 2)),
    }
    for name, bad in twins.items():
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(bad)
        assert name


def test_evidence_dir_is_ignored_in_keel_and_its_template(tmp_path):
    """Real git judges each ignore file this checkout ships: its own
    `.gitignore` and, in keel, the template's `.gitignore.jinja` twin. Each is
    judged alone in a fresh scratch repository, because the copier suite runs a
    generated project's tests before that project is a git work tree, and
    because a checkout's own `.git/info/exclude` must not be able to pass it."""
    rel = _EVIDENCE["dir"] + "/verify.json"
    files = [f for f in (".gitignore", ".gitignore.jinja") if (_ROOT / f).exists()]
    assert ".gitignore" in files, "no .gitignore to judge"
    work = tmp_path / "work"
    work.mkdir()
    env = _env(work)
    for name in files:
        proj = tmp_path / name.lstrip(".")
        proj.mkdir()
        shutil.copy(str(_ROOT / name), str(proj / ".gitignore"))
        assert _run(proj, env, "git", "init", "-q").returncode == 0
        assert git_tree.is_ignored(str(proj), rel), (name, rel)


def test_keels_verify_recipe_runs_the_driver_over_the_goals_check_w_reads():
    """The goals moved from prerequisites into the driver's `$(MAKE)` line, so a
    failing goal still lets the driver write a red record; check_W reads that
    line, so the label closure is the same as before."""
    rule = _keel_verify()
    assert rule.prereqs == [], rule.prereqs
    (cmd,) = rule.recipe
    assert cmd.startswith("$(PY) scripts/gate_evidence.py --gate $@ -- $(MAKE) "), cmd
    goals, unresolved = cs._recursions(cmd)
    assert goals == [
        "check-all",
        "lint",
        "typecheck",
        "test",
        "trace",
        "eval",
        "test-fe",
    ], goals
    assert unresolved == [], unresolved
    assert rule.recursions == goals, rule.recursions
    assert cs.target_effects(str(_ROOT))["verify"] == (("local",), None)
    (test_rule,) = [
        r
        for r in cs.make_target_rules((_ROOT / "Makefile").read_text("utf-8"))
        if r.target == "test"
    ]
    assert any("$(JUNIT_XML)" in line for line in test_rule.recipe), test_rule.recipe


# A goal list a document spells beside `make verify`: a `(`- or `#`-led run of
# make-target names joined by `+`, backticked or bare, across a line break.
_DOC_GOAL_LIST = re.compile(
    r"make verify`?[ \t]*(?:\(|#)\s*(`?[\w-]+`?(?:\s*\+\s*`?[\w-]+`?)+)"
)


def test_every_document_that_spells_the_verify_goals_spells_the_makefiles():
    """CMP-4.S5 added `test-fe` to verify while CONVENTIONS.md and two guides
    still listed four goals. Every document that writes verify's goals out as
    `make verify (a + b + ...)` or `make verify  # a + b + ...` must name
    exactly the goals keel's recipe runs, in its order. The tree is walked as
    check_structure walks it, not listed by git: a generated project runs this
    suite before it has a repository."""
    goals, _unresolved = cs._recursions(_keel_verify().recipe[0])
    seen, stale = 0, []
    for dirpath, _dirs, files in sorted(cs.walk(str(_ROOT))):
        for name in sorted(files):
            if not name.endswith((".md", ".md.jinja")):
                continue
            path = Path(dirpath) / name
            text = path.read_text("utf-8")
            for m in _DOC_GOAL_LIST.finditer(text):
                seen += 1
                named = [g.strip().strip("`") for g in m.group(1).split("+")]
                if named != goals:
                    line = text.count("\n", 0, m.start()) + 1
                    stale.append(
                        "%s:%d lists %s" % (path.relative_to(_ROOT), line, named)
                    )
    assert seen, "no document spells verify's goals: the pattern matches nothing"
    assert stale == [], "verify runs %s, but\n%s" % (goals, "\n".join(stale))


def _goal(name, counts):
    return {"name": name, "result": "pass", "returncode": 0, "tests": counts}


def test_a_goal_without_a_report_adds_no_counts_and_no_red():
    """`make verify` runs the frontend suites as their own goal, which writes no
    junit report, so its `tests` is null. That null adds nothing to the counts
    and is not by itself `no-test-report` while pytest's goal reported; with
    pytest's report missing the record is still red. A change that read a null
    as zeros would turn that red reason into `zero-tests` and fail here."""
    counts = {"passed": 5, "failed": 0, "skipped": 1, "errors": 0}
    targets = [_goal("test", counts), _goal("test-fe", None)]
    tests = gate_evidence._sum_counts(targets)
    assert tests == counts, tests
    assert gate_evidence.overall(targets, tests, False, True) == ("pass", [])

    targets = [_goal("test", None), _goal("test-fe", None)]
    tests = gate_evidence._sum_counts(targets)
    assert tests is None, tests
    assert gate_evidence.overall(targets, tests, False, True) == (
        "fail",
        ["no-test-report"],
    )


# A writer that crashes, planted into the scratch copy: the check pass inside the
# driver raising, and the renderer itself raising. Each must leave the gate red and
# replace the green record a clean run left.
_CRASHES = {
    "checks": (
        "check_structure.py",
        "\n\ndef run_checks(root):\n    raise RuntimeError('planted')\n",
        "checks-unavailable",
    ),
    "writer": (
        "gate_evidence.py",
        "\n\ndef render(record):\n    raise RuntimeError('planted')\n",
        "writer-error",
    ),
}


@pytest.mark.parametrize("where", sorted(_CRASHES))
def test_a_crashing_writer_keeps_the_gate_red_and_replaces_the_green_record(
    tmp_path, where
):
    repo, env = _build(tmp_path)
    assert _verify(repo, env).returncode == 0
    green = json.loads(_record_path(repo).read_text("utf-8"))
    assert green["result"] == "pass", green
    script, plant, reason = _CRASHES[where]
    path = repo / "scripts" / script
    text = path.read_text("utf-8")
    main_guard = 'if __name__ == "__main__":'
    if main_guard in text:
        head, tail = text.rsplit(main_guard, 1)
        text = head + plant.lstrip("\n") + "\n\n" + main_guard + tail
    else:
        text += plant
    path.write_text(text, encoding="utf-8")
    out = _verify(repo, env)
    # The driver exits 3 (every goal passed, the evidence is red); make reports
    # its failed recipe as 2. Never 0.
    assert out.returncode == 2, out.stdout
    assert "planted" in out.stdout, out.stdout
    rec = json.loads(_record_path(repo).read_text("utf-8"))
    assert rec["result"] == "fail" and reason in rec["reasons"], rec


def test_the_test_policy_variable_reaches_the_goal_through_the_driver(tmp_path):
    """tests/optional_deps.py turns a skip into a failure when its variable names
    the surface. The driver hands each goal the allowlisted environment, so the
    variable must be on the allowlist, or `make verify` would quietly skip what
    the caller declared required: a gate greener than the caller asked for."""
    repo, env = _build(tmp_path)
    name = optional_deps.ENV_VAR
    (repo / "tests" / "test_policy.py").write_text(
        "import os\n\n\ndef test_policy():\n"
        "    assert os.environ.get(%r) == 'dev'\n" % name,
        encoding="utf-8",
    )
    env = dict(env)
    env[name] = "dev"
    out = _verify(repo, env)
    assert out.returncode == 0, out.stdout
    rec = json.loads(_record_path(repo).read_text("utf-8"))
    assert rec["tests"]["passed"] == 3, rec


# --- the guide's section on the record, held equal to the files that own it ----

_GUIDE = _ROOT / "docs" / "guides" / "deterministic-checks.md"
_SECTION = "## The gate's evidence record"


def _guide_section():
    text = _GUIDE.read_text("utf-8")
    assert _SECTION in text, "%s lost its section %r" % (_GUIDE.name, _SECTION)
    body = text.split(_SECTION, 1)[1]
    return re.split(r"(?m)^## ", body, maxsplit=1)[0]


def _table_rows(section):
    """{first-cell text: second-cell text} for each body row of the field table."""
    rows = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 2 and "`" in cells[0]:
            rows[cells[0]] = cells[1]
    return rows


def _ticked(text):
    return re.findall(r"`([^`]+)`", text)


def test_the_guide_names_the_record_as_the_schema_and_the_makefile_define_it():
    """docs/guides/deterministic-checks.md describes the record's fields, its
    closed reasons vocabulary and the goals `make verify` runs. The schema owns
    the first two and keel's verify recipe the third, so each copy in the guide
    is read back and held equal to its owner: a rename in either one fails here
    until the guide follows."""
    schema = json.loads((_ROOT / _EVIDENCE["schema"]).read_text("utf-8"))
    section = _guide_section()
    rows = _table_rows(section)
    fields = sorted(f for cell in rows for f in _ticked(cell))
    assert fields == sorted(schema["properties"]), fields
    (reasons_row,) = [v for k, v in rows.items() if "`reasons`" in k]
    assert "closed vocabulary:" in reasons_row, reasons_row
    named = _ticked(reasons_row.split("closed vocabulary:", 1)[1])
    assert sorted(named) == sorted(schema["$defs"]["reason"]["enum"]), named
    for key, owner in (
        ("`source`", schema["properties"]["source"]["properties"]),
        ("`tests`", schema["$defs"]["counts"]["properties"]),
    ):
        missing = sorted(set(owner) - set(_ticked(rows[key])))
        assert not missing, (key, missing)
    target_results = schema["$defs"]["target"]["properties"]["result"]["enum"]
    missing = sorted(set(target_results) - set(_ticked(rows["`targets`"])))
    assert not missing, missing
    goals = re.search(r"runs each goal \(([^)]*)\)", section)
    assert goals, "the guide no longer lists the goals verify runs"
    (cmd,) = _keel_verify().recipe
    assert _ticked(goals.group(1)) == cs._recursions(cmd)[0], goals.group(1)
