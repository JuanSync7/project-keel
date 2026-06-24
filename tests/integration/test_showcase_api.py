"""
title: Integration — showcase REST API
kind: tests
layer: backend
summary: The FastAPI showcase router serves overview/features/checks/wiki/search over the live repo.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
