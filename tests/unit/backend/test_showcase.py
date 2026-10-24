"""
title: Unit — backend.showcase
kind: tests
layer: backend
summary: Mirrors src/backend/showcase/. Exercises the read model via the public API with no disk, except the two agreement tests, which read the document each curated table must agree with: the catalogue of deterministic checks for CHECKS, and the feature catalogue config/project.json `doc_drift.features_reference` names for FEATURES.
"""

import re

import pytest

from backend.showcase import CHECKS, FEATURES, Showcase, to_jsonable

pytestmark = pytest.mark.unit

# config/project.json `corpus.served_visibilities` as keel ships it.
_SERVED = frozenset({"public", "internal"})


def _corpus():
    """A tiny in-memory corpus: one doc with two sections + one module/symbol."""
    return {
        "schema_version": 1,
        "nodes": [
            {
                "node_id": "readme",
                "kind": "doc",
                "title": "Readme",
                "path": "README.md",
                "summary": "the root readme",
                "text_excerpt": "body",
                "owner": "alice",
                "tags": ["template", "axi"],
                "anchor": None,
                "lineno": None,
                "parent": None,
                "children": ["readme#setup"],
                "links": [{"to": "guide"}],
                "visibility": "internal",
            },
            {
                "node_id": "readme#setup",
                "kind": "section",
                "title": "Setup",
                "path": "README.md",
                "summary": "how to set up",
                "text_excerpt": "",
                "owner": "alice",
                "tags": ["setup"],
                "anchor": "setup",
                "lineno": 5,
                "parent": "readme",
                "children": [],
                "links": [],
                "visibility": "internal",
            },
            {
                "node_id": "guide",
                "kind": "doc",
                "title": "Guide",
                "path": "docs/guide.md",
                "summary": "a guide about AXI",
                "text_excerpt": "",
                "owner": "",
                "tags": ["axi", "guide"],
                "anchor": None,
                "lineno": None,
                "parent": None,
                "children": [],
                "links": [{"to": "readme"}],
                "visibility": "public",
            },
            {
                "node_id": "mod-py",
                "kind": "module",
                "title": "mod.py",
                "path": "src/mod.py",
                "summary": "a module",
                "text_excerpt": "",
                "owner": "bob",
                "owner_source": "default",
                "tags": ["mod"],
                "anchor": None,
                "lineno": 1,
                "parent": None,
                "children": ["mod-py::fn"],
                "links": [],
                "visibility": "internal",
            },
            {
                "node_id": "mod-py::fn",
                "kind": "symbol",
                "title": "fn",
                "path": "src/mod.py",
                "summary": "a function",
                "text_excerpt": "",
                "owner": "bob",
                "tags": ["fn"],
                "anchor": "fn",
                "lineno": 3,
                "parent": "mod-py",
                "children": [],
                "links": [],
                "visibility": "internal",
            },
        ],
    }


def _project():
    return {
        "name": "demoproj",
        "layers": {
            "frontend": {
                "language": "typescript",
                "root": "src/frontend",
                "stack": "astro",
                "available": ["react-vite", "astro"],
            },
            "backend": {"language": "python", "path": "src/backend"},
        },
        "transports": {
            "enabled": ["rest"],
            "available": {"rest": "api/rest_fastapi", "mcp": "mcp"},
        },
    }


def _sc(present=frozenset()):
    return Showcase(
        name="demoproj",
        project=_project(),
        corpus=_corpus(),
        present_scripts=present,
        served_visibilities=_SERVED,
    )


def test_overview_counts_and_layers():
    ov = _sc().overview()
    assert ov.name == "demoproj"
    assert ov.stats.docs == 2 and ov.stats.sections == 1
    assert ov.stats.modules == 1 and ov.stats.symbols == 1
    assert ov.stats.directories == 2  # README.md -> ".", docs/guide.md -> "docs"
    assert ov.stats.checks >= 5
    names = {layer.name for layer in ov.layers}
    assert names == {"frontend", "backend"}
    rest = next(t for t in ov.transports if t.name == "rest")
    assert rest.enabled and rest.directory == "api/rest_fastapi"
    assert next(t for t in ov.transports if t.name == "mcp").enabled is False


def test_checks_mirror_the_catalogue_row_for_row():
    """The showcase's Checks page and docs/guides/deterministic-checks.md must
    describe one gate. check_R holds the catalogue to the Makefile; this holds
    the mirror to the catalogue, with the same table reader, so a row added to
    either without the other fails here rather than shipping two truths."""
    import sys as _sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    _sys.path.insert(0, str(root / "scripts"))
    import check_structure as cs  # noqa: PLC0415 — the reader is the gate's own

    catalogue = root / "docs" / "guides" / "deterministic-checks.md"
    header, rows = cs._pipe_table(
        catalogue.read_text(encoding="utf-8"), ("Script", "Gate?")
    )
    col = header.index("script")
    catalogued = {cs._BACKTICKED.search(r[col]).group(1).split()[0] for r in rows}
    assert {c.script for c in CHECKS} == catalogued


