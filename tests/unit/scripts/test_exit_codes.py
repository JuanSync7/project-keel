"""
title: Unit — exit_codes (the closed list of exit codes and the one place a process ends)
kind: tests
layer: n/a
summary: ExitCode is a closed, alias-free enum whose every member carries its value, a meaning and what to do, and compares equal to its int. report writes exactly one `<what>: <on>; <next>` line to the stream it is given (stderr by default, never stdout) and returns the member; it refuses a blank or non-string part by name, a bare int and SUCCESS, and writes nothing when it refuses. passthrough wraps a wrapped tool's status, spells a signal death the way the shell does and refuses anything but an int. finish exits with a member's or a passed-through value, and exits USAGE with one line naming the value when it is handed a bare int, a bool or None. fail is finish over report. The module parses on the oldest interpreter a hook runs it under, and runs there when the host has one.
"""

import ast
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "tests" / "integration"))

import exit_codes  # noqa: E402
import test_gate_scope as gate_scope  # noqa: E402
from child_env import build_child_env  # noqa: E402
from exit_codes import (  # noqa: E402
    BlankMessagePart,
    ExitCode,
    PassedThrough,
    fail,
    finish,
    passthrough,
    report,
)

pytestmark = pytest.mark.unit

_HELPER = _ROOT / "scripts" / "exit_codes.py"
_PARTS = ("what", "on", "next_step")
# Statuses another program already gives a meaning, as inclusive (first, last)
# bands; a member a script chooses for a fact of its own stays outside them, so
# a caller that reads the number alone cannot take one for the other.
_TAKEN_BANDS = (
    # 0 and 1 are the shell's, 2 is argparse's and make's, 1 to 5 are pytest's.
    (0, 5),
    # sysexits.h.
    (64, 78),
    # timeout(1), `git bisect` skip, not executable, not found, then 128+signal.
    (124, 165),
    # What a shell reports for an exit status out of range.
    (255, 255),
)
# The two facts one number used to carry, and the member that no longer exists.
_SPLIT_MEMBERS = ("RED_RECORD", "BACKEND_ABSENT")
_RETIRED_MEMBER = "UNAVAILABLE"


def test_the_enum_is_closed_unique_and_every_member_says_what_it_means_and_what_to_do():
    members = list(ExitCode)
    assert members, "no member -- zero items"
    # __members__ lists an alias under its own name; a closed list has none.
    assert len(ExitCode.__members__) == len(members)
    assert len({int(m) for m in members}) == len(members)
    for member in members:
        assert isinstance(member, int) and member == member.value
        for text in (member.meaning, member.action):
            assert isinstance(text, str) and text.strip(), member
    assert ExitCode.SUCCESS == 0
    assert ExitCode(1) is ExitCode.FAILURE and ExitCode(2) is ExitCode.USAGE
    with pytest.raises(ValueError):
        ExitCode(4)
    assert sorted(exit_codes.__all__) == sorted(
        ["BlankMessagePart", "ExitCode", "PassedThrough", "fail", "finish"]
        + ["passthrough", "report"]
    )


def test_the_red_record_and_the_absent_backend_are_two_members_with_their_own_value_meaning_and_action():
    """One number carries one fact: a red evidence record and a backend that
    did not answer each have a member, and neither value is one a shell,
    argparse, make, pytest, sysexits.h or a signal already uses."""
    names = set(ExitCode.__members__)
    assert _RETIRED_MEMBER not in names
    assert set(_SPLIT_MEMBERS) <= names, sorted(names)
    red, absent = (ExitCode[name] for name in _SPLIT_MEMBERS)
    assert int(red) != int(absent)
    others = [m for m in ExitCode if m not in (red, absent)]
    assert others, "no other member -- zero items"
    for member in (red, absent):
        assert all(int(member) != int(other) for other in others), member
        taken = [band for band in _TAKEN_BANDS if band[0] <= int(member) <= band[1]]
        assert taken == [], (member, taken)
        assert member.meaning.strip() and member.action.strip(), member
    assert red.meaning != absent.meaning
    assert red.action != absent.action


