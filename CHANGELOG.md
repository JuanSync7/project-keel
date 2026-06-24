# Changelog

All notable changes. Format: Keep a Changelog.

## [Unreleased]
- Initial template.
- Deterministic-check suite: `check_scaffold_sync.py` (scaffold embeds stay
  byte-identical to live scripts), `jobs/check_corpus.py` (corpus integrity +
  build reproducibility), `check_structure.py` check I (CLAUDE.md↔AGENT.md
  symlinks), and an OpenAPI drift `--check`. Unified via `make check-all`;
  catalogued in `docs/guides/deterministic-checks.md`; wired into pre-commit + CI.
- Showcase demo: `backend.showcase` read model + thin REST router
  (`api/rest_fastapi/showcase_api.py`) + a minimalist Astro docs/wiki site
  (`src/frontend/astro`) that renders the template live from the backend.
  See `docs/guides/showcase-site.md`; run with `make run-api` + `make run-web`.
