"""
title: Unit — shell_gate (the shell lint, format and test gates, driven through stub tools)
kind: tests
layer: n/a
summary: scripts/shell_gate.py driven against stub tools, one small Python program put on a private PATH under each name config/project.json `shell.linter`, `shell.formatter` and `shell.test_runner` gives, which records its argv and environment and answers from a plan file. Every mode judges exactly the shell scripts a commit could carry, found by a `shell.script_suffixes` suffix or a `shell.shebang_shells` shebang (an `env` one with options included), never a Python file, a test file, an ignored file, a symlink, a tracked file deleted from the work tree or a file a `shell.excluded_paths` entry covers by whole path parts, an entry that covers no file being CONFIG; the test mode runs exactly the `shell.test_suffixes` files. The tool's own status is the answer, so a finding is the tool's status passed through, and each tool gets the allowlisted environment and never a planted variable. Off (`shell.enabled` false), the gate says why and runs nothing, exit 0; with no shell script and no test file it judges nothing (NOTHING_JUDGED) unless `shell.no_scripts` states the reason, which it prints before it exits 0, and a reason left beside a shell file, or a blank one, is CONFIG; shell scripts with no test file, or test files the runner counts as zero tests, judge nothing (NOTHING_JUDGED), and a runner whose count is not a number gave no verdict (BACKEND_ABSENT). An `env` option that takes an argument (`-u FOO`, `--chdir DIR`) never hides the shell after it, a path that starts with `-` reaches the tool as `./`-prefixed, and a tool in the running interpreter's directory answers before one on PATH, which answers when that directory has none. A tool on neither the interpreter's directory nor PATH is BACKEND_ABSENT naming the tool and its role, an adapter name the module does not know or a malformed suffix list is CONFIG before anything runs, and a tree that is not a git repository judges nothing. The tool names asserted are read from config/project.json through scripts/config_loader.py, never typed here.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import config_loader  # noqa: E402
import shell_gate  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit

_ROLES = ("linter", "formatter", "test_runner")


def _shell_config():
    """keel's shell block, which the fixture copies into each project, so a
    test reads every value it asserts and types none."""
    fields = _ROLES + ("script_suffixes", "shebang_shells", "test_suffixes")
    keys = config_loader.rows(*[("shell", f) for f in fields])
    got = config_loader.resolve(
        config_loader.read(str(_ROOT)), keys, config_loader.CONFIG_FILE
    )
    return {path[-1]: value for path, value in got.items()}


_CFG = _shell_config()
# Kept before the fixture patches it out, for the tests of the lookup order.
_REAL_INTERPRETER_DIR = shell_gate._interpreter_dir
_LINTER, _FORMATTER, _RUNNER = (_CFG[r] for r in _ROLES)

# The stub stands in for every tool: it records what it was handed and answers
# with the plan for its own name, so a test can make a tool find, pass or lie.
_STUB = """#!%s
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
name = os.path.basename(sys.argv[0])
with open(os.path.join(here, "plan.json")) as fh:
    plan = json.load(fh).get(name, {})
argv = sys.argv[1:]
with open(os.path.join(here, "calls.jsonl"), "a") as fh:
    fh.write(json.dumps({"tool": name, "argv": argv, "env": dict(os.environ)}) + "\\n")
