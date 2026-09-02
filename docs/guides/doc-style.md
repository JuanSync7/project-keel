---
title: Documentation style — how prose is written here
kind: doc
layer: n/a
status: template
owner: TBD
tags: [documentation, style, rosters, citations, freshness, guide]
summary: The canonical statement of how documentation is written in this repo — the judgment half above the gated floor. What a document is for, one claim per sentence, the discriminator between siblings (rosters and NOT lines), the citation grammar, freshness as a fact, the plain imperative over BCP 14, idempotency stated and proven, and what the gate checks versus what a reviewer must judge. The twin of python-style.md.
id: docs-guides-doc-style
created: 2026-09-02
updated: 2026-09-02
visibility: internal
canonical: true
---

# Documentation style — how prose is written here

This is the documentation twin of `python-style.md`: the judgment that sits
above the gated floor. `scripts/check_structure.py` proves what a rule can
prove about the docs — every link and `§N` resolves (`check_Q`), every roster
matches its directory (`check_S`), every tool spec has its seven sections and
its `- NOT` line (`check_F`), every `##`-annotated target is in `make help`
(`check_P`), the check catalogue tells the truth (`check_R`) — and
`scripts/jobs/review_docs.py` proves that `updated:` is not a lie. Everything else
on this page is what those checks cannot decide and a reviewer, human or
agent, holds you to. Where a rule below is gated, the gate is named; where
it is not, that is deliberate, and the reason is given.

## 0. The priority order

**Unambiguous, then complete, then short.** A reader should never have to
guess which of two things a sentence means, and never have to hold a
question open because the document declined to answer it. Length is the
price of the first two, paid willingly; a long document that answers every
question beats a short one that raises them. Cut words, never claims.

The reader is someone who knows the domain and has not read the rest of the
repository. Write so that the thought has already been done for them: the
decision, its reason, the alternative rejected, the thing to do next.

## 1. What a document is FOR

Every document has one job, declared in its frontmatter `kind:` and its first
paragraph, and it does not do a sibling's job:

| `kind` | Its job | Not its job |
|---|---|---|
| `readme` | orient: what is here, what each member is for, what it is *not* for | teach a procedure (a guide) or record a decision (an ADR) |
| `rules` (`AGENT.md`) | the imperatives an agent follows in this directory | explain why at length (link the rule that does) |
| `doc` / guide | the playbook for a rule stated elsewhere, with worked examples | be the rule's canonical statement (that is CONVENTIONS or an ADR) |
| `adr` | one decision, its context, its alternatives, at one moment — immutable once accepted | a living catalogue (supersede it; never edit the decision) |
| `design` | a bounded-convergence record: status table, passes, decisions, corrections | ship to a generated project (keel-only design records are pruned) |
| `spec` / `tool` | a contract: command, purpose, when (and when NOT) to use, args, output, effects | narrative |

When a document and the rule it describes disagree, the rule wins and the
document is the thing to fix.

## 2. Rosters and the discriminator (gated — `check_S`, `check_F`)

Two things that look alike sitting side by side, with nothing that says why
they are two, is the documentation failure a reader feels most. Each part
describes itself well; nothing states the **discriminator**. This repository
mandates two-artifact decompositions everywhere (trigger and doer, adapter and
tool, neutral surface and wire adapter — CONVENTIONS §7, §9, §14), so it is
unusually exposed.

The fix is structural. A directory README that declares `## What ships here`
carries a **roster** (CONVENTIONS §2): every member named once in a `Member`
column, and a `Not for` cell on every row that says what a reader must *not*
reach for that member to do — **naming the sibling that does it**. A tool spec
carries the same discriminator as a `- NOT ...` bullet under `## When to use`.
The gate proves the cells exist and the members match; only you can make the
cell true. A `Not for` cell that says "everything else" or "n/a" is a cell
that declined to answer.

Write the discriminator from what the code does, not from what the names
suggest: `rebuild_index.py` and `build_corpus.py` both say "index", and the
roster says one writes a README list nothing reads and the other writes the
graph every agent queries.

## 3. Citations and links (gated — `check_Q`)

A reference is an edge of the knowledge graph, and it is written in one of two
closed forms so a machine and a reader parse it the same way:

- **A relative Markdown link** `[text](path#anchor)` names a file, a directory,
  or a heading that exists. Inside fenced or inline code it is an illustration,
  not a link.
- **A section citation** `§N` names a numbered heading. A bare `§N` **always**
  cites `CONVENTIONS.md`. A section of any other document is cited by naming
  the document immediately before the sign — `docs/guides/python-style.md §3`,
  backticks, a comma or a line break between them or not. A bare `§N` never
  means "this document": that reading turns ambiguous the moment a guide
  numbers its own sections. A `§N` counts everywhere, code included: a quoted
  help string cites the same section a sentence does.

A backticked repository path (`scripts/check_structure.py`) is a **mention**:
the corpus turns it into an edge when it resolves, and `make advise` lists the
ones that do not. Prefer the root-relative spelling; a bare basename used as a
noun (`check_structure.py`, twenty-nine times in this tree) is prose, and the
graph cannot follow it.

