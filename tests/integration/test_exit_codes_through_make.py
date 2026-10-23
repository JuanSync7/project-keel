"""
title: Integration — an exit code reaches a caller of make as 2, and make's error line carries the number
kind: tests
layer: n/a
summary: Each failing ExitCode member is the status of a scratch makefile's recipe, a real child process that ends through scripts/exit_codes.py `finish`, run by real GNU make with the allowlisted environment from scripts/child_env.py. make exits 2 for every member, and the last line it writes names the recipe's own number as `Error <N>`, so a caller acts on the number alone only when it runs the script itself, as the comment above RED_RECORD in scripts/exit_codes.py, the exit-code section of docs/guides/limits-and-troubleshooting.md and docs/guides/generate-and-upgrade.md say. SUCCESS ends make with 0. A planted judge that expects the member's own number from make is the proof the cases can fail. It does not judge what a script prints before it exits (tests/integration/test_exit_codes_cli.py).
@covers scripts/exit_codes.py
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import child_env  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.integration

# GNU make's status when a recipe it ran failed (make(1), EXIT STATUS).
_MAKE_RECIPE_FAILED = 2
_GOAL = "end"
# make's own report of a failed recipe: `make: *** [<file>:<line>: <goal>] Error <N>`.
_ERROR_LINE = re.compile(r"^make: \*\*\* \[[^\]]*\b%s\] Error (\d+)$" % _GOAL)
_FAILING = [member for member in ExitCode if member is not ExitCode.SUCCESS]


def _makefile(scripts, member):
    """A makefile whose one recipe ends with *member* through `finish`."""
    program = "import sys; sys.path.insert(0, %r); import exit_codes; " % str(
        scripts
    ) + ("exit_codes.finish(exit_codes.ExitCode.%s)" % member.name)
    return '%s:\n\t%s -c "%s"\n' % (_GOAL, sys.executable, program)


def _run_make(tmp_path, member):
    makefile = tmp_path / "Makefile"
    makefile.write_text(_makefile(_ROOT / "scripts", member), encoding="utf-8")
    return subprocess.run(
        ["make", "-f", str(makefile), _GOAL],
        cwd=str(tmp_path),
        env=child_env.build_child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def judge(member, proc, expected_status):
    """The findings for one make run; empty when make exited
    *expected_status* and its last line names *member*'s number."""
    findings = []
    if proc.returncode != expected_status:
        findings.append(
            "%s: make exited %d, expected %d"
            % (member.name, proc.returncode, expected_status)
        )
    lines = proc.stdout.splitlines()
    named = _ERROR_LINE.match(lines[-1]) if lines else None
    if named is None or int(named.group(1)) != int(member):
        findings.append(
            "%s: make's last line does not say `Error %d`: %r"
            % (member.name, int(member), lines[-1:])
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


# Each place that tells a caller it can act on the number, and so must say
# what make leaves of it.
_CLAIMS = (
    "scripts/exit_codes.py",
    "docs/guides/limits-and-troubleshooting.md",
    "docs/guides/generate-and-upgrade.md",
)


@pytest.mark.parametrize("path", _CLAIMS)
def test_each_claim_names_the_line_make_carries_the_number_on(path):
    text = (_ROOT / path).read_text("utf-8")
    assert "Error <N>" in text, "%s does not name make's `Error <N>` line" % path
