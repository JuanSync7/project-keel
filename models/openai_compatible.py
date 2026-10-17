"""
title: OpenAI-compatible model backend
layer: backend
public_api: no
summary: Adapter for any HTTP endpoint speaking the OpenAI chat-completions API. It is built only for a `base_url` that is an http or https URL with a host and no user part, query or fragment, written in unreserved URL characters, and, for http, only when the host is a loopback address literal (127.0.0.0/8 or ::1 by the stdlib ipaddress module, read through scripts/child_env.py canonical_host_entry; the name localhost is refused, since a name resolves through DNS or a hosts file), so the bearer token never crosses a network in clear text; and only for an `api_key_env` that config/project.json `models.credential_env` declares for this adapter (scripts/child_env.py load_policy), so no caller, and no config a caller forwards, can choose another environment variable to send as the bearer token; either refusal is a ValueError that names the argument and never a value. Between the two, the base_url's host and port must be listed in config/project.json `models.allowed_hosts` for this adapter, compared exactly in scripts/child_env.py canonical_host_entry's one form (an entry `host` matches only the scheme's default port, `host:port` only that port, nothing by suffix, prefix or wildcard); the shipped list is empty, so every host, the default one included, is refused until a project lists it, and the refusal names that key and the entry to add, never the path, before the credential variable is read, which it is through scripts/config_loader.py `env`, at each call. base_url is read-only after that check. A redirect is never followed: urllib's default handler would re-send a 301, 302 or 303 as a GET with the Authorization header to a host nobody listed, so any 3xx is a RuntimeError naming the endpoint and the status, never the Location. Defence in depth, not a sandbox (docs/adr/keel/K-0018-model-endpoint-host-allowlist.md). An unreachable endpoint is ModelUnavailable (absent); an endpoint that answers with an error, or with a body that is not a chat completion, is broken, and that body is described by its keys, never quoted. An error names the endpoint by scheme, host and port, never by its path.
"""

from __future__ import annotations

import email.message
import http.client
import ipaddress
import json
import string
import urllib.error
import urllib.parse
import urllib.request
from typing import IO, Any, Callable, Optional, Tuple

from scripts import config_loader
from scripts.child_env import canonical_host_entry, load_policy

from .contracts import ModelBackend, ModelUnavailable

__all__ = ["OpenAICompatible"]

# A transport is (url, payload, headers, timeout) -> parsed-json dict. The real
# one is urllib (stdlib, in-process — no curl/subprocess); tests inject a fake.
Transport = Callable[[str, dict, dict, float], dict]

# The wire format is HTTP; any other scheme urllib can open (file:, ftp:) is
# not an endpoint this adapter talks to.
_SCHEMES = ("http", "https")
# The scheme that carries the bearer token unencrypted, admitted only to a
# loopback address, where the request never reaches a network.
_CLEAR_SCHEME = "http"
# The port a URL with no written port is sent to, per scheme: an allowlist entry
# with no port matches only this one.
_DEFAULT_PORTS = {"http": 80, "https": 443}
_MANIFEST_KEY = "models.credential_env"
_HOSTS_KEY = "models.allowed_hosts"
# A base_url is refused unless every character is one of these. urlsplit drops
# a tab, a newline and leading whitespace and urllib then refuses or re-reads
# them, so a URL holding one is read one way by the check and another way by
# the request; a backslash is a path separator to some readers and not others.
# `?` and `#` are absent because the adapter appends its own path.
_URL_CHARS = frozenset(string.ascii_letters + string.digits + "-._~:/[]%@!$&'()*+,;=")


def _checked_base_url(base_url: str) -> urllib.parse.SplitResult:
    """*base_url*'s parts, or ValueError when it is not an http(s) URL with a
    host and no user part, query or fragment, or when it is http to a host
    that is not a loopback address. The message never quotes the
    URL, since the part refused may be a credential. The caller rebuilds the
    URL it requests from these parts, so the request cannot go anywhere the
    check did not see."""
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
    if parts.scheme == _CLEAR_SCHEME and not _is_loopback(host):
        raise ValueError(
            "base_url uses `%s` to host `%s`, which is not a loopback address, "
            "so the credential would cross the network in clear text; use "
            "https, or a loopback address for a local server, written as an "
            "address (`http://127.0.0.1` or `http://[::1]`): a name such as "
            "localhost resolves through DNS or a hosts file, which is not "
            "trusted" % (parts.scheme, host)
        )
    return parts


def _written(host: str) -> str:
    """*host* as an allowlist entry writes it: urlsplit strips an IPv6
    literal's brackets, and an entry keeps them."""
    return "[%s]" % host if ":" in host else host


