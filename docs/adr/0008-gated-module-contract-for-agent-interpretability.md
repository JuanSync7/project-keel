---
title: "ADR-0008: Agent interpretability is a gated contract — the module header, authored coverage, and corpus currency"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, corpus, docstrings, gate, agents, readability, practices]
summary: "An agent can only rely on what the gate proves. The machine-readable module header (title:/summary:) becomes check_O, authored symbol coverage (check_E) is promoted to an error, the corpus builder single-sources its scope from check_structure, and the local corpus agents query is gated fresh-when-present. The judgment half — readability and failure-mode discipline — is canonical prose in docs/guides/python-style.md, deliberately ungated."
id: docs-adr-0008-gated-module-contract-for-agent-interpretability
created: 2026-08-18
updated: 2026-08-18
visibility: internal
canonical: true
---

# ADR-0008: A gated module contract for agent interpretability

**Status:** accepted. Extends the practices registry of
[coding-practices](../guides/coding-practices.md); the enforcement mechanics
live in `scripts/check_structure.py` (`check_O`, `check_E`) and
`scripts/jobs/check_corpus.py`. Takes the check letter `O`;
[ADR-0005](0005-external-environment-manifest.md)'s proposed completeness scan
(never implemented) moves to `check_P` — letters belong to landed checks.

## Context

This project is built to be read by more agents than authors, in a company
where most readers are not software engineers. Its agents (`wiki_navigator`,
`query_corpus`, `index_enforcer`) interpret the code through one artifact: the
corpus knowledge graph built from module docstring headers (`title:` /
`summary:` / `owner:`) and `__all__` symbol docstrings.

The question this ADR answers: **what guarantees that interpretation?** The
honest answer must be "the gate", because an agent trusts the convention
whether or not it held. A discipline that is followed but unenforced is worse
than none — the agent cannot tell the difference. Measured on this tree, the
guarantee had three holes:

1. **The header was 100% followed, 0% enforced.** All 109 modules carried a
   docstring; 5 lacked explicit `title:`/`summary:` and silently fell back
   (filename as title, first prose line as summary — then labeled
   `summary_source: "authored"`, claiming an authorship it did not have). A
   module with *no* docstring is silently dropped from the corpus
   (`build_corpus.py`: `if not doc: return`), so an agent's "what does this
   project contain?" would be confidently incomplete, at exit 0.
2. **The corpus walked a private copy of the scope.** `build_corpus.py`
   re-typed `CODE_ROOTS` and never carried `runtimes` (from the initial commit
   onward) — six modules invisible to every corpus query the whole time.
3. **Nothing gated the corpus agents actually read.** `wiki/corpus.json` is a
   gitignored generated view; `make check-corpus` builds *fresh* and never
   compares the on-disk file, so it was three modules (33 nodes) behind the
   tree while `make verify` ran green — the `openapi.json` defect class
   (ADR-0007), but the stale artifact here is the agents' world-model.

## Decision

**1. `check_O` (ERROR): every `.py` under `CODE_ROOTS` carries a module
docstring with explicit, non-empty `title:` and `summary:` lines.** The grammar
is exactly the one `build_corpus._docstring_meta` reads; because
`check_structure.py` must stay 3.6-safe and cannot import a `$(PY)`-only
module, the parser is duplicated and **pinned by a parity test** that runs both
over the same corpus of tricky docstrings. Unparseable files are skipped
(check_D already warns there — same idiom as check_E).

**2. `check_E` is promoted WARN → ERROR.** Authored docstrings on
`__all__`-exported symbols are the symbol half of the same contract, and the
tree measures at zero findings, so promotion costs nothing. The grace-tier rule
(ship WARN one release, promote next) binds from `v0.1.0` onward; there has
been no release yet.

**3. `build_corpus` single-sources `CODE_ROOTS` and `IGNORE_DIRS` from
`check_structure`.** The drifted private copy is deleted; a future tenth code
root cannot be forgotten twice. `check_structure` stays the canonical scope —
the same source `make lint`/`fmt` are already pinned to by
`tests/integration/test_gate_scope.py`.

**4. `make check-corpus` gates the local corpus when present.** Absent → say so
loudly, exit 0 (a fresh clone, CI, and a day-one generated project have none —
the absent-vs-drifted split ADR-0007 established for `openapi.json`).
Present-but-stale → ERROR naming `make site-data`. Staleness is judged on the
**deterministic projection**: nodes' `"generated"` summaries and links are
stripped back to their deterministic base before comparison, so
`index_enforcer`'s legitimate enrichment is never read as rot.

**5. The judgment half is prose, deliberately ungated.**
`docs/guides/python-style.md` becomes the canonical statement of how Python is
written here — readability and loud failure modes outrank speed; comments carry
reasons, not restatements; how a code agent works in this repo. It enters the
practices registry as **doc-tier**: per the tier rule, a gate that blocks a
commit on a judgment heuristic would reject correct code. Guides ship verbatim,
so every generated project inherits the same contract.

## What is deliberately NOT required

- **`owner:` on modules** stays a warning-tier concern. Ownership inherits from
  the nearest labeled `README.md` (build_corpus's chain); requiring it per
  module would red keel itself (0/109 declare one) — the grace-tier rule
  forbids shipping a rule the template fails.
- **Docstrings on non-exported symbols.** Only `__all__` names are corpus
  symbol nodes; requiring the rest buys the agent nothing and taxes every
  helper. (80 such functions exist today, legally.)
- **An exemption mechanism.** No committed `.py` legitimately lacks the header
  today (test data is built in `tmp_path` fixtures, per house style). The first
  real need adds a *declared* waiver, not a silent carve-out.

## Alternatives considered

- **Docstring presence only (no explicit keys).** Rejected: the fallback path
  is precisely the defect — filename titles and accidental first-line summaries
  labeled `authored`. The corpus cannot honestly synthesize what was not
  written.
- **Sharing the parser by import instead of a parity test.** Rejected:
  `check_structure` runs under the 3.6 pre-commit interpreter;
  `scripts/jobs/build_corpus.py` is `$(PY)`-only. Importing in either direction
  couples the interpreter floors; the parity test pins the grammar without the
  coupling.
- **Committing `wiki/corpus.json` and drift-gating it like `openapi.json`.**
  Rejected: a 500-node JSON in every diff is merge-conflict bait, and unlike
  the OpenAPI contract no external consumer needs it at rest — agents build it
  locally. Gating freshness-when-present keeps the guarantee without the churn.
- **An LLM "readability reviewer" as the enforcement mechanism.** Rejected as
  the *guarantee* (a model's judgment is not a proof, and the tier rule already
  sorts judgment out of the gate); nothing prevents adding one later as an
  advisory doer over the same registry.

## Consequences

- A new module cannot enter the tree without the header an agent needs to find
  it; an exported symbol cannot ship without its authored summary; a stale
  local corpus fails the gate instead of quietly mis-informing every query.
- `make check-corpus` acquires a repair instruction (`make site-data`) but
  never repairs anything itself — a check that writes is not a check.
- Five modules gain explicit headers in the landing commit, including
  `check_structure.py`, which must satisfy its own check.
- Future work, out of scope here: `wiki/llms.txt` / `llms-full.txt` currency
  (same class, showcase-coupled surface), and symbol coverage for private
  modules whose names are re-exported by a package `__init__`.
