---
title: Documentation quality — the gated half, the judgment half, and the agent
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, documentation, checks, corpus, rosters, citations, convergence]
summary: The bounded-convergence record for keel's documentation-quality system: which documentation rules are decidable by a machine and are now gated (checks P–S, the tool-spec body, supersession), which are judgment and belong to a guide and an agent, what each pass measured and decided, and what remains. The status table is authoritative; the per-pass notes below it are historical.
id: docs-design-documentation-quality
created: 2026-09-02
updated: 2026-09-02
visibility: internal
canonical: true
---

# Documentation quality — the gated half, the judgment half, and the agent

This is keel's own worklist for making its documentation stay **current,
correct and unambiguous** by the same means its code does: a deterministic
gate for what a rule can decide, an advisory for what a rule can only suspect,
and a guide plus an agent for what needs judgment. It is keel-only prose (a
generated project does not carry it — `copier.yml` `_exclude`); the *rules* it
produced live where a project can read them: `CONVENTIONS.md` §2, §6, §10 and
`docs/guides/deterministic-checks.md`.

## Where this stands (verified 2026-09-02)

| Phase | Subject | Status |
|---|---|---|
| 1 | Free gates, green on arrival: help parity (`check_P`), cross-references (`check_Q`), supersession symmetry (`check_A`) | done (`93c5606`, `6ac108f`) |
| 2 | Honesty about the check inventory: catalogue parity (`check_R`), the cdmon decision | done (`003c471`) |
| — | Adversarial review of P/Q/R — 59 raised, the modelled/unmodelled boundary made explicit | done (`b8d0226`) |
| 3 | The seam: rosters (`check_S`, six `## What ships here` tables) and the tool-spec body contract (`check_F`) | done (this commit) |
| 4 | Freshness: `updated:` versus the git history | **not started** — needs the `updated:` decision below |
| 5 | Make the knowledge graph authored: reference edges in `build_corpus`, edge-kind vocabulary in `check_corpus`, retrieval repair in `query_corpus` | **not started** |
| 6 | The model-absent path in `models/claude_code_headless.py` (absent says so and exits 0; present-but-failing fails) | **not started** — prerequisite for anything automatic |
| 7 | The deterministic doer (`scripts/review_docs.py`), a `subject` field in `config/practices.json`, `docs/guides/doc-style.md`, the `make check` tail nudge | **not started** |
| 8 | `agents/doc_reviewer/` and its three thin adapters (skill, stop-hook, pre-commit); the scheduled job repointed | **not started** |

Every phase lands as one bounded pass: red test, smallest change, `make verify`
green, one commit. Letters belong to landed checks (ADR-0008): the next free
one is `T`.

## Why

Two failures motivated this. The first is generic: documentation rots at exit
0. A renumbered section, a moved guide, a target added without its `##`
annotation, a check listed in the catalogue that nothing runs — every one of
these was true somewhere in this repo on 2026-09-02, none failed anything, and
each was found only because a person went looking. The second is the one a
reader actually feels: **unexplained decomposition**. Two things that look
alike sit side by side (`svc-vllm` and `vllmctl` in another project;
`rebuild_index.py` and `build_corpus.py`, `structure_check` and
`accountability_report`, `refactor_practice.py` and `agents/practice_refactor`
here) and no document says why they are two. Each part describes itself well;
nothing states the *discriminator*. keel is unusually exposed to this because
CONVENTIONS §7, §9 and §14 each *mandate* a two-artifact decomposition (trigger
and doer, adapter and tool, neutral surface and wire adapter).

## The tier rule, applied to documentation

The rule is the one `docs/guides/coding-practices.md` already states for code:
*can a rule decide it deterministically, with no model and no network?* If yes
it is a gate in `scripts/check_structure.py`, 3.6-safe and stdlib-only, and it
fails the build. If a rule can only suspect it, it is an advisory under `make
advise`. If it needs judgment, it is a guide, and an agent that has read the
guide can apply it. Nothing in the gate calls a model; nothing in the agent
fails a build.

Three properties every gate here shares, because the code gates share them:

- **Absent is not broken.** A file a generated project legitimately lacks
  degrades in silence; a file that is present but unreadable is an error; a
  shape the check cannot read is a WARN that says *unverified*, never a pass
  ("a check that reports success while checking nothing" is the defect
  family, named silent-green in the code).
- **Every error names the file, the line where there is one, the value as the
  author wrote it, and the remedy.** The message is the documentation of the
  rule at the moment it matters.
- **Read the source of truth, do not restate it.** `check_P` applies the help
  recipe's *own* grep pattern; `check_R` reads the catalogue's *own* table and
  the Makefile's *own* rules; `check_S` reads the directory's *own* listing.
  A check that restates what it verifies can agree with a wrong answer.

## What landed

### `check_P` — Makefile help parity (Phase 1)

