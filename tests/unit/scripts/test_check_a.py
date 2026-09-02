"""
title: Unit — check_structure check_A (frontmatter lifecycle symmetry)
kind: tests
layer: n/a
summary: check_A's lifecycle rule, pinned: a document whose status says it has been replaced must name its replacement. `deprecated` has required `superseded_by` since the first frontmatter check; `superseded` — the ADR lifecycle's word for the same fact — did not, so an ADR could be marked superseded by nothing and the corpus's "follow the chain to the live version" promise ended at a dead end. The two statuses are one rule with two vocabularies.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway root with the gate's module-level state isolated."""
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    return tmp_path


def _doc(path, status, superseded_by=None):
    lines = [
        "---",
        "title: T",
        "kind: adr",
        "layer: n/a",
        "status: %s" % status,
        "owner: someone",
        "summary: S",
        "id: %s" % path.stem,
        "created: 2026-01-01",
        "updated: 2026-01-01",
        "visibility: internal",
        "canonical: true",
    ]
    if superseded_by:
        lines.append("superseded_by: %s" % superseded_by)
    lines.append("---")
    path.write_text("\n".join(lines) + "\n# T\n", encoding="utf-8")
    return path


def _lifecycle_errors():
    return [e for e in cs.errors if "superseded_by" in e]


@pytest.mark.parametrize("status", ["deprecated", "superseded"])
def test_a_replaced_document_that_names_no_replacement_errors(repo, status):
    cs.check_frontmatter(str(_doc(repo / "a.md", status)), {})
    errs = _lifecycle_errors()
    assert len(errs) == 1 and status in errs[0], cs.errors


@pytest.mark.parametrize("status", ["deprecated", "superseded"])
def test_a_replaced_document_that_names_its_replacement_passes(repo, status):
    cs.check_frontmatter(str(_doc(repo / "a.md", status, "docs/adr/0010-x.md")), {})
    assert _lifecycle_errors() == [], cs.errors


@pytest.mark.parametrize("status", ["accepted", "proposed", "stable", "draft"])
def test_a_live_document_needs_no_replacement(repo, status):
    cs.check_frontmatter(str(_doc(repo / "a.md", status)), {})
    assert _lifecycle_errors() == [], cs.errors
