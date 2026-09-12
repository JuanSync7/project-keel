---
title: Idempotency
kind: doc
layer: n/a
status: template
owner: TBD
tags: [idempotency, writers, fixed-point, determinism, guide]
summary: How a doer that writes into the tree is built so that running it twice changes nothing the first run did not, and how that is declared and proven here — the `effect:` / `rerun:` / `rerun_proof:` header check_V gates, the recipe for reaching a fixed point, the ladder of proofs, and the honest declarations for the writers that cannot reach one. The code twin of doc-style.md §6, which governs how the claim is written down rather than how it is made true.
id: docs-guides-idempotency
created: 2026-09-12
updated: 2026-09-12
visibility: internal
canonical: true
---

# Idempotency — how a writer behaves the second time

Every doer in this repository could already be run twice safely. Nothing held
it there. Generation, the corpus, the two schemas and the static snapshot were
each measured running twice and landing byte-identical — and the property was a
habit, not a rule, which is exactly what a generated project cannot inherit.
This guide is the rule, and `scripts/check_structure.py` `check_V` is its floor.

`scripts/AGENT.md` has always said a script must be "safe to run twice". This
says what that means, how to get it, and how you show it.

## 1. Three properties, and the one `rerun:` names

`doc-style.md` §6 separates three things the word "idempotent" is used for.
That guide governs how the claim is written in prose; this one governs the code.

- **Generator fixed point** — running the doer twice yields byte-identical
  output. This is what `rerun:` declares and what `check_V` gates.
- **Stated repeat-safety** — a document says the command may be re-run.
  Presence is checkable; truth is the author's.
- **Procedure idempotency** — a multi-step procedure lands the same state from
  any starting point. Judgment only; section 6 below is what can be said about it.

Write the property, never the bare adjective. "Recomputes every keyword edge
from scratch and keeps the authored ones" says what "idempotent" only gestures at.

## 2. The declaration (gated — `check_V`)

A module that writes to the filesystem declares three things in the module
docstring, beside `title:` and `summary:`, in the same header grammar
`build_corpus` reads:

```python
"""
title: Build corpus job
summary: Deterministic: walk the repo into wiki/corpus.json (the one-brain index).
effect: writes
rerun: fixed-point
rerun_proof: make:check-corpus
"""
```

`effect:` is the CONVENTIONS §10 `tool_effect` vocabulary, reused rather than
re-invented, so the word means the same thing in a tool spec and in a module:

| `effect:` | Means | Not for |
|-----------|-------|---------|
| `read-only` | reads the tree and writes nothing | a module that writes anywhere, including a cache or a temp file it leaves behind |
| `writes` | mutates the filesystem | declaring an in-memory mutation; `effect:` is about the world outside the process |
| `model-call` | reaches a model | a deterministic doer, even one that reads a prompt file |

`rerun:` says what a **second** run does. Three values, and the split that
matters is between the claim and the two admissions:

| `rerun:` | Means | Needs a proof? |
|----------|-------|----------------|
| `fixed-point` | a second run leaves the tree byte-identical | **yes** — name it in `rerun_proof:` |
| `append-only` | each run adds to what is there; re-running duplicates | no |
| `unsafe` | re-running is not safe; the caller must guard | no |

Only `fixed-point` needs evidence, because only `fixed-point` claims anything.
Demanding a proof of the other two would push an honest author toward the
flattering word, which is the opposite of what this is for.

`rerun_proof:` names the mechanism in the closed grammar check_T already holds
`enforced_by` to — `check:<LETTER>`, `script:<path>`, `test:<path>`,
`make:<target>`, `doc:<path>`. One grammar for "name the thing that proves
this", wherever the claim is made.

**What the gate proves and what it does not.** `check_V` proves the declaration
exists, its values are in the closed sets, and its proof resolves. It does not
read the proof. The detector is exact — it resolves the base of every call, so
`text.replace(...)` is not `os.replace(...)` — but it is exact by
under-reporting: a write behind `subprocess`, or through an aliased import, is
invisible to it. A module that declares `effect: writes` with no write the check
can see gets a WARN that reads *unverified*, never a silent pass and never an
error, because the honest declaration must not be the one that fails the build.

## 3. Building a writer that reaches a fixed point

Six rules, in the order they usually go wrong:

1. **Derive, never accumulate.** Compute the whole output from the inputs and
   write it. `build_corpus` walks the tree and emits the corpus; it never opens
   the previous corpus and adds to it. A writer that reads its own last output is
   one bug away from `append-only`.
2. **Write whole files.** Open `"w"`, not `"a"`. An append is the single most
   common way a doer stops being a fixed point, and the only way it does so
   silently — the file just grows.
