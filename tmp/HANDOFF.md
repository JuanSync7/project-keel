---
title: Handoff — resume the keel hardening work on another machine
kind: doc
layer: n/a
status: draft
owner: TBD
tags: [handoff, scratch, hardening, resume]
summary: Working state and the remaining worklist for the project-keel hardening branch, written so a fresh agent session on a different machine can pick up without re-deriving context.
id: tmp-handoff
created: 2026-08-06
updated: 2026-08-06
visibility: internal
canonical: false
---

# Handoff — resuming the keel hardening work

**This file is scratch.** It is a snapshot of *in-flight* work, not a source of
truth. The authoritative documents are `docs/design/keel-hardening-plan.md` (the
pass table and the "Deferred, with reasons" section) and the ADRs. If this file
and the plan disagree, **the plan wins** — and this file should then be deleted or
corrected, not trusted. Delete `tmp/` entirely once the branch merges.

---

## 1. Start here

```bash
git checkout feat/keel-hardening-pass-1
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,template]"
.venv/bin/pip install -r api/rest_fastapi/requirements.txt
make PY=.venv/bin/python verify        # expect: 364 passed, 0 skipped, exit 0
```

**`make verify` on its own will fail** at `check-python` on any host whose
`/usr/bin/python3` predates the project floor (`>=3.10`); the machine this branch
was written on has 3.6.8. Always pass `PY=.venv/bin/python`. That is a property of
the *host*, not a defect — `check_python_version.py` is doing its job.

To run pytest directly you need the same path setup the Makefile applies:

```bash
PYTHONPATH=src:tests:. .venv/bin/python -m pytest -q
```

To reproduce **CI's** stricter mode, where a missing optional dependency is a hard
collection error instead of a skip:

```bash
KEEL_REQUIRED_EXTRAS="template,dev,transport" PYTHONPATH=src:tests:. .venv/bin/python -m pytest -q
```

Both must be 364 passed / 0 skipped. A run reporting skips means a surface is not
installed — find out which before doing anything else, because the whole point of
`tests/optional_deps.py` is that a skip is now a signal rather than noise.

## 2. Where the branch is

`feat/keel-hardening-pass-1`, **9 commits ahead of `main`**, newest first:

| Commit | What |
|---|---|
| `55048fb` | the `showcase` question + manifest-driven identity (ADR-0007) |
| `c1383ef` | the silent-skip class (`KEEL_REQUIRED_EXTRAS`) + the README delete-advice bug |
| `9dd4164` | answer retirement via `_migrations` (ADR-0006) |
| `3337c1d` | check_M's two blind spots + check_N (template twin parity) |
| `219fc73` | pass-2 review findings |
| `9478258` | widen lint/type scope to CODE_ROOTS, three silent-green paths |
| `fca1ae5` | pass-1 review findings |
| `b98a0b0` | make `copier update` runnable and gated in CI |
| `d0a25c4` | track `.copier-answers.yml` downstream; plan + ADR-0005 |

Gate at the tip: **364 passed, 0 skipped, exit 0**; `make advise` clean.

## 3. Remaining work, in the order I would take it

### 3.1 The other optional-surface questions — `wiki`, `evals`, `containers` (+ maybe `agents`)

The last live piece of the original pass-4 scope. Mechanical now, and that is the
point: `55048fb` landed the pattern and both gates that police it, so each new
question inherits them without argument.

- `test_every_answer_driven_prune_has_a_retirement_migration` — a prune with no
  mirroring `_migrations` entry fails at the source.
- `test_no_retirement_migration_deletes_something_every_project_needs` — the
  over-reach half. Add each new must-survive path to `_MUST_SURVIVE_ANY_ANSWER`.

Copy the shape from the `showcase` block in `copier.yml` (question → `_exclude`
entries → mirroring `_migrations` entries) and from
`tests/integration/test_copier_generation.py`'s showcase tests.

**Two things to check before pruning any directory**, both learned the hard way:

1. **Does anything shipped-verbatim name it?** `Makefile`, `.github/workflows/*`
   and `scripts/*` ship unrendered and are not answer-aware. `make site-data` and
   `site-static` now `[ -f ... ]`-guard the showcase scripts for exactly this
   reason; `pages.yml` was the original instance (pass 3.5).
2. **Does anything import it, or link to it?** A pruned `docs/guides/*.md` that a
   surviving README links to is a broken link in every generated project.
   `README.md.jinja` wraps the showcase section in `{% if showcase %}` for this.

**Note on `README.md.jinja`:** it is a `parity` twin, so `check_N` rejects any
non-templated line the twin has and `README.md` lacks. An `{% else %}` branch with
new prose **will fail the gate** — I tried. Wrap-and-omit, do not wrap-and-replace.

**`agents/` deserves a decision, not a default.** Keel ships four agents
(`index_enforcer`, `practice_refactor`, `wiki_navigator`, `triage`), seven
`agents/tools/*.tool.md` contracts, and a `.claude/skills/practice-refactor/`
adapter — all unconditionally. Three of the four are corpus-coupled (query, build,
walk-as-KG); the corpus survives every answer, so they *work*, but "always ships"
is currently an accident rather than a choice. Either add an `agents` question or
record in the ADR why they are foundational.

### 3.2 `api/rest_fastapi/export_openapi.py:44` — blanket `except Exception: return 0`

Small, and the same silent-green class the last four passes have been closing.
Under `--check`, *any* failure building the spec degrades to exit 0 with a stderr
note — so a future import error or a broken route reads as a passing gate.

