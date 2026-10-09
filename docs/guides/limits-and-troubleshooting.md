---
title: Limits and troubleshooting
kind: doc
layer: n/a
status: template
owner: TBD
tags: [limits, waivers, exit-codes, troubleshooting, guide]
summary: What adopting keel costs, the risks its rails leave open, the checks that pass by skipping, what no gate can see, every waiver a project may use, every exit code the gate's scripts return, and the symptom-to-fix list for the failures a newcomer meets first.
id: docs-guides-limits-and-troubleshooting
created: 2026-10-09
updated: 2026-10-09
visibility: internal
canonical: true
---

# Limits and troubleshooting

This guide says where keel stops. Read it before you adopt keel, and again when
a gate refuses you. `tests/integration/test_doc_drift.py` holds two of its
sections to the code: the waiver table names every waiver the checkers grant,
and the exit-code table names every code a script in `make verify` returns.

## What adopting costs

- **A Python backend.** The gate (`scripts/check_structure.py`), the jobs under
  `scripts/jobs/` and the test suite are Python. A project with no Python code
  still runs them, and gains little from them.
- **A fixed top-level layout.** Every top-level directory is a CONVENTIONS §2
  taxonomy row or is declared in `config/project.json`
  `structure.extra_toplevel`; check_B refuses any other.
- **Frontmatter on every governed document.** check_A and check_F refuse a
  document without the labels CONVENTIONS §1 defines, and
  `scripts/jobs/review_docs.py --strict` refuses a stale `updated:`.
- **Two interpreters.** pre-commit runs the gate on a bare `python3`; the
  rest of `make verify` runs on the project interpreter that `pyproject.toml`
  `requires-python` sets.
- **Taking updates.** keel's fixes reach a project only through
  `copier update`, which rewrites template files and can conflict with your
  edits to them (`generate-and-upgrade.md`).

## Residual risks

- **The child-process allowlist is not a sandbox.** `scripts/child_env.py`
  removes the default of inheriting every variable; a child running as the
  same user can still read credential files, use the network and read its
  parent's environment through `/proc`
  ([ADR-K-0012](../adr/keel/K-0012-child-process-environment-allowlist.md),
  "What this is not"). A proxy URL that embeds a credential is refused unless
  `child_env.credentialed_values` names it (CONVENTIONS §7).
- **The allowlist covers Python spawns only.** check_X holds every Python
  `subprocess` call to `env=build_child_env(...)`. A recipe that runs `npm` or
  a shell command hands that program make's whole environment.
- **An effect label is a claim.** A make target's `[local]`, `[tree]`,
  `[read]`, `[cost]` or `[write]` label is what its author says it does;
  `tests/integration/test_make_target_effects.py` measures each gate target
  against its label, and `scripts/run_make_target.py` refuses a target outside
  `make_targets.gate_effects`
  ([ADR-K-0011](../adr/keel/K-0011-make-target-effect-labels.md)).
- **The gate runner sees only what git lists.** `scripts/run_make_target.py`
  fails a run that changed a tracked or untracked-and-unignored file; a write
  to an ignored path, or outside the work tree, passes.

## Checks that pass when they skip

Each item below exits 0 when the thing it judges is absent. Each is queued for
a decision on whether it should fail instead.

- `scripts/check_python_version.py` assumes the floor `_FALLBACK = (3, 10)`
  when `pyproject.toml` is absent or declares no `requires-python`. Queued for
  a decision.
- A missing `config/project.json` is a WARN, not an error, in the gate's
  manifest check, so every manifest-driven check is silent. Queued for a
  decision.
- check_K is silent when `config/practices.json` declares no
  `tokens.config_marker`. Queued for a decision.
- `make lint-fe` and `make typecheck-fe` exit 0 when no frontend app is
  found, when `npm` is not installed, or when an app has no `node_modules`.
  Queued for a decision.
- `make check-openapi` and `make check-aad` skip when FastAPI or pydantic is
  not installed. Queued for a decision.
- `scripts/cdmon_sync.py` exits 0 when the `cdmon` program or its config is
  absent; otherwise it passes cdmon's exit code through. Queued for a decision.
- A `.py` file that does not parse is a WARN in check_D and the other checks
  that read the syntax tree, so its imports go unchecked. Queued for a
  decision.
- `scripts/jobs/check_corpus.py` passes when no local corpus has been built;
  it then judges a fresh build only. Queued for a decision.
- `tests/integration/test_release_identity.py` and
  `tests/integration/test_work_trailers.py` skip without git. Queued for a
  decision.

## What the gates cannot see

- **check_D's scope.** check_D flags an import of any module whose name has a
  leading-underscore segment, so it also flags the stdlib `_thread`, the
  `_pytest` internals and a package importing its own private module by its
  absolute name. It has no waiver; import from the public package instead.
- **Dead registry keys.** `practices.schema_version` and
  `tokens.owned_error_marker` in `config/practices.json` are read by no code.