3. **Sort every iteration that reaches the output.** A `set`, a `dict` built
   from a set, and `os.walk`'s directory order are all unordered enough to
   differ between runs or between machines. `build_corpus` sorts `dirnames` in
   place during the walk for exactly this reason.
4. **Serialize canonically.** JSON goes out as
   `json.dumps(obj, indent=2, sort_keys=True) + "\n"` — the form
   `check_corpus._dumps` pins, so a re-serialized corpus compares equal.
5. **Keep the clock, the hostname and absolute paths out of the output.** A
   timestamp in a generated artifact makes byte-identity impossible by
   construction. Where a date genuinely belongs in the output, take it as a flag
   with a default (`review_docs.py --today`) so a test can pin it.
6. **Replace atomically where a partial file would be read.** Write a temporary
   file and `os.replace` it, as `runtimes/_checkpoint.py` does; `os.replace` is
   atomic on POSIX, so a reader sees the old bytes or the new ones and never
   half of each.

## 4. The ladder of proofs

Pick the cheapest rung that actually proves the claim:

1. **A `--check` mode and a `make` target**, when the output is a committed
   artifact. `make check-openapi` and `make check-aad` re-render and compare
   against what is committed, which is the fixed point stated over the
   repository's own state. This is the strongest rung because CI runs it on
   every push.
2. **A double-build comparison**, when the output is derived and gitignored.
   `make check-corpus` builds the corpus twice and compares the two.
3. **A case in `tests/integration/test_idempotence.py`**, for everything else.
   It runs the doer, snapshots its output, runs it again and asserts nothing
   changed.

That file derives its worklist from the headers: every module naming it as
`rerun_proof:` must have a case, marked `@covers <path>` in the case's
docstring, and a module that names it with no case fails the suite. A proof that
silently covers nothing is the defect the declaration exists to prevent, so the
proof is not allowed to be one.

## 5. Declaring the writers that cannot reach a fixed point

`append-only` and `unsafe` are legitimate. State the property and say what the
caller must do:

- A log or an audit trail is `append-only`. Say what bounds it.
- A doer that consumes its input (moves a file out of an inbox) is `unsafe` on a
  partial run. Say where the resume point is.

There is a fourth shape worth naming because it looks like a failure and is not:
a doer whose second run **refuses**. `scripts/apply_refactor.py` applies a
proposal by unique search/replace, so once the edit lands the anchor is gone and
a second identical apply raises before writing anything. The tree is unchanged,
so the declaration is `fixed-point` — re-running is safe because the refusal is
loud, not because the edit is repeatable. A doer that instead found *some other*
occurrence and edited it would be the real failure, and it would be silent.

## 6. Procedure idempotency, and what a generated project inherits

The rungs above are about one command. Two procedures here are idempotent as a
whole, and neither is something a rule can decide, so both are held by tests
named after the property:

- **Generation.** `copier copy` with the same answers into two destinations
  produces byte-identical trees, and re-running it over an existing generated
  project reports every file `identical` and writes nothing.
- **Update.** `copier update --trust` against the template revision a project is
  already on leaves the working tree clean. The `_migrations` are `rm -rf` and
  `rm -f` commands, which are no-ops on an absent path by construction — a
  migration that was not is the thing to catch in review.

A project generated from this template inherits all of it without doing
anything: `scripts/check_structure.py` ships verbatim, so `check_V` runs in its
`make check` from the first commit; `tests/integration/test_idempotence.py`
ships, so its own writers are re-run by its own suite; and this guide ships, so
the agent working in it is told the rule before it writes the tenth doer.

## 7. What is enforced, what is advised, what is judged

| Claim | Held by | Tier |
|-------|---------|------|
| A module that writes declares `effect: writes` | `check_V` | gate |
| `effect:` / `rerun:` are in the closed vocabularies | `check_V` | gate |
| A `rerun: fixed-point` claim names a proof that resolves | `check_V` | gate |
| Every module naming `test_idempotence.py` as its proof is actually re-run there | `tests/integration/test_idempotence.py` | gate |
| The declared fixed points really are fixed points | `make check-corpus`, `make check-openapi`, `make check-aad`, `tests/integration/test_idempotence.py` | gate |
| Generating twice, and re-generating over a project, changes nothing | `tests/integration/test_copier_generation.py` | gate |
| Updating a project already on the template revision changes nothing | `tests/integration/test_copier_update.py` | gate |
| A write reached through `subprocess` is declared | — | judged (the detector cannot see it; `check_V` says *unverified*) |
| `append-only` or `unsafe` is the honest value, not a dodge | — | judged |
| A procedure lands the same state from any starting point | — | judged |
