"""
title: Unit — models registry + backend conformance
kind: tests
layer: backend
summary: Every registered ModelBackend conforms to the contract; the fake backend is deterministic.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from models import ModelBackend, get_model, list_models  # noqa: E402

pytestmark = pytest.mark.unit


def test_registry_lists_the_default_and_more():
    names = list_models()
    assert names == sorted(names), "list_models() must be sorted/stable"
    assert "claude-code-headless" in names   # the shipped reference adapter
    assert "fake" in names                    # the deterministic test/dev backend


def test_every_registered_backend_satisfies_the_contract():
    """Structural conformance: instantiate each by name with safe defaults and
    check it IS a ModelBackend with a string name and a callable run(). We never
    call run() on real adapters (they'd hit a network/subprocess) — the fake
    covers behaviour below; this pins the shape for the whole registry."""
    for name in list_models():
        backend = get_model(name)
        assert isinstance(backend, ModelBackend), name
        assert isinstance(backend.name, str) and backend.name, name
        assert callable(backend.run), name


def test_get_model_defaults_to_the_default_model():
    default = get_model()
    explicit = get_model("claude-code-headless")
    assert default.name == explicit.name == "claude-code-headless"


def test_unknown_model_raises_with_a_helpful_message():
    with pytest.raises(KeyError) as exc:
        get_model("no-such-model")
    assert "no-such-model" in str(exc.value)


def test_fake_backend_is_deterministic_and_offline():
    """The fake never touches a network/process: same prompt -> same output,
    every time, so agents and transports can be exercised hermetically."""
    a = get_model("fake")
    b = get_model("fake")
    assert a.run("hello") == a.run("hello") == b.run("hello")
    # Different prompts are distinguishable (it's not a constant black hole).
    assert a.run("hello") != a.run("world")


def test_fake_backend_can_be_scripted_with_a_fixed_reply():
    """A fixed reply makes a backend's output a known value for assertions."""
    canned = get_model("fake", reply="the answer is 42")
    assert canned.run("anything at all") == "the answer is 42"
