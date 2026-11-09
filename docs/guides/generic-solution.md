---
title: Solving the general case (don't fit the eval)
kind: doc
form: explanation
layer: n/a
status: template
owner: TBD
tags: [generic, overfitting, evals, golden-set, hardcoding, advisory, agents, guide]
summary: How to solve the class behind an eval, golden set or bug report, with tests, review and an advisory answer-key scan.
id: docs-guides-generic-solution
created: 2026-06-24
updated: 2026-11-09
visibility: internal
canonical: true
---

# Solving the general case

Hand an LLM (or a tired human) an eval, a golden file, or one failing test and the
tempting move is to make *that case* pass — hardcode its expected answer,
special-case its specimen value, paste its datum into the code. The case goes
green; the code learned nothing. This repo is a **template**: everything built
from it should solve the **broader problem the example only points at**, not the
example itself.

The imperative form of this rule lives in the root [`AGENT.md`](../../AGENT.md) and
[`CONVENTIONS.md`](../../CONVENTIONS.md) §18; this is the playbook with worked
examples. It is the discipline **sibling** of the development loops
([dev-loops.md](dev-loops.md); §17): there a test is the pressure that keeps you
honest — here the rule is the thing the test only *samples*. The two pull in the
same direction: write a test, then satisfy the **rule it demonstrates**, not the
single row in front of you.

## The discipline is the judge

There is no gate that can prove code is "generic" — genericity is a property of
the whole input space, not of the source text. So the real pressure is
**behavioral**, not a checkmark:

- **behavior-asserting tests** that sample more than one case (edge, empty,
  boundary), so a hardcoded answer can't satisfy them — see
  [`tests/AGENT.md`](../../tests/AGENT.md);
- **review** that asks "would a sibling input of the same class still work?";
- an **advisory backstop**, `make advise`, that points at the one smell a static
  scan *can* catch (below).

`make advise` never fails the build. Treat its output as a question to answer, and
the rules below as the actual standard.

## The eval is a sample, not the spec

A golden set illustrates the behavior; it does not define it. Read a row as "the
rule must also produce this", never as "the rule *is* this row".

```python
# A spec ships one eval row: parse("AXI4") -> "INCR".
# DON'T — fit the row:
def burst_kind(proto):
    if proto == "AXI4":
        return "INCR"          # passes the eval, knows nothing about the next protocol

# DO — implement the rule the row demonstrates:
def burst_kind(proto):
    return _parse_protocol(proto).default_burst   # the row is now one consequence of the rule
```

Generalize from the example to the property it demonstrates, then satisfy the
property — and add a test that samples a *second* member of the class.

## Name the general rule before you special-case

Before you write `if x == "<specimen>"`, say out loud the rule the specimen is an
instance of, and implement *that*. A special-case branch is justified only when
the general rule genuinely has a discontinuity there — and then it is documented
as a real edge, not as a way to turn one test green.

An **enum-style dispatch over a fixed, documented set of kinds** *is* a general
rule (it enumerates the whole space on purpose). A **lone branch that exists only
to pass one case** is not — that is the smell.

## Derive, don't hardcode (the answer-key trap)

Compute outputs from inputs. A literal lifted verbatim from a test's expected
value and embedded in `src/` logic is an **answer key**: it makes the sample pass
while teaching the code nothing — and it is exactly what `make advise` flags.

```python
# tests/unit/backend/test_wiki.py
assert resolve(doc) == "docs-guides-agent-surface"   # the golden

# src/backend/wiki/_resolve.py
# DON'T — the answer key, copied into logic:
def resolve(doc):
    return "docs-guides-agent-surface"               # <-- make advise will flag this
# DO — derive it:
def resolve(doc):
    return slugify(doc.path)                          # the golden falls out of the rule
```

If the value genuinely *is* content — a slug, a catalogue row, a curated title —
it is **data**, and data belongs in a declared registry (`*_data.py`, a fixture, a
`kind: config` module per §8), which `make advise` deliberately ignores. Logic
*reads* data; it does not *memorize* it. When a literal in logic is meaningful,
either promote it to an `ALL_CAPS` named constant (naming it *is* the general
move) or, if it is a deliberate fixed token, annotate it so the next reader knows
it was a choice:

```python
TIMEOUT_SECONDS = 30                  # named: clearly a knob, not an answer key
sep = "—"  # generic-ok: U+2014 em-dash is the intended literal, not a fixture value
```

## When a golden fails, fix the generator — not the golden

A committed golden drifted from the output. Ask **which is right** before you
touch anything:

- the **golden is correct** → fix the producing logic until it earns that output;
- the **behavior legitimately changed** → regenerate the golden and say *why* in
  the commit message.

Never hand-tweak the code so it emits exactly the stored bytes for that one
input. That is overfitting wearing the costume of a bug fix.

## A patch is not a fix

If a change only makes the named failing case pass — and a slightly different
input of the *same class* would still fail — you patched the symptom, not the
cause. The fix is the **smallest change that makes the whole class pass**, carried
by a test (§17) that samples more than the original case. "It's green" is
necessary, not sufficient.

## From a bug report to a class fix

A reported bug is evidence of a failing mechanism.
Use the following path to turn the report into a fix for every input that
reaches that cause.
Review alone holds this procedure.
No structural gate requires these steps.
The tests selected for a fix enforce only the cases their assertions cover.

1. **Reproduce.** Record the triggering input, the command and the observed
   failure in the fix brief.
   Add a regression test that fails on the reported behavior before changing
   the implementation.
   Check that the failure comes from the bug rather than a missing dependency.
   The regression test's assertions enforce the reproduced behavior.
   Review alone checks that it reproduces the report.
2. **Name the mechanism.** State how the input reaches the faulty operation.
   Name the responsible function and the invariant it violates.
   For the corpus-reader example below, the mechanism was formatting absolute
   checkout paths into diagnostics forwarded to an MCP client.
   Review alone checks the causal explanation.
3. **Widen to the class.** Search for the same operation in sibling callers,
   adapters, readers and writers.
   Record the search commands, paths searched, matches and relevant nonmatches
   in the fix brief.
   Define the class by reachability of the cause, rather than by resemblance
   to the reported input.
   For corpus diagnostics, inspect the error branches in
   `scripts/query_corpus.py` and `scripts/corpus_level.py`, then follow their
   messages through `agents/wiki_navigator/_brain.py`.
   Review alone checks the search's coverage.
4. **Fix the shared place.** Put the correction where the affected paths
   converge.
   Route each caller found by the search through that correction.
   For corpus diagnostics, `scripts/config_loader.py` `checkout_name` supplies
   the shared checkout-folder spelling.
   Allow a narrow fix only with a recorded reason that no other path reaches
   the cause.
   Review alone checks that boundary and the caller inventory.
5. **Prove the class.** Use table-driven or generated tests to vary the inputs
   that reach the mechanism.
   Assert the invariant through the public surface as well as the shared helper.
   Sweep the affected paths with planted faults: restore the faulty operation
   at the shared place and at callers that could bypass it.
   Record which test fails for each planting.
   A planting that stays green exposes a gap in the proof.
   Keep a "how else can this break?" list in the fix brief.
   For corpus diagnostics, include missing roots, selector conflicts,
   unreadable corpora, config refusals and paths repeated inside OS exceptions.
   `tests/unit/scripts/test_query_corpus.py` checks diagnostic branches.
   `tests/integration/test_mcp_servers.py` checks the errors exposed by
   `wiki_answer` and public `answer`.
   Review alone checks the breadth of the matrix and the planted-fault sweep.
6. **Repair the fallout.** Identify data the buggy writer already persisted.
   Supply a repair or regeneration procedure for affected data.
   State how to detect what needs repair and how to verify the result.
   Correct the documentation and the other affected places found by the search.
   If no stored data needs repair, record why the failing path writes none.
   Review alone checks that the repair inventory is complete.

### Repository evidence

The commit titled "fix(corpus): every corpus-reader refusal names the checkout,
never its host path" records an audit of the sibling diagnostic paths.
Its commit message identifies missing-checkout, selector, corpus-read,
config-read and informational messages beyond the reported served-level refusal.
The correction uses `scripts/config_loader.py` `checkout_name` across those
diagnostics.
`scripts/query_corpus.py` reports an `OSError` through `strerror` to avoid
repeating its filename.
The parametrized retrieval-refusal tests in
[`tests/integration/test_mcp_servers.py`](../../tests/integration/test_mcp_servers.py)
assert that client errors contain no scratch-root path.
Those tests also assert that retrieval refusals make no model call.
The commit message records failures after restoring the missing-checkout call
site and after making the shared helper return the absolute path.
These are recorded mutation results, rather than a mutation gate run by this
guide.
The query tool is a reader, so its diagnostic correction needs no stored-data
migration.
Its read-only contract is stated in `scripts/query_corpus.py`'s module header.
Review alone checks whether another affected component persisted the messages.

The preceding commit titled "fix(corpus): a refused served level names the
checkout, not its host path" corrected the reported served-level refusal.
Its mutation check exercised that refusal.
The later audit found other messages that still exposed host paths.
That earlier fix therefore left members of the diagnostic class uncovered.
A passing regression for the reported branch did not establish class coverage.

### The fix brief and the reviewer

Give a fix brief one evidence entry for each of the six steps.
Include the reproduction, causal invariant, recorded search, shared correction
or narrow-scope reason, test matrix and mutation results, breakage list, and
repair inventory.
For unfinished evidence, name the remaining work explicitly.
Review alone holds the brief to this format.

The reviewer traces each search match to a correction or a reason it cannot
reach the cause.
The reviewer checks that a sibling input and a bypassing caller are covered by
the proof.
The reviewer checks the data-repair instructions against the buggy writer.
Return the fix for more work when an applicable step lacks evidence.
Review alone holds these decisions.
A green test run proves only its assertions.
`make advise`'s answer-key scan does not enforce this procedure.

## What the advisor catches (and what it deliberately doesn't)

`make advise` runs [`scripts/check_generic.py`](../../scripts/check_generic.py): it
joins the **distinctive literals a test asserts as expected** (an `==` operand or
`assertEqual` argument) with the **literals hardcoded in non-data `src/` logic**,
and reports the intersection — the "answer key in source" smell. It is precision-
first on purpose: it ships into every generated project, and an advisor that cries
wolf trains people to ignore the whole check suite.

| | Caught | Deliberately not caught |
| --- | --- | --- |
| Answer key in source | yes — an equality-golden literal also hardcoded in non-data `src/`, distinctive (≥ 12 chars, not trivial) | — |
| Special-case branch (`if x == "specimen"`) | no — high false-positive rate; left to review | a smell to self-check, per §18 |
| Magic specimen literal | no — overlaps `ruff` magic-value rules | name it a constant / load it from `config/` |
| Membership assertion (`assert "## Heading" in txt`) | no — presentation strings; the join is equality-only | — |

Suppress a deliberate literal with a `# generic-ok: <reason>` trailing comment
(an empty reason is itself reported, so a suppression always carries its
justification). Data/registry modules (`*_data.py`, fixtures, `conftest.py`) and
any literal named as an `ALL_CAPS` constant are excluded wholesale. It matches
only literal, top-level or one-level-nested `==`/`assertEqual` operands — goldens
built by f-string or concatenation, nested deeper, or passed as keyword arguments
are not detected (acceptable false negatives for a precision-first advisor).

One honest false-positive class: an exact **error/message string** pinned by an
`==` assertion *and* raised verbatim in `src/` will flag. That is usually a real
nudge — assert the message with membership (`assert "positive integer" in str(e)`,
which the advisor ignores) or lift it to a named constant — but if the exact
wording is a deliberate contract, `# generic-ok: <reason>` says so.

> **Honesty caveat.** No static check can prove code is generic — genericity is a
> property of the input space, not of the source text. `check_generic.py`
> (`make advise`) flags exactly one smell — an answer-key literal that is both a
> test's expected value and hardcoded in non-data `src/` logic — and nothing more.
> It excludes data registries, `ALL_CAPS`-named constants, and trivial literals,
> honours `# generic-ok: <reason>`, and **always exits 0**. Read a clean run as "no obvious answer keys",
> never as "this is generic". The real gate is `make verify` plus tests that
> sample the whole class, and review.

## See also

- Root [`AGENT.md`](../../AGENT.md) and [`CONVENTIONS.md`](../../CONVENTIONS.md) §18 — the rules in imperative form.
- [dev-loops.md](dev-loops.md) — the sibling discipline (§17): test-first, bounded convergence, e2e coverage.
- [deterministic-checks.md](deterministic-checks.md) — the check catalogue; `make advise` is the `report`-gate advisor.
- [`tests/AGENT.md`](../../tests/AGENT.md) — assert behavior across a class, keep golden values out of `src/`.
