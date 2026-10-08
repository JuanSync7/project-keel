"""
title: Unit — resolve_stamp_conflicts (the rule that settles a stamp-only conflict)
kind: tests
layer: n/a
summary: The pure half of scripts/jobs/resolve_stamp_conflicts.py, pinned: `resolve_stamp_conflict` resolves a file copier left conflicted only when its markers make exactly one hunk, each side of it is one line, that line is the frontmatter `updated:` value on both sides (read through review_docs' `updated_span`), the two sides differ in nothing else, and both values are real calendar dates. It then returns the project's text with the later date, the base section ignored and the line endings kept. Every other shape -- a content hunk beside the stamp, a two-line side, a body line that reads `updated:`, CRLF on one side only, unbalanced markers, bytes that are not UTF-8, a date the regex admits but the calendar refuses -- is refused with a reason from the module's closed vocabulary, never half-resolved.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
sys.path.insert(0, str(_ROOT / "scripts"))

import resolve_stamp_conflicts as rsc  # noqa: E402

pytestmark = pytest.mark.unit

# copier 9.x passes these labels to `git merge-file -L`; the job must not rely
# on them, which test_marker_labels_are_not_hardcoded holds it to.
# Spelled as repetitions so this file holds no marker text, which a tree scan
# for leftover conflicts (test_copier_update.py's) would read as one.
_LT, _BAR, _EQ, _GT = ("<" * 7, "|" * 7, "=" * 7, ">" * 7)
_OURS = _LT + " before updating\n"
_BASE = _BAR + " last update\n"
_SPLIT = _EQ + "\n"
_THEIRS = _GT + " after updating\n"

_HEAD = "---\ntitle: t\nowner: TBD\n"
_TAIL = "---\n\n# t\n\nbody line\n\nmore body\n"


def _doc(date):
    return _HEAD + "updated: %s\n" % date + _TAIL


def _hunk(ours, theirs, base=None):
    """One conflict hunk, each side a list of lines (with their newlines)."""
    out = _OURS + "".join(ours)
    if base is not None:
        out += _BASE + "".join(base)
    return out + _SPLIT + "".join(theirs) + _THEIRS


def _stamp_conflict(ours, theirs, base=None):
    return (
        _HEAD
        + _hunk(
            ["updated: %s\n" % ours],
            ["updated: %s\n" % theirs],
            None if base is None else ["updated: %s\n" % base],
        )
        + _TAIL
    )


def _b(text):
    return text.encode("utf-8")


def _run(text):
    data = text if isinstance(text, bytes) else _b(text)
    return rsc.resolve_stamp_conflict(data)


@pytest.mark.parametrize(
    "ours, theirs",
    [("2026-03-03", "2026-02-02"), ("2026-02-02", "2026-03-03")],
    ids=["ours_later", "theirs_later"],
)
def test_a_lone_stamp_hunk_resolves_to_the_later_date(ours, theirs):
    out, reason = _run(_stamp_conflict(ours, theirs))
    assert reason == rsc.RESOLVED
    assert out == _b(_doc("2026-03-03"))


def test_equal_dates_resolve_to_that_date():
    """The identical-sides shape a restamp inside a conflicted document left in
    the 7f0a68b rehearsal: no reader can pick a side, but both say the same."""
    out, reason = _run(_stamp_conflict("2026-10-08", "2026-10-08"))
    assert reason == rsc.RESOLVED
    assert out == _b(_doc("2026-10-08"))


@pytest.mark.parametrize(
    "base",
    [
        ["updated: 2026-01-01\n"],
        # zdiff3 moves common lines out of the hunk but keeps the whole base.
        ["owner: TBD\n", "updated: 2026-01-01\n", "---\n"],
        [],
    ],
    ids=["diff3", "zdiff3", "empty_base"],
)
def test_the_diff3_base_section_is_ignored(base):
    plain, _ = _run(_stamp_conflict("2026-02-02", "2026-03-03"))
    text = (
        _HEAD
        + _hunk(["updated: 2026-02-02\n"], ["updated: 2026-03-03\n"], base)
        + _TAIL
    )
    out, reason = _run(text)
    assert reason == rsc.RESOLVED
    assert out == plain


def test_crlf_on_both_sides_keeps_crlf():
    text = _stamp_conflict("2026-02-02", "2026-03-03").replace("\n", "\r\n")
    out, reason = _run(text)
    assert reason == rsc.RESOLVED
    assert out == _b(_doc("2026-03-03").replace("\n", "\r\n"))
    lines = out.split(b"\n")
    assert all(line.endswith(b"\r") for line in lines[:-1]), lines
    assert lines[-1] == b""


@pytest.mark.parametrize(
    "labels",
    [
        (_LT + " ours\n", _BAR + " base\n", _GT + " theirs\n"),
        (_LT + "\n", _BAR + "\n", _GT + "\n"),
    ],
    ids=["other_labels", "no_labels"],
)
def test_marker_labels_are_not_hardcoded(labels):
    """The markers are read as `git merge-file` writes them with any label (or
    none): copier's 'before updating' / 'after updating' are its choice."""
    open_, base, close = labels
    text = (
        _HEAD
        + open_
        + "updated: 2026-02-02\n"
        + base
        + "updated: 2026-01-01\n"
        + _SPLIT
        + "updated: 2026-03-03\n"
        + close
        + _TAIL
    )
    out, reason = _run(text)
    assert reason == rsc.RESOLVED
    assert out == _b(_doc("2026-03-03"))


