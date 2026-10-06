"""
title: Unit — check_structure check_B (the closed directory taxonomy)
kind: tests
layer: n/a
summary: check_B's rule, pinned: the top level is a closed vocabulary — a non-hidden root directory is a CONVENTIONS §2 row or a name declared in config/project.json structure.extra_toplevel, and anything else is an error naming both fixes. A declaration must exist, must not repeat a row, and must be a plain top-level name; a malformed one still fails closed. Every admitted top-level directory and every directory directly under agents/ (each agents/<name>/ and the shared agents/tools/) carries README.md and CLAUDE.md, and no other nested directory is required to. An undeclared symlinked directory warns, because no check reads through a link; it never errors and is never silent.
"""

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


def _label(dirpath):
    """Give a directory the two label files check_B looks for."""
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "README.md").write_text("# r\n", encoding="utf-8")
    (dirpath / "CLAUDE.md").write_text("# c\n", encoding="utf-8")
    return dirpath


def _manifest(root, data):
    """Write config/project.json as the given JSON value."""
    (root / "config" / "project.json").write_text(json.dumps(data), encoding="utf-8")


def _declare(root, value):
    """Declare `value` as structure.extra_toplevel."""
    _manifest(root, {"structure": {"extra_toplevel": value}})


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A labelled, taxonomy-only root with the gate's module state isolated.

    ROOT is a CHILD of tmp_path so a symlink target can live outside the root,
    which is the case the symlink rule is about. The config memo is reset too:
    it is keyed by relpath, so it would otherwise leak one test's manifest into
    the next.
    """
    root = tmp_path / "repo"
    for d in ("src", "tests", "docs", "config"):
        _label(root / d)
    monkeypatch.setattr(cs, "ROOT", str(root))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    return root


def _rerun(monkeypatch):
    """Fresh gate state for a second check_B over the same tree."""
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    cs.check_B()


def test_a_labelled_taxonomy_tree_passes(repo):
    """The vacuity control: every negative test below starts from this tree."""
    cs.check_B()
    assert cs.errors == [] and cs.warnings == []


@pytest.mark.parametrize(
    "dirname, missing",
    [("docs", "CLAUDE.md"), ("src", "README.md"), ("scripts", "CLAUDE.md")],
    ids=["required-row", "required-row-readme", "optional-row"],
)
def test_a_taxonomy_directory_without_a_label_errors(repo, dirname, missing):
    """A §2 row is admitted by the vocabulary, never excused from its labels.

    scripts/ is a row the fixture does not create, so the case covers a row
    that is present but not in REQUIRED_TOPLEVEL.
    """
    _label(repo / dirname)
    (repo / dirname / missing).unlink()
    cs.check_B()
    assert cs.errors == ["%s/: missing %s" % (dirname, missing)], cs.errors
    assert cs.warnings == []


def test_a_missing_required_top_level_directory_errors(repo):
    for f in ("README.md", "CLAUDE.md"):
        (repo / "tests" / f).unlink()
    (repo / "tests").rmdir()
    cs.check_B()
    assert cs.errors == ["required top-level dir 'tests/' is missing"], cs.errors


@pytest.mark.parametrize("with_manifest", [True, False])
def test_an_undeclared_top_level_directory_errors_and_names_both_fixes(
    repo, with_manifest
):
    (repo / "parked").mkdir()
    (repo / "parked" / "notes.txt").write_text("x\n", encoding="utf-8")
    if with_manifest:
        _declare(repo, [])
    else:
        assert not (repo / "config" / "project.json").exists()
    cs.check_B()
    assert len(cs.errors) == 1, cs.errors
    msg = cs.errors[0]
    assert msg.startswith("parked/"), msg
    assert "config/project.json" in msg and "structure.extra_toplevel" in msg, msg
    assert "move" in msg, msg
    assert cs.warnings == []


def test_labels_do_not_stand_in_for_a_declaration(repo):
    _label(repo / "parked")
    cs.check_B()
    assert len(cs.errors) == 1, cs.errors
    assert cs.errors[0].startswith(
        "parked/: top-level directory is not in the taxonomy"
    )


def test_a_declared_directory_without_labels_errors(repo, monkeypatch):
    (repo / "parked").mkdir()
    _declare(repo, ["parked"])
    cs.check_B()
    assert sorted(cs.errors) == [
        "parked/: missing CLAUDE.md",
        "parked/: missing README.md",
    ]
    _label(repo / "parked")
    _rerun(monkeypatch)
    assert cs.errors == [] and cs.warnings == []


@pytest.mark.parametrize("shape", ["absent", "file", "dangling-link"])
def test_a_stale_declaration_errors(repo, shape):
    gone = repo / "gone"
    if shape == "file":
        gone.write_text("x\n", encoding="utf-8")
    elif shape == "dangling-link":
        os.symlink(str(repo / "missing"), str(gone))
    _declare(repo, ["gone"])
    cs.check_B()
    assert len(cs.errors) == 1, cs.errors
    assert "gone" in cs.errors[0] and "does not exist" in cs.errors[0], cs.errors


def test_declaring_a_taxonomy_directory_is_redundant(repo):
    _declare(repo, ["docs"])
    cs.check_B()
    assert len(cs.errors) == 1, cs.errors
    assert "docs" in cs.errors[0] and "already in the taxonomy" in cs.errors[0]


@pytest.mark.parametrize(
    "value, expect",
    [
        ([".github"], "'.github' is outside the taxonomy rule"),
        (["node_modules"], "'node_modules' is outside the taxonomy rule"),
        (["src/zzz"], "'src/zzz' is not a top-level directory name"),
        ([""], "'' is not a top-level directory name"),
        ([3], "3 is not a top-level directory name"),
        (["parked", "parked"], "names 'parked' twice"),
    ],
    ids=["hidden", "ignored", "nested", "empty", "not-a-string", "duplicate"],
)
def test_a_declaration_the_rule_never_consults_errors(repo, value, expect):
    """Each rejection is its own branch, so each case asserts its own wording.

    Every declared path that can exist does exist (and is labelled), so the
    stale-declaration error cannot stand in for the branch under test: a
    mutant that drops the branch accepts the name and yields zero errors.
    """
    _label(repo / "parked")
    _label(repo / ".github")
    _label(repo / "node_modules")
    _label(repo / "src" / "zzz")
    if value != ["parked", "parked"]:
        value = value + ["parked"]  # parked/ stays legitimately declared
    _declare(repo, value)
    cs.check_B()
    assert len(cs.errors) == 1, cs.errors
    assert cs.errors[0].startswith("config/project.json: structure.extra_toplevel "), (
        cs.errors
    )
    assert expect in cs.errors[0], cs.errors


@pytest.mark.parametrize(
    "text, expect",
    [
        (json.dumps({"structure": "x"}), "structure must be an object"),
        (json.dumps({"structure": []}), "structure must be an object"),
        (
            json.dumps({"structure": {"extra_toplevel": "parked"}}),
            "structure.extra_toplevel must be a list",
        ),
        ("{not json", "unreadable (invalid JSON"),
    ],
    ids=["structure-str", "structure-list", "names-str", "invalid-json"],
)
def test_a_malformed_declaration_is_an_error_and_still_fails_closed(repo, text, expect):
    """A broken manifest declares nothing, so it can never turn the gate green."""
    _label(repo / "parked")
    (repo / "config" / "project.json").write_text(text, encoding="utf-8")
    cs.check_B()
    assert len(cs.errors) == 2, cs.errors
    assert any(e.startswith("config/project.json") and expect in e for e in cs.errors)
    assert any(e.startswith("parked/: top-level directory") for e in cs.errors)


def test_hidden_ignored_and_non_directory_entries_are_out_of_scope(repo):
    for d in (".github", ".cache", "node_modules", "build", "__pycache__"):
        (repo / d).mkdir()
    (repo / "Makefile").write_text("all:\n", encoding="utf-8")
    os.symlink(str(repo / "missing"), str(repo / "ghost"))
    cs.check_B()
    assert cs.errors == [] and cs.warnings == []


def test_an_undeclared_symlinked_directory_warns_and_does_not_error(repo, tmp_path):
    (tmp_path / "outside").mkdir()
    os.symlink(str(tmp_path / "outside"), str(repo / "linked"))
    cs.check_B()
    assert cs.errors == []
    assert len(cs.warnings) == 1, cs.warnings
    assert cs.warnings[0].startswith("linked/") and "symlink" in cs.warnings[0]


def test_a_symlink_never_hides_a_real_directory(repo):
    (repo / "parked").mkdir()
    os.symlink("parked", str(repo / "alias"))
    cs.check_B()
    assert len(cs.errors) == 1 and cs.errors[0].startswith("parked/"), cs.errors
    assert len(cs.warnings) == 1 and cs.warnings[0].startswith("alias/"), cs.warnings


def test_a_declared_symlinked_directory_is_held_to_its_labels(
    repo, tmp_path, monkeypatch
):
    (tmp_path / "outside").mkdir()
    os.symlink(str(tmp_path / "outside"), str(repo / "linked"))
    _declare(repo, ["linked"])
    cs.check_B()
    assert sorted(cs.errors) == [
        "linked/: missing CLAUDE.md",
        "linked/: missing README.md",
    ]
    assert cs.warnings == []
    _label(tmp_path / "outside")
    _rerun(monkeypatch)
    assert cs.errors == [] and cs.warnings == []


def test_an_agent_directory_without_labels_errors(repo):
    _label(repo / "agents")
    (repo / "agents" / "newbot").mkdir()
    (repo / "agents" / "newbot" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "agents" / "newbot" / "__pycache__").mkdir()
    (repo / "agents" / "__pycache__").mkdir()
    (repo / "agents" / ".hidden").mkdir()
    _label(repo / "agents" / "labelled_bot")
    cs.check_B()
    assert len(cs.errors) == 2, cs.errors
    assert sorted(e.split(" (")[0] for e in cs.errors) == [
        "agents/newbot/: missing CLAUDE.md",
        "agents/newbot/: missing README.md",
    ]
    assert all("sections 10 and 13" in e for e in cs.errors), cs.errors


def test_the_shared_tools_directory_is_held_and_cited_as_such(repo):
    """agents/tools/ is not an agent (§10, not §13); the rule and message say so.

    The gate labels every immediate subdirectory of agents/, so its message
    must not call agents/tools/ an agent directory under §13 alone.
    """
    _label(repo / "agents")
    (repo / "agents" / "tools").mkdir()
    cs.check_B()
    assert sorted(e.split(" (")[0] for e in cs.errors) == [
        "agents/tools/: missing CLAUDE.md",
        "agents/tools/: missing README.md",
    ], cs.errors
    for e in cs.errors:
        assert "an agent directory" not in e, e
        assert "directly under agents/" in e and "sections 10 and 13" in e, e


def test_other_nested_directories_need_no_labels(repo):
    """Pins the narrow nested rule so it cannot widen silently."""
    (repo / "src" / "zzz").mkdir()
    (repo / "docs" / "adr").mkdir()
    (repo / "tests" / "unit" / "scripts").mkdir(parents=True)
    cs.check_B()
    assert cs.errors == [] and cs.warnings == []
