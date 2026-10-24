"""
title: Unit — the corpus's visibility fails closed along each node's README chain
kind: tests
layer: n/a
summary: build_corpus gives each doc, section, module and symbol the most restrictive visibility stated on its chain — its own frontmatter or docstring and every README.md from its directory up to the root — in scripts/check_structure.py VISIBILITY_ORDER, so a child README that states none, or states a looser level, can never hide a confidential parent; with nothing stated anywhere a node is `internal`, and a value outside the vocabulary outranks every member so check_corpus refuses each node under it. A file reached through a symlink takes the strictest of the path chain and its target's chain inside the root, and a README.md that cannot be read, a dangling or looping link included, passes on a marker that outranks every level.
"""

import itertools
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import build_corpus as bc  # noqa: E402
import check_corpus as cc  # noqa: E402
import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_ORDER = cs.VISIBILITY_ORDER


def _readme(doc_id, owner=None, visibility=None):
    head = "---\ntitle: %s\nkind: readme\nsummary: About %s.\nid: %s\n" % (
        doc_id,
        doc_id,
        doc_id,
    )
    if owner is not None:
        head += "owner: %s\n" % owner
    if visibility is not None:
        head += "visibility: %s\n" % visibility
    return head + "---\n# %s\n\n## Part\n\ntext\n" % doc_id


def _module(visibility=None):
    head = "title: M\nsummary: Does m.\n"
    if visibility is not None:
        head += "visibility: %s\n" % visibility
    return (
        '"""\n%s"""\n__all__ = ["f"]\n\n\ndef f():\n    """Return f."""\n    return 1\n'
        % (head)
    )


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _visibility(root):
    return {n["node_id"]: n["visibility"] for n in bc.build_corpus(str(root))["nodes"]}


# --- the order itself --------------------------------------------------------


def test_the_order_is_the_closed_vocabulary_least_restrictive_first():
    assert _ORDER == ("public", "internal", "confidential", "restricted")
    assert set(_ORDER) == cs.VISIBILITIES == cc.VISIBILITIES


def test_the_strictest_of_nothing_stated_is_none():
    assert cs.strictest_visibility([]) is None
    assert cs.strictest_visibility([None, ""]) is None


@pytest.mark.parametrize("a, b", list(itertools.product(_ORDER, repeat=2)))
def test_the_strictest_is_the_later_member_whatever_the_order_given(a, b):
    want = _ORDER[max(_ORDER.index(a), _ORDER.index(b))]
    assert cs.strictest_visibility([a, None, b]) == want
    assert cs.strictest_visibility([b, a]) == want


def test_a_value_outside_the_vocabulary_outranks_every_member():
    """It cannot be ranked, so it is kept rather than read as a looser level:
    the gates that refuse it then see it on every node it reaches."""
    assert cs.strictest_visibility(["restricted", "secret", "public"]) == "secret"


# --- modules and symbols -----------------------------------------------------


def test_an_owned_child_readme_with_no_visibility_cannot_hide_a_confidential_parent(
    tmp_path,
):
    """The KEEL-VIS-1 defect: the walk ended at the owned child README and
    its modules came out `internal`."""
    _write(tmp_path, "src/README.md", _readme("src-readme", None, "confidential"))
    _write(tmp_path, "src/backend/README.md", _readme("be-readme", "bob", None))
    _write(tmp_path, "src/backend/m.py", _module())
    vis = _visibility(tmp_path)
    assert vis["src/backend/m-py"] == "confidential"
    assert vis["src/backend/m-py::f"] == "confidential"


@pytest.mark.parametrize("parent, child", list(itertools.product(_ORDER, repeat=2)))
def test_a_module_takes_the_strictest_readme_on_its_chain(tmp_path, parent, child):
    _write(tmp_path, "src/README.md", _readme("src-readme", "alice", parent))
    _write(tmp_path, "src/backend/README.md", _readme("be-readme", "bob", child))
    _write(tmp_path, "src/backend/m.py", _module())
    want = _ORDER[max(_ORDER.index(parent), _ORDER.index(child))]
    vis = _visibility(tmp_path)
    assert vis["src/backend/m-py"] == want
    assert vis["src/backend/m-py::f"] == want


def test_the_root_readme_is_on_every_chain(tmp_path):
    _write(tmp_path, "README.md", _readme("root-readme", None, "restricted"))
    _write(tmp_path, "src/README.md", _readme("src-readme", "alice", "public"))
    _write(tmp_path, "src/m.py", _module("public"))
    assert _visibility(tmp_path)["src/m-py"] == "restricted"


def test_a_module_s_own_looser_visibility_does_not_beat_its_readme(tmp_path):
    _write(tmp_path, "src/README.md", _readme("src-readme", None, "confidential"))
    _write(tmp_path, "src/m.py", _module("public"))
    assert _visibility(tmp_path)["src/m-py"] == "confidential"


