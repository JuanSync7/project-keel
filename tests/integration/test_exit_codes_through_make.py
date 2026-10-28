"""
title: Integration — an exit code reaches a caller of make as 2, and make's error line carries the number
kind: tests
layer: n/a
summary: Each failing ExitCode member is the status of a scratch makefile's recipe, a real child process that ends through scripts/exit_codes.py `finish`, run by real GNU make with the allowlisted environment from scripts/child_env.py. make exits 2 for every member, and its error line for the recipe names the recipe's own number as `Error <N>`; under `make -k` later output follows that line, and through keel's real `verify` driver line (a scratch repository running scripts/gate_evidence.py) the outer make says `Error 2` while the number is on the goal's own make line before it. So a caller acts on the number alone only when it runs the script itself, as the comment above RED_RECORD in scripts/exit_codes.py, the exit-code section of docs/guides/limits-and-troubleshooting.md and docs/guides/generate-and-upgrade.md say. SUCCESS ends make with 0. A planted judge that expects the member's own number from make is the proof the cases can fail. Each claim file's block that names `Error <N>` must also say the number alone serves only a caller that runs the script itself and that make hands back 2; the planted old claim, token kept, is refused. It does not judge what a script prints before it exits (tests/integration/test_exit_codes_cli.py).
@covers scripts/exit_codes.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

sys.path.insert(0, str(_ROOT / "tests"))

import check_structure as cs  # noqa: E402
import child_env  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import hermetic_git  # noqa: E402
import script_copy  # noqa: E402

pytestmark = pytest.mark.integration

_EVIDENCE = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))[
    "evidence"
]

# GNU make's status when a recipe it ran failed (make(1), EXIT STATUS).
_MAKE_RECIPE_FAILED = 2
_GOAL = "end"
# make's own report of a failed recipe, at any make level:
# `make: *** [<file>:<line>: <target>] Error <N>`.
_ERROR_LINE = re.compile(r"^make(?:\[\d+\])?: \*\*\* \[[^\]]*: (\S+)\] Error (\d+)$")
_FAILING = [member for member in ExitCode if member is not ExitCode.SUCCESS]


def _program(scripts, member):
    """A one-line Python program that ends with *member* through `finish`."""
    return "import sys; sys.path.insert(0, %r); import exit_codes; " % str(scripts) + (
        "exit_codes.finish(exit_codes.ExitCode.%s)" % member
    )


def _makefile(scripts, member):
    """A makefile whose one recipe ends with *member* through `finish`."""
    return '%s:\n\t%s -c "%s"\n' % (
        _GOAL,
        sys.executable,
        _program(scripts, member.name),
    )


def _run(argv, cwd, env):
    return subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def _run_make(tmp_path, member):
    makefile = tmp_path / "Makefile"
    makefile.write_text(_makefile(_ROOT / "scripts", member), encoding="utf-8")
    return _run(
        ["make", "-f", str(makefile), _GOAL], tmp_path, child_env.build_child_env()
    )


def error_lines(output):
    """[(target, number)] for each make error line in *output*, in order."""
    lines = output.splitlines()
    return [
        (named.group(1), int(named.group(2)))
        for named in map(_ERROR_LINE.match, lines)
        if named
    ]


def judge(member, proc, expected_status):
    """The findings for one make run; empty when make exited
    *expected_status* and its error line for the goal names *member*'s number."""
    findings = []
    if proc.returncode != expected_status:
        findings.append(
            "%s: make exited %d, expected %d"
            % (member.name, proc.returncode, expected_status)
        )
    if (_GOAL, int(member)) not in error_lines(proc.stdout):
        findings.append(
            "%s: no make line says `%s] Error %d`" % (member.name, _GOAL, int(member))
        )
    return findings


def test_every_failing_member_is_named():
    assert _FAILING, "the enum has no failing member -- zero items"
    # 10 to 14 are the members a caller would act on by number.
    assert {10, 11, 12, 13, 14} <= {int(member) for member in _FAILING}


