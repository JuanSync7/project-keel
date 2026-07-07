"""
title: Unit — apply_refactor (pure edit application)
kind: tests
layer: n/a
summary: apply_one applies a search/replace only when the target text occurs EXACTLY once, so a refactor edit is unambiguous — zero or multiple matches raise before anything is written.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import apply_refactor as ar  # noqa: E402

pytestmark = pytest.mark.unit


def test_apply_one_replaces_a_unique_match():
    assert ar.apply_one("a = 1\nb = 2\n", "b = 2", "b = 3") == "a = 1\nb = 3\n"


def test_apply_one_raises_when_not_present():
    with pytest.raises(ar.RefactorError):
        ar.apply_one("x = 1\n", "nope", "y")


def test_apply_one_raises_on_ambiguous_match():
    with pytest.raises(ar.RefactorError):
        ar.apply_one("pass\npass\n", "pass", "return")


def test_apply_one_preserves_the_rest_of_the_text():
    src = "class C:\n    pass\n"
    out = ar.apply_one(src, "    pass", "    __slots__ = ()")
    assert out == "class C:\n    __slots__ = ()\n"
