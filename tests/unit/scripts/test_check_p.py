"""
title: Unit — check_structure check_P (Makefile help parity)
kind: tests
layer: n/a
summary: check_P errors when a Makefile target carries a `## ` help annotation that the `help` recipe's own grep pattern cannot match, because that target is then invisible to `make help` while looking documented. The live instance was `e2e` — hidden for as long as it existed because the recipe's character class `[a-zA-Z_-]` has no digits. The check reads the recipe's pattern out of the Makefile rather than restating it, so it can never agree with a wrong pattern by construction; a recipe it cannot read is a stated WARN, never a silent pass.
"""

import sys
from pathlib import Path
from typing import cast

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

# The shape keel's Makefile uses: `help` greps every makefile for annotated
# target lines. The pattern under test is the recipe's, so each fixture states
# its own.
_HELP_NARROW = (
    "help: ## List tasks\n"
    "\t@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \\\n"
    '\t\tawk \'BEGIN{FS=":.*?## "}{printf "  %-14s %s\\n",$$1,$$2}\'\n'
)
_HELP_WIDE = _HELP_NARROW.replace("[a-zA-Z_-]", "[a-zA-Z0-9_-]")


def _find(text: str, **more: str) -> tuple[list[str], list[str]]:
    """One root Makefile (plus optional includes) -> (errs, warns)."""
    makefiles = [("Makefile", text)] + sorted(more.items())
    return cast(tuple[list[str], list[str]], cs._help_parity_findings(makefiles))


# --- the regression, exactly ---------------------------------------------------


def test_a_digit_named_target_hidden_by_a_digitless_pattern_errors():
    """`e2e: ## Run end-to-end tests` existed, was annotated, and never once
    appeared in `make help`, because `[a-zA-Z_-]` cannot match a `2`."""
    errs, warns = _find(
        _HELP_NARROW + "e2e: ## Run end-to-end tests\n\tpytest -m e2e\n"
    )
    assert len(errs) == 1, errs
    assert "e2e" in errs[0] and "grep pattern" in errs[0] and "make help" in errs[0]
    assert warns == []


def test_the_same_target_under_a_pattern_that_matches_it_passes():
    assert _find(_HELP_WIDE + "e2e: ## Run end-to-end tests\n\tpytest -m e2e\n") == (
        [],
        [],
    )


def test_every_hidden_target_is_named_not_just_the_first():
    errs, _ = _find(_HELP_NARROW + "e2e: ## a\n\tx\nv2-build: ## b\n\ty\n")
    assert sorted(e.split("'")[1] for e in errs) == ["e2e", "v2-build"]


# --- what is NOT an annotated target ------------------------------------------


def test_an_unannotated_target_is_nobodys_business():
    """No `## ` means the author chose not to list it; that is not a defect."""
    assert _find(_HELP_NARROW + "e2e:\n\tpytest -m e2e\n") == ([], [])


@pytest.mark.parametrize(
    "line",
    [
        "PY ?= python3 ## the interpreter",  # a variable, not a target
        "X := 1 ## also a variable",
        "# e2e: ## a commented-out target",
        ".PHONY: e2e ## a special target",
        "$(VAR): ## a target named by a variable cannot be listed by name",
    ],
)
def test_lines_that_are_not_listable_targets_are_ignored(line):
    assert _find(_HELP_NARROW + line + "\n") == ([], [])


# --- includes: `make help` greps $(MAKEFILE_LIST), so must this ---------------


def test_an_annotated_target_in_an_included_makefile_is_checked_too():
    errs, _ = _find(
        _HELP_NARROW + "include rules.mk\n", **{"rules.mk": "e2e: ## a\n\tx\n"}
    )
    assert len(errs) == 1 and "rules.mk" in errs[0] and "e2e" in errs[0], errs


# --- absent vs unverifiable ---------------------------------------------------


def test_no_help_target_is_silent():
    """Nothing lists the annotations, so nothing can hide one."""
    assert _find("e2e: ## a\n\tx\n") == ([], [])


def test_a_help_recipe_without_a_readable_pattern_warns_and_gates_nothing():
    """A recipe this check cannot read is 'unverified', said out loud — the
    alternative is a green run that checked nothing (the silent-green class)."""
    errs, warns = _find("help: ## List tasks\n\t@./list-targets.sh\ne2e: ## a\n\tx\n")
    assert errs == []
    assert len(warns) == 1 and "unverified" in warns[0], warns


