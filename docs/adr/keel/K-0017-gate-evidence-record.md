---
title: "ADR-K-0017: make verify writes a derived, typed evidence record through a driver in its recipe"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, gate, evidence, verify, idempotency]
summary: "make verify runs its goals through scripts/gate_evidence.py on its one recipe line, and the driver writes one canonical JSON record per gate to config/project.json evidence.dir. The record follows a JSON Schema that alone owns the version. The Makefile owns the list of goals. Test counts come from pytest's own junit report, and check findings from check_structure.run_checks in process. The record keeps no history, is not signed, and the goals run in sequence."
id: docs-adr-0017-gate-evidence-record
created: 2026-10-10
updated: 2026-10-10
visibility: internal
canonical: true
---

# ADR-K-0017: make verify writes a derived, typed evidence record through a driver in its recipe

**Status:** proposed 2026-10-10.

## Context

`make verify` reported only an exit code and log text. Nothing outside the
repository could read which gate ran, on which commit, with what result,
without scraping the log. project-jarvis needs a file it can ingest. That
file must be readable, typed, versioned and byte-identical on a rerun of the
same tree. It must also never make the gate greener: a red run must never
leave a green record standing.

## Decision

1. **A driver in the recipe, not a writer after the prerequisites.** `verify`
   has no prerequisites. Its one recipe line is
   `$(PY) scripts/gate_evidence.py --gate $@ -- $(MAKE) check-all lint typecheck test`.
   make stops at the first failed prerequisite and never runs the recipe, so
   a writer placed after the prerequisites could not record a red run, and
   the previous green record would stand. The driver runs each goal itself.
   It writes a red `incomplete` placeholder before the first goal, and it
   passes a failing goal's code through. `scripts/gate_evidence.py` stays
   3.6-safe and stdlib-only, so a `PY` older than `requires-python` still
   replaces the record with a red one.
2. **The schema owns the version.** `config/evidence/gate-record.schema.json`
   (config/project.json `evidence.schema`) states `schema_version` as a
   `const`. The driver reads the version from there, and config/project.json
   holds only `evidence.dir` and `evidence.schema`. A version kept in config
   would be a second owner: a project could bump it without changing the
   format, or change the format without bumping it.
3. **The Makefile owns the goal list.** The goals are the words on the
   recipe's `$(MAKE)` line. check_W already closes `verify`'s effect label
   over that line. `scripts/check_structure.py` `_scripts_reachable_from` now
   follows it too, so the limits guide's exit-code table still covers every
   gate script. A list in config would be a second truth needing an equality
   check.
4. **Test counts come from junit, not from a conftest hook.** The `test`
   recipe passes `--junitxml=$(JUNIT_XML)` only when the driver sets that make
   variable. The driver counts each `<testcase>` once and never reads the
   suite totals. A hook would add a second writer inside every pytest
   process, including the nested runs under `tests/`.
5. **Check findings come from `run_checks` in process, not from a `--json`
   mode.** `scripts/check_structure.py` `run_checks` is the one owner of the
   check list. The driver calls it and strips the repository root from each
   message, so no new output format needs keeping in step.

## Consequences

- The record lives in an ignored directory, and the driver refuses with exit
  2 a record path git would list. So `verify` stays `[local]`, and
  `scripts/run_make_target.py` sees an unchanged tree.
- The goals now get the allowlisted environment of `scripts/child_env.py`
  instead of make's whole environment. `KEEL_REQUIRED_EXTRAS` joins
  `child_env.names`, so a caller who declares a surface required still gets
  a hard failure, not a skip.
- The outer make's flags and command-line variables reach each goal as
  arguments. The driver reads `-n`, `-q` and `-t` as a dry run and `-k` as
  keep-going.
- The gate is stricter than before in four ways. Zero tests is red, and an
  all-skipped suite counts as zero tests. A missing junit report is red. A
  tree that changes during the run is red. A junit report that counts a failed
  or errored test is red even when its goal exited 0, as a test recipe that
  ignores pytest's exit does; under `make -i` the outer make still exits 0, as
  `-i` asks, but the record says red.

## What is deliberately NOT decided here

- **History.** Each run replaces the file whole. The ledger across runs and
  repositories is project-jarvis's, and so is ingesting the record.
- **Signing.** The record is unsigned and sits in a writable directory, so it
  is evidence, not attestation.
- **Parallel goals.** Under `make -j` the driver still runs the goals in
  sequence. It does not pass make's jobserver on.

## Alternatives considered

- **A writer recipe after the four prerequisites.** A red run never reaches
  the recipe, so a stale green record survives it. This was rejected by
  decision 1.
- **`PYTEST_ADDOPTS=--junitxml=...`.** pytest reads that variable in every
  process, and the suite's nested pytest runs copy it from `os.environ`, so
  each would write a report of its own. A make variable reaches only the
  `test` recipe.
- **Reusing `scripts/run_make_target.py` `run_target` for each goal.** That
  module is not 3.6-safe, so verify would fail at an old interpreter before
  writing anything. It also captures a goal's output until the goal ends,
  and the test goal runs for many minutes. Only its definition of what git
  lists is reused: `scripts/git_tree.py` holds it, and both scripts import
  it.
