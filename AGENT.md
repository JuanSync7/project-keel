---
title: Root agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Global rules for any agent working in this repo.
id: agent
created: 2026-06-17
updated: 2026-10-17
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
- **Write Python to the house pattern.** `docs/guides/python-style.md` is
  canonical: readability and loud failure modes outrank speed; every module
  carries the gated `title:`/`summary:` header the corpus reads (check_O);
  docstrings say what, comments say why — a comment carries a reason or a
  measurement, never a restatement. The mechanical floor is gated (ruff, mypy
  strict, check_O/E); the rest is what review holds you to.
- **Write documentation to the house pattern.** `docs/guides/doc-style.md` is
  canonical, and it is `python-style.md`'s twin: unambiguous before complete
  before short; one checkable claim per sentence, naming the mechanism that
  enforces it; a roster row or a tool spec says what a member is **not** for and
  names the sibling that is; a bare `§N` always cites `CONVENTIONS.md` and any
  other document is cited by name; `updated:` means touched. The mechanical
  floor is gated (checks A, F, P, Q, R, S, T, U and `make check-docs`); the rest
  is what review, and `make doc-review`, hold you to.
- **Make every writer safe to run twice.** A module that writes into the
  tree says so in its header and says what a second run does: `effect: writes`,
  `rerun:` from `fixed-point` / `append-only` / `unsafe`, and — for the strong
  claim — a `rerun_proof:` that resolves (check_V). Reach the fixed point by
  deriving rather than accumulating: whole files not appends, sorted iteration,
  canonical JSON, no wall-clock in the output, and an output path git either
  tracks or ignores. `docs/guides/idempotency.md` is
  canonical; the proof is a rung on its ladder — a `--check` target, a double
  build, or a case in `tests/integration/test_idempotence.py`.
- **Label every make target with its effect.** A `## `-annotated target
  opens its help with `[local]`, `[tree]`, `[read]`, `[cost]` or `[write]`
  (comma-joined in that order; `local` alone), covering what its prerequisites
  reach; a `[write]` recipe opens with `$(WRITE_GUARD)` (check_W). Run a gate
  through `scripts/run_make_target.py`, which runs only a target inside
  `config/project.json` `make_targets.gate_effects` and fails one that changed
  the tree. `docs/adr/keel/K-0011-make-target-effect-labels.md` is the decision.
- **Start a child process through the allowlist.** Pass
  `env=build_child_env(...)` from `scripts/child_env.py` to every subprocess;
  name a variable a child needs in `config/project.json` `child_env.names`, or
  an adapter's credential in `models.credential_env`, never in code (check_X).
  `docs/adr/keel/K-0012-child-process-environment-allowlist.md` is the decision; it
  is defence-in-depth, not a sandbox.
- **End every process through the exit helper.** A script's entry line is
  `finish(main())`, and `main` returns a member of `ExitCode` from
  `scripts/exit_codes.py`: `report(member, what failed, on which input, what
  to do next)` for a failure, `passthrough(...)` for a wrapped tool's status,
  read where the script ran the tool and never `main`'s own result or a
  literal.
  A module another project module imports raises or returns and never calls
  `fail` or `finish` outside its entry block; `passthrough` ends nothing.
  `tests/integration/test_exit_gate.py` fails any other exit and a blank
  message part. `make exit-codes` regenerates the exit-code table in
  `docs/guides/limits-and-troubleshooting.md`, and `make check-exit-codes`
  fails a stale one.
- **Read a configured value through the loader.** Read `config/project.json`,
  `config/practices.json` or a variable they declare through
  `scripts/config_loader.py` (`read`, `resolve`, `env`), and give a key its
  type and default in a `KEYS` row, never in a `.get(key, default)`; a config
  fault returns `report(ExitCode.CONFIG, ...)`.
  `tests/integration/test_config_reads_gate.py` fails a direct read that
  `config/project.json` `config_reads.allowed` does not excuse.
  `docs/adr/keel/K-0022-one-config-loader.md` is the proposed decision.
