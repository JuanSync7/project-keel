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
updated: 2026-10-13
visibility: internal
canonical: true
---

# Limits and troubleshooting

This guide says where keel stops. Read it before you adopt keel, and again when
a gate refuses you. `tests/integration/test_doc_drift.py` holds two of its
sections to the code: the waiver table names every waiver the checkers grant,
and the exit-code table is the one `scripts/exit_code_table.py` generates from
the `ExitCode` enum and the scripts `make verify` runs.
Every setting a gate reads, with its default and its valid values, is a row of
the [settings reference](../reference/settings.md). Every feature, with its
own limits, is a row of the [feature catalogue](../reference/features.md).

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
- **The evidence record is evidence, not attestation.** `make verify` writes
  `.evidence/verify.json` (config/project.json `evidence.dir`) unsigned, in a
  directory any process of the same user can write. A consumer should match its
  `source.commit` and `source.tree_digest` to the tree it asks about. Three
  kinds of run leave an earlier record standing, because the latest run wrote
  none:
  - a run refused with exit 2 before any goal: a usage error, a malformed
    `--gate` or goal, a bad `evidence` block, or a record or report path git
    would list;
  - a dry run (`make -n`, `-q` or `-t`), which writes nothing by design;
  - a run whose interpreter cannot parse the driver at all
    (`scripts/gate_evidence.py` parses at Python 3.6).

- **The frontend suites count no test themselves.** `make test-fe-unit` and
  `make test-fe-e2e` judge by their runners' exit codes alone. A runner that
  finds zero tests exits non-zero, but a suite whose every test is skipped
  exits 0 in both runners, and the evidence record lists `test-fe` with
  `tests: null`, so nothing counts those skips. CI runs `make test`, which
  does not reach `make test-fe`, so a broken frontend suite does not fail CI.
- **The browser runner's version fixes the browser.** Each app pins
  `@playwright/test` exactly, and that version names the chromium revision the
  browser cache must hold. `tests/integration/test_gate_scope.py` holds every
  app, and each committed lockfile, to one exact pin; a bump to
  a version whose revision is not in the cache shows only when the journey
  runs, as the missing-browser row below.

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
- `make lint-fe`, `make typecheck-fe`, `make test-fe-unit` and
  `make test-fe-e2e` exit 0 when no frontend app is found, when `npm` is not
  installed, or when an app has no `node_modules`. Queued for a decision.
  With `node_modules` installed, a browser missing from the cache is red, not
  a skip.
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
- The REST half of `tests/integration/test_e2e_coverage.py`, and every
  scenario that uses the `rest_server` fixture in `tests/e2e/conftest.py`,
  skip when FastAPI or uvicorn is not installed; the MCP half still judges.
  CI turns the skip into a failure, because `tests/optional_deps.py` fails a
  surface named in `KEEL_REQUIRED_EXTRAS`, and CI names `transport`. Queued for
  a decision.

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
- **What an e2e scenario asserts.** `tests/integration/test_e2e_coverage.py`
  proves that a scenario names each endpoint with the `endpoint` marker. It
  does not prove the scenario asserts anything about the endpoint's result.
- **What a test that names a requirement asserts.** `make trace`
  (`scripts/trace_requirements.py`) proves that a collected test carries the
  `req` marker with a unit's id. It reads the marker from source and imports
  no test, so it does not prove the test asserts what the requirement says,
  and a skipped or always-passing test still covers its unit.
- **A marker `make trace` cannot see.** `scripts/pytest_markers.py` reads a
  marker call written as `<name>.mark.req(...)` or, after
  `from pytest import mark`, as `mark.req(...)`, on a collected test, a
  collected class or in a `pytestmark`. One reached through any other name
  (`m = pytest.mark`, `covers = pytest.mark.req`) or added at run time is not
  read by `make trace`, which neither counts nor reports it. A call it does
  see that sits on no collected test, a `pytest.param(..., marks=...)`
  included, is the finding `marker-unattached`.
