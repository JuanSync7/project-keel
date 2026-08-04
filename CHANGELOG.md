# Changelog

All notable changes. Format: Keep a Changelog.

Generated projects record the template ref they came from in
`.copier-answers.yml` (tracked, not ignored — see 0.1.0). Generate a **named**
version rather than a bare commit:
`copier copy --vcs-ref v0.1.0 gh:JuanSync7/project-keel my-project`.

## [Unreleased]

### Fixed
- `_min_copier_version` is `9.1.0`, not `9`. `multiselect:` questions landed in
  copier 9.1.0, so 9.0.1 passed the declared gate and *then* died on
  `Could not convert [] to string` — the mystery error the gate exists to
  pre-empt. A floor that admits a copier which crashes is worse than no floor,
  because the user is told the version was checked. Pinned to the features
  `copier.yml` actually uses by a contract test.
- A generated project starts **its own** `CHANGELOG.md` (new `.jinja` divergence
  twin) instead of inheriting keel's release history — previously a new project
  shipped with a dated `[0.1.0]` it never released, describing keel's internals
  as if they were its changes. The twin keeps the attribution and the
  `.copier-answers.yml` provenance note.
- `test_generated_project_commits_its_copier_answers` is hermetic against the
  developer's machine. `git add -A` honours global excludes, and git reads
  `~/.config/git/ignore` with no config entry at all — so a single `*.yml` line
  there failed the tracked-answers assertion on someone else's laptop.
- `copier.yml`'s note on how twins render was wrong (and predates these passes):
  the plain file is *not* copied-then-overwritten. For any path with a
  `<name>.jinja` sibling copier's `_render_path` returns early, so the plain twin
  is never copied and walk order is irrelevant.
- `make new` now hands copier an **absolute** template path. Copier records that
  argument verbatim as `_src_path`, so the old literal `.` was re-resolved against
  the *generated project* on `copier update` — copier cloned the project as if it
  were the template and git died with `pathspec '<keel sha>' did not match any
  file(s) known to git`, a raw traceback with no diagnostic.
- `make new` also refuses a **dirty** keel tree (`ALLOW_DIRTY=1` overrides): from a
  dirty template copier records a WIP commit that exists only in its throwaway
  clone, so the generated project could never resolve `_commit` either.
- CI installs the optional `template` extra (`.[dev,template]`) and declares it
  required via `KEEL_REQUIRE_TEMPLATE=1`. The copier tests `importorskip`ped, so
  keel's own generation gates had **never run in CI**; a missing copier is now a
  hard collection error there, while a bare local clone still skips gracefully.
  CI also checks out full history (`fetch-depth: 0`) so a `--vcs-ref v0.1.0` pin
  can resolve — a depth-1 checkout carries no tags.
- Generated projects no longer ship keel's template **meta-tests**
  (`tests/integration/test_copier_*.py`). They assert on `copier.yml` and the
  `.jinja` twins, which a generated project does not have, and `ci.yml` ships
  verbatim — so with the extra now installed they would have turned every
  descendant's CI red.