- **Respect the `__init__.py` boundary.** Import a package's public
  symbols from the package, never from its private (`_*`) submodules,
  `from pkg import _sub` included (check_D).
  When you add a public symbol, add it to `__all__` and re-export it.
  Imports flow up `config/project.json` `import_layers.order`: a lower
  layer never imports a higher one
  (`tests/integration/test_import_layers_gate.py`).
- **Label new dirs.** A new top-level directory is not done until it is a
  CONVENTIONS §2 row or declared in `config/project.json`
  `structure.extra_toplevel`, and has a `README.md` and `CLAUDE.md` with valid
  frontmatter. Every directory directly under `agents/` needs the same two
  files: each `agents/<name>/` (§13) and the shared `agents/tools/` (§10).
  check_B enforces both; no other nested directory is required to carry them.
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
- **Name the work you deliver.** Name a campaign `CMP-<n>` and a slice
  `CMP-<n>.S<m>` in a plan doc's slice table, and end the commit that delivers
  a slice with a `Slice: CMP-<n>.S<m>` trailer; a pass is counted, never named
  (CONVENTIONS §20, check_Z, tests/integration/test_work_trailers.py).
- **Cover user-facing flows end to end.** A new route, page, or transport
  endpoint gets a `tests/e2e/` scenario that drives it through its public
  surface, and names each endpoint it drives with `@pytest.mark.endpoint`;
  `tests/integration/test_e2e_coverage.py` fails an endpoint no scenario names
  and `config/project.json` `e2e.exempt` does not excuse with a reason. (The
  loops above are disciplines for *you*; the playbook is
  `docs/guides/dev-loops.md`, the rule is CONVENTIONS §17.)
- **Name the requirement a test is evidence for.** A requirement is a heading
  in a `kind: spec` document under `docs/specs/` that opens with an id, and a
  numbered criterion is a `- AC-<n>: <text>` line below it. Mark the test with
  `@pytest.mark.req("<id>")`, one criterion at a time: a bare requirement id
  never covers numbered criteria. `make trace`
  (`scripts/trace_requirements.py`) fails a unit no test names and
  `config/project.json` `traceability.gaps` does not excuse with a reason
  (`docs/specs/README.md`, CONVENTIONS §17).
- **Solve the class of inputs, not the example.** When a spec ships an eval, a
  golden set, or one failing case, build the capability that *computes* the right
  answer across the whole input space — name the general rule before you
  special-case, and never hardcode the sample's expected value in `src/` to make
  one check pass. If a change only makes the named case pass, it is a patch, not
  a fix. Treat fixtures as illustrations; if a literal truly is data, it lives in
  a `*_data.py` registry, not in logic. (Advisory only: `make advise` flags
  hardcoded answer keys; the gate stays `make verify`. See CONVENTIONS §18.)
- **Let the gate decide "done."** A step is finished when `make verify` (or
  the smallest sufficient `make` target) exits green — never on self-report.
- **Keep docs by purpose**, not by source file (except `docs/reference/`).

## Never
- Reach into another package's internals to "save an import".
- Add business logic to `api/`, `mcp/`, `scripts/`, or `app/`.
- Bake a vendor/provider name into a doer — that belongs in a thin adapter.
- Fit the solution to the eval — hardcode, special-case, or paste a test's
  expected value into `src/` logic instead of solving the general problem
  (CONVENTIONS §18).
- Report work complete (or advance a loop) on your own assessment instead of
  a green `make verify`.
- Run a `[tree]` or `[write]` make target unattended, or label a target
  narrower than what it does to get it past the gate runner — the label is the
  claim `tests/integration/test_make_target_effects.py` measures.
- Hand a child `os.environ` (directly or through `extra=`), or spawn with
  `os.system`/`os.popen`.
- Open a config file or read a declared variable outside
  `scripts/config_loader.py`, or bury a default in the code that reads it.
- Commit secrets to `config/` — only defaults and `*.example.*`.