answer = plan.get("count" if "--count" in argv else "run", {})
sys.stdout.write(answer.get("stdout", ""))
sys.exit(answer.get("rc", 0))
"""


def _git(repo, env, *argv):
    subprocess.run(
        ["git", *argv], cwd=str(repo), env=env, check=True, capture_output=True
    )


class _Project:
    def __init__(self, root, bin_dir, env):
        self.root = root
        self.bin_dir = bin_dir
        self.env = env

    def plan(self, **tools):
        (self.bin_dir / "plan.json").write_text(json.dumps(tools), encoding="utf-8")

    def calls(self, tool=None):
        path = self.bin_dir / "calls.jsonl"
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        return [r for r in rows if tool is None or r["tool"] == tool]

    def shell(self, **values):
        path = self.root / "config" / "project.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["shell"].update(values)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def write(self, rel, text, mode=None):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if mode is not None:
            path.chmod(mode)
        return path

    def commit_all(self):
        _git(self.root, self.env, "add", "-A")
        _git(self.root, self.env, "commit", "-q", "-m", "more")

    def run(self, *argv):
        return shell_gate.main(list(argv), root=str(self.root))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A committed project with keel's config and one stub per tool on a
    private PATH that holds git and nothing else of the host's, so a real
    linter on the machine running the suite cannot answer for a stub."""
    work = tmp_path / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    shutil.copyfile(
        str(_ROOT / "config" / "project.json"), str(root / "config" / "project.json")
    )
    proj = _Project(root, tmp_path / "bin", env)
    # Keel's own reason for having no shell file would go stale the moment a
    # test plants one, so each test starts from the strict null and opts in.
    proj.shell(no_scripts=None)
    (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git(root, env, "init", "-q")
    _git(root, env, "add", "-A")
    _git(root, env, "commit", "-q", "-m", "init")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in (_LINTER, _FORMATTER, _RUNNER):
        stub = bin_dir / name
        stub.write_text(_STUB % sys.executable, encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    os.symlink(shutil.which("git"), str(bin_dir / "git"))
    monkeypatch.setenv("PATH", str(bin_dir))
    # The interpreter's own directory is searched first in a real run (a tool a
    # venv installed); here it would let the host's tools answer for a stub.
    monkeypatch.setattr(shell_gate, "_interpreter_dir", lambda: None)
    proj.plan()
    return proj


def _plant_tree(project):
    """Every shape a shell script takes, and every near miss, committed."""
    project.write("scripts/build.sh", "echo build\n")
    project.write("scripts/deploy.bash", "echo deploy\n")
    project.write("scripts/release", "#!/bin/sh\necho release\n", mode=0o755)
    project.write("ops/rotate", "#!/usr/bin/env -S bash -eu\necho rotate\n")
    project.write("scripts/tool.py", "#!/usr/bin/env python3\nprint(1)\n")
    project.write("scripts/notes.txt", "#!not a shell\n")
    project.write("tests/shell/build.bats", "#!/usr/bin/env bats\n@test x { :; }\n")
    project.write("ignored/skip.sh", "echo skipped\n")
    project.write("scripts/gone.sh", "echo gone\n")
    os.symlink("build.sh", str(project.root / "scripts" / "alias.sh"))
    project.commit_all()
    (project.root / "scripts" / "gone.sh").unlink()


_SCRIPTS = ["ops/rotate", "scripts/build.sh", "scripts/deploy.bash", "scripts/release"]
_TESTS = ["tests/shell/build.bats"]


# --- what each mode judges ---------------------------------------------------


def test_lint_runs_the_linter_over_every_shell_script_a_commit_could_carry(project):
    _plant_tree(project)
    assert project.run("lint") == ExitCode.SUCCESS
    (call,) = project.calls(_LINTER)
    assert call["argv"][-len(_SCRIPTS) :] == _SCRIPTS, call["argv"]
    assert project.calls(_FORMATTER) == project.calls(_RUNNER) == []


def test_an_untracked_script_git_does_not_ignore_is_judged_too(project):
    project.write("scripts/new.sh", "echo new\n")
    assert project.run("lint") == ExitCode.SUCCESS
    (call,) = project.calls(_LINTER)
    assert call["argv"][-1] == "scripts/new.sh", call["argv"]


@pytest.mark.parametrize("rc", [1, 3])
def test_the_linters_status_is_the_answer(project, rc):
    _plant_tree(project)
    project.plan(**{_LINTER: {"run": {"rc": rc}}})
    assert int(project.run("lint")) == rc


def test_format_check_and_format_run_the_formatter_in_two_different_ways(project):
    _plant_tree(project)
    assert project.run("format-check") == ExitCode.SUCCESS
    assert project.run("format") == ExitCode.SUCCESS
    check, write = project.calls(_FORMATTER)
    assert check["argv"][-len(_SCRIPTS) :] == _SCRIPTS
    assert write["argv"][-len(_SCRIPTS) :] == _SCRIPTS
    assert check["argv"] != write["argv"], "a check that writes is not a check"
    project.plan(**{_FORMATTER: {"run": {"rc": 1}}})
    assert int(project.run("format-check")) == 1


def test_the_test_mode_counts_then_runs_exactly_the_test_files(project):
    _plant_tree(project)
    project.plan(**{_RUNNER: {"count": {"stdout": "3\n"}}})
    assert project.run("test") == ExitCode.SUCCESS
    count, run = project.calls(_RUNNER)
    assert "--count" in count["argv"] and "--count" not in run["argv"]
    assert count["argv"][-1:] == run["argv"][-1:] == _TESTS
    project.plan(**{_RUNNER: {"count": {"stdout": "3\n"}, "run": {"rc": 1}}})
    assert int(project.run("test")) == 1


def test_test_files_that_hold_no_test_judge_nothing(project, capsys):
    _plant_tree(project)
    project.plan(**{_RUNNER: {"count": {"stdout": "0\n"}}})
    assert project.run("test") == ExitCode.NOTHING_JUDGED
    assert len(project.calls(_RUNNER)) == 1, "the runner ran over zero tests"
    assert "0 tests" in capsys.readouterr().err


@pytest.mark.parametrize(
    "answer", [{"stdout": "many\n"}, {"stdout": ""}, {"stdout": "4\n", "rc": 1}]
)
def test_a_runner_that_gives_no_count_gave_no_verdict(project, answer):
    _plant_tree(project)
    project.plan(**{_RUNNER: {"count": answer}})
    assert project.run("test") == ExitCode.BACKEND_ABSENT
    assert len(project.calls(_RUNNER)) == 1


def test_shell_scripts_with_no_test_file_judge_nothing(project, capsys):
    project.write("scripts/build.sh", "echo build\n")
    project.commit_all()
    assert project.run("test") == ExitCode.NOTHING_JUDGED
    assert project.calls() == []
    err = capsys.readouterr().err
    assert "scripts/build.sh" in err and _CFG["test_suffixes"][0] in err, err


_MODES = ["lint", "format-check", "format", "test"]
_REASON = "this project's scripts are all Python"


@pytest.mark.parametrize("mode", _MODES)
def test_a_project_with_no_shell_file_and_no_reason_judged_nothing(
    project, mode, capsys
):
    assert project.run(mode) == ExitCode.NOTHING_JUDGED
    assert project.calls() == []
    assert "shell.no_scripts" in capsys.readouterr().err


@pytest.mark.parametrize("mode", _MODES)
def test_a_stated_reason_lets_a_project_with_no_shell_file_pass(project, mode, capsys):
    project.shell(no_scripts=_REASON)
    assert project.run(mode) == ExitCode.SUCCESS
    assert project.calls() == []
    out = capsys.readouterr().out
    assert "shell.no_scripts" in out and _REASON in out, out


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize(
    "rel, text",
    [("scripts/build.sh", "echo build\n"), ("tests/shell/a.bats", "@test x { :; }\n")],
)
def test_a_reason_left_in_place_once_a_shell_file_exists_is_stale(
    project, mode, rel, text, capsys
):
    project.shell(no_scripts=_REASON)
    project.write(rel, text)
    assert project.run(mode) == ExitCode.CONFIG
    assert project.calls() == []
    err = capsys.readouterr().err
    assert "shell.no_scripts" in err and rel in err, err


def test_a_blank_reason_is_refused(project, capsys):
    project.shell(no_scripts=" ")
    assert project.run("lint") == ExitCode.CONFIG
    assert "shell.no_scripts" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["lint", "format-check", "format", "test"])
def test_shell_switched_off_runs_nothing_and_says_why(project, mode, capsys):
    _plant_tree(project)
    project.shell(enabled=False)
    assert project.run(mode) == ExitCode.SUCCESS
    assert project.calls() == []
    assert "shell.enabled" in capsys.readouterr().out


def test_an_env_option_that_takes_an_argument_does_not_hide_the_shell(project):
    # `-u FOO` unsets FOO: FOO is the option's argument, not the interpreter.
    project.write("ops/clean", "#!/usr/bin/env -u FOO bash\necho clean\n")
    project.write("ops/chdir", "#!/usr/bin/env --chdir /tmp sh\necho chdir\n")
    project.commit_all()
    assert project.run("lint") == ExitCode.SUCCESS
    (call,) = project.calls(_LINTER)
    assert call["argv"][-2:] == ["ops/chdir", "ops/clean"], call["argv"]


def test_a_path_that_starts_with_a_dash_is_handed_over_as_a_path(project):
    project.write("-x.sh", "echo x\n")
    project.commit_all()
    assert project.run("lint") == ExitCode.SUCCESS
    (call,) = project.calls(_LINTER)
    assert call["argv"][-1] == "./-x.sh", call["argv"]
    assert "-x.sh" not in call["argv"], call["argv"]


def test_an_excluded_path_and_everything_under_it_is_never_judged(project):
    _plant_tree(project)
    project.write("vendor/lib/third.sh", "echo vendored\n")
    project.write("vendor/lib/third.bats", "@test v { :; }\n")
    project.write("scripts/copied.sh", "echo copied\n")
    project.shell(
        excluded_paths={
            "vendor/lib": "a vendored library, judged upstream",
            "scripts/copied.sh": "copied verbatim from upstream",
        }
    )
    project.commit_all()
    project.plan(**{_RUNNER: {"count": {"stdout": "1\n"}}})
    for mode in ("lint", "format-check", "test"):
        assert project.run(mode) == ExitCode.SUCCESS
    lint, check, count, test = project.calls()
    for call in (lint, check):
        assert call["argv"][-len(_SCRIPTS) :] == _SCRIPTS, call["argv"]
    assert count["argv"][-1:] == test["argv"][-1:] == _TESTS


def test_an_exclusion_that_covers_no_file_is_stale(project, capsys):
    _plant_tree(project)
    project.shell(excluded_paths={"vendor/gone": "removed upstream"})
    assert project.run("lint") == ExitCode.CONFIG
    assert project.calls() == []
    err = capsys.readouterr().err
    assert "shell.excluded_paths" in err and "vendor/gone" in err, err


def test_a_prefix_of_a_name_is_not_its_directory(project, capsys):
    # `scripts/bu` covers scripts/bu and scripts/bu/x, never scripts/build.sh.
    _plant_tree(project)
    project.shell(excluded_paths={"scripts/bu": "a near miss"})
    assert project.run("lint") == ExitCode.CONFIG
    assert "scripts/bu" in capsys.readouterr().err


# --- what each tool is handed --------------------------------------------------


def test_each_tool_gets_the_allowlisted_environment(project, monkeypatch):
    _plant_tree(project)
    monkeypatch.setenv("KEEL_PLANTED_SECRET", "not-for-children")
    project.plan(**{_RUNNER: {"count": {"stdout": "1\n"}}})
    for mode in ("lint", "format-check", "test"):
        assert project.run(mode) == ExitCode.SUCCESS
    calls = project.calls()
    assert len(calls) == 4
    for call in calls:
        assert "KEEL_PLANTED_SECRET" not in call["env"], call["tool"]
        assert call["env"]["PATH"] == str(project.bin_dir)


def _venv_with(project, tmp_path, monkeypatch, *tools):
    """An interpreter directory holding a stub for each of *tools*, made the
    running interpreter's directory the way a virtual environment is."""
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    for name in tools:
        shutil.copy2(str(project.bin_dir / name), str(venv_bin / name))
    (venv_bin / "plan.json").write_text("{}", encoding="utf-8")
    # The real _interpreter_dir reads sys.executable; nothing here spawns it.
    monkeypatch.setattr(shell_gate, "_interpreter_dir", _REAL_INTERPRETER_DIR)
    monkeypatch.setattr(sys, "executable", str(venv_bin / "python"))
    return venv_bin


def _calls_in(directory):
    path = directory / "calls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_tool_in_the_interpreters_directory_wins_over_path(
    project, tmp_path, monkeypatch
):
    _plant_tree(project)
    venv_bin = _venv_with(project, tmp_path, monkeypatch, _LINTER)
    assert project.run("lint") == ExitCode.SUCCESS
    assert [c["tool"] for c in _calls_in(venv_bin)] == [_LINTER]
    assert project.calls() == [], "PATH's tool answered for the venv's"


