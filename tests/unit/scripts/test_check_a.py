"""
title: Unit — check_structure check_A (frontmatter lifecycle symmetry)
kind: tests
layer: n/a
summary: check_A's lifecycle rule, pinned: a document whose status says it has been replaced must name its replacement. `deprecated` has required `superseded_by` since the first frontmatter check; `superseded` — the ADR lifecycle's word for the same fact — did not, so an ADR could be marked superseded by nothing and the corpus's "follow the chain to the live version" promise ended at a dead end. The two statuses are one rule with two vocabularies. A document stating a looser visibility than a README.md on its chain is an error, and a file reached by a link and its target is judged once, at the path build_corpus keeps for it, against the chain build_corpus ranks the node by: the chain of every path the walk reaches the one real file by, so the level it names is the strictest of them whichever directory sorts first. A README.md the walk skips (in `build/`, or a directory named README.md) is read by the one reader build_corpus ranks a node by, so a BOM-saved one, a dangling or looping link, a directory, a mode-000 file and a value outside the vocabulary each get the level the corpus serves and the check_A error a walked README.md of that shape gets.
"""

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway root with the gate's module-level state isolated."""
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    return tmp_path


def _doc(path, status, superseded_by=None):
    lines = [
        "---",
        "title: T",
        "kind: adr",
        "layer: n/a",
        "status: %s" % status,
        "owner: someone",
        "summary: S",
        "id: %s" % path.stem,
        "created: 2026-01-01",
        "updated: 2026-01-01",
        "visibility: internal",
        "canonical: true",
    ]
    if superseded_by:
        lines.append("superseded_by: %s" % superseded_by)
    lines.append("---")
    path.write_text("\n".join(lines) + "\n# T\n", encoding="utf-8")
    return path


def _lifecycle_errors():
    return [e for e in cs.errors if "superseded_by" in e]


@pytest.mark.parametrize("status", ["deprecated", "superseded"])
def test_a_replaced_document_that_names_no_replacement_errors(repo, status):
    cs.check_frontmatter(str(_doc(repo / "a.md", status)), {})
    errs = _lifecycle_errors()
    assert len(errs) == 1 and status in errs[0], cs.errors


@pytest.mark.parametrize("status", ["deprecated", "superseded"])
def test_a_replaced_document_that_names_its_replacement_passes(repo, status):
    cs.check_frontmatter(str(_doc(repo / "a.md", status, "docs/adr/0010-x.md")), {})
    assert _lifecycle_errors() == [], cs.errors


@pytest.mark.parametrize("status", ["accepted", "proposed", "stable", "draft"])
def test_a_live_document_needs_no_replacement(repo, status):
    cs.check_frontmatter(str(_doc(repo / "a.md", status)), {})
    assert _lifecycle_errors() == [], cs.errors


# --- a child stating a looser visibility than a README above it -------------
#
# The corpus gives a node the strictest visibility on its README chain
# (scripts/check_structure.py strictest_visibility), so a looser level stated
# below a README is overridden in silence; check_A names the contradiction.

_ORDER = cs.VISIBILITY_ORDER
_PAIRS = [(a, b) for a in _ORDER for b in _ORDER]


def _contradictions(stated):
    return cs._visibility_contradictions(stated)


@pytest.mark.parametrize("above, below", _PAIRS)
def test_a_looser_child_is_named_and_an_equal_or_stricter_one_is_not(above, below):
    found = _contradictions({"README.md": above, "docs/plan.md": below})
    if _ORDER.index(below) < _ORDER.index(above):
        assert len(found) == 1, found
        message = found[0]
        assert message.startswith("docs/plan.md: visibility '%s'" % below), message
        assert "'%s'" % above in message and "README.md" in message, message
    else:
        assert found == [], found


