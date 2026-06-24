---
title: Solving the general case (don't fit the eval)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [generic, overfitting, evals, golden-set, hardcoding, advisory, agents, guide]
summary: How to solve the general problem an eval/golden set exemplifies instead of overfitting to it — the discipline, plus the advisory check that backstops it.
id: docs-guides-generic-solution
created: 2026-06-24
updated: 2026-06-24
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
