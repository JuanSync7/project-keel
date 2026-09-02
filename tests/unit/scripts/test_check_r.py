"""
title: Unit — check_structure check_R (check catalogue parity)
kind: tests
layer: n/a
summary: check_R errors when the catalogue of deterministic checks and the triggers that run them disagree on one membership — a catalogued script that does not exist, a row claiming the error tier whose script `make check-all` never runs, a script `check-all` runs that the catalogue does not list, a report row no make target invokes, or a pre-commit hook the hooks table omits (and vice versa). The live instance: the catalogue marked `cdmon_sync.py --check` as an error-tier gate for as long as it existed while `check-all` never ran it — a claim, not a check. Absent is silent (no catalogue, no Makefile); a catalogue whose table this check cannot read is a stated WARN.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_CATALOGUE = """# Checks

## The checks

| Check | Script | Gate? | Interpreter | What it guarantees |
|-------|--------|:-----:|-------------|--------------------|
| Structure | `scripts/check_structure.py` | error | 3.6-safe | conventions |
| Corpus | `scripts/jobs/check_corpus.py` | error | >=3.7 | the graph |
| Advisor | `scripts/check_generic.py` | report | 3.6-safe | smells |

## How the hooks are wired

| Hook id | Calls |
|---------|-------|
| `structure` | `python3 scripts/check_structure.py` |
| `eslint` / `ruff` | style |
"""

_MAKEFILE = """check: ## structure
\t$(PY) scripts/check_structure.py
check-all: check check-corpus ## all
check-corpus: ## corpus
\t$(PY) scripts/jobs/check_corpus.py
advise: ## advisory
\t-$(PY) scripts/check_generic.py
"""

_PRECOMMIT = """repos:
  - repo: local
    hooks:
      - id: structure
        entry: python3 scripts/check_structure.py
      - id: eslint
        entry: make lint-fe
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.18
    hooks:
      - id: ruff
"""

_TREE = {
    "scripts/check_structure.py",
    "scripts/jobs/check_corpus.py",
    "scripts/check_generic.py",
}


def _find(catalogue=_CATALOGUE, makefile=_MAKEFILE, precommit=_PRECOMMIT, tree=_TREE):
    return cs._catalogue_parity_findings(catalogue, makefile, precommit, tree)


def test_a_catalogue_that_agrees_with_its_triggers_passes():
    assert _find() == ([], [])


# --- the regression, exactly ---------------------------------------------------


def test_an_error_tier_row_that_check_all_never_runs_errors():
    """`cdmon_sync.py --check | error*` sat in the table while `check-all` ran
    everything BUT it. A gate nobody runs is a claim."""
    cat = _CATALOGUE.replace(
        "| Advisor |",
        "| Drift | `scripts/cdmon_sync.py --check` | error* | any | drift |\n| Advisor |",
    )
    errs, warns = _find(cat, tree=_TREE | {"scripts/cdmon_sync.py"})
    assert len(errs) == 1 and "cdmon_sync.py" in errs[0] and "check-all" in errs[0], (
        errs
    )
    assert "error*" in errs[0]
    assert warns == []


def test_the_same_row_passes_once_check_all_reaches_it_transitively():
    cat = _CATALOGUE.replace(
        "| Advisor |",
        "| Drift | `scripts/cdmon_sync.py --check` | error* | any | drift |\n| Advisor |",
    )
    mk = _MAKEFILE.replace(
        "check-all: check check-corpus ## all",
        "check-all: check check-corpus check-drift ## all\ncheck-drift: ## drift\n\t$(PY) scripts/cdmon_sync.py --check",
    )
    assert _find(cat, mk, tree=_TREE | {"scripts/cdmon_sync.py"}) == ([], [])


# --- the other directions ------------------------------------------------------


def test_a_catalogued_script_that_does_not_exist_errors():
    errs, _ = _find(tree=_TREE - {"scripts/check_generic.py"})
    assert (
        len(errs) == 1 and "scripts/check_generic.py" in errs[0] and "exist" in errs[0]
    ), errs


def test_a_script_check_all_runs_that_the_catalogue_omits_errors():
    """`check-python` runs `scripts/check_python_version.py` under `check-all`
    (via `check-corpus`) and the catalogue never listed it."""
    mk = (
        _MAKEFILE.replace(
            "check-corpus: ## corpus\n",
            "check-corpus: check-python ## corpus\n",
        )
        + "check-python: ## floor\n\t$(PY) scripts/check_python_version.py\n"
    )
    errs, _ = _find(makefile=mk, tree=_TREE | {"scripts/check_python_version.py"})
    assert (
        len(errs) == 1
        and "check_python_version.py" in errs[0]
        and "catalogue" in errs[0]
    ), errs


def test_a_report_row_no_make_target_runs_errors():
    """A report nobody runs is the `make advise` precedent: documented, invoked
    by nothing. Any target will do — reports are not held to `check-all`."""
    mk = _MAKEFILE.replace(
        "advise: ## advisory\n\t-$(PY) scripts/check_generic.py\n", ""
    )
    errs, _ = _find(makefile=mk)
    assert (
        len(errs) == 1 and "check_generic.py" in errs[0] and "no make target" in errs[0]
    ), errs


def test_an_unknown_tier_word_errors():
    errs, _ = _find(_CATALOGUE.replace("| report |", "| advisory |"))
    assert len(errs) == 1 and "advisory" in errs[0], errs


def test_a_hook_the_table_omits_errors_and_so_does_a_row_with_no_hook():
    pc = _PRECOMMIT + "      - id: ruff-format\n"
    errs, _ = _find(precommit=pc)
    assert len(errs) == 1 and "ruff-format" in errs[0], errs
    errs, _ = _find(
        precommit=_PRECOMMIT.replace(
            "      - id: eslint\n        entry: make lint-fe\n", ""
        )
    )
    assert len(errs) == 1 and "eslint" in errs[0], errs


def test_hook_rows_naming_several_ids_count_each():
    """`| \\`eslint\\` / \\`ruff\\` |` is one row and two hooks."""
    assert _find() == ([], [])


# --- absent vs unverifiable ---------------------------------------------------


def test_no_catalogue_is_silent():
    assert _find(catalogue=None) == ([], [])


def test_a_catalogue_without_a_readable_checks_table_warns():
    errs, warns = _find(catalogue="# Checks\n\nprose only\n")
    assert errs == []
    assert len(warns) == 1 and "unverified" in warns[0], warns


def test_no_makefile_warns_rather_than_claiming_reachability():
    errs, warns = _find(makefile=None)
    assert errs == []
    assert len(warns) == 1 and "unverified" in warns[0] and "Makefile" in warns[0], (
        warns
    )


def test_a_makefile_without_check_all_warns():
    errs, warns = _find(
        makefile=_MAKEFILE.replace("check-all: check check-corpus ## all\n", "")
    )
    assert errs == []
    assert len(warns) == 1 and "check-all" in warns[0], warns


def test_no_precommit_config_leaves_the_hooks_table_unchecked_silently_when_the_table_is_absent():
    cat = _CATALOGUE.split("## How the hooks are wired")[0]
    assert _find(catalogue=cat, precommit=None) == ([], [])


def test_a_hooks_table_with_no_precommit_config_errors_per_row():
    errs, _ = _find(precommit=None)
    assert sorted(e.split("'")[1] for e in errs) == ["eslint", "ruff", "structure"], (
        errs
    )