- **`make verify` gated 2 of the repo's 9 Python roots.** `Makefile:72` linted
  `src tests` and `pyproject.toml:79` typed `files = ["src"]`, while
  `scripts/check_structure.py:74` already declared all nine in `CODE_ROOTS` —
  three unreconciled scope lists. Outside the gated two sat 6,571 Python lines
  (58% of the repo's Python) and **101 ruff errors**, among them a `B904` at
  `runtimes/langgraph_adapter.py:158` that breaks keel's own *gate-tier*
  `exception-chaining` practice: `ruff check --select B904 runtimes` reports it
  while `ruff check src tests` said *All checks passed!*. An agent told "let the
  gate decide done" was being lied to across most of the repo. `lint-py`/`fmt`
  now use `$(wildcard $(CODE_ROOTS))` — the wildcard because ruff exits 1 with
  `E902 No such file or directory` on a root copier pruned downstream — and
  `typecheck-py` passes mypy **no paths at all**, since an explicit path argument
  overrides `[tool.mypy] files` and would have made widening the config inert.
  Ruff is now clean over all nine roots: of the 101, 41 T201 entrypoint prints
  became declared per-file ignores, 55 were fixed in code, 5 carry a reasoned
  inline `# noqa`.
- mypy checked 19 files and now checks 36: `files = ["src"]` →
  `["src", "models", "demo", "agents"]`, with `explicit_package_bases` and
  `mypy_path` (without the first mypy does not start at all) and per-module
  overrides that relax only measured flags — never `strict = false`. Full strict
  over all nine roots is 1,411 errors, so the remaining roots are declared, with
  a measured cost and a removal condition each, in `config/practices.json`
  `rulesets.mypy.ratchet`; a test fails if a code root is in neither place, so a
  root can no longer be silently unmentioned.
- `make lint-fe` / `make typecheck-fe` printed *"npm not found; skipping"* and
  then hard-failed anyway: each recipe **line** is its own shell, so the guard's
  `|| exit 0` ended only the guard, and make ran the loop on the next line into
  `npm: command not found` (measured on the old Makefile with an empty PATH:
  exit 2 at `Makefile:75`). The Makefile ships verbatim, so every generated
  project's `make lint` broke on any host without node. Guard and loop are one
  logical line now, and `FE_APPS` is tested first so a `frontend_stack: none`
  project is silent rather than told about npm.
- `scripts/cdmon_sync.py` could not be **parsed** by the interpreter its own
  pre-commit hook runs it with. `language: system` hooks exec the committing
  shell's ambient `python3` (3.6.8 here), where line 8's
  `from __future__ import annotations` is `SyntaxError: future feature
  annotations is not defined` — the flagship external-tool adapter aborted the
  commit instead of skipping gracefully. Deleting that line alone is not enough:
  the evaluated `list[str] | None` annotation then raises `TypeError` at def
  time. Both are gone; `/usr/bin/python3 scripts/cdmon_sync.py --check` exits 0.
- The gate's config readers could not tell **absent** from **unreadable**. A
  present-but-malformed `config/practices.json` turned check_K, check_L and
  check_M — the meta-gate whose whole job is proving `pyproject.toml` cannot
  silently loosen the declared lint/type policy — into no-ops while
  `check_structure.py` still printed `0 error(s)` and exited 0 (reproduced at
  `fca1ae5`). One shared reader pair makes the split once: absent stays silent
  (copier legitimately prunes files), unreadable is reported once and exits 1.
  All 16 blind `except Exception:` clauses in `check_structure.py` are gone — 8
  deleted with the readers they guarded, 8 narrowed to two named exception
  tuples.
- `scripts/agent_surface/generate_aad_schema.py --check` reported success on a
  broken model: `except Exception: return 0` was meant as a graceful skip for an
  old interpreter or absent pydantic, but it also swallowed every real failure,
  so the AAD drift guard was green while verifying nothing. Only `ImportError`
  and `SyntaxError` — the two ways the *environment* cannot run the check — still
  skip; anything else means the check ran and the model is broken, and now fails
  in both modes.
- `pyproject.toml.jinja` had drifted from `pyproject.toml`, and a generated
  project's pyproject comes **entirely** from the twin (`_render_path` returns
  early for any path with a `.jinja` sibling). Since `Makefile` ships verbatim,
  widening one side and not the other handed every descendant a gate red on
  arrival — measured in a freshly generated project: **40 T201 errors, exit 1** —
  plus a mypy scope narrower than keel's own (19 files against 36) and therefore
  silently green, re-opening downstream the exact blind spot this pass closes.
  The twin was regenerated from `pyproject.toml` and is now text-pinned to it.
- `api/rest_fastapi/showcase_api.py`'s `/api/wiki/node` handler bound its query
  parameter to the builtin name `id` (ruff `A002`). Renamed to `node_id` with
  `alias="id"`, so the published wire name is unchanged: `export_openapi.py
  --check` still says *openapi.json up to date* and the committed contract is
  byte-identical.

### Added
- `tests/integration/test_copier_update.py` — the upgrade channel ADR-0004 chose
  copier for, tested for the first time: generate → commit downstream work →
  evolve the template → `copier update`, asserting new files arrive, edits land,
  downstream work survives, the `.gitignore` divergence twin holds, `_commit`
  advances, no conflicts are left, and the upgraded tree still passes its own gate.
- `tests/integration/test_copier_generator_contract.py` — pins the `make new`
  recipe and the CI wiring above so neither can silently regress.