@pytest.mark.parametrize("member", _FAILING, ids=lambda member: member.name)
def test_make_exits_2_and_names_the_recipes_own_number(tmp_path, member):
    proc = _run_make(tmp_path, member)
    assert judge(member, proc, _MAKE_RECIPE_FAILED) == [], proc.stdout


def test_a_recipe_that_succeeds_ends_make_with_0(tmp_path):
    proc = _run_make(tmp_path, ExitCode.SUCCESS)
    assert proc.returncode == 0, proc.stdout


def test_a_judge_that_expects_the_number_through_make_fails(tmp_path):
    """Fault injection: the claim this file corrects, that make hands the
    caller the recipe's own number, is what the judge reports as wrong."""
    member = ExitCode.NOTHING_JUDGED
    proc = _run_make(tmp_path, member)
    findings = judge(member, proc, int(member))
    assert findings == ["NOTHING_JUDGED: make exited 2, expected 13"], findings


def test_under_k_the_error_line_is_not_make_s_last_line(tmp_path):
    """make -k runs a later goal after a failed one, so the line naming the
    failed recipe's number is make's line for that target, not its last."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        _makefile(_ROOT / "scripts", ExitCode.CONFIG) + "later:\n\techo later ran\n",
        encoding="utf-8",
    )
    proc = _run(
        ["make", "-k", "-f", str(makefile), _GOAL, "later"],
        tmp_path,
        child_env.build_child_env(),
    )
    assert proc.returncode == _MAKE_RECIPE_FAILED, proc.stdout
    assert error_lines(proc.stdout) == [(_GOAL, int(ExitCode.CONFIG))], proc.stdout
    assert _ERROR_LINE.match(proc.stdout.splitlines()[-1]) is None, proc.stdout


# The driver keel's `verify` recipe runs and the siblings it imports;
# tests/script_copy.py adds any import this list misses.
_GATE_SCRIPTS = (
    "gate_evidence.py",
    "git_tree.py",
    "child_env.py",
    "check_structure.py",
    "config_loader.py",
    "exit_codes.py",
    "run_date.py",
)
# A test run under the gate runner carries the outer make's state; the scratch
# gate must start from none of it.
_MAKE_INHERITANCE = ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES", "RALPH")


def _scratch_verify():
    """keel's own verify recipe with its `$(MAKE)` goals swapped for `end`."""
    text = (_ROOT / "Makefile").read_text("utf-8")
    (rule,) = [r for r in cs.make_target_rules(text) if r.target == "verify"]
    (cmd,) = rule.recipe
    goals, unresolved = cs._recursions(cmd)
    assert goals and not unresolved, (cmd, unresolved)
    tail = " ".join(goals)
    assert cmd.endswith(tail), cmd
    return "verify:\n\t%s%s\n" % (cmd[: -len(tail)], _GOAL)


@pytest.fixture(scope="module")
def gate(tmp_path_factory):
    """A committed scratch repository whose `verify` is keel's own driver line
    over one goal that ends with the member `MEMBER=` names; (repo, env)."""
    base = tmp_path_factory.mktemp("gate")
    env = {k: v for k, v in os.environ.items() if k not in _MAKE_INHERITANCE}
    (base / "work").mkdir()
    env.update(hermetic_git.git_env_vars(base / "work"))
    repo = base / "repo"
    (repo / "scripts").mkdir(parents=True)
    script_copy.copy_with_imports(repo, _ROOT, ["scripts/" + n for n in _GATE_SCRIPTS])
    (repo / "config").mkdir()
    shutil.copy(
        str(_ROOT / "config" / "project.json"), str(repo / "config" / "project.json")
    )
    schema = repo / _EVIDENCE["schema"]
    schema.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(str(_ROOT / _EVIDENCE["schema"]), str(schema))
    (repo / ".gitignore").write_text(
        "%s/\n__pycache__/\n" % _EVIDENCE["dir"], encoding="utf-8"
    )
    (repo / "Makefile").write_text(
        'PY ?= python3\n.PHONY: verify %s\n%s%s:\n\t$(PY) -c "%s"\n'
        % (
            _GOAL,
            _scratch_verify(),
            _GOAL,
            _program(repo / "scripts", "$(MEMBER)"),
        ),
        encoding="utf-8",
    )
    for argv in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "init")):
        out = _run(["git"] + list(argv), repo, env)
        assert out.returncode == 0, out.stdout
    return repo, env


