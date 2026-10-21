---
title: Development loops (TDD, bounded convergence, end-to-end coverage)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [tdd, bounded-convergence, ralph-loop, testing, e2e, workflow, agents, guide]
summary: The default working loops any human or LLM follows in this repo — test-first, bounded convergence, and end-to-end coverage — all gated by `make verify`.
id: docs-guides-dev-loops
created: 2026-06-22
updated: 2026-10-21
visibility: internal
canonical: true
---

# Development loops

Code in this repo is produced by **bounded, gated loops**, not one-shot edits.
Any agent working here follows them by default — the imperative form lives in the
root [`AGENT.md`](../../AGENT.md) and [`CONVENTIONS.md`](../../CONVENTIONS.md) §17,
so an LLM reads the rules before it touches a file and doesn't need them
re-explained each session.

These are disciplines for *how you work*. Their **executable analog** — a loop a
program runs unattended — is a `Plan` on a `Runtime` (see
[agent-runtimes.md](agent-runtimes.md); `agents/index_enforcer/` already ships a
durable, resumable fill-loop). Same shape, two homes: here it governs the
human+LLM dev cycle; there it is data a machine executes.

## The gate is the judge

Every loop below ends each pass at the **same gate**, and "done" means the gate is
green — never a self-assessment:

```
make verify   # check-all + secret-scan + lint + typecheck + test + trace + eval + test-fe   (the full bar)
make test     # plain pytest over the whole suite (tiers: unit · integration · e2e · smoke)
make check    # fast, 3.6-safe structural gate (runs in pre-commit)
```

`make verify` also writes its verdict to `.evidence/verify.json` (config/project.json
`evidence.dir`), and the record's `source.commit` names the commit that verdict
belongs to (`docs/guides/deterministic-checks.md`, "The gate's evidence record").

A test tier fails when zero tests ran, skips included: `tests/conftest.py` counts
the tests that ran and `tests/selection_guard.py` turns a run of zero into exit 5,
unless the tier's one `-m` marker is declared in config/project.json
`make_targets.empty_test_selections` with a reason. The declaration covers only
that bare `-m <marker>` run: narrowed by `-k` or a path it exits 5, and the
message names the selection as given. So a green tier always
executed at least one assertion.

A test reaches the network, the disk and the stores only as its tier allows.
`tests/isolation_guard.py`, which `tests/conftest.py` installs as a Python audit
hook, judges each test's setup, call and teardown on three axes against the row
of config/project.json `tests.isolation.tiers` its closest tier marker names:
`network` (`none`, `loopback`, `any`), `writes` (`temp`, `any`) and `stores`
(`temp`, `any`). A test with no tier marker gets the strictest value on every
axis. A reach outside the rule fails the test with a line naming the test, the
phase, the tier, the event and its target, even when the test caught the error.
Fix it in this order: write scratch to `tmp_path`; reach a live store
`tests.isolation.stores` lists through the `store_copy` fixture, which copies it
with its sqlite siblings into the test's own directory; move the test to the
tier that allows the reach; and only then give it a reason in
`tests.isolation.exempt` under its axis and node id. An exemption whose test ran
and reached nothing on that axis fails the run, so an exemption cannot outlive
its reason. The guard is defence-in-depth, not a sandbox: it does not see a
child process, a C extension's own file or socket calls, a FIFO or device node,
or the directory an `os.open` with a relative path and a `dir_fd` lands in, and
it does not judge a name lookup, by choice, because the connect that follows is
judged (`docs/adr/keel/K-0024-what-a-test-may-reach.md`).

