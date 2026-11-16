---
title: CMP-4 — keel enforces what it claims, and emits evidence jarvis can read
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-4.
id: docs-internals-campaigns-cmp-4
created: 2026-10-07
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-4 — keel enforces what it claims, and emits evidence jarvis can read

**Why.** A generated project is told to work test-first, in bounded passes, with
end-to-end coverage and checked responses. On 2026-10-07 the maintainer asked
which of those keel enforces. Measured against the tree:

| Practice | What ships | Enforced by |
|----------|------------|-------------|
| Idempotency | `docs/guides/idempotency.md`, `effect:`/`rerun:` headers | check_V and `tests/integration/test_idempotence.py` |
| TDD | `docs/guides/dev-loops.md`, the mirror-test rule | the mirror rule only; nothing proves a test can fail |
| Ralph loop | `docs/guides/dev-loops.md` | check_Z on plan tables and `tests/integration/test_work_trailers.py` on `Slice:` commit trailers; neither proves a pass converged |
| E2E, Python | `tests/e2e/`, two scenarios | nothing; both scenarios call the app in process, not over a socket |
| E2E, frontend | eslint and the type check | nothing; neither frontend has a test runner, so zero tests pass the gate |
| Actual responses | an empty `evals/` | nothing |
| SDD | `docs/specs/` | nothing; project-jarvis has requirement ids and a traceability check, keel has neither |
| Test generation | none | none |

**The boundary with project-jarvis.** keel judges one commit from its files
alone and keeps no history. jarvis keeps the ledger across runs and repositories
and starts the agents and workflows. A rule that can be judged from the files is
a keel check that jarvis reads; a feature that needs history, a schedule or a
database is jarvis's. jarvis monitors keel's own development by tracking keel as
one of its projects, not by keel carrying the spine.

**Cap.** Eight slices, each one commit on a green `make verify`, in this order.
The two documentation slices, S1 and S3, were added at the maintainer's request
to audit documentation before Campaign 4's enforcement work. The maintainer
chose to insert S2 to fix a defect a downstream project hit updating to 0.2.1,
to be released as 0.2.2.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-4.S1 | A newcomer cannot learn what keel offers, its limits, or how to adopt and upgrade it from docs that cannot silently drift | done — `make verify` green (1771 passed); 11 of 12 review findings confirmed and fixed |
| CMP-4.S2 | An update whose config/project.json holds a merge conflict stops with a JSON error from the first migration, and no later migration runs | done — `make verify` green (1822 passed); 3 of 4 review findings confirmed and fixed |
| CMP-4.S3 | No catalogue lists every feature and no reference lists every setting, so a newcomer cannot see what exists or how to configure it | done — `make verify` green (1841 passed); 10 of 10 review findings confirmed and fixed |
| CMP-4.S4 | `make verify` reports only an exit code and log text, so nothing outside the repo can read which gate ran, on which commit, with what result | done — `make verify` green (1906 passed); 6 of 6 review findings confirmed and fixed (two reviewers found the same defect) |
| CMP-4.S5 | A frontend has no test runner, so it ships with zero tests and the gate is green | done — `make verify` green (1924 passed); 6 of 7 review findings confirmed and fixed |
| CMP-4.S6 | The e2e scenarios call the app in process, and nothing checks that a route has a scenario | done — `make verify` green (1973 passed); 4 of 5 review findings confirmed and fixed |
| CMP-4.S7 | Nothing calls a real model or a running server and judges what comes back | done — `make verify` green (2149 passed); 5 of 5 review findings confirmed and fixed |
| CMP-4.S8 | A spec's requirements are not tied to tests, so an uncovered requirement passes the gate | done — `make verify` green (2465 passed); 13 of 13 review findings confirmed and fixed |

- **CMP-4.S1, documentation truth.** Every stale claim the documentation audit
  verified is fixed in place, and a drift test refuses a shipped document that
  names a slice id, a host-specific phrase, an undeclared loopback port, or a
  document the template never ships. The README is reworked for a newcomer.