def _is_loopback(host: str) -> bool:
    """Whether *host*, as urlsplit reads it, is a loopback address literal:
    127.0.0.0/8 or ::1, by the stdlib's definition. A name is not one, since
    it resolves through DNS or a hosts file; neither is a host with no single
    form in canonical_host_entry (a numeric respelling, an IPv4-mapped
    address, a zone id), so the address tested is the one the allowlist
    compares."""
    try:
        canonical = canonical_host_entry(_written(host))
        address = ipaddress.ip_address(canonical.strip("[]"))
    except ValueError:
        return False
    return address.is_loopback


def _checked_host(
    adapter: str, scheme: str, host: str, port: Optional[int], entries: Tuple[str, ...]
) -> None:
    """ValueError unless *entries* (config/project.json
    `models.allowed_hosts.<adapter>`) lists *host* on *port* (None: the
    scheme's default port), compared in canonical_host_entry's one form.

    An entry `host` matches only the scheme's default port and `host:port` only
    that port; nothing else matches, so no suffix, prefix or wildcard does. A
    host with no single form (a trailing dot, a zone id, a numeric spelling
    other than a dotted quad) is refused, not rewritten. The message names
    the key and the entry to add, never the URL's path."""
    effective = _DEFAULT_PORTS[scheme] if port is None else port
    written = _written(host)
    key = "config/project.json `%s.%s`" % (_HOSTS_KEY, adapter)
    try:
        bare = canonical_host_entry(written)
        with_port = canonical_host_entry("%s:%d" % (written, effective))
    except ValueError as why:
        # `from None`: the reason never quotes the host, and a chained cause
        # would carry nothing more.
        raise ValueError(
            "base_url's host cannot be compared with %s: %s; write base_url's "
            "host in that form" % (key, why)
        ) from None
    if with_port in entries or (
        effective == _DEFAULT_PORTS[scheme] and bare in entries
    ):
        return
    wanted = bare if effective == _DEFAULT_PORTS[scheme] else with_port
    raise ValueError(
        "base_url names a host %s does not list; this adapter sends its "
        "credential there, so add `%s` to that list" % (key, wanted)
    )


def _checked_key_env(adapter: str, api_key_env: str, declared: Tuple[str, ...]) -> str:
    """*api_key_env*, or ValueError when *declared* (config/project.json
    `models.credential_env.<adapter>`) does not list it."""
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Follows no redirect. urllib's default handler re-sends a request
    answered 301, 302 or 303 as a GET to the `Location` it was given, carrying
    the Authorization header, so the credential would reach a host
    models.allowed_hosts never listed (measured on the stdlib server; 307 and
    308 after a POST are not followed). Returning None leaves the 3xx as an
    HTTPError, which _post_json refuses."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: email.message.Message,
        newurl: str,
    ) -> Optional[urllib.request.Request]:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _urlopen(req: urllib.request.Request, timeout: float) -> Any:
    """Open *req* through the opener that follows no redirect."""
    return _OPENER.open(req, timeout=timeout)  # noqa: S310 (own, checked URL)


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    """POST ``payload`` as JSON and return the decoded JSON response (stdlib)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _urlopen(req, timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            exc.close()
            # `from None`, and the Location is not quoted: it can carry a
            # path that is itself a key.
            raise RuntimeError(
                "the endpoint at %s answered with a redirect (HTTP %d), which is "
                "refused because the credential would follow it; point base_url "
                "at the URL the endpoint serves from" % (_endpoint(url), exc.code)
            ) from None
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
    declares for this adapter, and ``base_url`` an https URL, or an http URL
    to a loopback address literal, with a host and no user part, query or
    fragment, whose host and port
    ``models.allowed_hosts`` lists for this adapter; anything else is a
    ValueError at construction, checked in that order, so an unlisted host is
    refused before the credential variable is looked at. The shipped list is
    empty, so the default ``base_url`` is refused until a project lists its
    host. A redirect is refused, never followed. Defence in depth, not a
    sandbox: whoever can edit config/project.json can list any host.
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
        parts = _checked_base_url(base_url)
        policy = load_policy()
        _checked_host(
            self.name,
            parts.scheme,
            parts.hostname or "",
            parts.port,
            policy.allowed_hosts.get(self.name, ()),
        )
        # netloc is host[:port] here (no user part); the host is lowercased the
        # way `hostname` reads it, so the text sent is the host that was checked.
        self._base_url = "%s://%s%s" % (
            parts.scheme,
            parts.netloc.lower(),
            parts.path.rstrip("/"),
        )
        self.model = model
        self.api_key_env = _checked_key_env(
            self.name, api_key_env, policy.credentials.get(self.name, ())
        )
        self.timeout = timeout
        self._transport = transport or _post_json

    @property
    def base_url(self) -> str:
        """The URL checked at construction; read-only, so the host the
        allowlist admitted is the host the credential is sent to."""
        return self._base_url

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
        key = config_loader.env(self.api_key_env)
        if key:
            headers["Authorization"] = "Bearer " + key
        data = self._transport(url, payload, headers, self.timeout)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "unexpected response from %s: %s" % (_endpoint(url), _shape(data))
            ) from exc
