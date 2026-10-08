---
title: App (composition root) — OPTIONAL
kind: package
layer: app
status: template
owner: TBD
public_api: src/app/__init__.py
tags: []
summary: OPTIONAL single-process composition root. Delete it for client-server web apps, and set config/project.json layers.app to null with it.
id: src-app-readme
created: 2026-06-17
updated: 2026-10-08
visibility: internal
canonical: true
---

# App (composition root) — OPTIONAL

OPTIONAL single-process composition root. Delete it for client-server web apps, and set config/project.json layers.app to null with it.

**Optional. Keep it only if one process wires the layers together.**

`app/` is a *composition root*: dependency injection, config loading,
CLI/`__main__`, server bootstrap. **No business logic** — it only
wires `backend`/`frontend`/`shared` and starts them.

Two archetypes decide whether you need it:

| Project | Entrypoint | Keep `app/`? |
|---------|-----------|--------------|
| **Client-server web** (separate FE build + BE server) | FE = its own build; BE = its server (`api/`/`backend/`) | **No** — nothing imports both in one process. Delete this dir. |
| **Single-process** (CLI, service, library) | one `__main__`/`bin` that wires everything | **Yes** — that wiring *is* this dir. |

genbuild is the single-process kind (a CLI, no `frontend/`), so it
has an `app/`-equivalent in `bin/`. A React+API product is the first
kind, so it has no `app/`.

`make run` runs the module config/project.json `layers.app` names
(`scripts/run_app.py`), here `{"path": "src/app", "module": "app"}`, and
`make smoke` runs `make run` (`tests/smoke/test_app_runs.py`) and requires
exit 0. Moving the composition root means changing `layers.app`; check_H
errors when its path or module stops matching the tree.

**Delete this dir** and three entries change with it, or the gate goes red:
set config/project.json `layers.app` to `null` (so `make run` says there is
no composition root instead of failing to import one); add `smoke` to
`make_targets.empty_test_selections` with a reason such as `"no composition
root to smoke"` (the smoke test skips, and a tier where zero tests ran fails
unless declared); and add `run` to `make_targets.effect_proof_skip` with the
honest reason `"no composition root (layers.app is null)"` (the effect sweep
would otherwise run a target that now exits 2). Give `smoke` a real test when
the project has a surface to smoke, and drop the declaration: once a test of
that marker runs, the entry is stale and fails the run.

If the composition root becomes a long-running server, `make run` no longer
exits, so `tests/smoke/test_app_runs.py` and the effect sweep would wait on it
until their timeouts.
Replace the smoke test with one that starts the server, waits on its own
readiness probe, and stops it, and move `run` to
`make_targets.effect_proof_skip` with that reason.
