"""
title: Unit — check_structure check_T (practice mechanisms resolve)
kind: tests
layer: n/a
summary: check_T errors when a config/practices.json entry's `enforced_by` names a mechanism that does not exist — a check letter check_structure does not define, a script, test or guide path (or numbered section) not in the tree, a make target the Makefile lacks — or is not in the closed grammar at all. The registry's `mechanism` prose had no consumer; a practice could claim any enforcer. This is the check-catalogue lesson (check_R) applied to the practices registry.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

# The section sign spelled as an escape: check_Q reads this file's SOURCE too.
_S = "\u00a7"

_LETTERS = {"A", "B", "O", "P"}
_TREE = {
    "scripts/check_practices.py",
    "tests/integration/test_x.py",
    "docs/guides/style.md",
}
_TARGETS = {"check", "fmt-check", "verify"}
_SECTIONS = {"docs/guides/style.md": {0, 1, 2}}


def _find(*enforced, pid="p"):
    reg = {"practices": [{"id": pid, "enforced_by": list(enforced)}]}
    return cs._mechanism_findings(
        reg, _LETTERS, _TREE, _TARGETS, lambda p: _SECTIONS.get(p)
    )


@pytest.mark.parametrize(
    "ref",
    [
        "check:O",
        "script:scripts/check_practices.py",
        "test:tests/integration/test_x.py",
        "make:fmt-check",
        "doc:docs/guides/style.md",
        "doc:docs/guides/style.md " + _S + "2",
        "ruff:B904",
        "mypy:strict",
    ],
)
def test_every_form_of_the_grammar_resolves_when_its_target_exists(ref):
    assert _find(ref) == []


@pytest.mark.parametrize(
    "ref, word",
    [
        ("check:Z", "check_Z"),
        ("script:scripts/nope.py", "scripts/nope.py"),
        ("test:tests/unit/nope.py", "tests/unit/nope.py"),
        ("make:nope", "make nope"),
        ("doc:docs/guides/nope.md", "docs/guides/nope.md"),
        ("doc:docs/guides/style.md " + _S + "9", _S + "9"),
    ],
)
def test_a_reference_to_something_that_does_not_exist_errors_naming_it(ref, word):
    errs = _find(ref)
    assert len(errs) == 1 and word in errs[0] and "'p'" in errs[0], errs


def test_a_reference_outside_the_grammar_errors_and_shows_the_grammar():
    errs = _find("check_structure.py check_O")
    assert len(errs) == 1 and "grammar" in errs[0] and "check:<LETTER>" in errs[0], errs


def test_an_entry_with_no_enforced_by_errors():
    reg = {"practices": [{"id": "orphan", "mechanism": "prose only"}]}
    errs = cs._mechanism_findings(reg, _LETTERS, _TREE, _TARGETS, lambda p: None)
    assert len(errs) == 1 and "orphan" in errs[0] and "enforced_by" in errs[0], errs


def test_external_tool_codes_are_accepted_as_written():
    """ruff and mypy own their vocabularies; the tools reject an unknown code."""
    assert _find("ruff:XYZ999", "mypy:made_up_flag") == []


def test_a_registry_without_practices_is_silent():
    assert cs._mechanism_findings({}, _LETTERS, _TREE, _TARGETS, lambda p: None) == []
    assert (
        cs._mechanism_findings(
            {"practices": "not a list"}, _LETTERS, _TREE, _TARGETS, lambda p: None
        )
        == []
    )
