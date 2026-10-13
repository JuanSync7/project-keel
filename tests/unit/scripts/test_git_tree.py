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


def test_through_symlink_judges_a_path_by_where_it_resolves(tmp_path):
    root = tmp_path / "proj"
    outside = tmp_path / "outside"
    (root / "out" / "deep").mkdir(parents=True)
    outside.mkdir()
    (root / "out" / "file.json").write_text("{}", encoding="utf-8")
    plain = ["out", "out/deep", "out/file.json", "out/absent.json", "absent/a/b"]
    assert git_tree.through_symlink(str(root), plain) == []

    (root / "linked").symlink_to(outside, target_is_directory=True)
    (root / "out" / "leaf.json").symlink_to(outside / "leaf.json")
    (root / "out" / "inside.json").symlink_to("file.json")
    paths = plain + [
        "linked",
        "linked/x/matrix.json",
        "out/leaf.json",
        "out/inside.json",
    ]
    # A dangling link and a link that stays inside the project are both links:
    # the question is whether the path is the file it names, not where it lands.
    assert git_tree.through_symlink(str(root), paths) == [
        "linked",
        "linked/x/matrix.json",
        "out/leaf.json",
        "out/inside.json",
    ]

    # The project root itself may be reached through a link; only what lies
    # below it is judged.
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    assert git_tree.through_symlink(str(alias), plain) == []
    assert git_tree.through_symlink(str(alias), ["linked/x"]) == ["linked/x"]


def test_run_evals_reads_the_one_symlink_check():
    import run_evals

    assert not hasattr(run_evals, "_through_symlink")
    assert "through_symlink" in git_tree.__all__


# --- three answers: git is not installed, no repository, git failed -----------


def _empty_head(repo):
    """A repository whose HEAD names nothing git can read."""
    (repo / ".git" / "HEAD").write_text("garbage\n", encoding="utf-8")


def _missing_gitdir(repo):
    """A work tree whose `.git` file names a git directory that is not there."""
    import shutil

    shutil.rmtree(str(repo / ".git"))
    (repo / ".git").write_text("gitdir: %s\n" % (repo / "gone"), encoding="utf-8")


_BREAKS = {"head-is-garbage": _empty_head, "gitdir-is-missing": _missing_gitdir}
_ASKS = {
    "tree_snapshot": lambda root: git_tree.tree_snapshot(root),
    "is_ignored": lambda root: git_tree.is_ignored(root, "ignored.txt"),
    "head_commit": lambda root: git_tree.head_commit(root),
}


def test_a_git_that_is_not_installed_is_NoGitError(repo, tmp_path, monkeypatch):
    """git_tree hands git the allowlisted environment, PATH included, so a PATH
    that holds no git is the spawn failing: the first of the two "no git"
    answers, even inside a repository."""
    bare = tmp_path / "no-tools"
    bare.mkdir()
    monkeypatch.setenv("PATH", str(bare))
    for name in ("tree_snapshot", "is_ignored"):
        with pytest.raises(git_tree.NoGitError) as caught:
            _ASKS[name](str(repo))
        assert "not installed" in str(caught.value), name
    assert git_tree.head_commit(str(repo)) is None


@pytest.mark.parametrize("ask", sorted(_ASKS))
@pytest.mark.parametrize("broken", sorted(_BREAKS))
def test_a_git_that_ran_and_failed_is_GitFailedError_never_NoGitError(
    repo, tmp_path, monkeypatch, broken, ask
):
    """A repository git cannot read is unknown, not absent. git exits 128 for
    this and for "not a git repository" alike, so the status cannot tell them
    apart: the `.git` entry on disk does."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    _BREAKS[broken](repo)
    with pytest.raises(git_tree.GitFailedError) as caught:
        _ASKS[ask](str(repo))
    exc = caught.value
    assert isinstance(exc.returncode, int) and exc.returncode != 0, exc.returncode
    assert exc.stderr.strip(), "git's own complaint is missing"
    assert "git exited %d" % exc.returncode in str(exc) and exc.stderr in str(exc)
    assert len(exc.stderr) <= git_tree.STDERR_MAX
    assert not isinstance(exc, git_tree.NoGitError)
    assert not issubclass(git_tree.GitFailedError, git_tree.NoGitError)
    assert not issubclass(git_tree.NoGitError, git_tree.GitFailedError)


def test_a_git_that_cannot_be_started_for_another_reason_is_GitFailedError(
    repo, tmp_path, monkeypatch
):
    """A git binary the process may not execute is not "not installed"."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "git").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (tools / "git").chmod(0o644)
    monkeypatch.setenv("PATH", str(tools))
    with pytest.raises(git_tree.GitFailedError) as caught:
        git_tree.tree_snapshot(str(repo))
    assert caught.value.returncode is None
    assert "could not be started" in str(caught.value)


def test_inside_a_repository_stops_where_git_stops(repo, tmp_path, monkeypatch):
    """The walk answers "is there a repository git would look for here": it
    climbs to a `.git` entry and stops below a directory
    GIT_CEILING_DIRECTORIES names, as git's own discovery does."""
    monkeypatch.delenv("GIT_CEILING_DIRECTORIES", raising=False)
    deep = repo / "a" / "b"
    deep.mkdir(parents=True)
    assert git_tree.inside_a_repository(str(repo)) is True
    assert git_tree.inside_a_repository(str(deep)) is True
    # The ceiling is the repository's own directory: git, started in a/b, looks
    # in a/b and a and never climbs into the directory that holds .git.
    assert (
        git_tree.inside_a_repository(str(deep), {"GIT_CEILING_DIRECTORIES": str(repo)})
        is False
    )
    with_ceiling = {"GIT_CEILING_DIRECTORIES": "%s:%s" % (tmp_path / "x", repo)}
    assert git_tree.inside_a_repository(str(deep), with_ceiling) is False
    # A ceiling is never the start directory itself, and one above the
    # repository hides nothing.
    assert (
        git_tree.inside_a_repository(str(repo), {"GIT_CEILING_DIRECTORIES": str(repo)})
        is True
    )
    assert (
        git_tree.inside_a_repository(
            str(deep), {"GIT_CEILING_DIRECTORIES": str(tmp_path)}
        )
        is True
    )
    # The default environment is the one git is given: the allowlisted one.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(repo))
    assert git_tree.inside_a_repository(str(deep)) is False
    lone = tmp_path / "lone"
    lone.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert git_tree.inside_a_repository(str(lone)) is False


def test_inside_a_repository_does_not_cross_a_filesystem(repo, monkeypatch):
    """git does not look for a repository on another filesystem than the one it
    started on, so a `.git` above a mount point is not this directory's."""
    monkeypatch.delenv("GIT_CEILING_DIRECTORIES", raising=False)
    deep = repo / "a"
    deep.mkdir()
    real_stat = git_tree.os.stat
    start = real_stat(str(deep)).st_dev

    class Other:
        st_dev = start + 1

    def stat(path, *args, **kwargs):
        if str(path) == str(repo):
            return Other()
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(git_tree.os, "stat", stat)
    assert git_tree.inside_a_repository(str(deep), {}) is False
    # Told to cross filesystems, git would find it, so the walk must too.
    crossing = {"GIT_DISCOVERY_ACROSS_FILESYSTEM": "1"}
    assert git_tree.inside_a_repository(str(deep), crossing) is True


def test_the_gate_runner_re_exports_both_git_errors():
    assert rmt.GitFailedError is git_tree.GitFailedError
    for name in ("GitFailedError", "NoGitError", "inside_a_repository"):
        assert name in git_tree.__all__, name
