"""
title: Integration — showcase REST API
kind: tests
layer: backend
summary: The FastAPI showcase router serves overview/features/checks/wiki/search over the live repo. Over a scratch project it serves no node outside corpus.served_visibilities, and a config the loader refuses answers 500 on every request, including one that replaces a config whose model was already loaded, so that model is never reused; a document reclassified on disk after the corpus was built, or made unreadable, is answered as unknown by the node route and its body is on no route, though the router's cached model answers.
"""

import json
import sys
from pathlib import Path

import pytest

import optional_deps
import reclassify

optional_deps.importorskip("fastapi", extra="transport")  # optional transport dep
optional_deps.importorskip("httpx", extra="dev")  # backs FastAPI's TestClient

from fastapi.testclient import TestClient  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "api" / "rest_fastapi"))

from app import app  # noqa: E402

# The showcase read model reads wiki/corpus.json, a GENERATED view that a
# fresh clone and a freshly generated project do not have. Declared as a
# fixture rather than assumed: these tests used to fail on arrival in a new
# project (9 of them) while its README said to run `make verify`.
pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("real_corpus")]

client = TestClient(app)


def test_overview_is_live():
    r = client.get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] and body["stats"]["docs"] > 0
    assert {layer["name"] for layer in body["layers"]} >= {"backend"}


def test_features_and_checks_listed():
    feats = client.get("/api/features").json()
    assert any(f["slug"] == "deterministic-checks" for f in feats)
    checks = client.get("/api/checks").json()
    assert {c["slug"] for c in checks} >= {"structure", "corpus"}
    assert all(c["present"] for c in checks)  # scripts exist in this repo


def test_principles_listed():
    principles = client.get("/api/principles").json()
    assert principles, "principles should be served"
    assert "agent-rules" in {p["slug"] for p in principles}
    assert all(p["title"] and p["essence"] and p["detail"] for p in principles)


def test_models_listed_from_the_manifest():
    models = client.get("/api/models").json()
    by_name = {m["name"]: m for m in models}
    assert {"claude-code-headless", "openai-compatible", "fake"} <= set(by_name)
    assert by_name["claude-code-headless"]["default"] is True
    assert [m["name"] for m in models if m["default"]] == ["claude-code-headless"]


def test_practices_listed_from_the_registry():
    practices = client.get("/api/practices").json()
    assert practices, "practices should be listed from config/practices.json"
    assert {p["tier"] for p in practices} >= {"gate", "advisory"}  # both tiers present
    assert all(p["tier"] in ("gate", "advisory", "doc") for p in practices)
    assert all(p["scope"] in ("universal", "domain") for p in practices)
    rows = [p["row"] for p in practices]
    assert rows == sorted(rows), "practices are returned sorted by row"
    # The owned-exception gate we shipped (check_J) is surfaced and enabled.
    by_id = {p["id"]: p for p in practices}
    assert by_id["owned-exception-boundary"]["status"] == "on"


def test_domain_profiles_listed_and_enabled_flags_mirror_the_manifest():
    """Every profile defined in practices.json is listed, and each `enabled` flag
    agrees with `config/project.json`.

    This asserted `all(p["enabled"] is False ...)` — keel's own answer, pasted in.
    A project that enabled a profile (the question the template asks) served a
    correct payload and failed this test anyway. The property that holds for
    every answer is that the API mirrors the manifest."""
    profiles = client.get("/api/profiles").json()
    assert profiles, "domain profiles should be listed from config/practices.json"
    names = [p["name"] for p in profiles]
    assert names == sorted(names)  # stable order
    assert {"ai", "cuda", "langgraph"} <= set(names)

    with open(str(_ROOT / "config" / "project.json"), encoding="utf-8") as fh:
        declared = (json.load(fh).get("practices") or {}).get("profiles") or {}
    for profile in profiles:
        assert profile["enabled"] is (declared.get(profile["name"]) is True), (
            "/api/profiles reports %s enabled=%s while config/project.json says %r"
            % (profile["name"], profile["enabled"], declared.get(profile["name"]))
        )
    cuda = next(p for p in profiles if p["name"] == "cuda")
    assert "shape-typed-tensors" in cuda["activates"]  # definition joined in