- **CMP-4.S2, a conflicted manifest stops an update by name, and the update
  can be finished.** Every copier job refuses over a conflict hunk in a fixed
  project file its modules declare reading, naming the file, the line and the
  command that finishes the update; `scripts/jobs/finish_update.py` is that
  command, replaying the after-migrations copier never reached. The
  downstream update is replayed end to end in a template-only test, and the
  finish command's `--dry-run` is checked against the migrations copier runs.
  Review found the guard's union over a job's imports refused the restamp
  over files only check_structure reads (a conflicted Makefile stopped the
  last migration); the restamp no longer imports check_structure, and a test
  fails a job whose imports hold a reading module it takes only constants
  from.
- **CMP-4.S3, the feature catalogue and settings reference.**
  `docs/reference/features.md` lists every feature and
  `docs/reference/settings.md` every setting, each held to the tree by a drift
  test.
- **CMP-4.S4, the evidence contract.** `make verify` writes a canonical JSON
  record next to its exit: commit, gate targets run, per-target result, test
  counts, check letters and their findings. It is written under an ignored path
  and is byte-identical on a second run of the same commit. The schema is typed
  and versioned, and a test holds the record to it. This is the format
  project-jarvis ingests; the ingest itself is jarvis work.
- **CMP-4.S5, frontend tests.** Each shipped stack gets a unit runner (Vitest)
  and a browser journey (Playwright, run headless against the built site),
  wired into the gate behind the existing `node_modules` skip. A stack with a
  runner and zero tests fails the gate.
- **CMP-4.S6, Python e2e over a socket.** One scenario starts the real server on
  a free loopback port, drives it over HTTP and stops it. A check fails when a
  route or transport endpoint has no scenario naming it (CONVENTIONS §17).
- **CMP-4.S7, evals that judge actual responses.** A dataset format, a scorer
  and a threshold gate in `evals/`. The default mode replays recorded responses,
  so `make verify` needs no network and no credential; a `[cost]` target runs it
  live through `models/` and the `child_env` allowlist.
- **CMP-4.S8, spec-to-test traceability.** A generic requirement-id grammar and
  a check that every requirement in `docs/specs/` is named by a test or by a
  documented gap, lifted from project-jarvis's `scripts/traceability_matrix.py`.
  jarvis's own copy is then retired in favour of keel's on update; that is a
  jarvis change and needs the maintainer's yes. The live status of each
  requirement stays in jarvis's ledger.
  The maintainer narrowed S8 to requirement-level coverage, with ids ready for
  acceptance criteria. An id is `<requirement-id>` or
  `<requirement-id>#AC-<n>`, where `n` is a positive integer with no leading
  zero. A spec defines a criterion with a line `- AC-<n>: <text>`. A bare id does
  not cover a requirement that has numbered criteria: each criterion needs its
  own test marker or a gap row. Which prefixes name a requirement comes from a
  `traceability.id_prefixes` registry in config/project.json; an unlisted
  prefix fails closed and the longest prefix wins. keel copies the registry's
  key and family list from project-jarvis, which lands it first. A test file
  names a requirement and is never itself evidence that the requirement is
  built, and each requirement gets exactly one verdict. Coverage
  statuses, a requirement hierarchy and mutation evidence are out of S8.

**Queued for Campaign 5.**
- `make new-test MODULE=` writes a mirror test that fails until it is filled in.
- Proof that a test can fail: mutation testing over changed code.
- The vault backlog: KEEL-FE-2, then FE-1, then FE-6; FE-3; TEST-1 (no test
  touches a live store); SEC-1 (secrets scan).
- The agent and playbook contract, the seed of keel-lite: a design document
  and an ADR before any code.
- project-jarvis side, in jarvis's repository: register keel as a tracked
  project and ingest CMP-4.S4's record and the `Slice:` trailers.
- The D0 decisions the documentation audit left open: each dead key is wired
  or deleted; the manifest defaults (`runtimes.default`, `models.default`)
  drive the registries or stay declarative; the example TOMLs are labelled as
  patterns or get a loader; each gate that passes on a skip fails closed or
  stays a stated skip; check_D's scope, and whether it takes a waiver.
- `make new` is not refused in a generated project, where it has no template
  to copy.
- Every installed value comes from config, and a doc states it beside its
  key: the REST port the Makefile `run-api` and `run-web` recipes spell out,
  the Astro proxy fallback, and the registry defaults move into
  `config/project.json`; a drift test reds a reference default with no source.
