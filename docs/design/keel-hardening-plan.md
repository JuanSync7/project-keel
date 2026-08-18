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
updated: 2026-08-18
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

### Pass 3 — close the gate's blind spot *(done)*

`make verify` is green while `ruff check agents models runtimes mcp api demo
scripts` reports **101 errors** across **6,571 Python lines (58% of the repo's
Python)** — including a `B904` at `runtimes/langgraph_adapter.py:158` that
violates keel's own *gate-tier* `exception-chaining` practice. `Makefile:72`
lints only `src tests`; `pyproject.toml:79` types only `src`. An agent told
*"let the gate decide done"* is being lied to across most of the repo.
*(Re-measured at `fca1ae5` for this pass by extracting the commit and linting
it: 101 errors — scripts 83, api 7, agents 3, runtimes 3, demo 2, models 2,
mcp 1 — over 6,571 lines. The draft's 99 / 6,453 / 59% did not reproduce and
have been corrected; the shape of the finding is unchanged.)*

Reuse the existing `CODE_ROOTS` list (`check_structure.py:74`) as the lint and
type scope, then ratchet with per-module mypy overrides rather than in one jump.
Also fix the two confirmed silent-failure modes: `Makefile:74,87` (`command -v
npm || exit 0` exits only its own sub-shell, so the loop still runs and hard-fails)
and `scripts/cdmon_sync.py:8,20` (3.6-illegal `from __future__ import
annotations` + `list[str] | None` make the flagship §9 external-tool adapter
unparseable under the very pre-commit interpreter the repo documents).

**Done when:** `ruff check $(CODE_ROOTS)` is clean, mypy's scope is widened with
recorded overrides, and `/usr/bin/python3 scripts/cdmon_sync.py --check` exits 0.

**Landed.** All three done-conditions met, and `make verify
PY=.venv/bin/python` exits 0 (300 passed, 1 skipped — the skip is the
pre-existing `jsonschema` `importorskip` below, identical at `fca1ae5`). A bare
`make verify` still exits 2 at `check-python`, because `PY ?= python3` is this
host's 3.6.8; that is pre-existing and deliberate, and `check-python` is
untouched by this pass.

- **The three scope lists are one list.** `Makefile` declares
  `CODE_ROOTS := src tests api models mcp agents demo scripts runtimes` — the
  same nine as `check_structure.py:74` — and `lint-py`/`fmt` use
  `$(wildcard $(CODE_ROOTS))`; the wildcard is load-bearing, because ruff exits
  1 with `E902 No such file or directory` on a root copier pruned downstream.
  `typecheck-py` now passes mypy **no paths**: an explicit path argument
  overrides `[tool.mypy] files`, so widening the config alone would have been
  silently inert. CI already runs `make lint` and `make typecheck`, so the
  widening reaches CI without a workflow change.
- **ruff is clean over all nine roots** (`All checks passed!`, re-measured
  today). Disposition of the 101: 41 T201 entrypoint prints became declared
  per-file ignores (`scripts/**` as a glob because every print there is inside a
  `main()`; `api/` and `demo/` named file-by-file so a genuine library print is
  still caught), 55 were fixed in code, and 5 carry a reasoned inline `# noqa`
  (3 PERF401 inside check_M's own body, 1 SIM102, 1 BLE001 that degrades into a
  visible `owner_source == "none"` signal). The carve-outs are mirrored as data
  in `config/practices.json` `rulesets.ruff.per_file_ignores` — but see the
  check_M blind spot below: that mirror is reviewed data, not an enforced gate.
