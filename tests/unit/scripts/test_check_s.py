"""
title: Unit — check_structure check_S (roster parity)
kind: tests
layer: n/a
summary: check_S errors when a roster README disagrees with its directory — a member it does not name, a row naming something that is not a member, a missing `Member` first column, a missing `Not for` column, or a `Not for` cell left empty — and when config/project.json `rosters.readmes` disagrees with the READMEs that carry `## What ships here`: a listed README without the table, a listed path with no file, a malformed or doubled entry, or a headed README the list does not name. The list, not the heading, is the switch, so renaming the heading cannot silence the check, and an absent key fails closed.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_MEMBERS = {"build_corpus.py", "link_corpus.py", "jobs/"}

_README = """# Scripts

Prose.

## What ships here

| Member | Purpose | Not for |
|--------|---------|---------|
| `build_corpus.py` | builds the graph | linking it (that is `link_corpus.py`) |
| `jobs/` | scheduled doers | anything a human runs by hand (that is the top level) |
| `link_corpus.py` | adds edges | building nodes (that is `build_corpus.py`) |

## Later

More prose.
"""


def _find(text=_README, members=_MEMBERS, path="scripts/README.md"):
    return cs._roster_findings(path, text, members)


def test_a_roster_that_matches_its_directory_passes():
    assert _find() == []


def test_a_readme_without_the_heading_is_not_a_roster():
    """Opt-in: a README that never claims to list its directory is not held to it."""
    assert _find("# Scripts\n\nProse only.\n") == []


def test_a_member_the_roster_does_not_name_errors():
    errs = _find(members=_MEMBERS | {"new_thing.py"})
    assert (
        len(errs) == 1 and "new_thing.py" in errs[0] and "does not name" in errs[0]
    ), errs


def test_a_row_naming_a_non_member_errors():
    errs = _find(members=_MEMBERS - {"jobs/"})
    assert len(errs) == 1 and "jobs/" in errs[0] and "not" in errs[0], errs


def test_a_directory_member_matches_with_or_without_its_slash():
    text = _README.replace("| `jobs/` |", "| `jobs` |")
    assert _find(text) == []


def test_a_member_named_twice_errors():
    text = _README.replace(
        "| `link_corpus.py` |", "| `jobs/` | again | again |\n| `link_corpus.py` |"
    )
    errs = _find(text)
    assert len(errs) == 1 and "jobs/" in errs[0] and "twice" in errs[0], errs


def test_the_heading_with_no_table_under_it_errors():
    text = _README.split("| Member")[0] + "\nProse instead of a table.\n"
    errs = _find(text)
    assert len(errs) == 1 and "no table" in errs[0], errs


def test_a_first_column_not_named_member_errors():
    errs = _find(_README.replace("| Member |", "| File |"))
    assert len(errs) == 1 and "Member" in errs[0] and "File" in errs[0], errs


def test_a_missing_not_for_column_errors():
    text = _README.replace("| Not for |", "| Notes |")
    errs = _find(text)
    assert len(errs) == 1 and "Not for" in errs[0], errs


@pytest.mark.parametrize("empty", ["", "—", "-", "n/a", "N/A", "none"])
def test_an_empty_not_for_cell_errors_naming_the_row(empty):
    text = _README.replace(
        "| linking it (that is `link_corpus.py`) |", "| %s |" % empty
    )
    errs = _find(text)
    assert len(errs) == 1 and "build_corpus.py" in errs[0] and "Not for" in errs[0], (
        errs
    )


def test_a_table_in_a_later_section_is_not_the_roster():
    text = (
        _README.split("| Member")[0]
        + "\nProse.\n\n## Later\n\n| Member | Not for |\n|---|---|\n| `x` | y |\n"
    )
    errs = _find(text)
    assert len(errs) == 1 and "no table" in errs[0], errs


def test_members_are_computed_from_a_directory_listing():
    """Boilerplate labels and packaging are not members; hidden and ignored
    directories are not members; a directory member carries a slash."""
    listing = [
        "README.md",
        "AGENT.md",
        "CLAUDE.md",
        "__init__.py",
        "__pycache__",
        ".hidden",
        "node_modules",
        "a.py",
        "b.pyc",
        "sub",
    ]
    isdir = {"__pycache__", ".hidden", "node_modules", "sub"}
    assert cs._roster_members(listing, lambda n: n in isdir) == {"a.py", "sub/"}


# --- which READMEs are rosters: config/project.json rosters.readmes --------
#
# The heading is the roster's content, not its switch: a README edit that drops
# the heading must not silence the check. The switch is a protected config list.

_ROSTERS = ["scripts/README.md", "agents/README.md"]


def _registry(
    declared=_ROSTERS,
    headed=("scripts/README.md", "agents/README.md"),
    present=("scripts/README.md", "agents/README.md"),
):
    return cs._roster_registry_findings(
        declared, set(headed), lambda p: p in set(present)
    )


def test_a_registry_that_matches_the_headed_readmes_passes():
    assert _registry() == []


def test_a_listed_readme_without_the_heading_errors():
    """The F5 repro: renaming the heading (to '## Contents') no longer turns
    the check off for that README."""
    errs = _registry(headed=("agents/README.md",))
    assert (
        len(errs) == 1
        and "scripts/README.md" in errs[0]
        and "rosters.readmes" in errs[0]
    ), errs


def test_a_headed_readme_the_registry_does_not_list_errors():
    errs = _registry(declared=["agents/README.md"])
    assert (
        len(errs) == 1 and "scripts/README.md" in errs[0] and "not listed" in errs[0]
    ), errs


def test_a_listed_readme_that_is_absent_errors():
    errs = _registry(
        declared=_ROSTERS + ["gone/README.md"],
    )
    assert len(errs) == 1 and "gone/README.md" in errs[0] and "no such" in errs[0], errs


@pytest.mark.parametrize(
    "entry", [7, "", "/abs/README.md", "../x/README.md", "scripts/notes.md"]
)
def test_an_entry_that_is_not_a_readme_path_errors(entry):
    errs = _registry(declared=_ROSTERS + [entry])
    assert len(errs) == 1 and "rosters.readmes" in errs[0], errs


def test_an_entry_listed_twice_errors():
    errs = _registry(declared=_ROSTERS + ["agents/README.md"])
    assert len(errs) == 1 and "twice" in errs[0], errs


def test_no_registry_holds_every_headed_readme_unlisted():
    """Fail closed: an absent key lists nothing, so every roster README errors
    rather than every roster going unchecked."""
    errs = _registry(declared=[])
    assert len(errs) == 2, errs


def _tree(tmp_path, monkeypatch, rosters, readme):
    import json

    (tmp_path / "config").mkdir()
    manifest = {"structure": {"extra_toplevel": []}}
    if rosters is not None:
        manifest["rosters"] = {"readmes": rosters}
    (tmp_path / "config" / "project.json").write_text(json.dumps(manifest))
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "README.md").write_text(readme)
    for name in sorted(_MEMBERS):
        if name.endswith("/"):
            (tmp_path / "scripts" / name).mkdir()
        else:
            (tmp_path / "scripts" / name).write_text("")
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    cs.check_S()
    return cs.errors


def test_check_s_reads_the_registry_from_the_manifest(tmp_path, monkeypatch):
    assert _tree(tmp_path, monkeypatch, ["scripts/README.md"], _README) == []


def test_renaming_the_heading_of_a_listed_roster_fails_check_s(tmp_path, monkeypatch):
    """The F5 repro through check_S itself: an agent renames the heading so a
    stale roster would go unchecked; the registry still names the README."""
    errs = _tree(
        tmp_path,
        monkeypatch,
        ["scripts/README.md"],
        _README.replace("## What ships here", "## Contents"),
    )
    assert len(errs) == 1 and "rosters.readmes" in errs[0], errs


def test_check_s_without_the_key_fails_closed(tmp_path, monkeypatch):
    errs = _tree(tmp_path, monkeypatch, None, _README)
    assert len(errs) == 1 and "not listed" in errs[0], errs
