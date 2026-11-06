"""
title: Integration — free-text project names are safe before template rendering
kind: tests
layer: n/a
summary: Renders the project_name validator in-process: characters outside its ASCII alphabet and invalid identifier boundaries are refused with a repair, while keel's own name and supported display names remain accepted. No copier process or generated destination is needed.
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


def _verdict(name):
    questions = yaml.safe_load((_ROOT / "copier.yml").read_text(encoding="utf-8"))
    validator = questions["project_name"].get("validator", "")
    return (
        jinja_sandbox.SandboxedEnvironment()
        .from_string(validator)
        .render(project_name=name)
        .strip()
    )


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
