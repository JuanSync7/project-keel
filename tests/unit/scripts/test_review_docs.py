"""
title: Unit — review_docs (the freshness rule)
kind: tests
layer: n/a
summary: The pure half of scripts/review_docs.py, pinned: `updated:` must be an ISO date, never earlier than the file's last commit, and a file modified in the working tree must carry today's date or later. Measured before the rule landed: 135 of 153 governed documents were stamped earlier than their last commit — including AGENT.md and CONVENTIONS.md — and nothing said so.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import review_docs  # noqa: E402

pytestmark = pytest.mark.unit

TODAY = "2026-09-02"


def _find(*records):
    return review_docs.stale_findings(list(records), TODAY)


def test_a_document_stamped_on_or_after_its_last_commit_passes():
    assert _find(("a.md", "2026-08-18", "2026-08-18", False)) == []
    assert _find(("a.md", "2026-09-01", "2026-08-18", False)) == []


def test_a_document_committed_after_its_stamp_is_stale_naming_both_dates():
    """The measured shape: a commit changed the file, the stamp stayed behind."""
    out = _find(("CONVENTIONS.md", "2026-06-24", "2026-08-18", False))
    assert len(out) == 1
    assert out[0]["path"] == "CONVENTIONS.md" and out[0]["expected"] == "2026-08-18"
    assert "2026-06-24" in out[0]["reason"] and "2026-08-18" in out[0]["reason"]


def test_a_modified_document_must_carry_today():
    out = _find(("a.md", "2026-08-18", "2026-08-18", True))
    assert (
        len(out) == 1
        and out[0]["expected"] == TODAY
        and "today" not in out[0]["expected"]
    )
    assert _find(("a.md", TODAY, "2026-08-18", True)) == []


def test_a_never_committed_document_is_held_only_to_today_when_modified():
    assert _find(("new.md", "2026-01-01", None, False)) == []
    assert len(_find(("new.md", "2026-01-01", None, True))) == 1


def test_a_stamp_that_is_not_a_date_is_a_finding():
    out = _find(("a.md", "yesterday", "2026-08-18", False))
    assert len(out) == 1 and "not a date" in out[0]["reason"]


def test_a_committed_stale_stamp_is_reported_once_even_when_also_modified():
    out = _find(("a.md", "2026-06-24", "2026-08-18", True))
    assert len(out) == 1 and out[0]["expected"] == "2026-08-18"


def test_no_records_no_findings():
    assert review_docs.stale_findings([], TODAY) == []