Every target line carrying a `## ` annotation must be one the `help` recipe's
grep pattern lists. The live instance: `e2e` was annotated from the day it
existed and never once appeared in `make help`, because `[a-zA-Z_-]` has no
digits. The recipe was widened to `[a-zA-Z0-9_-]` and the name column from 14
to 22. The check models a `grep -E`/`-P`/`egrep` first stage over
`$(MAKEFILE_LIST)`, `-i`, a pattern held in a plain make variable, later
`grep -v` stages and recursive `include`/`-include`/`sinclude`; it says
*unverified* for a grep without `-E` (basic regex, which Python cannot run),
`-F`, a second selecting grep, an include named by a variable or wildcard, and
a pattern variable it cannot expand. Landed at the error tier: the tree
complied the moment the recipe was widened.

### `check_Q` — cross-references resolve (Phase 1)

Every relative Markdown link in prose (file, directory, `#anchor`) names
something that exists, and every `§N` citation names a numbered heading. The
citation grammar is closed on purpose, because the tree had already grown
ambiguous: a bare `§N` **always** cites `CONVENTIONS.md`; a section of any
other document is cited by naming it immediately before the sign
(`docs/guides/python-style.md §3`; backticks, a comma or a line break between
them are all read). A bare `§N` never means "this document" — `python-style.md`
had cited its own §1 and §3 in exactly the form that means CONVENTIONS
everywhere else, and ADR-0003 wrote a backticked `AGENT.md`, a comma and then §9,
meaning two references; both are explicit now. Measured on landing: 57 links and 132 citations, none
dead — so the check is a regression barrier, and what it buys is that
renumbering `CONVENTIONS.md` or moving a guide fails with the full list of
citations to update. The check proved itself on its author twice: its first
real-tree run flagged the example citation in its own comment, and the review
round's wider grammar found ADR-0003.

Two descendant defects surfaced with it. ADR-0009 hyperlinked
`docs/design/keel-hardening-plan.md`, which copier prunes from every generated
project — now a plain citation that says why. And the README's remedy for
deleting `models/` was incomplete once links are held: two guides link into it,
so both README twins now say the second `make check` lists every doc still
linking into the removed directory, and the generation test follows that
remedy end to end.

### Supersession symmetry (Phase 1, in `check_A`)

`status: superseded` requires `superseded_by`, as `deprecated` always has. One
rule, two lifecycle vocabularies; the ADR one had no consumer.

### `check_R` — check catalogue parity (Phase 2)

`docs/guides/deterministic-checks.md` and the triggers agree on one
membership: every catalogued script exists; an `error`/`error*` row is
reachable from `make check-all`; a `report` row is run by *some* target; every
script `check-all` reaches is catalogued; the hooks table and
`.pre-commit-config.yaml` name the same hook ids, and neither exists without
the other. Its first run found four lies: the cdmon row claimed the error tier
while `check-all` never ran it; the accountability report was catalogued and
run by nothing; `check_python_version.py` ran under `check-all` with no row;
the hooks table omitted `ruff-format`.

**The cdmon decision.** `cdmon` is not on PyPI (measured with the site's CA
bundle). It stays, because it is CONVENTIONS §9's worked example of a thin
adapter over an external tool and the adapter skips loudly; the row now says
so, and `make check-cdmon`, reached from `check-all`, makes the claim true: a
stated skip (exit 0) until `cdmon` is on PATH and `config/cdmon/cdmon.yaml`
exists. The showcase's Checks page, which mirrors the catalogue, gained the
three rows it lacked and a test that pins it to the catalogue with the gate's
own table reader.

### The adversarial review (between Phases 2 and 3)

Four lenses — generated-project behaviour, silent-green paths, message
quality, spec coherence — over P, Q and R raised 59 findings. The sharpest,
confirmed by independent skeptics: `check_P` applied every grep pattern with
Python's engine whatever grep's flags said, so a recipe without `-E` reported
every target listed while `make help` printed nothing; `check_Q` read a named
citation only when the name sat directly before the sign, so the house
spelling `` `doc.md` §N `` fell back silently to CONVENTIONS; `check_R` counted
a commented-out `# $(PY) scripts/x.py` as running `x.py`, so the exact cdmon
lie it was written for would have stayed green once `check-all` stopped
running it. All modelled now, and every unmodelled shape says *unverified*.

### `check_S` — roster parity, and the tool-spec body (Phase 3)

