---
title: app — agent rules
kind: rules
layer: app
status: template
owner: TBD
summary: Local agent rules inside src/app/.
id: src-app-agent
created: 2026-06-17
updated: 2026-10-08
visibility: internal
canonical: true
---

# Agent rules — `src/app/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- OPTIONAL. If frontend and backend are separate deployables (client-server web), there is no single-process root — delete this dir, and in the same change make three config/project.json edits, or the gate goes red: set `layers.app` to `null` (check_H errors on a `layers.app.path` that does not exist), declare `smoke` in `make_targets.empty_test_selections` (its one test skips without a composition root, and a tier that ran zero tests fails), and add `run` to `make_targets.effect_proof_skip` (`make run` exits 2 with no composition root). `src/app/README.md`, under "Delete this dir", gives the reasons to write.
- Wiring only — construct concretes, inject them via `contracts`, start the process. No domain logic.
- This is the ONLY layer allowed to import from both `frontend` and `backend`.
- Read config from `config/`; never hardcode environment specifics.
