"""
title: Unit — check_structure check_O (module header contract) + promoted check_E
kind: tests
layer: n/a
summary: check_O errors on any CODE_ROOTS module whose docstring lacks the explicit, non-empty title:/summary: lines the corpus reads — a docstring that merely EXISTS is the defect (filename-as-title fallback, first-prose-line summary, both then labeled authored). The grammar is a copy of scripts/corpus_level.py docstring_meta, pinned here by a parity test over tricky docstrings. check_E is an ERROR now (ADR-K-0008): an __all__-exported symbol with no docstring is a gap in the corpus, not a note. A shell file under the code roots, as scripts/shell_gate.py `kind` finds it, carries the same two lines in the comment block that opens it (after a `#!` line, up to the first line not starting with `#`), read with the same grammar; a `.jinja` source, a symlink, a `shell.excluded_paths` path and a dangling link are not judged, and a refused `shell` block is an error, never the defaults.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import check_structure as cs  # noqa: E402
from corpus_level import docstring_meta  # noqa: E402

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
    """docstring_meta scans every line, not just a leading block — the mirror
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
    check_structure._module_meta and corpus_level.docstring_meta extract the
    SAME title and summary. If either grammar changes alone, this fails."""
    for doc in _TRICKY_DOCSTRINGS:
        theirs, _first = docstring_meta(doc)
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
    # The config read is memoised per run; each test is a run of its own.
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
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
    """check_E, promoted WARN -> ERR by ADR-K-0008: authored symbol docstrings are
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
    reader — found by a mutation check, not by review (ADR-K-0008 pass). Both
    readers were widened together."""
    (gate / "src" / "mod.py").write_text(
        '"""\ntitle: m\nsummary: s\n"""\n'
        '__all__: list[str] = ["f"]\n\n\ndef f():\n    return 1\n',
        encoding="utf-8",
    )
    cs.check_E()
    assert any("'f'" in e for e in cs.errors), cs.errors


def test_bom_module_is_read_not_skipped(gate):
    """A UTF-8-BOM module is valid Python at import time, but read as plain
    utf-8 the BOM survives into the str, ast.parse raises, and the
    except-UNPARSEABLE swallow re-opened the silent-drop class for exactly
    those files — found by the ADR-K-0008 review pass. Every .py read that feeds
    ast is utf-8-sig now, in check_structure and build_corpus together."""
    (gate / "src" / "bom_ok.py").write_bytes(b"\xef\xbb\xbf" + _OK.encode("utf-8"))
    (gate / "src" / "bom_bad.py").write_bytes(b"\xef\xbb\xbfX = 1\n")
    cs.check_O()
    assert any("bom_bad.py" in e for e in cs.errors), cs.errors
    assert not any("bom_ok.py" in e for e in cs.errors), cs.errors


def test_documented_exported_symbol_stays_clean(gate):
    (gate / "src" / "mod.py").write_text(
        '"""\ntitle: m\nsummary: s\n"""\n__all__ = ["f"]\n\n\n'
        'def f():\n    """Return one."""\n    return 1\n',
        encoding="utf-8",
    )
    cs.check_E()
    assert cs.errors == []


# --- the shell header (KEEL-SHELL-1 slice 2) -----------------------------------
#
# A shell file cannot carry a docstring, so its header is the comment block that
# opens it: after a `#!` line when there is one, every line up to the first that
# does not start with `#`, each read with that one `#` removed and then by the
# grammar _module_meta reads a docstring with.

_SH_OK = "#!/bin/sh\n# title: A thing\n# summary: Does a thing.\nset -eu\n"


def _sh_findings(files):
    """files: {relpath: shell source} -> check_O's error strings."""
    return cs._shell_header_findings(files)


def test_a_shell_script_with_its_header_passes():
    assert _sh_findings({"scripts/a.sh": _SH_OK}) == []


def test_a_shell_header_with_no_shebang_passes():
    assert _sh_findings({"scripts/a.sh": "# title: A\n# summary: B\n"}) == []


def test_a_shell_script_with_no_comment_block_errors_naming_the_file():
    errs = _sh_findings({"scripts/a.sh": "#!/bin/sh\nset -eu\n"})
    assert len(errs) == 1, errs
    assert errs[0].startswith("scripts/a.sh: has no header"), errs


