---
title: src — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside src/.
id: src-agent
created: 2026-06-17
updated: 2026-06-22
visibility: internal
canonical: true
---

# Agent rules — `src/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- **Every export crosses an `__init__.py`.** Add public symbols to `__all__` and re-export them; keep implementation in `_*` modules.
- **Drive new behavior with its test (TDD).** Before adding or changing a public symbol, write/extend its `tests/unit/...` mirror so it fails first, then make it pass, then refactor with the suite green (CONVENTIONS §17).
- Respect the dependency direction: `app → {frontend, backend} → shared`. No back-edges, no FE↔BE direct imports.
- `shared/` must stay framework-free and import nothing else in `src/`.
- Each package needs a `shared/` only if it has domain-shared code, and a `util/` only if it has generic helpers — don't create empty ones.
