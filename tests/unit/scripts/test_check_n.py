"""
title: Unit — check_structure check_N (template twin parity)
kind: tests
layer: n/a
summary: check_N is the render-free half of twin parity — it runs in the 3.6 pre-commit gate with no jinja2, over ALL twins rather than one. It proves every `*.jinja` is declared with a kind in config/project.json template.twins, that the declaration matches reality (a parity/divergence twin has a plain sibling, a generated one does not), that a parity twin carries no non-templated line the plain file has lost, and that a divergence twin actually diverges.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


def _find(files, declared):
    """files: {relpath: text}. declared: the template.twins mapping."""
    return cs._twin_parity_findings(files, declared)


_PLAIN = 'name = "keel"\nstrict = true\nfiles = ["src", "api"]\n'
_TWIN = 'name = "{{ project_slug }}"\nstrict = true\nfiles = ["src", "api"]\n'


def test_matching_parity_twin_passes():
    assert (
        _find(
            {"pyproject.toml": _PLAIN, "pyproject.toml.jinja": _TWIN},
            {"pyproject.toml": "parity"},
        )
        == []
    )


def test_parity_twin_carrying_a_stale_policy_line_errors():
    """The pass-3 regression, exactly: the plain file's lint/type scope widened and
    the twin kept the old narrow one, so every generated project inherited a gate
    weaker than keel's — and silently, because a narrower mypy still exits 0."""
    stale = 'name = "{{ project_slug }}"\nstrict = true\nfiles = ["src"]\n'
    errs = _find(
        {"pyproject.toml": _PLAIN, "pyproject.toml.jinja": stale},
        {"pyproject.toml": "parity"},
    )
    assert any('files = ["src"]' in e for e in errs), errs


def test_undeclared_twin_errors():
    """A sixth twin added without a declaration is the drift class re-opening."""
    errs = _find({"secrets.env": "a\n", "secrets.env.jinja": "a\n"}, {})
    assert any("secrets.env" in e for e in errs), errs


def test_declared_parity_twin_with_no_plain_sibling_errors():
    errs = _find({"pyproject.toml.jinja": _TWIN}, {"pyproject.toml": "parity"})
    assert any("pyproject.toml" in e for e in errs), errs


def test_declared_twin_whose_jinja_vanished_errors():
    """A stale declaration is as misleading as a missing one — it reads as
    "this is covered". Needs another twin present, because a tree with NO twins
    at all is a generated project, not a template with a deleted one."""
    errs = _find(
        {"pyproject.toml": _PLAIN, "README.md": "a\n", "README.md.jinja": "a\n"},
        {"pyproject.toml": "parity", "README.md": "parity"},
    )
    assert any("pyproject.toml" in e for e in errs), errs
    assert not any("README.md" in e for e in errs), errs


def test_divergence_twin_that_stopped_diverging_errors():
    """`.gitignore.jinja` must NOT reproduce keel's file — it drops the
    `.copier-answers.yml` ignore so the answers file is TRACKED downstream. If a
    well-meaning edit restores parity, every generated project loses its upgrade
    channel again and nothing else would notice."""
    errs = _find(
        {".gitignore": "a\nb\n", ".gitignore.jinja": "a\nb\n"},
        {".gitignore": "divergence"},
    )
    assert any(".gitignore" in e for e in errs), errs


def test_divergence_twin_that_diverges_passes():
    assert (
        _find(
            {".gitignore": "a\nb\n", ".gitignore.jinja": "a\n"},
            {".gitignore": "divergence"},
        )
        == []
    )


def test_generated_twin_must_not_have_a_committed_plain_file():
    """copier WRITES .copier-answers.yml into the project; keel committing one of
    its own would make it a generated project, which it is not."""
    errs = _find(
        {".copier-answers.yml": "x\n", ".copier-answers.yml.jinja": "x\n"},
        {".copier-answers.yml": "generated"},
    )
    assert any(".copier-answers.yml" in e for e in errs), errs


def test_generated_twin_without_a_plain_file_passes():
    assert (
        _find(
            {".copier-answers.yml.jinja": "x\n"}, {".copier-answers.yml": "generated"}
        )
        == []
    )


def test_unknown_kind_errors():
    errs = _find({"a": "x\n", "a.jinja": "x\n"}, {"a": "sort-of-parity"})
    assert any("sort-of-parity" in e for e in errs), errs


def test_templated_lines_are_exempt_from_the_parity_rule():
    """A line the twin templates is licensed to differ — that is what a twin IS.
    Both `{{ }}` expressions and `{% %}` control flow count."""
    plain = 'a\nname = "keel"\nb\n'
    twin = 'a\n{% if x %}\nname = "{{ project_slug }}"\n{% endif %}\nb\n'
    assert _find({"p": plain, "p.jinja": twin}, {"p": "parity"}) == []


def test_no_jinja_files_at_all_is_silent():
    """A GENERATED project inherits the declaration but has no twins; it must not
    be told its template is broken."""
    assert _find({"pyproject.toml": _PLAIN}, {}) == []
