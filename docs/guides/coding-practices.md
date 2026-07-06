---
title: Coding practices (what Keel enforces, advises, and documents)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [practices, gate, advisory, ruff, mypy, types, llm, cuda, langgraph, guide]
summary: The catalogue of good-Python practices Keel promotes for general and LLM/CUDA/LangGraph code — each sorted onto the gate/advisory/doc line, sourced from config/practices.json.
id: docs-guides-coding-practices
created: 2026-07-06
updated: 2026-07-06
visibility: internal
canonical: true
---

# Coding practices

Keel already keeps a project **structurally** honest (labeling, package
boundaries, the corpus — see [deterministic-checks](deterministic-checks.md)).
This guide covers the other axis: the **code-level** practices that keep
Python — and especially LLM / CUDA / LangGraph code — legible and safe, and
exactly *how far* Keel goes to enforce each one.

The single source of truth is **`config/practices.json`** — a vendor-neutral
data registry read by path (never imported) by the gate, the advisory, and the
refactor agent alike. This document is its human-readable face.

## The one rule that sorts every practice

A practice lands in one of three tiers by a single test — **can a rule decide
it deterministically, with no model and no network?**

| Tier | Where it runs | Fails the build? | Boundary |
|------|---------------|------------------|----------|
| **gate** | `make verify` (ruff / mypy / `check_structure.py`) | **yes** | provable from the source text alone |
| **advisory** | `make advise` (`check_practices.py`) | never (exits 0) | a *smell* — real judgment, over/under-flags |
| **doc** | this guide + review | no | a convention a static check can't certify |

This is the same line CONVENTIONS §18 draws: *"a static check cannot prove code
is generic — genericity is a property of the input space, not the source text."*
Anything needing "should this be injected / is this really hot-path / does this
shape make sense" is an **advisory or a doc**, never a gate — a gate that
blocks a commit on a heuristic would reject correct code.

## Universal vs domain

Most practices are **universal** — they apply to any Python and ship on by
default. A handful are **domain-specific** (tensors, CUDA, LangGraph state);
those ship *defined but off*, behind a profile in `config/practices.json`. A
consuming repo turns one on with `project.json` → `practices.profiles`
(e.g. `{"cuda": true}`); until then the domain checks never fire, so the core
template stays domain-neutral. A profile's `tags` scope its checks to corpus
nodes carrying those tags — the knowledge graph tells the checker *where* a
domain rule is even relevant.

## The catalogue

### Gates — enforced now, config-first (Slice 0)

These ride the existing `make lint` / `make typecheck` into `make verify` with
near-zero custom code — Keel shipped ruff/mypy essentially unconfigured, so
populating `select` + a few strict flags was the highest-leverage first move:

| Practice | Mechanism |
|----------|-----------|
| Declare element types on `dict/list/set` | mypy `disallow_any_generics` |
| No implicit `Optional`; no `Optional`-as-silent-failure | mypy `no_implicit_optional`, `strict_optional`; ruff `RET` |
| Don't return `Any` from a typed function | mypy `warn_return_any` |
| Preserve the cause; never blind-except | ruff `B904`, `BLE001` |
| An ABC declares an `@abstractmethod` | ruff `B024` + mypy |
| No `print()` in library code; no interpolation inside log calls | ruff `T20`, `G`, `LOG` |
| Public API via `__init__`/`__all__`; no cross-package `_private` import | `check_structure.py` `check_C/D/E` + ruff `I` |
| `assert_never` in the default branch of `Literal`/`Enum` routing | mypy Never-narrowing (convention) |

Deliberately **deferred** (measured as high-churn or style-fighting): `UP`
(house style is `%`-formatting), `RUF022` (semantic `__all__` order), `RUF100`
(intentional `# noqa` codes), `E501` (long docstring summaries). They belong in
a later *widen* slice, fixed chunk-by-chunk.

### Gates — custom AST checks (later slices)

No off-the-shelf rule understands these, so they become small checks inside the
existing `check_structure.py`, keyed on **declared intent** (a marker), never a
name suffix — `*Config` name-matching would be exactly the fit-to-specimen smell
§18 warns against:

| Practice | Check | Note |
|----------|-------|------|
| Don't leak a third-party exception across a public boundary | `check_J` | owned-error set from a declared base marker |
| A declared config/settings class is frozen | `check_K` | keyed on `practice: frozen-config` marker |
| Tensor params carry a shape, not a bare `Tensor` | `check_L` | **domain** (cuda profile); `warn()`, not `err()` — it over/under-flags |

### Advisories — smells, never block (`make advise`)

Real judgment calls. `check_practices.py` reports them and always exits 0; each
finding can be waived with `# practice-ok: <reason>`:

| Practice | Smell |
|----------|-------|
| Inject collaborators; don't construct a backend inline | a provider constructor (`tokens.provider_constructors`) built in a doer, not passed in |
| Prefer `singledispatch` to a long `isinstance` chain | ≥3 `isinstance` branches on one subject |
| Give a hot-path class `__slots__` | a `# hot-path`-marked class without slots |
| Wrap acquire-prone resources in a context manager | a CUDA/session/file acquire (`tokens.acquire_apis`) bound outside a `with` — **domain** (cuda profile) |

### Docs — conventions to follow

Shape/dtype/device-aware hints (`jaxtyping` or a `TypeAlias` + inline `# (B, T, H)`
comment); `Protocol` for structurally typing third-party shapes you don't own;
`TypedDict`/Pydantic for LangGraph state; frozen config vs mutable state kept
visibly separate. These are judgment; the reviewer (or the refactor agent)
applies them.

## Applying them to an existing codebase

The companion to enforcement is `agents/practice_refactor/` (and its
`practice-refactor` skill): a doer that walks the corpus knowledge graph one
bounded neighbourhood at a time, refactors each chunk toward a *named* practice
from this catalogue, and gates every step on the same `make verify` — so it
cannot mark a chunk done unless it satisfies the very rule the gate encodes.
See [dev-loops](dev-loops.md) for the convergence discipline it follows.

## Extending the catalogue

Add or retrank a practice by editing `config/practices.json` (a data change),
then wiring its mechanism: a ruff/mypy flag in `pyproject.toml`, a `check_*`
in `check_structure.py`, or a smell in `check_practices.py`. Enabling a domain
profile is a one-line flag in `config/project.json`.
