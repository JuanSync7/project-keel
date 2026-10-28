"""
title: Unit — query_corpus retrieval (stems and excerpts)
kind: tests
layer: n/a
summary: query_corpus scores a node by query-token overlap, and before this two things made it miss: tokens were compared verbatim, so `idempotency` found nothing while `idempotent` found eight nodes; and only tags, title and summary were read, so a term that lives in the body was invisible. Tokens are now lightly stemmed on both sides and the body excerpt counts, below the title and summary, so a body-only match never outranks a summary match. A node at a level outside config/project.json corpus.served_visibilities, or that states none, is cut before scoring, so it is neither a hit nor a neighbour, and the CLI reads the configured list. A served node the CLI prints names no hidden node in its links, children or parent: a public doc linking to a confidential one, built by the real build_corpus and link_corpus, prints neither the confidential doc's id nor its title. A node whose file under `--root` now states a stricter level is not printed either: in the reviewer's repro, `docs/pubguide.md` reclassified after the build in each of tests/reclassify.py's ways, neither its node nor its id in a served doc's links is printed, the script's own checkout set apart from `--root` so a CLI that ignores `--root` is red, and stderr counts the withheld nodes, never a node the corpus itself hides; the other tests write each node's file stating its corpus level. The root is derived from the corpus, never chosen beside it, in the reviewer's repros: checkout `a` made its guide confidential without rebuilding its corpus, `b` is a copy taken before, `c` holds only the guide and another folder only a README.md. a's corpus, named from inside b, is read with a's files and withholds the guide; b's corpus, named by a relative path from inside b, serves it; `c` and the README folder keep no corpus, so `--root` there prints `[]` and names where the corpus would be; `--root b` beside a's corpus, and a copy of a's corpus outside some checkout's wiki/corpus.json, are refused with USAGE and nothing printed; a root that does not exist is refused with USAGE naming it.
"""

import json
import shutil
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