Test scratch lives in memory when the host can hold it. `tests/conftest.py`
takes the first root of three that applies: `KEEL_TEST_SCRATCH` when it is set; else `tests.memory_scratch_root` with `-<uid>` appended, when its parent exists, its file system has `tests.memory_scratch_min_free_mb` megabytes free, and the directory is this user's with mode 0700; else `tests.scratch_root`. It points
tempfile, `TMPDIR` and pytest's basetemp there before any test module is
imported, and pytest's `scratch:` header line, which `-q` hides, names the root and why memory was
passed over. It refuses, before any test runs, a root that is relative or sits
under the system temporary directory or inside the checkout. A root that holds the checkout is accepted,
and the checkout stays outside it. A passed test's directory is removed and a
failed one's is kept, named after the test (`pyproject.toml`
`tmp_path_retention_policy`). A test that starts a child process gives it the
seconds `tests.child_timeout_seconds` names.

Run the *smallest sufficient* target often (a focused `pytest -m unit -k name`),
and the full `make verify` before declaring a task complete. A loop that advances
on the model's claim of success rather than a real exit code is unsafe — gate on
the exit code, always (see the deterministic-checks catalogue:
[deterministic-checks.md](deterministic-checks.md)).

On a host other people share, start the full gate through the launcher:
`python3 scripts/launch.py -- make verify`. It prints one line saying where the
command runs and why, then runs it here, here at a lower CPU priority
(config/project.json `launcher.limited.niceness`), or on the farm
`launcher.farm.adapter` names, and passes the gate's own exit status through.
The shipped adapter is `none`, so on a shared host a long script runs here at
the lower priority until a project names a farm. `--dry-run` prints the line and
runs nothing. Exit 12 (`NO_CAPACITY`) means the farm did not start the command
in time and this host was busy, so nothing ran; it is not the gate's verdict.
The launcher records each run's seconds, and `make long-scripts` proposes the
scripts that took longer than `launcher.long_after_seconds` and are not yet
listed (`CONVENTIONS.md` §7, "Where a long script runs").

## Slice work vertically

The tree is layered (`app → {frontend, backend} → shared`, with transports,
agents, and runtimes at the edges), but **build across the layers in vertical
slices**, not layer-by-layer. A slice is one capability taken end-to-end — its
data, domain logic, transport, and UI together — small enough to finish and
verify on its own.

Why slice this way:

- Each slice is **independently shippable and verifiable** — it passes
  `make verify` by itself and carries its own test, so you get working software
  early.
