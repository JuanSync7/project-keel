"""
title: Confined restamp_docs mutations
summary: External sentinel preservation, usable internal links and explicit output policy.
"""

import datetime

import pytest
import restamp_docs as job
from exit_codes import ExitCode

pytestmark = pytest.mark.unit


def test_parent_escape(escaped, monkeypatch):
    root, outside = escaped
    sentinel = outside / "a.md"
    before = b"---\nupdated: 2020-01-01\n---\n"
    sentinel.write_bytes(before)
    monkeypatch.setattr(
        job, "worklist", lambda *args: [("linked/a.md", datetime.date(2026, 11, 7))]
    )
    rc = job.main(["--root", str(root), "--today", "2026-11-07"])
    assert sentinel.read_bytes() == before
    assert rc == ExitCode.USAGE


def test_escape_aborts_run_before_any_write(escaped, monkeypatch):
    root, outside = escaped
    before = b"---\nupdated: 2020-01-01\n---\n"
    (root / "a.md").write_bytes(before)
    (outside / "z.md").write_bytes(before)
    monkeypatch.setattr(
        job,
        "worklist",
        lambda *args: [
            (p, datetime.date(2026, 11, 7)) for p in ("a.md", "linked/z.md")
        ],
    )
    rc = job.main(["--root", str(root), "--today", "2026-11-07"])
    assert (outside / "z.md").read_bytes() == before
    assert (root / "a.md").read_bytes() == before
    assert rc == ExitCode.USAGE


def test_internal_parent_link(tmp_path, monkeypatch):
    root = tmp_path / "project"
    real = root / "real"
    real.mkdir(parents=True)
    (root / "alias").symlink_to(real, target_is_directory=True)
    doc = real / "a.md"
    doc.write_bytes(b"---\nupdated: 2020-01-01\n---\n")
    monkeypatch.setattr(
        job, "worklist", lambda *args: [("alias/a.md", datetime.date(2026, 11, 7))]
    )
    assert job.main(["--root", str(root), "--today", "2026-11-07"]) == ExitCode.SUCCESS
    assert b"updated: 2026-11-07" in doc.read_bytes()
