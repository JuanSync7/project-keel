---
title: "ADR-K-0018: a model adapter sends its credential only to a host config lists for it"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, models, credentials, allowlist, redirect, child-env]
summary: "models/openai_compatible.py sent its bearer token to whatever host base_url named, and urllib re-sent it to whatever host a 301, 302 or 303 named. Now config/project.json models.allowed_hosts lists, per adapter, the `host` or `host:port` entries it may send its credential to, compared exactly in one canonical form that scripts/child_env.py canonical_host_entry defines; an entry with no port matches only the scheme's default port, and http is refused unless the host is a loopback address literal. The list ships empty, so every host, the adapter's default one included, is refused until a project lists it. The check runs at construction, before any request is built and before the credential variable is read, and any redirect is refused rather than followed. Defence in depth, not a sandbox."
id: docs-adr-0018-model-endpoint-host-allowlist
created: 2026-10-12
updated: 2026-10-15
visibility: internal
canonical: true
---

# ADR-K-0018: a model adapter sends its credential only to a host config lists

**Status:** accepted 2026-10-15 by the maintainer. It adds a destination rule beside the credential-variable
rule of [ADR-K-0012](K-0012-child-process-environment-allowlist.md), which
stands and is not edited.

## Context

`models/openai_compatible.py` reads a bearer token from the environment
variable `api_key_env` names and sends it to `base_url`. ADR-K-0012 and
config/project.json `models.credential_env` already decide *which* variable
may leave the process. Nothing decided *where* it may go.

- `base_url` comes from a constructor argument, and `scripts/run_evals.py`
  forwards it from config/project.json `evals.live.model_options`. Any value
  that passed the URL-shape check received the token.
- urllib's default redirect handler re-sends a POST answered 301, 302 or 303
  as a GET to the `Location` it was given, with the Authorization header.
  On the stdlib test server the second host received the header for all
  three; a 307 or 308 after a POST is not followed. A listed endpoint could
  therefore hand the token to a host nobody listed.

## Decision

1. **A list per adapter, in config.** config/project.json
   `models.allowed_hosts` maps an adapter in `models.available` to a list of
   `host` or `host:port` entries, beside `models.credential_env`. No host is
   written in code. An adapter the key does not name, an empty list and a
   missing key all allow no host.
2. **One canonical form, matched exactly.** `scripts/child_env.py`
   `canonical_host_entry` defines the form: a lower-case ASCII name, a
   dotted-quad IPv4 address or a bracketed compressed IPv6 address, then
   `:port` when a port is written. The config validator refuses an entry that
   is not already in that form, and the adapter passes the host it parsed
   from `base_url` through the same function, so the two compare one string.
   There is no wildcard, suffix, prefix or substring match.
3. **Hosts with more than one spelling are refused, not rewritten.** A
   trailing dot, an IPv6 zone id, an IPv4-mapped IPv6 address and any numeric
   host other than a dotted quad (`127.1`, `2130706433`, `0x7f.0.0.1`,
   `0177.0.0.1`) are refused in an entry and in `base_url`. A non-ASCII name
   is refused; an internationalised name is written in its `xn--` form. Case
   and IPv6 compression are canonicalised.
4. **The port rule.** An entry `host` matches only the default port of the
   URL's scheme (80 for http, 443 for https). An entry `host:port` matches
   only that port. So `llm.example` admits `https://llm.example`, and not
   `https://llm.example:8443`; `127.0.0.1` admits `http://127.0.0.1`, and not
   `http://127.0.0.1:443`.
5. **The check runs first.** The adapter checks the URL's shape, then its
   host, then `api_key_env`, all at construction. An unlisted host is refused
   before any request is built and before the credential variable is read,
   even when a test injects a transport. The refusal names
   `models.allowed_hosts.<adapter>` and the entry to add, and never the
   credential, the path or a reply. `base_url` is read-only after the check.
6. **Redirects are refused.** The adapter opens its request through an opener
   whose redirect handler follows nothing, so any 3xx is a RuntimeError naming
   the endpoint by scheme, host and port and the status, never the
   `Location`.
7. **The shipped list is empty.** `openai-compatible` ships with `[]`, so its
   default `base_url` is refused until a project lists that host.
8. **http only to a loopback address.** An `http` base_url is refused unless
   its host is a loopback address literal: 127.0.0.0/8 or `::1`, as the
   stdlib `ipaddress` module's `is_loopback` reads the host's
   `canonical_host_entry` form. A name is refused, `localhost` included,
   because a name resolves through DNS or a hosts file, which this rule does
   not trust; the refusal says to write `http://127.0.0.1` or `http://[::1]`.
   A host with no canonical form (`2130706433`, an IPv4-mapped address) is
   not a loopback address either. The check is part of the URL-shape check,
   so it runs before the host list is read and before the credential variable
   is read. Its `ValueError` names the scheme and the host, and says to use
   https or a loopback address; it never names the path or the credential.

## Consequences

- **Action is required on update.** A project that uses `openai-compatible`
  gets `models.allowed_hosts` with an empty list and must add its endpoint's
  host before the adapter will start. The refusal says which entry to add.
- **A test that builds the adapter with its defaults lists the host itself.**
  The empty default was weighed against a gate test it turned red:
  tests/unit/models/test_registry.py built every registered backend with its
  defaults, so `make unit`, and with it `make verify`, failed in keel and in
  every generated project. The default stays empty, because nothing a
  generated project runs by default builds this adapter (models/registry.py
  `DEFAULT_MODEL` names another one), and that test now lists the default
  base_url's host through a fixture. A project that does build it lists its
  host first.
- **Defence in depth, not a sandbox.** Whoever can edit config/project.json
  can list any host. The rule stops a forwarded argument, a stray
  `model_options` value or a redirect from choosing the destination; it does
  not stop the project's own author.
- **A plain-http server on another machine needs TLS in front of it.** A
  local Ollama or vLLM server on loopback works over http; the same server on
  another host is reached over https or not at all. The bearer token
  crosses a network only encrypted, though a request to a loopback port still
  reaches whichever local process holds that port.
- **A proxy sees the request.** urllib honours the proxy variables of the
  process the adapter runs in, and a proxy sees the Authorization header of an
  http request. The allowlist names the endpoint, not the route.
- **DNS answers are trusted.** The check compares names, not addresses. A
  listed name that resolves somewhere else sends the token there.
- **A project that removes an adapter removes its entry.** An
  `allowed_hosts` key for an adapter not in `models.available` is a check_X
  error, as a `credential_env` key is.

## Not for

- Which environment variable an adapter may send: ADR-K-0012 and
  `models.credential_env` decide that.
- What a child process inherits: `scripts/child_env.py` `build_child_env`.

## Alternatives considered

- **Ship the vendor's default host in the list.** Rejected. A project that
  never meant to call that vendor would send its token there by default, and
  the list would start with a vendor's name baked into a vendor-neutral
  template.
- **Match a domain suffix or a wildcard.** Rejected. A suffix rule admits any
  host under the domain, including one a third party controls, and a
  substring rule admits `llm.example.evil.example`.
- **Follow 307 and 308 only.** Rejected. A redirect target is chosen by the
  endpoint, not by config, so following any of them lets the endpoint choose
  where the token goes.
- **Check the host per request instead of at construction.** Rejected. The
  URL does not change after construction, so one check made before the
  credential is read is both earlier and simpler.