@pytest.mark.parametrize("excluded", [False, True], ids=["select", "exclude"])
def test_a_pattern_this_check_cannot_compile_warns_unverified(
    *, excluded: bool
) -> None:
    # grep treats an escaped 'q' as literal; Python rejects the unknown escape.
    pattern = r"PRIVATE\q"
    if excluded:
        bad = _HELP_WIDE.replace(
            "$(MAKEFILE_LIST) |", "$(MAKEFILE_LIST) | grep -v '%s' |" % pattern
        )
    else:
        bad = _HELP_WIDE.replace("^[a-zA-Z0-9_-]+:.*?## ", pattern)
    errs, warns = _find(bad + "e2e: ## a\n\tx\n")
    assert errs == []
    assert len(warns) == 1
    assert "Makefile" in warns[0] and "help recipe grep pattern" in warns[0]
    assert "unverified" in warns[0] and "Python" in warns[0]
    assert "PRIVATE" not in warns[0] and pattern not in warns[0]


@pytest.mark.parametrize("excluded", [False, True], ids=["select", "exclude"])
@pytest.mark.parametrize(
    "pattern",
    [
        "(" * 600 + "HOSTILE" + ")" * 600,
        "HOSTILE{4294967296}",
        "HOSTILE{" + "9" * 5000 + "}",
        "HOSTILE" + "x" * 65536,
    ],
    ids=["depth", "overflow", "decimal-limit", "size"],
)
def test_help_pattern_faults_refuse_without_echoing(
    pattern: str, *, excluded: bool
) -> None:
    if excluded:
        text = _HELP_WIDE.replace(
            "$(MAKEFILE_LIST) |", "$(MAKEFILE_LIST) | grep -v '%s' |" % pattern
        )
    else:
        text = _HELP_WIDE.replace("^[a-zA-Z0-9_-]+:.*?## ", pattern)
    with pytest.raises(cs.config_loader.ConfigError) as exc:
        _find(text)
    message = str(exc.value)
    assert "Makefile" in message and "help" in message and "pattern" in message
    assert "correct" in message and "HOSTILE" not in message


