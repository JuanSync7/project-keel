"""
title: Unit — OpenAI-compatible model backend
kind: tests
layer: backend
summary: The adapter builds a correct chat-completions request and parses the reply, with no network. It refuses at construction an `api_key_env` config/project.json `models.credential_env` does not declare for it and a `base_url` that is not an http or https URL with a host and no user part, query or fragment, naming the argument and never a value. It describes an unexpected response body by its keys without quoting it, and names an endpoint in an error by scheme, host and port, never by its path. It requests the URL rebuilt from the parts it checked, and a refusal by urllib or a reply that is not JSON keeps neither the path nor the body. It sends the credential only to a base_url whose host and port config/project.json `models.allowed_hosts.openai-compatible` lists exactly (an entry with no port only on the scheme's default port; no prefix, suffix, subdomain, trailing dot, numeric respelling, IPv4-mapped address or zone id), refusing every other one before any request and before the credential variable is read, with a message naming the key and the entry to add and never the path or the key. It sends http only to a loopback address literal (127.0.0.0/8 or ::1), refusing a listed name, localhost included with the address to write instead, a private or unspecified address and a numeric respelling, before the credential variable is read and with the same message whether it is set or not, naming the scheme and host and never the path or the key; https to any listed host is unaffected. The default base_url is refused until listed, and base_url is read-only after the check.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from models import get_model  # noqa: E402
from scripts.child_env import load_policy  # noqa: E402

pytestmark = pytest.mark.unit

_ADAPTER = "openai-compatible"
_URL = "https://llm.example/v1"


def allowing(monkeypatch, *entries, listed=True):
    """Have the adapter read a policy whose `models.allowed_hosts` lists
    *entries* for it (or, with listed=False, does not name it at all), so a
    test states the hosts it relies on instead of inheriting the shipped list,
    which is empty."""
    from models import openai_compatible as mod

    hosts = {_ADAPTER: tuple(entries)} if listed else {}
    policy = load_policy()._replace(allowed_hosts=hosts)
    monkeypatch.setattr(mod, "load_policy", lambda root=None: policy)
    return policy


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
    allowing(monkeypatch, "llm.example")
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
    allowing(monkeypatch, "llm.example")
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
    allowing(monkeypatch, "llm.example")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured: dict = {}
    backend = get_model(
        "openai-compatible", base_url=_URL, transport=_captured_transport(captured)
    )
    backend.run("ping")
    assert "Authorization" not in captured["headers"]


def test_optional_params_pass_through(monkeypatch):
    allowing(monkeypatch, "llm.example")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    captured: dict = {}
    backend = get_model(
        "openai-compatible", base_url=_URL, transport=_captured_transport(captured)
    )
    backend.run("ping", temperature=0.0, max_tokens=16)
    assert captured["payload"]["temperature"] == 0.0
    assert captured["payload"]["max_tokens"] == 16


def test_unexpected_response_shape_raises(monkeypatch):
    allowing(monkeypatch, "llm.example")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")

    def bad_transport(url, payload, headers, timeout):
        return {"error": {"message": "nope"}}  # no 'choices'

    backend = get_model("openai-compatible", base_url=_URL, transport=bad_transport)
    with pytest.raises(RuntimeError):
        backend.run("ping")


# --- absent vs broken over the default (urllib) transport ------------------------


def test_an_unreachable_endpoint_is_unavailable(monkeypatch):
    import urllib.error

    from models import ModelUnavailable
    from models import openai_compatible as mod

    def refuse(req, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(mod, "_urlopen", refuse)
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

    monkeypatch.setattr(mod, "_urlopen", fail)
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
    allowing(monkeypatch, "llm.example")
    monkeypatch.setenv("UNRELATED_SECRET", "canary-not-a-model-key")
    with pytest.raises(ValueError) as info:
        get_model(
            "openai-compatible",
            base_url=_URL,
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
        "https://llm.example/v1?",
        "https://llm.example/v1#",
        "https://llm.example/v1/to ken",
        "https://llm.example\t/v1/token",
        " https://llm.example/v1/token",
        "https://llm.example/v1/\x7ftoken",
        "https://llm.example/v1/tok\u00e9n",
        "https://llm.example\\@token.example/v1",
    ],
)
def test_a_base_url_that_is_not_a_plain_http_endpoint_is_refused(monkeypatch, base_url):
    # The host is listed, so the URL's own shape is what refuses each one.
    allowing(monkeypatch, "llm.example", "llm.example:8443")
    with pytest.raises(ValueError) as info:
        get_model("openai-compatible", base_url=base_url, transport=_refusing_transport)
    assert "base_url" in str(info.value)
    assert "allowed_hosts" not in str(info.value)
    assert "pw" not in str(info.value) and "token" not in str(info.value)


def test_an_unexpected_response_is_described_by_shape_never_quoted(monkeypatch):
    """An endpoint may echo the request's credential in its error body; the
    exception a report records names the body's keys, not its content."""
    allowing(monkeypatch, "llm.example")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-canary")

    def echoing(url, payload, headers, timeout):
        return {"error": "bad", "echo": headers["Authorization"]}

    backend = get_model("openai-compatible", base_url=_URL, transport=echoing)
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

    monkeypatch.setattr(mod, "_urlopen", refuse)
    with pytest.raises(ModelUnavailable) as caught:
        mod._post_json(_KEYED_URL + "/chat/completions", {}, {}, 1.0)
    assert "path-canary" not in str(caught.value)
    assert "https://llm.example:8443" in str(caught.value)