- **What only pytest can decide about collection.** `make trace` reads source,
  so it does not see a class that inherits `__init__`, a `collect_ignore` in a
  `conftest.py`, an `--ignore` option or a collection hook.
  `tests/integration/test_requirement_traceability.py` does: it asks a child
  `pytest --collect-only` which collected tests carry which id and fails when
  that differs from what the reader found, an unseen alias included. That
  comparison runs in `make test`, not in `make trace`.
- **A refused `traceability` block leaves the last matrix standing.** The
  block names the matrix path, so when config/project.json `traceability` is
  refused (exit 2) `scripts/trace_requirements.py` writes and removes nothing
  and says so on stderr. The exit code is the verdict, not that file.
- **The traceability matrix is evidence, not attestation.** It is unsigned and
  sits in a writable, git-ignored directory, as the gate's evidence record
  does. The evidence record lists `trace` with `tests: null`: the verdict
  counts are in `traceability.matrix_path`, not in the record.
- **A server left behind by a killed run.** `tests/live_server.py` stops the
  REST server in a `finally`, and from a handler when SIGTERM or SIGHUP ends
  the run. A pytest killed by SIGKILL, or by the out-of-memory killer, runs
  neither, so its uvicorn process survives; find it with `ps -eo pid,args | grep uvicorn`.
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
| `exempt` | `config/project.json` `e2e` | lets one named endpoint through `tests/integration/test_e2e_coverage.py` with no scenario, with the reason; a stale, redundant or reasonless entry is red |
| `gaps` | `config/project.json` `traceability` | lets one named unit, a criterion or a requirement that has none, through `make trace` with no test, with the reason; an entry for a covered, undefined or malformed id is red, and a blank reason is refused |
| `no_requirements` | `config/project.json` `traceability` | lets a project with zero requirements through `make trace`, with the reason; red once a requirement or a `req` marker exists |
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

- **A replayed eval judges recorded answers, not today's model.** `make eval`
  runs the real doer and fails a case whose prompt changed, but it scores the
  response stored in the case. Whether the model still answers that way shows
  only in `make eval-live`, which is not a `make verify` goal. A case whose
  `recorded.source` is `authored` was written by a person, not answered by a
  model.
- **A crash before the eval config is read leaves the last report standing.**
  `scripts/run_evals.py` writes its `incomplete` placeholder only after it has
  imported the harness and read config/project.json `evals`. A doer that fails
  to import, such as a syntax error in `agents/triage`, ends the run with
  Python's exit 1, the same code as a failing suite, and the previous
  `<evals.report_dir>/<mode>.json` is not replaced. The gate still fails;
  read the traceback, not the report.
- **A refused `evals` block removes the last report instead of replacing it.**
  When config/project.json `evals` is refused (exit 2), `scripts/run_evals.py`
  cannot write a report, because the schema it would follow is part of what
  was refused. It deletes `<evals.report_dir>/<mode>.json`, and in live mode
  `<evals.report_dir>/live-candidates/`, when that path is git-ignored. When
  `evals.report_dir` itself is the refused key, it cannot find the report and
  says the earlier one may still stand; trust the exit code, not that file.
  `tests/integration/test_evals_gate.py` holds both cases.
- **The gate run's date trusts its caller, within a bound.**
  `scripts/gate_evidence.py` hands every goal the date the run began in
  `KEEL_GATE_RUN_DATE` (config/project.json `evidence.run_date.env`), and
  `scripts/jobs/review_docs.py` judges a touched document by it. Whoever sets
  that variable for a check can move the check's today back by
  `evidence.run_date.max_age_days` (`1`) days and never forward, so a document
  touched today and stamped yesterday passes that check. A committed
  document's stamp is still compared with its commit date, which the variable
  does not move. `SOURCE_DATE_EPOCH` moves today back without a bound
  ([ADR-K-0019](../adr/keel/K-0019-one-date-per-gate-run.md)).
