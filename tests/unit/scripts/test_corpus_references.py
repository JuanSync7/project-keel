"""
title: Unit — the corpus's authored reference edges
kind: tests
layer: n/a
summary: build_corpus turns every relative Markdown link, `§N` citation and backticked repository path in a document into an edge (`kind` link / citation / mention, `source` deterministic) from the section that wrote it to the node it names — the knowledge graph's AUTHORED edges, computed with the very grammar check_Q gates so the two can never disagree about what a reference is. link_corpus recomputes only its own keyword edges and keeps these. Before this, the corpus had 2,790 edges and not one of them was something an author wrote: CONVENTIONS.md, cited 132 times, was an island.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import build_corpus as bc  # noqa: E402
import check_corpus as cc  # noqa: E402
import link_corpus as lc  # noqa: E402

pytestmark = pytest.mark.unit

_S = "§"  # spelled as an escape: check_Q reads this file's source too


def _fm(doc_id, title):
    return (
        "---\ntitle: %s\nkind: doc\nlayer: n/a\nstatus: stable\nowner: someone\n"
        "tags: [x]\nsummary: About %s.\nid: %s\ncreated: 2026-01-01\n"
        "updated: 2026-01-01\nvisibility: internal\ncanonical: true\n---\n"
        % (title, title, doc_id)
    )


_CONV = _fm("conventions", "Conventions") + (
    "# Conventions\n\nPreamble linking [the guide](docs/guide.md).\n\n"
    "## 1. Frontmatter\n\ntext\n\n"
    "## 2. Taxonomy\n\nSee `src/thing.py` and [part one](docs/guide.md#part-one).\n"
)
_GUIDE = _fm("guide", "Guide") + (
    "# Guide\n\nCites CONVENTIONS " + _S + "2 and links [conv](../CONVENTIONS.md).\n\n"
    "## Part one\n\nMentions `src/thing.py`, `scripts/` and [nowhere](missing.md).\n\n"
    "## Part two\n\n```md\n[fenced](../CONVENTIONS.md)\n```\n\nand `not a path` here.\n"
)
_MOD = '"""\ntitle: Thing\nsummary: Does things.\n"""\n__all__ = ["thing"]\n\n\ndef thing():\n    """Return the thing."""\n    return 1\n'
_SCRIPTS_README = _fm("scripts-readme", "Scripts") + "# Scripts\n\nDoers.\n"


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "thing.py").write_text(_MOD, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(_GUIDE, encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "README.md").write_text(_SCRIPTS_README, encoding="utf-8")
    (tmp_path / "CONVENTIONS.md").write_text(_CONV, encoding="utf-8")
    return tmp_path


def _nodes(root):
    return {n["node_id"]: n for n in bc.build_corpus(str(root))["nodes"]}


def _edges(node, kind):
    return [(e["to"], e["via"]) for e in node["links"] if e["kind"] == kind]


def test_a_link_becomes_a_link_edge_from_the_writing_node_to_the_doc(repo):
    nodes = _nodes(repo)
    assert ("conventions", "../CONVENTIONS.md") in _edges(nodes["guide"], "link")
    assert ("guide", "docs/guide.md") in _edges(nodes["conventions"], "link")


def test_a_link_with_an_anchor_targets_the_section_node(repo):
    nodes = _nodes(repo)
    sec = nodes["conventions#2-taxonomy"]
    assert ("guide#part-one", "docs/guide.md#part-one") in _edges(sec, "link")


def test_a_section_citation_becomes_a_citation_edge_to_the_numbered_section(repo):
    nodes = _nodes(repo)
    assert ("conventions#2-taxonomy", _S + "2") in _edges(nodes["guide"], "citation")


def test_a_backticked_repository_path_becomes_a_mention_edge(repo):
    nodes = _nodes(repo)
    module = [
        n
        for n in nodes.values()
        if n["kind"] == "module" and n["path"] == "src/thing.py"
    ][0]
    part_one = nodes["guide#part-one"]
    assert (module["node_id"], "src/thing.py") in _edges(part_one, "mention")
    assert (module["node_id"], "src/thing.py") in _edges(
        nodes["conventions#2-taxonomy"], "mention"
    )


def test_a_directory_mention_targets_its_readme(repo):
    nodes = _nodes(repo)
    assert ("scripts-readme", "scripts/") in _edges(nodes["guide#part-one"], "mention")


def test_what_does_not_resolve_leaves_no_edge_and_no_error(repo):
    """A dead link is check_Q's finding, not the corpus's; a backticked phrase
    that is not a path is prose."""
    nodes = _nodes(repo)
    assert not [e for e in nodes["guide#part-one"]["links"] if "missing" in e["via"]]
    assert not [e for e in nodes["guide#part-two"]["links"] if "not a path" in e["via"]]


def test_a_link_inside_a_fence_is_an_illustration_not_an_edge(repo):
    assert _edges(_nodes(repo)["guide#part-two"], "link") == []


def test_reference_edges_are_deterministic_and_carry_the_shape_check_corpus_knows(repo):
    first, second = bc.build_corpus(str(repo)), bc.build_corpus(str(repo))
    assert cc._dumps(first) == cc._dumps(second)
    for n in first["nodes"]:
        for e in n["links"]:
            assert e["source"] == "deterministic" and e["score"] == 1.0
            assert e["to"] != n["node_id"], "no self-edges"
    assert cc.validate(first) == []


def test_link_corpus_keeps_reference_edges_and_recomputes_only_keywords(repo):
    corpus = lc.link_corpus(bc.build_corpus(str(repo)), max_links=1)
    guide = [n for n in corpus["nodes"] if n["node_id"] == "guide"][0]
    assert ("conventions", "../CONVENTIONS.md") in _edges(guide, "link")
    assert len(_edges(guide, "keyword")) <= 1
    again = lc.link_corpus(corpus, max_links=1)
    assert cc._dumps(again) == cc._dumps(corpus), "linking is idempotent"


def test_reference_edges_survive_the_deterministic_projection(repo):
    corpus = lc.link_corpus(bc.build_corpus(str(repo)))
    kept = cc._deterministic_projection(corpus)
    guide = [n for n in kept["nodes"] if n["node_id"] == "guide"][0]
    assert _edges(guide, "citation"), (
        "authored edges are part of what staleness compares"
    )