def test_the_message_names_the_nearest_readme_at_the_strictest_level():
    found = _contradictions(
        {
            "README.md": "confidential",
            "src/README.md": "confidential",
            "src/backend/README.md": "public",
            "src/backend/AGENT.md": "internal",
        }
    )
    by_path = {m.split(":", 1)[0]: m for m in found}
    assert sorted(by_path) == ["src/backend/AGENT.md", "src/backend/README.md"], found
    assert "stated by src/README.md" in by_path["src/backend/AGENT.md"], found
    assert "stated by src/README.md" in by_path["src/backend/README.md"], found
    assert "CONVENTIONS §1" in by_path["src/backend/AGENT.md"], found


def test_a_readme_is_judged_against_the_readmes_above_and_not_itself():
    assert _contradictions({"docs/README.md": "public"}) == []
    found = _contradictions({"README.md": "internal", "docs/README.md": "public"})
    assert len(found) == 1 and found[0].startswith("docs/README.md:"), found


def test_a_sibling_or_a_non_readme_above_is_not_an_ancestor():
    assert (
        _contradictions(
            {
                "docs/AGENT.md": "restricted",
                "docs/other/README.md": "restricted",
                "docs/plan.md": "public",
            }
        )
        == []
    )


def test_a_value_outside_the_vocabulary_is_left_to_the_invalid_visibility_error():
    assert _contradictions({"README.md": "secret", "docs/plan.md": "public"}) == []
    assert _contradictions({"README.md": "internal", "docs/plan.md": "open"}) == []


