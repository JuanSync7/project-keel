"""
title: Unit — OpenAI-compatible model backend
kind: tests
layer: backend
summary: The adapter builds a correct chat-completions request and parses the reply, with no network. It refuses at construction an `api_key_env` config/project.json `models.credential_env` does not declare for it and a `base_url` that is not an http or https URL with a host and no user part, query or fragment, naming the argument and never a value. It describes an unexpected response body by its keys without quoting it, and names an endpoint in an error by scheme, host and port, never by its path.
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


# --- what config may not choose: the credential variable and the destination ----


def _refusing_transport(url, payload, headers, timeout):
    raise AssertionError("a refused adapter must not send a request")


def test_an_undeclared_credential_variable_is_refused(monkeypatch):
    """`api_key_env` picks which environment variable leaves the process as a
    bearer token, so only a name config/project.json `models.credential_env`
    declares for this adapter is accepted."""
    monkeypatch.setenv("UNRELATED_SECRET", "canary-not-a-model-key")
    with pytest.raises(ValueError) as info:
        get_model(
            "openai-compatible",
            api_key_env="UNRELATED_SECRET",
            transport=_refusing_transport,
        )
    assert "models.credential_env" in str(info.value)
    assert "UNRELATED_SECRET" in str(info.value)
    assert "canary-not-a-model-key" not in str(info.value)


@pytest.mark.parametrize(
    "base_url",
    [
        "file:///etc/passwd",
        "ftp://llm.example/v1",
        "llm.example/v1",
        "https:///v1",
        "https://user:pw@llm.example/v1",
        "https://token@llm.example/v1",
        "https://llm.example/v1?api_key=token",
        "https://llm.example/v1#token",
        "https://token@[llm.example/v1",
        "https://llm.example:token/v1",
    ],
)
def test_a_base_url_that_is_not_a_plain_http_endpoint_is_refused(base_url):
    with pytest.raises(ValueError) as info:
        get_model("openai-compatible", base_url=base_url, transport=_refusing_transport)
    assert "base_url" in str(info.value)
    assert "pw" not in str(info.value) and "token" not in str(info.value)


def test_an_unexpected_response_is_described_by_shape_never_quoted(monkeypatch):
    """An endpoint may echo the request's credential in its error body; the
    exception a report records names the body's keys, not its content."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-canary")

    def echoing(url, payload, headers, timeout):
        return {"error": "bad", "echo": headers["Authorization"]}

    backend = get_model("openai-compatible", transport=echoing)
    with pytest.raises(RuntimeError) as info:
        backend.run("ping")
    assert "sk-canary" not in str(info.value)
    assert "echo" in str(info.value) and "error" in str(info.value)


# --- an error names the endpoint by scheme, host and port, never by its path ----

_KEYED_URL = "https://llm.example:8443/v1/keys/path-canary"


def test_an_unreachable_endpoint_is_named_without_its_path(monkeypatch):
    """A gateway may issue a per-caller URL whose path is itself the key, and
    this message reaches logs and the eval report."""
    import urllib.error

    from models import ModelUnavailable
    from models import openai_compatible as mod

    def refuse(req, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(mod.urllib.request, "urlopen", refuse)
    with pytest.raises(ModelUnavailable) as caught:
        mod._post_json(_KEYED_URL + "/chat/completions", {}, {}, 1.0)
    assert "path-canary" not in str(caught.value)
    assert "https://llm.example:8443" in str(caught.value)


def test_an_unexpected_response_names_the_endpoint_without_its_path():
    backend = get_model(
        "openai-compatible", base_url=_KEYED_URL, transport=lambda *a: {"error": "x"}
    )
    with pytest.raises(RuntimeError) as info:
        backend.run("ping")
    assert "path-canary" not in str(info.value)
    assert "https://llm.example:8443" in str(info.value)


def test_a_refused_base_url_leaves_no_parser_text_on_the_exception_chain():
    """The URL parser's own error can quote the text it rejected, and a
    traceback prints a chained cause."""
    with pytest.raises(ValueError) as info:
        get_model("openai-compatible", base_url="https://token@[llm.example/v1")
    assert info.value.__cause__ is None and info.value.__suppress_context__
