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
    assert any("warn_return_any" in e and "false" in e
               for e in _find(toml, flags=["warn_return_any"]))


def test_last_writer_wins_false_after_true_errors():
    toml = "[tool.mypy]\nstrict = true\nstrict = false\n"
    assert _find(toml, flags=["strict"])          # off wins -> err


def test_deferred_family_selected_errors():
    toml = '[tool.ruff.lint]\nextend-select = ["I", "UP"]\n'
    assert any("UP" in e and "DEFERRED" in e
               for e in _find(toml, extend=["I"], deferred={"UP": "house style"}))


def test_root_dotted_mypy_flag_false_errors():
    toml = "tool.mypy.warn_return_any = false\n"
    assert _find(toml, flags=["warn_return_any"])


def test_extend_select_table_absent_errors():
    assert any("absent" in e for e in _find("[tool.other]\nx = 1\n", extend=["I"]))


def test_declared_flag_absent_errors():
    assert any("absent" in e for e in _find("[tool.mypy]\nfiles = ['src']\n", flags=["strict"]))


def test_whole_token_declared_I_not_satisfied_by_SIM():
    toml = '[tool.ruff.lint]\nextend-select = ["SIM"]\n'
    assert any("'I'" in e for e in _find(toml, extend=["I"]))


def test_strict_optional_not_satisfied_by_strict_substring():
    toml = "[tool.mypy]\nstrict = true\n"
    assert any("strict_optional" in e for e in _find(toml, flags=["strict_optional"]))


def test_in_string_pragma_does_not_waive_a_real_loosening():
    toml = ('description = """\n# practice-ok: prose inside a string\n"""\n'
            "[tool.mypy]\ndisallow_any_generics = false\n")
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
    toml = ('note = "escaped \\" then # not a comment"\n'
            '[tool.ruff.lint]\nextend-select = ["I"]\n')
    assert _find(toml, extend=["I"]) == []


def test_in_string_bracket_and_flag_lines_are_ignored():
    toml = ('doc = """\nextend-select = ["X"]\nstrict = false\n"""\n'
            '[tool.ruff.lint]\nextend-select = ["I"]\n[tool.mypy]\nstrict = true\n')
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
