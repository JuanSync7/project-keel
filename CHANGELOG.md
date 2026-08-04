# Changelog

All notable changes. Format: Keep a Changelog.

Generated projects record the template ref they came from in
`.copier-answers.yml` (tracked, not ignored — see 0.1.0). Generate a **named**
version rather than a bare commit:
`copier copy --vcs-ref v0.1.0 gh:JuanSync7/project-keel my-project`.

## [Unreleased]

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