The answer to unexplained decomposition is a **roster**: a README that
declares `## What ships here` is held to its directory — every member named
exactly once in a `Member` column, nothing else named, and a `Not for` column
whose every cell says what a reader must *not* reach for that member to do,
naming the sibling that does. That cell is the discriminator a bare listing
never states. Opt-in by the heading, so no generated project is retro-failed;
keel declares six: `agents/` (which named none of its four agents), `agents/tools/`
(none of its seven specs), `docs/guides/`, `mcp/`, `scripts/` and
`scripts/jobs/`. The two READMEs whose members are pruned with the showcase are
`.jinja` twins (`parity`, declared in `config/project.json`), so a
`showcase=false` project's roster matches its pruned tree — and the generation
tests run `check_S` inside every generated project, which is what proved the
twins. Rows are data: a `.jinja` twin is not a member (check_N's business), nor
are the labels and packaging (`README.md`, `AGENT.md`, `CLAUDE.md`,
`__init__.py`, `__pycache__`).

The same discriminator, at the tool level: `check_F` now gates the body
CONVENTIONS §10 always described — the seven sections in order, `## Side
effects` opening with the word for the declared `tool_effect` (the body and
the frontmatter are read by different agents and must not disagree), and at
least one `- NOT ...` bullet under `## When to use`. Six of seven specs
carried that line by discipline; `accountability_report.tool.md` did not.

Found while writing the rosters, and fixed: `scripts/README_check_structure.md`
was a stale duplicate of the catalogue (checks A–D of what is now A–S,
referenced by nothing, indexed by the corpus) — removed; `structure_check.tool.md`'s
Purpose listed the same A–F-era set; `scripts/jobs/README.md` claimed
LLM-backed jobs call agents, and none does.

## Decisions taken here (the ones a later reader will look for)

- **Letters belong to landed checks** (ADR-0008's rule, applied). ADR-0005's
  proposed scan had taken `check_P` by name; `P` is help parity, and ADR-0005
  (status: proposed) now says "the next free letter" instead of reserving one.
  ADR-0008 carries a maintenance note; the plan carries a correction.
- **The grace tier is spent.** ADR-0008 ships a new check as WARN for one
  release and promotes it in the next, from `v0.1.0`. P, Q, R, S and the
  `check_F` body land at the error tier anyway, each for the same stated
  reason: the tree complied on arrival, or was made to in the landing commit.
  Phase 4 (freshness) claims the same only because its landing commit
  restamps every stale document; without that it would ship as a WARN.
- **Accepted ADRs may have a cross-reference maintained.** ADR-0003, -0008 and
  -0009 each gained a one-clause edit (a citation made explicit, a link turned
  into a plain citation, a note that a letter moved). The decision text is
  untouched; ADR-0004 and -0008 already carried this kind of edit.
- **`rebuild_index.py` stays.** It is the MCP action server's one tool and the
  scheduled job's artifact; nothing reads `wiki/INDEX.md`, and the roster now
  says exactly that. Whether to retire it or repoint the schedule is Phase 8's
  question, taken when the scheduled job has a real doer to point at.
- **A `§N` inside code is a citation; a link inside code is not.** A quoted
  help string cites the same section a sentence does; a link written in a
  fence is how one illustrates link syntax. The asymmetry is stated in the
  catalogue.

## Open questions, with the answer this plan will take unless told otherwise

1. **What does `updated:` mean?** The only machine-checkable reading is
   *touched*: `updated:` is never earlier than the file's last commit date.
   A separate `reviewed:` key can carry the human meaning later. Phase 4 lands
   on this reading, as a WARN first, with a mechanical normalisation of the
   135 stale files in its own commit, then promotes (ADR-0008 grace).
2. **May `check_structure.py` shell out to git?** No — ADR-0009 already
   decided that for the release gate. Freshness goes to
   `tests/integration/test_doc_freshness.py`, beside `test_release_identity.py`.
3. **Rosters: opt-in or mandatory?** Opt-in by the heading. Making them
   mandatory for taxonomy directories is a later promotion, if the six prove
   their worth.
4. **May the doc-review agent write?** Dry-run by default, like every agent
   here; writes only behind `execute=True`, gated on `make verify` through
   `apply_refactor`, exactly as `practice_refactor` does.

## Rejected, with reasons

Vale / textlint / write-good / alex / proselint (need `vale sync` over the
network, and vendor a third party's house style); hosted freshness services
(network and secrets); Obsidian `[[wikilinks]]` (not portable Markdown); the
MADR template (keel's ADRs are better, and ADRs are immutable); a Diátaxis
re-organisation (re-paths 158 files and breaks the corpus, the links and the
twins); lychee / markdown-link-check / `mkdocs --strict` (0 broken links on
landing; 25 lines of stdlib do it, inside the gate that already runs);
doctest / Sybil / mktestdocs (execute shell from docs — a hazard on an
endpoint-protected host); gating unresolved backticked paths (204 of 863 are
bare basenames used as nouns — advisory at most); gating corpus near-twin
scores (the top pairs are all agent artifacts); a standalone `make doc-review`
as the primary nudge (`make advise` is the cautionary precedent: clean,
documented, invoked by nothing — the nudge goes on `make check`'s tail);
CODEOWNERS (vendor-specific, a second source of truth); a second registry
`config/doc_practices.json` (one `subject` field in the existing one); RFC 2119
capitalisation as house style (adapt, not adopt: a declared `normative:` key
over a closed vocabulary, later).

## Corrections to this document

None yet. When a claim above goes stale, correct it inline and log it here.