- `tests/integration/test_gate_scope.py` (16 tests) — the gate's scope read off
  the real `make -n` expansions, the real `pyproject.toml` and the real
  `.pre-commit-config.yaml`: `lint-py`/`fmt` must cover every `CODE_ROOTS` entry
  (*imported* from `check_structure.py`, never re-typed, so the lists cannot
  drift), `typecheck-py` must pass no paths, mypy's scope and the declared
  ratchet must partition `CODE_ROOTS`, ruff must be clean over it, the FE gates
  must skip-not-fail without npm *and* still fail on a real frontend failure, and
  every bare-`python3` pre-commit entry must be legal at the documented 3.6
  floor. Verified to bite: narrowing the Makefile's `CODE_ROOTS` back to
  `src tests` turns two of them red.
- `tests/unit/scripts/test_config_loaders.py`, `tests/unit/scripts/test_generate_aad_schema.py`
  and `tests/unit/runtimes/test_langgraph_adapter.py` — the absent-vs-unreadable
  split (including that a JSON `null` manifest stays a *shape* error), the AAD
  drift guard failing on a broken model while still skipping on a broken
  environment, and the pause signal keeping its `__cause__` (removing the
  `raise ... from p` turns that one red again).
- Two tests in `tests/integration/test_copier_generation.py`: a freshly generated
  project must be lint-clean over the roots **its own** shipped `Makefile`
  declares, and `pyproject.toml.jinja` is pinned as text to `pyproject.toml`
  except the three per-answer fields. (General twin parity for all five twins is
  still pass 5 of the hardening plan.)

### Known limitation
- A project made with `make new` records the template's machine-local absolute
  path, so `copier update` works on that machine only. Generate from
  `gh:JuanSync7/project-keel` for a project you intend to share.
- `make fmt` now covers all nine code roots, but it is not part of `make verify`
  and has evidently never been run: `ruff format --check` reports 104 of 111
  files as *would reformat*. The first person to run it reformats the whole
  corpus, including the five `scripts/` files constrained to 3.6-legal syntax.

## [0.1.0] — 2026-08-04
First named version. Everything below existed before this tag; the tag exists so
a descendant can state which keel it came from and upgrade to a known-good ref
instead of a bare SHA (`docs/design/keel-hardening-plan.md`, pass 1).

### Fixed
- Generated projects now **track** their own `.copier-answers.yml`. Keel's
  `.gitignore` shipped verbatim and ignored it, so while `copier update` worked
  in the directory copier created, any `git clone`, teammate checkout or CI run
  had no answers file and update failed with "Cannot update because cannot
  obtain old template references". A `.gitignore.jinja` divergence twin drops
  that line downstream; keel keeps ignoring its own copy.
- `_min_copier_version: "9"` — an old copier now fails with copier's own message
  instead of a mystery render error.

### Added
- ADR-0005 (proposed): declare the external environment in
  `config/environment.json` — the parts a container cannot reach.
- `docs/design/keel-hardening-plan.md` — the bounded convergence plan.

## Template foundations (pre-0.1.0)
- Initial template.
- Deterministic-check suite: `jobs/check_corpus.py` (corpus integrity + build
  reproducibility), `check_structure.py` checks A–M (incl. CLAUDE.md↔AGENT.md
  symlinks and the coding-practice gates), and OpenAPI / AAD drift `--check`s.
  Unified via `make check-all`; catalogued in `docs/guides/deterministic-checks.md`;
  wired into pre-commit + CI.
- Project generation: a `copier` template (the repo root is the template) —
  one command runs an interactive Q&A into a tailored skeleton, and `copier
  update` pulls later template improvements. Replaced the hand-authored
  `scaffold.py` generator + its byte-synced embeds + `check_scaffold_sync`
  (parity-proven first; ADR 0004). The Q&A tailors the project name (→ manifest,
  `pyproject` slug, README title), minimum Python, frontend stack (un-chosen stacks
  pruned), add-on transports (`grpc`/`edge_nginx` pruned unless selected; REST+MCP
  are the always-shipped foundation), and domain practice profiles.
- Showcase demo: `backend.showcase` read model + thin REST router
  (`api/rest_fastapi/showcase_api.py`) + a minimalist Astro docs/wiki site
  (`src/frontend/astro`) that renders the template live from the backend.
  See `docs/guides/showcase-site.md`; run with `make run-api` + `make run-web`.
