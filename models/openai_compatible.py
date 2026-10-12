"""
title: OpenAI-compatible model backend
layer: backend
public_api: no
summary: Adapter for any HTTP endpoint speaking the OpenAI chat-completions API. It is built only for a `base_url` that is an http or https URL with a host and no user part, query or fragment, written in unreserved URL characters, and only for an `api_key_env` that config/project.json `models.credential_env` declares for this adapter (scripts/child_env.py load_policy), so no caller, and no config a caller forwards, can choose another environment variable to send as the bearer token; either refusal is a ValueError that names the argument and never a value. An unreachable endpoint is ModelUnavailable (absent); an endpoint that answers with an error, or with a body that is not a chat completion, is broken, and that body is described by its keys, never quoted. An error names the endpoint by scheme, host and port, never by its path.
"""

from __future__ import annotations

import http.client
import json
import os
import string
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from scripts.child_env import load_policy

from .contracts import ModelBackend, ModelUnavailable

__all__ = ["OpenAICompatible"]

# A transport is (url, payload, headers, timeout) -> parsed-json dict. The real
# one is urllib (stdlib, in-process — no curl/subprocess); tests inject a fake.
Transport = Callable[[str, dict, dict, float], dict]

# The wire format is HTTP; any other scheme urllib can open (file:, ftp:) is
# not an endpoint this adapter talks to.
_SCHEMES = ("http", "https")
_MANIFEST_KEY = "models.credential_env"
# A base_url is refused unless every character is one of these. urlsplit drops
# a tab, a newline and leading whitespace and urllib then refuses or re-reads
# them, so a URL holding one is read one way by the check and another way by
# the request; a backslash is a path separator to some readers and not others.
# `?` and `#` are absent because the adapter appends its own path.
_URL_CHARS = frozenset(string.ascii_letters + string.digits + "-._~:/[]%@!$&'()*+,;=")


def _checked_base_url(base_url: str) -> str:
    """*base_url* without its trailing slash, or ValueError when it is not an
    http(s) URL with a host and no user part, query or fragment. The message
    never quotes the URL, since the part refused may be a credential. The
    value returned is rebuilt from the parts that were checked, so the request
    cannot go anywhere the check did not see."""
    if not base_url or not _URL_CHARS.issuperset(base_url):
        raise ValueError(
            "base_url must be written in unreserved URL characters only: no "
            "space, control character, backslash, `?`, `#` or non-ASCII letter; "
            "percent-encode a path segment that needs one"
        )
    try:
        parts = urllib.parse.urlsplit(base_url)
        host, user, password = parts.hostname, parts.username, parts.password
        parts.port  # noqa: B018 (reading it is what refuses a port that is not a number)
    except ValueError:
        # `from None`: the parser's message can quote the text it rejected, and
        # a traceback prints a chained cause.
        raise ValueError(
            "base_url is not a URL: check its host and port; write it as "
            "scheme://host[:port]/path"
        ) from None
    if parts.scheme not in _SCHEMES or not host:
        raise ValueError(
            "base_url must be an %s URL with a host" % " or ".join(_SCHEMES)
        )
    if parts.query or parts.fragment:
        raise ValueError(
            "base_url must not carry a query or a fragment; the adapter appends "
            "its own path, and the credential is read from the environment "
            "variable `api_key_env` names"
        )
    if user is not None or password is not None:
        raise ValueError(
            "base_url must not carry a user part; the credential is read from "
            "the environment variable `api_key_env` names"
        )
    # netloc is host[:port] here (no user part); the host is lowercased the way
    # `hostname` reads it, so the text sent is the host that was checked.
    return "%s://%s%s" % (parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"))


def _checked_key_env(adapter: str, api_key_env: str) -> str:
    """*api_key_env*, or ValueError when config/project.json does not declare
    it as one of *adapter*'s credential variables."""
    declared = load_policy().credentials.get(adapter, ())
    if api_key_env not in declared:
        raise ValueError(
            "api_key_env %r is not declared in config/project.json `%s.%s` (%s); "
            "this adapter sends that variable's value to base_url, so add the "
            "name there to allow it"
            % (api_key_env, _MANIFEST_KEY, adapter, ", ".join(declared) or "none")
        )
    return api_key_env


def _endpoint(url: str) -> str:
    """The scheme, host and port of *url*, which is how an error names where a
    request went: a gateway can issue a URL whose path is itself a key, and
    this text reaches logs and reports."""
    parts = urllib.parse.urlsplit(url)
    return "%s://%s" % (parts.scheme, parts.netloc.rpartition("@")[2])


def _shape(data: object) -> str:
    """What *data* is, without its content: an endpoint may echo the request's
    credential in an error body, and this text reaches logs and reports."""
    if isinstance(data, dict):
        return "an object with keys %s" % (", ".join(sorted(map(str, data))) or "none")
    return "a %s" % type(data).__name__


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    """POST ``payload`` as JSON and return the decoded JSON response (stdlib)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (own URL)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError:
        raise  # the endpoint answered: present, and failing -- not absent
    except urllib.error.URLError as exc:
        # No route, refused, unknown host: the endpoint is not here to run.
        raise ModelUnavailable(f"cannot reach {_endpoint(url)}: {exc.reason}") from exc
    except json.JSONDecodeError:
        # `from None`: the parser's error holds the whole body it could not
        # read, and an endpoint may echo the request's credential there.
        raise RuntimeError(
            "the reply from %s is not JSON; check that base_url names a "
            "chat-completions endpoint" % _endpoint(url)
        ) from None
    except (http.client.InvalidURL, ValueError):
        # `from None`: urllib's refusal quotes the path it rejected.
        raise RuntimeError(
            "urllib cannot build a request for %s; check base_url's path for a "
            "character a URL cannot carry" % _endpoint(url)
        ) from None


class OpenAICompatible(ModelBackend):
    """Talks to ANY server speaking the OpenAI chat-completions wire format.

    The provider is a *configuration* choice, not a baked-in vendor: point
    ``base_url`` at OpenAI, a local Ollama/vLLM/LM Studio server, Together,
    Groq, or an internal gateway — the adapter is identical. The API key is read
    from the environment (``api_key_env``), never from config or constructor
    args; a keyless local server simply gets no Authorization header.
    ``api_key_env`` must be a name config/project.json ``models.credential_env``
    declares for this adapter, and ``base_url`` an http(s) URL with a host and
    no user part, query or fragment; anything else is a ValueError at
    construction.
    """

    name = "openai-compatible"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        api_key_env: str = "OPENAI_API_KEY",
        timeout: float = 60.0,
        transport: Optional[Transport] = None,
    ):
        self.base_url = _checked_base_url(base_url)
        self.model = model
        self.api_key_env = _checked_key_env(self.name, api_key_env)
        self.timeout = timeout
        self._transport = transport or _post_json

    def run(self, prompt: str, **opts) -> str:
        url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        # Trusted-caller pass-through (temperature, max_tokens, …); by design it
        # can also override model/messages — the agent, not the world, calls this.
        payload.update(opts)
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
        if key:
            headers["Authorization"] = "Bearer " + key
        data = self._transport(url, payload, headers, self.timeout)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "unexpected response from %s: %s" % (_endpoint(url), _shape(data))
            ) from exc