- **Display-only profile fields.** `profiles.*.activates` is read only by the
  showcase read model (`src/backend/showcase/_repo.py`), and a profile's tags
  only by `agents/practice_refactor/_brain.py`; no gate enforces either.
- **Two defaults each.** `models.default` and `runtimes.default` in
  `config/project.json` are checked for shape; the constants the code falls
  back to, `DEFAULT_MODEL` in `models/registry.py` and `DEFAULT_RUNTIME` in
  `runtimes/registry.py`, are not compared with them.
- **Example settings files with no loader.** `config/default.example.toml`,
  `config/rag.example.toml` and `models/config/default.example.toml` are read
  by no code; a typo in a copy of one goes unnoticed.

## I disagree with a rule

Every way to switch a rule off is in the table below. Each one is a recorded
decision in the tree, so a reviewer sees it.

| Waiver | Where it lives | What it switches off |
|--------|----------------|----------------------|
| `practice-ok` | a `#` comment that names it: on the flagged Python line, or in `pyproject.toml` on any line of the flagged ruleset entry | one finding on that line of `scripts/check_practices.py`, check_J, check_K (frozen config), check_L (tensor parameters) or check_M (ruleset parity with `config/practices.json`) |
| `generic-ok` | a `#` comment that names it, on the flagged line | one answer-key finding of `scripts/check_generic.py` on that line |
| `unattended_vars` | `config/project.json` `make_targets` | names the variables under which `WRITE_GUARD` refuses a `[write]` target; a name left out lets that caller write |
| `gate_runner_var` | `config/project.json` `make_targets` | names the variable the gate runner sets so `WRITE_GUARD` refuses a `[write]` target |
| `gate_effects` | `config/project.json` `make_targets` | names the effect labels the gate runner accepts; a wider list lets it run a wider target |
| `write_shapes` | `config/project.json` `make_targets` | names the target-name suffixes check_W requires to be `[write]`; an empty list requires none |
| `write_shape_exempt` | `config/project.json` `make_targets` | keeps a write-shaped target's narrower label, with the reason ([ADR-K-0015](../adr/keel/K-0015-write-shape-exemptions-and-guarded-recipe-converse.md)) |
| `area_dir` | `config/project.json` `make_targets` | names the directory of `<area>.mk` makefiles; `null` turns areas off |
| `effect_proof_skip` | `config/project.json` `make_targets` | keeps a `[local]` target out of `tests/integration/test_make_target_effects.py`, by name and reason |
| `effect_proof_kept_dirs` | `config/project.json` `make_targets` | names the directories that sweep keeps under its fresh `HOME`; a write under one is not seen |
| `empty_test_selections` | `config/project.json` `make_targets` | names a pytest marker a `-m <marker>` recipe may select zero tests of, with the reason |
| `gate_vars` | `config/project.json` `make_targets` | names the variables a caller may pass the gate runner |
| `ignore_errors` | a `[[tool.mypy.overrides]]` table in `pyproject.toml` | every mypy error in the named modules; the gate refuses one `rulesets.mypy.overrides` does not declare |
| `rulesets.ruff.deferred` | `config/practices.json` | ruff rules held back from the gate |
| `rulesets.ruff.per_file_ignores` | `config/practices.json` | ruff rules for named files |
| `rulesets.mypy.overrides` | `config/practices.json` | mypy settings for named modules |
| `rulesets.mypy.ratchet` | `config/practices.json` | the strict mypy flags a module has not reached yet |
| `deferred` | a practice's `status` in `config/practices.json` | the whole practice, until its status is `on` |
| `structure.extra_toplevel` | `config/project.json` | check_B for a top-level directory the project adds |
| `structure.project_checks` | `config/project.json` | nothing: it adds the project's own checks |
| `work_naming.adoption_boundary` | `config/project.json` | check of commit trailers before the named commit |
| `doc_drift.history_paths` | `config/project.json` | every rule of `tests/integration/test_doc_drift.py` for a Markdown file under a listed prefix |
| `child_env.names` | `config/project.json` | the allowlist for a named variable: every child of `scripts/child_env.py` receives it |
| `child_env.prefixes` | `config/project.json` | the allowlist for every variable that starts with a listed prefix |
| `child_env.credentialed_values` | `config/project.json` | the credential refusal for a named variable, with the reason its value may carry a user part |
| `child_env.credential_value_patterns` | `config/project.json` | names the patterns a value is refused for; a pattern left out lets a matching value through |
| `child_env.login_name_schemes` | `config/project.json` | the credential refusal for a user part with no password in a URL of a listed scheme |
| `child_env.repo_context_names` | `config/project.json` | names git's repository-context variables, which a child never receives unless its call asks; a name left out is copied like any other |
| `child_env.config_injection_names` | `config/project.json` | names the variables that hand git its `-c` settings, which a child never receives; a name left out is copied like any other |
| `child_env.config_injection_prefixes` | `config/project.json` | the same, for the numbered families under a listed prefix |

