"""
title: Integration — showcase loads the live repo
kind: tests
layer: backend
summary: load_showcase reads config/project.json + wiki/corpus.json from the real tree.
"""
import os

import pytest

from backend.showcase import load_showcase

pytestmark = pytest.mark.integration

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_load_showcase_reads_real_repo():
    sc = load_showcase(ROOT)
    ov = sc.overview()
    assert ov.name  # from config/project.json
    # The repo has docs and at least the backend layer.
    assert ov.stats.docs > 0
    assert any(layer.name == "backend" for layer in ov.layers)
    # Every catalogued check script actually exists in this repo.
    assert all(c.present for c in sc.checks()), \
        [c.slug for c in sc.checks() if not c.present]


def test_known_doc_node_resolves():
    sc = load_showcase(ROOT)
    # The conventions doc is a stable corpus node id.
    detail = sc.node("conventions")
    if detail is not None:           # corpus may be unbuilt in a fresh checkout
        assert detail.title
        assert detail.path.endswith("CONVENTIONS.md")


def test_search_finds_something():
    sc = load_showcase(ROOT)
    if sc.doc_tree():                # only meaningful once the corpus is built
        hits = sc.search("conventions frontmatter", limit=5)
        assert hits


def test_markdown_body_is_real_markdown():
    sc = load_showcase(ROOT)
    if sc.node("conventions") is not None:
        md = sc.markdown("conventions")
        assert "## " in md                       # real markdown headings
        assert not md.startswith("---")          # frontmatter stripped
        assert "frontmatter" in md.lower()
    # unknown node -> empty, never raises
    assert sc.markdown("definitely-not-a-node") == ""


def test_code_node_markdown_is_not_a_fenced_block():
    """Module/symbol docstrings render AS markdown (so `backtick` terms become
    code), not wrapped in a verbatim ``` fence that would show backticks."""
    sc = load_showcase(ROOT)
    mod = next((g for g in sc.doc_tree()), None)
    # find any module/symbol node id from the corpus via search
    hits = sc.search("showcase repository facade", limit=10)
    code = [h.node for h in hits if h.node.kind in ("module", "symbol")]
    if code:
        md = sc.markdown(code[0].node_id)
        assert not md.lstrip().startswith("```")   # not fenced verbatim
    assert mod is not None
