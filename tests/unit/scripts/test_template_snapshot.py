"""
title: Unit — template_snapshot (the working tree, committed in a scratch clone)
kind: tests
layer: n/a
summary: scripts/template_snapshot.py pinned against a small git repository in pytest's tmp_path. `snapshot_working_tree` clones it and commits its uncommitted edits and untracked files on top, so the snapshot's HEAD holds what the working tree holds; it never copies a path its caller names in `skip` (the canary's scratch root, which a snapshot that copied it would recurse into) nor an untracked symlink, which it names in the not-checked list it returns; the template's own index and status are left as they were; and two snapshots of one tree under the hermetic environment `scratch_env` writes commit the same sha, which is the module's fixed point. `scratch_env` pins commit dates and SOURCE_DATE_EPOCH to the given day at midnight UTC and keeps copier's settings, cache and temporary files inside the scratch directory. A child that fails raises SnapshotError naming the step; nothing here ends the process. Excluded from generated projects with the module.
"""

import datetime
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import template_snapshot as ts  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit

_DAY = datetime.date(2026, 10, 17)


def _git(cwd, *args):
    # The hermetic config goes beside the repository, never into it, where it
    # would be one more untracked file of the tree under test.
    work = Path(cwd).parent / ".gitenv"
    work.mkdir(exist_ok=True)
    done = subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        env=hermetic_git.git_env(work),
    )
    assert done.returncode == 0, done.stdout
    return done.stdout


@pytest.fixture
def template(tmp_path, monkeypatch):
    """A committed repository with one edit, one untracked file, an untracked
    file under the scratch root and an untracked symlink in its working tree."""
    for name, value in hermetic_git.git_env_vars(tmp_path).items():
        monkeypatch.setenv(name, value)
    repo = tmp_path / "template"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "kept.md").write_text("committed\n", encoding="utf-8")
    (repo / "edited.txt").write_text("before\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "edited.txt").write_text("after\n", encoding="utf-8")
    (repo / "new.txt").write_text("untracked\n", encoding="utf-8")
    (repo / ".canary").mkdir()
    (repo / ".canary" / "x").write_text("a run's own output\n", encoding="utf-8")
    os.symlink(str(tmp_path), str(repo / "sibling"))
    return repo


def test_snapshot_skips_the_scratch_root_and_untracked_symlinks(template, tmp_path):
    status_before = _git(template, "status", "--porcelain=v1", "-uall")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    extra = ts.scratch_env(str(scratch), _DAY)
    snap, not_checked = ts.snapshot_working_tree(
        str(template), str(scratch), extra, skip=(".canary",)
    )
    snap = Path(snap)
    assert snap.parent == scratch
    listed = _git(snap, "ls-files").split()
    assert sorted(listed) == ["docs/kept.md", "edited.txt", "new.txt"], listed
    assert (snap / "edited.txt").read_text(encoding="utf-8") == "after\n"
    assert not (snap / ".canary").exists()
    assert not os.path.lexists(str(snap / "sibling"))
    assert [entry["item"] for entry in not_checked] == ["sibling"], not_checked
    assert "symlink" in not_checked[0]["reason"]
    assert _git(snap, "status", "--porcelain=v1", "-uall") == ""
    # The template is only read: its index and status are what they were.
    assert _git(template, "status", "--porcelain=v1", "-uall") == status_before


def test_without_a_skip_the_scratch_root_is_copied_so_the_skip_is_what_keeps_it_out(
    template, tmp_path
):
    """The control for the test above: the same tree with no skip copies the
    file, so its absence there is the skip's doing, not git's."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    snap, _ = ts.snapshot_working_tree(
        str(template), str(scratch), ts.scratch_env(str(scratch), _DAY)
    )
    assert (Path(snap) / ".canary" / "x").is_file()


def test_two_snapshots_of_one_tree_commit_the_same_sha(template, tmp_path):
    heads = []
    for name in ("one", "two"):
        scratch = tmp_path / name
        scratch.mkdir()
        snap, _ = ts.snapshot_working_tree(
            str(template),
            str(scratch),
            ts.scratch_env(str(scratch), _DAY),
            skip=(".canary",),
        )
        heads.append(_git(snap, "rev-parse", "HEAD").strip())
    assert heads[0] == heads[1], heads


def test_a_clean_tree_is_its_head_with_no_commit_on_top(tmp_path, monkeypatch):
    for name, value in hermetic_git.git_env_vars(tmp_path).items():
        monkeypatch.setenv(name, value)
    repo = tmp_path / "clean"
    repo.mkdir()
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    snap, not_checked = ts.snapshot_working_tree(
        str(repo), str(scratch), ts.scratch_env(str(scratch), _DAY)
    )
    assert not_checked == []
    assert _git(snap, "rev-parse", "HEAD") == _git(repo, "rev-parse", "HEAD")


def test_scratch_env_pins_the_day_and_keeps_tool_state_in_the_scratch(tmp_path):
    extra = ts.scratch_env(str(tmp_path), _DAY)
    epoch = int(
        datetime.datetime(2026, 10, 17, tzinfo=datetime.timezone.utc).timestamp()
    )
    assert extra["SOURCE_DATE_EPOCH"] == str(epoch)
    assert (
        extra["GIT_AUTHOR_DATE"] == extra["GIT_COMMITTER_DATE"] == "@%d +0000" % epoch
    )
    for name in (
        "GIT_CONFIG_GLOBAL",
        "COPIER_SETTINGS_PATH",
        "XDG_CACHE_HOME",
        "TMPDIR",
    ):
        assert extra[name].startswith(str(tmp_path) + os.sep), (name, extra[name])
    assert Path(extra["TMPDIR"]).is_dir()
    config = Path(extra["GIT_CONFIG_GLOBAL"]).read_text(encoding="utf-8")
    assert "hooksPath = %s" % os.devnull in config


def test_a_failed_clone_raises_naming_the_step(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(ts.SnapshotError) as caught:
        ts.snapshot_working_tree(
            str(tmp_path / "absent"), str(scratch), ts.scratch_env(str(scratch), _DAY)
        )
    assert "git clone" in str(caught.value)
