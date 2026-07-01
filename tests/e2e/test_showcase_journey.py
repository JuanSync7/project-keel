"""
title: E2E — showcase visitor journey
kind: tests
layer: n/a
summary: A visitor walks the whole showcase surface and every curated link resolves into the live corpus.
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # optional transport dep — skip when absent
pytest.importorskip("httpx")    # backs the FastAPI TestClient

from fastapi.testclient import TestClient  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "api" / "rest_fastapi"))

from app import app  # noqa: E402

pytestmark = pytest.mark.e2e

client = TestClient(app)

# Every backend payload a visitor's session loads as they walk the nav.
PAGE_FEEDS = (
    "/api/features",     # Conventions/Features/Checks/Setup are list endpoints
    "/api/principles",
    "/api/models",       # the Architecture page's live model-adapter list
    "/api/checks",
    "/api/setup",
    "/api/wiki/tree",
)


def test_visitor_loads_every_page_payload():
    overview = client.get("/api/overview")
    assert overview.status_code == 200
    assert overview.json()["stats"]["docs"] > 0
    for feed in PAGE_FEEDS:
        r = client.get(feed)
        assert r.status_code == 200, feed
        assert r.json(), "%s should be non-empty" % feed


def test_curated_links_resolve_into_the_corpus():
    """Click-through guarantee: every 'read the rule →' link lands on a real node.

    Features and conventions both link out to corpus nodes; a dead link would
    strand the visitor. Asserting the general invariant (not specific ids) keeps
    the curated content honest against the live corpus as either side changes.
    """
    hrefs = sorted({
        link["href"]
        for feed in ("/api/features", "/api/principles")
        for item in client.get(feed).json()
        for link in item["links"]
    })
    assert hrefs, "there should be curated links to verify"
    dead = [h for h in hrefs
            if client.get("/api/wiki/node", params={"id": h}).status_code != 200]
    assert not dead, "dead curated links (no such corpus node): %s" % dead
