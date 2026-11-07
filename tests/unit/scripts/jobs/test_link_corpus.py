"""
title: Confined link_corpus mutations
summary: External sentinel preservation, usable internal links and explicit output policy.
"""

import link_corpus as job
import pytest
from exit_codes import ExitCode

pytestmark = pytest.mark.unit


def test_external_output_preserved(escaped, monkeypatch):
    root, outside = escaped
    monkeypatch.setattr(job, "ROOT", str(root))
    sentinel = outside / "corpus.json"
    before = b'{"nodes": []}'
    sentinel.write_bytes(before)
    rc = job.main(["--corpus", "linked/corpus.json"])
    assert sentinel.read_bytes() == before
    assert rc == ExitCode.USAGE


@pytest.mark.parametrize(
    "linked", [False, True], ids=["missing_target", "internal_parent_link"]
)
def test_missing_target_created(tmp_path, monkeypatch, linked):
    root = tmp_path / "project"
    root.mkdir()
    target = root / "real"
    target.mkdir()
    if linked:
        (root / "alias").symlink_to(target, target_is_directory=True)
    parent = "alias" if linked else "real"
    monkeypatch.setattr(job, "ROOT", str(root))
    (target / "corpus.json").write_text('{"nodes": []}', encoding="utf-8")
    assert job.main(["--corpus", parent + "/corpus.json"]) == ExitCode.SUCCESS
    assert (target / "corpus.json").is_file()


def test_explicit_outside_root(escaped, monkeypatch):
    root, outside = escaped
    (outside / "corpus.json").write_text('{"nodes": []}', encoding="utf-8")
    monkeypatch.setattr(job, "ROOT", str(root))
    assert job.main(["--corpus", str(outside / "corpus.json")]) == ExitCode.SUCCESS