def test_help_pattern_fault_is_a_config_exit(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pattern = "HOSTILE{4294967296}"
    (repo / "Makefile").write_text(
        _HELP_WIDE.replace("^[a-zA-Z0-9_-]+:.*?## ", pattern), encoding="utf-8"
    )
    monkeypatch.setattr(cs, "CHECKS", [("P", cs.check_P)])
    assert cs.main(["--root", str(repo)]) == cs.exit_codes.ExitCode.CONFIG
    message = capsys.readouterr().err
    assert "Makefile" in message and "help" in message and "pattern" in message
    assert "repair" in message and "HOSTILE" not in message


def test_posix_character_classes_in_the_recipe_are_understood():
    """grep -E accepts `[[:alnum:]]`; Python's re does not. The widening a user
    is most likely to write must not turn the check dark."""
    posix = _HELP_NARROW.replace("[a-zA-Z_-]", "[[:alnum:]_-]")
    assert _find(posix + "e2e: ## a\n\tx\n") == ([], [])


def test_an_empty_makefile_list_is_silent():
    assert cs._help_parity_findings([]) == ([], [])


# --- review round: grep semantics, includes, variables, pipelines --------------


def test_a_recipe_without_dash_e_is_unverified_not_green():
    """`grep -h '^[a-z0-9_-]+:.*?## '` is BRE: `+` and `?` are literal, so `make
    help` prints nothing — while a Python re would say every target is listed.
    The check has no BRE engine, so it must say so instead of agreeing."""
    bre = _HELP_WIDE.replace("grep -hE", "grep -h")
    errs, warns = _find(bre + "e2e: ## a\n\tx\n")
    assert errs == []
    assert len(warns) == 1 and "unverified" in warns[0] and "-E" in warns[0], warns


def test_a_fixed_string_grep_is_unverified():
    errs, warns = _find(_HELP_WIDE.replace("grep -hE", "grep -hF") + "e2e: ## a\n\tx\n")
    assert errs == [] and len(warns) == 1 and "unverified" in warns[0], warns


@pytest.mark.parametrize("cmd", ["egrep -h", "grep -hP", "grep -h -E", "grep -E -h"])
def test_extended_regex_spellings_are_all_understood(cmd):
    assert _find(_HELP_WIDE.replace("grep -hE", cmd) + "e2e: ## a\n\tx\n") == ([], [])


def test_case_insensitive_grep_lists_a_capitalised_target():
    ci = _HELP_NARROW.replace("grep -hE '^[a-zA-Z_-]", "grep -hiE '^[a-z_-]")
    assert _find(ci + "Build: ## Build it\n\tx\n") == ([], [])


def test_a_help_variable_assignment_is_not_the_help_target():
    text = "help := unused\n" + _HELP_WIDE + "e2e: ## a\n\tx\n"
    assert _find(text) == ([], [])


def test_a_comment_line_inside_the_help_recipe_does_not_end_it():
    text = _HELP_WIDE.replace(
        "help: ## List tasks\n",
        "help: ## List tasks\n\t# the pattern below is the contract\n",
    )
    assert _find(text + "e2e: ## a\n\tx\n") == ([], [])


def test_a_pattern_held_in_a_make_variable_is_expanded_when_assigned():
    text = "HELP_RE := ^[a-zA-Z0-9_-]+:.*?## \n" + _HELP_WIDE.replace(
        "'^[a-zA-Z0-9_-]+:.*?## '", '"$(HELP_RE)"'
    )
    assert _find(text + "e2e: ## a\n\tx\n") == ([], [])


def test_a_pattern_variable_this_check_cannot_expand_is_unverified():
    text = _HELP_WIDE.replace("'^[a-zA-Z0-9_-]+:.*?## '", '"$(HELP_RE)"')
    errs, warns = _find(text + "e2e: ## a\n\tx\n")
    assert (
        errs == []
        and len(warns) == 1
        and "help recipe grep pattern" in warns[0]
        and "unverified" in warns[0]
    ), warns


def test_a_later_grep_dash_v_hides_targets_on_purpose():
    """`| grep -v '^_'` is how an author hides helper targets from help; a target
    the author excluded is not a defect."""
    text = _HELP_WIDE.replace(
        "$(MAKEFILE_LIST) | \\", "$(MAKEFILE_LIST) | grep -v '^_' | \\"
    )
    assert _find(text + "_internal: ## hidden on purpose\n\tx\n") == ([], [])


def test_a_second_selecting_grep_is_a_pipeline_this_check_does_not_model():
    text = _HELP_WIDE.replace(
        "$(MAKEFILE_LIST) | \\", "$(MAKEFILE_LIST) | grep -E 'x' | \\"
    )
    errs, warns = _find(text + "e2e: ## a\n\tx\n")
    assert errs == [] and len(warns) == 1 and "unverified" in warns[0], warns


def test_grep_reading_something_other_than_makefile_list_is_unverified():
    text = _HELP_WIDE.replace("$(MAKEFILE_LIST)", "Makefile")
    errs, warns = _find(text + "include rules.mk\n", **{"rules.mk": "e2e: ## a\n\tx\n"})
    assert errs == [] and len(warns) == 1 and "MAKEFILE_LIST" in warns[0], warns


def test_the_error_names_the_line_and_the_makefile_holding_the_pattern():
    errs, _ = _find(
        _HELP_NARROW + "\ne2e: ## a\n\tx\n", **{"rules.mk": "v2: ## b\n\ty\n"}
    )
    assert any(e.startswith("Makefile:5:") for e in errs), errs
    assert any(e.startswith("rules.mk:1:") and "(in Makefile)" in e for e in errs), errs


# --- check_P itself: include resolution over a real tree -----------------------


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    return tmp_path


def test_a_nested_include_is_read(repo):
    (repo / "Makefile").write_text(_HELP_NARROW + "include a.mk\n", encoding="utf-8")
    (repo / "a.mk").write_text("include b.mk\n", encoding="utf-8")
    (repo / "b.mk").write_text("e2e: ## a\n\tx\n", encoding="utf-8")
    cs.check_P()
    assert len(cs.errors) == 1 and "b.mk" in cs.errors[0] and "e2e" in cs.errors[0], (
        cs.errors
    )


def test_an_include_this_check_cannot_resolve_is_unverified(repo):
    (repo / "Makefile").write_text(
        _HELP_WIDE + "include $(EXTRA)\ninclude *.mk\n", encoding="utf-8"
    )
    cs.check_P()
    assert cs.errors == []
    assert len(cs.warnings) == 2 and all("unverified" in w for w in cs.warnings), (
        cs.warnings
    )


def test_an_optional_include_that_is_absent_is_silent(repo):
    """`-include x.mk` / `sinclude x.mk` is make's own 'if present'."""
    (repo / "Makefile").write_text(
        _HELP_WIDE + "-include missing.mk\nsinclude gone.mk\n", encoding="utf-8"
    )
    cs.check_P()
    assert cs.errors == [] and cs.warnings == []


def test_a_required_include_that_is_absent_is_said_out_loud(repo):
    (repo / "Makefile").write_text(
        _HELP_WIDE + "include missing.mk\n", encoding="utf-8"
    )
    cs.check_P()
    assert cs.errors == [] and len(cs.warnings) == 1 and "missing.mk" in cs.warnings[0]