def test_an_unexpected_response_names_the_endpoint_without_its_path(monkeypatch):
    allowing(monkeypatch, "llm.example:8443")
    backend = get_model(
        "openai-compatible", base_url=_KEYED_URL, transport=lambda *a: {"error": "x"}
    )
    with pytest.raises(RuntimeError) as info:
        backend.run("ping")
    assert "path-canary" not in str(info.value)
    assert "https://llm.example:8443" in str(info.value)


def test_a_refused_base_url_leaves_no_parser_text_on_the_exception_chain(monkeypatch):
    """The URL parser's own error can quote the text it rejected, and a
    traceback prints a chained cause."""
    allowing(monkeypatch, "llm.example")
    with pytest.raises(ValueError) as info:
        get_model("openai-compatible", base_url="https://token@[llm.example/v1")
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_the_url_requested_is_built_from_the_parts_that_were_checked(monkeypatch):
    """What is checked and what is sent are one reading of the URL: the
    adapter requests the scheme, host, port and path the check saw."""
    allowing(monkeypatch, "llm.example:8443")
    captured = {}
    backend = get_model(
        "openai-compatible",
        base_url="HTTPS://LLM.Example:8443/v1/",
        transport=_captured_transport(captured),
    )
    backend.run("ping")
    assert captured["url"] == "https://llm.example:8443/v1/chat/completions"


@pytest.mark.parametrize(
    "error",
    [
        "invalid-url",
        "value-error",
    ],
)
def test_a_url_urllib_refuses_is_named_without_its_path(monkeypatch, error):
    """urllib's own refusal quotes the path it rejected."""
    import http.client

    from models import openai_compatible as mod

    raised = {
        "invalid-url": http.client.InvalidURL("can't contain '/v1/keys/path-canary'"),
        "value-error": ValueError("unknown url type: '/v1/keys/path-canary'"),
    }[error]

    def refuse(req, timeout):
        raise raised

    monkeypatch.setattr(mod, "_urlopen", refuse)
    with pytest.raises(RuntimeError) as caught:
        mod._post_json(_KEYED_URL + "/chat/completions", {}, {}, 1.0)
    assert "path-canary" not in str(caught.value)
    assert "https://llm.example:8443" in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_a_reply_that_is_not_json_is_broken_and_keeps_no_copy_of_the_body(monkeypatch):
    """The JSON parser's error holds the whole document it could not read,
    and an endpoint may echo the request's credential in it."""
    import io

    from models import ModelUnavailable
    from models import openai_compatible as mod

    monkeypatch.setattr(
        mod,
        "_urlopen",
        lambda req, timeout: io.BytesIO(b"<html>sk-canary</html>"),
    )
    with pytest.raises(RuntimeError) as caught:
        mod._post_json(_KEYED_URL + "/chat/completions", {}, {}, 1.0)
    assert not isinstance(caught.value, ModelUnavailable)
    assert "sk-canary" not in str(caught.value) and "path-canary" not in str(
        caught.value
    )
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


