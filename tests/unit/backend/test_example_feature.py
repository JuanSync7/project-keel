"""
title: Unit — backend.example_feature
kind: tests
layer: backend
summary: Mirrors src/backend/example_feature/. Tests via the public API. Each test names the requirement or criterion of docs/specs/example-feature.md it is evidence for with `pytest.mark.req`, which `make trace` reads.
"""

import dataclasses

import pytest

from backend import Thing, do_thing  # public API, not _impl

pytestmark = pytest.mark.unit


@pytest.mark.req("REQ-0001#AC-1")
def test_do_thing_returns_thing():
    t = do_thing("x", 3)
    assert isinstance(t, Thing)
    assert t.name == "x" and t.value == 3


@pytest.mark.req("REQ-0001#AC-2")
def test_do_thing_defaults_value_to_zero():
    assert do_thing("x").value == 0


@pytest.mark.req("REQ-0002")
def test_a_thing_is_frozen():
    t = do_thing("x", 3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.value = 4
    assert t.value == 3