def test_a_blank_shell_field_counts_as_missing():
    errs = _sh_findings({"scripts/a.sh": "#!/bin/sh\n# title:\n# summary: B\n"})
    assert len(errs) == 1, errs
    assert "title:" in errs[0] and "summary:" not in errs[0], errs


def test_a_shell_field_after_the_block_ends_is_not_read():
    """A blank line ends the header, so a `# summary:` lower in the file is a
    comment on the code, not the file's label."""
    text = "#!/bin/sh\n# title: A\n\n# summary: B\n"
    errs = _sh_findings({"scripts/a.sh": text})
    assert len(errs) == 1, errs
    assert "summary:" in errs[0] and "title:" not in errs[0], errs


def test_a_shell_block_with_neither_field_names_both():
    errs = _sh_findings({"scripts/a.sh": "#!/bin/sh\n# shellcheck shell=sh\nx=1\n"})
    assert len(errs) == 1, errs
    assert "title:" in errs[0] and "summary:" in errs[0], errs


def test_the_shell_header_is_read_with_the_module_grammar():
    """One grammar for both languages: the block, its `#` removed, is what
    _module_meta reads, so a later key wins and the value is stripped."""
    text = "#!/bin/sh\n#  title: first\n# title:  second \n# summary: B\n"
    assert cs._module_meta(cs._shell_header(text)) == {
        "title": "second",
        "summary": "B",
    }


def test_check_o_reads_shell_scripts_and_tests_through_the_gate(gate):
    (gate / "src" / "bad.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (gate / "src" / "bad.bats").write_text("@test x { true; }\n", encoding="utf-8")
    (gate / "src" / "good.sh").write_text(_SH_OK, encoding="utf-8")
    cs.check_O()
    assert sorted(e.split(":", 1)[0] for e in cs.errors) == [
        "src/bad.bats",
        "src/bad.sh",
    ], cs.errors


def test_check_o_reads_a_shell_script_by_its_shebang(gate):
    (gate / "src" / "tool").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    cs.check_O()
    assert [e.split(":", 1)[0] for e in cs.errors] == ["src/tool"], cs.errors


def test_check_o_skips_a_shell_template_source(gate):
    """A `.jinja` file is copier's source, and the file it renders is the one
    judged (shell_gate.kind)."""
    (gate / "src" / "bad.sh.jinja").write_text("#!/bin/sh\n", encoding="utf-8")
    cs.check_O()
    assert cs.errors == []


def test_check_o_skips_a_shell_file_in_excluded_paths(gate):
    (gate / "config").mkdir()
    (gate / "config" / "project.json").write_text(
        '{"shell": {"excluded_paths": {"src/vendor": "vendored as shipped"}}}',
        encoding="utf-8",
    )
    (gate / "src" / "vendor").mkdir()
    (gate / "src" / "vendor" / "bad.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (gate / "src" / "bad.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    cs.check_O()
    assert [e.split(":", 1)[0] for e in cs.errors] == ["src/bad.sh"], cs.errors


def test_check_o_judges_a_shell_file_whatever_shell_enabled_says(gate):
    """`shell.enabled` switches the shell tools only, never the header rule."""
    (gate / "config").mkdir()
    (gate / "config" / "project.json").write_text(
        '{"shell": {"enabled": false}}', encoding="utf-8"
    )
    (gate / "src" / "bad.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    cs.check_O()
    assert [e.split(":", 1)[0] for e in cs.errors] == ["src/bad.sh"], cs.errors


def test_check_o_reports_a_refused_shell_block(gate):
    """Fail closed: a shell block the loader refuses is an error, never a
    quiet fall back to the default suffixes."""
    (gate / "config").mkdir()
    (gate / "config" / "project.json").write_text(
        '{"shell": {"script_suffixes": "sh"}}', encoding="utf-8"
    )
    cs.check_O()
    assert any("shell.script_suffixes" in e for e in cs.errors), cs.errors


def test_check_o_holds_a_shell_symlink_at_its_target_only(gate):
    """A link is judged where its target lives, so a target outside the walk
    is not judged through the link, and a dangling link is nothing to read."""
    (gate / "elsewhere").mkdir()
    (gate / "elsewhere" / "bad.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (gate / "src" / "link.sh").symlink_to("../elsewhere/bad.sh")
    (gate / "src" / "dangling.sh").symlink_to("absent.sh")
    cs.check_O()
    assert cs.errors == []
