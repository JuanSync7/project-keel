"""
title: Unit — child_exec (a shell script re-runs itself under the child environment allowlist)
kind: tests
layer: n/a
summary: scripts/child_exec.py, pinned: it replaces itself with the program it is handed, under the environment scripts/child_env.py `build_child_env` builds plus `MARKER` set to its own pid, so a variable outside the allowlist never reaches the program and the program can tell it was re-run; no program is USAGE, an allowlist that cannot be built is CONFIG naming the program, and a file that cannot be read or whose interpreter cannot be started is USAGE naming it. It starts the file by its path, never a PATH search, under the interpreter its `#!` line names (read as Linux reads it) or /bin/sh, so the execute bit does not matter. End to end, a script that opens with `REEXEC_LINE` runs its body once, under the allowlist; a marker its parent exported does not let it skip the re-run; and `sh probe.sh` re-runs the file here, not a namesake on PATH, with or without the execute bit.
@covers scripts/child_exec.py
"""

import errno
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

    monkeypatch.setattr(child_exec.os, "execve", fake)
    return calls


def _file(tmp_path, first_line, name="script.sh"):
    path = tmp_path / name
    path.write_text(first_line + "echo body\n", encoding="utf-8")
    return str(path)


def test_the_program_runs_under_the_allowlist_with_the_marker_set_to_this_pid(
    execed, monkeypatch, tmp_path
):
    monkeypatch.setenv(_OUTSIDE, "1")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "/usr/bin"))
    script = _file(tmp_path, "#!/bin/sh\n")
    with pytest.raises(_Execed):
        child_exec.main([script, "a b", "c"])
    [(program, argv, env)] = execed
    assert program == "/bin/sh"
    assert argv == ["/bin/sh", script, "a b", "c"]
    assert _OUTSIDE not in env
    assert env["PATH"] == os.environ["PATH"]
    assert env[child_exec.MARKER] == str(os.getpid())


@pytest.mark.parametrize(
    "first_line, start",
    [
        ("#!/bin/sh\n", ["/bin/sh"]),
        ("#! /bin/bash\n", ["/bin/bash"]),
        ("#!/usr/bin/env bash\n", ["/usr/bin/env", "bash"]),
        ("#!/usr/bin/env bash -e -u \n", ["/usr/bin/env", "bash -e -u"]),
        ("echo no shebang\n", ["/bin/sh"]),
        ("#!\n", ["/bin/sh"]),
    ],
    ids=[
        "sh",
        "a space after #!",
        "env",
        "one argument, as Linux reads it",
        "no #! line",
        "an empty #! line",
    ],
)
def test_the_file_starts_by_its_path_under_its_shebang_interpreter(
    tmp_path, first_line, start
):
    script = _file(tmp_path, first_line)
    assert child_exec.start_argv(script) == start + [script]


def test_a_bare_name_is_the_file_here_never_a_path_search(tmp_path, monkeypatch):
    _file(tmp_path, "#!/bin/sh\n", name="probe.sh")
    monkeypatch.chdir(tmp_path)
    assert child_exec.start_argv("probe.sh") == ["/bin/sh", "./probe.sh"]


def test_no_program_is_usage(execed, capsys):
    assert child_exec.main([]) is ExitCode.USAGE
    assert execed == []
    assert "child_exec" in capsys.readouterr().err


def test_an_allowlist_that_cannot_be_built_is_config_naming_the_program(
    execed, monkeypatch, capsys, tmp_path
):
    def broken(**_kwargs):
        raise child_env.ChildEnvError("config/project.json: child_env is broken")

    monkeypatch.setattr(child_exec.child_env, "build_child_env", broken)
    script = _file(tmp_path, "#!/bin/sh\n")
    assert child_exec.main([script]) is ExitCode.CONFIG
    assert execed == []
    err = capsys.readouterr().err
    assert script in err and "child_env is broken" in err


@pytest.mark.parametrize(
    "make",
    [
        lambda path: None,
        lambda path: path.mkdir(),
        lambda path: path.write_text("#!/no/such/shell\n", encoding="utf-8"),
    ],
    ids=["absent", "a directory", "an interpreter that does not exist"],
)
def test_a_program_that_cannot_be_started_is_usage_naming_it(
    capsys, monkeypatch, tmp_path, make
):
    def guarded(program, argv, env):
        # A real exec here would replace pytest itself, so only the kernel's
        # refusal of an absent interpreter is reproduced.
        if not os.path.exists(program):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT))
        raise _Execed

    monkeypatch.setattr(child_exec.os, "execve", guarded)
    script = tmp_path / "s.sh"
    make(script)
    assert child_exec.main([str(script)]) is ExitCode.USAGE
    err = capsys.readouterr().err
    assert str(script) in err and "#!" in err


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


def _run(command, extra, cwd=None, path=None):
    # The parent environment is built here, not inherited, so the variable the
    # allowlist must drop is the only thing under test.
    env = {"PATH": path or os.environ["PATH"], "HOME": os.environ.get("HOME", "/")}
    env.update(extra)
    return subprocess.run(
        [str(word) for word in command],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_script_runs_its_body_once_under_the_allowlist(tmp_path):
    script = _script(tmp_path, 'echo "ran outside=${%s-unset} pid=$$"\n' % _OUTSIDE)
    r = _run([script], {_OUTSIDE: "leaked"})
    assert r.returncode == 0, r.stderr
    [line] = r.stdout.splitlines()
    assert line.startswith("ran outside=unset pid=")


def test_a_marker_the_parent_exported_does_not_skip_the_rerun(tmp_path):
    script = _script(tmp_path, 'echo "outside=${%s-unset}"\n' % _OUTSIDE)
    r = _run([script], {_OUTSIDE: "leaked", child_exec.MARKER: "1"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["outside=unset"]


def test_a_script_handed_to_a_shell_by_bare_name_reruns_itself_not_a_namesake(
    tmp_path,
):
    """`sh probe.sh` ran the file here, so its re-run must too, whatever PATH holds."""
    here = tmp_path / "here"
    here.mkdir()
    _script(here, 'echo "body outside=${%s-unset}"\n' % _OUTSIDE).rename(
        here / "probe.sh"
    )
    namesake = tmp_path / "bin"
    namesake.mkdir()
    (namesake / "probe.sh").write_text("#!/bin/sh\necho NAMESAKE\n", encoding="utf-8")
    (namesake / "probe.sh").chmod(0o755)
    r = _run(
        ["sh", "probe.sh"],
        {_OUTSIDE: "leaked"},
        cwd=str(here),
        path="%s:%s" % (namesake, os.environ["PATH"]),
    )
    assert (r.returncode, r.stdout) == (0, "body outside=unset\n"), r.stderr


def test_a_script_without_the_execute_bit_reruns_when_handed_to_a_shell(tmp_path):
    script = _script(tmp_path, 'echo "body outside=${%s-unset}"\n' % _OUTSIDE)
    script.chmod(0o644)
    r = _run(["sh", script], {_OUTSIDE: "leaked"})
    assert (r.returncode, r.stdout) == (0, "body outside=unset\n"), r.stderr
