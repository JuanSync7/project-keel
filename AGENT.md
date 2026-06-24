---
title: Root agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Global rules for any agent working in this repo.
id: agent
created: 2026-06-17
updated: 2026-06-22
visibility: internal
canonical: true
---
# Agent rules — repo root

This file (`AGENT.md`) is the **canonical, vendor-neutral** agent-rules
file. `CLAUDE.md` is a symlink to it, so Claude Code and any other agent
tool read the same rules. Edit `AGENT.md`, never the symlink.

Read **`CONVENTIONS.md`** before doing structural work; it is the source
of truth for labeling and the directory taxonomy. Each directory's own
`AGENT.md` adds local rules that override these where more specific.

## Always
- **State new features vendor-agnostically.** When you propose or add a
  capability, design it so no single vendor/provider/tool is baked in:
  put the doer in `scripts/`/`agents/`, keep provider choice behind
  `models/`, and confine vendor-specific wiring to thin adapters
  (see CONVENTIONS §7). Name the neutral concept first; a vendor is one
  interchangeable option.
- **Respect the `__init__.py` boundary.** Import a package's public
  symbols from the package, never from its private (`_*`) submodules.
  When you add a public symbol, add it to `__all__` and re-export it.
- **Label new dirs.** A new directory is not done until it has a
  `README.md` and `CLAUDE.md` with valid frontmatter (see CONVENTIONS).
- **Put code where the taxonomy says.** Transport layers (`api/`,
  `mcp/`) must stay thin and call into `src/`; never duplicate domain
  logic there. Triggers (hooks/schedules) stay thin over
  `scripts/`/`agents/`.
- **Keep `config/project.json` true.** It is the machine-checked manifest
  of project facts (chosen frontend stack, backend language/version,
  enabled transports); update it when those change — `check_structure.py`
  enforces it (see CONVENTIONS §15).
- **Mirror unit tests, not the rest.** A new `src/<pkg>/<mod>.py` gets a
  matching `tests/unit/<pkg>/test_<mod>.py`. Integration/e2e tests go
  by scenario.
- **Work test-first (TDD).** For new or changed `src/` behavior, drive it
  from its mirror test: write/extend the test until it fails for the right
  reason, make it pass with the smallest change, then refactor with the
  suite green. A public symbol with no test is unfinished. (A convention you
  follow — not a structural check; the gate is `make verify`.)
- **Slice work vertically.** Decompose a task into end-to-end slices — each one
  capability through the layers (`app → {frontend, backend} → shared`, plus
  transports/agents), independently verifiable — not one horizontal layer at a
  time. Each convergence pass should complete one slice.
- **Converge in bounded passes.** When a change spans more than one file or
  can't be finished and verified in a single edit, write the plan down first,
  then each pass: do the next slice (one capability end-to-end), run
  `make verify`, and commit. Re-derive the worklist from the repo each pass
  (search before assuming something is unbuilt) and delegate heavy reads to a
  subagent. Stop at the plan's done-condition — or at a pass cap (default 5 if
  the task gives none), and report done-vs-remaining instead of starting another
  pass.
- **Cover user-facing flows end to end.** A new route, page, or transport
  endpoint gets a `tests/e2e/` scenario that drives it through its public
  surface. (The loops above are disciplines for *you*; the playbook is
  `docs/guides/dev-loops.md`, the rule is CONVENTIONS §17.)
- **Let the gate decide "done."** A step is finished when `make verify` (or
  the smallest sufficient `make` target) exits green — never on self-report.
- **Keep docs by purpose**, not by source file (except `docs/reference/`).

## Never
- Reach into another package's internals to "save an import".
- Add business logic to `api/`, `mcp/`, `scripts/`, or `app/`.
- Bake a vendor/provider name into a doer — that belongs in a thin adapter.
- Report work complete (or advance a loop) on your own assessment instead of
  a green `make verify`.
- Commit secrets to `config/` — only defaults and `*.example.*`.