def test_a_setext_underline_outside_the_hunk_is_content():
    """A Markdown heading underlined with exactly seven `=` is a line of the
    document, not a marker, when no hunk is open."""
    tail = "---\n\nTitle\n" + _EQ + "\n\nbody\n"
    text = _HEAD + _hunk(["updated: 2026-02-02\n"], ["updated: 2026-03-03\n"]) + tail
    out, reason = _run(text)
    assert reason == rsc.RESOLVED
    assert out == _b(_HEAD + "updated: 2026-03-03\n" + tail)


_STAMP = _hunk(["updated: 2026-02-02\n"], ["updated: 2026-03-03\n"])
_CONTENT = _hunk(["body line ours\n"], ["body line theirs\n"])

_NOT_STAMP_ONLY = [
    (
        "stamp_plus_content_hunk",
        _HEAD + _STAMP + "---\n\n# t\n\n" + _CONTENT + "\nmore body\n",
        rsc.MORE_THAN_ONE_HUNK,
    ),
    (
        "two_hunks",
        _doc("2026-01-01")
        .replace("body line\n", _CONTENT)
        .replace("more body\n", _hunk(["more ours\n"], ["more theirs\n"])),
        rsc.MORE_THAN_ONE_HUNK,
    ),
    (
        "stamp_and_adjacent_line",
        "---\ntitle: t\n"
        + _hunk(
            ["owner: us\n", "updated: 2026-02-02\n"],
            ["owner: TBD\n", "updated: 2026-03-03\n"],
        )
        + _TAIL,
        rsc.SIDE_NOT_ONE_LINE,
    ),
    (
        "empty_side",
        _HEAD + _hunk([], ["updated: 2026-03-03\n"]) + _TAIL,
        rsc.SIDE_NOT_ONE_LINE,
    ),
    (
        "multi_line_side",
        _HEAD
        + _hunk(
            ["updated: 2026-02-02\n"],
            ["updated: 2026-03-03\n", "status: draft\n", "tags: [x]\n"],
        )
        + _TAIL,
        rsc.SIDE_NOT_ONE_LINE,
    ),
    (
        "body_updated_line",
        _HEAD
        + "updated: 2026-01-01\n---\n\n# t\n\n"
        + _hunk(["updated: 2026-02-02\n"], ["updated: 2026-03-03\n"])
        + "\nmore body\n",
        rsc.NOT_THE_STAMP_LINE,
    ),
    (
        "one_line_content_hunk",
        _doc("2026-01-01").replace("body line\n", _CONTENT),
        rsc.NOT_THE_STAMP_LINE,
    ),
    (
        "stamp_spacing",
        _HEAD + _hunk(["updated:   2026-02-02\n"], ["updated: 2026-03-03\n"]) + _TAIL,
        rsc.DIFFERS_OUTSIDE_STAMP,
    ),
    (
        "crlf_one_side",
        _HEAD + _hunk(["updated: 2026-02-02\r\n"], ["updated: 2026-03-03\n"]) + _TAIL,
        rsc.LINE_ENDINGS_DIFFER,
    ),
    (
        "unbalanced_markers",
        _HEAD
        + _OURS
        + "updated: 2026-02-02\n"
        + _SPLIT
        + "updated: 2026-03-03\n"
        + _TAIL,
        rsc.UNBALANCED,
    ),
    (
        "stray_close_marker",
        _doc("2026-01-01") + _THEIRS,
        rsc.UNBALANCED,
    ),
    (
        "non_utf8",
        _b(_stamp_conflict("2026-02-02", "2026-03-03")).replace(
            b"body line", b"body \xff line"
        ),
        rsc.NOT_UTF8,
    ),
    ("no_markers", _doc("2026-01-01"), rsc.NO_HUNK),
    (
        "no_frontmatter",
        _hunk(["updated: 2026-02-02\n"], ["updated: 2026-03-03\n"]) + "body\n",
        rsc.NO_FIELD,
    ),
    (
        "bare_updated_key",
        _HEAD + _hunk(["updated:\n"], ["updated: 2026-03-03\n"]) + _TAIL,
        rsc.NO_FIELD,
    ),
]