def test_a_tool_missing_from_the_interpreters_directory_is_found_on_path(
    project, tmp_path, monkeypatch
):
    _plant_tree(project)
    venv_bin = _venv_with(project, tmp_path, monkeypatch)
    assert project.run("lint") == ExitCode.SUCCESS
    assert _calls_in(venv_bin) == []
    assert [c["tool"] for c in project.calls()] == [_LINTER]


# --- refusals ------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode, role",
    [
        ("lint", "linter"),
        ("format-check", "formatter"),
        ("format", "formatter"),
        ("test", "test_runner"),
    ],
)
def test_a_missing_tool_is_backend_absent_naming_it(project, mode, role, capsys):
    _plant_tree(project)
    (project.bin_dir / _CFG[role]).unlink()
    assert project.run(mode) == ExitCode.BACKEND_ABSENT
    err = capsys.readouterr().err
    assert _CFG[role] in err and "shell." + role in err, err


@pytest.mark.parametrize("role", _ROLES)
def test_an_adapter_the_module_does_not_know_is_config(project, role, capsys):
    _plant_tree(project)
    project.shell(**{role: "not-a-known-tool"})
    mode = {"linter": "lint", "formatter": "format", "test_runner": "test"}[role]
    assert project.run(mode) == ExitCode.CONFIG
    assert project.calls() == []
    assert "not-a-known-tool" in capsys.readouterr().err


@pytest.mark.parametrize(
    "key, value",
    [
        ("script_suffixes", ["sh"]),
        ("script_suffixes", []),
        ("test_suffixes", [".b/ats"]),
        ("shebang_shells", ["/bin/sh"]),
        ("enabled", "yes"),
        ("excluded_paths", {"vendor": " "}),
        ("excluded_paths", {"../vendor": "outside the project"}),
        ("excluded_paths", {"/vendor": "absolute"}),
        ("excluded_paths", {"vendor/": "a trailing slash"}),
        ("excluded_paths", ["vendor"]),
    ],
)
def test_a_malformed_shell_block_is_config_before_anything_runs(
    project, key, value, capsys
):
    _plant_tree(project)
    project.shell(**{key: value})
    assert project.run("lint") == ExitCode.CONFIG
    assert project.calls() == []
    assert "shell." + key in capsys.readouterr().err


def test_a_tree_that_is_not_a_repository_judges_nothing(project, capsys):
    _plant_tree(project)
    shutil.rmtree(str(project.root / ".git"))
    assert project.run("lint") == ExitCode.NOTHING_JUDGED
    assert project.calls() == []
    assert "git" in capsys.readouterr().err
