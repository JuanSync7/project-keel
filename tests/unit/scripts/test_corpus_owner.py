"""
title: Unit — the corpus's owner resolution and the configured default owner
kind: tests
layer: n/a
summary: build_corpus resolves each node's owner finest-wins then inherit, and fills config/project.json `accountability.default_owner`, read through scripts/config_loader.py, where and only where the resolution ends on a `TBD` (in any letter case) in frontmatter, a marker or a package README, recording `owner_source: default` and the place the TBD stands as `owner_origin`. A real owner anywhere on the chain beats the default; a package README that cannot be read stops the walk, so a module and its symbols that name no owner of their own have owner and owner_source null, unknown; a node that names no owner, or a null spelling, stays `none`; with the default null or no config file every TBD stays `none`; a refused default raises, and the job exits CONFIG. check_corpus accepts `default` and still refuses an unknown source, and the accountability report counts the default as its own line, apart from the owned and the unowned, while `--json` still lists the unowned only.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import accountability_report as ar  # noqa: E402
import build_corpus as bc  # noqa: E402
import check_corpus as cc  # noqa: E402
import config_loader  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit

_DEFAULT = "ops"


def _fm(doc_id, owner=None):
    owner_line = "" if owner is None else "owner: %s\n" % owner
    return (
        "---\ntitle: %s\nkind: doc\nlayer: n/a\nstatus: stable\n%s"
        "summary: About %s.\nid: %s\ncreated: 2026-01-01\n"
        "updated: 2026-01-01\nvisibility: internal\ncanonical: true\n---\n"
        % (doc_id, owner_line, doc_id, doc_id)
    )


def _doc(owner, body="## Plain\n\ntext\n"):
    return _fm("d", owner) + "# D\n\n" + body


def _module(owner=None, symbol_marker=None):
    head = "title: M\nsummary: Does m.\n"
    if owner is not None:
        head += "owner: %s\n" % owner
    marker = "" if symbol_marker is None else "\n\n    owner: %s\n    " % symbol_marker
    return (
        '"""\n%s"""\n__all__ = ["f", "g"]\n\n\n'
        'def f():\n    """Return f.%s"""\n    return 1\n\n\n'
        'def g():\n    """Return g."""\n    return 2\n' % (head, marker)
    )


def _tree(root, default=_DEFAULT, config=True):
    if config:
        (root / "config").mkdir(exist_ok=True)
        manifest = (
            {} if default is ... else {"accountability": {"default_owner": default}}
        )
        (root / "config" / "project.json").write_text(json.dumps(manifest))
    return root


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _nodes(root):
    return {n["node_id"]: n for n in bc.build_corpus(str(root))["nodes"]}


def _owner(node):
    return node["owner"], node["owner_source"], node["owner_origin"]


@pytest.fixture(autouse=True)
def _fresh_announcements():
    config_loader._ANNOUNCED.clear()
    yield
    config_loader._ANNOUNCED.clear()


# --- documents and sections --------------------------------------------------


@pytest.mark.parametrize("tbd", ["TBD", "tbd", "Tbd"])
def test_a_tbd_doc_and_its_sections_answer_to_the_default(tmp_path, tbd):
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc(tbd))
    nodes = _nodes(root)
    assert _owner(nodes["d"]) == (_DEFAULT, "default", "docs/d.md")
    assert _owner(nodes["d#plain"]) == (_DEFAULT, "default", "docs/d.md")


def test_a_real_section_marker_under_a_tbd_doc_wins(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc("TBD", "## Owned\n<!-- owner: alice -->\n\nt\n"))
    nodes = _nodes(root)
    assert _owner(nodes["d#owned"]) == ("alice", "marker", "docs/d.md#owned")


def test_a_tbd_section_marker_under_an_owned_doc_inherits_the_real_owner(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc("bob", "## Later\n<!-- owner: TBD -->\n\nt\n"))
    nodes = _nodes(root)
    assert _owner(nodes["d#later"]) == ("bob", "inherited", "docs/d.md")


def test_a_tbd_section_marker_under_a_doc_with_no_owner_takes_the_default(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc(None, "## Later\n<!-- owner: tbd -->\n\nt\n"))
    nodes = _nodes(root)
    assert _owner(nodes["d"]) == ("", "none", None)
    assert _owner(nodes["d#later"]) == (_DEFAULT, "default", "docs/d.md#later")


@pytest.mark.parametrize("owner", [None, "", "null", "NULL", "~"])
def test_a_doc_that_names_no_owner_stays_unowned_with_a_default_set(tmp_path, owner):
    """The default stands in for TBD only: nobody marked these, so the
    corpus does not claim them."""
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc(owner))
    nodes = _nodes(root)
    assert _owner(nodes["d"]) == ("", "none", None)
    assert _owner(nodes["d#plain"]) == ("", "none", None)


@pytest.mark.parametrize("default", [None, ...], ids=["null", "absent-key"])
def test_with_no_default_a_tbd_doc_stays_unowned(tmp_path, default):
    root = _tree(tmp_path, default=default)
    _write(root, "docs/d.md", _doc("TBD"))
    nodes = _nodes(root)
    assert _owner(nodes["d"]) == ("", "none", None)
    assert _owner(nodes["d#plain"]) == ("", "none", None)


def test_with_no_config_file_a_tbd_doc_stays_unowned(tmp_path):
    root = _tree(tmp_path, config=False)
    _write(root, "docs/d.md", _doc("TBD"))
    assert _owner(_nodes(root)["d"]) == ("", "none", None)


def test_a_real_doc_owner_is_untouched_by_the_default(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc("bob"))
    nodes = _nodes(root)
    assert _owner(nodes["d"]) == ("bob", "frontmatter", "docs/d.md")
    assert _owner(nodes["d#plain"]) == ("bob", "inherited", "docs/d.md")


# --- modules and symbols -----------------------------------------------------


def test_a_module_under_a_tbd_readme_and_its_symbols_answer_to_the_default(tmp_path):
    root = _tree(tmp_path)
    _write(root, "src/README.md", _fm("src-readme", "TBD") + "# src\n")
    _write(root, "src/m.py", _module(symbol_marker="carol"))
    nodes = _nodes(root)
    assert _owner(nodes["src/m-py"]) == (_DEFAULT, "default", "src/README.md")
    assert _owner(nodes["src/m-py::f"]) == ("carol", "marker", "src/m.py::f")
    assert _owner(nodes["src/m-py::g"]) == (_DEFAULT, "default", "src/README.md")


def test_a_tbd_module_under_an_owned_readme_inherits_the_real_owner(tmp_path):
    root = _tree(tmp_path)
    _write(root, "src/README.md", _fm("src-readme", "dave") + "# src\n")
    _write(root, "src/m.py", _module(owner="TBD"))
    nodes = _nodes(root)
    assert _owner(nodes["src/m-py"]) == ("dave", "inherited", "src/README.md")
    assert _owner(nodes["src/m-py::g"]) == ("dave", "inherited", "src/README.md")


def test_a_tbd_module_with_no_owned_readme_takes_the_default_at_itself(tmp_path):
    root = _tree(tmp_path)
    _write(root, "src/m.py", _module(owner="TBD"))
    nodes = _nodes(root)
    assert _owner(nodes["src/m-py"]) == (_DEFAULT, "default", "src/m.py")
    assert _owner(nodes["src/m-py::g"]) == (_DEFAULT, "default", "src/m.py")


def test_a_tbd_symbol_marker_with_nothing_above_takes_the_default(tmp_path):
    root = _tree(tmp_path)
    _write(root, "src/m.py", _module(symbol_marker="TBD"))
    nodes = _nodes(root)
    assert _owner(nodes["src/m-py"]) == ("", "none", None)
    assert _owner(nodes["src/m-py::f"]) == (_DEFAULT, "default", "src/m.py::f")
    assert _owner(nodes["src/m-py::g"]) == ("", "none", None)


# --- the default is read through the loader, and a refused one is loud -------


@pytest.mark.parametrize("bad", ["TBD", "two words", "null", 7])
def test_a_refused_default_raises_the_loaders_error(tmp_path, bad):
    root = _tree(tmp_path, default=bad)
    _write(root, "docs/d.md", _doc("TBD"))
    with pytest.raises(config_loader.ConfigError):
        bc.build_corpus(str(root))


def test_the_job_exits_config_on_a_refused_default(tmp_path, capsys):
    root = _tree(tmp_path, default="TBD")
    _write(root, "docs/d.md", _doc("TBD"))
    rc = bc.main(["--root", str(root), "--out", str(tmp_path / "out.json")])
    assert rc == ExitCode.CONFIG
    assert "accountability.default_owner" in capsys.readouterr().err
    assert not (tmp_path / "out.json").exists()


def test_the_gate_exits_config_on_a_refused_default(tmp_path, capsys):
    root = _tree(tmp_path, default="TBD")
    _write(root, "docs/d.md", _doc("TBD"))
    assert cc.main(["--root", str(root)]) == ExitCode.CONFIG
    assert "accountability.default_owner" in capsys.readouterr().err


_REFUSED = 'accountability.default_owner is string "TBD"'


@pytest.mark.parametrize("run", ["job", "gate"])
def test_a_refused_default_prints_the_loaders_line_once(tmp_path, capsys, run):
    root = _tree(tmp_path, default="TBD")
    _write(root, "docs/d.md", _doc("TBD"))
    assert _main(run, root, tmp_path) == ExitCode.CONFIG
    assert capsys.readouterr().err.count(_REFUSED) == 1


@pytest.mark.parametrize("run", ["job", "gate"])
def test_an_unreadable_config_names_the_file_not_the_default_owner(
    tmp_path, capsys, run
):
    """A broken file is not a refused default: the line names the file and
    why it cannot be read, so the repair is in the right place."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text('{"accountability": ')
    _write(tmp_path, "docs/d.md", _doc("TBD"))
    assert _main(run, tmp_path, tmp_path) == ExitCode.CONFIG
    err = capsys.readouterr().err
    assert "config/project.json cannot be read as JSON" in err
    assert "accountability.default_owner" not in err


