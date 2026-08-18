"""
title: Unit — check_structure check_M (ruleset parity)
kind: tests
layer: n/a
summary: check_M proves pyproject.toml cannot silently loosen the lint/type policy declared in config/practices.json rulesets — a missing ruff family, a mypy flag off/absent, or a deferred family selected all err. It reads real TOML (multi-line arrays, dotted keys and header forms, escaped quotes, multi-line strings) with a stdlib scanner, matches families as whole quoted tokens, and honours # practice-ok.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


def _find(text, extend=None, deferred=None, flags=None):
    rules = {"ruff": {}, "mypy": {}}
    if extend is not None:
        rules["ruff"]["extend_select"] = extend
    if deferred is not None:
        rules["ruff"]["deferred"] = deferred
    if flags is not None:
        rules["mypy"]["flags"] = flags
    errs, _ = cs._ruleset_parity_findings({"rulesets": rules}, text)
    return errs


# --- MUST-ERR (a silent loosening) -------------------------------------------


def test_declared_family_missing_errors():
    toml = '[tool.ruff.lint]\nextend-select = ["I"]\n'
    assert any("'B'" in e for e in _find(toml, extend=["I", "B"]))


def test_mypy_flag_false_errors():
    toml = "[tool.mypy]\nwarn_return_any = false\n"
    assert any(
        "warn_return_any" in e and "false" in e
        for e in _find(toml, flags=["warn_return_any"])
    )


def test_last_writer_wins_false_after_true_errors():
    toml = "[tool.mypy]\nstrict = true\nstrict = false\n"
    assert _find(toml, flags=["strict"])  # off wins -> err


def test_deferred_family_selected_errors():
    toml = '[tool.ruff.lint]\nextend-select = ["I", "UP"]\n'
    assert any(
        "UP" in e and "DEFERRED" in e
        for e in _find(toml, extend=["I"], deferred={"UP": "house style"})
    )


def test_root_dotted_mypy_flag_false_errors():
    toml = "tool.mypy.warn_return_any = false\n"
    assert _find(toml, flags=["warn_return_any"])


def test_extend_select_table_absent_errors():
    assert any("absent" in e for e in _find("[tool.other]\nx = 1\n", extend=["I"]))


def test_declared_flag_absent_errors():
    assert any(
        "absent" in e for e in _find("[tool.mypy]\nfiles = ['src']\n", flags=["strict"])
    )


def test_whole_token_declared_I_not_satisfied_by_SIM():
    toml = '[tool.ruff.lint]\nextend-select = ["SIM"]\n'
    assert any("'I'" in e for e in _find(toml, extend=["I"]))


def test_strict_optional_not_satisfied_by_strict_substring():
    toml = "[tool.mypy]\nstrict = true\n"
    assert any("strict_optional" in e for e in _find(toml, flags=["strict_optional"]))


def test_in_string_pragma_does_not_waive_a_real_loosening():
    toml = (
        'description = """\n# practice-ok: prose inside a string\n"""\n'
        "[tool.mypy]\ndisallow_any_generics = false\n"
    )
    assert _find(toml, flags=["disallow_any_generics"])


# --- MUST-PASS (parity holds, or a genuine waiver) ---------------------------


def test_multiline_array_is_captured_whole():
    toml = '[tool.ruff.lint]\nextend-select = [\n  "I",  # sort\n  "B",  # bugbear\n]\n'
    assert _find(toml, extend=["I", "B"]) == []


def test_dotted_key_form_under_tool_ruff_passes():
    toml = '[tool.ruff]\nlint.extend-select = ["I", "B"]\n'
    assert _find(toml, extend=["I", "B"]) == []


def test_root_dotted_forms_pass():
    toml = 'tool.ruff.lint.extend-select = ["I"]\ntool.mypy.strict = true\n'
    assert _find(toml, extend=["I"], flags=["strict"]) == []


def test_escaped_quote_in_a_value_does_not_break_parsing():
    toml = (
        'note = "escaped \\" then # not a comment"\n'
        '[tool.ruff.lint]\nextend-select = ["I"]\n'
    )
    assert _find(toml, extend=["I"]) == []


def test_in_string_bracket_and_flag_lines_are_ignored():
    toml = (
        'doc = """\nextend-select = ["X"]\nstrict = false\n"""\n'
        '[tool.ruff.lint]\nextend-select = ["I"]\n[tool.mypy]\nstrict = true\n'
    )
    assert _find(toml, extend=["I"], flags=["strict"]) == []


def test_deferred_authored_as_a_list_does_not_crash():
    toml = '[tool.ruff.lint]\nextend-select = ["I"]\n'
    assert _find(toml, extend=["I"], deferred=["UP"]) == []


def test_table_missing_is_waivable_file_level():
    toml = "# practice-ok: bootstrapping\n[tool.other]\nx = 1\n"
    assert _find(toml, extend=["I"]) == []