def test_check_a_reports_the_contradiction_over_a_tree(repo):
    readme = _doc(repo / "README.md", "stable").read_text(encoding="utf-8")
    (repo / "README.md").write_text(
        readme.replace("visibility: internal", "visibility: confidential"),
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    _doc(repo / "docs" / "plan.md", "stable")
    cs.check_A()
    found = [e for e in cs.errors if "less restrictive" in e]
    assert len(found) == 1 and found[0].startswith("docs/plan.md:"), cs.errors


def _stated(path, visibility):
    """A governed document at *path* that states *visibility*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _doc(path, "stable").read_text(encoding="utf-8")
    path.write_text(
        text.replace("visibility: internal", "visibility: %s" % visibility),
        encoding="utf-8",
    )


def _linked_tree(repo, link_dir, target_dir, plan_visibility):
    """`docs/a-open/plan.md` links to `docs/z-secret/plan.md`, which states
    *plan_visibility*; the directories' README.md files state *link_dir* and
    *target_dir* (None states none). The sorted walk meets the link first, so
    build_corpus keeps the doc under the link's path."""
    _stated(repo / "README.md", "public")
    if link_dir:
        _stated(repo / "docs" / "a-open" / "README.md", link_dir)
    if target_dir:
        _stated(repo / "docs" / "z-secret" / "README.md", target_dir)
    _stated(repo / "docs" / "z-secret" / "plan.md", plan_visibility)
    (repo / "docs" / "a-open").mkdir(exist_ok=True)
    (repo / "docs" / "a-open" / "plan.md").symlink_to("../z-secret/plan.md")


def _served(repo):
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    import build_corpus as bc

    return {
        n["node_id"]: (n["path"], n["visibility"])
        for n in bc.build_corpus(str(repo))["nodes"]
    }


# (link directory's README, target directory's README, the doc's own level,
# the README the message names, the level the corpus serves)
_LINKED = [
    pytest.param(
        None,
        "confidential",
        "public",
        "docs/z-secret/README.md",
        "confidential",
        id="target-stricter-public",
    ),
    pytest.param(
        None,
        "confidential",
        "internal",
        "docs/z-secret/README.md",
        "confidential",
        id="target-stricter-internal",
    ),
    pytest.param(
        "restricted",
        "public",
        "public",
        "docs/a-open/README.md",
        "restricted",
        id="link-stricter",
    ),
    pytest.param(
        "restricted",
        "confidential",
        "public",
        "docs/a-open/README.md",
        "restricted",
        id="link-strictest-of-two",
    ),
]


@pytest.mark.parametrize("link_dir, target_dir, own, where, level", _LINKED)
def test_check_a_judges_a_linked_file_where_the_corpus_serves_it(
    repo, link_dir, target_dir, own, where, level
):
    """build_corpus keeps a linked doc under the first path of its sorted
    walk and ranks it by served_chain; check_A judges the file at that path
    by that chain, so it names that path, the README that wins and the level
    the corpus serves, whether the link's directory or the target's is the
    stricter."""
    _linked_tree(repo, link_dir, target_dir, own)
    cs.check_A()
    found = [e for e in cs.errors if "less restrictive" in e]
    assert len(found) == 1, cs.errors
    message = found[0]
    assert message.startswith("docs/a-open/plan.md: visibility '%s'" % own), message
    assert "stated by %s" % where in message, message
    assert "serves it as '%s'" % level in message, message
    assert _served(repo)["plan"] == ("docs/a-open/plan.md", level)


def test_a_linked_file_as_strict_as_its_served_chain_is_no_contradiction(repo):
    _linked_tree(repo, "restricted", "public", "restricted")
    cs.check_A()
    assert [e for e in cs.errors if "less restrictive" in e] == [], cs.errors


def test_a_link_into_a_sibling_whose_name_extends_the_root_s_takes_no_chain_there(
    tmp_path, monkeypatch
):
    """`repo-x` starts with the text `repo` but is not inside it, so a file
    linked in from `repo-x` takes only the chain of the path it is walked by.
    The tree links `repo-x`'s restricted README.md in elsewhere, so a chain
    that climbed `repo-x` would reach a README check_A has read, and the
    public file would be a false contradiction."""
    repo = tmp_path / "repo"
    monkeypatch.setattr(cs, "ROOT", str(repo))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    _stated(repo / "README.md", "public")
    _stated(tmp_path / "repo-x" / "README.md", "restricted")
    _stated(tmp_path / "repo-x" / "plan.md", "public")
    (repo / "docs" / "a").mkdir(parents=True)
    (repo / "docs" / "a" / "README.md").symlink_to(tmp_path / "repo-x" / "README.md")
    (repo / "docs" / "plan.md").symlink_to(tmp_path / "repo-x" / "plan.md")
    cs.check_A()
    assert [e for e in cs.errors if "less restrictive" in e] == [], cs.errors
    assert _served(repo)["plan"] == ("docs/plan.md", "public")


def test_check_a_names_a_linked_file_where_the_corpus_does_in_any_walk_order(
    repo, monkeypatch
):
    """os.walk yields entries in the filesystem's order. check_A sorts its
    walk as build_corpus does, so with the order reversed it still runs the
    frontmatter check, and names the contradiction, at the path the corpus
    keeps."""
    _linked_tree(repo, None, "confidential", "public")
    plan = repo / "docs" / "z-secret" / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("title: T\n", ""))
    real_walk = cs.os.walk

    def reversed_walk(top, *args, **kwargs):
        for dirpath, dirnames, filenames in real_walk(top, *args, **kwargs):
            dirnames.reverse()
            filenames.reverse()
            yield dirpath, dirnames, filenames

    monkeypatch.setattr(cs.os, "walk", reversed_walk)
    cs.check_A()
    paths = {e.split(":", 1)[0] for e in cs.errors}
    named = sorted(p for p in paths if p.endswith("plan.md"))
    assert named == ["docs/a-open/plan.md"], cs.errors
    assert any("title" in e for e in cs.errors), cs.errors
    assert any("less restrictive" in e for e in cs.errors), cs.errors


# --- one real file reached by several paths ---------------------------------
#
# (a README level per directory role, the links as (link role, target role),
# the level the corpus serves), each tree given twice with its directory names
# swapped: the strictest chain of every path decides, whichever sorts first.
_REACHED = [
    pytest.param(
        {"target": "public", "link": "confidential"},
        [("link", "target")],
        "confidential",
        id="stricter-link-directory",
    ),
    pytest.param(
        {"target": "public", "low": "internal", "high": "restricted"},
        [("low", "target"), ("high", "target")],
        "restricted",
        id="two-links-of-different-levels",
    ),
    pytest.param(
        {"first": "public", "middle": "restricted", "last": "internal"},
        [("first", "middle"), ("middle", "last")],
        "restricted",
        id="a-chain-of-links",
    ),
]