## 4. Statements: one claim per sentence, and name the mechanism

A sentence makes one claim, and the claim is checkable. "The gate enforces
this" is not checkable; "`check_Q` errors on a `§N` no numbered heading
answers" is. When a document says something is enforced, advised or judged,
it names the check letter, the make target, the test, or the guide that does
it — the `enforced_by` field of `config/practices.json` is the machine-read
form of the same habit, and `check_T` proves those names resolve.

Numbers are measurements, and a measurement says when and how it was taken
("57 links and 132 citations as the check counts them, 2026-09-02"). A number
without a method is an opinion with digits.

Prefer the plain imperative to a modal: "cite the document by name", not "the
document should be cited". Say what to do, not what would be nice.

## 5. The normative register: adapt BCP 14, do not adopt it

RFC 2119's capitalised keywords (MUST, SHOULD, MAY) fit a specification whose
readers implement it independently. Most documents here are not that: a guide
teaches, an ADR records, a README orients. The house register is the plain
imperative of §4, which carries the same force without the boilerplate.

A document that *is* a specification — a wire contract, a tool spec's body, a
features list a third party implements against — may use BCP 14 keywords. If
it does, it declares so with the standard boilerplate sentence at its top and
uses the keywords consistently thereafter; a lone `MUST` in a paragraph of
plain prose is emphasis pretending to be a rule. This is not gated (a
`normative:` frontmatter key over a closed vocabulary was designed and is
deferred until a second specification wants it); the one such keyword in the
tree, in `agents/practice_refactor/prompt.md`, is used correctly.

## 6. Idempotency: state it, then say how it is proven

"Idempotent" is claimed in six places in this tree and proven in one class of
them. There are three separable properties, and a document names which it
means:

- **Generator fixed point** — running the doer twice yields byte-identical
  output. Gated where it matters: `check_corpus` builds twice and compares;
  `export_openapi --check` and `generate_aad_schema --check` compare the
  committed artifact with a fresh render.
- **Stated repeat-safety** — the document says the command may be re-run.
  Presence is checkable; truth is the author's.
- **Procedure idempotency** — a multi-step procedure lands the same state
  from any starting point. Judgment only; say what the steps assume.

Write the property, not the adjective: "recomputes the keyword edges from
scratch each run and keeps the authored ones" says what "idempotent" only
gestures at.

## 7. Freshness is a fact, not a courtesy (gated — `review_docs`)

`updated:` means **touched**: never earlier than the file's last commit, and
today's date when the file is modified (CONVENTIONS §1). It is a cache of the
git date kept in the file so the corpus can rank by recency without git. Set it
in the same change that touches the file; the gate lists every file that was
not. A separate `reviewed:` key can carry the human meaning — "someone read
this and it is still true" — when someone wants to track that.

A design record carries a **corrections log**: when a claim above it goes
stale, the claim is corrected inline and the correction is logged with its
date, so a reader can tell what was true when.

## 8. ADRs are immutable; cross-references are not

An accepted ADR records a decision at a moment. Its decision text is never
edited: a changed decision is a new ADR that supersedes it (`status:
superseded`, `superseded_by`, both gated). A cross-reference in an accepted
ADR — a link to a file that moved, a citation made ambiguous by a later
grammar, a note that a check letter moved — may be maintained, in a one-clause
edit that leaves the decision untouched, and that edit restamps `updated:`.

## 9. What is enforced, advised, and judged

| Property | Enforced by | Tier |
|---|---|---|
| Frontmatter present, vocabularies valid, `superseded_by` when replaced | `check_A` | gate |
| Every `##`-annotated make target is in `make help` | `check_P` | gate |
| Every link and `§N` resolves | `check_Q` | gate |
| The check catalogue and the triggers agree | `check_R` | gate |
| A roster names every member, nothing else, with a `Not for` cell | `check_S` | gate |
| A tool spec's seven sections, effect word, `- NOT` line | `check_F` | gate |
| `updated:` no earlier than the last commit; today when modified | `scripts/jobs/review_docs.py`, `tests/integration/test_doc_freshness.py` | gate |
| Every practice's `enforced_by` names a mechanism that exists | `check_T` | gate |
| A backticked path that resolves to nothing | `scripts/jobs/review_docs.py` under `make advise` | advisory |
| A `Not for` cell that is true; a `- NOT` line that names the right sibling | this guide, a reviewer, `agents/doc_reviewer` (`make doc-review`) | judgment |
| One claim per sentence; the mechanism named; measurements dated | this guide | judgment |
| The normative register used deliberately | this guide | judgment |

## 10. The review loop

`make check` runs the gate on every commit; `make advise` reports what the
gate does not fail on; `make doc-review` runs the doc reviewer's dry-run (and
the stop hook runs it when a turn ends); `make doc-review-apply` lets the agent
propose one gated edit per finding, with this guide's rules retrieved from the
corpus as its context. Each is a tier of the same
rule: decidable, suspected, judged. None of them replaces the sentence you
write with the reader in mind.
