"""
title: Unit — the corpus's owner resolution and the configured default owner
kind: tests
layer: n/a
summary: build_corpus resolves each node's owner finest-wins then inherit, and fills config/project.json `accountability.default_owner`, read through scripts/config_loader.py, where and only where the resolution ends on a `TBD` (in any letter case) in frontmatter, a marker or a package README, recording `owner_source: default` and the place the TBD stands as `owner_origin`. A real owner anywhere on the chain beats the default; a package README that cannot be read stops the walk, so a module and its symbols that name no owner of their own have owner and owner_source null, unknown; a node that names no owner, or a null spelling, stays `none`; with the default null or no config file every TBD stays `none`; a refused default raises, and the job exits CONFIG. check_corpus accepts `default` and still refuses an unknown source, and the accountability report, which lists a row missing a field with that field missing and never tracebacks, counts the default as its own line, apart from the owned and the unowned, while `--json` still lists the unowned only; a corpus with no `nodes` list is refused by the report and by each bucket a library caller asks for.
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
import check_structure as cs  # noqa: E402
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


def test_a_readable_readme_stating_the_unreadable_marker_does_not_stop_the_walk(
    tmp_path,
):
    """The owner walk stops at a README.md that could not be read, known by
    identity, not at one that can be read and happens to state the marker's
    value: that one names no owner, so the owner above it is inherited."""
    root = _tree(tmp_path)
    _write(root, "src/README.md", _readme("src-readme", "alice", None))
    _write(
        root,
        "src/pkg/README.md",
        "---\nvisibility: %s\n---\n# P\n" % cs.UNREADABLE_VISIBILITY,
    )
    _write(root, "src/pkg/m.py", _module())
    assert _owner(_nodes(root)["src/pkg/m-py"]) == (
        "alice",
        "inherited",
        "src/README.md",
    )


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


@pytest.mark.parametrize("stored", [None, "assumed"])
def test_an_owner_source_outside_the_set_is_one_error_naming_the_set(tmp_path, stored):
    """An unknown owner is (None, None, None): one error that says which
    sources check_corpus accepts, not a second one calling the null owner
    incoherent with a source the node does not have."""
    root = _tree(tmp_path)
    _write(root, "docs/d.md", _doc("alice"))
    corpus = bc.build_corpus(str(root))
    corpus["nodes"][0].update(owner=None, owner_source=stored, owner_origin=None)
    found = [e for e in cc.validate(corpus) if "owner" in e]
    assert len(found) == 1, found
    assert "expected one of %s" % sorted(cc.OWNER_SOURCES) in found[0], found
    if stored is None:
        assert "cannot read" in found[0] and "repair that README.md" in found[0]


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
    # build_corpus writes an unknown owner where a README.md above the node
    # cannot be read, so rebuilding alone repeats it; the repair is the README.
    (advice,) = [line for line in text.splitlines() if "name no owner source" in line]
    assert "repair the unreadable README.md above it (or state an owner" in advice
    assert "-- rebuild" not in advice, advice
    for node_id in ("u0", "u1", "u2", "u3"):
        assert " %s  (%s.md)" % (node_id, node_id) in text
    assert "accountability: 1 of 8 nodes have a real owner" in text


@pytest.mark.parametrize("readme", ["scripts/README.md", "scripts/README.md.jinja"])
def test_the_scripts_roster_names_every_bucket_the_report_prints(readme):
    """The accountability_report row in each twin names the four buckets the
    text report prints: unowned (`none`), on the default owner, unknown (no
    owner source) and owned."""
    text = (_ROOT / readme).read_text(encoding="utf-8")
    (row,) = [
        line
        for line in text.splitlines()
        if line.startswith("| `accountability_report.py` |")
    ]
    for bucket in (
        "`owner_source` is `none`",
        "`owner_source: default`",
        "name no owner source",
        "a real owner",
    ):
        assert bucket in row, (readme, bucket)


def _report(tmp_path, capsys, corpus, *flags):
    out = tmp_path / "corpus.json"
    out.write_text(json.dumps(corpus))
    code = ar.main(["--corpus", str(out), *flags])
    return code, capsys.readouterr().out


def test_a_row_missing_its_kind_and_path_is_listed_with_them_missing(tmp_path, capsys):
    """A hand-written or older corpus row lacks fields the report shows; the
    row is still listed, the missing field reads as missing, and the report
    keeps its documented exit 0."""
    code, text = _report(tmp_path, capsys, {"nodes": [{"node_id": "x", "owner": "a"}]})
    assert code == ExitCode.SUCCESS
    assert "accountability: 1 of 1 nodes name no owner source" in text
    assert "  %-9s x  (%s)" % (ar.MISSING, ar.MISSING) in text, text


def test_rows_missing_the_fields_each_bucket_reads_are_listed(tmp_path, capsys):
    corpus = {
        "nodes": [
            {"owner_source": "none"},
            {"node_id": "n", "owner_source": "none"},
            {"node_id": "d", "owner_source": "default", "owner": "ops"},
            {
                "node_id": "e",
                "owner_source": "default",
                "owner": "ops",
                "owner_origin": "docs/e.md",
            },
            "not-a-row",
        ]
    }
    code, text = _report(tmp_path, capsys, corpus)
    assert code == ExitCode.SUCCESS
    assert "accountability: 2 of 5 nodes have no resolved owner" in text
    assert "  %-9s %s  (%s)" % (ar.MISSING, ar.MISSING, ar.MISSING) in text, text
    assert "from 2 TBD:" in text and "  %s\n" % ar.MISSING in text, text
    assert "accountability: 1 of 5 nodes name no owner source" in text, text


def test_each_listed_bucket_is_in_node_id_order_whatever_the_corpus_order(
    tmp_path, capsys
):
    """The report sorts each list by node_id as printed, so a row missing its
    node_id sorts as the missing marker, and two corpora with the same rows
    print the same report."""
    rows = [
        {"node_id": "b", "owner_source": "none"},
        {"owner_source": "none"},
        {"node_id": "a", "owner_source": "none"},
        {"node_id": "z", "owner_source": "bogus"},
        {"node_id": "y"},
    ]
    _, text = _report(tmp_path, capsys, {"nodes": rows})
    _, again = _report(tmp_path, capsys, {"nodes": rows[::-1]})
    assert text == again
    listed = [line.split()[1] for line in text.splitlines() if line.startswith("  ")]
    assert listed == sorted(["a", "b", ar.MISSING]) + ["y", "z"], text


def test_the_json_report_shows_a_missing_field_as_null(tmp_path, capsys):
    code, out = _report(
        tmp_path, capsys, {"nodes": [{"owner_source": "none", "kind": "doc"}]}, "--json"
    )
    assert code == ExitCode.SUCCESS
    assert json.loads(out) == [{"kind": "doc", "node_id": None, "path": None}]


def test_the_report_s_real_sources_are_check_corpus_s_vocabulary(monkeypatch):
    """The report derives the sources that name a real owner from
    corpus_vocabulary OWNER_SOURCES, the set check_corpus judges by, so a
    source added there is counted owned here with no second edit."""
    import importlib

    import corpus_vocabulary as cv

    assert cc.OWNER_SOURCES is cv.OWNER_SOURCES
    assert set(ar._REAL_SOURCES) | {"none", "default"} == cv.OWNER_SOURCES
    monkeypatch.setattr(cv, "OWNER_SOURCES", cv.OWNER_SOURCES | {"bequeathed"})
    try:
        assert "bequeathed" in importlib.reload(ar)._REAL_SOURCES
    finally:
        monkeypatch.undo()
        importlib.reload(ar)


def _imports(path):
    """The top-level module names *path* imports."""
    import ast

    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_the_report_reads_the_owner_vocabulary_without_the_corpus_gate():
    """The report takes OWNER_SOURCES from a module that imports nothing of
    the project, so reading a corpus never loads check_corpus, and through
    it build_corpus and check_structure."""
    report = _imports(_ROOT / "scripts" / "accountability_report.py")
    assert "corpus_vocabulary" in report, report
    assert not report & {"check_corpus", "build_corpus", "check_structure"}, report
    vocabulary = _imports(_ROOT / "scripts" / "corpus_vocabulary.py")
    assert vocabulary <= set(sys.stdlib_module_names), vocabulary


_NOT_A_CORPUS = [
    pytest.param('{"nodes": null}', "`nodes` is null, not a list", id="nodes-null"),
    pytest.param('{"nodes": "ab"}', "`nodes` is a str, not a list", id="nodes-str"),
    pytest.param("{}", "`nodes` is missing", id="nodes-missing"),
    pytest.param("[]", "is a list, not an object", id="not-an-object"),
    pytest.param("{", "is not JSON", id="not-json"),
]


@pytest.mark.parametrize("flags", [(), ("--json",)], ids=["text", "json"])
@pytest.mark.parametrize("text, why", _NOT_A_CORPUS)
def test_a_corpus_without_a_nodes_list_is_refused_as_an_input_fault(
    tmp_path, capsys, text, why, flags
):
    """A corpus that is not an object with a `nodes` list cannot be counted:
    the report refuses it with USAGE and one line naming the file, what is
    wrong with it and how to get a good one, instead of a traceback or a
    count over nothing."""
    out = tmp_path / "corpus.json"
    out.write_text(text)
    assert ar.main(["--corpus", str(out), *flags]) == ExitCode.USAGE
    captured = capsys.readouterr()
    assert captured.out == ""
    (line,) = captured.err.splitlines()
    assert why in line and str(out) in line, line
    assert "build_corpus.py" in line, line


@pytest.mark.parametrize("bucket", ["unowned", "unknown", "defaulted"])
@pytest.mark.parametrize(
    "corpus, why",
    [
        pytest.param({}, "`nodes` is missing", id="nodes-missing"),
        pytest.param({"nodes": None}, "`nodes` is null", id="nodes-null"),
        pytest.param({"nodes": "ab"}, "`nodes` is a str", id="nodes-str"),
        pytest.param([], "is a list, not an object", id="not-an-object"),
    ],
)
def test_a_library_caller_s_corpus_without_a_nodes_list_is_refused(bucket, corpus, why):
    """A caller that imports the report and hands a bucket a corpus with no
    `nodes` list gets the ValueError the report's own reader raises, never
    an empty bucket that reads as every node owned."""
    with pytest.raises(ValueError, match=why):
        getattr(ar, bucket)(corpus)