def test_line_level_waiver_on_a_missing_family():
    toml = '[tool.ruff.lint]\nextend-select = ["I"]  # practice-ok: B lands next PR\n'
    assert _find(toml, extend=["I", "B"]) == []


# --- string-blind bracket counting must not runaway-swallow the file ---------


def test_bracket_inside_a_string_value_does_not_swallow_the_policy():
    # A '[' inside a string value must NOT unbalance the array accumulator and
    # gobble the [tool.ruff.lint]/[tool.mypy] tables that follow (regression).
    toml = (
        '[project]\ndescription = "My project [beta"\n'
        '[tool.ruff.lint]\nextend-select = ["I", "B"]\n'
        "[tool.mypy]\nstrict = true\n"
    )
    assert _find(toml, extend=["I", "B"], flags=["strict"]) == []


def test_closing_bracket_inside_an_array_element_string_does_not_truncate():
    toml = '[tool.ruff.lint]\nextend-select = [\n  "I",\n  "weird]tok",\n  "B",\n]\n'
    assert _find(toml, extend=["I", "B"]) == []


# --- a deferred family reached via a parent prefix / ALL is caught ------------


def test_deferred_family_via_parent_prefix_errors():
    toml = '[tool.ruff.lint]\nextend-select = ["I", "RUF"]\n'
    assert any(
        "RUF022" in e
        for e in _find(toml, extend=["I"], deferred={"RUF022": "semantic order"})
    )


def test_deferred_family_via_ALL_selector_errors():
    toml = '[tool.ruff.lint]\nextend-select = ["ALL"]\n'
    assert any("UP" in e for e in _find(toml, deferred={"UP": "house style"}))


def test_sibling_prefix_does_not_falsely_flag_a_deferred_family():
    # RSE/RET share a first letter with RUF022 but are NOT prefixes of it.
    toml = '[tool.ruff.lint]\nextend-select = ["RSE", "RET"]\n'
    assert (
        _find(toml, extend=["RSE", "RET"], deferred={"RUF022": "semantic order"}) == []
    )


# --- blind spot 1: per-file-ignores had NO consumer at all -------------------
# `grep -rn per_file_ignores scripts/` was empty: practices.json declared the
# carve-outs and nothing read them, so ruff's per-file-ignores could disable any
# rule anywhere and check_M — the gate whose whole job is proving pyproject cannot
# silently loosen the declared policy — reported nothing.


def _find_pfi(text, declared):
    rules = {"ruff": {"extend_select": ["B"], "per_file_ignores": declared}, "mypy": {}}
    errs, _ = cs._ruleset_parity_findings({"rulesets": rules}, text)
    return errs


def test_blanket_per_file_ignore_errors():
    """The whole-corpus off switch: one line silences a family everywhere."""
    toml = (
        '[tool.ruff.lint]\nextend-select = ["B"]\n'
        "[tool.ruff.lint.per-file-ignores]\n"
        '"**/*.py" = ["B904", "BLE001"]\n'
    )
    errs = _find_pfi(toml, {"src/app/**": ["T201"]})
    assert any("**/*.py" in e for e in errs), errs


def test_undeclared_per_file_ignore_pattern_errors():
    toml = (
        '[tool.ruff.lint]\nextend-select = ["B"]\n'
        "[tool.ruff.lint.per-file-ignores]\n"
        '"src/app/**" = ["T201"]\n"secret/**" = ["B904"]\n'
    )
    errs = _find_pfi(toml, {"src/app/**": ["T201"]})
    assert any("secret/**" in e for e in errs), errs


def test_undeclared_code_on_a_declared_pattern_errors():
    """Widening an existing carve-out is the same loosening as inventing one."""
    toml = (
        '[tool.ruff.lint]\nextend-select = ["B"]\n'
        "[tool.ruff.lint.per-file-ignores]\n"
        '"src/app/**" = ["T201", "B904"]\n'
    )
    errs = _find_pfi(toml, {"src/app/**": ["T201"]})
    assert any("B904" in e for e in errs), errs


def test_declared_per_file_ignores_pass():
    toml = (
        '[tool.ruff.lint]\nextend-select = ["B"]\n'
        "[tool.ruff.lint.per-file-ignores]\n"
        '"src/app/**" = ["T201"]\n"scripts/**" = ["T201"]\n'
    )
    assert _find_pfi(toml, {"src/app/**": ["T201"], "scripts/**": ["T201"]}) == []


def test_per_file_ignores_comment_key_is_not_a_pattern():
    """practices.json uses `_comment` keys; they are documentation, not policy."""
    toml = (
        '[tool.ruff.lint]\nextend-select = ["B"]\n'
        '[tool.ruff.lint.per-file-ignores]\n"src/app/**" = ["T201"]\n'
    )
    assert _find_pfi(toml, {"_comment": "why", "src/app/**": ["T201"]}) == []


