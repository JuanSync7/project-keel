"""
title: Unit — backend.example_feature
kind: tests
layer: backend
summary: Mirrors src/backend/example_feature/. Tests via the public API.
"""
import pytest
from backend import do_thing, Thing  # public API, not _impl

pytestmark = pytest.mark.unit


def test_do_thing_returns_thing():
    t = do_thing("x", 3)
    assert isinstance(t, Thing)
    assert t.name == "x" and t.value == 3
