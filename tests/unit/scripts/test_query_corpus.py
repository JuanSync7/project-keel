"""
title: Unit — query_corpus retrieval (stems and excerpts)
kind: tests
layer: n/a
summary: query_corpus scores a node by query-token overlap, and before this two things made it miss: tokens were compared verbatim, so `idempotency` found nothing while `idempotent` found eight nodes; and only tags, title and summary were read, so a term that lives in the body was invisible. Tokens are now lightly stemmed on both sides and the body excerpt counts, below the title and summary, so a body-only match never outranks a summary match. A node at a level outside config/project.json corpus.served_visibilities, or that states none, is cut before scoring, so it is neither a hit nor a neighbour, and the CLI reads the configured list. A served node the CLI prints names no hidden node in its links, children or parent: a public doc linking to a confidential one, built by the real build_corpus and link_corpus, prints neither the confidential doc's id nor its title. A node whose file under `--root` now states a stricter level is not printed either: in the reviewer's repro, `docs/pubguide.md` reclassified after the build in each of tests/reclassify.py's ways, neither its node nor its id in a served doc's links is printed, and stderr counts the withheld nodes, never a node the corpus itself hides; the other tests write each node's file stating its corpus level. A root that does not exist, or that holds none of the files the corpus names (holds_corpus: one such file is enough, and an empty corpus is held by any directory), is refused with USAGE, nothing printed and the root named on stderr.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import query_corpus as qc  # noqa: E402

import reclassify  # noqa: E402

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


def _on_disk(root, corpus):
    """*corpus* with each node's file written under *root* at `docs/<id>.md`,
    stating the level its node states (none when the node states none), so
    the level each file states now is the corpus's."""
    (root / "docs").mkdir(exist_ok=True)
    for n in corpus["nodes"]:
        n["path"] = "docs/%s.md" % n["node_id"]
        level = n.get("visibility")
        fm = "visibility: %s\n" % level if isinstance(level, str) else ""
        (root / n["path"]).write_text("---\n%s---\n" % fm, encoding="utf-8")
    return corpus


def _ids(root, corpus, question, served=_SERVED):
    """The node ids query returns for *question* over *corpus*, its files on disk."""
    hits = qc.query(_on_disk(root, corpus), question, served=served, root=str(root))
    return [n["node_id"] for n in hits]


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


def test_a_query_finds_a_node_that_uses_another_inflection(tmp_path):
    corpus = {
        "nodes": [
            _node("a", summary="Deterministic and idempotent."),
            _node("b", summary="Other."),
        ]
    }
    assert _ids(tmp_path, corpus, "idempotency") == ["a"]


def test_a_body_only_match_counts_but_ranks_below_a_summary_match(tmp_path):
    corpus = {
        "nodes": [
            _node("body", summary="Unrelated.", excerpt="the corpus links nodes"),
            _node("head", summary="How the corpus is linked."),
        ]
    }
    assert _ids(tmp_path, corpus, "corpus linking") == ["head", "body"]


def test_acronyms_still_match_verbatim(tmp_path):
    corpus = {"nodes": [_node("bus", summary="The AXI bus.")]}
    assert _ids(tmp_path, corpus, "AXI") == ["bus"]


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


def test_a_node_outside_the_served_levels_is_neither_a_hit_nor_a_neighbour(tmp_path):
    assert _ids(tmp_path, _hidden_corpus(), "zebra plan") == ["hub"]


def test_the_served_levels_decide_which_nodes_are_retrieved(tmp_path):
    served = frozenset({"confidential"})
    assert _ids(tmp_path, _hidden_corpus(), "zebra plan", served) == ["secret"]


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
    path.write_text(json.dumps(_on_disk(tmp_path, corpus)), encoding="utf-8")
    monkeypatch.setattr(qc, "ROOT", str(tmp_path))
    assert qc.main(["zebra", "--corpus", str(path)]) is qc.ExitCode.SUCCESS
    captured = capsys.readouterr()
    assert [n["node_id"] for n in json.loads(captured.out)] == ["open"]
    # Each file states its node's level, so nothing the corpus serves is
    # withheld, and a node the corpus itself hides is not counted as withheld.
    assert "withheld" not in captured.err


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


# ---- a served node names no hidden node in its links, children or parent ---


def _doc(doc_id, title, visibility, body):
    return (
        "---\ntitle: %s\nkind: doc\nlayer: n/a\nstatus: stable\nowner: someone\n"
        "tags: [x]\nsummary: About %s.\nid: %s\ncreated: 2026-01-01\n"
        "updated: 2026-01-01\nvisibility: %s\ncanonical: true\n---\n%s"
        % (title, title, doc_id, visibility, body)
    )