- **A gate longer than the bound refuses, it does not guess.** A `make verify`
  that runs past `evidence.run_date.max_age_days` (`1`) days after it began has
  every later date check exit 2 naming the key. Raise the bound to fit the
  run; `tests/unit/scripts/test_run_date.py` holds the rule.
- **The eval config chooses where the model key goes.** `openai-compatible`
  accepts only an `api_key_env` that config/project.json
  `models.credential_env.openai-compatible` lists, so
  `evals.live.model_options` cannot name another variable to send. It still
  chooses `base_url`, but only among the hosts config/project.json
  `models.allowed_hosts.openai-compatible` lists, which ships empty; a
  redirect is refused, so the endpoint cannot move the key elsewhere. That
  list is defence in depth, not a sandbox: whoever can edit
  `config/project.json` can list a host of their choosing, an `http://`
  base_url is admitted only to a loopback address, and a listed name is
  trusted to resolve where DNS says
  ([ADR-K-0018](../adr/keel/K-0018-model-endpoint-host-allowlist.md)).
  `scripts/run_evals.py` refuses a report path that resolves
  through a symlink, and it checks once, before it writes: a symlink planted
  during the run is not seen. Where git is not installed, or no repository
  holds the project, it does not check the ignore rule, because there is no
  tree to dirty. A git command that ran and failed is refused with exit 2.
  `tests/unit/models/test_openai_compatible.py`,
  `tests/integration/test_evals_gate.py` and
  `tests/integration/test_evals_live_stub.py` hold the refusals.
- **The live cap counts calls, not money.** config/project.json
  `evals.live.max_calls` bounds how many cases one live run may send; the price
  of one call depends on the model, the endpoint and the prompt, and nothing
  here measures it. The evidence record lists `eval` with `tests: null`: its
  case counts are in `<evals.report_dir>/replay.json`, not in the record.

## Exit codes

Every keel script ends through `scripts/exit_codes.py`: `main` returns a member
of its `ExitCode` enum and the entry line is `finish(main())`.
`tests/integration/test_exit_gate.py` fails an exit written anywhere else.
`scripts/exit_code_table.py` writes the two tables between the marker lines
below. The first has one row per member, read from the enum. The second has one
row per script `make verify` runs, read from what that script's `main` can
return. `make exit-codes` regenerates both, and `make check-exit-codes`, a
prerequisite of `make check-all`, fails when either is stale. Do not edit
between the markers.

<!-- exit-codes:begin -->
| Exit | Name | Meaning | What to do |
|------|------|---------|------------|
| 0 | `SUCCESS` | it ran and found nothing wrong, or it skipped and said why | nothing |
| 1 | `FAILURE` | it ran and the answer is no: a check found something, or the work did not succeed | read the last stderr line, fix what it names, and run it again |
| 2 | `USAGE` | it refused before judging: wrong usage, bad config, or an input it could not read | correct the call or the input the last stderr line names, and run it again |
| 10 | `RED_RECORD` | every step it ran passed, and the record it wrote of the run says fail | read `reasons` in the record the last stderr line names, fix what they name, and run it again |
| 11 | `BACKEND_ABSENT` | the backend it was told to use did not answer, so nothing was judged | start or configure the backend the last stderr line names, and run it again |
| 130 | `INTERRUPTED` | it was interrupted before it finished | run it again; what it had written so far is not a result |

| Script | Exit |
|--------|------|
| `api/rest_fastapi/export_openapi.py` | 0, 1 |
| `scripts/agent_surface/generate_aad_schema.py` | 0, 1 |
| `scripts/cdmon_sync.py` | 0, passes through |
| `scripts/check_python_version.py` | 0, 1 |
| `scripts/check_structure.py` | 0, 1, 2 |
| `scripts/exit_code_table.py` | 0, 1, 2 |
| `scripts/gate_evidence.py` | 0, 2, 10, 130, passes through |
| `scripts/jobs/check_corpus.py` | 0, 1 |
| `scripts/run_evals.py` | 0, 1, 2, 11 |
| `scripts/trace_requirements.py` | 0, 1, 2 |
<!-- exit-codes:end -->