# --- where the credential may go: config/project.json models.allowed_hosts -----

_KEY_CANARY = "sk-host-canary"
_PATH = "/v1/path-canary"
# (base_url, entries listed, URL requested): the host and effective port match
# an entry exactly, in one canonical form.
_ADMITTED = [
    ("https://llm.example" + _PATH, ["llm.example"], "https://llm.example"),
    ("HTTPS://LLM.Example:443" + _PATH, ["llm.example"], "https://llm.example:443"),
    (
        "https://llm.example:8443" + _PATH,
        ["llm.example:8443"],
        "https://llm.example:8443",
    ),
    ("http://127.0.0.1:8080" + _PATH, ["127.0.0.1:8080"], "http://127.0.0.1:8080"),
    ("http://[::1]:8080" + _PATH, ["[::1]:8080"], "http://[::1]:8080"),
    # An entry with no port matches http's default port too, on a loopback host.
    ("http://127.0.0.1" + _PATH, ["127.0.0.1"], "http://127.0.0.1"),
]
# (base_url, entries, or None when the adapter is not named at all).
_REFUSED = {
    "empty-list": ("https://llm.example" + _PATH, []),
    "missing-key": ("https://llm.example" + _PATH, None),
    "entry-without-port-vs-8443": ("https://llm.example:8443" + _PATH, ["llm.example"]),
    "entry-8443-vs-default": ("https://llm.example" + _PATH, ["llm.example:8443"]),
    "https-default-on-http": ("http://127.0.0.1:443" + _PATH, ["127.0.0.1"]),
    "prefix": ("https://evil-llm.example" + _PATH, ["llm.example"]),
    "suffix": ("https://llm.example.evil.example" + _PATH, ["llm.example"]),
    "subdomain": ("https://sub.llm.example" + _PATH, ["llm.example"]),
    "trailing-dot": ("https://llm.example." + _PATH, ["llm.example"]),
    "integer-host": ("https://2130706433" + _PATH, ["127.0.0.1"]),
    "short-quad": ("https://127.1" + _PATH, ["127.0.0.1"]),
    "hex-quad": ("https://0x7f.0.0.1" + _PATH, ["127.0.0.1"]),
    "octal-quad": ("https://0177.0.0.1" + _PATH, ["127.0.0.1"]),
    "ipv4-mapped": ("https://[::ffff:127.0.0.1]" + _PATH, ["127.0.0.1"]),
    "zone-id": ("https://[fe80::1%25eth0]:8080" + _PATH, ["[fe80::1]:8080"]),
    "port-zero": ("https://llm.example:0" + _PATH, ["llm.example"]),
}


@pytest.mark.parametrize("base_url, entries, origin", _ADMITTED)
def test_a_base_url_host_is_sent_the_credential_only_when_config_lists_it(
    monkeypatch, base_url, entries, origin
):
    allowing(monkeypatch, *entries)
    monkeypatch.setenv("OPENAI_API_KEY", _KEY_CANARY)
    captured: dict = {}
    backend = get_model(
        "openai-compatible", base_url=base_url, transport=_captured_transport(captured)
    )
    backend.run("ping")
    assert captured["url"] == origin + _PATH + "/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer " + _KEY_CANARY


@pytest.mark.parametrize("case", sorted(_REFUSED))
def test_a_base_url_host_config_does_not_list_is_refused_before_any_request(
    monkeypatch, case
):
    base_url, entries = _REFUSED[case]
    allowing(monkeypatch, *(entries or ()), listed=entries is not None)
    monkeypatch.setenv("OPENAI_API_KEY", _KEY_CANARY)
    with pytest.raises(ValueError) as info:
        get_model("openai-compatible", base_url=base_url, transport=_refusing_transport)
    message = str(info.value)
    assert "models.allowed_hosts.openai-compatible" in message, message
    assert "path-canary" not in message and _KEY_CANARY not in message, message
    assert info.value.__cause__ is None


