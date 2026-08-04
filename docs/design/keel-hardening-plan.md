---
title: Keel hardening — bounded convergence plan
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, copier, upgrade, gate, environment, convergence]
summary: Five bounded passes that fix the template-as-product defects found by the 2026-08-04 audit and then land the external-environment manifest of ADR-0005. Each pass is one vertical slice with an explicit done-condition, gated on `make verify`.
id: docs-design-keel-hardening-plan
created: 2026-08-04
updated: 2026-08-04
visibility: internal
canonical: true
---

# Keel hardening — bounded convergence plan

## Why

A 2026-08-04 audit generated real projects from the template and ran them. The
conventions engine held up well; the template-as-product did not. The finding
that frames everything below: **keel has never been generated and used by anyone
who did not write it**, so the defects cluster entirely in the downstream
experience — the upgrade channel, the generated project's day one, and the
scope of the gate.

Every defect here was reproduced by running, not by reading. Claims that did not
survive an adversarial re-check were dropped or corrected; the surviving numbers
are recorded with each pass.

## Ground rules (AGENT.md §"Converge in bounded passes")

- One pass = one **vertical slice**, independently verifiable.
- A pass is done when `make verify` exits green — never on self-report.
- Commit per pass. Re-derive the remaining worklist from the repo each pass.
- **Pass cap: 5.** At the cap, report done-vs-remaining rather than continuing.
- Order is deliberate: the upgrade channel is first, because every later pass
  ships a change that descendants must be able to *receive*.

## Passes

### Pass 1 — restore the upgrade channel *(done)*

`copier update` is the entire justification for choosing copier (ADR-0004), and
it is advertised in six places and tested in none.

- **Defect A.** `.gitignore:29-31` ignores `.copier-answers.yml` and ships
  **verbatim** into every generated project (no `.jinja` twin, not in
  `_exclude`). Copier reads the answers file from the working tree, so update
  still works in the directory copier created — but any `git clone`, teammate
  checkout or CI run has no answers file at all and update fails with *"Cannot
  update because cannot obtain old template references."*
- **Defect B.** No version identity: zero git tags, one `## [Unreleased]`
  CHANGELOG heading, no `_min_copier_version:`. Copier prints *"No git tags
  found in template; using HEAD as ref"* and records a bare
  `_commit: <sha>`. Pinning via `--vcs-ref <sha>` does work — there is simply no
  **named** known-good version a descendant can state or upgrade to.

**Done when:** a generated project commits its own `.copier-answers.yml`
(proved by `git init && git add -A && git ls-files` inside the generated tree,
in a test); keel's own copy stays ignored; a drift test pins the twin to keel's
`.gitignore`; `v0.1.0` exists with a matching CHANGELOG section.

**Landed** (`d0a25c4`): the `.gitignore.jinja` divergence twin, the twin drift
test, `_min_copier_version: "9"`, and the `0.1.0` CHANGELOG section.
**Outstanding:** the `v0.1.0` **git tag** itself does not exist yet
(`git tag -l` is empty), so copier still prints *"No git tags found in
template"* and records a bare SHA. Defect B is only half closed until the tag
is pushed.

### Pass 2 — make `copier update` actually runnable, and test it *(done)*

- `Makefile:26` is `copier copy . "$(DEST)"`, which records the literal
  `_src_path: "."`. Running `copier update` from inside the generated project
  then resolves `.` to the project itself and dies on an unhandled plumbum
  traceback with no diagnostic. Fix: `$(abspath .)`. *(An absolute local path
  and the `gh:` path both already work — this is the one broken entry point.)*
- CI never installs `.[template]`, and
  `tests/integration/test_copier_generation.py:14` is
  `pytest.importorskip("copier")` — so its six real tests, which do generate
  five projects and gate each one, **have never run in CI**. Fix: install the
  extra in `ci.yml`; keep the skip for bare local runs behind an env flag.
- `copier update` itself has no test at all.

**Done when:** `make new` produces a project whose `copier update` succeeds; a
`tests/integration/test_copier_update.py` exercises generate → commit → evolve
template → update; CI runs both without skipping.

**Landed.** `Makefile` now passes `$(abspath .)`, pinned by a `make -n` contract
test that reads the expanded recipe and requires the argument to be absolute *and*
to be a template (`copier.yml` present). `ci.yml` installs `.[dev,template]`,
checks out full history (`fetch-depth: 0`, so a future `--vcs-ref v0.1.0` can
resolve), and sets `KEEL_REQUIRE_TEMPLATE=1` on the suite step; both copier test
modules hard-import under that flag and `importorskip` without it — measured:
absent copier + flag → collection error, exit 2; absent copier, no flag → 1
skipped, exit 0. `tests/integration/test_copier_update.py` runs the full
generate → commit → evolve → update cycle against a throwaway clone of keel
(7 tests, ~15s).

Two findings from the pass that were not in the original bullet list:

- **`ci.yml` and the copier tests ship verbatim downstream.** Installing the
  `template` extra in the shared `ci.yml` would therefore run keel's *template
  meta-tests* inside every generated project — where `copier.yml` and the
  `.jinja` twins do not exist (measured: 6 of 8 fail). `copier.yml` now prunes
  `tests/integration/test_copier_*.py` at generation, pinned by a test.
- **A dirty template also breaks update**, independently of `_src_path`: copier
  records a WIP commit that exists only in its throwaway clone, so `_commit` is
  unresolvable. `make new` now refuses a dirty tree (`ALLOW_DIRTY=1` overrides).