check_X (every Python spawn goes through `build_child_env`) and check_D
(private imports) have no waiver; what `build_child_env` lets through is set by
the `child_env` keys above. An edit to `scripts/check_structure.py` itself conflicts on the next
`copier update`. No migration reads that module, so the update finishes and
leaves the conflict markers in it, and `make verify` cannot run the gate
until you resolve them
([ADR-K-0014](../adr/keel/K-0014-project-owned-structure-checks.md);
`tests/integration/test_copier_project_checks.py`). So a
project adds its own checks under `structure.project_checks`, and proposes a
change to a template check upstream as an issue or a pull request.

## Exit codes

The scripts `make verify` runs, and what each exit code means.

| Script | Exit | Meaning |
|--------|------|---------|
| `scripts/check_structure.py` | 0, 1, 2 | 0: no error. 1: at least one error, each printed. 2: a bad `--root` |
| `scripts/check_python_version.py` | 0, 1 | 0: the interpreter meets `requires-python`. 1: it does not, and the message names the floor |
| `api/rest_fastapi/export_openapi.py` | 0, 1 | 0: the committed `openapi.json` matches the app, or FastAPI is absent. 1: it is stale or unreadable |
| `scripts/agent_surface/generate_aad_schema.py` | 0, 1 | 0: the committed schema matches the model, or pydantic is absent. 1: it is stale or unreadable |
| `scripts/jobs/check_corpus.py` | 0, 1 | 0: the corpus is well-formed and its build is reproducible. 1: it is not, and each error is printed |
| `scripts/cdmon_sync.py` | 0, passes through | 0: cdmon or its config is absent. Otherwise cdmon's own code passes through |

Three more codes come from the tools around these scripts:

- **pytest exit 5** means the run selected zero tests. `tests/selection_guard.py`
  fails such a run unless its `-m` marker is named in
  `make_targets.empty_test_selections`.
- **argparse exit 2** means a script was called with an argument it does not
  take; the usage line names the right ones.
- **make exit 2** means make itself failed: a recipe returned non-zero, or the
  target does not exist. The line above it names the recipe's own code.

## Symptom, cause, fix

| Symptom | Cause | Fix |
|---------|-------|-----|
| pre-commit fails with a syntax error before any check runs | the bare `python3` is older than the gate supports | install a newer `python3`, or run `make check` with the project interpreter |
| `make verify` stops on a missing `pytest`, `ruff` or `mypy` | the `dev` extra is not installed | `.venv/bin/pip install -e ".[dev]"` |
| check_B names a directory you just added | it is not a taxonomy row | add its name to `structure.extra_toplevel` and give it a `README.md` and `CLAUDE.md` |
| check_W names a make target | its `##` help does not open with an effect label | open the help with `[local]`, `[tree]`, `[read]`, `[cost]` or `[write]` |
| `make check-docs` names a stale `updated:` | a document changed without its stamp | `make restamp-docs` |
| `make new` refuses | no `DEST`, the template is not a git checkout, or its tree is dirty | see `generate-and-upgrade.md`; `ALLOW_DIRTY=1` overrides the dirty tree only |
| a test target exits 5 | it selected zero tests | add tests, or name its marker in `make_targets.empty_test_selections` |
| `copier update` stops with exit 2 naming files | a migration found conflict markers in a file it imports, or in a fixed project file one of its modules declares reading (`config/project.json`, the `Makefile`) | resolve each named file, then run the command the message prints: under an update it is `<python> scripts/jobs/finish_update.py`, which runs the migrations copier never reached |
| a command stops with `config/project.json holds a merge-conflict hunk at line N` | an update left the manifest conflicted, so `scripts/child_env.py` has no allowlist and lets no child start | resolve the hunk, then finish the update as `generate-and-upgrade.md` says |
| a job stops on `Expecting property name enclosed in double quotes` after `copier update` | the update went to a template release whose migrations read `config/project.json` without checking it for conflict markers, and the manifest was conflicted; copier ran no later migration, and that release has no `scripts/jobs/finish_update.py` | resolve the file and `git add` it; copy `scripts/jobs/finish_update.py` from a newer keel checkout into the project, run `python scripts/jobs/finish_update.py --template <that keel checkout>`, delete the copied script (that release's `scripts/jobs/README.md` roster does not name it, so `check_structure.py` fails on it), then review and commit. On a release that has the check, the same conflict stops with the refusal row above instead, and `tests/integration/test_copier_job_conflict_refusal.py` keeps it so |
| `copier update` refuses the ref you named | it is older than the project's recorded `_commit` | update to a newer tag ([ADR-K-0009](../adr/keel/K-0009-release-identity-and-the-tag-ordering-rule.md)) |
| `make check-corpus` fails after you added documents | the local corpus is stale | `make site-data` |
