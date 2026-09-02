---
title: Python style (how code is written here)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [practices, style, readability, robustness, docstrings, comments, agents, guide]
summary: The canonical statement of how Python is written in this project — readability and loud failure modes outrank speed; the machine-readable module header; comment and docstring discipline; and how a code agent works here. The provable floor is gated (check_O/E, ruff, mypy); this guide is the judgment above it.
id: docs-guides-python-style
created: 2026-08-18
updated: 2026-09-02
visibility: internal
canonical: true
---

# Python style — how code is written here

This project is built to be **read more often than written, and by more agents
than authors** — including readers who are not software engineers by trade. The
same rules serve both audiences: what makes code legible to a hardware engineer
reviewing it also makes it legible to an LLM interpreting it, because both read
the names, the docstrings, and the comments before they read the control flow.

This guide is the **judgment half** of the practices registry
(`config/practices.json`; catalogue in [coding-practices](coding-practices.md)).
Everything a rule can decide is already a gate — formatting, typing, the module
header, exception hygiene. What follows is the part a gate cannot prove, stated
plainly enough that a reviewer can point at a section and an agent can follow
it as an instruction.

## 0. The priority order

1. **Readable.** Someone who did not write this — human or agent — can say what
   it does and why it exists from the file alone.
2. **Robust.** Every failure mode is either handled or *loudly* propagated.
   Silence is the only forbidden outcome.
3. **Fast enough.** Speed matters only when measured to matter. Never trade 1
   or 2 for it without a measurement in a comment justifying the trade.

When two rules collide, the lower number wins. A clever one-liner that needs a
comment to decode loses to three plain lines that don't. An optimization that
obscures a failure path is a defect even when it works.

## 1. The module header (gated — `check_O`)

Every `.py` file begins with a docstring carrying explicit `title:` and
`summary:` lines:

```python
"""
title: Pinmux checklist — verify pad-ring assignments against the spec
summary: Reads the pad CSV and the pinmux spec, reports every mismatch with its spec row, and exits non-zero if any pad is unassigned or double-driven.
"""
```

**The whole summary lives on its one line.** The grammar is line-based: a
wrapped continuation line is silently dropped from what the corpus stores, so
a wrapped summary reads fine to a human and truncates mid-sentence for every
agent. Let the line run long — `E501` is deferred here for exactly these
header lines.

This is not paperwork. The corpus — the knowledge graph every agent queries —
is built **from these lines**. A module without them is either invisible to
agents or filed under its filename with an accidental first sentence as its
meaning. The gate (`check_O`) makes that impossible; your part is making the
two lines *true*:

- `title:` names the capability, not the file (`Pinmux checklist`, not
  `pinmux_check.py`).
- `summary:` says what it does **and** what happens on failure, in one or two
  sentences. If you cannot summarize the module in two sentences, the module
  is doing too much — split it.

## 2. Docstrings say WHAT; comments say WHY

**Docstrings**: every name in `__all__` has one. The gate (`check_E`) proves
this for symbols *defined in the exporting module*; a re-exported name is held
to the same rule at its definition site by convention — the gate does not yet
follow it there. The first line is the summary an agent retrieves, so make
it a sentence about behavior, not a restatement of the signature:

```python
def resolve_tool_version(name: str) -> str:
    """Return the gate-verified version for *name*, or raise UnknownTool.

    'Gate-verified' means the version listed in config/tools.json, which CI
    proves installable — never whatever happens to be on PATH.
    """
```

**Comments** carry what the code cannot: the *reason*, the *measurement*, the
*rejected alternative*, the *defect this line prevents*. This repo's house
style is deliberately comment-heavy — but every comment must earn its line:

- A comment that restates the code is noise. Delete it.
- A comment that carries a decision is documentation. `# Read the file's
  presence, not ImportError: a broken module must fail loudly, not degrade
  into fewer routes` tells the next reader (or agent) which change would be a
  regression.
- When a value or threshold is chosen from evidence, cite the evidence:
  `# 8 links max — measured: beyond 8, every extra edge was noise (2026-08).`

The test: could a reviewer who distrusts the code check it against the
comments? If the comments only repeat the code, there is nothing to check
against.

## 3. Failure modes: silence is the defect

The recurring bug class this project hardens against is **silent green** — a
thing that fails without saying so, or never runs while reporting success.
Every rule here exists because one of those was found and measured:

- **Never blanket-except.** `except Exception: return 0` converts every future
  bug into a passing check. Catch the exceptions you can *name*, and let the
  rest crash — a traceback is loud, and loud is correct. (Gated: ruff `BLE001`;
  chain with `raise ... from` — `B904`.)
- **Distinguish *absent* from *broken*.** "The optional thing is not installed"
  and "the thing is installed but failing" must take different paths: absent →
  say so and continue (exit 0, with a message naming how to get it); broken →
  fail. Collapsing the two is how a broken install reads as a clean skip.