def _reached_tree(repo, levels, links, names):
    """Each role in *levels* a directory under `docs/` named from *names* in
    role order, its README.md stating the role's level; `plan.md` stating
    `public` is real in the one role no link starts from, and every other
    role holds a link to the role it names. Returns {role: directory}."""
    name = dict(zip(levels, names[: len(levels)], strict=True))
    _stated(repo / "README.md", "public")
    for role, level in levels.items():
        _stated(repo / "docs" / name[role] / "README.md", level)
    linked = {start for start, _ in links}
    (real,) = [role for role in levels if role not in linked]
    _stated(repo / "docs" / name[real] / "plan.md", "public")
    for start, to in links:
        (repo / "docs" / name[start] / "plan.md").symlink_to("../%s/plan.md" % name[to])
    return {role: "docs/%s" % name[role] for role in levels}


@pytest.mark.parametrize(
    "names", [("a", "m", "z"), ("z", "m", "a")], ids=["a-first", "z-first"]
)
@pytest.mark.parametrize("levels, links, level", _REACHED)
def test_check_a_judges_a_file_reached_by_several_paths_by_the_strictest_chain(
    repo, levels, links, level, names
):
    """build_corpus serves one real file at the strictest level of every
    chain that reaches it; check_A judges the file once, at the path the
    corpus keeps, against that level, and names it and a README.md that
    states it, so swapping the directory names changes neither."""
    dirs = _reached_tree(repo, levels, links, names)
    cs.check_A()
    found = [e for e in cs.errors if "less restrictive" in e]
    assert len(found) == 1, cs.errors
    message = found[0]
    kept = "%s/plan.md" % min(dirs.values())  # the sorted walk meets it first
    assert message.startswith("%s: visibility 'public'" % kept), message
    assert "serves it as '%s'" % level in message, message
    stating = [r for r, v in levels.items() if v == level]
    assert any("stated by %s/README.md" % dirs[r] in message for r in stating), message
    assert _served(repo)["plan"] == (kept, level)


# --- the path check_A keys a file by is the path the corpus keeps -----------


def test_a_readme_link_that_sorts_after_its_target_passes_the_target_s_level_on(
    repo,
):
    """`docs/z/README.md` links to the confidential `docs/a/README.md`, which
    the walk meets first, so check_A reads the level at the kept path; a doc
    in `docs/z` is judged by it, as build_corpus serves it."""
    _stated(repo / "README.md", "public")
    _stated(repo / "docs" / "a" / "README.md", "confidential")
    (repo / "docs" / "z").mkdir()
    (repo / "docs" / "z" / "README.md").symlink_to("../a/README.md")
    _stated(repo / "docs" / "z" / "plan.md", "public")
    cs.check_A()
    found = [e for e in cs.errors if "less restrictive" in e]
    assert len(found) == 1, cs.errors
    message = found[0]
    assert message.startswith("docs/z/plan.md: visibility 'public'"), message
    assert "stated by docs/a/README.md" in message, message
    assert _served(repo)["plan"] == ("docs/z/plan.md", "confidential")


def test_a_file_kept_at_a_path_check_a_does_not_govern_is_named_there(repo):
    """`agents/plan.md` links to `docs/s/plan.md`. The walk meets the link
    first, so the corpus keeps the doc at `agents/plan.md`, a path check_A
    does not govern; check_A reads the file at `docs/s/plan.md` and names
    the contradiction at the path the corpus serves."""
    _stated(repo / "README.md", "public")
    _stated(repo / "docs" / "s" / "README.md", "confidential")
    _stated(repo / "docs" / "s" / "plan.md", "public")
    (repo / "agents").mkdir()
    (repo / "agents" / "plan.md").symlink_to("../docs/s/plan.md")
    cs.check_A()
    found = [e for e in cs.errors if "less restrictive" in e]
    assert len(found) == 1, cs.errors
    message = found[0]
    assert message.startswith("agents/plan.md: visibility 'public'"), message
    assert "stated by docs/s/README.md" in message, message
    assert _served(repo)["plan"] == ("agents/plan.md", "confidential")


