"""
title: Unit — backend.shared
kind: tests
layer: backend
summary: Mirrors src/backend/shared/. Exercises the project-identity derivation via the public API, no disk.
"""

import pytest

from backend.shared import IdentityUnreadable, display_title, project_identity

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("acme_widgets", "Acme Widgets"),  # the generated case: slug -> title
        ("acme-widgets", "Acme Widgets"),  # hyphens are separators too
        ("project_keel", "Project Keel"),  # keel's own answer round-trips
        ("widgets", "Widgets"),  # single word
        ("acme  widgets", "Acme  Widgets"),  # already spaced, left alone
        ("", ""),  # nothing in, nothing out (caller decides)
    ],
)
def test_display_title_is_the_slug_to_title_derivation(name, expected):
    """The whole input class, not the one name that prompted this.

    This has to agree with copier's computed `project_title` answer, because the
    same project is presented through both: copier writes the title into the
    generated README/pyproject at generation, and this derives it at runtime from
    the manifest. Two derivations that disagree would show a project one name in
    its docs and another in its API.
    """
    assert display_title(name) == expected


def test_display_title_does_not_reach_for_a_default():
    """No hardcoded fallback name lives in the derivation.

    The template's own name being served by a generated project is the defect this
    exists to remove, so an empty name must stay empty here and be resolved by the
    caller (which falls back to the project directory) rather than being papered
    over with a literal in domain code.
    """
    assert display_title("") == ""


@pytest.mark.parametrize(
    "text", ["[1]", '{"name": [1]}', "[" * 2000 + "0" + "]" * 2000]
)
def test_identity_decode_refusal_names_manifest_and_repair(tmp_path, text):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(text, encoding="utf-8")
    with pytest.raises(IdentityUnreadable, match=r"config/project.json.*repair"):
        project_identity(str(tmp_path))
