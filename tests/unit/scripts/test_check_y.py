"""
title: Unit — check_structure check_Y (template and project ADRs live in separate number spaces)
kind: tests
layer: n/a
summary: check_Y's rule, pinned: config/project.json `adr` names the project space, the template space, the template prefix and the digit count, and a missing or malformed block fails closed naming the key. An ADR in the project space is NNNN-<slug>.md and never carries the template prefix; an ADR in the template space is <prefix>NNNN-<slug>.md, and an unprefixed one is an error naming the project space as where it belongs. A number is unique within its space (both paths named), and the same number once in each space is clean. A template-space file is one `template_adrs` lists and every listed name is a file there, so a project's decision under a free K- number fails. A `kind: adr` document anywhere but directly in one of the two spaces fails, and a `.MD` name is judged. The block's path, unknown-key, bool-digit and list guards each fail closed. An ADR has kind adr and a title that begins ADR-<prefix?>NNNN: naming its own file. Both spaces empty is a warning, never silence. Keel's own tree is clean and the check sees every ADR in each space as config/project.json names them, never a keel-only fact: the same assertion passes on a tree that records a project ADR, and fails when the inventory loses one.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_BLOCK = {
    "project_dir": "docs/adr",
    "template_dir": "docs/adr/keel",
    "template_prefix": "K-",
    "number_digits": 4,
    "template_adrs": ["K-0001-theirs.md"],
}


def _adr(path, title, kind="adr"):
    """An ADR file with the frontmatter check_Y reads (kind, title)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '---\ntitle: "%s"\nkind: %s\nid: x-%s\n---\n\n# %s\n'
        % (title, kind, path.stem, title),
        encoding="utf-8",
    )
    return path


def _manifest(root, block):
    data = {} if block is None else {"adr": block}
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "project.json").write_text(json.dumps(data), encoding="utf-8")