- Left by CMP-4.S5. A frontend suite whose tests are all skipped exits 0,
  because neither runner reports a count the gate reads. CI runs no
  `test-fe`. Whether a missing browser stays red, rather than a stated skip, is
  the maintainer's call. react-vite ships no lockfile, so its resolved versions
  float within its ranges. A copier copy from a dirty tree also copies
  untracked files, such as a stray symlink at the repo root, into the
  generated project.
- Left by CMP-4.S6. A generated project with the `grpc` transport ships
  `grpc /thing.v1.ThingService/CreateThing` in `e2e.exempt`, because no gate
  generates the gRPC stubs or installs `grpcio`; a gate that does both, a
  scenario that calls the method, and deleting the exemption close it. A
  test run killed by SIGKILL still orphans its uvicorn server, because only
  SIGTERM and SIGHUP are caught and nothing asks the kernel to end the server
  with its parent.
- Lane and gate tooling ships from keel: clone the commit, run the gate
  through a neutral batch-scheduler adapter (local by default; the farm's
  submit command and limits in config), and merge fast-forward only on a
  green gate of that exact commit, off unless a project turns it on.
- conflict_guard precision (a union over the import closure); finish_update
  gaps (StrictUndefined, `_jinja_extensions`, private-remote credentials); a
  conflicted entry module or conflict_guard itself still tracebacks.
- Left by CMP-4.S7. The shipped recordings are hand-authored
  (`recorded.source: authored`); no model output is recorded until the
  maintainer approves a first paid `make eval-live` run and promotes its
  candidates by hand. One threshold, `evals.threshold`, governs replay and
  live; a separate live threshold has no consumer until that run. A
  JSON-Schema scorer and a model-as-judge scorer are not built. A refused `evals.report_dir`
  cannot be given a red placeholder report, so an earlier report can stand
  beside a red gate.
- Left by CMP-4.S8. A requirement heading with a colon after its id
  (`## REQ-0001: Title`) is refused with exit 2; whether the one parser takes
  an optional colon is the maintainer's call. `make trace` reads what pytest
  collects from source, so `collect_ignore`, `--ignore` and a collection hook
  are seen only by the comparison in `make test`. A refused `traceability`
  block leaves an earlier matrix standing, because the command cannot know
  the matrix path. `docs/specs/example-feature.md` arrives on `copier update`
  and reds `make trace` in a project that deleted the example test.
  project-jarvis holds its own `traceability` block with a `kind_evidence`
  key this loader refuses, so sharing one registry waits for a mapping
  decision. `scripts/gate_evidence.py` writes under `evidence.dir` without the
  symlink check `scripts/git_tree.py` now holds, and `scripts/run_evals.py`
  takes its `--help` text from the wrong docstring line. The mutation proof is
  hand-written mutants, not a mutation runner.
- The maintainer's coding rules get a kernel and checks, in this order: one
  config loader every value comes through (a default applies only when a key
  is not set and prints one `[using default]` line naming the key and the
  config file; a key that is set and wrong fails; a secret, a host or a
  live-store path has no default); one exit helper with a closed list of
  codes and a table held equal to it; checks for what a helper cannot carry
  (text matching as a last resort with a stated reason, the import boundary,
  a bare `except`, a comment that reports a change); typed inputs read once
  at the edge and a log helper that writes fields. The existing pattern
  matches are listed in config and that list may only shrink.
- Proposed by project-jarvis from its own lanes and reviews. A write path
  never migrates a store: it refuses one below the current schema and names
  the migrate step, and a test holds the store's bytes unchanged on every
  refused or failed write. Every list of guarded things has a test that fails
  when an entry is removed. A module docstring's claim about behaviour is
  asserted by a named test. Every persisted field is a closed list, an open
  list or a validated format. A grammar with one home is imported, never
  copied. Time bounds in tests take their load margin from config. A
  git-ignored config the gate needs ships as an example, and the gate's first
  step names the copy command. A tool resolves lane placeholders at land and
  merges the changelog and the ledger without conflict (with the lane and gate
  tooling above). The template `.gitignore` covers the directory a browser
  automation server leaves at the repo root.

