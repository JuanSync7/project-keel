---
title: Tests
kind: tests
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: Unit tests mirror src/; integration/e2e/smoke go by scenario.
id: tests-readme
created: 2026-06-17
updated: 2026-10-09
visibility: internal
canonical: true
---

# Tests

Unit tests mirror src/; integration/e2e/smoke go by scenario.

| Subdir | Mirrors `src/`? | Organize by |
|--------|-----------------|-------------|
| `unit/` | **Yes, 1:1** | source module |
| `integration/` | No | scenario (2+ real components) |
| `e2e/` | No | user journey |
| `smoke/` | No | liveness check |

`fixtures/` holds shared data; `conftest.py` holds shared pytest
fixtures. Markers (`unit`/`integration`/`e2e`/`smoke`) are declared
in `pyproject.toml` — select with `pytest -m`.

## A run in which zero tests ran fails

pytest itself exits 5 only when it collects nothing; a run whose every selected
test skipped exits 0 having executed no assertion. `conftest.py` counts the
tests that ran (passed, failed, or xfail) and, when the session ends,
`selection_guard.py` turns a run of zero into exit 5 with a message naming the
selection. That covers every `make` tier and a direct `pytest` call alike, so a
single file run alone whose tests all skip now exits 5 too.

The one exemption is a bare `-m <marker>` selection declared in
config/project.json `make_targets.empty_test_selections` with a reason: that
run exits 0 and prints the reason. A compound `-m` expression, the whole
suite, and a run narrowed by `-k` or an explicit path are never exempt, and the
message names that selection as given (`-m smoke -k name tests/x.py`), never as
the whole suite. Once a test of a declared marker runs, the declaration is
stale and the run exits 1 until it is removed. `--collect-only`,
`--setup-plan` and `--setup-only` (which execute no test by design), a run
that already failed, and an xdist worker are left alone.

## A copied Makefile carries its includes

A test that runs make in a scratch copy of a project copies the root Makefile
with `makefile_copy.copy_makefiles`, never alone. It copies every makefile
`scripts/check_structure.py` `walk_makefiles` says make reads (an area's
`<area>.mk`, any `include`), each at its own path, because a generated project
that adds an area otherwise fails a correct test with `No such file or
directory`. It raises, naming the include, only where a copy would differ
from the source in a way it can see: a required include named through a
variable or wildcard, an optional wildcard that matches a file, or a path
leaving the root. An include the gate only WARNs about otherwise stays as make
sees it: an absent `-include`, an optional include named through a variable,
and a required include naming no file (behind a false conditional or not) are
left out, so make gives the copy the verdict it gives the source. It copies makefiles only: the scripts and config a recipe needs are
the calling test's to copy. `tests/integration/test_makefile_copy.py` proves
each case and that a second copy changes nothing.

## A test reads the project's own facts

A test that runs in keel and in every generated project reads a list from the
project's config, never keel's value of it: the ADR files from the
config/project.json `adr` block, the credential opt-ins from
`child_env.credentialed_values`. `tests/unit/scripts/test_check_y.py` and
`tests/unit/scripts/test_child_env.py` each run their check once on keel's tree
and once on a fixture that adds what a project adds, so an assertion that only
keel's facts satisfy goes red in keel too.