def test_a_served_node_names_no_hidden_node_it_links_to(tmp_path, monkeypatch, capsys):
    """The reviewer's shape, built by the real build_corpus and link_corpus:
    a public doc links to a confidential `docs/secret/README.md`, and the
    printed JSON names neither the secret doc's id nor its title, in
    `links[].to`, `children`, `parent` or anywhere else."""
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    import build_corpus as bc  # noqa: E402
    import link_corpus as lc  # noqa: E402

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text("{}", encoding="utf-8")
    (tmp_path / "docs" / "secret").mkdir(parents=True)
    (tmp_path / "docs" / "open.md").write_text(
        _doc(
            "open-guide",
            "Open guide",
            "public",
            "# Open guide\n\nThe zebra notes, and [more](secret/README.md).\n\n"
            "## Zebra part\n\nZebra detail, see [the plan](secret/README.md).\n",
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "secret" / "README.md").write_text(
        _doc(
            "hush-plan",
            "Hush plan",
            "confidential",
            "# Hush plan\n\nZebra.\n\n## Hush part\n\nZebra too.\n",
        ),
        encoding="utf-8",
    )
    corpus = lc.link_corpus(bc.build_corpus(str(tmp_path)))
    nodes = {n["node_id"]: n for n in corpus["nodes"]}
    hidden = {nid for nid, n in nodes.items() if n.get("visibility") == "confidential"}
    # The fixture is the leak's shape only if the built corpus carries it.
    assert "hush-plan" in hidden and any(
        e["to"] in hidden for n in nodes.values() for e in n.get("links", [])
    )
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    monkeypatch.setattr(qc, "ROOT", str(tmp_path))
    assert qc.main(["zebra", "--corpus", str(path)]) is qc.ExitCode.SUCCESS
    out = capsys.readouterr().out
    printed = json.loads(out)
    assert printed and all(n["visibility"] == "public" for n in printed)
    for n in printed:
        assert not {e["to"] for e in n.get("links", [])} & hidden
        assert not set(n.get("children", [])) & hidden
        assert n.get("parent") not in hidden
    assert "hush" not in out.lower()


# ---- a file reclassified after the build is printed on its level now -------


@pytest.mark.parametrize("how", reclassify.HOWS)
def test_a_node_whose_file_now_states_a_stricter_level_is_not_printed(
    tmp_path, monkeypatch, capsys, how
):
    """The reviewer's repro: the scratch corpus says `docs/pubguide.md` is
    public, then the file is reclassified on disk (*how*). The CLI prints
    neither its node nor its id in the links of `guides/open.md`, a public
    doc that links to it and lives where the reclassify does not reach."""
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    import build_corpus as bc  # noqa: E402
    import link_corpus as lc  # noqa: E402

    (tmp_path / "guides").mkdir()
    (tmp_path / "guides" / "open.md").write_text(
        _doc(
            "open-guide",
            "Open guide",
            "public",
            "# Open guide\n\nThe zebra notes, and [more](../docs/pubguide.md).\n",
        ),
        encoding="utf-8",
    )
    reclassify.public_project(tmp_path, "The zebra body.")
    corpus = lc.link_corpus(bc.build_corpus(str(tmp_path)))
    path = tmp_path / "wiki" / "corpus.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    monkeypatch.setattr(qc, "ROOT", str(tmp_path))

    def printed():
        argv = ["zebra", "--corpus", str(path), "--root", str(tmp_path)]
        assert qc.main(argv) is qc.ExitCode.SUCCESS
        captured = capsys.readouterr()
        nodes = json.loads(captured.out)
        guide = {n["node_id"] for n in nodes if n["path"] == reclassify.GUIDE}
        linked = {e["to"] for n in nodes for e in n.get("links", [])}
        return nodes, guide, linked, captured.err

    nodes, guide, linked, err = printed()
    # The repro is the leak's shape only if the guide is printed and linked.
    assert "pubguide" in guide and "pubguide" in linked
    assert "withheld" not in err
    reclassify.reclassify(tmp_path / reclassify.GUIDE, how)
    nodes, guide, linked, err = printed()
    assert nodes and not guide
    # The guide's two nodes, `pubguide` and `pubguide#part`, are counted.
    assert "withheld 2 node(s)" in err and str(tmp_path) in err
    assert not linked & {
        n["node_id"] for n in corpus["nodes"] if n["path"] == reclassify.GUIDE
    }
    assert "About pubguide." not in json.dumps(nodes)


# ---- a root that cannot be the corpus's checkout is refused ----------------


def test_a_root_holds_a_corpus_when_it_holds_one_file_the_corpus_names(tmp_path):
    corpus = _on_disk(tmp_path, {"nodes": [_node("here"), _node("gone")]})
    (tmp_path / "docs" / "gone.md").unlink()
    assert qc.holds_corpus(corpus, str(tmp_path))
    assert not qc.holds_corpus(corpus, str(tmp_path / "docs"))
    assert not qc.holds_corpus(corpus, str(tmp_path / "nowhere"))


def test_an_empty_corpus_is_held_by_any_directory_that_exists(tmp_path):
    assert qc.holds_corpus({"nodes": []}, str(tmp_path))
    assert not qc.holds_corpus({"nodes": []}, str(tmp_path / "nowhere"))


@pytest.mark.parametrize("where", ["nowhere", "empty"])
def test_main_refuses_a_root_that_cannot_be_the_corpus_checkout(
    tmp_path, monkeypatch, capsys, where
):
    """A root that does not exist, or one that holds none of the files the
    corpus names, is refused with nothing printed, rather than printing `[]`
    as if the question had no answer."""
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    (project / "config" / "project.json").write_text("{}", encoding="utf-8")
    corpus = _on_disk(project, {"nodes": [_node("zebra", summary="Zebra.")]})
    path = project / "corpus.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    root = tmp_path / where
    if where == "empty":
        root.mkdir()
    monkeypatch.setattr(qc, "ROOT", str(project))
    argv = ["zebra", "--corpus", str(path), "--root", str(root)]
    assert qc.main(argv) is qc.ExitCode.USAGE
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(root) in captured.err and "--root" in captured.err