- It avoids big-bang integration risk: layer-by-layer ("all the backend, then
  all the frontend") leaves nothing working until the last layer lands.
- It is the natural unit for the loops below — one slice = one TDD cycle (plus an
  e2e scenario if user-facing) = one pass of the convergence loop.

Slicing by layer or dimension is the right move for a **read-only review or
research sweep** (each worker is a lens, not a deliverable) — but not for
building functionality.

### Naming the slice you are on

A slice has one name, `CMP-<n>.S<m>`: slice `m` of campaign `n`, declared as a
row of a plan doc's slice table (§20). Write the row before the first commit
that names it, because `check_Z` reports a mention that no row declares and the
trailer test reports a trailer that none declares. A pass of the convergence
loop below is counted against its cap, not named: the slice it works on is the
name.

The commit that delivers the slice ends with a `Slice:` trailer in its last
paragraph, beside `Co-Authored-By:`. An optional `Backlog:` trailer names the
backlog item the slice closes:

```text
feat(naming): campaigns and slices carry one checked name

check_Z judges the plan docs and the trailer test judges commits.

Slice: CMP-2.S4
Backlog: KEEL-42
Co-Authored-By: A Contributor <contributor@example.com>
```

`tests/integration/test_work_trailers.py` judges the trailers. Another
repository's slice is named with its `config/project.json` `name` as a prefix,
such as `project_jarvis:CMP-2.S1`; this repository does not judge that id.

## TDD loop — red → green → refactor

Drive new or changed `src/` behavior from its test:

1. **Red** — write or extend the mirror unit test
   (`src/<pkg>/<mod>.py` → `tests/unit/<pkg>/test_<mod>.py`, see
   [`tests/AGENT.md`](../../tests/AGENT.md)) until it **fails for the right
   reason**. The failure proves the test can detect the behavior's absence.
2. **Green** — write the smallest change that makes it pass. Resist building more
   than the test demands.
3. **Refactor** — clean up with the suite green; the passing tests are your
   safety net.

Test through the package's public API (`__init__`), not its `_*` internals —
tests are callers too. A public symbol with no test is unfinished. For an
exploratory spike you may defer the test, but the bar must be green before you
commit.

> **Honesty caveat.** No structural check today verifies the test mirror — not
> that the test file exists, not that it was written first, not that it exercises
> the code. TDD here is a discipline you follow, gated only indirectly by
> `make verify` (a red suite fails the gate) and complemented by coverage and
> review — never a checkbox labelled "TDD". A future test-mirror *existence* gate
> could prove the file is present and named right; it still couldn't prove
> red-before-green.

## Bounded convergence loop ("Ralph")

"Ralph" names a technique, not a tool: for a change too large for one edit — it
spans more than one file, or can't be finished and verified in a single pass —
converge by repetition instead of trying to do it all at once.

1. Write the plan down (a checklist, a `test-docs/` entry, or an issue) with an
   explicit **done-condition** and a **pass cap** (max iterations; default to 5
   if nothing else sets it).
2. Each pass: re-read the plan, **re-derive the worklist from the repo**
   (search before assuming something is unbuilt), do the **next vertical slice**,
   run `make verify`, and commit.
3. Stop when the done-condition holds — or at the pass cap. At the cap, **stop and
   report** what's done vs. what remains; don't silently start another pass.

Why these guardrails:

- **Re-derive each pass** so progress lives in the tree and the commits, not in
  one ever-growing context. Push heavy reads to subagents to keep the working
  context fresh — this is what stops the loop from drifting or rebuilding work it
  already did.
- **Pass cap** so a loop that isn't converging stops and asks, instead of
  spinning. (The `runtimes/` engine has only a global `_MAX_STEPS` *safety-abort*;
  a clean bounded exit is a per-loop counter you own.)
- **Commit each pass** so a bad iteration is isolated and revertible.
- **Gate through the read-only runner.** A loop that runs its own gate calls
  `scripts/run_make_target.py <target>`, not `make` directly. The runner runs a
  target only when its effect label is inside `config/project.json`
  `make_targets.gate_effects` (`[local]` and `[read]` in keel), sets `RALPH=1`
  last so a `[write]` recipe's `$(WRITE_GUARD)` refuses, and fails a green run
  that changed what git sees. `make verify` is `[local]`, so it is a legal gate;
  `make fmt` is `[tree]`, so it is refused before it can rewrite the code the
  pass is about to commit (CONVENTIONS §7).

When you want this loop to run unattended (a program, not you, driving it), encode
it as a durable `Plan` and let a `Runtime` checkpoint and resume it — see
[agent-runtimes.md](agent-runtimes.md). A true fresh-context-per-pass run is the
`scripts/` entrypoint re-invoked per iteration (a new process), not one long
conversation; keep that restart in the trigger/driver layer, never in the Plan.

## End-to-end coverage

A new **user-facing flow** — a route, a page, or a transport endpoint — gets a
`tests/e2e/` scenario that drives it through its public surface (and, if it's a
user journey worth documenting, a `test-docs/` plan entry). The scenario must
drive the real entrypoint and **assert on the user-visible result**, not just
import it. Don't defer it:
author the e2e scenario alongside the change, so the flow is covered the moment it
ships. Name e2e/integration/smoke tests by the **scenario**, not by a source file
(only `tests/unit/` mirrors `src/` 1:1).

`make test` holds every backend endpoint to a scenario:
`tests/integration/test_e2e_coverage.py` fails when an endpoint an enabled
transport serves is named by no scenario. A scenario names one with
`@pytest.mark.endpoint("<transport> <id>")`, the id spelled per transport:
`rest GET /health`, `mcp keel-wiki-qa/wiki_answer`,
`grpc /thing.v1.ThingService/CreateThing`. The gate derives the endpoints from
the code, as config/project.json `e2e.sources` says per transport: `openapi`
runs the REST app's exporter (`e2e.openapi_exporter`) and reads its
OpenAPI document, after a child walks every route the app serves and fails
one the document cannot list (anything but an API route in the schema, bar
the documentation routes the app's own settings name), `mcp-stdio` asks each `__main__`-guarded MCP server for
`tools/list` over its stdio, `proto` reads each `.proto` service's `rpc`
lines, and `none` declares a transport with no endpoint of its own. Each
child a derivation or a scenario starts is killed after `e2e.list_timeout_s`
(`30`) seconds. A REST scenario takes the `rest_server` fixture of
`tests/e2e/conftest.py`, which starts the real app under uvicorn on
`e2e.server.host` (`127.0.0.1`) at a port the OS picks, so there is no port
key and two runs never collide. It is ready when `e2e.server.probe_path`
(`/health`) answers 200 within `e2e.server.ready_timeout_s` (`30`), polled
every `e2e.server.probe_interval_s` (`0.1`); each request is bounded by
`e2e.server.request_timeout_s` (`30`); and its process group gets SIGTERM, then
SIGKILL after `e2e.server.stop_timeout_s` (`10`), even when the scenario
fails, and when SIGTERM or SIGHUP ends the test run itself. An MCP scenario takes `mcp_session`, which speaks JSON-RPC to the real
server over its stdio with `e2e.mcp_env` added to its environment. A marker
counts only on a test pytest collects or in a `pytestmark`; one anywhere
else is red. An endpoint
no scenario can reach yet goes in `e2e.exempt` with the reason; an entry that
names no endpoint, that a scenario makes redundant, or whose reason is blank is
red. The gate checks that a scenario names each endpoint, not that it asserts
something meaningful, and `make run-api`'s fixed port is a separate value from
any of these.

A project with a frontend also gives each app under `src/frontend/` two suites
of its own, and `make verify` runs both as its `test-fe` goal (`make test-fe`).
The **unit runner** is the app's npm script `test:unit` (Vitest in the shipped
stacks) over `src/**/*.test.ts` (`*.test.tsx` too in react-vite); it fails on
zero tests, because its config sets `passWithNoTests: false`, and on a focused
test (`.only`), because it sets `allowOnly: false`; the journey's config sets
`forbidOnly: true` for the same reason. The **browser journey** is the app's npm script `test:e2e` (Playwright in the shipped
stacks) over `e2e/*.spec.ts`: it builds the site, serves it with the stack's
own preview server and drives it in headless chromium, asserting what a
visitor sees. Each journey config reads config/project.json
`layers.frontend.journey`: `host` (`127.0.0.1`), `port` (`4391`),
`server_timeout_ms` (`120000`) and `browser_executable` (`null`, the runner's
own browser cache, at `PLAYWRIGHT_BROWSERS_PATH` when that is set, which
config/project.json `child_env.names` passes to each `make verify` goal). No
browser is downloaded under the gate: `make fe-browsers` downloads it, through
each app's npm script `test:e2e:browsers`. Neither suite skips. With a frontend
app present, a missing `npm` or an app without `node_modules` ends the suite
with exit 2, naming the app and `make fe-install`, because a suite that ran
nothing must not pass; only a project with no frontend app runs them silently.
CI runs `make fe-install`, `make fe-browsers` and then `make test-fe`.
`tests/integration/test_gate_scope.py` holds every app to both scripts, both
configs and a file in each suite. These suites are not for the backend: its
routes and transport endpoints are `tests/e2e/` scenarios.

