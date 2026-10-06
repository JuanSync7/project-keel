"""
title: Unit — review_docs (the freshness rule)
kind: tests
layer: n/a
summary: The pure half of scripts/review_docs.py, pinned: `updated:` must be an ISO date, never earlier than the file's last commit, and a file modified in the working tree must carry today's date or later. Measured before the rule landed: 135 of 153 governed documents were stamped earlier than their last commit — including AGENT.md and CONVENTIONS.md — and nothing said so.
"""

import datetime
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

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


def test_a_stale_reason_names_the_remedy():
    """A finding that does not say how to clear it is a chore with no handle.
    The dates stay in the reason; the command that fixes it is added."""
    committed = _find(("a.md", "2026-06-24", "2026-08-18", False))[0]["reason"]
    modified = _find(("a.md", "2026-08-18", "2026-08-18", True))[0]["reason"]
    for reason in (committed, modified):
        assert "make restamp-docs" in reason, reason
    assert "2026-06-24" in committed and "2026-08-18" in committed
    assert "`updated: %s`" % TODAY in modified


def test_a_bom_prefixed_doc_is_governed(tmp_path):
    """`text.startswith('---')` is False after a U+FEFF, so a BOM document used
    to be silently ungoverned. The span helper is the one grammar the judge and
    the writer (restamp_docs) share."""
    doc = tmp_path / "bom.md"
    text = "\ufeff---\ntitle: x\nupdated: 2026-01-01\n---\n# x\n"
    doc.write_text(text, encoding="utf-8")
    assert review_docs._frontmatter_updated(str(doc)) == "2026-01-01"
    start, end = review_docs.updated_span(text)
    assert text[start:end] == "2026-01-01"


def test_an_empty_updated_never_borrows_the_next_line():
    """`updated:\\s*` used to span the newline and read the NEXT line's token as
    the date; the value is horizontal-whitespace-delimited now."""
    assert review_docs.updated_span("---\nupdated:\ntitle: 2026-01-01\n---\n") is None
    assert review_docs.updated_span("---\ntitle: x\n---\nupdated: 2026-01-01\n") is None


# --- the advisory that stays advisory: unresolved mentions ---------------------


def test_a_backticked_path_that_resolves_to_nothing_is_listed(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "real.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "docs" / "a.md").write_text(
        "See `scripts/real.py`, `scripts/gone.py`, `docs/a.md`, `a.md` and `not a path`.\n"
        "Also `check_structure.py` as a noun.\n",
        encoding="utf-8",
    )
    found = review_docs.unresolved_mentions(str(tmp_path))
    assert found == [
        ("docs/a.md", 1, "scripts/gone.py"),
        ("docs/a.md", 2, "check_structure.py"),
    ]


def test_mentions_never_make_strict_fail(tmp_path, monkeypatch, capsys):
    """Advisory in every mode: `--strict` gates freshness only."""
    (tmp_path / "a.md").write_text("`nowhere/x.py`\n", encoding="utf-8")
    monkeypatch.setattr(review_docs, "collect", lambda root: [])
    assert review_docs.main(["--root", str(tmp_path), "--strict"]) == 0
    assert "unresolved mention" in capsys.readouterr().out


# --- roster rows: the facts the doc reviewer judges -----------------------------


def test_every_roster_row_is_reported_with_its_not_for_cell(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "README.md").write_text(
        "# S\n\n## What ships here\n\n| Member | Purpose | Not for |\n|---|---|---|\n"
        "| `a.py` | does a | b (that is `b.py`) |\n| `b.py` | does b | n/a |\n\n## Later\n\n| Member | Not for |\n|---|---|\n| `z` | no |\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plain.md").write_text("# no roster\n", encoding="utf-8")
    rows = review_docs.roster_rows(str(tmp_path))
    assert rows == [
        {
            "path": "scripts/README.md",
            "member": "a.py",
            "line": 7,
            "not_for": "b (that is `b.py`)",
        },
        {"path": "scripts/README.md", "member": "b.py", "line": 8, "not_for": "n/a"},
    ]


# --- one clock: the judge and the writer read "today" from the same source -----


def test_the_judge_resolves_today_from_source_date_epoch_then_the_clock():
    """The writer (restamp_docs) stamps with SOURCE_DATE_EPOCH when it is set. A
    judge that ignored it held a modified document to a different day than the
    writer stamped, so the remedy it names wrote nothing and the gate stayed red
    (measured with SOURCE_DATE_EPOCH=1767225600). One resolver, owned here."""
    assert review_docs.resolve_today("2030-05-06", {}) == datetime.date(2030, 5, 6)
    env = {"SOURCE_DATE_EPOCH": "86399"}  # one second before midnight UTC
    assert review_docs.resolve_today(None, env) == datetime.date(1970, 1, 1)
    assert review_docs.resolve_today(None, {}) == datetime.date.today()


@pytest.mark.parametrize(
    "argv_today, epoch",
    [
        (None, "tomorrow"),
        (None, ""),
        (None, "1.5"),
        # Digits, but past datetime's year 9999: fromtimestamp raises, and an
        # uncaught raise exits 1, which in `--check` means "would restamp".
        (None, "99999999999999"),
        ("2026-9-2", None),
        ("2026-02-30", None),
    ],
)
def test_a_malformed_date_source_is_a_named_error_never_a_crash(argv_today, epoch):
    env = {} if epoch is None else {"SOURCE_DATE_EPOCH": epoch}
    with pytest.raises(review_docs.DateSourceError):
        review_docs.resolve_today(argv_today, env)


def test_the_judge_exits_2_on_a_malformed_date_source(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "99999999999999")
    assert review_docs.main(["--root", str(tmp_path)]) == 2
    assert "SOURCE_DATE_EPOCH" in capsys.readouterr().err
