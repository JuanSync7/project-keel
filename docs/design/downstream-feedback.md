---
title: Downstream feedback — what the first generated project found wrong with keel
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The bounded-convergence record for the defects bedrock-platform, the first real project generated from keel, reported back — a red gate on arrival, unknown directories the gate never sees, make targets whose effect nobody declares, and child processes that inherit every credential — plus the command that checks any keel-generated project for all of them. One slice per defect, five passes, each landed as one commit on a green `make verify`.
id: docs-design-downstream-feedback
created: 2026-10-06
updated: 2026-10-06
visibility: internal
canonical: true
---

# Downstream feedback — what the first generated project found wrong with keel

bedrock-platform was generated from keel at `7f0a68b` and reported five defects.
Each was reproduced in keel before it was accepted. This document is the worklist:
the status table is authoritative, the per-slice notes record the measurement and
the decision.

## Status

| Slice | Defect | Status |
|-------|--------|--------|
| 1 | A generated project fails its own doc-freshness test on arrival | done — `make verify` green (776 passed); ADR-0010 proposed, awaiting acceptance |
| 2 | An unknown directory is invisible to the structure gate | done — `make verify` green (807 passed) |
| 3 | A make target's effect is declared nowhere, so a "check" can write | planned |
| 4 | Every child process inherits every credential in the environment | planned |
| 5 | No command checks an existing keel project for slices 1–4 | planned |

The cap is these five passes. A concern found mid-slice is queued at the end of
this document, not started.

## Ground rules

- Each slice lands as one commit, test-first, on a green `make verify`.
- A slice is not done until it holds downstream: it is exercised in a project
  generated from the working tree, not only in keel.
- No project fact is hardcoded in a check. A list a check consults lives in
  `config/` or is read from the document that owns it.
- Every writer a slice adds is declared to check_V and proven to reach its fixed
  point (`docs/guides/idempotency.md`).

## Slice 1 — freshness on arrival

**Measured.** Keel's 31 governed documents, committed once into a fresh
repository, are 31 of 31 stale under `tests/integration/test_doc_freshness.py`:
every `updated:` is a literal from keel's history, and the arrival commit is newer.

**Not only arrival.** The same failure recurs on every `copier update` that brings
a document in: the upstream stamp is older than the commit that lands it.

**Decision.** `updated:` means touched *in this repository*, so a document that
arrives from the template is touched on the day it arrives. A restamping doer sets
`updated:` to today on every governed document that is new or modified in the
working tree and leaves every other byte alone, so a second run is a no-op. Copier
runs it after copy and after update, and the project can run it by hand. The
freshness rule itself is not weakened.

**Built.** The writer is `scripts/jobs/restamp_docs.py` (`make restamp-docs`),
recorded in `docs/adr/0010-generation-needs-trust-to-stamp-docs.md`. Its cost is
that `copier copy` now needs `--trust`. A project generated from the working
tree measured 112 of 112 governed documents stale before the writer and 0 after.
The tests are `tests/unit/scripts/test_restamp_docs.py`,
`tests/integration/test_doc_restamp.py`, and the arrival and update cases in
`tests/integration/test_copier_generation.py` and
`tests/integration/test_copier_update.py`.

**Hardened.** A review found the copy task skipped two shapes: generating into a
repository with history (105 of 113 documents stale after the first commit) and
`copier update --conflict rej` (one `.rej` per document). The task now carries no
mode flag. The writer and the judge share one clock
(`review_docs.resolve_today`), the writer's target is never earlier than the last
commit, and both read changed paths with `git diff --relative`, so a project
below its repository's top is judged on its own documents. Each shape has a case
in the files above, and `tests/integration/test_copier_generator_contract.py`
holds every copier invocation of the writer to one argument list.

## Slice 2 — the directory taxonomy is closed

**Measured.** `check_B` labelled only directories named in its own `TAXONOMY`
list, so a `parked/` at the root passed with zero errors, in keel and in a
project generated from it. Keel tracks 81 directories, and 45 of them lack
`README.md` or `CLAUDE.md`. That count includes 6 hidden directories
(`.claude/**`, `.github/**`), which CONVENTIONS §5 puts outside the taxonomy.
Of the 75 non-hidden directories, 16 are top-level; all 16 are `TAXONOMY` rows
and all carry both labels. Of the 59 nested ones, 20 carry both labels (6 agent
directories, 4 under `api/`, 6 `src/` layers and stacks, `ops/scheduled`,
`scripts/hooks`, `scripts/jobs`, `demo/aad_reference_agent`). 10 carry
`README.md` only (5 `docs/` subfolders, `test-docs/test-plan`, 4 `tests/`
scenario directories), and 29 carry neither. The 39 that are not fully labelled
are 5 Python packages under `src/backend/` (check_C gates them as packages), 9
frontend source directories, 11 test directories, 8 `docs/` and `test-docs/`
subfolders, 5 config and data subfolders, and `scripts/agent_surface`. An
unlabelled `src/zzz/` passes only while it holds no `.py`; with Python and no
`__init__.py`, check_C already errors. A generation from a dirty keel tree
copies keel's untracked root symlink `project-keel` into the project, because
copier's dirty-HEAD clone runs `git add -A` on the work tree.