## Requirement traceability

A requirement a spec states is named by a test, or it is a documented gap.
`make verify` runs `make trace` as a goal, and `make trace` runs
`scripts/trace_requirements.py`. The command reads every `kind: spec` document
under config/project.json `traceability.specs_root` (`docs/specs`) and every
test file pytest collects under `traceability.tests_root` (`tests`), entering
no directory pytest's `norecursedirs` skips.
[`docs/specs/README.md`](../specs/README.md) gives the grammar of an id and of
a criterion line.

One pass for a new requirement:

1. Write the requirement as a heading in a spec, with a `- AC-<n>: <text>`
   line per acceptance criterion. `make trace` exits 1 and names each
   `uncovered` unit.
2. Write the failing test and mark it with the unit's id:
   `@pytest.mark.req("REQ-0001#AC-1")`. The marker name is
   `traceability.marker` (`req`), and its arguments are string literals.
3. Make the test pass. `make trace` exits 0 once every unit is `covered`.

A requirement with numbered criteria is covered criterion by criterion: a
marker that names the bare requirement id covers none of them. A unit no test
can name yet goes in `traceability.gaps`, keyed by its id, with the reason. A
gap row whose id does not parse, names nothing a spec defines or names a unit
a test already covers is a finding (exit 1); a blank reason is refused
(exit 2). A marker that names an undefined or malformed id, that pytest reads
on no collected test, or whose arguments are not string literals is a finding.
`tests/integration/test_requirement_traceability.py` also asks pytest's own
collection which test carries which id, and fails when the reader disagrees.

