"""
title: Unit — backend.showcase
kind: tests
layer: backend
summary: Mirrors src/backend/showcase/. Exercises the read model via the public API, no disk.
"""
import pytest

from backend.showcase import Showcase, to_jsonable

pytestmark = pytest.mark.unit


def _corpus():
    """A tiny in-memory corpus: one doc with two sections + one module/symbol."""
    return {
        "schema_version": 1,
        "nodes": [
            {"node_id": "readme", "kind": "doc", "title": "Readme",
             "path": "README.md", "summary": "the root readme",
             "text_excerpt": "body", "owner": "alice", "tags": ["template", "axi"],
             "anchor": None, "lineno": None, "parent": None,
             "children": ["readme#setup"], "links": [{"to": "guide"}]},
            {"node_id": "readme#setup", "kind": "section", "title": "Setup",
             "path": "README.md", "summary": "how to set up", "text_excerpt": "",
             "owner": "alice", "tags": ["setup"], "anchor": "setup", "lineno": 5,
             "parent": "readme", "children": [], "links": []},
            {"node_id": "guide", "kind": "doc", "title": "Guide",
             "path": "docs/guide.md", "summary": "a guide about AXI",
             "text_excerpt": "", "owner": "", "tags": ["axi", "guide"],
             "anchor": None, "lineno": None, "parent": None, "children": [],
             "links": [{"to": "readme"}]},
            {"node_id": "mod-py", "kind": "module", "title": "mod.py",
             "path": "src/mod.py", "summary": "a module", "text_excerpt": "",
             "owner": "bob", "tags": ["mod"], "anchor": None, "lineno": 1,
             "parent": None, "children": ["mod-py::fn"], "links": []},
            {"node_id": "mod-py::fn", "kind": "symbol", "title": "fn",
             "path": "src/mod.py", "summary": "a function", "text_excerpt": "",
             "owner": "bob", "tags": ["fn"], "anchor": "fn", "lineno": 3,
             "parent": "mod-py", "children": [], "links": []},
        ],
    }


def _project():
    return {
        "name": "demoproj",
        "layers": {
            "frontend": {"language": "typescript", "root": "src/frontend",
                         "stack": "astro", "available": ["react-vite", "astro"]},
            "backend": {"language": "python", "path": "src/backend"},
        },
        "transports": {"enabled": ["rest"],
                       "available": {"rest": "api/rest_fastapi", "mcp": "mcp"}},
    }


def _sc(present=frozenset()):
    return Showcase(name="demoproj", project=_project(), corpus=_corpus(),
                    present_scripts=present)


def test_overview_counts_and_layers():
    ov = _sc().overview()
    assert ov.name == "demoproj"
    assert ov.stats.docs == 2 and ov.stats.sections == 1
    assert ov.stats.modules == 1 and ov.stats.symbols == 1
    assert ov.stats.directories == 2          # README.md -> ".", docs/guide.md -> "docs"
    assert ov.stats.checks >= 5
    names = {layer.name for layer in ov.layers}
    assert names == {"frontend", "backend"}
    rest = next(t for t in ov.transports if t.name == "rest")
    assert rest.enabled and rest.directory == "api/rest_fastapi"
    assert next(t for t in ov.transports if t.name == "mcp").enabled is False


def test_checks_present_flag_reflects_disk():
    present = frozenset({"scripts/check_structure.py"})
    checks = {c.slug: c for c in _sc(present).checks()}
    assert checks["structure"].present is True
    assert checks["corpus"].present is False
    assert checks["structure"].gate == "error"


def test_features_are_nonempty_and_curated():
    feats = _sc().features()
    assert any(f.slug == "deterministic-checks" for f in feats)
    assert all(f.title and f.summary for f in feats)


def test_principles_cover_the_agent_rules_gap_and_link_out():
    principles = _sc().principles()
    slugs = [p.slug for p in principles]
    # The biggest documented gap — the AGENT.md/CLAUDE.md mechanism — is covered.
    assert "agent-rules" in slugs
    # Every principle is well-formed and points at its source section to read.
    assert all(p.title and p.essence and p.detail and p.links for p in principles)
    # Slugs are unique (stable anchors the conventions page renders).
    assert len(set(slugs)) == len(slugs)


def test_edge_adapters_feature_links_to_the_new_capabilities():
    """The MCP/model/scheduled additions are surfaced as a curated feature that
    points at their corpus docs (link integrity is asserted live in integration)."""
    feats = {f.slug: f for f in _sc().features()}
    assert "edge-adapters" in feats
    hrefs = {ln.href for ln in feats["edge-adapters"].links}
    assert {"mcp-readme", "models-readme"} <= hrefs


def _project_with_models():
    p = _project()
    p["models"] = {
        "default": "claude-code-headless",
        "available": {"claude-code-headless": "models",
                      "openai-compatible": "models", "fake": "models"},
    }
    return p


def test_model_adapters_projected_from_the_manifest():
    sc = Showcase(name="demoproj", project=_project_with_models(),
                  corpus=_corpus(), present_scripts=frozenset())
    adapters = sc.model_adapters()
    names = [m.name for m in adapters]
    assert names == sorted(names)                                   # stable order
    assert set(names) == {"claude-code-headless", "openai-compatible", "fake"}
    assert [m.name for m in adapters if m.default] == ["claude-code-headless"]
    assert all(m.directory == "models" for m in adapters)


def test_model_adapters_absent_block_is_graceful_empty():
    # An older manifest with no 'models' block stays valid — empty, not an error.
    assert _sc().model_adapters() == ()


def test_doc_tree_groups_by_top_dir():
    groups = {g.directory: g for g in _sc().doc_tree()}
    assert set(groups) == {".", "docs"}
    assert groups["."].docs[0].node_id == "readme"


def test_node_resolves_neighbours():
    detail = _sc().node("readme")
    assert detail is not None
    assert detail.parent is None
    assert [c.node_id for c in detail.children] == ["readme#setup"]
    assert [r.node_id for r in detail.related] == ["guide"]   # link resolved
    assert _sc().node("missing") is None


def test_search_ranks_by_overlap():
    hits = _sc().search("AXI", limit=5)
    ids = [h.node.node_id for h in hits]
    assert "guide" in ids and "readme" in ids
    assert all(h.score > 0 for h in hits)
    assert _sc().search("") == ()


def test_llms_index_follows_the_convention():
    txt = _sc().llms_index("https://example.test")
    lines = txt.splitlines()
    assert lines[0].startswith("# ")              # single H1
    assert any(ln.startswith("> ") for ln in lines)  # blockquote summary
    assert "## Root" in txt and "## docs" in txt   # per-directory sections
    # link list items point at the wiki with the node id
    assert "- [Readme](https://example.test/wiki?id=readme): the root readme" in txt
    assert "## Optional" in txt
    assert "/llms-full.txt" in txt and "/api/wiki/tree" in txt
    # relative base by default
    assert "(/wiki?id=readme)" in _sc().llms_index()


def test_to_jsonable_roundtrips_overview():
    payload = to_jsonable(_sc().overview())
    assert isinstance(payload, dict)
    assert payload["stats"]["docs"] == 2
    assert isinstance(payload["layers"], list)
    import json
    json.dumps(payload)   # must be JSON-serialisable
