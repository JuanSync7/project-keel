"""
title: Confined build_corpus mutations
summary: External sentinel preservation, usable internal links and explicit output policy.
"""

import build_corpus as job
import pytest
from exit_codes import ExitCode

pytestmark = pytest.mark.unit


def test_external_output_preserved(escaped, monkeypatch):
    root, outside = escaped
    monkeypatch.setattr(job, "build_corpus", lambda root: {"nodes": []})
    sentinel = outside / "corpus.json"
    before = b"external sentinel"
    sentinel.write_bytes(before)
    rc = job.main(["--root", str(root), "--out", "linked/corpus.json"])
    assert sentinel.read_bytes() == before
    assert rc == ExitCode.USAGE


@pytest.mark.parametrize(
    "linked", [False, True], ids=["missing_target", "internal_parent_link"]
)
@pytest.mark.parametrize("relative_root", [False, True])
def test_missing_target_created(tmp_path, monkeypatch, linked, relative_root):
    root = tmp_path / "project"
    root.mkdir()
    target = root / "real"
    target.mkdir()
    if linked:
        (root / "alias").symlink_to(target, target_is_directory=True)
    parent = "alias" if linked else "real"
    monkeypatch.chdir(tmp_path)
    argument_root = "project" if relative_root else str(root)
    monkeypatch.setattr(job, "build_corpus", lambda root: {"nodes": []})
    assert (
        job.main(["--root", argument_root, "--out", parent + "/corpus.json"])
        == ExitCode.SUCCESS
    )
    assert (target / "corpus.json").is_file()


def test_explicit_outside_root(escaped, monkeypatch):
    root, outside = escaped
    monkeypatch.setattr(job, "build_corpus", lambda root: {"nodes": []})
    assert (
        job.main(["--root", str(root), "--out", str(outside / "corpus.json")])
        == ExitCode.SUCCESS
    )