A failing script's last stderr line has three parts: `<what failed>: <on which
input>; <what to do next>`. `scripts/exit_codes.py` `report` refuses a blank
part. `passes through` means the script exits with the status of the tool it
wraps, which need not be a row of the first table.

The table below is written by hand and no test compares it with the code. It
says when each script returns each code.

| Script | When |
|--------|------|
| `api/rest_fastapi/export_openapi.py` | 0: the committed `openapi.json` matches the app, or FastAPI is absent. 1: it is stale or unreadable |
| `scripts/agent_surface/generate_aad_schema.py` | 0: the committed schema matches the model, or pydantic is absent. 1: it is stale or unreadable |
| `scripts/cdmon_sync.py` | 0: cdmon or its config is absent. Otherwise cdmon's own code passes through |
| `scripts/check_python_version.py` | 0: the interpreter meets `requires-python`. 1: it does not, and the message names the floor |
| `scripts/check_structure.py` | 0: no error. 1: at least one error, each printed. 2: a bad `--root` |
| `scripts/exit_code_table.py` | 0: the exit-code table between the markers is current. 1: it is stale, and each differing row is one stderr line. 2: it could not build the table: a missing or repeated marker, a bad `doc_drift` block, a guide reached through a symlink, or a script whose returns it cannot read |
| `scripts/gate_evidence.py` | 0: every goal passed and the record is green. 2: refused before any goal ran: a malformed `--gate` or goal, zero goals, a bad `evidence` block, a record or report path that resolves through a symlink or that git does not ignore, a git command that ran and failed, or a date in the `evidence.run_date.env` variable that is not a date, is later than the clock or is older than `evidence.run_date.max_age_days` allows. 10: every goal passed but the record is red: zero tests, a failed or errored test in the junit report of a goal that exited 0, no junit report, the tree changed during the run, the checks could not run, or the writer crashed. 130: interrupted, and the red placeholder record stays. Otherwise the first failing goal's code passes through |
| `scripts/jobs/check_corpus.py` | 0: the corpus is well-formed and its build is reproducible. 1: it is not, and each error is printed |
| `scripts/run_evals.py` | 0: every suite passed. 1: a suite failed: below `evals.threshold`, an errored case or a stale recording. 2: refused: a bad `evals` block, a malformed or empty dataset, a live run over `evals.live.max_calls`, a null or unknown `evals.live.model`, an `evals.report_dir` git does not ignore, or a git command that ran and failed. 11: the live backend is absent; the first case is `absent` and the rest `not-run` |
| `scripts/trace_requirements.py` | 0: every unit is `covered` or a `traceability.gaps` row, and there is no finding. 1: at least one finding, each one stderr line: an `uncovered` unit, a marker or gap id that is malformed or undefined, an unreadable or unattached marker, a redundant gap, or zero requirements with no reason. 2: it could not judge: a bad `traceability` block, a path reached through a symlink, a `matrix_path` git does not ignore, a repository git cannot read, an unreadable schema, spec or test file, a spec line that does not parse, a document under the specs root that defines a requirement without `kind: spec`, or a collection rule pytest could not give; or it could not write the matrix at `traceability.matrix_path` |

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
| a migration names `scripts/exit_codes.py` as conflicted and then stops with exit 1 on a `SyntaxError` traceback, or `scripts/check_structure.py` stops on that traceback alone | the conflicted file is the exit helper itself, which every script imports to end with a chosen status, so nothing can exit 2; a project that added its own `ExitCode` member is the one an update conflicts here | resolve the hunk in `scripts/exit_codes.py`, keeping your members and the template's, run `make exit-codes`, then run the command the refusal line prints |
| a command stops with `config/project.json holds a merge-conflict hunk at line N` | an update left the manifest conflicted, so `scripts/child_env.py` has no allowlist and lets no child start | resolve the hunk, then finish the update as `generate-and-upgrade.md` says |
| a job stops on `Expecting property name enclosed in double quotes` after `copier update` | the update went to a template release whose migrations read `config/project.json` without checking it for conflict markers, and the manifest was conflicted; copier ran no later migration, and that release has no `scripts/jobs/finish_update.py` | resolve the file and `git add` it; copy `scripts/jobs/finish_update.py` from a newer keel checkout into the project, run `python scripts/jobs/finish_update.py --template <that keel checkout>`, delete the copied script (that release's `scripts/jobs/README.md` roster does not name it, so `check_structure.py` fails on it), then review and commit. On a release that has the check, the same conflict stops with the refusal row above instead, and `tests/integration/test_copier_job_conflict_refusal.py` keeps it so |
| `copier update` refuses the ref you named | it is older than the project's recorded `_commit` | update to a newer tag ([ADR-K-0009](../adr/keel/K-0009-release-identity-and-the-tag-ordering-rule.md)) |
| `make check-corpus` fails after you added documents | the local corpus is stale | `make site-data` |
| `make verify` fails with `Error 10` though every goal passed | the evidence record is red for a reason no goal's exit reports: zero tests ran, pytest's report counts a failed or errored test that the test recipe ignored, pytest wrote no report, the tree changed during the run, or the checks or the writer crashed | read `reasons` in `.evidence/verify.json` (config/project.json `evidence.dir`) and fix what it names |
| `make verify` stops before any goal, naming `.gitignore` | git would list the evidence record, so writing it would change the tree | add config/project.json `evidence.dir` (`.evidence`) to `.gitignore` |
| `make verify` stops before any goal, naming `evidence.dir` and `through a symlink` | the record, its temporary file or a goal's junit report resolves through a symlink, so a write or the delete of a stale report could land outside the project | replace the symlink under config/project.json `evidence.dir` (`.evidence`) with a real directory inside the project |
| `make verify`, `make eval`, `make trace` or the gate runner stops with exit 2 quoting `git exited` and a status | git ran and failed: a corrupt repository, one git refuses as unsafe because another user owns it, or a broken git configuration. That is not "no git", so nothing was written | run `git status` in the project, repair what it names, and run the command again |
| `make verify` stops before any goal, or `make check-docs` exits 2, naming `KEEL_GATE_RUN_DATE` | the variable config/project.json `evidence.run_date.env` names holds a value that is not a date written `YYYY-MM-DD`, is later than the clock, or is more than `evidence.run_date.max_age_days` (`1`) days before it: a stale export in your shell, or a gate that ran longer than the bound | `unset KEEL_GATE_RUN_DATE` and run again; for a gate that outlasts the bound, raise `evidence.run_date.max_age_days` |
| `make verify` refuses naming `evidence.run_date.env` and `child_env.names` | the variable the run's date travels in is not on the child-environment allowlist, so no check below the driver would receive it | add the name to config/project.json `child_env.names`, or remove `evidence.run_date` to make every check read the clock |
| `make eval` fails with `stale-recording` and a case detail `prompt is now sha256:…, recorded sha256:…` | the doer now sends a different prompt than the one the case's response was recorded for, so the recorded answer no longer judges the code | re-record the case: run `make eval-live` and promote its candidate, or, for an authored case, copy the new hash from the detail into `recorded.prompt_sha256` after checking the response still fits (`evals/README_run.md`) |
| `make eval` refuses with exit 2 naming `path:line` | a dataset line breaks `config/evals/eval-case.schema.json` or a rule it cannot state: a repeated key or id, or a `recorded.sha256` that does not match the response | fix that line; compute hashes with `evals.prompt_sha256` and `evals.sha256_text`, never by hand |
| `make eval` or `make eval-live` refuses naming `evals.report_dir` and `is not git-ignored` | git would list the report, so writing it would change the tree | add config/project.json `evals.report_dir` (`.evidence/evals`) to `.gitignore` |
| `make eval` or `make eval-live` refuses naming `evals.report_dir` and `through a symlink` | the report, its temporary file or `live-candidates/` resolves through a symlink, so a write or the live run's delete could land outside the project | replace the symlink under config/project.json `evals.report_dir` (`.evidence/evals`) with a real directory |
| `make eval-live` refuses naming `models.credential_env` | `evals.live.model_options.api_key_env` names a variable the adapter is not declared to use, and the adapter would send that variable's value to `base_url` | name a variable listed in config/project.json `models.credential_env.openai-compatible` (`OPENAI_API_KEY`), or add the name there |
| `make eval-live` refuses, or `get_model("openai-compatible", ...)` raises `ValueError`, naming `models.allowed_hosts.openai-compatible` | the host and port of `base_url` match no entry in that list, which ships empty; the adapter sends its credential there, so it refuses before any request and before the credential is read | add the entry the message names (`host`, or `host:port` for a port other than the scheme's default) to config/project.json `models.allowed_hosts.openai-compatible`, as `models/README.md` describes |
| a live case fails with `answered with a redirect (HTTP 301)` (or another 3xx) | the endpoint at `base_url` redirects, and following it would send the Authorization header to a host the list never named | point `base_url` at the URL the endpoint serves from, and list that host if it differs |
| `make eval-live` refuses naming `evals.live.model` or `evals.live.max_calls` | the shipped model is `null` and the shipped cap is `0`, so no live run is approved | set both, and `evals.live.model_options`, as `evals/README_run.md` says; the cap must be at least the number of cases |
| `make test-fe-unit` fails with `No test files found, exiting with code 1` | the app's unit runner found no test under its `include` list; this is the intended red for a stack with zero tests | add a test of the app's own code under `src/`, named `*.test.ts` (`*.test.tsx` in react-vite) |
| `make trace` prints `trace: uncovered: 'REQ-0001#AC-2' (docs/specs/<spec>.md:<line>)` | no collected test carries `@pytest.mark.req` with that unit's id; a marker naming the bare `REQ-0001` does not cover a requirement that has numbered criteria | write the test and mark it with the unit's id, or add the id to config/project.json `traceability.gaps` with the reason |
| `make trace` prints `trace: marker-undefined-id` or `marker-malformed-id` with a test file and line | the marker names an id no spec defines, or text that is not `<prefix><digits>` or `<prefix><digits>#AC-<n>` under a prefix `traceability.id_prefixes` lists | correct the id; [`docs/specs/README.md`](../specs/README.md) gives the grammar |
| `make trace` prints `trace: marker-unattached` | the marker call sits where pytest reads it on no collected test: a helper, a test a later definition of the same name replaces, a class pytest does not collect (its name does not match, it defines `__init__` or `__new__`, or `__test__` is false), a `pytestmark` in a scope with no test, or a `pytest.param` | move the marker onto the test function or class pytest collects; rename a duplicated test |
| `make trace` prints `trace: marker-unreadable` | a marker argument is not a string literal (a name, an f-string, a keyword), or the marker is used with no call | pass each id as a string literal |
| `make trace` prints `trace: gap-redundant`, `gap-undefined-id` or `gap-malformed-id` | a `traceability.gaps` key names a unit a test now covers, a unit no spec defines (a bare requirement id over numbered criteria included), or text that does not parse | delete or correct that key |
| `make trace` prints `trace: no-requirements` or `stale-no-requirements` | no `kind: spec` document under `traceability.specs_root` defines a requirement and `traceability.no_requirements` is `null`; or it holds a reason while a requirement or a marker exists | write the first requirement, or set the reason; set it back to `null` once a requirement exists |
| `make trace` exits 2 naming a spec `file:line` | a heading opens with something written like an id that does not parse (an unlisted prefix, a wrong digit count); a heading names a requirement id that is not its bare first word, or is indented or underlined; a list item that opens with `AC-` is not exactly `- AC-<n>: <text>` at the left margin, sits above any requirement or repeats; a fenced block is never closed; or a requirement is defined twice or inside another's section | fix that line as [`docs/specs/README.md`](../specs/README.md) writes it; add the prefix to `traceability.id_prefixes` if the id is meant |
| `make trace` exits 2 saying a document's `frontmatter says kind '<kind>'` | a document under `traceability.specs_root` whose `kind` is not `spec` would define a requirement if read as one, so that requirement would never be traced | set `kind: spec`, put the example in a fenced block, or move the document out of `traceability.specs_root` |
| `make trace` exits 2 saying `traceability.matrix_path` `cannot be written` | the filesystem refused the write: a directory sits at the matrix path, a file sits where its directory goes, or the directory is not writable | remove what is in the way, or point `traceability.matrix_path` at a git-ignored path that can be written |
| `uncovered` for a unit whose test carries the marker | the test file sits below a directory pytest does not enter (`norecursedirs`, a virtual environment, `__pycache__`), so pytest never runs it | move the test file to a directory pytest collects |
| `make trace` exits 2 naming `through a symlink` | `traceability.matrix_path`, its temporary file, `specs_root`, `tests_root` or `matrix_schema` resolves through a symlink, so a read or a write could land outside the project | replace the symlink with a real directory or file inside the project |
| `make trace` exits 2 naming `traceability.matrix_path` and `is not git-ignored` | git would list the matrix, so writing it would change the tree | add the directory of `traceability.matrix_path` (`.evidence/traceability/matrix.json`) to `.gitignore` |
| `make trace` exits 2 with `pytest read its ini from outside the project` | the project has no pytest configuration of its own, so pytest took a parent directory's and its collection rule is another project's | give the project its own `[tool.pytest.ini_options]` in `pyproject.toml` |
| `make test-fe-unit` fails with `Unexpected .only modifier` | a unit test is focused with `.only`, which would skip the rest of the suite; the app's `vitest.config.ts` sets `allowOnly: false`, and the journey's `forbidOnly: true` refuses the same in `e2e/` | remove the `.only` |
| `make eval-live` refuses, or `get_model("openai-compatible", ...)` raises `ValueError`, saying `base_url` uses `http` to a host that is not a loopback address | the adapter would send its credential in clear text over a network; http is admitted only to a loopback address literal, 127.0.0.0/8 or `[::1]`, and a name such as `localhost` is refused because it resolves through DNS or a hosts file | use https, or for a server on this machine write its address, `http://127.0.0.1:<port>` or `http://[::1]:<port>`, and list that `host:port` in `models.allowed_hosts.openai-compatible` |
| `make test-fe-e2e` fails with `Error: No tests found` | the app's journey directory holds no `*.spec.ts`; this is the intended red for a stack with zero journeys | add a journey under the app's `e2e/` |
| `make test-fe-e2e` fails with `browserType.launch: Executable doesn't exist at ...` and a box saying `npx playwright install` | the browser cache lacks the chromium revision the pinned `@playwright/test` expects, or config/project.json `layers.frontend.journey.browser_executable` names a path that does not exist; a cache that `PLAYWRIGHT_BROWSERS_PATH` relocates reaches each `make verify` goal only while config/project.json `child_env.names` lists that variable | outside the gate, run `npx playwright install chromium` in the app (it downloads into the user's browser cache, not the tree), or set `layers.frontend.journey.browser_executable` (`null` as shipped) to a chromium on the host |
| `make test-fe-e2e` fails with `http://<host>:<port> is already used` | another process holds config/project.json `layers.frontend.journey.port` (`4391` as shipped); the journey refuses to test a server it did not start | stop that process, or set `layers.frontend.journey.port` to a free port |
| `make test-fe-e2e` fails with `Timed out waiting <n>ms from config.webServer` | the build or the preview server took longer than config/project.json `layers.frontend.journey.server_timeout_ms` (`120000` as shipped), or never answered on the journey's URL | run the app's `npm run build` and `npm run preview` by hand to see why, or raise `layers.frontend.journey.server_timeout_ms` |
| `make test-fe-e2e` fails naming `layers.frontend.journey.<key> must be ...` | config/project.json lacks that key or holds the wrong type for it | restore the key; [settings.md](../reference/settings.md) gives each key's type and shipped default |
