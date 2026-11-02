"""
title: Unit — child_exec (a shell script re-runs itself under the child environment allowlist)
kind: tests
layer: n/a
summary: scripts/child_exec.py, pinned: it replaces itself with the program it is handed, under the environment scripts/child_env.py `build_child_env` builds plus `MARKER` set to its own pid, so a variable outside the allowlist never reaches the program and the program can tell it was re-run; no program is USAGE, an allowlist that cannot be built is CONFIG naming the program, and a program that cannot be started is USAGE naming it. End to end, a script that opens with `REEXEC_LINE` runs its body once, under the allowlist, and a marker its parent exported does not let it skip the re-run.
@covers scripts/child_exec.py
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import child_env  # noqa: E402
import child_exec  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit

# A variable no child_env allowlist source admits.
_OUTSIDE = "KEEL_TEST_NOT_ALLOWLISTED"


class _Execed(Exception):
    """The captured exec: like the real one, it never returns."""


@pytest.fixture
def execed(monkeypatch):
    """Capture the exec child_exec would make, instead of making it."""
    calls = []

    def fake(program, argv, env):
        calls.append((program, list(argv), dict(env)))
        raise _Execed

    monkeypatch.setattr(child_exec.os, "execvpe", fake)
    return calls


def test_the_program_runs_under_the_allowlist_with_the_marker_set_to_this_pid(
    execed, monkeypatch
):
    monkeypatch.setenv(_OUTSIDE, "1")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "/usr/bin"))
    with pytest.raises(_Execed):
        child_exec.main(["/some/script.sh", "a b", "c"])
    [(program, argv, env)] = execed
    assert program == "/some/script.sh"
    assert argv == ["/some/script.sh", "a b", "c"]
    assert _OUTSIDE not in env
    assert env["PATH"] == os.environ["PATH"]
    assert env[child_exec.MARKER] == str(os.getpid())


def test_no_program_is_usage(execed, capsys):
    assert child_exec.main([]) is ExitCode.USAGE
    assert execed == []
    assert "child_exec" in capsys.readouterr().err


def test_an_allowlist_that_cannot_be_built_is_config_naming_the_program(
    execed, monkeypatch, capsys
):
    def broken(**_kwargs):
        raise child_env.ChildEnvError("config/project.json: child_env is broken")

    monkeypatch.setattr(child_exec.child_env, "build_child_env", broken)
    assert child_exec.main(["/some/script.sh"]) is ExitCode.CONFIG
    assert execed == []
    err = capsys.readouterr().err
    assert "/some/script.sh" in err and "child_env is broken" in err


def test_a_program_that_cannot_be_started_is_usage_naming_it(
    monkeypatch, capsys, tmp_path
):
    script = tmp_path / "not-executable.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    assert child_exec.main([str(script)]) is ExitCode.USAGE
    err = capsys.readouterr().err
    assert str(script) in err and "chmod +x" in err


def _script(tmp_path, body):
    script = tmp_path / "s.sh"
    script.write_text(
        "#!/bin/sh\n"
        + child_exec.REEXEC_LINE.replace(
            '"$(dirname "$0")/child_exec.py"',
            '"%s"' % (_ROOT / "scripts" / "child_exec.py"),
        )
        + "\n"
        + body,
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def _run(script, extra):
    # The parent environment is built here, not inherited, so the variable the
    # allowlist must drop is the only thing under test.
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/")}
    env.update(extra)
    return subprocess.run(
        [str(script)], env=env, capture_output=True, text=True, check=False
    )


def test_a_script_runs_its_body_once_under_the_allowlist(tmp_path):
    script = _script(tmp_path, 'echo "ran outside=${%s-unset} pid=$$"\n' % _OUTSIDE)
    r = _run(script, {_OUTSIDE: "leaked"})
    assert r.returncode == 0, r.stderr
    [line] = r.stdout.splitlines()
    assert line.startswith("ran outside=unset pid=")


def test_a_marker_the_parent_exported_does_not_skip_the_rerun(tmp_path):
    script = _script(tmp_path, 'echo "outside=${%s-unset}"\n' % _OUTSIDE)
    r = _run(script, {_OUTSIDE: "leaked", child_exec.MARKER: "1"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["outside=unset"]