# The feature catalogue's pillar table: the columns it carries, read by the
# gate's own table reader, and the cell a row key opens.
_PILLAR_COLUMNS = ("Pillar slug", "Title", "Rows")


def _pillar_findings(text, features, table):
    """Each FEATURES entry is one pillar row with its slug and title, every
    pillar row is a FEATURES entry, and each key its Rows cell names opens a
    row of the catalogue."""
    import check_structure as cs  # noqa: PLC0415 -- the reader is the gate's own

    header, rows = table
    at = [header.index(c.lower()) for c in _PILLAR_COLUMNS]
    pillars = {}
    findings = []
    for raw in rows:
        cells = [raw[i] if i < len(raw) else "" for i in at]
        slug = cs._BACKTICKED.search(cells[0])
        if slug is None:
            findings.append("a pillar row names no slug: %r" % cells[0])
            continue
        pillars[slug.group(1)] = cells
    curated = {f.slug: f for f in features}
    for slug in sorted(set(curated) | set(pillars)):
        if slug not in pillars:
            findings.append("FEATURES `%s` has no pillar row" % slug)
            continue
        if slug not in curated:
            findings.append("pillar `%s` is no FEATURES entry" % slug)
            continue
        if pillars[slug][1] != curated[slug].title:
            findings.append(
                "pillar `%s` is titled %r; FEATURES says %r"
                % (slug, pillars[slug][1], curated[slug].title)
            )
        keys = cs._BACKTICKED.findall(pillars[slug][2])
        if not keys:
            findings.append("pillar `%s` names no catalogue row" % slug)
        findings.extend(
            "pillar `%s` names `%s`, which opens no row" % (slug, key)
            for key in keys
            if not re.search(r"^\|\s*`%s`" % re.escape(key), text, re.MULTILINE)
        )
    return findings


def test_features_mirror_the_catalogue_pillars():
    """The showcase home page's feature cards and the feature catalogue must
    describe one product: each card is a pillar row with its title, and each
    pillar names the catalogue rows that deliver it. A pillar dropped from
    either side is one finding."""
    import json
    import sys as _sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    _sys.path.insert(0, str(root / "scripts"))
    import check_structure as cs  # noqa: PLC0415 -- the reader is the gate's own

    manifest = json.loads(
        (root / "config" / "project.json").read_text(encoding="utf-8")
    )
    rel = manifest["doc_drift"]["features_reference"]
    text = (root / rel).read_text(encoding="utf-8")
    table = cs._pipe_table(text, _PILLAR_COLUMNS)
    assert table is not None, "%s holds no pillar table" % rel
    assert FEATURES, "FEATURES is empty -- zero items"
    findings = _pillar_findings(text, FEATURES, table)
    assert not findings, "\n".join(findings)
    header, rows = table
    assert len(_pillar_findings(text, FEATURES, (header, rows[1:]))) == 1
    assert len(_pillar_findings(text, FEATURES[1:], table)) == 1


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


def test_coding_practices_feature_links_to_the_guide():
    """The coding-practices work is surfaced as a curated feature pointing at its
    guide (link integrity is asserted live against the corpus in e2e)."""
    feats = {f.slug: f for f in _sc().features()}
    assert "coding-practices" in feats
    hrefs = {ln.href for ln in feats["coding-practices"].links}
    assert "docs-guides-coding-practices" in hrefs


def _project_with_models():
    p = _project()
    p["models"] = {
        "default": "claude-code-headless",
        "available": {
            "claude-code-headless": "models",
            "openai-compatible": "models",
            "fake": "models",
        },
    }
    return p


def test_model_adapters_projected_from_the_manifest():
    sc = Showcase(
        name="demoproj",
        project=_project_with_models(),
        corpus=_corpus(),
        present_scripts=frozenset(),
        served_visibilities=_SERVED,
    )
    adapters = sc.model_adapters()
    names = [m.name for m in adapters]
    assert names == sorted(names)  # stable order
    assert set(names) == {"claude-code-headless", "openai-compatible", "fake"}
    assert [m.name for m in adapters if m.default] == ["claude-code-headless"]
    assert all(m.directory == "models" for m in adapters)