def _main(run, root, tmp_path):
    if run == "job":
        return bc.main(["--root", str(root), "--out", str(tmp_path / "out.json")])
    return cc.main(["--root", str(root)])


# --- an owner outside the grammar names nobody --------------------------------

# How a line parser keeps a commented, quoted or otherwise malformed owner.
# check_F refuses each of these in a tool or agent doc, so none is owned there.
_MALFORMED = ["~ # nobody yet", "TBD  # later", '"TBD"', "'null'", '"alice"']


@pytest.mark.parametrize("owner", _MALFORMED)
def test_a_doc_owner_outside_the_grammar_is_unowned_not_defaulted(tmp_path, owner):
    """A quoted or commented TBD is not the placeholder: check_F refuses it
    rather than handing it the default, and the corpus agrees."""
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc(owner))
    nodes = _nodes(root)
    assert _owner(nodes["d"]) == ("", "none", None)
    assert _owner(nodes["d#plain"]) == ("", "none", None)


@pytest.mark.parametrize("owner", _MALFORMED)
def test_a_module_owner_outside_the_grammar_resolves_through_its_readme(
    tmp_path, owner
):
    root = _tree(tmp_path)
    _write(root, "src/README.md", _fm("src-readme", "dave") + "# src\n")
    _write(root, "src/m.py", _module(owner=owner))
    assert _owner(_nodes(root)["src/m-py"]) == ("dave", "inherited", "src/README.md")