def test_report_writes_one_line_and_returns_the_member(capsys):
    buf = io.StringIO()
    assert report(ExitCode.FAILURE, "a", "b", "c", stream=buf) is ExitCode.FAILURE
    assert buf.getvalue() == "a: b; c\n"
    assert capsys.readouterr() == ("", "")
    assert report(ExitCode.USAGE, "x", "y", "z") is ExitCode.USAGE
    assert capsys.readouterr() == ("", "x: y; z\n")


@pytest.mark.parametrize("part", _PARTS)
@pytest.mark.parametrize("blank", ["", "   ", "\n", None, 3])
def test_report_refuses_a_blank_part_and_names_it(part, blank):
    parts = dict.fromkeys(_PARTS, "said")
    parts[part] = blank
    buf = io.StringIO()
    with pytest.raises(BlankMessagePart) as refused:
        report(ExitCode.FAILURE, stream=buf, **parts)
    assert part in str(refused.value)
    assert buf.getvalue() == ""
    assert issubclass(BlankMessagePart, ValueError)


@pytest.mark.parametrize("code", [1, 0, True, None, "FAILURE", ExitCode.SUCCESS])
def test_report_refuses_a_non_member_and_success(code):
    buf = io.StringIO()
    with pytest.raises((TypeError, ValueError)):
        report(code, "a", "b", "c", stream=buf)
    assert buf.getvalue() == ""


def test_passthrough_keeps_a_status_and_spells_a_signal_as_the_shell_does():
    assert passthrough(7) == 7 and isinstance(passthrough(7), PassedThrough)
    assert passthrough(0) == 0
    assert passthrough(-2) == 130 and passthrough(-9) == 137
    # A status above one byte is the caller's to see, never clamped here.
    assert passthrough(300) == 300
    for bad in (None, "2", True, 1.0):
        with pytest.raises(TypeError):
            passthrough(bad)


def _exit_of(call):
    with pytest.raises(SystemExit) as stop:
        call()
    return stop.value.code


def test_finish_exits_with_the_member_value_and_refuses_a_bare_int(capsys):
    assert _exit_of(lambda: finish(ExitCode.USAGE)) == 2
    assert _exit_of(lambda: finish(ExitCode.SUCCESS)) == 0
    assert _exit_of(lambda: finish(passthrough(7))) == 7
    assert _exit_of(lambda: finish(passthrough(-2))) == 130
    assert capsys.readouterr() == ("", "")
    for bad in (1, 0, None, True, "1"):
        assert _exit_of(lambda bad=bad: finish(bad)) == ExitCode.USAGE
        out, err = capsys.readouterr()
        assert out == "" and err.count("\n") == 1 and repr(bad) in err, err


def test_fail_writes_the_line_and_exits_with_the_member(capsys):
    assert _exit_of(lambda: fail(ExitCode.FAILURE, "a", "b", "c")) == 1
    assert capsys.readouterr() == ("", "a: b; c\n")
    with pytest.raises(BlankMessagePart):
        fail(ExitCode.FAILURE, "a", " ", "c")


def test_the_helper_parses_on_the_oldest_supported_python_and_imports_only_the_stdlib():
    """The pre-commit hooks and copier's own interpreter run scripts that import
    this module; test_gate_scope holds the same rule for every hook entry."""
    assert gate_scope._too_new_syntax(_HELPER) == []
    assert gate_scope._old_python_safe(_HELPER)
    tree = ast.parse(_HELPER.read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]


def test_the_helper_runs_on_an_old_host_interpreter_when_there_is_one():
    """Opportunistic, which is why the syntax test above never depends on it."""
    old = gate_scope._old_python3()
    if old is None:
        pytest.skip("no python3 below requires-python on this host")
    # The highest status a script chooses for a fact of its own: one a bare
    # interpreter never exits with by itself.
    member = max(m for m in ExitCode if m is not ExitCode.INTERRUPTED)
    code = (
        "import sys; sys.path.insert(0, %r); import exit_codes as e; "
        "e.finish(e.report(e.ExitCode.%s, 'a', 'b', 'c'))"
        % (os.path.join(str(_ROOT), "scripts"), member.name)
    )
    done = subprocess.run(
        [old, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=build_child_env(),
    )
    assert done.returncode == member, done.stderr
    assert done.stderr == b"a: b; c\n" and done.stdout == b""
