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
updated: 2026-07-07
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
| Every function is fully typed (no untyped defs / calls / decorators) | mypy `strict` (Slice 5) |
| No blanket `# noqa` / `# type: ignore` — each names its code | ruff `PGH` (Slice 5) |
| One machine-decided layout (no hand-formatting in review) | `ruff format --check` via `make fmt-check` |
| Machine-readable module header (`title:`/`summary:`) + exported-symbol docstrings | `check_O` + `check_E` (ADR-0008); the local corpus gated fresh via `check_corpus` |

The **Slice-5 widen pass** measured every candidate rule first (Slice 0's
discipline). It took mypy to full **`strict`** (the backlog was 3 `no-untyped-def`
sites, now fixed) and added the ruff families that were measured at **zero**
current violations — `A`, `FA`, `FURB`, `ICN`, `ISC`, `PERF`, `PGH`, `PIE`,
`RSE`, `SLOT`, `NPY` — so enabling them is pure future-protection with no churn
(several pair with a keel practice: `PGH` ↔ the suppression discipline, `SLOT` ↔
slots-hot-path, `NPY` ↔ the tensor domain).

**Formatting is a gate, not a review topic.** `make fmt` had existed all along,
but nothing required it to have been *run* — so the tree drifted to 109
unformatted files while `make verify` stayed green. `make lint` now also runs
`make fmt-check` (`ruff format --check`) over the same `CODE_ROOTS`, read-only:
a check that repairs its own subject reports success instead of drift. The
formatter is left at its **defaults** deliberately — the value of this tier is
that no one re-litigates layout, and a tuned formatter reopens exactly that
argument. It reflows *code* only, so the `E501` deferral below still holds.

One thing to know if you suppress a rule: `ruff format` can move a `# noqa` off
the line whose diagnostic it silenced (it did, in `check_practices.py`). Anchor
a pragma to the line ruff *reports*, and re-run `make lint` after reformatting —
`RUF100` is deferred here, so an orphaned pragma is not flagged on its own.

Kept **off as deliberate house-style policy** (not deferred debt): `UP`
(house style is `%`-formatting), `RUF022` (semantic `__all__` order), `RUF100`
(intentional `# noqa` codes), `E501` (long docstring summaries). `check_M` errs
if any is silently *selected* in `pyproject.toml`.

### Gates — custom AST checks

No off-the-shelf rule understands these, so they are small checks inside the
existing `check_structure.py`, keyed on **declared intent** (a marker) or on
**registry data** (a token set), never a name suffix — `*Config` name-matching
would be exactly the fit-to-specimen smell §18 warns against:

| Practice | Check | Note |
|----------|-------|------|
| Don't leak a third-party exception across a public boundary | `check_J` | raises a foreign-imported exception type; builtins/stdlib/owned pass |
| A declared config/settings class is frozen | `check_K` | keyed on the `# practice: frozen-config` marker; resolves aliased frozen dataclass / `NamedTuple` / attrs-frozen; **err** |
| Tensor params carry a shape, not a bare `Tensor` | `check_L` | **domain** (cuda profile), over `tokens.tensor_base_types`; `warn()`, never `err()` — it over/under-flags |

`check_K` is **inverted** relative to `check_J`: `check_J` errs only when it
*proves* a leak, so a recognizer gap is a safe miss; `check_K` errs when a
*marked* class is **not proven** immutable, so recognition is deliberately broad
(alias-resolving) and any residual construct it can't prove — a frozen base
class, a functional `namedtuple()` — is a documented `# practice-ok` waiver, not
a silent false error.

### Ruleset parity — the config can't silently drift (`check_M`)

The gate rulesets above live **twice**: as behaviour in `pyproject.toml` (what
ruff/mypy actually enforce) and as DATA in `config/practices.json` `rulesets`
(what the template *declares* it enforces). `check_M` proves the two agree —
every declared ruff `extend_select` family is selected, every declared mypy flag
is enforced, and no `deferred` (policy-off) family is silently selected. So a
future edit that drops `strict` or removes a family from `pyproject.toml` fails
the build instead of quietly weakening the policy. It reads `pyproject.toml` as
text (no `tomllib` on the 3.6 pre-commit interpreter), understands multi-line
arrays, dotted-key and header table forms, and honours `# practice-ok`.

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

Enforcement keeps *new* code honest; the companion `agents/practice_refactor/`
agent brings *existing* code toward one **named** practice from this catalogue.
It is an ordinary keel agent — a neutral `Plan` on a `Runtime`, model from
`models/`, tools invoked as CLIs — with four steps:

1. **walk** (read-only) — `query_corpus` retrieves one bounded neighbourhood of
   the corpus knowledge graph where the practice is relevant (its tags scope
   *where* the rule applies).
2. **baseline** (read-only) — `run_make_target` gates the tree green *before*
   touching anything; a red baseline stops the run (a dirty tree yields a dirty
   refactor).
3. **propose** (model-call) — draft ONE bounded edit for the chunk at the cursor.
4. **apply** (writes) — `apply_refactor` applies it atomically and **rolls it
   back** unless `make verify` stays green.

So the agent **cannot mark a chunk done unless it satisfies the very rule the
gate encodes** — the gate, not the model's judgment, is the definition of done
(CONVENTIONS §17). It **defaults to dry-run** (walk + read-only baseline, propose
and write nothing) and the per-chunk loop is **durable** (one chunk per step, so
a crash mid-refactor resumes at the cursor without re-applying accepted chunks).

Its mechanical hands are two vendor-neutral `scripts/` doers (no model, no
provider): **`run_make_target.py`** runs a make target and reports a structured
pass/fail (the *gate*), and **`apply_refactor.py`** applies one bounded edit
*atomically* and **rolls it back** unless the gate stays green (the *safety
net*) — each declared as a tool in `agents/tools/`. The agent supplies the
judgment (which chunk, which practice, what edit); the doers keep the tree green
at every step. See [dev-loops](dev-loops.md) for the convergence discipline.

Run it through the thin CLI entrypoint (the vendor-agnostic doer) or its
vendor-specific trigger, the `practice-refactor` skill:

```
python3 scripts/refactor_practice.py <practice-id> --json            # dry-run preview
python3 scripts/refactor_practice.py <practice-id> --execute --json  # apply, gated
```

## Extending the catalogue

Add or retrank a practice by editing `config/practices.json` (a data change),
then wiring its mechanism: a ruff/mypy flag in `pyproject.toml`, a `check_*`
in `check_structure.py`, or a smell in `check_practices.py`. Enabling a domain
profile is a one-line flag in `config/project.json`.
