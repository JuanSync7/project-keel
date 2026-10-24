"""
title: E2E — showcase visitor journey
kind: tests
layer: n/a
summary: A visitor walks the whole showcase surface over a real socket - every page payload, every curated link into the live corpus, the owner source each node payload names, a search, and the llms.txt files - against the REST server running as its own process.
"""

import re
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

# The showcase read model reads wiki/corpus.json, a GENERATED view that a
# fresh clone and a freshly generated project do not have. Declared as a
# fixture rather than assumed: these tests used to fail on arrival in a new
# project (9 of them) while its README said to run `make verify`. The
# `rest_server` fixture depends on it.
pytestmark = [pytest.mark.e2e]

_ROOT = Path(__file__).resolve().parents[2]

# Every backend payload a visitor's session loads as they walk the nav.
PAGE_FEEDS = (
    "/api/features",  # Conventions/Features/Checks/Setup are list endpoints
    "/api/principles",
    "/api/models",  # the Architecture page's live model-adapter list
    "/api/practices",  # the Architecture page's live coding-practices list
    "/api/profiles",  # the Architecture page's live domain-profiles list
    "/api/checks",
    "/api/setup",
    "/api/wiki/tree",
)
# /api/search's `limit` is bounded at 50 by the route; one past it is refused.
_SEARCH_LIMIT = 50
# A word as search tokenizes one (a letter, then letters, digits or `_`), at
# least four long so it is not a stop-word-like fragment.
_WORD = re.compile(r"[a-z][a-z0-9_]{3,}")


@pytest.mark.endpoint("rest GET /api/overview")
@pytest.mark.endpoint("rest GET /api/features")
@pytest.mark.endpoint("rest GET /api/principles")
@pytest.mark.endpoint("rest GET /api/models")
@pytest.mark.endpoint("rest GET /api/practices")
@pytest.mark.endpoint("rest GET /api/profiles")
@pytest.mark.endpoint("rest GET /api/checks")
@pytest.mark.endpoint("rest GET /api/setup")
@pytest.mark.endpoint("rest GET /api/wiki/tree")
def test_visitor_loads_every_page_payload(rest_server):
    status, overview = rest_server.json("GET", "/api/overview")
    assert status == 200
    assert overview["stats"]["docs"] > 0
    for feed in PAGE_FEEDS:
        status, body = rest_server.json("GET", feed)
        assert status == 200, feed
        assert body, "%s should be non-empty" % feed


@pytest.mark.endpoint("rest GET /api/features")
@pytest.mark.endpoint("rest GET /api/principles")
@pytest.mark.endpoint("rest GET /api/wiki/node")
def test_curated_links_resolve_into_the_corpus(rest_server):
    """Click-through guarantee: every 'read the rule →' link lands on a real node.

    Features and conventions both link out to corpus nodes; a dead link would
    strand the visitor. Asserting the general invariant (not specific ids) keeps
    the curated content honest against the live corpus as either side changes.
    """
    hrefs = sorted(
        {
            link["href"]
            for feed in ("/api/features", "/api/principles")
            for item in rest_server.json("GET", feed)[1]
            for link in item["links"]
        }
    )
    assert hrefs, "there should be curated links to verify"
    dead = [
        h
        for h in hrefs
        if rest_server.request("GET", "/api/wiki/node?id=" + _quote(h))[0] != 200
    ]
    assert not dead, "dead curated links (no such corpus node): %s" % dead


@pytest.mark.endpoint("rest GET /api/features")
@pytest.mark.endpoint("rest GET /api/wiki/node")
def test_a_wiki_node_says_how_its_owner_was_resolved(rest_server):
    """The node page's owner chip reads owner_source off the payload: the live
    corpus names one of CONVENTIONS §12's sources for every node it writes, and
    a payload's null, unknown, would mean the corpus row lost it."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    import check_corpus as cc

    hrefs = sorted(
        {
            link["href"]
            for item in rest_server.json("GET", "/api/features")[1]
            for link in item["links"]
        }
    )
    assert hrefs, "there should be curated links to open"
    sources = {}
    for h in hrefs:
        status, node = rest_server.json("GET", "/api/wiki/node?id=" + _quote(h))
        assert status == 200, h
        sources[h] = node["owner_source"]
    off = {h: s for h, s in sources.items() if s not in cc.OWNER_SOURCES}
    assert not off, "nodes whose payload names no CONVENTIONS §12 source: %s" % off


def _quote(value):
    return quote(value, safe="")


def _haystack(rest_server, node_id):
    status, node = rest_server.json("GET", "/api/wiki/node?id=" + _quote(node_id))
    assert status == 200, node_id
    return " ".join([node["title"], node["summary"], *node["tags"]]).lower()


def _first_term_with_a_page_of_hits(rest_server, candidates):
    for term, source in candidates:
        status, hits = rest_server.json(
            "GET", "/api/search?q=%s&limit=%d" % (term, _SEARCH_LIMIT)
        )
        assert status == 200, term
        if len(hits) < _SEARCH_LIMIT:
            return term, source, hits
    pytest.fail("every doc-title word filled a page of %d hits" % _SEARCH_LIMIT)
    return None  # unreachable: pytest.fail raises


@pytest.mark.endpoint("rest GET /api/search")
@pytest.mark.endpoint("rest GET /api/wiki/tree")
@pytest.mark.endpoint("rest GET /api/wiki/node")
def test_search_finds_a_corpus_term_and_refuses_an_unbounded_limit(rest_server):
    """A word taken from a doc title finds that doc, and every hit carries the
    word in its title, summary or tags - the fields search ranks on."""
    _status, tree = rest_server.json("GET", "/api/wiki/tree")
    docs = [doc for group in tree for doc in group["docs"]]
    # The longest title words first: a rare word keeps its source doc inside
    # one page of hits, so "the source is found" is a real claim.
    candidates = sorted(
        {
            (word, doc["node_id"])
            for doc in docs
            for word in _WORD.findall(doc["title"].lower())
        },
        key=lambda pair: (-len(pair[0]), pair),
    )
    assert candidates, "the corpus should have a doc title with a word to search"
    term, source, hits = _first_term_with_a_page_of_hits(rest_server, candidates)
    assert hits, term
    assert source in {hit["node"]["node_id"] for hit in hits}, (term, source)
    for hit in hits:
        assert term in _haystack(rest_server, hit["node"]["node_id"]), (term, hit)

    status, _headers, _body = rest_server.request(
        "GET", "/api/search?q=%s&limit=%d" % (term, _SEARCH_LIMIT + 1)
    )
    assert status == 422


@pytest.mark.endpoint("rest GET /llms.txt")
@pytest.mark.endpoint("rest GET /llms-full.txt")
@pytest.mark.endpoint("rest GET /api/overview")
def test_llms_files_open_with_the_project_title(rest_server):
    _status, overview = rest_server.json("GET", "/api/overview")
    title = overview["title"]
    assert title
    for path in ("/llms.txt", "/llms-full.txt"):
        status, headers, body = rest_server.request("GET", path)
        assert status == 200, path
        content_type = {k.lower(): v for k, v in headers.items()}["content-type"]
        assert content_type.startswith("text/markdown"), (path, content_type)
        text = body.decode("utf-8")
        assert text.startswith("# " + title), (path, text[:80])
        assert len(text.splitlines()) > 1, path