@pytest.mark.parametrize("owner", _MALFORMED)
def test_a_readme_owner_outside_the_grammar_is_not_inherited(tmp_path, owner):
    root = _tree(tmp_path)
    _write(root, "src/README.md", _readme("src-readme", owner, "internal"))
    _write(root, "src/m.py", _module())
    assert _owner(_nodes(root)["src/m-py"]) == ("", "none", None)


# --- the package README walk -------------------------------------------------


def _readme(doc_id, owner=None, visibility=None):
    head = "---\ntitle: %s\nkind: doc\nsummary: About %s.\nid: %s\n" % (
        doc_id,
        doc_id,
        doc_id,
    )
    if owner is not None:
        head += "owner: %s\n" % owner
    if visibility is not None:
        head += "visibility: %s\n" % visibility
    return head + "---\n# %s\n" % doc_id


@pytest.mark.parametrize("vis", [None, "internal"], ids=["no-visibility", "visible"])
def test_a_real_owner_above_a_tbd_readme_beats_the_default(tmp_path, vis):
    """CONVENTIONS §12: a real owner anywhere on the chain beats the default,
    whether or not the nearer TBD README declares a visibility."""
    root = _tree(tmp_path)
    _write(root, "src/README.md", _readme("src-readme", "alice", "public"))
    _write(root, "src/backend/README.md", _readme("be-readme", "TBD", vis))
    _write(root, "src/backend/m.py", _module())
    nodes = _nodes(root)
    assert _owner(nodes["src/backend/m-py"]) == ("alice", "inherited", "src/README.md")
    assert _owner(nodes["src/backend/m-py::g"]) == (
        "alice",
        "inherited",
        "src/README.md",
    )


