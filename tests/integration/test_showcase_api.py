"""
title: Integration — showcase REST API
kind: tests
layer: backend
summary: The FastAPI showcase router serves overview/features/checks/wiki/search over the live repo.
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # optional transport dep — skip this module when absent
pytest.importorskip("httpx")    # backs starlette/FastAPI TestClient

from fastapi.testclient import TestClient  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "api" / "rest_fastapi"))

from app import app  # noqa: E402

pytestmark = pytest.mark.integration

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
    assert {c["slug"] for c in checks} >= {"structure", "scaffold-sync", "corpus"}
    assert all(c["present"] for c in checks)   # scripts exist in this repo


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


def test_every_feature_link_resolves_into_the_corpus():
    """Click-through guarantee: each feature's 'read more' link is a real node,
    so the new edge-adapters card (and every other) never strands the visitor."""
    feats = client.get("/api/features").json()
    hrefs = sorted({ln["href"] for f in feats for ln in f["links"]})
    assert "mcp-readme" in hrefs and "models-readme" in hrefs   # the new card's links
    dead = [h for h in hrefs
            if client.get("/api/wiki/node", params={"id": h}).status_code != 200]
    assert not dead, "dead feature links (no such corpus node): %s" % dead


def test_wiki_tree_node_and_404():
    tree = client.get("/api/wiki/tree").json()
    assert tree, "corpus should be built for this test"
    node_id = tree[0]["docs"][0]["node_id"]
    detail = client.get("/api/wiki/node", params={"id": node_id})
    assert detail.status_code == 200 and detail.json()["node_id"] == node_id
    assert isinstance(detail.json()["markdown"], str)   # renderable body included
    assert client.get("/api/wiki/node", params={"id": "no-such-node"}).status_code == 404


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
    assert body.startswith("# ")                 # H1
    assert "## Optional" in body and "/llms-full.txt" in body


def test_llms_full_txt_inlines_documents():
    r = client.get("/llms-full.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    # full text inlines doc bodies (markdown headings present, not just links)
    assert "— full text" in r.text
    assert r.text.count("## ") >= 2
