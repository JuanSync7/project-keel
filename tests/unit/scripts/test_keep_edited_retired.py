"""
title: Unit — keep_edited_retired (the rule that says a retired file was edited)
kind: tests
layer: n/a
summary: The pure half of scripts/jobs/keep_edited_retired.py, pinned: `is_edited` calls a project's copy unedited only when it differs from the template's blob in nothing but the frontmatter `updated:` value, read through review_docs' `updated_span` (the stamp the restamp writer moves on every update). Any other byte is an edit -- an `owner:` change, a body line that happens to read `updated:`, a CRLF conversion, a stamp added or removed -- and so is a file that is not UTF-8 and differs at all. scripts/audit_project.py's `retired` group imports this same function, so the guard and the audit cannot disagree.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
sys.path.insert(0, str(_ROOT / "scripts"))

import keep_edited_retired as ker  # noqa: E402

pytestmark = pytest.mark.unit

_DOC = "---\ntitle: t\nowner: TBD\nupdated: 2026-08-05\n---\n\n# t\n\nbody\n"


def _b(text):
    return text.encode("utf-8")


@pytest.mark.parametrize(
    "head, edited",
    [
        (_DOC, False),
        (_DOC.replace("2026-08-05", "2026-10-07"), False),
        (_DOC.replace("updated: 2026-08-05", "updated:   2026-10-07"), True),
        (_DOC.replace("owner: TBD", "owner: jarvis"), True),
        (_DOC.replace("body\n", "body\nupdated: 2026-08-05\n"), True),
        (_DOC.replace("\n", "\r\n"), True),
        (_DOC.replace("updated: 2026-08-05\n", ""), True),
        (_DOC + "\n", True),
    ],
    ids=[
        "identical",
        "stamp-only",
        "stamp-spacing",
        "owner-edit",
        "body-updated-line",
        "crlf",
        "stamp-removed",
        "trailing-newline",
    ],
)
def test_is_edited_ignores_only_the_frontmatter_stamp(head, edited):
    assert ker.is_edited(_b(head), _b(_DOC)) is edited


def test_is_edited_on_bytes_that_are_not_utf8():
    """A binary or non-UTF-8 file has no stamp to discount: equal bytes are
    unedited, any difference is an edit."""
    blob = b"\xff\xfe\x00binary"
    assert ker.is_edited(blob, blob) is False
    assert ker.is_edited(blob + b"x", blob) is True


def test_a_body_without_frontmatter_is_compared_whole():
    assert ker.is_edited(b"plain\n", b"plain\n") is False
    assert ker.is_edited(b"updated: 1\n", b"updated: 2\n") is True