def test_every_feature_link_resolves_into_the_corpus():
    """Click-through guarantee: each feature's 'read more' link is a real node,
    so the new edge-adapters card (and every other) never strands the visitor."""
    feats = client.get("/api/features").json()
    hrefs = sorted({ln["href"] for f in feats for ln in f["links"]})
    assert "mcp-readme" in hrefs and "models-readme" in hrefs  # the new card's links
    dead = [
        h
        for h in hrefs
        if client.get("/api/wiki/node", params={"id": h}).status_code != 200
    ]
    assert not dead, "dead feature links (no such corpus node): %s" % dead


def _owner_tree(root):
    """A scratch tree whose corpus holds every CONVENTIONS §12 owner source:
    a README's own owner (frontmatter) and its sections (inherited), a section
    marker (marker), a TBD document under a configured default (default), and
    a document nothing owns (none)."""
    files = {
        "config/project.json": json.dumps(
            {"accountability": {"default_owner": "platform-team"}}
        ),
        "docs/README.md": _md("docs-readme", "alice", "## Part\n\ntext\n"),
        "docs/plan.md": _md("plan", "TBD", "## Owned\n\n<!-- owner: bob -->\n\ntext\n"),
        "notes.md": _md("notes", None, "## Loose\n\ntext\n"),
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _md(doc_id, owner, body):
    head = "---\ntitle: %s\nkind: guide\nsummary: About %s.\nid: %s\n" % (
        doc_id,
        doc_id,
        doc_id,
    )
    if owner is not None:
        head += "owner: %s\n" % owner
    return head + "---\n# %s\n\n%s" % (doc_id, body)


def _scratch_client(root, nodes):
    from fastapi import FastAPI
    from showcase_api import build_showcase_router

    (root / "wiki").mkdir(exist_ok=True)
    (root / "wiki" / "corpus.json").write_text(
        json.dumps({"schema_version": 1, "nodes": nodes}), encoding="utf-8"
    )
    scratch = FastAPI()
    scratch.include_router(build_showcase_router(str(root)))
    return TestClient(scratch)


def test_wiki_node_says_how_its_owner_was_resolved(tmp_path):
    """The wiki marks a default owner as a placeholder only if the node payload
    carries the corpus row's owner_source unchanged. The corpus is built here,
    in scratch, so every source is present: the gitignored repo corpus may
    hold no `default` node, and a test over it would then prove nothing."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    import build_corpus as bc
    import check_corpus as cc

    _owner_tree(tmp_path)
    nodes = bc.build_corpus(str(tmp_path))["nodes"]
    first = {}
    for node in sorted(nodes, key=lambda n: n["node_id"]):
        first.setdefault(node["owner_source"], node["node_id"])
    # Every member of the closed set, or a source the payload drops goes unseen.
    assert set(first) == cc.OWNER_SOURCES, sorted(first)
    scratch = _scratch_client(tmp_path, nodes)
    for source, node_id in sorted(first.items()):
        detail = scratch.get("/api/wiki/node", params={"id": node_id}).json()
        assert detail["owner_source"] == source, node_id


@pytest.mark.parametrize("stored", ["absent", None, ""])
def test_a_node_with_no_owner_source_reads_as_unknown_not_none(tmp_path, stored):
    """A corpus row that carries no owner_source, such as one written before
    the field existed, says nothing about its owner: the payload is null, not
    `none`, the claim that nothing owns the node."""
    _owner_tree(tmp_path)
    node = {
        "node_id": "old",
        "kind": "doc",
        "title": "Old",
        "path": "notes.md",
        "summary": "An old row.",
        "owner": "alice",
        "children": [],
        "links": [],
        "visibility": "internal",
    }
    if stored != "absent":
        node["owner_source"] = stored
    detail = (
        _scratch_client(tmp_path, [node])
        .get("/api/wiki/node", params={"id": "old"})
        .json()
    )
    assert detail["owner_source"] is None, detail


def test_wiki_tree_node_and_404():
    tree = client.get("/api/wiki/tree").json()
    assert tree, "corpus should be built for this test"
    node_id = tree[0]["docs"][0]["node_id"]
    detail = client.get("/api/wiki/node", params={"id": node_id})
    assert detail.status_code == 200 and detail.json()["node_id"] == node_id
    assert isinstance(detail.json()["markdown"], str)  # renderable body included
    assert (
        client.get("/api/wiki/node", params={"id": "no-such-node"}).status_code == 404
    )


def test_search_finds_conventions():
    hits = client.get("/api/search", params={"q": "conventions frontmatter"}).json()
    assert hits
    assert any("conventions" in h["node"]["node_id"] for h in hits)


def test_search_validates_limit():
    assert client.get("/api/search", params={"q": "x", "limit": 0}).status_code == 422


def test_llms_txt_is_served_at_root():
    r = client.get("/llms.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    body = r.text
    assert body.startswith("# ")  # H1
    assert "## Optional" in body and "/llms-full.txt" in body


def test_llms_full_txt_inlines_documents():
    r = client.get("/llms-full.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    # full text inlines doc bodies (markdown headings present, not just links)
    assert "— full text" in r.text
    assert r.text.count("## ") >= 2


# ---- visibility: a node outside corpus.served_visibilities is absent ---------
_CODEWORD = "CODEWORD-ZEBRA"


def _visibility_tree(root, served=None):
    """A scratch project: an open doc, a confidential `docs/secret/README.md`
    whose body is the codeword, and a config that sets
    `corpus.served_visibilities` to *served* (absent, the default, when None)."""
    config = {} if served is None else {"corpus": {"served_visibilities": served}}
    files = {
        "config/project.json": json.dumps(config),
        "docs/open.md": _md("open", "alice", "## Open part\n\nzebra text\n"),
        "docs/secret/README.md": _md(
            "secret", "alice", "## Zebra plan\n\n%s\n" % _CODEWORD
        ).replace("---\n#", "visibility: confidential\n---\n#", 1),
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    import build_corpus as bc

    nodes = bc.build_corpus(str(root))["nodes"]
    hidden = sorted(n["node_id"] for n in nodes if n["visibility"] == "confidential")
    assert hidden, "the scratch corpus must hold a confidential node"
    return nodes, hidden


def _every_answer(scratch, ids):
    """The text of every showcase route a visitor or agent can reach."""
    pages = ["/api/overview", "/api/wiki/tree", "/llms.txt", "/llms-full.txt"]
    pages += ["/api/search?q=zebra+plan+secret&limit=50"]
    pages += ["/api/wiki/node?id=%s" % i for i in ids]
    return {page: scratch.get(page) for page in pages}


def test_a_confidential_node_reaches_no_showcase_route(tmp_path):
    nodes, hidden = _visibility_tree(tmp_path)
    scratch = _scratch_client(tmp_path, nodes)
    for node_id in hidden:
        r = scratch.get("/api/wiki/node", params={"id": node_id})
        assert r.status_code == 404, node_id
        assert r.json() == {"detail": "unknown node %r" % node_id}
    for page, r in _every_answer(scratch, [n["node_id"] for n in nodes]).items():
        assert _CODEWORD not in r.text, page
        # A request for a hidden id is answered as unknown, echoing the id asked.
        if not page.startswith("/api/wiki/node"):
            for node_id in hidden:
                assert node_id not in r.text, (page, node_id)
    assert scratch.get("/api/overview").json()["stats"]["docs"] == 1


def test_the_router_serves_the_configured_levels(tmp_path):
    """With `corpus.served_visibilities` set to `["public"]`, the internal doc
    goes too, so the router reads the key rather than a literal of its own."""
    nodes, _hidden = _visibility_tree(tmp_path, served=["public"])
    scratch = _scratch_client(tmp_path, nodes)
    assert scratch.get("/api/wiki/tree").json() == []
    assert scratch.get("/api/wiki/node", params={"id": "open"}).status_code == 404


def test_a_refused_served_level_serves_nothing(tmp_path):
    """A level outside the vocabulary is a config fault, and the router
    answers an error rather than guess which nodes to serve."""
    nodes, _hidden = _visibility_tree(tmp_path, served=["unreadable-readme"])
    from fastapi import FastAPI
    from showcase_api import build_showcase_router

    (tmp_path / "wiki").mkdir(exist_ok=True)
    (tmp_path / "wiki" / "corpus.json").write_text(
        json.dumps({"schema_version": 1, "nodes": nodes}), encoding="utf-8"
    )
    scratch = FastAPI()
    scratch.include_router(build_showcase_router(str(tmp_path)))
    r = TestClient(scratch, raise_server_exceptions=False).get("/llms-full.txt")
    assert r.status_code == 500 and _CODEWORD not in r.text


def test_a_refused_config_after_a_served_one_leaves_no_model_to_reuse(tmp_path):
    """The router caches its model by the watched files' mtimes. A config
    that serves the confidential doc loads, then one the loader refuses
    replaces it: every request after answers 500, the second one included,
    so the model loaded under the earlier config is never reused."""
    import os

    from fastapi import FastAPI
    from showcase_api import build_showcase_router

    every = ["public", "internal", "confidential", "restricted"]
    nodes, _hidden = _visibility_tree(tmp_path, served=every)
    (tmp_path / "wiki").mkdir(exist_ok=True)
    (tmp_path / "wiki" / "corpus.json").write_text(
        json.dumps({"schema_version": 1, "nodes": nodes}), encoding="utf-8"
    )
    scratch = FastAPI()
    scratch.include_router(build_showcase_router(str(tmp_path)))
    client = TestClient(scratch, raise_server_exceptions=False)
    first = client.get("/llms-full.txt")
    # The earlier model holds the codeword, so reusing it would serve it.
    assert first.status_code == 200 and _CODEWORD in first.text
    config = tmp_path / "config" / "project.json"
    config.write_text(
        json.dumps({"corpus": {"served_visibilities": ["unreadable-readme"]}}),
        encoding="utf-8",
    )
    later = os.path.getmtime(config) + 10
    os.utime(config, (later, later))
    for _ in range(2):
        r = client.get("/llms-full.txt")
        assert r.status_code == 500 and _CODEWORD not in r.text


@pytest.mark.parametrize("how", reclassify.HOWS)
def test_a_doc_reclassified_after_the_build_is_not_served(tmp_path, how):
    """The corpus says `docs/pubguide.md` is public; the file then states a
    stricter level, or none that can be read. The node route answers it as
    unknown and no route carries its body, though the model the router
    cached before the change is the one answering: the level is asked of the
    file on every read."""
    nodes = reclassify.public_project(tmp_path, _CODEWORD)
    ids = sorted(n["node_id"] for n in nodes if n["path"] == reclassify.GUIDE)
    assert "pubguide" in ids
    scratch = _scratch_client(tmp_path, nodes)
    before = scratch.get("/api/wiki/node", params={"id": "pubguide"})
    assert before.status_code == 200 and _CODEWORD in before.json()["markdown"]
    reclassify.reclassify(tmp_path / reclassify.GUIDE, how)
    for node_id in ids:
        r = scratch.get("/api/wiki/node", params={"id": node_id})
        assert r.status_code == 404, node_id
    for page in ("/llms-full.txt", "/llms.txt"):
        assert _CODEWORD not in scratch.get(page).text, page
