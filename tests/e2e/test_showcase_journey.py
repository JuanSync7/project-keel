"""
title: E2E — showcase visitor journey
kind: tests
layer: n/a
summary: A visitor walks the whole showcase surface over a real socket - every page payload, every curated link into the live corpus, the owner source each node payload names, a search, and the llms.txt files - against the REST server running as its own process; and a confidential node in a scratch corpus built by the real build_corpus and link_corpus, which an internal doc links to, absent from every route of a real server over it and from every file of the static export: no served page, node detail, search or llms file names its id or its title.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from scripts.child_env import build_child_env

import live_server
import optional_deps

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


# ---- a confidential node reaches no reader the project serves ---------------
_CODEWORD = "CODEWORD-ZEBRA"
_SCRATCH_APP = """
import sys
sys.path.insert(0, {src!r})
sys.path.insert(0, {rest!r})
from fastapi import FastAPI
from showcase_api import build_showcase_router

app = FastAPI()


@app.get("/health")
def health():
    return {{"status": "ok"}}


app.include_router(build_showcase_router({root!r}))
"""


def _doc(doc_id, body, visibility=None, title=None):
    title = title or doc_id
    head = "---\ntitle: %s\nkind: doc\nsummary: About %s.\nid: %s\nowner: alice\n" % (
        title,
        title,
        doc_id,
    )
    if visibility is not None:
        head += "visibility: %s\n" % visibility
    return head + "---\n# %s\n\n## Zebra part\n\n%s\n" % (title, body)


# The confidential doc's id and title: no served page may name either. The
# id is not "secret" because the open doc's link text names its path.
_HIDDEN_ID, _HIDDEN_TITLE = "hush-plan", "Hush plan"


def _confidential_project(root):
    """A scratch project whose corpus, built by the real build_corpus and
    link_corpus, holds an internal doc that links to a confidential README
    whose body is the codeword; returns the confidential node ids."""
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    import build_corpus
    import link_corpus

    files = {
        "config/project.json": "{}",
        "docs/open.md": _doc(
            "open", "zebra text, and [the zebra plan](secret/README.md)"
        ),
        "docs/secret/README.md": _doc(
            _HIDDEN_ID, _CODEWORD, "confidential", title=_HIDDEN_TITLE
        ),
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    nodes = link_corpus.link_corpus(build_corpus.build_corpus(str(root)))["nodes"]
    (root / "wiki").mkdir()
    (root / "wiki" / "corpus.json").write_text(
        json.dumps({"schema_version": 1, "nodes": nodes}), encoding="utf-8"
    )
    hidden = sorted(n["node_id"] for n in nodes if n["visibility"] == "confidential")
    assert _HIDDEN_ID in hidden, "the scratch corpus must hold the confidential doc"
    # The leak's shape is only tested if a served node's link names a hidden one.
    assert any(
        e["to"] in hidden
        for n in nodes
        if n["visibility"] != "confidential"
        for e in n.get("links", [])
    ), "the open doc must link to the confidential one"
    return hidden


def _names_hidden(text, hidden):
    """The hidden ids and the hidden title that *text* names."""
    named = [node_id for node_id in hidden if node_id in text]
    return named + ([_HIDDEN_TITLE] if _HIDDEN_TITLE.lower() in text.lower() else [])


@pytest.mark.endpoint("rest GET /api/overview")
@pytest.mark.endpoint("rest GET /api/wiki/tree")
@pytest.mark.endpoint("rest GET /api/wiki/node")
@pytest.mark.endpoint("rest GET /api/search")
@pytest.mark.endpoint("rest GET /llms.txt")
@pytest.mark.endpoint("rest GET /llms-full.txt")
def test_a_confidential_node_reaches_neither_the_server_nor_the_static_site(tmp_path):
    """The default `corpus.served_visibilities` serves public and internal
    nodes. A confidential README that an internal doc links to is absent from
    every route of a real server over that corpus: no served page, node
    detail, search or llms file names its id or its title, a request for it
    is an unknown node, and the static export that make site-static
    publishes holds it in no file."""
    optional_deps.importorskip("uvicorn", extra="transport")
    optional_deps.importorskip("fastapi", extra="transport")
    project = tmp_path / "project"
    hidden = _confidential_project(project)
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "scratch_showcase_app.py").write_text(
        _SCRATCH_APP.format(
            src=str(_ROOT / "src"),
            rest=str(live_server.rest_dir(str(_ROOT))),
            root=str(project),
        ),
        encoding="utf-8",
    )
    pages = ["/api/overview", "/api/wiki/tree", "/llms.txt", "/llms-full.txt"]
    pages += ["/api/search?q=zebra+secret+hush+plan&limit=%d" % _SEARCH_LIMIT]
    with live_server.live_server(
        str(_ROOT), str(app_dir), app="scratch_showcase_app:app"
    ) as server:
        status, body = server.json("GET", "/api/wiki/node?id=open")
        assert status == 200 and "zebra text" in body["markdown"]
        corpus = json.loads((project / "wiki" / "corpus.json").read_text("utf-8"))
        served = sorted(
            n["node_id"] for n in corpus["nodes"] if n["node_id"] not in hidden
        )
        assert "open" in served
        pages += ["/api/wiki/node?id=%s" % quote(node_id) for node_id in served]
        for node_id in hidden:
            status, body = server.json("GET", "/api/wiki/node?id=%s" % quote(node_id))
            assert status == 404 and body == {"detail": "unknown node %r" % node_id}
        for page in pages:
            status, _headers, raw = server.request("GET", page)
            text = raw.decode("utf-8")
            assert status == 200, page
            assert _CODEWORD not in text and "docs/secret" not in text, page
            assert _names_hidden(text, hidden) == [], page

    site = tmp_path / "site"
    export = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "scripts" / "jobs" / "export_showcase_static.py"),
            "--root",
            str(project),
            "--out-dir",
            str(site),
        ],
        cwd=str(_ROOT),
        env=build_child_env(root=str(_ROOT)),
        capture_output=True,
        text=True,
    )
    assert export.returncode == 0, export.stderr
    written = sorted(p for p in site.rglob("*") if p.is_file())
    assert written, "the export wrote nothing"
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert _CODEWORD not in text and _names_hidden(text, hidden) == [], path
    nodes = json.loads((site / "api" / "wiki" / "nodes.json").read_text("utf-8"))
    assert "open" in nodes and not set(hidden) & set(nodes)