def _isolate(monkeypatch, root):
    monkeypatch.setattr(cs, "ROOT", str(root))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A tree with the default block, one project ADR and one template ADR."""
    root = tmp_path / "repo"
    _manifest(root, _BLOCK)
    _adr(root / "docs/adr/0001-our-first.md", "ADR-0001: Our first")
    _adr(root / "docs/adr/keel/K-0001-theirs.md", "ADR-K-0001: Theirs")
    # Labels and non-.md files are not ADRs: never judged.
    for d in ("docs/adr", "docs/adr/keel"):
        for name in ("README.md", "AGENT.md", "CLAUDE.md"):
            (root / d / name).write_text("# label\n", encoding="utf-8")
        (root / d / "notes.txt").write_text("not an adr\n", encoding="utf-8")
    _isolate(monkeypatch, root)
    return root


def _ys():
    cs.check_Y()
    return list(cs.errors), list(cs.warnings)


def _rerun(monkeypatch, root):
    _isolate(monkeypatch, root)
    return _ys()


def _tree_inventory_holds(monkeypatch, root):
    """The tree at *root*: zero Y findings, and the inventory check_Y judges
    equals an independent listing of each space config/project.json `adr`
    names. Every value comes from root's own config, never a keel-only fact, so
    the same assertion holds in a project that records ADRs of its own. The
    template space must be non-empty and as long as `template_adrs` -- a pass
    over zero ADRs would be vacuous."""
    _isolate(monkeypatch, root)
    errs, warns = _ys()
    assert errs == [] and warns == [], (errs, warns)
    with open(str(root / "config" / "project.json"), encoding="utf-8") as fh:
        config = json.load(fh)
    policy, perrs = cs.adr_policy(config)
    assert perrs == [], perrs
    tdir, pdir = policy["template_dir"], policy["project_dir"]
    listed = sorted(
        tdir + "/" + n
        for n in os.listdir(str(root / tdir))
        if n.startswith(policy["template_prefix"]) and n.endswith(".md")
    )
    assert listed and len(listed) == len(policy["template_adrs"]), listed
    project_name = re.compile(r"^\d{%d}-.+\.md$" % policy["number_digits"])
    project_listed = []
    if os.path.isdir(str(root / pdir)):
        project_listed = sorted(
            pdir + "/" + n
            for n in os.listdir(str(root / pdir))
            if project_name.match(n) and os.path.isfile(str(root / pdir / n))
        )
    spaces = cs.adr_inventory(policy)
    assert sorted(rel for _num, rel in spaces["template"]) == listed
    assert sorted(rel for _num, rel in spaces["project"]) == project_listed
    assert all(num is not None for num, _rel in spaces["project"]), spaces
    # The ownership list is the same set: every file the template ships.
    assert sorted(tdir + "/" + n for n in policy["template_adrs"]) == listed


def test_keel_tree_is_y_clean_and_sees_every_template_adr(monkeypatch):
    """The real tree. In keel the project space is empty, so its half of the
    assertion is vacuous here; test_the_tree_check_sees_a_project_adr is its
    non-vacuity proof."""
    _tree_inventory_holds(monkeypatch, _ROOT)


def test_the_tree_check_sees_a_project_adr(repo, monkeypatch):
    """The same check on a tree that records an ADR of its own passes, and an
    inventory that loses the project space fails it (mutation proof)."""
    _tree_inventory_holds(monkeypatch, repo)
    real = cs.adr_inventory
    monkeypatch.setattr(
        cs, "adr_inventory", lambda policy: dict(real(policy), project=[])
    )
    with pytest.raises(AssertionError):
        _tree_inventory_holds(monkeypatch, repo)


def test_the_fixture_tree_is_clean(repo):
    """The vacuity control: every negative test starts from this tree."""
    assert _ys() == ([], [])


def test_y_rejects_template_prefix_in_project_space(repo, monkeypatch):
    """Mutation pair: the same file is clean in the template space and an
    error, naming the template space, in the project space."""
    _adr(repo / "docs/adr/keel/K-0002-moved.md", "ADR-K-0002: Moved")
    _manifest(repo, dict(_BLOCK, template_adrs=["K-0001-theirs.md", "K-0002-moved.md"]))
    assert _rerun(monkeypatch, repo) == ([], [])
    _manifest(repo, _BLOCK)
    os.rename(
        str(repo / "docs/adr/keel/K-0002-moved.md"),
        str(repo / "docs/adr/K-0002-moved.md"),
    )
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert "docs/adr/K-0002-moved.md" in errs[0], errs
    assert "docs/adr/keel" in errs[0] and "'K-'" in errs[0], errs


def test_y_rejects_unprefixed_adr_in_template_space(repo, monkeypatch):
    _adr(repo / "docs/adr/keel/0002-ours.md", "ADR-0002: Ours")
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert errs[0].startswith("docs/adr/keel/0002-ours.md:"), errs
    assert "belongs in docs/adr" in errs[0], errs


def test_y_rejects_a_name_outside_the_grammar_in_the_project_space(repo, monkeypatch):
    _adr(repo / "docs/adr/12-short.md", "ADR-12: Short")
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1 and errs[0].startswith("docs/adr/12-short.md:"), errs
    assert "NNNN-<slug>.md" in errs[0], errs


@pytest.mark.parametrize(
    "space, first, second",
    [
        ("docs/adr", "0001-our-first.md", "0001-our-second.md"),
        ("docs/adr/keel", "K-0001-theirs.md", "K-0001-theirs-again.md"),
    ],
    ids=["project", "template"],
)
def test_y_rejects_duplicate_number_within_a_space(
    repo, monkeypatch, space, first, second
):
    """The fixture holds 0001 once in each space and is clean: the number
    spaces are separate. A second 0001 inside one space is an error naming
    both paths."""
    prefix = "K-" if space.endswith("keel") else ""
    _adr(repo / space / second, "ADR-%s0001: Again" % prefix)
    if prefix:
        _manifest(repo, dict(_BLOCK, template_adrs=[first, second]))
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert "%s/%s" % (space, first) in errs[0], errs
    assert "%s/%s" % (space, second) in errs[0], errs


def test_y_title_must_name_its_file(repo, monkeypatch):
    _adr(repo / "docs/adr/0002-mistitled.md", "ADR-0003: Wrong number")
    _adr(repo / "docs/adr/keel/K-0002-unprefixed.md", "ADR-0002: Lost its prefix")
    _adr(repo / "docs/adr/0004-untitled.md", "A decision with no number")
    _adr(repo / "docs/adr/0005-a-doc.md", "ADR-0005: Not an adr", kind="doc")
    _manifest(
        repo,
        dict(_BLOCK, template_adrs=["K-0001-theirs.md", "K-0002-unprefixed.md"]),
    )
    errs, _w = _rerun(monkeypatch, repo)
    assert sorted(e.split(":")[0] for e in errs) == [
        "docs/adr/0002-mistitled.md",
        "docs/adr/0004-untitled.md",
        "docs/adr/0005-a-doc.md",
        "docs/adr/keel/K-0002-unprefixed.md",
    ], errs
    assert any("'ADR-0002:'" in e for e in errs), errs
    assert any("'ADR-K-0002:'" in e for e in errs), errs
    assert any("kind" in e and "'doc'" in e for e in errs), errs


def test_y_reads_its_spaces_from_config(tmp_path, monkeypatch):
    """Nothing about the spaces is hardcoded: another layout is judged by its
    own block, and docs/adr/keel -- keel's default -- is then not a space."""
    root = tmp_path / "repo"
    _manifest(
        root,
        {
            "project_dir": "docs/decisions",
            "template_dir": "docs/decisions/tpl",
            "template_prefix": "T-",
            "number_digits": 3,
            "template_adrs": ["T-001-theirs.md"],
        },
    )
    _adr(root / "docs/decisions/001-ours.md", "ADR-001: Ours")
    _adr(root / "docs/decisions/tpl/T-001-theirs.md", "ADR-T-001: Theirs")
    # Not a space here, so names under it are not judged (and not kind: adr,
    # which check_Y would place outside both spaces).
    _adr(root / "docs/adr/keel/K-9999-ignored.md", "not judged", kind="doc")
    _adr(root / "docs/adr/keel/garbage.md", "not judged", kind="doc")
    assert _rerun(monkeypatch, root) == ([], [])
    _adr(root / "docs/decisions/0002-four-digits.md", "ADR-0002: Four digits")
    _adr(root / "docs/decisions/T-002-misplaced.md", "ADR-T-002: Misplaced")
    errs, _w = _rerun(monkeypatch, root)
    assert sorted(e.split(":")[0] for e in errs) == [
        "docs/decisions/0002-four-digits.md",
        "docs/decisions/T-002-misplaced.md",
    ], errs


