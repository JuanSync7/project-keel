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
updated: 2026-10-29
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

## What a test may reach

`tests/isolation_guard.py` holds each test to its tier's rule, and
`conftest.py` installs it as a Python audit hook before any test module is
imported. A tier's rule is a row of `config/project.json` `tests.isolation.tiers`,
with a value on each of three axes:

| Axis | Values, strictest first | What it judges |
|------|-------------------------|----------------|
| `network` | `none`, `loopback`, `any` | a socket connect, sendto or sendmsg |
| `writes` | `temp`, `any` | a file, directory or link created, changed or removed, its mode, owner, flags, times or extended attributes changed, or an AF_UNIX socket bound to a path |
| `stores` | `temp`, `any` | a sqlite database opened, and any open of a listed store |

The closest tier marker on a test picks the row; a test with no tier marker
gets the strictest value on every axis. A reach outside the rule raises
`IsolationError` at the reach and fails the test in that phase, even when the
test caught the error, and an `xfail` does not hide it. A test that needs a
live store `tests.isolation.stores` lists asks the `store_copy` fixture for
its own copy, with the store's `-wal`, `-shm` and `-journal` siblings. A reach
a test truly needs gets a reason in `tests.isolation.exempt`, under its axis
and node id; a blank reason stops pytest before any test runs, and an
exemption whose test ran and reached nothing on its axis fails the run.

The guard is defence-in-depth, not a sandbox. It does not see a write or a
socket by a child process, a C extension's own file or socket calls, a FIFO or
device node, or the directory an `os.open` with a relative path and a `dir_fd`
lands in. It does not judge a name lookup, by choice: the connect that follows
is judged. A sqlite name that starts `file:` is judged as a URI and as a file
of that name in the working directory, so a test that opens a `file:` URI
changes directory to `tmp_path` first. `docs/adr/keel/K-0024-what-a-test-may-reach.md` is the decision.

## Where test scratch lives

`conftest.py` points tempfile, `TMPDIR` and pytest's numbered basetemp at
the first root of three that applies: `KEEL_TEST_SCRATCH` when it is set; else `tests.memory_scratch_root` with `-<uid>` appended, when its parent exists, its file system has `tests.memory_scratch_min_free_mb` megabytes free, and the directory is this user's with mode 0700; else `tests.scratch_root`. A nested pytest a test
starts inherits the root through `KEEL_TEST_SCRATCH`. Memory comes first
because test scratch is thrown away within seconds and needs no durability. A
host without the parent, with too little free, with a parent others may
write without the sticky bit, or with a directory that is not this user's
with mode 0700 falls back to disk, and pytest's `scratch:` header line, which `-q` hides, says
which root it took and why. Every root must be absolute and lie neither under
the system temporary directory, which every program shares, nor inside the
checkout, whose tree walkers would read a kept directory; anything else stops
pytest before any test runs. A root that holds the checkout is accepted, and
the checkout stays outside it. A test that starts a child process gives it the
seconds `tests.child_timeout_seconds` names. `pyproject.toml` keeps a failed test's directory,
named after the test, and removes a passed one's.

## `make test` runs on parallel workers

`make test`, and so `make verify`, passes pytest-xdist `-n auto`, and
`conftest.py` answers xdist's count with `tests.workers` (read by
`isolation_guard.py` `worker_count`); 0 runs the suite in one process. A tier
target, a direct `pytest` and a nested session pass no `-n`, so they stay in
one process. Each worker judges its own tests' reaches. The unused-exemption
check needs every test that ran, so a worker hands its record (`usage`) to the
controller when it ends, the controller adds the records up (`merge_usage`)
and judges once; a worker that ended without its record, such as one that
crashed, fails the run naming it, because its tests could not be judged.
`--expiring-tier-record` refuses to run with `-n`: each worker would write its
own share of the record to one path.

A module-scoped fixture runs once on each worker that runs one of the
module's tests, so its cost is paid once per such worker. An exemption is still per node id: a reach a module-scoped
fixture makes is judged in the setup of whichever test on that worker asked
for it first.

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
the calling test's to copy, with `script_copy.copy_with_imports` below.
`tests/integration/test_makefile_copy.py` proves each case and that a second
copy changes nothing.

## A copied script carries its imports

A test that copies scripts or test helpers into a scratch project lists the
files it runs and copies them with `script_copy.copy_with_imports`, never with
its own copy loop. The helper adds every project module a listed Python file
imports, followed to its end, resolved against the importer's own directory,
then `scripts/`, then the repo root, so `from scripts import x` and
`from scripts.x import y` are followed too. When a script starts importing a
new sibling, every copy then still starts; a hand-kept list stops with
`ModuleNotFoundError` in each fixture that copies the script. A listed file
that does not exist raises, naming it. An import of the project that no file
holds raises, naming the importer and the module, instead of being skipped. An
import made through `importlib` or `__import__`, or found through a `sys.path`
entry other than those three, is not seen, so that file stays on the list.
`tests/integration/test_script_copy.py` proves each case, that keel's
`scripts/check_structure.py` carries `scripts/corpus_level.py`, that
`scripts/run_make_target.py` carries `scripts/resource_limits.py` and its copy
starts, that an import cycle reads each file once, and that a second copy
changes nothing.

## A test reads the project's own facts

A test that runs in keel and in every generated project reads a list from the
project's config, never keel's value of it: the ADR files from the
config/project.json `adr` block, the credential opt-ins from
`child_env.credentialed_values`. `tests/unit/scripts/test_check_y.py` and
`tests/unit/scripts/test_child_env.py` each run their check once on keel's tree
and once on a fixture that adds what a project adds, so an assertion that only
keel's facts satisfy goes red in keel too.