- **mypy 19 → 36 files checked.** `files = ["src"]` →
  `["src", "models", "demo", "agents"]`, plus `explicit_package_bases` and
  `mypy_path = ["src"]` (without the first mypy does not start: *Source file
  found twice under different module names*), and four `[[tool.mypy.overrides]]`
  blocks that relax only measured flags and never `strict = false`. Full strict
  over all nine roots is **1,411 errors in 71 files** today, so the rest is a
  declared ratchet in `config/practices.json` `rulesets.mypy.ratchet`, one rung
  per root with an error count and a removal condition, and
  `test_gate_scope.py` fails if a code root is in neither `files` nor the
  ratchet. **Deliberate deviation from the plan's "widen the scope":** the roots
  that are not clean were *not* forced in. Doing so would have needed either the
  **173** errors that survive even with the whole `typed-everywhere` flag set
  relaxed (re-measured today; 161 when the deviation was taken, before this
  pass's own new tests) or a blanket `ignore_errors` — a fake gate. The
  one `ignore_errors` used is `runtimes.*`, which `agents/` drags in
  transitively; it is a declared rung with its cost and exit recorded.
- **The FE guards skip instead of failing.** Reproduced on the old Makefile with
  an empty PATH: *"npm not found; skipping frontend lint"* followed by
  `npm: command not found` and `make: *** [Makefile:75: lint-fe] Error 1`, exit
  2. Guard and loop are now one logical line, `FE_APPS` is tested first so a
  `frontend_stack: none` project says nothing about npm, and all four cells ×
  two targets are pinned — including the non-regression half (npm present, the
  app's script failing, target must still fail), which really ran here.
- **`cdmon_sync.py` parses at the documented floor.**
  `/usr/bin/python3 scripts/cdmon_sync.py --check` exits 0 and prints the
  graceful skip; at `fca1ae5` the same command was `SyntaxError: future feature
  annotations is not defined`, exit 1. Both hazards were fixed, not just line 8:
  with the future import gone, `list[str] | None` raises `TypeError` at def
  time.
- **Two silent-failure modes beyond the plan's two.** (a) The gate's config
  readers could not tell *absent* from *unreadable*: with a malformed
  `config/practices.json`, `fca1ae5`'s `check_structure.py` prints
  `0 error(s), 5 warning(s)` and exits 0 with check_K, check_L and check_M
  reduced to no-ops; it now prints one `ERROR config/practices.json:
  unreadable (...)` and exits 1, while an *absent* file stays silent because
  copier legitimately prunes files. All 16 blind `except Exception:` clauses in
  `check_structure.py` are gone (8 deleted, 8 narrowed to two named tuples).
  (b) `generate_aad_schema.py --check` returned 0 on a broken model; only
  `ImportError`/`SyntaxError` skip now. This closes half of the "blanket
  `except Exception: return 0`" item under *Deferred* — `export_openapi.py:44`
  is the surviving half.
- **The pass regressed every descendant, and the repair is pinned.** `Makefile`
  ships verbatim but `pyproject.toml` does not — a generated project's pyproject
  comes entirely from `pyproject.toml.jinja`. Mid-pass the twin still carried
  `files = ["src"]` and no T201 carve-outs, so a generated project got the
  9-root lint scope against a pyproject without them: measured, **40 T201
  errors, exit 1 on arrival**, plus a mypy scope of 19 files against keel's 36 —
  silently green, which is worse. The twin was regenerated *from*
  `pyproject.toml` and is now pinned as text; a second test lints a freshly
  generated project over the roots its own `Makefile` declares. Both were
  confirmed to bite by reverting the twin in a scratch copy.

**Not closed by this pass** (each verified, not assumed; the durable ones are
also filed under *Deferred, with reasons*):

- **check_M cannot see the two mechanisms this pass leaned on.** Adding a
  blanket `per-file-ignores = {"**/*.py" = ["B904", "BLE001"]}` *and* a
  `[[tool.mypy.overrides]] strict = false` to `pyproject.toml` still yields
  `check_structure: 0 error(s)`, exit 0 (measured in a scratch copy). `grep -rn
  per_file_ignores scripts/` returns nothing, and `overrides` appears nowhere in
  `check_structure.py`. So the entire mypy ratchet this pass introduced parks its
  declared debt inside the parity gate's blind spot. Highest-value follow-up;
  it needs `check_structure.py` + `pyproject.toml` + `config/practices.json` in
  one commit, which no single writer in this pass was allowed to make.
- **The two large ratchet rungs are already stale.** Re-measured today (full
  strict, own-file errors): tests **702**, scripts **482**, runtimes 87, api 43,
  mcp 16 — against the declared 622 / 464 / 87 / 43 / 16. The four small rungs
  reproduce exactly; the two big ones grew with the test files this pass added.
  `test_every_mypy_ratchet_entry_states_its_cost_and_its_exit` asserts only that
  an `errors` int and a `removed_when` exist — it does **not** re-measure, so
  these numbers are documentation, not a gate.
- **`make fmt` is widened but has never been run**: `ruff format --check` over
  the nine roots reports 104 of 111 files as *would reformat*. It is not in
  `make verify`, so nothing is red — but the first run reformats the corpus,
  including the five 3.6-constrained `scripts/`.
- **mypy still does not cover 5 of 9 roots**, by decision (above).
  `api/grpc/` additionally cannot enter scope without a choice: its
  `thing_pb2`/`thing_pb2_grpc` are `make gen` output that is not committed (the
  file genuinely does not exist here), and grpc ships no stubs.

### Pass 3.5 — close the pass-2 review findings *(done)*

Not a planned pass: an adversarial review of pass 2, run in an isolated worktree
pinned at `fca1ae5`, produced six defects that all reproduced. Landed as one slice
because each is small and they share a theme — *shipped-verbatim files, and tests
that pass without proving anything*.

- **`pages.yml` hardcoded `src/frontend/astro`**, which `_exclude` prunes under the
  DEFAULT answer, so a default-generated project's first push to `main` failed on
  `npm ci`. Same hardcode in `make run-web` and in `export_showcase_static.py`'s
  default output dir — and because the exporter *creates* its output, that one
  silently resurrected a declined stack. All three now discover the frontend; a new
  test scans every shipped Makefile/workflow/script of a generated project for a
  pruned path, so the next hardcode fails at the source.
- **`make new` passed no `--vcs-ref`**, so copier resolves the newest TAG, not HEAD.
  Latent only until `v0.1.0` is cut — the outstanding pass-1 item is what arms it.
  Now `VCS_REF ?= HEAD`, overridable for a release smoke-test.
- **`make new` read a non-git template as clean** (`git status --porcelain
  2>/dev/null` discards rc=128), generating a project with no `_commit` at all.
- **The update test's hermetic gitconfig omitted `core.excludesFile`** — a false red
  on a correct tree. Fixing it uncovered the larger half: `plumbum` snapshots the
  environment at import, so no fixture can reach copier's own git subprocesses. The
  neutralisation moved to `tests/conftest.py`, and one shared `tests/hermetic_git.py`
  replaced the two copies that had drifted.
- **The `KEEL_REQUIRE_TEMPLATE` backstop matched its own source**, so it could never
  fire; deleting both real copier test modules left it green.
- **`_exclude` cannot retire files on update** (see pass 4). Mitigated here by making
  the meta-tests self-neutralising wherever no `copier.yml` exists, pinned by
  generating a project, copying them back in, and running them the way CI does.

**Gate:** `make verify` -> 306 passed, 1 skipped, exit 0.

**Deliberately not fixed here:** the answer-change half of the `_exclude` finding.
It needs `_migrations`, and belongs to pass 4's redesign.

### Pass 4 — make the generated project the user's, not keel's *(retirement done; questions next)*

- `src/backend/showcase` is **1,205 of 1,433** Python lines (84%) in a generated
  project, against a 30-line `example_feature`, with no question to decline it.
  ADR-0004 declared no-showcase mode out of scope; it is now the highest-value
  knob in `copier.yml`.
- Keel branding is served live from the generated project's API:
  `src/backend/showcase/_repo.py:86` sets `title="project_keel"` immediately
  adjacent to the correctly-tailored `name`, and `api/rest_fastapi/app.py:26`
  is `FastAPI(title="Project Keel API")` — kept green downstream by
  `make check-openapi`.
- ~~`README.md.jinja` tells the user to delete `wiki/`, `models/`, `evals/` and
  `containers/`; doing exactly that produces 3 errors and exit 1, because
  `config/project.json` still declares the model adapters.~~ *(closed in pass 6:
  the advice drops `models/` and documents the manifest change; both halves are
  pinned by tests that read the sentence out of the generated README.)* Deleted
  dirs still return on any `copier update` that adds a file beneath them — that
  half needs the optional-surface questions below.

**Redesigned after the pass-2 review — `_exclude` cannot deliver this.** The
original plan was "multiselect questions for the optional surfaces driving
`_exclude`, so a declined surface stays declined across every future update."
That is false as designed, and structurally rather than by bug: `_exclude` is a
**generation-time filter**. On `copier update` copier renders the old template
copy with the UNION of the old and new excludes, deliberately, "to prevent
deletion" (`copier/_main.py`). An excluded path is therefore never *retired* —
only never *created*. Both halves measured: a project generated before an exclude
landed keeps the file forever, and re-answering (`--data frontend_stack=astro` on
a react-vite project) leaves the old stack on disk while `.copier-answers.yml`
says otherwise — 13 errors from that project's own gate.

So pass 4 is built on **`_migrations`**, the hook copier provides for exactly
"this version retires something", with `_exclude` kept only for the never-created
case. Each optional surface needs two things, not one: the answer that stops it
being generated, and the migration that removes it from a project that already
has it. A surface added without its migration is the same defect class this pass
exists to close, so the migration is part of the done-condition.

**The retirement half has landed** (ADR-0006). Every answer-driven `_exclude` entry
now has a mirroring `_migrations` entry; the *pairing* is asserted for the whole
class by `test_copier_generation.py`, so the questions added below inherit the rule
automatically rather than each having to remember it. Retirement is tested live by
a restack fixture (generate `react-vite` → commit → update to `astro`), which
requires the declined tree to be gone *and* the project's gate to pass. Cost
accepted: `copier update` now requires `--trust`; generation still does not.

> **Why this took a wasted pass, recorded so it is not repeated.** The first
> attempt concluded that `_migrations` "do not run against keel's clone" — an
> instrumented migration left no marker. That conclusion was wrong. The update
> fixtures cloned keel with `git clone`, which carries only HEAD, so the
> uncommitted `_migrations` block was absent from the template actually under
> test; the task list was empty because the migrations did not exist. Instrumenting
> `migration_tasks` showed `raw_entries=0` immediately. The fixture now replays the
> working-tree diff into the clone, so this class of "my change appears to do
> nothing" cannot recur. General lesson: when a mechanism appears inert, first
> verify the harness is exercising the artefact you edited.

**Remaining (the questions themselves):** a `showcase: bool` question and the
optional-surface questions, plus removing keel branding from
`src/backend/showcase/_repo.py:86` and `api/rest_fastapi/app.py:26`.

**Done when:** `showcase=false` generates a project with no keel branding in any
served response, and the optional-surface questions round-trip through
`copier update`.

### Pass 7 — the `showcase` question, and keel's name out of the user's API *(done)*

One vertical slice: **decline the showcase**. The branding belongs to the same
slice rather than a later one, because it is only *observable* once someone
declines — a `showcase=false` project that still answers `Project Keel API` is
the defect, not a cosmetic leftover.

**The coupling, measured rather than assumed.** ADR-0004 and `copier.yml` both
assert that the showcase is inseparable from the AAD reference implementation and
the corpus/wiki tooling. That is false, and the grep is the whole argument:
nothing under `api/rest_fastapi/aad/`, `mcp/`, `agents/` or `scripts/query_corpus.py`
imports `backend.showcase`. They read `wiki/corpus.json`, which the showcase reads
*too* but does not own. So the surfaces that actually depend on it are:

| Surface | Depends on `backend.showcase`? | Fate under `showcase=false` |
|---|---|---|
| `api/rest_fastapi/showcase_api.py` | imports it | pruned |
| `scripts/jobs/export_showcase_static.py` | imports it | pruned |
| `src/frontend/astro` | 7 pages, all fetching `/api/*` | pruned |
| `src/frontend/react-vite` | **no** `api/` reference at all | kept |
| `api/rest_fastapi/aad/`, `mcp/`, `agents/`, corpus scripts | no | kept |

`astro` is the showcase UI, so `frontend_stack=astro` + `showcase=false` is an
incoherent answer pair: `pages.yml` would `npm ci` a pruned tree and `make
site-static` would call a pruned exporter. Rejected by a `validator` on
`frontend_stack` with a message naming the fix — **not** silently coerced, which
is the failure class the last four passes have been closing.

**Branding is manifest-driven, not answer-driven.** `config/project.json` is
already the machine-checked source of project facts and `_repo.py` already reads
`name` from it, so the display title derives from that one place:
`api/rest_fastapi/app.py` reads it at import, and `check-openapi` keeps working as
a real drift gate with no exception carved for it. A copier *answer* would be
fixed at generation time and rot the first time the project renamed itself.

**Done when:** `make verify` is green; a `showcase=false` project has no
`backend.showcase`, no dangling import, and a green gate of its own; a project
generated under any name serves that name; and re-answering `showcase` retires
the tree through `copier update` (the pairing gate landed in pass 4 forces the
migration to exist, so this is inherited rather than re-argued).

**Gate:** `make verify` -> 364 passed, 0 skipped, exit 0 (from 345). ADR-0007.

**Two things the pass found that were not in the plan.**

*The branding was eight lines, not two.* Reading found `app.py` and `_repo.py`;
scanning the generated tree as a class found six more — the showcase SUMMARY and
two setup steps, the exporter's `--base-url` example, `config/default.example.toml`
and `config/practices.json`. The scan is now the gate, so the ninth fails at the
source rather than being read for.

*`openapi.json` made `make check-all` red on arrival.* Not from the showcase — from
the rename alone. Keel's committed contract names keel, so the moment the app
titled itself after the project, every generated project's `check-openapi` was
stale on the first run. It is a generated view and no longer ships;
`export_openapi.py --check` now separates "none published yet" (exit 0, loudly)
from "drifted" (exit 1). That is a deliberate new exit-0 path, so both branches
are tested: publish a contract, drift it, and the check must go red again.

**Deliberately not done here:** the remaining optional-surface questions
(wiki/evals/containers). They are the same shape as `showcase` and now inherit
both gates — the prune/migration pairing and the over-reach check — so they are a
mechanical repetition rather than a design question.

### Pass 8 — the machine-readable module contract, gated end to end

The audit behind this pass is the user's question, made precise: *what
guarantees that an agent (or a new human) can interpret this code?* The answer
must be "the gate", because an agent can only rely on what the gate proves —
a convention that merely happens to hold is worse than none, since the agent
trusts it. Three holes, all measured on this tree:

| Hole | Measurement |
|---|---|
| The module header (`title:`/`summary:`) is 100% followed and 0% enforced | 109/109 modules have a docstring; **5** lack the explicit keys and silently fall back (filename as title, first line as summary — then labeled `authored`); `build_corpus.py:343` silently *drops* an undocumented module (`if not doc: return`, exit 0) |
| The corpus walks a private copy of the scope | `build_corpus.py:34` re-types `CODE_ROOTS` and omits `runtimes` (drifted since `906a42b`, when pass 3's root landed in `check_structure` only) — **6 modules invisible** to every corpus-driven agent |
| Nothing gates the corpus agents actually read | `wiki/corpus.json` is a gitignored generated view; `make check-corpus` builds *fresh* and never looks at it; staleness is a WARN behind an opt-in `--corpus` flag. Measured: the on-disk corpus is 3 modules (33 nodes) behind the tree while `make verify` is green |

One vertical slice — the contract, its scope, and its currency:

1. **`check_O` (ERR):** every `.py` under `CODE_ROOTS` carries a module
   docstring with explicit, non-empty `title:` and `summary:` lines — the same
   grammar `build_corpus._docstring_meta` reads, pinned by a parity test rather
   than a shared import (`check_structure` must stay 3.6-safe and cannot import
   a `$(PY)`-only module). Unparseable files skip, as in check_E — check_D
   already warns there.
2. **`check_E` WARN → ERR.** Authored symbol coverage is the other half of the
   same contract, and keel measures at zero findings, so promotion is free.
   (The grace-tier rule — WARN one release, then ERR — binds from `v0.1.0`
   onward; there has been no release yet.)
3. **`build_corpus` single-sources its scope** (`CODE_ROOTS`, `IGNORE_DIRS`)
   from `check_structure`, killing the drifted private copy. `runtimes` becomes
   visible; a future tenth root cannot be forgotten twice.
4. **`make check-corpus` gates the local corpus:** absent → say so loudly, exit
   0 (a fresh clone and CI have none — the ADR-0007 absent-vs-drifted pattern);
   present-but-stale → ERROR naming `make site-data`. Staleness is judged on the
   **deterministic projection** (generated summaries/links stripped), so
   `index_enforcer`'s legitimate `"generated"` enrichment is never read as rot.
5. Fix the five non-compliant modules (three test helpers, two `scripts/` —
   including `check_structure.py` itself, which must satisfy its own check).

**Done when:** a module missing its header, an exported symbol missing its
docstring, and a stale local corpus each fail `make verify` (mutation-checked);
a fresh clone and a generated project are green on arrival; every on-disk
`CODE_ROOTS` module appears in a fresh corpus with an authored title+summary
(integration-tested). ADR-0008. **Note:** this pass takes the letter `O`;
ADR-0005's proposed completeness scan (status: proposed, never implemented)
moves to `check_P` — letters belong to landed checks.

**Slice 2 of the same pass:** the judgment half that cannot be a gate —
`docs/guides/python-style.md`, the canonical "how Python is written here"
(readability and loud failure modes outrank speed; comment and docstring
discipline; how a code agent works in this repo), linked from `AGENT.md` and
sorted into the practices registry as doc-tier. Guides ship verbatim, so it
governs every generated project: EDA scripts, checklist tools, agents, and
full products alike.

### Pass 5 — twin parity + the meta-gate's own holes *(first half done)*

**Landed: `check_N` and check_M's two blind spots.**

`check_M` — the meta-gate whose whole job is proving `pyproject.toml` cannot
silently loosen the declared lint/type policy — could itself be switched off
through exactly the two mechanisms pass 3's carve-outs and ratchet use:
`rulesets.ruff.per_file_ignores` had no consumer at all, and
`[[tool.mypy.overrides]]` blocks were invisible (and aliased onto one dotted key,
so only the last would have been read anyway). Both measured at zero findings,
exit 0. Both now error unless declared per module — including a relaxation of a
*component* of `strict` rather than `strict` itself.

`check_N` replaces the one-off pytest pins passes 1–3 kept adding: all six
`.jinja` twins are declared in `config/project.json` `template.twins` with a kind
(`parity` / `divergence` / `generated`), and the check is **render-free** because
`check_structure.py` is stdlib-only and 3.6-safe. That bounds it honestly — it
cannot byte-compare a rendered twin, so it proves instead that no twin is
undeclared, no parity twin carries a non-templated line the plain file has lost,
no divergence twin has stopped diverging, and no `generated` twin has a committed
plain file. The byte-exact rendered comparison stays in `tests/integration`.
Mutation-verified on all three failure modes; each was silent before.

**Gate:** `make verify` -> 334 passed, 1 skipped, exit 0.

**Still to do: ADR-0005 slice 1.** `config/environment.json`, the deterministic
declaration check (shape, vocabularies, and the undeclared-external completeness
scan — `check_P`, shifted from `check_O` by ADR-0008), and the generated `.env.example`. The lock, the fingerprint and
the provider adapters are slice 2, outside this plan. Its stated prerequisite is
now met: twin parity is gated, so adding a seventh twin can no longer manufacture
a new instance of the drift class it claims to fix.

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
  that `AGENT.md:34` already claims to enforce reds keel itself — the exact
  count depends on how the rule is scoped (keel ships 5 unlabeled nested
  packages under `src/backend/`, each missing both `README.md` and `CLAUDE.md`),
  so treat "10" as one plausible reading, not a measurement. `copier update`
  *can* carry the fixes downstream (plain files copy verbatim), so this is
  release discipline, not an undeliverable migration: ship
  a new rule as WARN for one release, promote to ERROR in the next, and never
  release a rule keel itself fails. Adopt as a rule from pass 1's tag onward.
- ~~**The same silent-skip defect, one more instance.**~~ *(closed in pass 6.)*
  Kept for the record, because the measurement is the point:
  `tests/integration/test_aad_conformance.py` `importorskip`ped `jsonschema`,
  which was in neither `.[dev]` nor `api/rest_fastapi/requirements.txt` nor the
  repo's own venv — so the "served AAD descriptor validates against the committed
  schema" assertion had **never executed anywhere**, while the suite reported
  success on every run. Closed as predicted here, by generalising to one
  `KEEL_REQUIRED_EXTRAS` declaration rather than a variable per extra — and
  applied to the whole class (`fastapi`/`httpx`/`copier` were unguarded the same
  way), with a scan that fails any module reaching for a raw `importorskip`
  outside the declared opt-in set. The assertion passes and was mutation-checked
  to bite.
- **Blanket `except Exception: return 0` in the two drift checks.** *(Half
  closed in pass 3.)* `scripts/agent_surface/generate_aad_schema.py` now skips
  only on `ImportError`/`SyntaxError` and fails on anything else.
  `api/rest_fastapi/export_openapi.py:44` still degrades *any* failure under
  `--check` to exit 0 with a stderr note — same class, same fix shape, left
  alone because `api/` was a different writer's slice in that pass. Not active
  today (CI installs the transport requirements, so it really runs), but a
  future import or route error would show up as a green gate.
- ~~**check_M's two proven blind spots**~~ *(closed in pass 5.)* Kept here for
  the record, because the measurement is the point: It
  reads `tool.ruff.lint.extend-select`, `deferred` and `tool.mypy.<flag>` only,
  so (a) `config/practices.json` `rulesets.ruff.per_file_ignores` has **no
  consumer at all** (`grep -rn per_file_ignores scripts/` is empty), and (b)
  `_toml_targets` normalises `[[tool.mypy.overrides]]` to the single dotted key
  `tool.mypy.overrides.<flag>`, so every override block aliases onto one entry
  and `_flag_state` is last-writer-wins. Measured: a blanket
  `per-file-ignores = {"**/*.py" = ["B904", "BLE001"]}` and a per-module
  `strict = false` each yield zero findings and exit 0 — i.e. the meta-gate can
  be silently switched off through exactly the two mechanisms pass 3's carve-outs
  and ratchet use. Needs `check_structure.py`, `pyproject.toml` and
  `config/practices.json` changed in **one** commit, so it could not be done by
  a single writer under pass 3's write discipline. Write the two failing unit
  tests first; both return `([], [])` today.
- **The corpus-wide enforcement path is opt-in.** `.pre-commit-config.yaml` runs
  ruff repo-wide over staged files and would have caught the `B904` years
  earlier, but it requires a manual `pre-commit install`, and
  `.github/workflows/ci.yml` runs `make check-all/lint/typecheck/test` and never
  `pre-commit run`. Adding `pre-commit run --all-files` to CI is the natural
  fix — but the config pins `ruff-pre-commit` at `v0.8.4` while the venv and CI
  run ruff `0.15.18`, and the newly clean corpus is only clean under the latter.
  Bump the pin in the same change, and re-run at the new pin first.
- **`mcp/protocol.py:105` passes `params.get("name")` into `call_tool(self,
  name: str, ...)`** (`mcp/protocol.py:57`), so a malformed JSON-RPC
  `tools/call` reaches a non-Optional parameter. It does not crash today —
  `self._by_name.get(None)` returns None and the caller gets
  `isError: "unknown tool: None"` — and it is a mypy finding in a root that is a
  declared ratchet rung, so nothing gates it. The class-correct fix is a
  `-32602 invalid params` at the transport boundary, which is an observable
  protocol change and needs its own failing test first. Sequence it with the
  `mcp` rung.
- **`query_corpus` token cost** (~4.4k tokens per call, no relevance floor, and
  only a ~400-char excerpt per node rather than the section body — so for most
  questions it costs more than `grep` + `Read` and answers less). Real, but it is
  an optimisation of a working thing, not a defect in the template contract.
