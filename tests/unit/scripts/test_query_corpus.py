"""
title: Unit — query_corpus retrieval (stems and excerpts)
kind: tests
layer: n/a
summary: query_corpus scores a node by query-token overlap, and before this two things made it miss: tokens were compared verbatim, so `idempotency` found nothing while `idempotent` found eight nodes; and only tags, title and summary were read, so a term that lives in the body was invisible. Tokens are now lightly stemmed on both sides and the body excerpt counts, below the title and summary, so a body-only match never outranks a summary match.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import query_corpus as qc  # noqa: E402

pytestmark = pytest.mark.unit


def _node(nid, title="", summary="", excerpt="", tags=()):
    return {
        "node_id": nid,
        "title": title,
        "summary": summary,
        "text_excerpt": excerpt,
        "tags": list(tags),
        "parent": None,
        "links": [],
    }


@pytest.mark.parametrize(
    "a, b",
    [
        ("idempotency", "idempotent"),
        ("sections", "section"),
        ("processes", "process"),
        ("linking", "links"),
        ("conventions", "convention"),
    ],
)
def test_inflections_of_one_word_stem_alike(a, b):
    assert qc._stem(a) == qc._stem(b)


def test_short_words_are_left_alone():
    assert qc._stem("is") == "is" and qc._stem("axi") == "axi"


def test_a_query_finds_a_node_that_uses_another_inflection():
    corpus = {
        "nodes": [
            _node("a", summary="Deterministic and idempotent."),
            _node("b", summary="Other."),
        ]
    }
    assert [n["node_id"] for n in qc.query(corpus, "idempotency")] == ["a"]


def test_a_body_only_match_counts_but_ranks_below_a_summary_match():
    corpus = {
        "nodes": [
            _node("body", summary="Unrelated.", excerpt="the corpus links nodes"),
            _node("head", summary="How the corpus is linked."),
        ]
    }
    assert [n["node_id"] for n in qc.query(corpus, "corpus linking")] == [
        "head",
        "body",
    ]


def test_acronyms_still_match_verbatim():
    corpus = {"nodes": [_node("bus", summary="The AXI bus.")]}
    assert [n["node_id"] for n in qc.query(corpus, "AXI")] == ["bus"]