**Decision.** The top level is a closed vocabulary. A non-hidden root directory
is a CONVENTIONS §2 row or is declared by name in `config/project.json`
`structure.extra_toplevel`; anything else is an error naming both fixes. The key
is a plain list of names, because the declared directory's own `README.md`
`summary:` already says why it exists, and a second copy in the manifest would
drift. A declaration must exist (else stale), must not repeat a row (else
redundant), and must be a plain top-level name. The nested rule is every
directory directly under `agents/`: each `agents/<name>/`, which CONVENTIONS §13
already makes a "done when" condition, and the shared `agents/tools/` (§10),
which keel already labels; every other nested directory is free, and `AGENT.md`,
CONVENTIONS §2, `CONTRIBUTING.md`, `README.md` and the showcase copy now say
exactly that. An undeclared symlinked directory is a WARN, not an ERROR: no
check reads through a link, and `scripts/check_structure.py` cannot ask git whether the
link is tracked. An ERROR would turn keel's local gate red over the stray
symlink, and every generation from a dirty tree with it. The rule lands as an
ERROR rather than a one-release WARN under the
`docs/adr/0008-gated-module-contract-for-agent-interpretability.md` grace tier,
because keel complies at landing, which is the precedent checks P, Q, R, S and
V set. A downstream project with its own top-level directory goes red on
`copier update`, so the `CHANGELOG.md` upgrade note names the one-line fix.

**Built.** `scripts/check_structure.py` `check_B` with `_declared_toplevel` and
`_require_labels`; the empty `structure.extra_toplevel` key in both
`config/project.json` and its twin; CONVENTIONS §2 ("The taxonomy is closed"),
§6 and §15; `AGENT.md`, `CONTRIBUTING.md`, both `README.md` twins,
`src/backend/showcase/_data.py`, `docs/guides/deterministic-checks.md` and
`CHANGELOG.md`. The tests are `tests/unit/scripts/test_check_b.py` (25 cases:
22 red before the change, 3 guards green) and
`test_an_undeclared_top_level_directory_reds_a_generated_project_until_declared_and_labelled`
in `tests/integration/test_copier_generation.py`. That test failed against the
old `check_B` (a generated project with `parked/` reported 0 errors) and passes
against the new one. Nine mutations of the new `check_B` each turned at least
one unit test red. Keel's own gate reports 0 errors and one WARN, for
`project-keel/`.

## Slice 3 — every make target declares its effect

**Measured.** `scripts/run_make_target.py` validates a target's spelling, not its
effect, and says so. bedrock-platform added effect labels (its ADR-0010) and
labels `fmt` and `site-data` `[local]`, the same as `check`, so the gap it closed
for remote writes stays open for the tree.

**Decision.** Port the labels, the `$(WRITE_GUARD)` refusal under CI and Ralph
loops and the labelled `make help` as check_W, letter-compatible with
bedrock-platform's, and split the read-only targets from the ones that rewrite the
tree. The gate runner refuses a target whose label says it writes and fails a
read-only one that dirtied the tree.

## Slice 4 — child processes get an allowlisted environment

**Measured.** No subprocess in keel passes `env=`. The model adapter that spawns a
model CLI hands it every variable in the parent's environment, cloud credentials
included.

**Decision.** One helper builds a child environment from a configured allowlist; a
model adapter that needs a credential names the variable in its own config. A
check fails a subprocess call that does not use it.

## Slice 5 — audit an existing keel project

**Decision.** One command runs the template's current gates for slices 1–4 against
another project's tree, read-only, and reports what that project would fail after
`copier update` — so a project learns what it owes before it updates.

## Queued

Found during the slices and deliberately not started:

- **ADR numbers collide downstream.** Keel's ADR-0010 and bedrock-platform's own
  ADR-0010 share a number, so `copier update` would bring keel's in beside it.
  Template ADRs and project ADRs need separate number spaces; slice 3's ADR
  must not deepen the collision.
- **`review_docs` path forms in a nested repository.** Porcelain paths and
  `ls-files` paths can disagree when the project is below its repository's top.
- **`_SKIP_DIRS` and the `_git` helper are duplicated** between
  `review_docs.py` and `restamp_docs.py`.
- **`make new ALLOW_DIRTY=1` copies untracked files** from a dirty template,
  including a stray symlink at the root.
- **The copier 9.3.0 floor is unverified** for `_tasks` with `_copier_python`.
- **An untagged template skips `_migrations`**, including the update restamp.
- **Nothing pins `TAXONOMY` to the CONVENTIONS §2 table.** The list in
  `scripts/check_structure.py` and the table are kept in step by hand, and since
  slice 2 a drift between them is an error source. A parity check or test should
  read one from the other.
- **Keel's copier `_exclude` names a root `tmp/`.** Under the closed taxonomy
  a scratch directory at the root cannot be declared (stale while absent) or left
  undeclared (error while present); scratch belongs in a dot-directory.
- **A declared extra directory is outside `CODE_ROOTS`.** Python in it is not
  read by check_D, E, O or V, by lint or by typecheck.
- **A `TAXONOMY` directory that is itself a symlink** passes check_B through the
  link while every walking check skips its contents.
- **Gitignored tool output at the root** (`site/`, `logs/`, `out/`) not in
  `IGNORE_DIRS` now reds a local `make check`; the gate cannot read
  `.gitignore` semantics without git.