**Deliberately not fixed here:** the recorded origin is a machine-local absolute
path, so a generated project handed to a colleague still cannot `copier update`
(different unhandled traceback: *"Local template must be a directory"*). The
answer is to generate from `gh:JuanSync7/project-keel`; `README.md` now says so
instead of implying `make new` is equivalent.

### Pass 3 — close the gate's blind spot *(next)*

`make verify` is green while `ruff check agents models runtimes mcp api scripts`
reports **99 errors** across **6,453 Python lines (59% of the repo)** — including
a `B904` at `runtimes/langgraph_adapter.py:158` that violates keel's own
*gate-tier* `exception-chaining` practice. `Makefile:60` lints only `src tests`;
`pyproject.toml:79` types only `src`. An agent told *"let the gate decide done"*
is being lied to across most of the repo.

Reuse the existing `CODE_ROOTS` list (`check_structure.py:74`) as the lint and
type scope, then ratchet with per-module mypy overrides rather than in one jump.
Also fix the two confirmed silent-failure modes: `Makefile:62,75` (`command -v
npm || exit 0` exits only its own sub-shell, so the loop still runs and hard-fails)
and `scripts/cdmon_sync.py:8,20` (3.6-illegal `from __future__ import
annotations` + `list[str] | None` make the flagship §9 external-tool adapter
unparseable under the very pre-commit interpreter the repo documents).

**Done when:** `ruff check $(CODE_ROOTS)` is clean, mypy's scope is widened with
recorded overrides, and `/usr/bin/python3 scripts/cdmon_sync.py --check` exits 0.

### Pass 4 — make the generated project the user's, not keel's

- `src/backend/showcase` is **1,205 of 1,433** Python lines (84%) in a generated
  project, against a 30-line `example_feature`, with no question to decline it.
  ADR-0004 declared no-showcase mode out of scope; it is now the highest-value
  knob in `copier.yml`.
- Keel branding is served live from the generated project's API:
  `src/backend/showcase/_repo.py:86` sets `title="project_keel"` immediately
  adjacent to the correctly-tailored `name`, and `api/rest_fastapi/app.py:26`
  is `FastAPI(title="Project Keel API")` — kept green downstream by
  `make check-openapi`.
- `README.md.jinja:82-83` tells the user to delete `wiki/`, `models/`, `evals/`
  and `containers/`; doing exactly that produces 3 errors and exit 1, because
  `config/project.json` still declares the model adapters. Deleted dirs also
  return on any `copier update` that adds a file beneath them.

Replace "delete dirs by hand" with answers: multiselect questions for the
optional surfaces driving `_exclude`, so a declined surface stays declined
across every future update.

**Done when:** `showcase=false` generates a project with no keel branding in any
served response, and the optional-surface questions round-trip through
`copier update`.

### Pass 5 — twin-parity, then the environment manifest (ADR-0005)

`grep -rn 'jinja\|copier' scripts/*.py` returns nothing: **no gate knows the four
`.jinja` twins exist.** The old parity harness died with `scaffold.py`
(ADR-0004). Land `check_N`-style twin parity first — render each twin with
keel's own answers and byte-compare — because ADR-0005 adds a fifth twin, and
adding it first would manufacture a new instance of the drift class it claims to
fix.

Then ship ADR-0005 slice 1 only: `config/environment.json`, the deterministic
declaration check (shape, vocabularies, and the undeclared-external completeness
scan), and the generated `.env.example`. The lock, the fingerprint and the
provider adapters are slice 2, outside this plan's cap.

**Done when:** twin parity is gated, the manifest declares the seven currently
undeclared externals, and the completeness scan errors on a new undeclared
`os.environ` read.

## Explicit non-goals

- Rewriting the conventions. `check_structure.py` A–M, `check_M`'s meta-gate and
  the symlinked per-directory rules are the parts that work; they are not in
  scope for change.
- Migration tooling for existing descendants. There are none yet — which is
  precisely why the version identity in pass 1 must land before there are.
- ADR-0005 slice 2 (lock, fingerprint, provider adapters). Deliberately deferred
  until slice 1 has been used.

## Deferred, with reasons

- **Grace tiers for new checks.** Adding the nested-directory README+CLAUDE rule
  that `AGENT.md:34` already claims to enforce produces 10 errors in keel
  itself. `copier update` *can* carry the fixes downstream (plain files copy
  verbatim), so this is release discipline, not an undeliverable migration: ship
  a new rule as WARN for one release, promote to ERROR in the next, and never
  release a rule keel itself fails. Adopt as a rule from pass 1's tag onward.
- **The same silent-skip defect, one more instance.**
  `tests/integration/test_aad_conformance.py:77` `importorskip`s `jsonschema`,
  which is in neither `.[dev]` nor `api/rest_fastapi/requirements.txt` and is not
  in the repo's own venv — so the "served AAD descriptor validates against the
  committed schema" assertion has **never executed anywhere**. Same class as pass
  2's finding, found while fixing it; left alone to keep pass 2 one slice. If a
  second extra ever needs the CI treatment, generalise to one
  `KEEL_REQUIRED_EXTRAS=template,...` variable rather than a variable per extra.
- **Blanket `except Exception: return 0` in the two drift checks.**
  `api/rest_fastapi/export_openapi.py:43-49` and
  `scripts/agent_surface/generate_aad_schema.py:47-55` degrade *any* failure
  under `--check` to exit 0 with a stderr note. Not active today (CI installs the
  transport requirements, so both really run), but it means a future import or
  route error would show up as a green gate. Fits pass 3's "silent-failure modes"
  bullet.
- **`query_corpus` token cost** (~4.4k tokens per call, no node bodies returned,
  no relevance floor — today strictly worse than `grep` + `Read` for most
  questions). Real, but it is an optimisation of a working thing, not a defect
  in the template contract.
