"""
title: Confined build_llms_txt mutations
summary: External sentinel preservation, usable internal links and explicit output policy.
"""

import build_llms_txt as job
import pytest
from exit_codes import ExitCode

pytestmark = pytest.mark.unit


def test_external_output_preserved(escaped, monkeypatch):
    root, outside = escaped
    (root / "config").mkdir()
    (root / "config" / "project.json").write_text("{}", encoding="utf-8")
    sentinel = outside / "llms.txt"
    before = b"external sentinel"
    sentinel.write_bytes(before)
    rc = job.main(["--root", str(root), "--out-dir", "linked"])
    assert sentinel.read_bytes() == before
    assert rc == ExitCode.USAGE


@pytest.mark.parametrize(
    "linked", [False, True], ids=["missing_target", "internal_parent_link"]
)
@pytest.mark.parametrize("relative_root", [False, True])
def test_missing_target_created(tmp_path, monkeypatch, linked, relative_root):
    root = tmp_path / "project"
    root.mkdir()
    (root / "config").mkdir()
    (root / "config" / "project.json").write_text("{}", encoding="utf-8")
    target = root / "real"
    target.mkdir()
    if linked:
        (root / "alias").symlink_to(target, target_is_directory=True)
    parent = "alias" if linked else "real"
    monkeypatch.chdir(tmp_path)
    argument_root = "project" if relative_root else str(root)
    assert job.main(["--root", argument_root, "--out-dir", parent]) == ExitCode.SUCCESS
    assert (target / "llms.txt").is_file()


def test_explicit_outside_root(escaped, monkeypatch):
    root, outside = escaped
    (root / "config").mkdir()
    (root / "config" / "project.json").write_text("{}", encoding="utf-8")
    assert (
        job.main(["--root", str(root), "--out-dir", str(outside)]) == ExitCode.SUCCESS
    )
    assert (outside / "llms-full.txt").is_file()
