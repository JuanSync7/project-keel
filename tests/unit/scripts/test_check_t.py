"""
title: Unit — check_structure check_T (practice mechanisms resolve)
kind: tests
layer: n/a
summary: check_T errors when a config/practices.json entry's `enforced_by` names a mechanism that does not exist — a check id absent from scripts/checks_data.py, a script, test or guide path (or numbered section) not in the tree, a make target the Makefile lacks — or is not in the closed grammar at all. The registry's `mechanism` prose had no consumer; a practice could claim any enforcer. This is the check-catalogue lesson (check_R) applied to the practices registry.
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

_IDS = {"CHECK-A", "CHECK-B", "CHECK-O", "CHECK-P"}
_TREE = {
    "scripts/check_practices.py",
    "tests/integration/test_x.py",
    "docs/guides/style.md",
}
_TARGETS = {"check", "fmt-check", "verify"}
_SECTIONS = {"docs/guides/style.md": {0, 1, 2, 3}}


def _find(*enforced, pid="p"):
    reg = {"practices": [{"id": pid, "enforced_by": list(enforced)}]}
    return cs._mechanism_findings(
        reg, _IDS, _TREE, _TARGETS, lambda p: _SECTIONS.get(p)
    )


@pytest.mark.parametrize(
    "ref",
    [
        "check:CHECK-O",
        "script:scripts/check_practices.py",
        "test:tests/integration/test_x.py",
        "make:fmt-check",
        "doc:docs/guides/style.md",
        "doc:docs/guides/style.md " + _S + "2",
        "doc:docs/guides/style.md " + _S + "3 ",
        "doc:docs/guides/style.md " + _S + "3\t",
        "ruff:B904",
        "mypy:strict",
    ],
)
def test_every_form_of_the_grammar_resolves_when_its_target_exists(ref):
    assert _find(ref) == []


@pytest.mark.parametrize(
    "ref, word",
    [
        ("check:CHECK-Z", "check:CHECK-Z"),
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
    assert (
        len(errs) == 1 and "grammar" in errs[0] and "check:CHECK-<LETTER>" in errs[0]
    ), errs


def test_an_entry_with_no_enforced_by_errors():
    reg = {"practices": [{"id": "orphan", "mechanism": "prose only"}]}
    errs = cs._mechanism_findings(reg, _IDS, _TREE, _TARGETS, lambda p: None)
    assert len(errs) == 1 and "orphan" in errs[0] and "enforced_by" in errs[0], errs


def test_external_tool_codes_are_accepted_as_written():
    """ruff and mypy own their vocabularies; the tools reject an unknown code."""
    assert _find("ruff:XYZ999", "mypy:made_up_flag") == []


def test_a_registry_without_practices_is_silent():
    assert cs._mechanism_findings({}, _IDS, _TREE, _TARGETS, lambda p: None) == []
    assert (
        cs._mechanism_findings(
            {"practices": "not a list"}, _IDS, _TREE, _TARGETS, lambda p: None
        )
        == []
    )


def test_a_valid_check_id_passes(monkeypatch):
    monkeypatch.setattr(
        cs,
        "_load_practices",
        lambda: {"practices": [{"id": "p", "enforced_by": ["check:CHECK-O"]}]},
    )
    monkeypatch.setattr(cs, "errors", [])
    cs.check_T()
    assert cs.errors == [], cs.errors


def test_an_unknown_check_id_names_the_reference_and_registry():
    errs = _find("check:CHECK-Z")
    assert len(errs) == 1, errs
    assert "check:CHECK-Z" in errs[0] and "scripts/checks_data.py" in errs[0], errs


def test_a_bare_check_letter_names_the_id_spelling():
    errs = _find("check:O")
    assert len(errs) == 1, errs
    assert "check:O" in errs[0] and "write check:CHECK-O" in errs[0], errs


@pytest.mark.parametrize(
    "source, why",
    [
        (None, "missing"),
        ("CHECKS = (\n", "malformed"),
        ("CHECKS = (1,)\n", "malformed"),
        ("CHECKS = [{'title': 'no id'}]\n", "malformed"),
        ("CHECKS = make_rows()\n", "malformed"),
        ("ROWS = []\n", "declares no literal CHECKS"),
    ],
)
def test_an_unusable_check_registry_is_one_named_error(
    tmp_path, monkeypatch, source, why
):
    path = tmp_path / "checks_data.py"
    if source is not None:
        path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    assert cs._registered_check_ids(str(path)) == set()
    assert cs._registered_check_ids(str(path)) == set()
    assert len(cs.errors) == 1, cs.errors
    assert "checks_data.py" in cs.errors[0] and why in cs.errors[0], cs.errors


@pytest.mark.parametrize(
    "section", ["x", "0_3", "٣", "²", "", "12345", "1\n", "2@private"]
)
def test_a_section_outside_the_ascii_grammar_is_one_finding(section):
    errs = _find("doc:docs/guides/style.md " + _S + section)
    assert len(errs) == 1 and "section" in errs[0], errs
    assert "private" not in errs[0], errs


@pytest.mark.parametrize("section", ["0", "0002", "9999"])
def test_ascii_section_boundaries_resolve(section):
    reg = {"practices": [{"id": "p", "enforced_by": ["doc:d.md " + _S + section]}]}
    assert (
        cs._mechanism_findings(reg, set(), {"d.md"}, set(), lambda _: {int(section)})
        == []
    )


@pytest.mark.parametrize("section", ["٣", "３", "𝟛"])
@pytest.mark.parametrize("reader", ["heading", "citation"])
def test_nonascii_document_numbers_are_refused(section, reader):
    if reader == "heading":
        numbers, errs = cs._numbered_sections("## " + section + ". Section\n")
        assert numbers == set()
    else:
        errs = cs._citation_findings(
            "use.md", "d.md " + _S + section, {}, {"d.md"}, lambda _: {3}
        )
    assert len(errs) == 1 and "ASCII" in errs[0], errs


def _deep_member():
    member = []
    for _ in range(sys.getrecursionlimit() * 2):
        member = [member]
    with pytest.raises(RecursionError):
        str(member)
    return member


def test_a_deep_nonstring_reference_gets_one_grammar_finding():
    errs = _find(_deep_member())
    assert len(errs) == 1 and "grammar" in errs[0], errs


def test_a_nonstring_practice_id_gets_one_grammar_finding():
    errs = _find("doc:docs/guides/style.md", pid=_deep_member())
    assert len(errs) == 1 and "id" in errs[0] and "grammar" in errs[0], errs


@pytest.mark.parametrize("reader", ["T", "U"])
@pytest.mark.parametrize("member", ["ref", "id"])
def test_deep_practice_members_already_render_without_a_traceback(reader, member):
    """Control: the base's guarded readers and shown() already avoid raw str."""
    value = _deep_member()
    reg = {
        "practices": [
            {
                "id": value if member == "id" else "p",
                "enforced_by": [value if member == "ref" else "doc:d.md"],
            }
        ]
    }
    if reader == "T":
        errs = cs._mechanism_findings(reg, set(), set(), set(), lambda _: None)
    else:
        errs = cs._policy_reachability_findings(reg, {"AGENT.md": "", "d.md": ""})
    assert len(errs) <= 1, errs
    assert all("config/practices.json" in err for err in errs), errs
