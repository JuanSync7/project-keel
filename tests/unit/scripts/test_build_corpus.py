"""
title: Confined build_corpus mutations
summary: External sentinel preservation, usable internal links and explicit output policy.
"""

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import build_corpus as job  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

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


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("interrupt", [False, True])
def test_readers_see_only_complete_replacements(
    tmp_path, monkeypatch, existing, interrupt
):
    path = tmp_path / "wiki" / "corpus.json"
    path.parent.mkdir()
    before = b'{"nodes": [], "generation": "old"}\n'
    if existing:
        path.write_bytes(before)
    corpus = {"nodes": [], "generation": "new"}
    monkeypatch.setattr(job, "build_corpus", lambda root: corpus)
    replace = os.replace
    seen = []

    def publish(source, destination):
        source, destination = Path(source), Path(destination)
        assert destination == path
        assert source.parent == destination.parent and source != destination
        assert json.loads(source.read_text("utf-8")) == corpus
        assert path.read_bytes() == before if existing else not path.exists()
        seen.append(source)
        if interrupt:
            raise InterruptedError("interrupted before publication")
        replace(source, destination)

    monkeypatch.setattr(os, "replace", publish)
    args = ["--root", str(tmp_path)]
    if interrupt:
        with pytest.raises(InterruptedError, match="before publication"):
            job.main(args)
        assert path.read_bytes() == before if existing else not path.exists()
    else:
        assert job.main(args) == ExitCode.SUCCESS
        assert json.loads(path.read_text("utf-8")) == corpus
    assert len(seen) == 1
    assert list(path.parent.iterdir()) == ([path] if path.exists() else [])
