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
updated: 2026-10-11
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
make verify   # check-all + lint + typecheck + test + test-fe   (the full bar)
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

Run the *smallest sufficient* target often (a focused `pytest -m unit -k name`),
and the full `make verify` before declaring a task complete. A loop that advances
on the model's claim of success rather than a real exit code is unsafe — gate on
the exit code, always (see the deterministic-checks catalogue:
[deterministic-checks.md](deterministic-checks.md)).

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
browser is downloaded under the gate. An app without `node_modules` skips both
suites, as `make lint-fe` does.
`tests/integration/test_gate_scope.py` holds every app to both scripts, both
configs and a file in each suite. These suites are not for the backend: its
routes and transport endpoints are `tests/e2e/` scenarios.

## Stop conditions & caps at a glance

| Loop | One pass does | Stops when |
| --- | --- | --- |
| TDD | red → green → refactor for one behavior | the behavior is covered and the suite is green |
| Convergence | the next single unit + `make verify` + commit | done-condition holds, or the pass cap is hit |
| E2E | adds/extends one scenario through the public surface | the flow is exercised end to end and green |

## See also

- Root [`AGENT.md`](../../AGENT.md) and [`CONVENTIONS.md`](../../CONVENTIONS.md) §17 — the rules in imperative form.
- [agent-runtimes.md](agent-runtimes.md) — the executable analog: a loop as a `Plan` on a `Runtime`.
- [deterministic-checks.md](deterministic-checks.md) — what each gate proves (and doesn't).
- [`tests/AGENT.md`](../../tests/AGENT.md) — the test-mirror and tier rules these loops rely on.
