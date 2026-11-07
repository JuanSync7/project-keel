"""
title: Integration — copier answers and README frontmatter preserve their grammar
kind: tests
layer: n/a
summary: Renders validators and README frontmatter in-process: project names are refused outside the supported alphabet, display titles round-trip through YAML, and both backend version-clause grammars agree on valid and invalid text. No copier process or generated destination is needed.
"""

import json
import string
from pathlib import Path

import pytest

import optional_deps

yaml = optional_deps.importorskip("yaml", extra="template")
jinja_sandbox = optional_deps.importorskip("jinja2.sandbox", extra="template")

_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="template-only: needs copier.yml (absent in generated projects)",
    ),
]


def _render(template, **answers):
    return jinja_sandbox.SandboxedEnvironment().from_string(template).render(**answers)


def _verdict(name):
    questions = yaml.safe_load((_ROOT / "copier.yml").read_text(encoding="utf-8"))
    validator = questions["project_name"].get("validator", "")
    return _render(validator, project_name=name).strip()


@pytest.mark.parametrize(
    "character",
    [char for char in string.punctuation if char not in "_-"]
    + [chr(code) for code in range(32)]
    + ["\x7f", "é", "３", "\u00a0"],
)
def test_project_name_refuses_each_unsafe_character_and_names_it(character):
    verdict = _verdict("Acme" + character + "Widgets")
    assert "project_name" in verdict, verdict
    assert "invalid characters " in verdict, verdict
    named, _ = json.JSONDecoder().raw_decode(verdict.split("invalid characters ", 1)[1])
    assert character in named, verdict
    assert "ASCII letters, digits, spaces, underscores or hyphens" in verdict, verdict


@pytest.mark.parametrize(
    "name", ["", "-acme", "acme-", "_acme", "acme_", " acme", "acme "]
)
def test_project_name_refuses_boundaries_that_make_an_invalid_package_name(name):
    verdict = _verdict(name)
    assert "project_name" in verdict, verdict
    assert "start and end with an ASCII letter or digit" in verdict, verdict


@pytest.mark.parametrize(
    "name", ["project_keel", "my_project", "Acme Widgets", "Acme-Widgets_2", "A", "7"]
)
def test_project_name_accepts_supported_identifier_and_display_forms(name):
    assert _verdict(name) == ""


def test_readme_frontmatter_preserves_colons_and_double_quotes():
    name = 'Acme: "Widgets"'
    rendered = _render(
        (_ROOT / "README.md.jinja").read_text(encoding="utf-8"),
        project_title=name,
        project_slug="acme_widgets",
        frontend_stack="none",
        showcase=False,
    )
    frontmatter = rendered.split("---", 2)[1]
    assert yaml.safe_load(frontmatter)["title"] == name


# Clause recognition must agree even when a valid clause rejects the CI release.
_VERSION_CLAUSES = (
    (">=3.10", True),
    (">=3", True),
    (">=3.10.1", True),
    ("<=3.11", True),
    (">3.11", True),
    ("<3.12", True),
    ("==3.11", True),
    ("!=3.11", True),
    ("~=3.11", True),
    ("~=3.11.2", True),
    ("==3.*", True),
    ("==3.11.*", True),
    ("!=3.11.*", True),
    (" >= 3.10 ", True),
    (">=3.10, <4", True),
    ("", True),
    (" , ", True),
    (" >=3 .10", False),
    (">=3. 10", False),
    (">=3.1 0", False),
    ("==3. 11.*", False),
    ("~=3", False),
    (">=3.*", False),
    ("===3.11", False),
    (">=3.10rc1", False),
    ("3.11", False),
    ("=>3.10", False),
    (">=3.1.2.3", False),
    (">=", False),
    (">=3..10", False),
    (">=３.10", False),
    (">=3.10\n", False),
    ("\t>=3.10", False),
    ('>=3.10"', False),
    (">=3.10\\", False),
)


def test_backend_and_toolchain_version_clause_grammars_agree():
    questions = yaml.safe_load((_ROOT / "copier.yml").read_text(encoding="utf-8"))
    assert len(_VERSION_CLAUSES) > 0, "no version clauses judged"
    judged = 0
    for clause, expected in _VERSION_CLAUSES:
        answer_verdict = _render(
            questions["backend_python"]["validator"], backend_python=clause
        ).strip()
        toolchain_verdict = _render(
            questions["toolchain_python"]["validator"],
            backend_python=clause,
            toolchain_python="3.11",
        ).strip()
        answer_accepts = answer_verdict == ""
        toolchain_accepts = "cannot judge" not in toolchain_verdict
        assert answer_accepts == toolchain_accepts, (
            clause,
            answer_verdict,
            toolchain_verdict,
        )
        assert answer_accepts == expected, (clause, answer_verdict, toolchain_verdict)
        judged += 1
    assert judged > 0, "no version clauses judged"
