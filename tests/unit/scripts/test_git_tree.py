"""
title: Unit — git_tree (what git lists, shared by the gate runner and the evidence writer)
kind: tests
layer: n/a
summary: tree_snapshot lists every path git status reports under a work tree (modified and untracked) and never an ignored one, each joined to its content digest; snapshot_digest is a stable sha256 over that snapshot and changes when one byte of a listed file changes; outside a work tree tree_snapshot raises NoGitError, and scripts/run_make_target.py re-exports the same class rather than defining a second one. Runs real git in a tmp_path repository under the hermetic git environment.
"""

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import git_tree  # noqa: E402
import run_make_target as rmt  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit


def _git(repo, env, *argv):
    subprocess.run(
        ["git", *argv], cwd=str(repo), env=env, check=True, capture_output=True
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A committed repository with one tracked file and an ignore rule; the
    hermetic git environment is exported, because git_tree's own git calls take
    their environment from child_env, which copies GIT_CONFIG_* from here."""
    work = tmp_path / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "tracked.txt").write_text("one\n", encoding="utf-8")
    (proj / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    _git(proj, env, "init", "-q")
    _git(proj, env, "add", "-A")
    _git(proj, env, "commit", "-q", "-m", "init")
    return proj


def test_snapshot_lists_untracked_and_modified_never_ignored(repo):
    (repo / "tracked.txt").write_text("two\n", encoding="utf-8")
    (repo / "new.txt").write_text("fresh\n", encoding="utf-8")
    (repo / "ignored.txt").write_text("hidden\n", encoding="utf-8")
    snap = git_tree.tree_snapshot(str(repo))
    assert sorted(snap) == ["new.txt", "tracked.txt"], snap
    assert snap["tracked.txt"].startswith(" M|sha:"), snap
    assert snap["new.txt"].startswith("??|sha:"), snap

    first = git_tree.snapshot_digest(snap)
    assert first == git_tree.snapshot_digest(git_tree.tree_snapshot(str(repo)))
    assert first.startswith("sha256:") and len(first) == len("sha256:") + 64
    (repo / "new.txt").write_text("freSh\n", encoding="utf-8")
    assert git_tree.snapshot_digest(git_tree.tree_snapshot(str(repo))) != first


def test_a_clean_tree_snapshots_empty_with_a_fixed_digest(repo):
    """A clean tree lists nothing; its digest is still a value, never absent."""
    assert git_tree.tree_snapshot(str(repo)) == {}
    assert git_tree.snapshot_digest({}) == git_tree.snapshot_digest({})


def test_no_git_raises_NoGitError(tmp_path, monkeypatch):
    # GIT_CEILING_DIRECTORIES keeps git from finding a repository above tmp_path.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(git_tree.NoGitError):
        git_tree.tree_snapshot(str(lone))
    assert rmt.NoGitError is git_tree.NoGitError
    assert rmt.tree_snapshot is git_tree.tree_snapshot


def test_git_runs_with_the_allowlisted_environment(repo, monkeypatch):
    """Every git call goes through child_env.build_child_env, looked up on the
    module at call time, so the gate runner's existing patches still reach it."""
    seen = []
    real = git_tree.child_env.build_child_env

    def spy(**kw):
        seen.append(kw)
        return real(**kw)

    monkeypatch.setattr(git_tree.child_env, "build_child_env", spy)
    git_tree.tree_snapshot(str(repo))
    assert seen, "tree_snapshot ran git without build_child_env"


def test_is_ignored_tells_an_ignored_path_from_a_listed_one(repo):
    """check-ignore's exit 1 is an answer (not ignored), never an error; a path
    that does not exist yet is judged by the rules alone."""
    assert git_tree.is_ignored(str(repo), "ignored.txt") is True
    assert git_tree.is_ignored(str(repo), "not-yet-there.txt") is False
    # A tracked file is never ignored, whatever a pattern says.
    (repo / ".gitignore").write_text("ignored.txt\ntracked.txt\n", encoding="utf-8")
    assert git_tree.is_ignored(str(repo), "tracked.txt") is False


def test_is_ignored_outside_a_work_tree_raises_NoGitError(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(git_tree.NoGitError):
        git_tree.is_ignored(str(lone), "x.json")


def test_head_commit_is_the_sha_or_none(repo, tmp_path):
    sha = git_tree.head_commit(str(repo))
    assert sha is not None and len(sha) == 40, sha
    assert all(c in "0123456789abcdef" for c in sha), sha
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, hermetic_git.git_env(tmp_path / "work"), "init", "-q")
    assert git_tree.head_commit(str(empty)) is None
