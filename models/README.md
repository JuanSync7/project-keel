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
updated: 2026-09-02
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
| `claude_code_headless.py` | The `claude-code-headless` backend: shells out to `claude -p <prompt> --model <m>` and returns stdout. A binary that is not on PATH raises `ModelUnavailable` (absent); a non-zero exit raises `RuntimeError` (broken) | Any HTTP endpoint — that is `openai_compatible.py`; offline tests or dry runs — that is `fake.py`; choosing which backend runs — `registry.py` |
| `config/` | Per-model configuration defaults (`default.example.toml`: default model name, launch flags), committed as examples only | API keys or any secret — those come from the environment (`api_key_env`), never a file here; the name→adapter map — `registry.py` |
| `contracts.py` | The `ModelBackend` ABC every adapter implements (`run(prompt, **opts) -> str`) and `ModelUnavailable`, the owned error for a backend that cannot run here — distinct from one that ran and failed | Provider logic of any kind — an adapter; selection — `registry.py` |
| `fake.py` | The `fake` backend: deterministic, offline, no network and no binary — what tests and disconnected development run on | Real inference; it echoes a canned answer, so a green run on `fake` proves the plumbing, not the model |
| `openai_compatible.py` | The `openai-compatible` backend: any server speaking the OpenAI chat-completions wire format (OpenAI, Ollama, vLLM, an internal gateway) via stdlib `urllib`, key from the environment. An unreachable endpoint (refused, no route, unknown host) raises `ModelUnavailable`; an HTTP error from a reachable one propagates as the failure it is | The Claude Code CLI — that is `claude_code_headless.py`; holding a key — the environment does |
| `registry.py` | `get_model(name=None)` / `list_models()`: the name → adapter map and the default (`claude-code-headless`); an unknown name is a `KeyError` naming the options | Implementing a backend — write an adapter and register it here; agents import the name, never a concrete class |

`ModelUnavailable` is the **absent-versus-broken** split for models (ADR-0007's
rule, applied here): the doers that call a model — `scripts/hooks/on_stop_triage.py`,
`scripts/refactor_practice.py` — catch it, print `model unavailable (...); skipping`
and exit 0, because a hook that fires on a machine without a model must not
fail the event it was attached to. A model that runs and fails still raises:
that is a defect, and it stays loud.

`agents/` depend on this dir: an agent asks the registry for a
backend by name and calls `.run(prompt)`. To add a provider (an
Anthropic API client, a local model), drop in an adapter that
implements `ModelBackend` and register it — no agent code changes.