def test_the_refusal_names_the_host_and_port_to_list():
    """The message says what to add, in the form an entry is written."""
    from models.openai_compatible import _checked_host

    with pytest.raises(ValueError) as info:
        _checked_host(_ADAPTER, "https", "llm.example", 8443, ())
    assert "`llm.example:8443`" in str(info.value)


def test_both_tables_ran():
    """A pass over zero cases would prove nothing."""
    assert len(_ADMITTED) >= 1 and len(_REFUSED) >= 1


def test_the_default_base_url_is_refused_until_its_host_is_listed(monkeypatch):
    """The adapter's default endpoint is one vendor's; a project lists it
    before the adapter will send a credential there."""
    allowing(monkeypatch)
    with pytest.raises(ValueError) as info:
        get_model("openai-compatible", transport=_refusing_transport)
    assert "models.allowed_hosts.openai-compatible" in str(info.value)


def test_the_host_is_checked_before_the_credential_variable(monkeypatch):
    """With an unlisted host and an undeclared variable, the host refuses
    first, and the environment is not read for any credential."""
    from models import openai_compatible as mod

    allowing(monkeypatch)
    read = []

    class Spy(dict):
        def get(self, key, default=None):
            read.append(key)
            return super().get(key, default)

        def __getitem__(self, key):
            read.append(key)
            return super().__getitem__(key)

    monkeypatch.setattr(mod.os, "environ", Spy(UNRELATED_SECRET="canary"))
    with pytest.raises(ValueError) as info:
        get_model(
            "openai-compatible",
            base_url=_URL,
            api_key_env="UNRELATED_SECRET",
            transport=_refusing_transport,
        )
    assert "models.allowed_hosts" in str(info.value)
    assert "models.credential_env" not in str(info.value)
    assert read == []


def test_the_checked_base_url_cannot_be_replaced_after_construction(monkeypatch):
    allowing(monkeypatch, "llm.example")
    backend = get_model(
        "openai-compatible", base_url=_URL, transport=_refusing_transport
    )
    with pytest.raises(AttributeError):
        backend.base_url = "https://elsewhere.example/v1"
    assert backend.base_url == _URL


# --- http only to a loopback address: the bearer token is never sent in clear --
# --- text over a network -----------------------------------------------------

# (base_url, entry listed): http to a loopback address literal, 127.0.0.0/8 or
# ::1, is admitted once listed.
_HTTP_LOOPBACK = [
    ("http://127.0.0.1:8080" + _PATH, "127.0.0.1:8080"),
    ("http://127.5.6.7:8080" + _PATH, "127.5.6.7:8080"),
    ("http://[::1]:8080" + _PATH, "[::1]:8080"),
]
# (base_url, entry listed): every host is listed, so the scheme rule, not the
# allowlist, is what refuses each one.
_HTTP_REFUSED = {
    "name": ("http://llm.example" + _PATH, "llm.example"),
    "localhost": ("http://localhost:8080" + _PATH, "localhost:8080"),
    "private-ipv4": ("http://10.0.0.5:8080" + _PATH, "10.0.0.5:8080"),
    "private-ipv4-192": ("http://192.168.1.10" + _PATH, "192.168.1.10"),
    "private-ipv6": ("http://[fd00::1]:8080" + _PATH, "[fd00::1]:8080"),
    "unspecified": ("http://0.0.0.0:8080" + _PATH, "0.0.0.0:8080"),
    "numeric-respelling": ("http://2130706433" + _PATH, "127.0.0.1"),
    "ipv4-mapped": ("http://[::ffff:127.0.0.1]:8080" + _PATH, "127.0.0.1:8080"),
}


