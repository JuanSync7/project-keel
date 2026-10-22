"""
title: Unit — models registry + backend conformance
kind: tests
layer: backend
summary: Every registered ModelBackend conforms to the contract, the HTTP adapter with the host of its own default base_url listed for the test because the shipped `models.allowed_hosts` list is empty; the fake backend is deterministic. choose_model is the one rule get_model resolves a name by: an absent or empty name is the registry default and says it defaulted, any other name is kept as named.
"""

import inspect
import sys
import urllib.parse
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from models import ModelBackend, choose_model, get_model, list_models  # noqa: E402
from models.registry import DEFAULT_MODEL  # noqa: E402

pytestmark = pytest.mark.unit


def test_registry_lists_the_default_and_more():
    names = list_models()
    assert names == sorted(names), "list_models() must be sorted/stable"
    assert "claude-code-headless" in names  # the shipped reference adapter
    assert "fake" in names  # the deterministic test/dev backend


@pytest.fixture
def adapters_listing_their_own_default_hosts(monkeypatch):
    """A policy whose `models.allowed_hosts` lists, for the HTTP adapter, the
    host of its own default base_url.

    The shipped list is empty, so that adapter refuses its own default
    endpoint until a project lists a host (fail closed,
    docs/adr/keel/K-0018-model-endpoint-host-allowlist.md);
    tests/unit/models/test_openai_compatible.py pins that refusal. Conformance
    is about the shape of each backend, not a project's choice of hosts, so
    this test lists the default host instead of shipping it in config. The
    host is read from the adapter's signature, so no endpoint is written here.
    """
    from models import openai_compatible as mod
    from scripts.child_env import canonical_host_entry, load_policy

    default = inspect.signature(mod.OpenAICompatible).parameters["base_url"].default
    parts = urllib.parse.urlsplit(default)
    written = parts.hostname or ""
    if parts.port is not None:
        written = "%s:%d" % (written, parts.port)
    policy = load_policy()._replace(
        allowed_hosts={mod.OpenAICompatible.name: (canonical_host_entry(written),)}
    )
    monkeypatch.setattr(mod, "load_policy", lambda root=None: policy)


@pytest.mark.usefixtures("adapters_listing_their_own_default_hosts")
def test_every_registered_backend_satisfies_the_contract():
    """Structural conformance: instantiate each by name with safe defaults and
    check it IS a ModelBackend with a string name and a callable run(). We never
    call run() on real adapters (they'd hit a network/subprocess) — the fake
    covers behaviour below; this pins the shape for the whole registry."""
    assert list_models(), "a pass over no backend proves nothing"
    for name in list_models():
        backend = get_model(name)
        assert isinstance(backend, ModelBackend), name
        assert isinstance(backend.name, str) and backend.name, name
        assert callable(backend.run), name


def test_get_model_defaults_to_the_default_model():
    default = get_model()
    explicit = get_model("claude-code-headless")
    assert default.name == explicit.name == "claude-code-headless"


@pytest.mark.parametrize("name", [None, ""])
def test_choose_model_says_when_it_fell_back_to_the_default(name):
    choice = choose_model(name)
    assert (choice.name, choice.defaulted) == (DEFAULT_MODEL, True)
    assert get_model(name).name == choice.name


def test_choose_model_keeps_a_named_model_and_says_it_was_named():
    choice = choose_model("fake")
    assert (choice.name, choice.defaulted) == ("fake", False)


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
