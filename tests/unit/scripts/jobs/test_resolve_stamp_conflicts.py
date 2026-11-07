"""
title: Confined resolve_stamp_conflicts mutations
summary: External sentinel preservation, usable internal links and explicit output policy.
"""

import pytest
import resolve_stamp_conflicts as job
from exit_codes import ExitCode

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "first", [False, True], ids=["parent_escape", "abort_before_write"]
)
def test_parent_escape(escaped, monkeypatch, first):
    root, outside = escaped
    before = (
        "---\n"
        + "<" * 7
        + " ours\nupdated: 2020-01-01\n"
        + "=" * 7
        + "\nupdated: 2021-01-01\n"
        + ">" * 7
        + " theirs\n---\n"
    ).encode()
    sentinel = outside / "z.md"
    sentinel.write_bytes(before)
    paths = ["linked/z.md"]
    if first:
        (root / "a.md").write_bytes(before)
        paths.insert(0, "a.md")
    monkeypatch.setattr(
        job,
        "unmerged",
        lambda root: {
            p: {"2": ("100644", "a" * 40), "3": ("100644", "b" * 40)} for p in paths
        },
    )
    monkeypatch.setattr(job, "_git", lambda *args: b"")
    rc = job.main(["--root", str(root)])
    assert sentinel.read_bytes() == before
    if first:
        assert (root / "a.md").read_bytes() == before
    assert rc == ExitCode.USAGE


def test_internal_parent_link(tmp_path, monkeypatch):
    root = tmp_path / "project"
    real = root / "real"
    real.mkdir(parents=True)
    (root / "alias").symlink_to(real, target_is_directory=True)
    before = (
        "---\n"
        + "<" * 7
        + " ours\nupdated: 2020-01-01\n"
        + "=" * 7
        + "\nupdated: 2021-01-01\n"
        + ">" * 7
        + " theirs\n---\n"
    ).encode()
    doc = real / "a.md"
    doc.write_bytes(before)
    monkeypatch.setattr(
        job,
        "unmerged",
        lambda root: {
            "alias/a.md": {"2": ("100644", "a" * 40), "3": ("100644", "b" * 40)}
        },
    )
    monkeypatch.setattr(job, "_git", lambda *args: b"")
    assert job.main(["--root", str(root)]) == ExitCode.SUCCESS
    assert doc.read_bytes() == b"---\nupdated: 2021-01-01\n---\n"