@pytest.mark.parametrize("vis", [None, "internal"], ids=["no-visibility", "visible"])
def test_a_tbd_readme_with_no_real_owner_above_takes_the_default(tmp_path, vis):
    root = _tree(tmp_path)
    _write(root, "src/README.md", _readme("src-readme", None, "public"))
    _write(root, "src/backend/README.md", _readme("be-readme", "TBD", vis))
    _write(root, "src/backend/m.py", _module())
    assert _owner(_nodes(root)["src/backend/m-py"]) == (
        _DEFAULT,
        "default",
        "src/backend/README.md",
    )


def test_the_nearest_tbd_readme_is_the_default_origin(tmp_path):
    root = _tree(tmp_path)
    _write(root, "src/README.md", _readme("src-readme", "TBD", "public"))
    _write(root, "src/backend/README.md", _readme("be-readme", "tbd", "internal"))
    _write(root, "src/backend/m.py", _module())
    assert _owner(_nodes(root)["src/backend/m-py"])[2] == "src/backend/README.md"


def test_a_readme_with_no_owner_does_not_cut_the_owner_chain(tmp_path):
    """A README that names no owner names nothing to inherit, so the walk
    goes on to the README above, as it does past a TBD one."""
    root = _tree(tmp_path)
    _write(root, "src/README.md", _readme("src-readme", "alice", "public"))
    _write(root, "src/backend/README.md", _readme("be-readme", None, "internal"))
    _write(root, "src/backend/m.py", _module())
    assert _owner(_nodes(root)["src/backend/m-py"]) == (
        "alice",
        "inherited",
        "src/README.md",
    )


_UNKNOWN = (None, None, None)
_UNDECODABLE = b"---\ntitle: P\nowner: zed\n\xff---\n"


def test_an_unreadable_readme_stops_the_owner_walk_at_unknown(tmp_path):
    """An unreadable README.md may name any owner, so nothing below it
    inherits the owner above it: the module and its symbols have owner and
    owner_source null, and the accountability report counts them unknown."""
    root = _tree(tmp_path)
    _write(root, "src/README.md", _readme("src-readme", "alice", "public"))
    (root / "src" / "pkg").mkdir()
    (root / "src" / "pkg" / "README.md").write_bytes(_UNDECODABLE)
    _write(root, "src/pkg/m.py", _module())
    corpus = bc.build_corpus(str(root))
    nodes = {n["node_id"]: n for n in corpus["nodes"]}
    for node_id in ("src/pkg/m-py", "src/pkg/m-py::f", "src/pkg/m-py::g"):
        assert _owner(nodes[node_id]) == _UNKNOWN, (node_id, _owner(nodes[node_id]))
    blind = {n["node_id"] for n in ar.unknown(corpus)}
    assert {"src/pkg/m-py", "src/pkg/m-py::f", "src/pkg/m-py::g"} <= blind, blind
    assert nodes["src-readme"]["owner"] == "alice"