def test_model_adapters_absent_block_is_graceful_empty():
    # An older manifest with no 'models' block stays valid — empty, not an error.
    assert _sc().model_adapters() == ()


def _practices():
    """A minimal practices registry matching config/practices.json's shape."""
    return {
        "schema_version": 1,
        "practices": [
            {
                "id": "narrow-optional",
                "row": 7,
                "scope": "universal",
                "tier": "gate",
                "status": "on",
                "title": "No implicit Optional",
                "mechanism": "mypy no_implicit_optional",
            },
            {
                "id": "precise-container-types",
                "row": 2,
                "scope": "universal",
                "tier": "gate",
                "status": "on",
                "title": "Declare element types",
                "mechanism": "mypy disallow_any_generics",
            },
            {
                "id": "shape-typed-tensors",
                "row": 1,
                "scope": "domain",
                "tier": "gate",
                "status": "deferred:slice-4",
                "title": "Shape-typed tensors",
                "mechanism": "check_L",
            },
        ],
    }


def test_practice_items_projected_and_sorted_by_row():
    sc = Showcase(
        name="demoproj",
        project=_project(),
        corpus=_corpus(),
        practices=_practices(),
        present_scripts=frozenset(),
        served_visibilities=_SERVED,
    )
    items = sc.practice_items()
    assert [p.id for p in items] == [
        "shape-typed-tensors",
        "precise-container-types",
        "narrow-optional",
    ]  # by row
    assert [p.row for p in items] == [1, 2, 7]
    assert {p.tier for p in items} == {"gate"}
    assert {p.scope for p in items} == {"universal", "domain"}  # both scopes surfaced


def test_practice_items_absent_registry_is_graceful_empty():
    # An older repo with no practices.json stays valid — empty, not an error.
    assert _sc().practice_items() == ()


def _project_with_profiles():
    p = _project()
    p["practices"] = {"profiles": {"cuda": True, "ai": False, "langgraph": False}}
    return p


def _profiles_registry():
    return {
        "schema_version": 1,
        "profiles": {
            "_comment": "definitions only; enable flags live in project.json",
            "ai": {"tags": ["ai", "llm"], "activates": ["dependency-injection"]},
            "cuda": {"tags": ["cuda", "gpu"], "activates": ["shape-typed-tensors"]},
            "langgraph": {"tags": ["langgraph"], "activates": ["typed-graph-state"]},
        },
    }


def test_domain_profiles_join_definitions_with_enable_flags():
    sc = Showcase(
        name="demoproj",
        project=_project_with_profiles(),
        corpus=_corpus(),
        practices=_profiles_registry(),
        present_scripts=frozenset(),
        served_visibilities=_SERVED,
    )
    profs = sc.domain_profiles()
    assert [p.name for p in profs] == [
        "ai",
        "cuda",
        "langgraph",
    ]  # sorted, _comment skipped
    by = {p.name: p for p in profs}
    assert by["cuda"].enabled is True  # from project.json
    assert by["ai"].enabled is False and by["langgraph"].enabled is False
    assert by["cuda"].tags == ("cuda", "gpu")  # from practices.json
    assert by["cuda"].activates == ("shape-typed-tensors",)


def test_domain_profiles_absent_registry_is_graceful_empty():
    # No practices registry (and no practices.profiles block) -> empty, not error.
    assert _sc().domain_profiles() == ()


def test_doc_tree_groups_by_top_dir():
    groups = {g.directory: g for g in _sc().doc_tree()}
    assert set(groups) == {".", "docs"}
    assert groups["."].docs[0].node_id == "readme"


def test_node_resolves_neighbours():
    detail = _sc().node("readme")
    assert detail is not None
    assert detail.parent is None
    assert [c.node_id for c in detail.children] == ["readme#setup"]
    assert [r.node_id for r in detail.related] == ["guide"]  # link resolved
    assert _sc().node("missing") is None


def test_node_carries_how_its_owner_was_resolved():
    """The wiki page marks a default owner as a placeholder, so the detail
    carries owner_source; a corpus node without one reads as unknown (None),
    never as `none`, the claim that nothing owns it."""
    assert _sc().node("mod-py").owner_source == "default"
    assert _sc().node("guide").owner_source is None


def test_search_ranks_by_overlap():
    hits = _sc().search("AXI", limit=5)
    ids = [h.node.node_id for h in hits]
    assert "guide" in ids and "readme" in ids
    assert all(h.score > 0 for h in hits)
    assert _sc().search("") == ()


def test_llms_index_follows_the_convention():
    txt = _sc().llms_index("https://example.test")
    lines = txt.splitlines()
    assert lines[0].startswith("# ")  # single H1
    assert any(ln.startswith("> ") for ln in lines)  # blockquote summary
    assert "## Root" in txt and "## docs" in txt  # per-directory sections
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

    json.dumps(payload)  # must be JSON-serialisable


