---
title: Models
kind: model
layer: backend
status: template
owner: TBD
public_api: none
tags: []
summary: Model backends the app/agents run on — adapters + registry behind one contract.
id: models-readme
created: 2026-06-17
updated: 2026-10-13
visibility: internal
canonical: true
---

# Models

Model backends the app/agents run on — adapters + registry behind one contract.

The catalog of **model backends** the system can run on. An agent is
reasoning/policy; it needs a *model* to actually run — this is where
those models live and how each is launched.

## What ships here

| Member | Purpose | Not for |
|--------|---------|---------|
| `claude_code_headless.py` | The `claude-code-headless` backend: shells out to `claude -p <prompt> --model <m>` and returns stdout. A binary that is not on PATH raises `ModelUnavailable` (absent); a non-zero exit raises `RuntimeError` (broken). The CLI child gets the allowlisted environment plus `models.credential_env["claude-code-headless"]` (config/project.json, via `scripts/child_env.py`); a name the parent lacks is absent | Any HTTP endpoint — that is `openai_compatible.py`; offline tests or dry runs — that is `fake.py`; choosing which backend runs — `registry.py` |
| `config/` | Per-model configuration defaults (`default.example.toml`: default model name, launch flags), committed as examples only | API keys or any secret — those come from the environment (`api_key_env`), never a file here; which credential names a CLI child receives — config/project.json `models.credential_env`; the name→adapter map — `registry.py` |
| `contracts.py` | The `ModelBackend` ABC every adapter implements (`run(prompt, **opts) -> str`) and `ModelUnavailable`, the owned error for a backend that cannot run here — distinct from one that ran and failed | Provider logic of any kind — an adapter; selection — `registry.py` |
| `fake.py` | The `fake` backend: deterministic, offline, no network and no binary — what tests and disconnected development run on | Real inference; it echoes a canned answer, so a green run on `fake` proves the plumbing, not the model |
| `openai_compatible.py` | The `openai-compatible` backend: any server speaking the OpenAI chat-completions wire format (OpenAI, Ollama, vLLM, an internal gateway) via stdlib `urllib`, key from the environment variable `api_key_env` names, which must be listed in config/project.json `models.credential_env.openai-compatible`; that, a `base_url` that is not an http or https URL with a host and no user part, query or fragment, written without a space, a control character, a backslash or a non-ASCII letter, and a `base_url` whose host `models.allowed_hosts.openai-compatible` does not list, is a `ValueError` at construction. An unreachable endpoint (refused, no route, unknown host) raises `ModelUnavailable`; a redirect is refused as a `RuntimeError`; an HTTP error from a reachable one propagates as the failure it is | The Claude Code CLI — that is `claude_code_headless.py`; holding a key — the environment does; choosing where the key may go — config/project.json `models.allowed_hosts` does |
| `registry.py` | `get_model(name=None)` / `list_models()`: the name → adapter map and the default (`claude-code-headless`); an unknown name is a `KeyError` naming the options | Implementing a backend — write an adapter and register it here; agents import the name, never a concrete class |

`ModelUnavailable` is the **absent-versus-broken** split for models (ADR-K-0007's
rule, applied here): the doers that call a model — `scripts/hooks/on_stop_triage.py`,
`scripts/refactor_practice.py` — catch it, print `model unavailable (...); skipping`
and exit 0, because a hook that fires on a machine without a model must not
fail the event it was attached to. A model that runs and fails still raises:
that is a defect, and it stays loud.

`agents/` depend on this dir: an agent asks the registry for a
backend by name and calls `.run(prompt)`. To add a provider (an
Anthropic API client, a local model), drop in an adapter that
implements `ModelBackend` and register it — no agent code changes.

## Where an adapter may send its credential

config/project.json `models.allowed_hosts` lists, per adapter that sends a
credential itself, the hosts it may send it to. It ships as
`{"openai-compatible": []}`: an empty list, so `openai-compatible` refuses
every `base_url`, its default one included, until the project lists the
endpoint's host. A project that calls an endpoint at
`https://llm.example/v1` and a local server at `http://127.0.0.1:8080/v1`
writes:

```json
"allowed_hosts": {
  "openai-compatible": ["llm.example", "127.0.0.1:8080"]
}
```

- **An entry is `host` or `host:port`, in one canonical form.** The host is
  a lower-case ASCII name, a dotted-quad IPv4 address or a bracketed
  compressed IPv6 address such as `[::1]:8080`; an internationalised name is
  written in its `xn--` form. check_X (through `scripts/child_env.py`
  `canonical_host_entry`) refuses an entry in any other form and names the
  form to write, and refuses a trailing dot, a wildcard, an IPv6 zone id, an
  IPv4-mapped IPv6 address and a numeric host other than a dotted quad.
- **An entry with no port matches only the scheme's default port**: 443 for
  https and 80 for http. `llm.example` admits `https://llm.example/v1` and
  not `https://llm.example:8443/v1`, which needs `llm.example:8443`.
- **Nothing matches by suffix, prefix or wildcard.** `llm.example` does not
  admit `sub.llm.example` or `llm.example.other.example`.
- **The check runs at construction**, before any request is built and before
  the credential variable is read. The `ValueError` names
  `models.allowed_hosts.openai-compatible` and the entry to add, never the
  URL's path or the credential.
- **A redirect is refused, never followed.** urllib's default handler would
  re-send a request answered 301, 302 or 303 as a GET, with the
  Authorization header, to the host the endpoint names. The adapter follows
  no redirect, and raises a `RuntimeError` naming the endpoint by scheme,
  host and port and the status, never the `Location`.
- **The scheme is not pinned.** `llm.example` admits `http://llm.example` as
  well, and an http request carries the bearer token in clear text.

Defence in depth, not a sandbox: whoever can edit config/project.json can
list any host, and the check trusts DNS. The decision and its limits are
[docs/adr/keel/K-0018-model-endpoint-host-allowlist.md](../docs/adr/keel/K-0018-model-endpoint-host-allowlist.md).