def test_per_file_ignores_undeclared_is_waivable():
    toml = (
        '[tool.ruff.lint]\nextend-select = ["B"]\n'
        "[tool.ruff.lint.per-file-ignores]\n"
        '"secret/**" = ["B904"]   # practice-ok\n'
    )
    assert _find_pfi(toml, {}) == []


# --- blind spot 2: [[tool.mypy.overrides]] was invisible ---------------------
# _toml_targets normalises every array-of-tables block to the single dotted key
# `tool.mypy.overrides.<flag>`, so all blocks aliased onto one entry and
# _flag_state read it last-writer-wins — while check_M only ever looked at
# `tool.mypy.<flag>`. A per-module `strict = false`, or `ignore_errors = true`,
# was therefore a silent, unreported off switch.


def _find_ovr(text, declared_overrides=None, flags=("strict",)):
    mypy = {"flags": list(flags)}
    if declared_overrides is not None:
        mypy["overrides"] = declared_overrides
    errs, _ = cs._ruleset_parity_findings(
        {"rulesets": {"ruff": {}, "mypy": mypy}}, text
    )
    return errs


_STRICT = "[tool.mypy]\nstrict = true\n"


def test_undeclared_per_module_flag_off_errors():
    toml = _STRICT + '[[tool.mypy.overrides]]\nmodule = ["x.*"]\nstrict = false\n'
    errs = _find_ovr(toml, {})
    assert any("x.*" in e and "strict" in e for e in errs), errs


def test_undeclared_ignore_errors_errors():
    """`ignore_errors` is stronger than `strict = false` — it disables the module."""
    toml = _STRICT + '[[tool.mypy.overrides]]\nmodule = ["y.*"]\nignore_errors = true\n'
    errs = _find_ovr(toml, {})
    assert any("y.*" in e and "ignore_errors" in e for e in errs), errs


def test_declared_per_module_relaxation_passes():
    toml = _STRICT + '[[tool.mypy.overrides]]\nmodule = ["x.*"]\nstrict = false\n'
    assert _find_ovr(toml, {"x.*": ["strict"]}) == []


def test_second_block_is_not_masked_by_the_first():
    """Every block is judged; they must not alias onto one dotted key."""
    toml = (
        _STRICT
        + '[[tool.mypy.overrides]]\nmodule = ["a.*"]\nstrict = false\n'
        + '[[tool.mypy.overrides]]\nmodule = ["b.*"]\nstrict = false\n'
    )
    errs = _find_ovr(toml, {"a.*": ["strict"]})
    assert any("b.*" in e for e in errs), errs
    assert not any("a.*" in e for e in errs), errs


def test_override_relaxation_is_waivable():
    toml = _STRICT + (
        '[[tool.mypy.overrides]]\nmodule = ["z.*"]\nstrict = false   # practice-ok\n'
    )
    assert _find_ovr(toml, {}) == []


def test_override_that_relaxes_nothing_declared_is_silent():
    """A block tuning an UNdeclared flag is not a loosening of declared policy."""
    toml = _STRICT + (
        '[[tool.mypy.overrides]]\nmodule = ["q.*"]\nignore_missing_imports = true\n'
    )
    assert _find_ovr(toml, {}) == []


def test_relaxing_a_strict_component_per_module_errors():
    """`strict` declared, then its components switched off per module, is the same
    loosening spelled differently — mypy's --strict IS that set of flags."""
    toml = _STRICT + (
        '[[tool.mypy.overrides]]\nmodule = ["m.*"]\ndisallow_untyped_defs = false\n'
    )
    errs = _find_ovr(toml, {})
    assert any("m.*" in e and "disallow_untyped_defs" in e for e in errs), errs


def test_declared_strict_component_relaxation_passes():
    toml = _STRICT + (
        '[[tool.mypy.overrides]]\nmodule = ["m.*"]\n'
        "disallow_untyped_defs = false\nwarn_return_any = false\n"
    )
    assert _find_ovr(toml, {"m.*": ["disallow_untyped_defs", "warn_return_any"]}) == []


def test_partially_declared_relaxation_still_errors_on_the_rest():
    toml = _STRICT + (
        '[[tool.mypy.overrides]]\nmodule = ["m.*"]\n'
        "disallow_untyped_defs = false\nwarn_return_any = false\n"
    )
    errs = _find_ovr(toml, {"m.*": ["disallow_untyped_defs"]})
    assert any("warn_return_any" in e for e in errs), errs
    assert not any("disallow_untyped_defs" in e for e in errs), errs


def test_component_relaxation_is_silent_when_strict_is_not_declared():
    """No `strict` in the declared flags means no claim about its components."""
    toml = (
        "[tool.mypy]\nwarn_unreachable = true\n"
        '[[tool.mypy.overrides]]\nmodule = ["m.*"]\ndisallow_untyped_defs = false\n'
    )
    assert _find_ovr(toml, {}, flags=("warn_unreachable",)) == []