@pytest.mark.parametrize("ignored", ["build", "node_modules"])
def test_a_link_into_a_directory_the_walk_skips_is_judged_by_its_target_s_chain(
    repo, ignored
):
    """The walk never enters an IGNORE_DIRS directory, so check_A meets a
    README.md there only on a chain. It reads that README.md's level as
    build_corpus does, so a doc linked in from there is judged by the level
    the corpus serves it at."""
    _stated(repo / "README.md", "public")
    _stated(repo / ignored / "x" / "README.md", "confidential")
    _stated(repo / ignored / "x" / "plan.md", "public")
    (repo / "docs").mkdir()
    (repo / "docs" / "plan.md").symlink_to("../%s/x/plan.md" % ignored)
    cs.check_A()
    found = [e for e in cs.errors if "less restrictive" in e]
    assert len(found) == 1, cs.errors
    message = found[0]
    assert message.startswith("docs/plan.md: visibility 'public'"), message
    assert "stated by %s/x/README.md" % ignored in message, message
    assert _served(repo)["plan"] == ("docs/plan.md", "confidential")


# --- a README.md the walk skips is read as build_corpus reads it ------------
#
# scripts/check_structure.py read_readme is the one reader of a README.md's
# stated level: build_corpus ranks a node by what it returns, and check_A
# judges a README.md the walk never entered by the same value.


def _bom_readme(path):
    _stated(path, "confidential")
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())