The fix shape is already in the repo: `scripts/agent_surface/generate_aad_schema.py`
was the twin of this defect and now skips only on `ImportError`/`SyntaxError` and
fails on everything else. Mirror it. Write the failing test first (a route that
raises at `app.openapi()` time must make `--check` exit non-zero).

Note `55048fb` already added a *legitimate* exit-0 path to this file — a missing
`openapi.json` means "no contract published yet", which is distinct from "drifted"
and is tested in both directions. Do not collapse the two while fixing the
`except`.

### 3.3 ADR-0005 slice 1 — the external environment manifest

The only remaining item that is still a **design** question rather than execution.
ADR-0005 is `status: proposed`, not accepted. Slice 1 is `config/environment.json`,
the deterministic declaration check (shape, vocabularies, and the
undeclared-external completeness scan — `check_O`), and the generated
`.env.example`. The lock, the fingerprint and the provider adapters are slice 2
and are **outside** this plan.

Its stated prerequisite is met: twin parity is gated by `check_N`, so adding a
seventh `.jinja` twin can no longer manufacture a new instance of the drift class
the ADR claims to fix.

**Framing constraint, carried from the memory note and the ADR itself:** scope this
honestly against Docker. Name the incumbent and say precisely where it does not
reach (Environment Modules, licence servers, Slurm, NFS automounts — the things a
container cannot swallow at this site). Do not pitch it as a container replacement.

## 4. Deferred, with reasons (verified still true at `55048fb`)

- **`.pre-commit-config.yaml` pins `ruff-pre-commit` at `v0.8.4`** while the venv
  and CI run ruff **0.15.18**, and `.github/workflows/ci.yml` never runs
  `pre-commit run --all-files` at all. So the repo-wide enforcement path is opt-in
  and pinned to a version the currently-clean corpus is not clean under. Bump the
  pin and add the CI step **in the same change**, and re-run at the new pin first.
- **`mcp/protocol.py:105`** passes `params.get("name")` into
  `call_tool(self, name: str, ...)`. It does not crash today
  (`self._by_name.get(None)` → `isError: "unknown tool: None"`), and `mcp` is a
  declared ratchet rung so nothing gates it. The class-correct fix is a
  `-32602 invalid params` at the transport boundary — an observable protocol
  change, so it needs its own failing test first. Sequence it with the `mcp` rung.
- **Grace tiers for new checks.** The nested-directory README+CLAUDE rule that
  `AGENT.md` already claims to enforce would redden keel itself (≥5 unlabeled
  nested packages under `src/backend/`). Ship a new rule as WARN for one release,
  promote to ERROR in the next, never release a rule keel itself fails.
- **`query_corpus` token cost** (~4.4k tokens/call, no relevance floor, ~400-char
  excerpts rather than section bodies). Real, but an optimisation of a working
  thing — not a defect in the template contract.

## 5. Housekeeping owed

- **Tag `v0.1.0`.** `git tag --list` is empty, yet `README.md` and `CHANGELOG.md`
  both tell users to generate with `--vcs-ref v0.1.0`, which resolves to nothing.
  Safe to cut now that `make new` pins `VCS_REF ?= HEAD`; before that fix, tagging
  armed a silent-wrong-source bug. Do it after this branch merges to `main`.
- **`agents/*/README.md` owners.** Five `WARN accountability: ... has no real owner
  (missing or 'TBD')`. Warnings, not errors — but they are the only noise left in a
  clean gate.

## 6. Traps already paid for — do not re-pay them

- **A mechanism that appears inert is usually a harness problem.** `_migrations`
  looked like a no-op for a whole pass. The update fixtures cloned keel with
  `git clone`, which carries **only HEAD**, so the uncommitted `_migrations` block
  was simply absent from the template under test. Instrumenting
  `Template.migration_tasks` showed `raw_entries=0` immediately. Fixed at source —
  `_clone_template` now replays the working-tree diff into the clone — but the
  general lesson is the valuable part: **before theorising about why your change
  did nothing, verify the harness is exercising the artefact you edited.**
- **Copier does not write `.copier-answers.yml` by itself.** The template must ship
  `.copier-answers.yml.jinja`, or generated projects cannot `copier update` at all.
- **Measure on a generated project, never on a keel clone.** Keel has `.jinja`
  twins and a `copier.yml`; a generated project has neither, so `check_N` and the
  meta-tests behave differently. Two separate false readings came from this.
- **When a defect is found by *reading*, make the gate a *scan*.** Reading found 2
  branding hardcodes; the scan found 8.
- **A committed artifact generated from live code cannot ship verbatim from a
  template.** `openapi.json` named keel and listed showcase routes, so
  `make check-all` was red on arrival in every generated project. Treat such files
  as generated views (`_exclude`) and teach their `--check` to distinguish "never
  published" from "drifted".
- **`curl`/`wget` are unsafe on these hosts.** CrowdStrike Falcon flags and may
  SIGKILL them, including for loopback health checks. Use `urllib.request` /
  `http.client` in `python3 -c`, or call the handler directly.
- **Never run an unscoped `find /`.** ~28 NFS exports (`/home` on qumulo, a farm of
  `/vols/*` under autofs) mean a bare `find /` triggers automounts and blocks for
  hours in `D` state. Scope the path, or add `-xdev`.

## 7. Working agreements this branch has been held to

From `AGENT.md`, and worth restating because every pass here has followed them:

- **Test-first.** Drive `src/` changes from the mirror test; a public symbol with
  no test is unfinished.
- **`make verify` decides "done".** Never a self-report.
- **One vertical slice per pass**, then verify, then commit. Re-derive the worklist
  from the repo each pass rather than trusting a stale list — including this file.
- **Solve the class, not the example.** If a change only makes the named case pass,
  it is a patch, not a fix.
