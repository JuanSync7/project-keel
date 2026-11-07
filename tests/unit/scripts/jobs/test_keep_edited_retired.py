"""
title: Confined keep_edited_retired mutations
summary: External sentinel preservation, usable internal links and explicit output policy.
"""

import contextlib

import keep_edited_retired as job
import pytest

pytestmark = pytest.mark.unit


def test_parent_escape(escaped, monkeypatch):
    root, outside = escaped
    sentinel = outside / "adapter.yml"
    before = b"unedited adapter\n"
    sentinel.write_bytes(before)
    monkeypatch.setattr(job, "deleted_paths", lambda root: [])
    monkeypatch.setattr(job, "_resolve", lambda *args: "base")
    monkeypatch.setattr(job, "_tree", lambda *args, **kwargs: {})
    monkeypatch.setattr(job, "_successors", lambda *args: {})
    monkeypatch.setattr(job, "_keel_render", lambda *args: (before, None))
    with contextlib.suppress(job.GuardError, ValueError):
        job.judge(str(root), str(root), "base", retire={"linked/adapter.yml": "ci"})
    assert sentinel.read_bytes() == before


def test_restoration_parent_escape(escaped):
    root, outside = escaped
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"unchanged")
    with contextlib.suppress(job.GuardError, ValueError):
        job._restore(str(root), "linked/restored.md", "100644", b"restored")
    assert sentinel.read_bytes() == b"unchanged"
    assert not (outside / "restored.md").exists()


@pytest.mark.parametrize("linked", [False, True])
def test_missing_target_created(tmp_path, linked):
    root = tmp_path / "project"
    target = root / "real"
    target.mkdir(parents=True)
    if linked:
        (root / "alias").symlink_to(target, target_is_directory=True)
    parent = "alias" if linked else "real"
    job._restore(str(root), parent + "/restored.md", "100755", b"restored")
    assert (target / "restored.md").read_bytes() == b"restored"
    assert (target / "restored.md").stat().st_mode & 0o111