@pytest.mark.parametrize(
    "block, key",
    [
        (None, "adr"),
        (dict(_BLOCK, template_dir="docs/adr"), "adr.template_dir"),
        (dict(_BLOCK, template_prefix="9-"), "adr.template_prefix"),
        (dict(_BLOCK, number_digits="4"), "adr.number_digits"),
        (dict(_BLOCK, project_dir=""), "adr.project_dir"),
        (dict(_BLOCK, project_dir="/docs/adr"), "adr.project_dir"),
        (dict(_BLOCK, template_dir="docs/../keel"), "adr.template_dir"),
        (dict(_BLOCK, number_digit=4), "number_digit"),
        (dict(_BLOCK, number_digits=True), "adr.number_digits"),
        (dict(_BLOCK, template_adrs="K-0001-theirs.md"), "adr.template_adrs"),
        (dict(_BLOCK, template_adrs=["0001-theirs.md"]), "adr.template_adrs"),
        (dict(_BLOCK, template_adrs=["keel/K-0001-theirs.md"]), "adr.template_adrs"),
        (
            dict(_BLOCK, template_adrs=["K-0001-theirs.md", "K-0001-theirs.md"]),
            "adr.template_adrs",
        ),
    ],
    ids=[
        "missing",
        "same-dir",
        "digit-prefix",
        "non-int-digits",
        "empty-string",
        "absolute-dir",
        "dotdot-dir",
        "unknown-key",
        "bool-digits",
        "list-not-a-list",
        "list-unprefixed",
        "list-with-a-dir",
        "list-duplicate",
    ],
)
def test_y_fails_closed_on_a_missing_or_malformed_block(repo, monkeypatch, block, key):
    _manifest(repo, block)
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert errs[0].startswith("config/project.json:"), errs
    assert key in errs[0], errs