def _dangling_readme(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to("gone.md")


def _looping_readme(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to("README.md")


def _directory_readme(path):
    path.mkdir(parents=True)


def _invalid_readme(path):
    _stated(path, "secret")


# (how build/x/README.md is made, the level the corpus serves docs/plan.md
# at, the check_A error that names build/x/README.md)
_SKIPPED_README = [
    pytest.param(_bom_readme, "confidential", "less restrictive", id="bom"),
    pytest.param(_dangling_readme, "unreadable-readme", "cannot read", id="dangling"),
    pytest.param(_looping_readme, "unreadable-readme", "cannot read", id="looping"),
    pytest.param(_directory_readme, "unreadable-readme", "cannot read", id="directory"),
    pytest.param(
        _invalid_readme, "secret", "invalid visibility 'secret'", id="invalid"
    ),
]


@pytest.mark.parametrize("make, served, verdict", _SKIPPED_README)
def test_check_a_judges_a_skipped_readme_by_the_level_the_corpus_serves(
    repo, make, served, verdict
):
    """`docs/plan.md` links to `build/x/plan.md`, which states `public`; the
    walk never enters `build/`, so check_A meets `build/x/README.md` only on
    the doc's chain. Whatever shape that README.md has, the corpus serves the
    doc at the level read_readme returns, and check_A names that README.md:
    a contradiction for a level it ranks, else the error it gives a walked
    README.md of the same shape."""
    _stated(repo / "README.md", "public")
    make(repo / "build" / "x" / "README.md")
    _stated(repo / "build" / "x" / "plan.md", "public")
    (repo / "docs").mkdir()
    (repo / "docs" / "plan.md").symlink_to("../build/x/plan.md")
    cs.check_A()
    found = [e for e in cs.errors if verdict in e]
    assert len(found) == 1, cs.errors
    if verdict == "less restrictive":
        assert found[0].startswith("docs/plan.md: visibility 'public'"), found
        assert "stated by build/x/README.md" in found[0], found
    else:
        assert found[0].startswith("build/x/README.md: "), found
    assert _served(repo)["plan"] == ("docs/plan.md", served)


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads a mode-000 file"
)
def test_a_skipped_readme_no_one_may_read_is_named_cannot_read(repo):
    """A mode-000 README.md in `build/` is a file the run cannot open: check_A
    names it `cannot read` with the fault, and the corpus serves the doc
    below it as unreadable."""
    _stated(repo / "README.md", "public")
    readme = repo / "build" / "x" / "README.md"
    _stated(readme, "public")
    _stated(repo / "build" / "x" / "plan.md", "public")
    (repo / "docs").mkdir()
    (repo / "docs" / "plan.md").symlink_to("../build/x/plan.md")
    readme.chmod(0)
    try:
        cs.check_A()
        served = _served(repo)["plan"]
    finally:
        readme.chmod(0o644)
    found = [e for e in cs.errors if e.startswith("build/x/README.md: cannot read (")]
    assert len(found) == 1 and "Permission denied" in found[0], cs.errors
    assert served == ("docs/plan.md", "unreadable-readme")


def test_kept_markdown_keeps_the_first_md_path_of_the_walked_paths_it_is_given():
    """kept_markdown reads only the walked paths it is handed, so check_A and
    build_corpus key a file by the walk each already made: the first `.md`
    path to each real file, and nothing for a real file with none."""
    walked = {
        "/r/docs/a/plan.md": ["/r/docs/a/plan.md", "/r/docs/z/plan.md"],
        "/r/AGENT.md": ["/r/AGENT", "/r/CLAUDE.md", "/r/AGENT.md"],
        "/r/m.py": ["/r/m.py"],
    }
    assert cs.kept_markdown(walked) == {
        "/r/docs/a/plan.md": "/r/docs/a/plan.md",
        "/r/AGENT.md": "/r/CLAUDE.md",
    }


def _mode_000_readme(path):
    _stated(path, "public")
    path.chmod(0)


def _bad_utf8_readme(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"---\ntitle: R\nvisibility: public\n\xff---\n")


_ROOT_IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0

# (how build/x/README.md is made, the level the corpus serves docs/plan.md
# at, the check_A error that names build/x/README.md)
_SKIPPED_README_UNDER_A_SILENT_DOC = [
    pytest.param(_dangling_readme, "unreadable-readme", "cannot read", id="dangling"),
    pytest.param(_looping_readme, "unreadable-readme", "cannot read", id="looping"),
    pytest.param(_directory_readme, "unreadable-readme", "cannot read", id="directory"),
    pytest.param(
        _mode_000_readme,
        "unreadable-readme",
        "cannot read",
        id="mode-000",
        marks=pytest.mark.skipif(_ROOT_IS_ROOT, reason="root reads a mode-000 file"),
    ),
    pytest.param(_bad_utf8_readme, "unreadable-readme", "cannot read", id="bad-utf8"),
    pytest.param(
        _invalid_readme, "secret", "invalid visibility 'secret'", id="invalid"
    ),
]


@pytest.mark.parametrize("make, served, verdict", _SKIPPED_README_UNDER_A_SILENT_DOC)
def test_check_a_names_a_skipped_readme_on_the_chain_of_a_doc_that_states_no_level(
    repo, make, served, verdict
):
    """`docs/plan.md` links to `build/x/plan.md`, which states no visibility,
    so there is no contradiction to find; the corpus still serves the doc at
    the level read_readme gives `build/x/README.md`. check_A reads the chain
    of every governed file, not only one that states a level, so it names a
    README.md it cannot read or whose value is outside the vocabulary."""
    _stated(repo / "README.md", "public")
    make(repo / "build" / "x" / "README.md")
    silent = repo / "build" / "x" / "plan.md"
    _stated(silent, "public")
    silent.write_text(
        silent.read_text(encoding="utf-8").replace("visibility: public\n", ""),
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    (repo / "docs" / "plan.md").symlink_to("../build/x/plan.md")
    readme = repo / "build" / "x" / "README.md"
    try:
        cs.check_A()
        served_at = _served(repo)["plan"]
    finally:
        # A mode-000 README.md left behind outlives the test in a kept tmp
        # directory; a link or a directory has no mode of its own to restore.
        if not readme.is_symlink() and readme.is_file():
            readme.chmod(0o644)
    found = [e for e in cs.errors if e.startswith("build/x/README.md: " + verdict)]
    assert len(found) == 1, cs.errors
    assert served_at == ("docs/plan.md", served)
