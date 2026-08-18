"""
title: Unit — check_structure check_O (module header contract) + promoted check_E
kind: tests
layer: n/a
summary: check_O errors on any CODE_ROOTS module whose docstring lacks the explicit, non-empty title:/summary: lines the corpus reads — a docstring that merely EXISTS is the defect (filename-as-title fallback, first-prose-line summary, both then labeled authored). The grammar is a 3.6-safe mirror of build_corpus._docstring_meta, pinned here by a parity test over tricky docstrings rather than by a shared import, because check_structure runs under the 3.6 pre-commit interpreter and must not import a $(PY)-only module. check_E is an ERROR now (ADR-0008): an __all__-exported symbol with no docstring is a gap in the corpus, not a note.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import check_structure as cs  # noqa: E402
from build_corpus import _docstring_meta  # noqa: E402

pytestmark = pytest.mark.unit

_OK = '"""\ntitle: A thing\nsummary: Does a thing.\n"""\nX = 1\n'


def _findings(files):
    """files: {relpath: python source} -> check_O's error strings."""
    return cs._module_header_findings(files)


# --- the pure findings function ----------------------------------------------


def test_compliant_module_passes():
    assert _findings({"src/a.py": _OK}) == []


def test_module_without_a_docstring_errors():
    """The silent-drop case: build_corpus skips such a module entirely, so an
    agent's picture of the project is confidently incomplete at exit 0."""
    errs = _findings({"src/a.py": "X = 1\n"})
    assert any("src/a.py" in e and "docstring" in e for e in errs), errs


def test_prose_docstring_without_explicit_keys_errors_naming_both():
    """The five-fixes case exactly: a docstring exists, so nothing LOOKS wrong,
    but the corpus falls back to the filename and the first prose line."""
    errs = _findings({"src/a.py": '"""Just prose, no keys."""\nX = 1\n'})
    assert len(errs) == 1
    assert "title" in errs[0] and "summary" in errs[0], errs


def test_an_empty_valued_key_counts_as_missing():
    """`title:` with nothing after it extracts as "" and the corpus falls back —
    same defect as absence, so the same error."""
    errs = _findings({"src/a.py": '"""\ntitle:\nsummary: ok\n"""\nX = 1\n'})
    assert len(errs) == 1
    assert "title" in errs[0] and "summary" not in errs[0], errs


def test_unparseable_module_is_skipped_here():
    """check_D owns parse failures (it already warns, same roots); a second
    report from check_O would be noise, not signal."""
    assert _findings({"src/a.py": "def broken(:\n"}) == []


def test_keys_after_prose_still_count():
    """_docstring_meta scans every line, not just a leading block — the mirror
    must accept the same placement or the two would disagree on real files."""
    doc = '"""\nOne prose line first.\n\ntitle: A\nsummary: B\n"""\nX = 1\n'
    assert _findings({"src/a.py": doc}) == []


# --- grammar parity with the corpus reader ------------------------------------

_TRICKY_DOCSTRINGS = [
    "title: A\nsummary: B",
    "prose first line\ntitle: A\nsummary: B",
    "title:\nsummary: B",  # empty value
    "  title: indented\nsummary: B",  # meta lines are stripped before matching
    "title: first\ntitle: second\nsummary: B",  # last occurrence wins
    "note: not a recognized key\nsummary: only",
    "no keys at all\njust prose",
    "summary: has: colons: inside\ntitle: T",
    "TITLE: case matters\nsummary: s",  # keys are lowercase-exact
    "",
]


def test_grammar_matches_the_corpus_reader_exactly():
    """The one assertion that keeps the duplicate honest: for every docstring,
    check_structure._module_meta and build_corpus._docstring_meta extract the
    SAME title and summary. If either grammar changes alone, this fails."""
    for doc in _TRICKY_DOCSTRINGS:
        theirs, _first = _docstring_meta(doc)
        ours = cs._module_meta(doc)
        for key in ("title", "summary"):
            assert ours.get(key, "") == theirs.get(key, ""), (doc, key)


# --- through the gate (module-global err/warn plumbing) ------------------------


@pytest.fixture()
def gate(tmp_path, monkeypatch):
    """A minimal repo the gate walks: patched ROOT/CODE_ROOTS, clean error lists."""
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "CODE_ROOTS", ["src"])
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    (tmp_path / "src").mkdir()
    return tmp_path


def test_check_o_reports_through_the_gate(gate):
    (gate / "src" / "bad.py").write_text("X = 1\n", encoding="utf-8")
    (gate / "src" / "good.py").write_text(_OK, encoding="utf-8")
    cs.check_O()
    assert any("bad.py" in e for e in cs.errors), cs.errors
    assert not any("good.py" in e for e in cs.errors), cs.errors


def test_check_o_is_silent_on_a_compliant_tree(gate):
    (gate / "src" / "good.py").write_text(_OK, encoding="utf-8")
    cs.check_O()
    assert cs.errors == []


def test_exported_symbol_without_docstring_is_an_error_now(gate):
    """check_E, promoted WARN -> ERR by ADR-0008: authored symbol docstrings are
    the corpus's symbol summaries, so a gap is a hole in the agents' map."""
    (gate / "src" / "mod.py").write_text(
        '"""\ntitle: m\nsummary: s\n"""\n__all__ = ["f"]\n\n\ndef f():\n    return 1\n',
        encoding="utf-8",
    )
    cs.check_E()
    assert any("mod.py" in e and "'f'" in e for e in cs.errors), (
        cs.errors,
        cs.warnings,
    )
    assert cs.warnings == []


def test_annotated_dunder_all_is_read_too(gate):
    """`__all__: list[str] = [...]` is an ast.AnnAssign; matching only ast.Assign
    made annotated exports invisible to check_E AND to the corpus's identical
    reader — found by a mutation check, not by review (ADR-0008 pass). Both
    readers were widened together."""
    (gate / "src" / "mod.py").write_text(
        '"""\ntitle: m\nsummary: s\n"""\n'
        '__all__: list[str] = ["f"]\n\n\ndef f():\n    return 1\n',
        encoding="utf-8",
    )
    cs.check_E()
    assert any("'f'" in e for e in cs.errors), cs.errors


def test_documented_exported_symbol_stays_clean(gate):
    (gate / "src" / "mod.py").write_text(
        '"""\ntitle: m\nsummary: s\n"""\n__all__ = ["f"]\n\n\n'
        'def f():\n    """Return one."""\n    return 1\n',
        encoding="utf-8",
    )
    cs.check_E()
    assert cs.errors == []
