"""
title: Unit — query_corpus retrieval (stems and excerpts)
kind: tests
layer: n/a
summary: query_corpus scores a node by query-token overlap, and before this two things made it miss: tokens were compared verbatim, so `idempotency` found nothing while `idempotent` found eight nodes; and only tags, title and summary were read, so a term that lives in the body was invisible. Tokens are now lightly stemmed on both sides and the body excerpt counts, below the title and summary, so a body-only match never outranks a summary match. A node at a level outside config/project.json corpus.served_visibilities, or that states none, is cut before scoring, so it is neither a hit nor a neighbour, and the CLI reads the configured list.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import query_corpus as qc  # noqa: E402

pytestmark = pytest.mark.unit


_SERVED = frozenset({"public", "internal"})


def _node(nid, title="", summary="", excerpt="", tags=(), visibility="internal"):
    return {
        "node_id": nid,
        "title": title,
        "summary": summary,
        "text_excerpt": excerpt,
        "tags": list(tags),
        "parent": None,
        "links": [],
        "visibility": visibility,
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
    assert [n["node_id"] for n in qc.query(corpus, "idempotency", served=_SERVED)] == [
        "a"
    ]


def test_a_body_only_match_counts_but_ranks_below_a_summary_match():
    corpus = {
        "nodes": [
            _node("body", summary="Unrelated.", excerpt="the corpus links nodes"),
            _node("head", summary="How the corpus is linked."),
        ]
    }
    assert [
        n["node_id"] for n in qc.query(corpus, "corpus linking", served=_SERVED)
    ] == [
        "head",
        "body",
    ]


def test_acronyms_still_match_verbatim():
    corpus = {"nodes": [_node("bus", summary="The AXI bus.")]}
    assert [n["node_id"] for n in qc.query(corpus, "AXI", served=_SERVED)] == ["bus"]


# ---- visibility: a node outside corpus.served_visibilities is absent ---------


def _hidden_corpus():
    secret = _node("secret", summary="The zebra plan.", visibility="confidential")
    unstated = _node("unstated", summary="A zebra note.")
    del unstated["visibility"]
    marker = _node("marker", summary="Zebra marker.", visibility="unreadable-readme")
    hub = _node("hub", summary="The zebra hub.")
    # The hub links every hidden node and is the parent of one, so the
    # neighbour expansion would reach them if the cut came after scoring.
    hub["links"] = [{"to": "secret"}, {"to": "unstated"}, {"to": "marker"}]
    secret["parent"] = "hub"
    return {"nodes": [hub, secret, unstated, marker]}


def test_a_node_outside_the_served_levels_is_neither_a_hit_nor_a_neighbour():
    hits = qc.query(_hidden_corpus(), "zebra plan", served=_SERVED)
    assert [n["node_id"] for n in hits] == ["hub"]


def test_the_served_levels_decide_which_nodes_are_retrieved():
    hits = qc.query(_hidden_corpus(), "zebra plan", served=frozenset({"confidential"}))
    assert [n["node_id"] for n in hits] == ["secret"]


def test_main_prints_only_the_configured_levels(tmp_path, monkeypatch, capsys):
    """The CLI the agents call reads `corpus.served_visibilities` from the
    repository it serves; with `["public"]` there an internal hit goes too."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"corpus": {"served_visibilities": ["public"]}}), encoding="utf-8"
    )
    corpus = _hidden_corpus()
    corpus["nodes"].append(_node("open", summary="Zebra open.", visibility="public"))
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    monkeypatch.setattr(qc, "ROOT", str(tmp_path))
    assert qc.main(["zebra", "--corpus", str(path)]) is qc.ExitCode.SUCCESS
    assert [n["node_id"] for n in json.loads(capsys.readouterr().out)] == ["open"]


def test_main_refuses_a_level_outside_the_vocabulary(tmp_path, monkeypatch, capsys):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"corpus": {"served_visibilities": ["unreadable-readme"]}}),
        encoding="utf-8",
    )
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(_hidden_corpus()), encoding="utf-8")
    monkeypatch.setattr(qc, "ROOT", str(tmp_path))
    assert qc.main(["zebra", "--corpus", str(path)]) is qc.ExitCode.CONFIG
    captured = capsys.readouterr()
    assert captured.out == "" and "corpus.served_visibilities" in captured.err
