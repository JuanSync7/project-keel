"""
title: Unit — check_structure check_S (roster parity)
kind: tests
layer: n/a
summary: check_S errors when a README that declares `## What ships here` disagrees with its directory — a member it does not name, a row naming something that is not a member, a missing `Member` first column, a missing `Not for` column, or a `Not for` cell left empty. Opt-in by the heading, so no README is retro-failed; once declared, the roster is held to the tree, and every row must say what a reader must NOT reach for that member to do — the discriminator between siblings that a bare listing never states.
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
