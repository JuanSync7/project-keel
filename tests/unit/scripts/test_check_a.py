"""
title: Unit — check_structure check_A (frontmatter lifecycle symmetry)
kind: tests
layer: n/a
summary: check_A's lifecycle rule, pinned: a document whose status says it has been replaced must name its replacement. `deprecated` has required `superseded_by` since the first frontmatter check; `superseded` — the ADR lifecycle's word for the same fact — did not, so an ADR could be marked superseded by nothing and the corpus's "follow the chain to the live version" promise ended at a dead end. The two statuses are one rule with two vocabularies. A document stating a looser visibility than a README.md on its chain is an error, and a symlinked file is judged once, at its real path, against the chain build_corpus ranks it by.
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


# --- a child stating a looser visibility than a README above it -------------
#
# The corpus gives a node the strictest visibility on its README chain
# (scripts/check_structure.py strictest_visibility), so a looser level stated
# below a README is overridden in silence; check_A names the contradiction.

_ORDER = cs.VISIBILITY_ORDER
_PAIRS = [(a, b) for a in _ORDER for b in _ORDER]


def _contradictions(stated):
    return cs._visibility_contradictions(stated)


@pytest.mark.parametrize("above, below", _PAIRS)
def test_a_looser_child_is_named_and_an_equal_or_stricter_one_is_not(above, below):
    found = _contradictions({"README.md": above, "docs/plan.md": below})
    if _ORDER.index(below) < _ORDER.index(above):
        assert len(found) == 1, found
        message = found[0]
        assert message.startswith("docs/plan.md: visibility '%s'" % below), message
        assert "'%s'" % above in message and "README.md" in message, message
    else:
        assert found == [], found


def test_the_message_names_the_nearest_readme_at_the_strictest_level():
    found = _contradictions(
        {
            "README.md": "confidential",
            "src/README.md": "confidential",
            "src/backend/README.md": "public",
            "src/backend/AGENT.md": "internal",
        }
    )
    by_path = {m.split(":", 1)[0]: m for m in found}
    assert sorted(by_path) == ["src/backend/AGENT.md", "src/backend/README.md"], found
    assert "stated by src/README.md" in by_path["src/backend/AGENT.md"], found
    assert "stated by src/README.md" in by_path["src/backend/README.md"], found
    assert "CONVENTIONS §1" in by_path["src/backend/AGENT.md"], found


def test_a_readme_is_judged_against_the_readmes_above_and_not_itself():
    assert _contradictions({"docs/README.md": "public"}) == []
    found = _contradictions({"README.md": "internal", "docs/README.md": "public"})
    assert len(found) == 1 and found[0].startswith("docs/README.md:"), found


def test_a_sibling_or_a_non_readme_above_is_not_an_ancestor():
    assert (
        _contradictions(
            {
                "docs/AGENT.md": "restricted",
                "docs/other/README.md": "restricted",
                "docs/plan.md": "public",
            }
        )
        == []
    )


def test_a_value_outside_the_vocabulary_is_left_to_the_invalid_visibility_error():
    assert _contradictions({"README.md": "secret", "docs/plan.md": "public"}) == []
    assert _contradictions({"README.md": "internal", "docs/plan.md": "open"}) == []


def test_check_a_reports_the_contradiction_over_a_tree(repo):
    readme = _doc(repo / "README.md", "stable").read_text(encoding="utf-8")
    (repo / "README.md").write_text(
        readme.replace("visibility: internal", "visibility: confidential"),
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    _doc(repo / "docs" / "plan.md", "stable")
    cs.check_A()
    found = [e for e in cs.errors if "less restrictive" in e]
    assert len(found) == 1 and found[0].startswith("docs/plan.md:"), cs.errors


def _stated(path, visibility):
    """A governed document at *path* that states *visibility*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _doc(path, "stable").read_text(encoding="utf-8")
    path.write_text(
        text.replace("visibility: internal", "visibility: %s" % visibility),
        encoding="utf-8",
    )


def _linked_secret_tree(repo, plan_visibility):
    """`docs/a-open/plan.md` links to `docs/z-secret/plan.md`, under a
    confidential README; the walk meets the link first if it is sorted."""
    _stated(repo / "README.md", "internal")
    _stated(repo / "docs" / "z-secret" / "README.md", "confidential")
    _stated(repo / "docs" / "z-secret" / "plan.md", plan_visibility)
    (repo / "docs" / "a-open").mkdir()
    (repo / "docs" / "a-open" / "plan.md").symlink_to("../z-secret/plan.md")


@pytest.mark.parametrize("plan_visibility", ["public", "internal"])
def test_check_a_judges_a_linked_file_at_its_real_path(repo, plan_visibility):
    """The corpus serves the file at the strictest level of its real path's
    README chain, so the message names that file, that level and that README,
    whichever path the walk met first."""
    _linked_secret_tree(repo, plan_visibility)
    cs.check_A()
    found = [e for e in cs.errors if "less restrictive" in e]
    assert len(found) == 1, cs.errors
    message = found[0]
    assert message.startswith(
        "docs/z-secret/plan.md: visibility '%s'" % plan_visibility
    ), message
    assert "stated by docs/z-secret/README.md" in message, message
    assert "serves it as 'confidential'" in message, message


def test_check_a_names_the_level_build_corpus_serves(repo):
    """check_A and build_corpus read one README chain, so the level the
    message names is the level the corpus records for the node."""
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    import build_corpus as bc

    _linked_secret_tree(repo, "public")
    cs.check_A()
    (message,) = [e for e in cs.errors if "less restrictive" in e]
    served = {
        n["node_id"]: n["visibility"] for n in bc.build_corpus(str(repo))["nodes"]
    }
    assert "serves it as '%s'" % served["plan"] in message, (
        message,
        served,
    )
