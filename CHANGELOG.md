# Changelog

All notable changes. Format: Keep a Changelog.

## [Unreleased]
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
  (parity-proven first; ADR 0004).
- Showcase demo: `backend.showcase` read model + thin REST router
  (`api/rest_fastapi/showcase_api.py`) + a minimalist Astro docs/wiki site
  (`src/frontend/astro`) that renders the template live from the backend.
  See `docs/guides/showcase-site.md`; run with `make run-api` + `make run-web`.
