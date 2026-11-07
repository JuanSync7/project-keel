"""
title: Confined rebuild_index mutations
summary: External sentinel preservation, usable internal links and explicit output policy.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import rebuild_index as job  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit


def test_external_output_preserved(escaped, monkeypatch):
    root, outside = escaped
    monkeypatch.chdir(root)
    sentinel = outside / "INDEX.md"
    before = b"external sentinel"
    sentinel.write_bytes(before)
    rc = job.main(["--root", str(root), "--out", "linked/INDEX.md"])
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
    assert (
        job.main(["--root", str(root), "--out", parent + "/INDEX.md"])
        == ExitCode.SUCCESS
    )
    assert (target / "INDEX.md").is_file()


def test_explicit_outside_root(escaped, monkeypatch):
    root, outside = escaped
    monkeypatch.chdir(root)
    assert (
        job.main(["--root", str(root), "--out", str(outside / "INDEX.md")])
        == ExitCode.SUCCESS
    )
