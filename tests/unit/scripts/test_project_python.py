"""
title: Unit — project interpreter launcher
summary: Temporary Git repositories and interpreter stubs prove local priority, main-checkout fallback, explicit refusals, transparent forwarding and Python 3.6 compatibility throughout the launcher's script imports.
@covers scripts/project_python.py
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402
from exit_codes import ExitCode  # noqa: E402
from jobs.conflict_guard import job_closure  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit
_LAUNCHER = _ROOT / "scripts/project_python.py"
_TIMEOUT = config_loader.resolve(
    config_loader.read(str(_ROOT)),
    config_loader.rows(("tests", "child_timeout_seconds")),
    config_loader.CONFIG_FILE,
)[("tests", "child_timeout_seconds")]


def _git(root, env, *args):
    subprocess.run(
        ["git", *args],
        cwd=root,
        env=build_child_env(extra=env),
        check=True,
        capture_output=True,
        timeout=_TIMEOUT,
    )


@pytest.fixture
def project(tmp_path):
    env = hermetic_git.git_env_vars(tmp_path)
    root = tmp_path / "main checkout"
    root.mkdir()
    _git(root, env, "init", "-q")
    _git(root, env, "commit", "-q", "--allow-empty", "-m", "fixture")
    return root, env


def _worktree(project):
    root, env = project
    tree = root.parent / "linked tree"
    _git(root, env, "worktree", "add", "--detach", str(tree))
    return tree


def _python(root, label, status=0):
    path = root / ".venv/bin/python"
    path.parent.mkdir(parents=True)
    path.write_text(
        '#!/bin/sh\nprintf "%s\\n" "' + label + f'" "$@"\ncat\nexit {status}\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _run(root, *args, stdin=""):
    return subprocess.run(
        [sys.executable, str(_LAUNCHER), *args],
        cwd=root,
        env=build_child_env(),
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT,
    )


def test_current_tree_venv_wins_over_main_checkout(project):
    root, _ = project
    tree = _worktree(project)
    _python(root, "main")
    _python(tree, "local")
    nested = tree / "nested"
    nested.mkdir()
    result = _run(nested, "script.py")
    assert result.returncode == ExitCode.SUCCESS, result.stderr
    assert result.stdout == "local\nscript.py\n"


def test_linked_tree_uses_main_checkout_venv(project):
    root, _ = project
    tree = _worktree(project)
    _python(root, "main")
    result = _run(tree, "script.py")
    assert result.returncode == ExitCode.SUCCESS, result.stderr
    assert result.stdout == "main\nscript.py\n"


def test_missing_venvs_refuse_with_both_paths_and_remedy(project):
    root, _ = project
    tree = _worktree(project)
    result = _run(tree, "script.py")
    assert result.returncode == ExitCode.USAGE
    assert "no project venv (USAGE)" in result.stderr
    assert str(tree / ".venv/bin/python") in result.stderr
    assert str(root / ".venv/bin/python") in result.stderr
    assert "build" in result.stderr and ".venv" in result.stderr


@pytest.mark.parametrize("status", [0, 7, 130])
def test_arguments_stdin_and_script_status_pass_through(project, status):
    root, _ = project
    _python(root, "local", status)
    result = _run(
        root, "a script.py", "", "two words", "*", "--flag", stdin="payload\n"
    )
    assert result.returncode == status, result.stderr
    assert result.stdout == "local\na script.py\n\ntwo words\n*\n--flag\npayload\n"


def test_unusual_common_dir_is_not_guessed(project):
    root, env = project
    metadata = root.parent / "metadata"
    (root / ".git").rename(metadata)
    (root / ".git").write_text(f"gitdir: {metadata}\n", encoding="utf-8")
    _python(root.parent, "must not run")
    result = _run(root, "script.py")
    assert result.returncode == ExitCode.USAGE
    assert "unusual" in result.stderr and str(metadata) in result.stderr
    assert result.stdout == ""


def test_bare_repository_is_refused(project):
    root, env = project
    bare = root.parent / "bare.git"
    _git(root, env, "init", "--bare", str(bare))
    result = _run(bare, "script.py")
    assert result.returncode == ExitCode.USAGE
    assert "work tree" in result.stderr


def test_no_script_is_usage(project):
    root, _ = project
    result = _run(root)
    assert result.returncode == ExitCode.USAGE
    assert "script" in result.stderr and "usage" in result.stderr.lower()


def test_linked_tree_with_bare_common_dir_is_refused(project):
    root, env = project
    bare = root.parent / "bare" / ".git"
    bare.parent.mkdir()
    _git(root, env, "clone", "--bare", str(root), str(bare))
    tree = root.parent / "bare linked tree"
    _git(bare, env, "worktree", "add", "--detach", str(tree))
    _python(bare.parent, "must not run")
    result = _run(tree, "script.py")
    assert result.returncode == ExitCode.USAGE
    assert "bare common directory" in result.stderr
    assert str(bare) in result.stderr
    assert result.stdout == ""


def test_launcher_and_transitive_script_imports_parse_on_python36():
    assert _LAUNCHER.is_file(), "the host-Python launcher must exist"
    # child_env loads the config loader by path; its error path loads the grammar
    # by path too. Ordinary import graphs cannot discover these dynamic edges.
    entries = [
        _LAUNCHER,
        _ROOT / "scripts/config_loader.py",
        _ROOT / "scripts/jobs/conflict_guard.py",
    ]
    checked = set()
    for entry in entries:
        for _, path in job_closure(
            str(entry), str(_ROOT), search_path=[str(_ROOT / "scripts"), str(_ROOT)]
        ):
            source = Path(path)
            if source.is_relative_to(_ROOT / "scripts"):
                ast.parse(
                    source.read_text(encoding="utf-8"),
                    filename=str(source),
                    feature_version=(3, 6),
                )
                checked.add(source)
    assert {
        _LAUNCHER,
        _ROOT / "scripts/child_env.py",
        _ROOT / "scripts/exit_codes.py",
        *entries,
    } <= checked