A project with no requirement yet states why in
`traceability.no_requirements` (`null` as shipped, since the template ships a
spec). Zero requirements under `null` is a finding, and so is a reason left in
place once a requirement or a marker exists.

The command writes one file, `traceability.matrix_path`
(`.evidence/traceability/matrix.json`): every requirement, its units, each
unit's verdict and the tests that name it.
`tests/integration/test_requirement_traceability.py` judges the same tree
inside `make test`, so a run of the suite alone still fails an uncovered
requirement. The gate reads marker calls from source and imports no test: it
checks that a test names a requirement, not that the test asserts what the
requirement says.

## The prompt-change loop (evals)

A change to a prompt an eval case drives (a doer in `evals/_doers.py`, such as
`agents/triage`) makes `make eval` fail with `stale-recording`. The recorded
answer was given to the old prompt, so replay no longer judges it, and the
stale case's detail names the new prompt hash. One pass:

1. Change the prompt. `make eval` exits 1 and names each stale case.
2. Set three config/project.json keys, then run `make eval-live`.
   `evals.live.model` names a model from `models.list_models()`; its default
   `null` refuses the run (exit 2). `evals.live.model_options` holds that
   adapter's keyword arguments (`{}`). `evals.live.max_calls` must be at least
   the case count; its default `0` refuses the run before any call (exit 2), so
   raising it is the spend approval.
3. Promote by hand: copy each candidate line from
   `.evidence/evals/live-candidates/<suite>.jsonl` over its case line in
   `evals/datasets/<suite>.jsonl`, and review the one-line diff.
4. Run `make eval`. The loop stops when it exits 0.

`evals/README_run.md` gives each step in full.

## Stop conditions & caps at a glance

| Loop | One pass does | Stops when |
| --- | --- | --- |
| TDD | red → green → refactor for one behavior | the behavior is covered and the suite is green |
| Convergence | the next single unit + `make verify` + commit | done-condition holds, or the pass cap is hit |
| E2E | adds/extends one scenario through the public surface | the flow is exercised end to end and green |
| Requirement traceability | one requirement: its spec heading, its criteria, a marked test per unit | `make trace` exits 0: every unit is `covered` or a `traceability.gaps` row with a reason |
| Live eval spend | one `make eval-live` run: one model call per case | `evals.live.model` is `null` (its default), or `evals.live.max_calls` (`0`) is below the case count: refused before any call (exit 2) |

## See also

- Root [`AGENT.md`](../../AGENT.md) and [`CONVENTIONS.md`](../../CONVENTIONS.md) §17 — the rules in imperative form.
- [agent-runtimes.md](agent-runtimes.md) — the executable analog: a loop as a `Plan` on a `Runtime`.
- [deterministic-checks.md](deterministic-checks.md) — what each gate proves (and doesn't).
- [`tests/AGENT.md`](../../tests/AGENT.md) — the test-mirror and tier rules these loops rely on.