def test_a_module_s_own_stricter_visibility_stands(tmp_path):
    _write(tmp_path, "src/README.md", _readme("src-readme", None, "internal"))
    _write(tmp_path, "src/m.py", _module("restricted"))
    vis = _visibility(tmp_path)
    assert vis["src/m-py"] == "restricted"
    assert vis["src/m-py::f"] == "restricted"


def test_a_child_that_states_nothing_inherits_the_nearest_stated_level(tmp_path):
    """To publish a subtree, the README above it says `public`."""
    _write(tmp_path, "src/README.md", _readme("src-readme", None, "public"))
    _write(tmp_path, "src/backend/README.md", _readme("be-readme", "bob", None))
    _write(tmp_path, "src/backend/m.py", _module())
    assert _visibility(tmp_path)["src/backend/m-py"] == "public"


def test_nothing_stated_anywhere_is_internal(tmp_path):
    _write(tmp_path, "src/README.md", _readme("src-readme", "alice", None))
    _write(tmp_path, "src/m.py", _module())
    _write(tmp_path, "docs/README.md", _readme("docs-readme", "alice", None))
    vis = _visibility(tmp_path)
    assert vis["src/m-py"] == "internal"
    assert vis["docs-readme"] == "internal"


# --- documents and sections --------------------------------------------------


def test_a_doc_takes_the_strictest_readme_above_it_and_its_sections_follow(tmp_path):
    _write(tmp_path, "docs/README.md", _readme("docs-readme", None, "internal"))
    _write(
        tmp_path,
        "docs/secret/README.md",
        _readme("secret-readme", None, "confidential"),
    )
    _write(tmp_path, "docs/secret/plan.md", _readme("plan", "alice", "public"))
    vis = _visibility(tmp_path)
    assert vis["plan"] == "confidential"
    assert vis["plan#part"] == "confidential"
    assert vis["docs-readme"] == "internal"


def test_a_readme_takes_the_strictest_readme_above_its_own_directory(tmp_path):
    _write(tmp_path, "docs/README.md", _readme("docs-readme", None, "restricted"))
    _write(tmp_path, "docs/sub/README.md", _readme("sub-readme", None, "internal"))
    vis = _visibility(tmp_path)
    assert vis["sub-readme"] == "restricted"
    assert vis["sub-readme#part"] == "restricted"


def test_a_doc_s_own_stricter_visibility_stands(tmp_path):
    _write(tmp_path, "docs/README.md", _readme("docs-readme", None, "public"))
    _write(tmp_path, "docs/plan.md", _readme("plan", None, "confidential"))
    assert _visibility(tmp_path)["plan"] == "confidential"


def test_an_unknown_value_reaches_every_node_under_it_and_check_corpus_refuses_it(
    tmp_path,
):
    _write(tmp_path, "src/README.md", _readme("src-readme", None, "secret"))
    _write(tmp_path, "src/m.py", _module("public"))
    corpus = bc.build_corpus(str(tmp_path))
    vis = {n["node_id"]: n["visibility"] for n in corpus["nodes"]}
    assert vis["src/m-py"] == "secret" and vis["src/m-py::f"] == "secret"
    refused = [e for e in cc.validate(corpus) if "invalid visibility" in e]
    assert any("src/m-py::f" in e for e in refused), refused


# --- a node's file reached through a symlink, and a README that cannot be read


def test_a_doc_symlinked_into_an_open_directory_keeps_its_target_s_level(tmp_path):
    """The walk reaches the doc by its link first (`a-open` sorts before
    `z-secret`), so its level is the strictest of both chains: the path it
    was walked by and the file it really is."""
    _write(tmp_path, "docs/README.md", _readme("docs-readme", None, "internal"))
    _write(
        tmp_path, "docs/z-secret/README.md", _readme("z-readme", None, "confidential")
    )
    _write(tmp_path, "docs/z-secret/plan.md", _readme("plan", "alice", None))
    (tmp_path / "docs" / "a-open").mkdir()
    (tmp_path / "docs" / "a-open" / "plan.md").symlink_to("../z-secret/plan.md")
    vis = _visibility(tmp_path)
    assert vis["plan"] == "confidential"
    assert vis["plan#part"] == "confidential"


def test_a_module_symlinked_into_an_open_package_keeps_its_target_s_level(tmp_path):
    _write(tmp_path, "src/a/README.md", _readme("a-readme", "bob", "public"))
    _write(tmp_path, "src/z/README.md", _readme("z-readme", "bob", "restricted"))
    _write(tmp_path, "src/z/m.py", _module())
    (tmp_path / "src" / "a" / "m.py").symlink_to("../z/m.py")
    vis = _visibility(tmp_path)
    assert vis["src/a/m-py"] == "restricted"
    assert vis["src/z/m-py"] == "restricted"


def test_a_symlink_to_a_file_outside_the_root_reads_no_readme_outside_it(tmp_path):
    """Only the tree's own README.md files are a chain: the walk never climbs
    out of the root to a README.md that is not part of the project."""
    repo = tmp_path / "repo"
    _write(tmp_path, "outside/README.md", _readme("out-readme", None, "restricted"))
    _write(tmp_path, "outside/x.md", _readme("x", None, None))
    _write(repo, "docs/README.md", _readme("docs-readme", None, "internal"))
    (repo / "docs" / "x.md").symlink_to(tmp_path / "outside" / "x.md")
    assert _visibility(repo)["x"] == "internal"