def test_an_unreadable_readme_above_a_tbd_readme_leaves_the_owner_unknown(tmp_path):
    """The unreadable README.md may name the real owner that beats the
    default, so a TBD below it does not take the default."""
    root = _tree(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "README.md").write_bytes(_UNDECODABLE)
    _write(root, "src/pkg/README.md", _readme("pkg-readme", "TBD", None))
    _write(root, "src/pkg/m.py", _module(symbol_marker="TBD"))
    nodes = _nodes(root)
    assert _owner(nodes["src/pkg/m-py"]) == _UNKNOWN
    assert _owner(nodes["src/pkg/m-py::f"]) == _UNKNOWN


def test_a_module_s_own_owner_stands_under_an_unreadable_readme(tmp_path):
    root = _tree(tmp_path)
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "README.md").write_bytes(_UNDECODABLE)
    _write(root, "src/pkg/m.py", _module("bob", symbol_marker="carol"))
    nodes = _nodes(root)
    assert _owner(nodes["src/pkg/m-py"]) == ("bob", "frontmatter", "src/pkg/m.py")
    assert _owner(nodes["src/pkg/m-py::g"])[:2] == ("bob", "inherited")
    assert _owner(nodes["src/pkg/m-py::f"])[:2] == ("carol", "marker")


def test_the_owner_walk_and_the_visibility_chain_are_independent(tmp_path):
    """The owner walk goes past a TBD README to a real owner above it, and the
    visibility is the strictest on the chain whichever README names the owner
    (tests/unit/scripts/test_corpus_visibility.py holds the visibility rule)."""
    root = _tree(tmp_path)
    _write(root, "src/README.md", _readme("src-readme", "alice", "public"))
    _write(root, "src/backend/README.md", _readme("be-readme", "TBD", "confidential"))
    _write(root, "src/backend/m.py", _module())
    nodes = _nodes(root)
    assert nodes["src/backend/m-py"]["visibility"] == "confidential"
    assert nodes["src/backend/m-py::g"]["visibility"] == "confidential"
    assert _owner(nodes["src/backend/m-py"]) == ("alice", "inherited", "src/README.md")


@pytest.mark.parametrize(
    "written, owner",
    [
        (None, ("", "none", None)),
        ("TBD", (_DEFAULT, "default", "src/backend/README.md")),
        ("bob", ("bob", "inherited", "src/backend/README.md")),
        ('"alice"', ("", "none", None)),
        ("null", ("", "none", None)),
    ],
    ids=["no-owner", "tbd", "owned", "quoted", "null"],
)
def test_a_readme_s_owner_has_no_say_in_the_visibility_it_passes_on(
    tmp_path, written, owner
):
    """A README that states no visibility passes on the one above it, however
    its owner is written: an owned or malformed one once ended the walk and
    gave its modules `internal` under a confidential parent (KEEL-VIS-1)."""
    root = _tree(tmp_path)
    _write(root, "src/README.md", _readme("src-readme", None, "confidential"))
    _write(root, "src/backend/README.md", _readme("be-readme", written, None))
    _write(root, "src/backend/m.py", _module())
    node = _nodes(root)["src/backend/m-py"]
    assert node["visibility"] == "confidential"
    assert _owner(node) == owner


# --- the vocabulary and the report -------------------------------------------