@pytest.mark.parametrize("base_url, entry", _HTTP_LOOPBACK)
def test_http_to_a_loopback_address_is_admitted(monkeypatch, base_url, entry):
    allowing(monkeypatch, entry)
    monkeypatch.setenv("OPENAI_API_KEY", _KEY_CANARY)
    captured: dict = {}
    backend = get_model(
        "openai-compatible", base_url=base_url, transport=_captured_transport(captured)
    )
    backend.run("ping")
    assert captured["url"] == base_url + "/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer " + _KEY_CANARY


@pytest.mark.parametrize("case", sorted(_HTTP_REFUSED))
def test_http_to_a_host_that_is_not_a_loopback_address_is_refused(monkeypatch, case):
    base_url, entry = _HTTP_REFUSED[case]
    allowing(monkeypatch, entry)
    monkeypatch.setenv("OPENAI_API_KEY", _KEY_CANARY)
    with pytest.raises(ValueError) as info:
        get_model("openai-compatible", base_url=base_url, transport=_refusing_transport)
    message = str(info.value)
    assert "base_url" in message and "`http`" in message, message
    assert "loopback" in message and "use https" in message, message
    assert "allowed_hosts" not in message, message
    assert "path-canary" not in message and _KEY_CANARY not in message, message
    assert info.value.__cause__ is None


def test_the_http_refusal_names_the_host():
    from models.openai_compatible import _checked_base_url

    with pytest.raises(ValueError) as info:
        _checked_base_url("http://llm.example:8080" + _PATH)
    assert "`llm.example`" in str(info.value)


def test_http_to_localhost_is_refused_with_the_address_to_write(monkeypatch):
    """`localhost` is a name, resolved through DNS or a hosts file, which the
    allowlist does not trust; the refusal says to write the address."""
    allowing(monkeypatch, "localhost:8080")
    with pytest.raises(ValueError) as info:
        get_model(
            "openai-compatible",
            base_url="http://localhost:8080/v1",
            transport=_refusing_transport,
        )
    assert "`http://127.0.0.1`" in str(info.value)


def test_https_to_a_host_that_is_not_a_loopback_address_is_unaffected(monkeypatch):
    allowing(monkeypatch, "10.0.0.5:8443")
    captured: dict = {}
    backend = get_model(
        "openai-compatible",
        base_url="https://10.0.0.5:8443/v1",
        transport=_captured_transport(captured),
    )
    backend.run("ping")
    assert captured["url"] == "https://10.0.0.5:8443/v1/chat/completions"


def test_the_http_refusal_comes_before_the_credential_variable_is_read(monkeypatch):
    """The host is listed and the variable undeclared: the scheme refuses
    first, and the environment is not read for any credential."""
    from models import openai_compatible as mod

    allowing(monkeypatch, "llm.example")
    read = []

    class Spy(dict):
        def get(self, key, default=None):
            read.append(key)
            return super().get(key, default)

        def __getitem__(self, key):
            read.append(key)
            return super().__getitem__(key)

    monkeypatch.setattr(mod.os, "environ", Spy(UNRELATED_SECRET="canary"))
    with pytest.raises(ValueError) as info:
        get_model(
            "openai-compatible",
            base_url="http://llm.example/v1",
            api_key_env="UNRELATED_SECRET",
            transport=_refusing_transport,
        )
    assert "loopback" in str(info.value)
    assert "models.credential_env" not in str(info.value)
    assert read == []


def test_the_http_refusal_is_the_same_with_the_credential_set_or_unset(monkeypatch):
    allowing(monkeypatch, "llm.example")
    messages = []
    for value in (_KEY_CANARY, None):
        if value is None:
            monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        else:
            monkeypatch.setenv("OPENAI_API_KEY", value)
        with pytest.raises(ValueError) as info:
            get_model(
                "openai-compatible",
                base_url="http://llm.example/v1",
                transport=_refusing_transport,
            )
        messages.append(str(info.value))
    assert messages[0] == messages[1] and "loopback" in messages[0]


def test_both_http_tables_ran():
    """A pass over zero cases would prove nothing."""
    assert len(_HTTP_LOOPBACK) >= 3 and len(_HTTP_REFUSED) >= 3
