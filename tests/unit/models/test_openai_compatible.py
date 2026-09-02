"""
title: Unit — OpenAI-compatible model backend
kind: tests
layer: backend
summary: The adapter builds a correct chat-completions request and parses the reply, with no network.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from models import get_model  # noqa: E402

pytestmark = pytest.mark.unit


def _captured_transport(captured, reply="hi there"):
    """A fake HTTP transport: record the call, return a canned chat response."""

    def transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {"choices": [{"message": {"role": "assistant", "content": reply}}]}

    return transport


def test_run_posts_chat_completions_and_returns_the_message(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    captured: dict = {}
    backend = get_model(
        "openai-compatible",
        base_url="https://llm.example/v1",
        model="some-model",
        transport=_captured_transport(captured, reply="the cake is a lie"),
    )

    out = backend.run("What is the cake?")

    assert out == "the cake is a lie"  # parsed from choices[0]
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    assert captured["payload"]["model"] == "some-model"
    assert captured["payload"]["messages"] == [
        {"role": "user", "content": "What is the cake?"}
    ]
    # Secret comes from the environment, never from config/constructor.
    assert captured["headers"]["Authorization"] == "Bearer sk-test-123"


def test_base_url_trailing_slash_is_normalised(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    captured: dict = {}
    backend = get_model(
        "openai-compatible",
        base_url="https://llm.example/v1/",
        transport=_captured_transport(captured),
    )
    backend.run("ping")
    assert (
        captured["url"] == "https://llm.example/v1/chat/completions"
    )  # no doubled slash


def test_missing_api_key_means_no_auth_header(monkeypatch):
    """A keyless endpoint (e.g. a local Ollama/vLLM server) is valid: send no
    Authorization header rather than 'Bearer None'."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured: dict = {}
    backend = get_model("openai-compatible", transport=_captured_transport(captured))
    backend.run("ping")
    assert "Authorization" not in captured["headers"]


def test_optional_params_pass_through(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    captured: dict = {}
    backend = get_model("openai-compatible", transport=_captured_transport(captured))
    backend.run("ping", temperature=0.0, max_tokens=16)
    assert captured["payload"]["temperature"] == 0.0
    assert captured["payload"]["max_tokens"] == 16


def test_unexpected_response_shape_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")

    def bad_transport(url, payload, headers, timeout):
        return {"error": {"message": "nope"}}  # no 'choices'

    backend = get_model("openai-compatible", transport=bad_transport)
    with pytest.raises(RuntimeError):
        backend.run("ping")


# --- absent vs broken over the default (urllib) transport ------------------------


def test_an_unreachable_endpoint_is_unavailable(monkeypatch):
    import urllib.error

    from models import ModelUnavailable
    from models import openai_compatible as mod

    def refuse(req, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(mod.urllib.request, "urlopen", refuse)
    with pytest.raises(ModelUnavailable) as caught:
        mod._post_json("http://localhost:1/v1/chat/completions", {}, {}, 1.0)
    assert "connection refused" in str(caught.value)


def test_an_endpoint_that_answers_with_an_error_is_broken_not_absent(monkeypatch):
    """HTTP 500 means the server is there and failing; skipping would hide a defect."""
    import urllib.error

    from models import ModelUnavailable
    from models import openai_compatible as mod

    def fail(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, None)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fail)
    with pytest.raises(urllib.error.HTTPError):
        mod._post_json("http://h/v1/chat/completions", {}, {}, 1.0)
    with pytest.raises(Exception) as caught:
        mod._post_json("http://h/v1/chat/completions", {}, {}, 1.0)
    assert not isinstance(caught.value, ModelUnavailable)