@pytest.mark.parametrize(
    "text, reason",
    [(t, r) for _, t, r in _NOT_STAMP_ONLY],
    ids=[i for i, _, _ in _NOT_STAMP_ONLY],
)
def test_a_conflict_that_is_not_stamp_only_is_left(text, reason):
    out, got = _run(text)
    assert out is None
    assert got == reason
    assert got in rsc.REFUSALS


@pytest.mark.parametrize("side", ["ours", "theirs"])
@pytest.mark.parametrize(
    "bad",
    ["2026-13-40", "TBD", "2026-02-30", '""'],
    ids=["2026-13-40", "TBD", "2026-02-30", "empty"],
)
def test_a_malformed_date_is_left_and_named(bad, side):
    """Never the parsable side: a stamp that is not a date is the operator's.
    2026-02-30 passes ISO_DATE and fails the calendar, so the check is not the
    regex alone."""
    good = "2026-03-03"
    ours, theirs = (bad, good) if side == "ours" else (good, bad)
    out, reason = _run(_stamp_conflict(ours, theirs))
    assert out is None
    assert reason == rsc.UNPARSABLE_DATE


def test_the_field_is_read_through_review_docs(monkeypatch):
    """The field grammar is review_docs' `updated_span`, the reader the restamp
    writer and check_Q share; the job carries no regex of its own for it."""
    monkeypatch.setattr(rsc.review_docs, "updated_span", lambda text: None)
    out, reason = _run(_stamp_conflict("2026-02-02", "2026-03-03"))
    assert out is None
    assert reason == rsc.NO_FIELD


def test_the_reasons_are_a_closed_vocabulary():
    """Every reason the job can print is a member of REASONS, once."""
    assert isinstance(rsc.REASONS, tuple)
    assert len(set(rsc.REASONS)) == len(rsc.REASONS)
    assert rsc.RESOLVED in rsc.REASONS
    assert set(rsc.REFUSALS) | set(rsc.SKIPS) | {rsc.RESOLVED} == set(rsc.REASONS)
    used = {r for _, _, r in _NOT_STAMP_ONLY} | {rsc.UNPARSABLE_DATE}
    assert used == set(rsc.REFUSALS), "a refusal no test reaches"
