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

### Added
- `tests/integration/test_copier_update.py` — the upgrade channel ADR-0004 chose
  copier for, tested for the first time: generate → commit downstream work →
  evolve the template → `copier update`, asserting new files arrive, edits land,
  downstream work survives, the `.gitignore` divergence twin holds, `_commit`
  advances, no conflicts are left, and the upgraded tree still passes its own gate.
- `tests/integration/test_copier_generator_contract.py` — pins the `make new`
  recipe and the CI wiring above so neither can silently regress.

### Known limitation
- A project made with `make new` records the template's machine-local absolute
  path, so `copier update` works on that machine only. Generate from
  `gh:JuanSync7/project-keel` for a project you intend to share.

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