# ---- visibility: a node outside the served levels is absent, not redacted ----
_CODEWORD = "CODEWORD-ZEBRA"


def _hidden_corpus():
    """_corpus() plus a confidential doc with a section, a restricted module, a
    node at the corpus's unreadable-readme marker and one with no level; the
    readme names the confidential doc as a child and a link."""
    corpus = _corpus()
    readme = corpus["nodes"][0]
    readme["children"] = ["readme#setup", "secret"]
    readme["links"] = [{"to": "guide"}, {"to": "secret"}]

    def node(node_id, kind, path, visibility, **extra):
        out = {
            "node_id": node_id,
            "kind": kind,
            "title": "Zebra %s" % node_id,
            "path": path,
            "summary": "zebra %s" % _CODEWORD,
            "text_excerpt": _CODEWORD,
            "owner": "carol",
            "tags": ["zebra", "axi"],
            "anchor": None,
            "lineno": None,
            "parent": None,
            "children": [],
            "links": [{"to": "guide"}],
            "visibility": visibility,
        }
        out.update(extra)
        return out

    corpus["nodes"] += [
        node(
            "secret",
            "doc",
            "docs/secret/README.md",
            "confidential",
            parent="readme",
            children=["secret#plan"],
        ),
        node(
            "secret#plan",
            "section",
            "docs/secret/README.md",
            "confidential",
            parent="secret",
            anchor="plan",
            lineno=3,
        ),
        node("vault-py", "module", "src/vault.py", "restricted"),
        node("broken", "doc", "hidden/README.md", "unreadable-readme"),
        node("unstated", "doc", "old/README.md", None),
    ]
    del corpus["nodes"][-1]["visibility"]
    return corpus


_HIDDEN = ("secret", "secret#plan", "vault-py", "broken", "unstated")


def _hidden_sc(tmp_path, served=_SERVED):
    (tmp_path / "docs" / "secret").mkdir(parents=True)
    (tmp_path / "docs" / "secret" / "README.md").write_text(
        "---\nvisibility: confidential\n---\n# Secret\n\n## Plan\n%s\n" % _CODEWORD,
        "utf-8",
    )
    (tmp_path / "README.md").write_text("# Readme\nbody\n", "utf-8")
    return Showcase(
        name="demoproj",
        project=_project(),
        corpus=_hidden_corpus(),
        present_scripts=frozenset(),
        root=str(tmp_path),
        served_visibilities=served,
    )


@pytest.mark.parametrize("node_id", _HIDDEN)
def test_a_hidden_node_answers_as_an_unknown_node(tmp_path, node_id):
    sc = _hidden_sc(tmp_path)
    assert sc.node(node_id) is None
    assert sc.markdown(node_id) == ""


def test_no_listing_count_or_link_names_a_hidden_node(tmp_path):
    sc = _hidden_sc(tmp_path)
    ids = {r.node_id for g in sc.doc_tree() for r in g.docs}
    assert ids == {"readme", "guide"}
    assert {g.directory for g in sc.doc_tree()} == {".", "docs"}
    stats = sc.overview().stats
    assert (stats.docs, stats.sections, stats.modules) == (2, 1, 1)
    readme = sc.node("readme")
    assert [c.node_id for c in readme.children] == ["readme#setup"]
    assert [r.node_id for r in readme.related] == ["guide"]
    assert sc.node("readme#setup").parent.node_id == "readme"
    assert [h.node.node_id for h in sc.search("zebra axi", limit=50)] == [
        "guide",
        "readme",
    ]


def test_no_llms_text_carries_a_hidden_node(tmp_path):
    sc = _hidden_sc(tmp_path)
    full, index = sc.llms_full(), sc.llms_index()
    for text in (full, index):
        assert _CODEWORD not in text and "Zebra" not in text
    assert "# Readme" in full


def test_the_served_levels_are_the_configured_ones(tmp_path):
    """The allowlist is what the caller read from config, not a literal: with
    only `public` served, the internal readme is gone too."""
    sc = _hidden_sc(tmp_path, served=frozenset({"public"}))
    assert sc.node("readme") is None and sc.node("guide") is not None
    assert [r.node_id for g in sc.doc_tree() for r in g.docs] == ["guide"]
    assert sc.node("guide").related == ()


def test_a_showcase_needs_its_served_levels():
    with pytest.raises(TypeError, match="served_visibilities"):
        Showcase(name="x", project={}, corpus=_corpus())  # type: ignore[call-arg]