def test_check_corpus_accepts_default_and_still_refuses_an_unknown_source(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc("TBD"))
    corpus = bc.build_corpus(str(root))
    assert cc.validate(corpus) == []
    corpus["nodes"][0]["owner_source"] = "assumed"
    assert any("invalid owner_source" in e for e in cc.validate(corpus))


def test_a_default_node_with_no_owner_is_incoherent(tmp_path):
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc("TBD"))
    corpus = bc.build_corpus(str(root))
    corpus["nodes"][0]["owner"] = ""
    assert any("owner is empty" in e for e in cc.validate(corpus))


def _report_corpus(root):
    _write(root, "docs/d.md", _doc("TBD"))
    _write(root, "docs/e.md", _fm("e", "bob") + "# E\n")
    _write(root, "docs/f.md", _fm("f") + "# F\n")
    return bc.build_corpus(str(root))


def test_the_report_counts_the_default_apart_from_owned_and_unowned(tmp_path):
    corpus = _report_corpus(_tree(tmp_path))
    assert [n["node_id"] for n in ar.unowned(corpus)] == ["f"]
    assert sorted(n["node_id"] for n in ar.defaulted(corpus)) == ["d", "d#plain"]


def test_the_report_prints_one_line_each_for_unowned_default_and_owned(
    tmp_path, capsys
):
    root = _tree(tmp_path)
    out = tmp_path / "corpus.json"
    out.write_text(json.dumps(_report_corpus(root)))
    assert ar.main(["--corpus", str(out)]) == ExitCode.SUCCESS
    text = capsys.readouterr().out
    assert "accountability: 1 of 4 nodes have no resolved owner" in text
    assert (
        "accountability: 2 of 4 nodes answer to the default owner until a real "
        "one is named, from 1 TBD:" in text
    )
    assert "  docs/d.md" in text
    assert "accountability: 1 of 4 nodes have a real owner" in text


def test_the_json_report_still_lists_the_unowned_only(tmp_path, capsys):
    """index_enforcer reads `--json` as its owner gaps; a default node is
    owned for now, so it is not a gap there."""
    root = _tree(tmp_path)
    out = tmp_path / "corpus.json"
    out.write_text(json.dumps(_report_corpus(root)))
    assert ar.main(["--corpus", str(out), "--json"]) == ExitCode.SUCCESS
    listed = json.loads(capsys.readouterr().out)
    assert [n["node_id"] for n in listed] == ["f"]


def _with_unknown(corpus):
    """Four rows that name no CONVENTIONS §12 source: a corpus written before
    owner_source existed, or by hand. Each is unknown, neither owned nor not."""
    rows = []
    for i, stored in enumerate(["absent", None, "", "bogus"]):
        row = {"node_id": "u%d" % i, "kind": "doc", "path": "u%d.md" % i}
        row["owner"] = "alice"
        if stored != "absent":
            row["owner_source"] = stored
        rows.append(row)
    corpus["nodes"] = corpus["nodes"] + rows
    return corpus


def test_the_report_counts_an_unknown_owner_source_as_its_own_bucket(tmp_path):
    corpus = _with_unknown(_report_corpus(_tree(tmp_path)))
    assert [n["node_id"] for n in ar.unknown(corpus)] == ["u0", "u1", "u2", "u3"]
    assert [n["node_id"] for n in ar.unowned(corpus)] == ["f"]


def test_the_report_prints_the_unknown_apart_and_never_counts_it_owned(
    tmp_path, capsys
):
    out = tmp_path / "corpus.json"
    out.write_text(json.dumps(_with_unknown(_report_corpus(_tree(tmp_path)))))
    assert ar.main(["--corpus", str(out)]) == ExitCode.SUCCESS
    text = capsys.readouterr().out
    assert "accountability: 1 of 8 nodes have no resolved owner" in text
    assert "accountability: 4 of 8 nodes name no owner source" in text
    for node_id in ("u0", "u1", "u2", "u3"):
        assert " %s  (%s.md)" % (node_id, node_id) in text
    assert "accountability: 1 of 8 nodes have a real owner" in text