- **A check that writes is not a check.** Verifiers report; they never repair
  their own subject. A gate that regenerates the artifact it validates will
  always pass.
- **Fail at the boundary you own.** Validate inputs where they enter (the CLI
  arg, the config load, the API edge) with a message that names the fix — not
  three calls deeper where the traceback names an implementation detail.
- **Exit codes are the contract for scripts.** `0` = clean, non-zero = act.
  Print *what to do*, not just what is wrong: `regenerate with make site-data`
  beats `stale`.

For a script wrapping an external tool (an EDA flow, a license query, a farm
submission), assume the tool **will** misbehave: check the return code, check
that the output file exists *and is non-empty*, and echo the command on
failure so the reader can rerun it by hand.

## 4. Plain over clever

- **Small, flat functions.** Prefer early returns to nesting; prefer a second
  function to a second responsibility. (Judgment, deliberately unmeasured — a
  length gate would reject correct code; the reviewer's question is "can I
  hold this whole function in my head?")
- **stdlib first.** Every dependency is a thing the next machine must have.
  A one-off script that needs only `json`, `csv`, `pathlib`, and `argparse`
  should import exactly those.
- **Explicit over implicit.** No magic globals, no behavior toggled by
  invisible state; wire dependencies in at the call site so a reader can trace
  where anything comes from.
- **Names carry the domain.** `unassigned_pads`, not `res2`; the reader may
  know pad rings far better than Python — meet them in their vocabulary.
- **Library code logs; entrypoints print.** `print()` is banned outside
  process entrypoints (ruff `T20`; the carve-outs are declared per file). The
  substitute is stdlib `logging` — and the gate has opinions there too: no
  f-string/`%`/`+` interpolation *inside* the call (ruff `G`/`LOG`). Pass lazy
  arguments instead:

  ```python
  logger = logging.getLogger(__name__)
  logger.info("resolved %s to %s", name, version)   # yes
  logger.info(f"resolved {name} to {version}")      # fails the gate (G004)
  ```
- **Types are documentation that cannot rot.** mypy runs `strict` over the
  ratcheted scope (gated): `src/` fully, leaf roots under declared, costed
  relaxations listed in `config/practices.json` `rulesets.mypy` — every one
  with its exit condition. Annotate as you write, not after; a precise
  signature is the cheapest docstring there is.

## 5. How a code agent works here

The process rules live in the root `AGENT.md`; these are the code-level habits
that go with them, for any agent (or person) writing Python in this repo:

1. **Read the neighborhood first.** Match the idioms of the file you are in —
   comment density, naming, error style. New code that reads like the
   surrounding code is reviewable; a style island is not.
2. **Test first, gate decides.** Drive changed behavior from its mirror test;
   done means `make verify` exits green, never self-assessment.
3. **Solve the class, not the example.** If the fix only makes the named case
   pass, it is a patch. Name the general rule first (CONVENTIONS §18).
4. **When you find a defect by reading, add the gate that finds it by
   scanning.** Reading found 2 branding hardcodes here; the scan found 8.
5. **Write the why down at the decision site.** An agent session ends; the
   comment is what the next session — or the next engineer — inherits.

## 6. The same contract at every size

| Scale | What holds | What relaxes |
|---|---|---|
| One-off EDA script / checklist | header (python-style.md §1), failure modes (python-style.md §3), stdlib-first | no package structure, no mirror test required outside `src/` |
| Agent + tooling around it | all of the above + `__all__` boundary + tool spec (`agents/tools/`) | — |
| Full product (`src/`) | everything: mirror tests, e2e for user-facing flows, strict types | nothing |

The header and the failure-mode discipline never relax, because they are what
keep the *smallest* scripts findable and trustworthy years later — the one-off
that quietly becomes load-bearing is precisely the file nobody re-reads.

## 7. What is enforced, advised, and judged

| Concern | Tier | Where |
|---|---|---|
| Formatting, import order | gate | `ruff format --check`, `ruff I` |
| Module header, symbol docstrings | gate | `check_O`, `check_E` |
| Types — `strict` over the ratcheted scope | gate | mypy (`rulesets.mypy` declares every relaxation) |
| Exception hygiene (no blind except, chaining) | gate | ruff `BLE`, `B904` |
| No `print()` in library code | gate | ruff `T20` |
| Inline-constructed backends (DI), `isinstance` chains, hot-path `__slots__`, resources outside `with` | advisory | `make advise` |
| Function size, complexity, naming | judgment | this guide + review |
| Comment quality, absent-vs-broken splits | judgment | this guide + review |

The line between the tiers is principled (see
[coding-practices](coding-practices.md)): *can a rule decide it
deterministically?* Yes → gate. It's a smell → advisory. It needs judgment →
this guide, and a reviewer pointing at the section that was not followed.