def test_a_symlink_into_a_sibling_whose_name_extends_the_root_s_is_outside_it(
    tmp_path,
):
    """`repo-x` starts with the text `repo` but is not inside it: the target's
    chain is read only below the root as a directory, never by string prefix."""
    repo = tmp_path / "repo"
    _write(tmp_path, "repo-x/README.md", _readme("x-readme", None, "restricted"))
    _write(tmp_path, "repo-x/x.md", _readme("x", None, None))
    _write(repo, "docs/README.md", _readme("docs-readme", None, "internal"))
    (repo / "docs" / "x.md").symlink_to(tmp_path / "repo-x" / "x.md")
    assert _visibility(repo)["x"] == "internal"


def test_a_root_reached_through_a_link_spells_the_whole_chain_under_it(tmp_path):
    """A root given as a link (a checkout under a linked work directory) still
    spells every README.md on a linked file's chain under the root as given,
    the target's included, so a reader can name each one relative to it."""
    real = tmp_path / "real"
    _write(real, "docs/z/README.md", _readme("z-readme", None, "confidential"))
    _write(real, "docs/z/plan.md", _readme("plan", None, None))
    (real / "docs" / "a").mkdir()
    (real / "docs" / "a" / "plan.md").symlink_to("../z/plan.md")
    root = tmp_path / "linked"
    root.symlink_to(real)
    chain = cs.readme_chain(str(root / "docs" / "a" / "plan.md"), str(root))
    assert str(root / "docs" / "z" / "README.md") in chain, chain
    assert all(r.startswith(str(root) + "/") for r in chain), chain
    assert _visibility(root)["plan"] == "confidential"


def test_a_symlink_changes_no_owner(tmp_path):
    """Only visibility reads the target's chain; a module still inherits the
    owner of the package README.md on the path it was walked by."""
    _write(tmp_path, "src/a/README.md", _readme("a-readme", "alice", None))
    _write(tmp_path, "src/z/README.md", _readme("z-readme", "zed", "restricted"))
    _write(tmp_path, "src/z/m.py", _module())
    (tmp_path / "src" / "a" / "m.py").symlink_to("../z/m.py")
    nodes = {n["node_id"]: n for n in bc.build_corpus(str(tmp_path))["nodes"]}
    linked = nodes["src/a/m-py"]
    assert linked["visibility"] == "restricted"
    assert (linked["owner"], linked["owner_source"]) == ("alice", "inherited")
    assert nodes["src/z/m-py"]["owner"] == "zed"


def test_an_unreadable_readme_makes_every_node_below_it_unrankable(tmp_path):
    """A README that cannot be decoded may state any level, so nothing below
    it is ranked as looser: each node keeps a marker check_corpus refuses."""
    _write(tmp_path, "src/README.md", _readme("src-readme", None, "public"))
    (tmp_path / "src" / "pkg").mkdir()
    (tmp_path / "src" / "pkg" / "README.md").write_bytes(
        b"---\ntitle: P\nvisibility: confidential\n\xff---\n"
    )
    _write(tmp_path, "src/pkg/m.py", _module("public"))
    _write(tmp_path, "src/pkg/d.md", _readme("d", None, "public"))
    corpus = bc.build_corpus(str(tmp_path))
    vis = {n["node_id"]: n["visibility"] for n in corpus["nodes"]}
    for node_id in ("src/pkg/m-py", "src/pkg/m-py::f", "d", "d#part"):
        assert vis[node_id] not in _ORDER, (node_id, vis[node_id])
        assert cs.strictest_visibility(["restricted", vis[node_id]]) == vis[node_id]
    assert vis["src-readme"] == "public"
    refused = [e for e in cc.validate(corpus) if "invalid visibility" in e]
    assert any("src/pkg/m-py" in e for e in refused), refused


@pytest.mark.parametrize("target", ["../../gone/README.md", "README.md"])
def test_a_readme_link_that_reaches_no_file_is_unreadable(tmp_path, target):
    """A README.md that exists as a name but cannot be opened (a dangling
    link, or one that loops to itself) may state any level, so it is
    unreadable like a decode fault, never absent."""
    _write(tmp_path, "src/README.md", _readme("src-readme", None, "public"))
    (tmp_path / "src" / "pkg").mkdir()
    (tmp_path / "src" / "pkg" / "README.md").symlink_to(target)
    _write(tmp_path, "src/pkg/m.py", _module("public"))
    _write(tmp_path, "src/pkg/d.md", _readme("d", None, "public"))
    vis = _visibility(tmp_path)
    for node_id in ("src/pkg/m-py", "src/pkg/m-py::f", "d", "d#part"):
        assert vis[node_id] == bc.UNREADABLE_VISIBILITY, (node_id, vis[node_id])
    assert vis["src-readme"] == "public"