def _corpus_file(root):
    """Where *root* keeps its corpus, its directory made."""
    path = root / "wiki" / "corpus.json"
    path.parent.mkdir(exist_ok=True)
    return path


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
    path = _corpus_file(tmp_path)
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
    path = _corpus_file(tmp_path)
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
    path = _corpus_file(tmp_path)
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
    (tmp_path / "wiki" / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    # The script's own checkout is elsewhere and holds none of these files,
    # so only a CLI that reads `--root` sees the guide at all.
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    (home / "config" / "project.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(qc, "ROOT", str(home))

    def printed():
        argv = ["zebra", "--root", str(tmp_path)]
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


# ---- the root is derived from the corpus, never chosen beside it ----------


def _stale_project(base):
    """The reviewer's repros under *base*: checkout `a` made its guide
    confidential and did not rebuild its corpus, which still serves it; `b`
    is a copy of `a` taken before; `c` holds only the guide, copied from b;
    `readme` holds only a README.md. Returns (a, b, c, readme)."""
    a, b, c, readme = (base / name for name in ("a", "b", "c", "readme"))
    a.mkdir()
    reclassify.public_project(a, "The zebra body.")
    shutil.copytree(str(a), str(b))
    reclassify.reclassify(a / reclassify.GUIDE, "own")
    (c / "docs").mkdir(parents=True)
    shutil.copy(str(b / reclassify.GUIDE), str(c / reclassify.GUIDE))
    readme.mkdir()
    (readme / "README.md").write_text("# Readme\n\nZebra.\n", encoding="utf-8")
    return a, b, c, readme


_GUIDE_IDS = {"pubguide", "pubguide#part"}


def _main(argv, capsys):
    """(exit code, printed node ids or None when nothing was printed, stderr)."""
    code = qc.main(argv)
    captured = capsys.readouterr()
    ids = {n["node_id"] for n in json.loads(captured.out)} if captured.out else None
    return code, ids, captured.err


def test_a_corpus_is_answered_against_its_own_checkouts_files(
    tmp_path, monkeypatch, capsys
):
    """The stale-copy repro: a's corpus, named from any directory, is read
    with a's files, so a's confidential guide is withheld even from inside
    b, whose files still state it public; b's own corpus, named by a
    relative path from inside b, is b's to serve."""
    a, b, _, _ = _stale_project(tmp_path)
    monkeypatch.setattr(qc, "ROOT", str(a))
    monkeypatch.chdir(b)
    code, ids, err = _main(
        ["zebra", "--corpus", str(a / "wiki" / "corpus.json")], capsys
    )
    assert code is qc.ExitCode.SUCCESS and not ids & _GUIDE_IDS
    assert "withheld 2 node(s)" in err and str(a) in err
    code, ids, _ = _main(["zebra", "--corpus", "wiki/corpus.json"], capsys)
    assert code is qc.ExitCode.SUCCESS and ids == _GUIDE_IDS
    code, ids, _ = _main(["zebra", "--root", str(a)], capsys)
    assert code is qc.ExitCode.SUCCESS and not ids & _GUIDE_IDS


@pytest.mark.parametrize("folder", ["c", "readme"])
def test_a_folder_with_no_corpus_of_its_own_prints_nothing_of_anothers(
    tmp_path, monkeypatch, capsys, folder
):
    """The folder `c` holding only the guide, and one holding only a
    README.md, keep no corpus, so `--root` there answers from none: `[]`,
    with stderr naming where the corpus would be and how to build it."""
    a, _, _, _ = _stale_project(tmp_path)
    monkeypatch.setattr(qc, "ROOT", str(a))
    root = tmp_path / folder
    code, ids, err = _main(["zebra", "--root", str(root)], capsys)
    assert code is qc.ExitCode.SUCCESS and ids == set()
    assert str(root / "wiki" / "corpus.json") in err and "make site-data" in err


def test_a_root_and_a_corpus_given_together_are_refused(tmp_path, monkeypatch, capsys):
    """`--root b` beside a's corpus would read a's corpus with b's files, the
    pairing that printed a's confidential guide, so it is refused, nothing
    printed."""
    a, b, _, _ = _stale_project(tmp_path)
    monkeypatch.setattr(qc, "ROOT", str(a))
    argv = ["zebra", "--root", str(b), "--corpus", str(a / "wiki" / "corpus.json")]
    code, ids, err = _main(argv, capsys)
    assert code is qc.ExitCode.USAGE and ids is None
    assert "not both" in err


@pytest.mark.parametrize(
    "where", ["corpus.json", "b/corpus.json", "b/docs/corpus.json"]
)
def test_a_corpus_outside_a_checkouts_wiki_is_refused(
    tmp_path, monkeypatch, capsys, where
):
    """A copy of a's corpus anywhere but some checkout's wiki/corpus.json has
    no checkout to read its files in, so it is refused, naming the path."""
    a, _, _, _ = _stale_project(tmp_path)
    monkeypatch.setattr(qc, "ROOT", str(a))
    corpus = tmp_path / where
    shutil.copy(str(a / "wiki" / "corpus.json"), str(corpus))
    code, ids, err = _main(["zebra", "--corpus", str(corpus)], capsys)
    assert code is qc.ExitCode.USAGE and ids is None
    assert str(corpus) in err and "wiki/corpus.json" in err


def test_a_missing_root_is_refused_before_its_corpus_is_looked_for(
    tmp_path, monkeypatch, capsys
):
    """A root that does not exist has no corpus; that is a refusal naming the
    root, not the `[]` of a checkout with no corpus yet."""
    a, _, _, _ = _stale_project(tmp_path)
    monkeypatch.setattr(qc, "ROOT", str(a))
    root = tmp_path / "nowhere"
    code, ids, err = _main(["zebra", "--root", str(root)], capsys)
    assert code is qc.ExitCode.USAGE and ids is None and str(root) in err