def test_y_warns_when_both_spaces_are_empty(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _manifest(root, dict(_BLOCK, template_adrs=[]))
    errs, warns = _rerun(monkeypatch, root)
    assert errs == [], errs
    assert len(warns) == 1 and "docs/adr" in warns[0] and "docs/adr/keel" in warns[0]


def test_y_rejects_an_adr_in_the_template_space_the_template_does_not_ship(
    repo, monkeypatch
):
    """A project's own decision written as docs/adr/keel/K-0002-*.md is named
    to the template's grammar but not shipped by it: the template's next
    K-0002 would land beside it on update. The file is an error naming the
    ownership list; the same file listed there (what the template does when it
    ships one) is clean -- the mutation pair."""
    _adr(repo / "docs/adr/keel/K-0002-ours.md", "ADR-K-0002: Ours")
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert errs[0].startswith("docs/adr/keel/K-0002-ours.md:"), errs
    assert "adr.template_adrs" in errs[0] and "docs/adr" in errs[0], errs
    _manifest(repo, dict(_BLOCK, template_adrs=["K-0001-theirs.md", "K-0002-ours.md"]))
    assert _rerun(monkeypatch, repo) == ([], [])


def test_y_rejects_a_listed_template_adr_the_tree_lacks(repo, monkeypatch):
    """The ownership list and the directory are one set: a listed name with no
    file is an error, so the list cannot drift from what ships."""
    _manifest(repo, dict(_BLOCK, template_adrs=["K-0001-theirs.md", "K-0002-gone.md"]))
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert "K-0002-gone.md" in errs[0] and "docs/adr/keel" in errs[0], errs


@pytest.mark.parametrize(
    "rel",
    [
        "docs/adr/proposed/0001-second.md",
        "docs/adr/proposed/K-0014-third.md",
        "docs/adr/keel/old/K-0001-theirs.md",
        "docs/decisions/0001-fourth.md",
    ],
    ids=["project-subdir", "prefixed-subdir", "template-subdir", "elsewhere"],
)
def test_y_rejects_an_adr_outside_both_spaces(repo, monkeypatch, rel):
    """A `kind: adr` document lives directly in one of the two spaces. One in a
    subdirectory or another folder would never be numbered against the rest,
    so three ADR-0001s could pass; it is an error naming both spaces. A
    document of another kind there is not an ADR and is not judged."""
    _adr(repo / rel, "ADR-0001: Elsewhere", kind="doc")
    assert _rerun(monkeypatch, repo) == ([], [])
    _adr(repo / rel, "ADR-0001: Elsewhere")
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert errs[0].startswith(rel + ":"), errs
    assert "docs/adr" in errs[0] and "docs/adr/keel" in errs[0], errs


def test_y_judges_an_upper_case_md_extension(repo, monkeypatch):
    """0002-a.MD is a Markdown file in the project space whose name is outside
    the grammar; a case-sensitive filter would never see it."""
    _adr(repo / "docs/adr/0002-a.MD", "ADR-0002: Shouting")
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1 and errs[0].startswith("docs/adr/0002-a.MD:"), errs