@pytest.mark.parametrize("member", _FAILING, ids=lambda member: member.name)
def test_make_verify_names_the_number_on_the_goal_s_own_make_line(gate, member):
    """Through keel's real verify driver, the outer make's line names the
    driver's status, 2 for a failing goal; the recipe's own number is only on
    the goal's own make line, before it."""
    repo, env = gate
    proc = _run(
        ["make", "PY=" + sys.executable, "MEMBER=" + member.name, "verify"], repo, env
    )
    assert proc.returncode == _MAKE_RECIPE_FAILED, proc.stdout
    assert error_lines(proc.stdout) == [
        (_GOAL, int(member)),
        ("verify", _MAKE_RECIPE_FAILED),
    ], proc.stdout


# Each place that tells a caller it can act on the number, and so must say
# what make leaves of it.
_CLAIMS = (
    "scripts/exit_codes.py",
    "docs/guides/limits-and-troubleshooting.md",
    "docs/guides/generate-and-upgrade.md",
)
# What the block naming `Error <N>` must say, each as a pattern and the fact it
# stands for: the bare token alone let the old false claim back in.
_CLAIM_PARTS = (
    (r"Error <N>", "make's error line that still carries the number"),
    (r"runs? (?:a|the) script itself", "the number alone serves only a direct caller"),
    (r"\b2\b", "through make the caller sees 2"),
    (
        r"`make verify`.*goal's own make",
        "through `make verify` the number is on the goal's own make line",
    ),
)
# What such a block must not say: make -k and `make verify` both print lines
# after the one that names the recipe's number.
_CLAIM_FORBIDDEN = ((r"last line", "the number is on make's last line"),)


def _blocks(text):
    """*text* cut into the blocks a claim is made in: markdown paragraphs and
    list items, and runs of `#` comment lines in Python."""
    blocks, current, comment = [], [], None
    for line in text.splitlines():
        stripped = line.strip()
        is_comment = stripped.startswith("#")
        if not stripped or is_comment != comment or stripped.startswith("- "):
            if current:
                blocks.append(" ".join(current))
            current = []
        comment = is_comment
        if stripped:
            current.append(stripped.lstrip("#").strip() if is_comment else stripped)
    if current:
        blocks.append(" ".join(current))
    return blocks


def claim_findings(text):
    """The findings for one claim file; empty when a block names `Error <N>`
    and every such block says each fact in `_CLAIM_PARTS`."""
    named = [block for block in _blocks(text) if "Error <N>" in block]
    if not named:
        return ["no block names make's `Error <N>` line"]
    return [
        "%r does not say: %s" % (block[:60], fact)
        for block in named
        for pattern, fact in _CLAIM_PARTS
        if not re.search(pattern, block)
    ] + [
        "%r says: %s" % (block[:60], fact)
        for block in named
        for pattern, fact in _CLAIM_FORBIDDEN
        if re.search(pattern, block)
    ]


@pytest.mark.parametrize("path", _CLAIMS)
def test_each_claim_says_what_make_leaves_of_the_number(path):
    findings = claim_findings((_ROOT / path).read_text("utf-8"))
    assert findings == [], (path, findings)


def test_the_old_claim_with_the_token_kept_is_refused():
    """Fault injection: the reviewer's planted claim, which kept `Error <N>`
    and dropped the direct-caller limit, is what the guard reports."""
    planted = (
        "# A caller can then act on the number alone, through make too, which\n"
        "# carries it as `Error <N>`.\n"
    )
    findings = claim_findings(planted)
    assert [f.split(": ", 1)[1] for f in findings] == [
        "the number alone serves only a direct caller",
        "through make the caller sees 2",
        "through `make verify` the number is on the goal's own make line",
    ], findings
