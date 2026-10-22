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
updated: 2026-10-22
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

- **The launcher is not a scheduler.** `scripts/launch.py` lowers a long
  script's CPU priority on a shared host; it caps neither CPU nor memory, and
  it neither queues nor retries. Its run record is last writer wins: two
  launches of one key at once keep the later one's entry, with no lock. A
  farm job's seconds include its time in the queue. With the `slurm` adapter,
  a command that itself exits 251 or 252 is read as the farm's own status
  (`launcher.farm.adapters.slurm.not_allocated_status`, `farm_error_status`),
  and the job receives only the allowlist, so a `SLURM_*` input variable the
  caller set does not reach `srun` unless `child_env.names` lists it
  ([ADR-K-0020](../adr/keel/K-0020-shared-compute-launcher.md)).
- **The frontend suites count no test themselves.** `make test-fe-unit` and
  `make test-fe-e2e` judge by their runners' exit codes alone. A runner that
  finds zero tests exits non-zero, but a suite whose every test is skipped
  exits 0 in both runners, and the evidence record lists `test-fe` with
  `tests: null`, so nothing counts those skips. CI runs `make test-fe` as a
  step of its own, after `make fe-install` and `make fe-browsers`.
- **CI downloads the journey's browser on every run.** A fresh CI machine has
  no browser cache, so the `make fe-browsers FE_BROWSER_FLAGS=--with-deps`
  step reads the network each run; nothing caches it between runs.
- **The browser runner's version fixes the browser.** Each app pins
  `@playwright/test` exactly, and that version names the chromium revision the
  browser cache must hold. `tests/integration/test_gate_scope.py` holds every
  app, and each committed lockfile, to one exact pin; a bump to
  a version whose revision is not in the cache shows only when the journey
  runs, as the missing-browser row below.
- **An interactive agent's direct edit is not policed.** config/project.json
  `agents` binds only edits that land through `scripts/apply_refactor.py`. An
  interactive agent's own Edit or Write tool reaches every file its permissions
  allow; closing that needs hooks or permission rules, which are not built
  (`docs/guides/coding-practices.md` owns agent edit safety).
- **A refused chunk shows only as skipped.** The agents' brains keep
  `apply_refactor`'s exit and drop its refusal text, so a report lists a chunk
  refused as protected like any other skipped chunk; recording the reason needs
  a rejection ledger, which is not built.
- **A judge the project adds is protected only when listed.** The frontend
  tests and configs keel ships (`*.test.*`, `*.spec.*`, `tsconfig*.json`) are
  covered by `agents.protected_names`, and any file git does not track is
  refused, but a tracked judge a project adds under another name, such as the
  directory `structure.project_checks` names or the `make_targets.area_dir`
  makefiles, is covered only once `agents.protected_paths` or
  `agents.protected_names` names it.
- **A `README.md` under a protected directory stays editable.**
  `agents.editable_names` carves it out by design, so `agents/doc_reviewer` can
  fix a roster row. A README's `## What ships here` heading does not switch
  check_S on or off: config/project.json `rosters.readmes` does, so check_S
  fails a listed README whose heading an edit removed.

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
  Queued for a decision. The suites do not skip: with a frontend app,
  `make test-fe-unit`, `make test-fe-e2e` and `make fe-browsers` exit 2 on a
  missing `npm` or `node_modules`, and a browser missing from the cache is
  red.
- `make check-openapi` and `make check-aad` skip when FastAPI or pydantic is
  not installed. Queued for a decision.
- `scripts/cdmon_sync.py` exits 0 when the `cdmon` program or its config is
  absent; otherwise it passes cdmon's exit code through. Queued for a decision.
- A `.py` file that does not parse is a WARN in check_D and the other checks
  that read the syntax tree, so its imports go unchecked. Queued for a
  decision.
- `scripts/jobs/check_corpus.py` passes when no local corpus has been built;
  it then judges a fresh build only. Queued for a decision.
- `tests/integration/test_frontend_lockfile_gate.py` skips in a tree outside
  any git repository, because it judges what git tracks, and in a project
  with no frontend app and no `layers.frontend.stack`. Queued for a
  decision.
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
  `from pkg import _sub` is caught only when `_sub.py` or `_sub/__init__.py`
  exists under `pkg/`; a private function imported from a public module is
  review's.
- **The layer gate's reach.** `tests/integration/test_import_layers_gate.py`
  resolves an import through config/project.json `import_layers.search_roots`
  only. An import made through `importlib`, `__import__`, or a `sys.path`
  entry no search root names is invisible to it, and an import under
  `TYPE_CHECKING` or in `try/except ImportError` counts as a real edge.
- **Heuristic comment gate.** `tests/integration/test_change_comment_gate.py`
  reads only the opening words of a comment, so `# The cache, which used to
  be a dict, ...` passes; review catches a change reported mid-sentence.
- **The config-reads gate's reach.**
  `tests/integration/test_config_reads_gate.py` follows a config path only
  through constants, names bound to them, a starred split, a path constant of
  a module imported at module level (read as `mod.NAME` or imported with
  `from mod import NAME`), and a helper of the same module. A path handed in
  as a parameter, an attribute of a module imported inside a function or
  relatively, a function of another module that opens what it is given, a
  method called through an object, a variable name the code holds in a
  variable, and a read through `subprocess` or `importlib` all pass. In a
  generated project its two finding tests judge through
  `scripts/expiring_tier.py`: a direct read under config/project.json
  `config_reads.roots` that `expiring_tier.baseline` records warns until
  `expiring_tier.expires`, and any other is red.
- **What a swallowed error looks like to the gate.**
  `tests/integration/test_swallowed_error_gate.py` judges a broad handler by
  its body's shape: one that logs nothing useful and returns a computed value,
  or an error dropped through `contextlib.suppress`, passes.
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
- **What the isolation guard cannot see.** `tests/isolation_guard.py` judges
  the reaches a Python audit event carries, in the pytest process alone. A
  write, a socket or a store opened by a child process the test starts (a
  nested pytest, `make`, `git`, copier), a C extension's own file or socket
  calls, and a FIFO or device node (`os.mkfifo` and `os.mknod` raise no audit
  event) pass unjudged; so does a read of a file outside the temp roots, of
  which only a listed store's open counts. An `os.open` with a relative path
  and a `dir_fd` is judged against the working directory, because the open
  event does not carry the `dir_fd`. A name lookup is not judged, by choice:
  library code looks names up without reaching anywhere, and the connect that
  follows is judged. A test that keeps
  its reach inside a child keeps it out of the guard: the guard is
  defence-in-depth, not a sandbox
  ([ADR-K-0024](../adr/keel/K-0024-what-a-test-may-reach.md)).
- **A sqlite `file:` name outside the roots.** The `sqlite3.connect` audit
  event does not say whether the call passed `uri=True`, so the guard judges a
  name that starts `file:` both as a URI and as a file of that name in the
  working directory. A test that opens a `file:` URI while the working
  directory is outside the temp roots fails, even for a memory database;
  `monkeypatch.chdir(tmp_path)` first.
- **A scratch root the caller moves.** A `--basetemp` given on the command
  line is honoured wherever it is and only checked against the system
  temporary directory, and pytest's own `PYTEST_DEBUG_TEMPROOT` moves the
  basetemp past config/project.json `tests.scratch_root`. A run killed by
  SIGKILL or SIGTERM leaves its numbered basetemp behind; pytest's retention
  count removes it in a later session.
- **What the secret layers cannot see.** The keyed gate,
  `tests/integration/test_committed_secrets_gate.py`, judges names: a value
  under a name no secret `KEYS` row declares, in a file type it does not parse
  (YAML, TOML, source code), or in a basename outside
  `secrets.json_files` and `secrets.dotenv_files`, is not its to see. The
  scanner, `scripts/scan_secrets.py`, judges shapes: a weak password, a value
  split across two literals, and a file its default allowlist skips
  (`package-lock.json`, `go.sum`, `*.svg`, `*.pdf`, `node_modules/`) pass it.
  An exclusion excuses every later finding of its rule in its file. The record
  proves the scanner has not changed since `make secrets-install`, not that
  the program it recorded is the real scanner. A value already pushed stays
  exposed whatever either layer says: see "A credential was committed".
  `docs/guides/deterministic-checks.md` section 15 lists each way past that
  was tried and its outcome.
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
| `tests.isolation.tiers` | `config/project.json` | a tier's rule on each axis; `any` on an axis lets every test of that tier reach anywhere on it, and a wider value widens every test the tier's marker names |
| `tests.isolation.exempt` | `config/project.json` | lets one named test reach outside its tier on one axis (`network`, `writes` or `stores`), with the reason; a blank reason stops pytest before any test runs, and an exemption whose test ran and reached nothing on that axis is red |
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
| 12 | `NO_CAPACITY` | nothing ran: the farm did not start the job within the wait bound and this host had no spare compute | run it again later, or raise config/project.json launcher.farm.wait_seconds |
| 13 | `NOTHING_JUDGED` | it ran and found no item to judge, so it cannot answer yes | give it something to judge, as the last stderr line names, then run it again |
| 14 | `CONFIG` | it refused before judging: a config value is missing or wrong, in config/project.json or a variable it declares | set or correct each key a `[not set]` or `accepted:` line on stderr names, then run it again |
| 130 | `INTERRUPTED` | it was interrupted before it finished | run it again; what it had written so far is not a result |

| Script | Exit |
|--------|------|
| `api/rest_fastapi/export_openapi.py` | 0, 1 |
| `scripts/agent_surface/generate_aad_schema.py` | 0, 1 |
| `scripts/cdmon_sync.py` | 0, passes through |
| `scripts/check_python_version.py` | 0, 1 |
| `scripts/check_structure.py` | 0, 1, 2 |
| `scripts/exit_code_table.py` | 0, 1, 2, 14 |
| `scripts/gate_evidence.py` | 0, 2, 10, 14, 130, passes through |
| `scripts/jobs/check_corpus.py` | 0, 1 |
| `scripts/run_evals.py` | 0, 1, 2, 11, 14 |
| `scripts/scan_secrets.py` | 0, 1, 2, 11, 13, 14 |
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
| `scripts/exit_code_table.py` | 0: the exit-code table between the markers is current. 1: it is stale, and each differing row is one stderr line. 2: it could not build the table: a missing or repeated marker, a guide reached through a symlink, or a script whose returns it cannot read. 14: config/project.json or its `doc_drift` block cannot be used, each key at fault named on its own stderr line first |
| `scripts/gate_evidence.py` | 0: every goal passed and the record is green. 2: refused before any goal ran: a malformed `--gate` or goal, zero goals, an evidence schema file that cannot be read, a record or report path that resolves through a symlink or that git does not ignore, a git command that ran and failed, or a date in the `evidence.run_date.env` variable that is not a date, is later than the clock or is older than `evidence.run_date.max_age_days` allows. 10: every goal passed but the record is red: zero tests, a failed or errored test in the junit report of a goal that exited 0, no junit report, the tree changed during the run, the checks could not run, or the writer crashed. 130: interrupted, and the red placeholder record stays. 14: refused before any goal ran because a config/project.json `evidence` value, `evidence.run_date` included, is missing or wrong, each key at fault named on its own stderr line first. Otherwise the first failing goal's code passes through |
| `scripts/launch.py` | the launched command's own status passes through when it ran, here or on the farm. 2: refused before anything ran: a bad `launcher` block, a state path reached through a symlink or one git would list, a git that failed, no command or one that is not installed here, an environment holding a credential name `launcher.credentials` does not list for the key, an unwritable run record before the start, or a farm that refused the submission. 11: the farm's submit command is not installed. 12 (`NO_CAPACITY`): the farm did not start the command within `launcher.farm.wait_seconds` and this host was not spare, so nothing ran. 130: interrupted while the command ran, recorded as `interrupted` |
| `scripts/jobs/check_corpus.py` | 0: the corpus is well-formed and its build is reproducible. 1: it is not, and each error is printed |
| `scripts/long_scripts.py` | 0: at least one recorded run was judged and none is over `launcher.long_after_seconds` and unlisted. 1: a key is proposed, each one `propose:` stdout line. 13 (`NOTHING_JUDGED`): no recorded run carried a duration, so nothing was judged. 2: refused: a bad `launcher` block, a durations file reached through a symlink, one git would list, a git that failed, or a file that is unreadable, not JSON or not a JSON object |
| `scripts/run_evals.py` | 0: every suite passed. 1: a suite failed: below `evals.threshold`, an errored case or a stale recording. 2: refused: a schema the `evals` block names that cannot be read, a malformed or empty dataset, a live run over `evals.live.max_calls`, a null or unknown `evals.live.model`, an `evals.report_dir` git does not ignore, or a git command that ran and failed. 11: the live backend is absent; the first case is `absent` and the rest `not-run`. 14: an `evals` value is missing, unknown or wrong, each key at fault named on its own stderr line first |
| `scripts/scan_secrets.py` | 0: `--locate` recorded the scanner, or a scan judged at least one file or commit and every finding is a `secrets.scanner.exclusions` entry. 1: a finding, each one `file:line rule` stdout line (a history finding with its commit after it), never the value, and nothing else. 2: not exactly one of `--locate`, `--staged`, `--history` or `--staged-or-history`, or a git command that ran and failed. 11 (`BACKEND_ABSENT`): no scanner on PATH for `--locate`, `--staged` or `--staged-or-history`; for a history scan, no record, a record naming another program or rev, a recorded path that is gone or a program whose digest changed; or a scanner that ran and gave no verdict: a status other than 0 and the finding status, a report that is not a JSON list of findings, no report, or a status and report that disagree. 13 (`NOTHING_JUDGED`): no repository, a history with no commit, `secrets.scanner.history_log_opts` that reach no commit, or a `--staged` scan of a stage that adds or changes no file. 14 (`CONFIG`): a bad `secrets.scanner` block, a `secrets.scanner.name` other than the one scanner the adapter adapts, a record file git would track, the scanner's own config or ignore file in the tree, or an exclusion the history scan did not use |
| `scripts/trace_requirements.py` | 0: every unit is `covered` or a `traceability.gaps` row, and there is no finding. 1: at least one finding, each one stderr line: an `uncovered` unit, a marker or gap id that is malformed or undefined, an unreadable or unattached marker, a redundant gap, or zero requirements with no reason. 2: it could not judge: a bad `traceability` block, a path reached through a symlink, a `matrix_path` git does not ignore, a repository git cannot read, an unreadable schema, spec or test file, a spec line that does not parse, a document under the specs root that defines a requirement without `kind: spec`, or a collection rule pytest could not give; or it could not write the matrix at `traceability.matrix_path` |

Three more codes come from the tools around these scripts:

- **pytest exit 5** means the run selected zero tests. `tests/selection_guard.py`
  fails such a run unless its `-m` marker is named in
  `make_targets.empty_test_selections`.
- **argparse exit 2** means a script was called with an argument it does not
  take; the usage line names the right ones.
- **make exit 2** means make itself failed: a recipe returned non-zero, or the
  target does not exist. The line above it names the recipe's own code.

## Lines the config loader writes

A script that reads its config through `scripts/config_loader.py` writes two
kinds of line to stderr about the keys it reads.
`tests/integration/test_config_default_lines_docs.py` fails this section when a
line quoted here is not one the loader writes.

- **`[using default]`** means a key that has a declared default is absent, and
  the run goes on with that default. The loader writes the line once per process
  in this shape:
  `[using default] <key> = <value>  (not set; to change it, set <key> in <config file>)`.
  A `config/project.json` with no `practices.profiles` block makes `make advise`
  write
  `[using default] practices.profiles = {}  (not set; to change it, set practices.profiles in config/project.json)`.
  For a key only a variable sets, `<config file>` reads `the environment`, and a
  secret's value is shown as `<hidden>`. The line does not change the exit code.
  If the default is what you want, do nothing. To silence the line, set the key
  in the file it names, to the default or to another value. Each defaulted key's
  row in [settings.md](../reference/settings.md) quotes its line.
- **`[not set]`** means a key that has no default is absent, and the script
  stops with exit 14 (`CONFIG`) in this shape:
  `[not set] <key>  (required, no default; set <key> in <config file>)`.
  A `config/project.json` with no `evidence.dir` makes the gate's driver write
  `[not set] evidence.dir  (required, no default; set evidence.dir in config/project.json)`
  before any goal runs. Add each key a line names; settings.md gives its type
  and shipped value.

A value of the wrong type, or out of a key's range, is a third line,
`<config file>: <key> is <JSON type> <value>; accepted: <what it accepts>`,
with `<value>` left out for a list, an object or a secret, and also stops the
script with exit 14. A value read from an environment variable is blamed on
it instead: `the environment: <variable> is <JSON type> <value>; accepted: <what it accepts>`. The loader writes every `[not set]` and wrong-value line before it stops,
so one run names every key at fault. A script that config/project.json
`config_reads.allowed` still lists reads its config directly: it writes its own
message and stops with exit 2 until it is moved onto the loader.

## A credential was committed

A finding from the keyed gate or the scanner means a credential is in a file
git would commit, or in a commit already made. Deleting the line does not undo
it: history keeps the value, and a pushed commit has been fetched by every
clone and by CI. Work in this order.

1. **Rotate it first.** Revoke the credential at its provider and issue a new
   one, before anything else. Once it was pushed, treat it as read by someone
   else; the steps below stop it spreading, not the exposure that happened.
2. **Remove it from the tree.** Delete the value and set the new one where the
   keyed gate expects it: the environment, or a git-ignored file such as
   `.env`. Leave an empty placeholder (`ANTHROPIC_API_KEY=`) in
   `.env.example`; the empty value is the only one the keyed gate accepts.
3. **Purge history when it was pushed.** Rewrite every branch and tag that
   holds the commit with a history-rewriting tool, force-push, and ask each
   holder of a clone to re-clone. This is irreversible and visible to everyone
   with access, so it needs the repository owner's say. A commit not yet
   pushed needs only `git commit --amend` or a rebase, then
   `make secret-scan` to confirm that no branch reaches it.
4. **Confirm.** `make secret-scan` is green and the keyed gate passes.

A `secrets.scanner.exclusions` entry is never the fix for a real credential:
it hides a finding and leaves the value where it was. It is for a fake value
kept on purpose, such as a test fixture, with its reason.

## Symptom, cause, fix

| Symptom | Cause | Fix |
|---------|-------|-----|
| pre-commit fails with a syntax error before any check runs | the bare `python3` is older than the gate supports | install a newer `python3`, or run `make check` with the project interpreter |
| `make verify` stops on a missing `pytest`, `ruff` or `mypy` | the `dev` extra is not installed | `.venv/bin/pip install -e ".[dev]"` |
| `make secret-scan` (or `make verify`'s `secret-scan` goal) exits 11 with `there is no scanner record at` | `make secrets-install` has not run on this machine, as in a fresh clone or a newly generated project | run `make secrets-install`, then run the scan again |
| `make secret-scan` exits 11 with `is gone`, `changed after it was recorded`, or a record naming another rev | the recorded build was deleted or rebuilt, or `.pre-commit-config.yaml` now pins another rev | run `make secrets-install`, which records the build pre-commit holds for the pinned rev |
| `make secret-scan` exits 13 with `the repository has no commit` | the project was never committed, so there is no history to judge | `git add -A && git commit`, then run it again |
| `scripts/scan_secrets.py --staged` exits 13 with `nothing is staged` | it was run by hand with a stage that adds or changes no file; the commit hook runs `--staged-or-history`, which scans every commit then, and pre-commit skips the hook at a commit that adds or changes no file | stage the files to commit with `git add`; `make secret-scan` judges the history |
| `make secret-scan` exits 13 with `reaches no commit` | `secrets.scanner.history_log_opts` select no commit (such as `--max-count=0`, or an `--author` or `--since` that matches nothing), so the scan would judge nothing | widen the options until `git log` with them lists at least one commit |
| a scan exits 11 with `exited <n>, its own error`, `without a report` or `not a JSON list of findings` | the scanner crashed or is not the program the adapter expects, so it gave no verdict; no credential is implicated | read the scanner's stderr the scan prints above, run `make secrets-install` to rebuild it, then run the scan again |
| a scan exits 14 with `adapts gitleaks only` | `secrets.scanner.name` names a scanner `scripts/scan_secrets.py` has no adapter for | set it back to `gitleaks`, or write an adapter for the other scanner first |
| a scan exits 2 with `git failed` | git could not read the repository (a broken `.git`, a corrupt `HEAD`, or an option in `secrets.scanner.history_log_opts` git refuses) | fix what git's stderr in the message names, then run the scan again |
| `make secret-scan` exits 14 with `exclusions the scan did not use` | a `secrets.scanner.exclusions` entry names a file and rule no finding has, because the fixture moved or the value is gone | delete the entry, or correct its path or rule id |
| a scan exits 14 with `the scanner's own config or ignore file is in the tree` | a file `secrets.scanner.refused_files` names, such as `.gitleaksignore`, is in a file git would commit or at the root | delete it; excuse a fake value with a `secrets.scanner.exclusions` entry and its reason |
| `make secrets-install` fails with an unexpected EOF or a certificate error while pre-commit builds the scanner | a site that intercepts TLS breaks the Go module download pre-commit's golang build makes | on such a host, set `GOPROXY=direct` and point `SSL_CERT_FILE` and `GIT_SSL_CAINFO` at the site's CA bundle, then rerun; this is a host fact, so it is not in config |
| `make secrets-install` fails on a farm node and works on a login host | the node's CA bundle lacks the root the site's TLS interception signs with | run `make secrets-install` once on a host that has the root: pre-commit's cache under the home directory is shared, so the node then reuses that build |
| a config-reads or exit gate test fails in a generated project with `no config/gate-baseline.json records it` | `make gate-baseline` has not run since the project was generated or updated, so the tier has no record of the project's own findings | fix the finding, or run `make gate-baseline` once after `copier update` and commit the file it writes |
| such a test fails with `does not record it` | the finding is new since the commit the baseline records, which the tier holds red at once | fix the finding; the baseline grows only after the next `copier update` moves `_commit` |
| such a test fails with `which no finding matches; delete the entry` | a finding the baseline records is gone, so the file must shrink | rerun `make gate-baseline`, or delete the named entry, and commit the file |
| such a test fails with `its grace in config/gate-baseline.json ended on` | today is on or after config/project.json `expiring_tier.expires`, so recorded findings are red | fix each finding the line names; a later date than `scripts/expiring_tier_data.py` `CEILING` is refused |
| such a test errors with `later than the ceiling` | config/project.json `expiring_tier.expires` holds a date after keel's `CEILING` | set it to the ceiling or an earlier date |
| `make gate-baseline` exits 1 with `would gain` | the gate tests found a finding the baseline lacks while `.copier-answers.yml` `_commit` still names the commit the file records | fix the finding the line names, then run it again |
| `make gate-baseline` exits 1 with `is committed but missing from the work tree` | the baseline was deleted while git's index or HEAD still holds it, and a rewrite would lift its only-shrinks rule | restore it with `git checkout -- config/gate-baseline.json`, then run it again |
| `make gate-baseline` exits 2 with `git cannot say whether` | there is no baseline file and no git repository, or git failed, so the writer cannot tell a first baseline from a deleted one and fails closed | run it in the project's git repository after at least one commit |
| `make gate-baseline` exits 13 with `judged no finding for` | a registered gate test stopped before it handed its findings to the tier, such as on a walk over zero files | run the named test, fix what stops it, then run the target again |
| check_B names a directory you just added | it is not a taxonomy row | add its name to `structure.extra_toplevel` and give it a `README.md` and `CLAUDE.md` |
| check_W names a make target | its `##` help does not open with an effect label | open the help with `[local]`, `[tree]`, `[read]`, `[cost]` or `[write]` |
| check_W says `WRITE_GUARD does not refuse when make ignores recipe errors` | the guard's definition does not open with `$(if $(findstring i,$(firstword -$(MAKEFLAGS))),$(error ...))`, so under `make -i` the shell's `exit 1` is ignored and the `[write]` recipe runs | open the definition with that clause, as the root Makefile does |
| check_W says `.IGNORE makes make ignore recipe errors` | a makefile holds a `.IGNORE` rule, which lets every recipe it names, or every recipe, carry on past a failing line, including the guard's `exit 1` | delete the `.IGNORE` rule; put a `-` on the one line whose failure may be ignored |
| a `[write]` target stops with `refusing '<target>': make is ignoring recipe errors` | make was run with `-i`, `--ignore-errors`, `MAKEFLAGS=i` or under a bare `.IGNORE:`, so the guard could not stop the target | run the target without that flag |
| `make test-fe-unit`, `make test-fe-e2e` or `make fe-browsers` exits 2 with `<target>: npm is not on PATH` | Node.js is not installed or not on `PATH`, and a frontend app exists | install Node.js, run `make fe-install`, then run the target again |
| `make test-fe-unit`, `make test-fe-e2e` or `make fe-browsers` exits 2 with `<target>: <app> has no node_modules` | the app's packages are not installed, as in a fresh clone or a newly generated project | run `make fe-install`, then run the target again |
| `make fe-install` stops with `node major is <found>, and config/project.json toolchain.node_major is <configured>` | the Node on `PATH` is another major than the one every lockfile was resolved under | install that Node major, or change `toolchain.node_major`, run `make fe-install` and commit the regenerated lockfiles |
| `make fe-install` stops with `node cannot be run` or `node --version printed` | Node.js is not on `PATH`, or the `node` found is not Node.js | install Node.js of the major `toolchain.node_major` names, then run the target again |
| `test_frontend_lockfile_gate` says `<app>/package-lock.json exists but git does not track it` or `has no package-lock.json` | the app's lockfile was never committed, so CI's npm resolves a tree of its own | run `npm install` in the app and commit its `package-lock.json` |
| `test_frontend_lockfile_gate` says `<app>/package.json <section> differs from its package-lock.json root entry` | the manifest was edited without reinstalling, so the lockfile records other dependencies | run `npm install` in the app and commit the lockfile with the manifest |
| `test_toolchain_gate` names a `runs-on` label, or a `node-version` or `python-version` that is not a `toolchain` step output | a workflow job uses a label `toolchain.runner_images` does not list, or spells a version instead of reading the `toolchain` step | name a listed image, or add the `toolchain` step before the setup step and read `${{ steps.toolchain.outputs.node }}` or `${{ steps.toolchain.outputs.python }}` |
| `test_toolchain_gate` says `toolchain.python <release> does not satisfy` a floor | `layers.backend.python` or `requires-python` was raised above the release CI installs | set `toolchain.python` to a release that satisfies both; in a generated project, record it as the copier answer too (`copier update --data toolchain_python=<release>`) |
| In the keel template, `make canary` ends with exit 1 and `<n> of <m> canary projects failed`, each `<set> <path> at <step>` | a project rendered from that answer set and path failed at that step; the line for it names its log, and stderr names the project it kept under the scratch root | read the log beside the kept project and the step's row in [generate-and-upgrade.md](generate-and-upgrade.md); fix keel, then rerun that project alone with `make canary CANARY_FLAGS="--set <set> --path <path>"` |
| `make canary` ends with exit 2 and `no previous release to update from` | no dated `## [X.Y.Z]` heading of `CHANGELOG.md` has a tag that is a strict ancestor of `HEAD`, as in a shallow clone with no tags | fetch the tags (`git fetch --tags`, or a checkout with full history), tag the last release, or run the fresh path alone with `CANARY_FLAGS="--path fresh"` |
| `make canary` ends with exit 2 and `no such answer set` | a `--set` name in `CANARY_FLAGS` is not a key of config/project.json `canary.answer_sets` | name a set the message lists, or add the set to `canary.answer_sets` |
| `make canary` ends with exit 13 and `there is no answer set to render` | config/project.json `canary.answer_sets` is empty | add a set to `canary.answer_sets`, then run the target again |
| `make canary` ends with exit 14 and `the canary settings are refused`, `an answer set is not a plain name mapped to an object of answers` or `the run date is refused` | a `canary` key, or `evidence.run_date`, in config/project.json is missing or wrong, or a set name is not one plain segment of letters, digits, `.`, `_` or `-` | fix the key the message names; config/project.json's `canary._comment` says what each key holds |
| `make canary` ends with exit 14 and `an answer set names a question copier.yml does not ask`, each `<set>.<key>` | a key of a config/project.json `canary.answer_sets` set is not a question copier.yml asks, as with a misspelt name; copier would ignore it and render that question's default | spell the key as copier.yml names its question, or drop it from the set |
| `make canary` ends with exit 1 and `the template's copier.yml could not be read` | PyYAML, which copier brings, is not installed for the interpreter `make` runs, or copier.yml does not parse to a mapping | install the template extra with `pip install -e '.[template]'`, or fix copier.yml as the message says |
| `make canary` ends with exit 14 and `the canary's scratch root is refused` | config/project.json `canary.scratch_root`, or `KEEL_CANARY_SCRATCH` when it is set, is under the system temporary directory, or is inside the checkout and git tracks a file in it or does not ignore it | point it at a directory of the checkout that `.gitignore` names, or at local disk outside the system temporary directory |
| `make canary` ends with exit 1 and `git could not answer about the template checkout` or `the template checkout could not be snapshotted` | the canary was run outside a keel git checkout, or git failed while it cloned the checkout and committed its uncommitted files | run it from a keel git checkout whose `git status` succeeds; the message says which git step failed and quotes its last output lines |
| `scripts/launch.py` ends with exit 12 and `the farm did not start the command within launcher.farm.wait_seconds` | the farm had no free slot within the wait, and the load per cpu of the host it was called on was over `launcher.spare.max_load_per_cpu` or unknown, so nothing ran | run it again later, or raise config/project.json `launcher.farm.wait_seconds` |
| `scripts/launch.py` ends with exit 2 and `the farm refused the submission, so nothing ran` | the submit command returned the adapter's `farm_error_status`: a size the farm cannot grant, or a farm-side error; a command that itself exits that status reads the same | lower the size in config/project.json `launcher.long_scripts` or `launcher.default_size`, or run the submit command by hand to see the farm's message |
| `scripts/launch.py` ends with exit 2 naming `config/project.json launcher.credentials` | the environment would hold a credential name the launch key's `launcher.credentials` entry does not list | add the name to that key's entry, or unset it before the launch |
| check_D says `imports the private submodule <pkg>.<_sub> from outside its package` | a file outside `<pkg>/` imports `_sub` by name, which reaches inside the package as `from pkg._sub import x` does | import the name `<pkg>/__init__.py` exports, and add it to `__all__` there if it is missing |
| `test_import_layers_gate` names `<file>:<line>: layer <n> (...) imports <other> in the higher layer <m>` | a lower layer of `import_layers.order` imports from a higher one | move the shared code down to the lower layer, or pass the higher layer's behaviour in as an argument; change the order only when the layering itself is wrong |
| `test_import_layers_gate` says `no prefix in config/project.json import_layers.order holds it` | a new top-level directory or file sits in no layer | add its path prefix to the layer it belongs in, in both `config/project.json` and its `.jinja` twin |
| `test_import_layers_gate` says `import_layers.order names <prefix>, which places no Python file` | the entry is stale: its directory holds no Python file any more | delete the entry, or point it at the files it means |
| `test_exit_gate` says `<name> is imported by <importer>, so it must raise or return, never end the process` | a shared module calls `fail` or `finish` outside its entry block | raise an exception or return a value, and let the entry point's `main` turn it into `report(...)` |
| `test_exit_gate` says `import_layers.may_end_the_process names <path>, which is no shared module that ends the process` | the exemption is stale: the module no longer ends the process, or nothing imports it | delete the entry |
| `test_exit_gate` says `passthrough wraps a wrapped tool's status, never this script's own` | `passthrough` is handed the entry function's result, an int literal, a member, or a function of the same module whose every return is one of those, also under a sign, combined with `or` or arithmetic, or through a builtin such as `int`, so a script's own status would pass as a wrapped tool's | return `ExitCode` members from `main` through `report`, and call `passthrough` only on the status of the tool the script ran, where it reads it (`subprocess.run(...).returncode`) |
| `test_exit_gate` says `the entry line is finish(main()); call passthrough inside main where the wrapped tool's status is read` | the entry block hands `finish` a `passthrough(...)` call, or a name bound to one | write the entry line as `finish(main())`, and return `passthrough(<the tool's status>)` from `main` |
| `test_swallowed_error_gate` says `<handler> swallows the error, so the caller reads a failure as a success` | a bare `except:`, or a broad handler whose body only passes, continues, breaks, or returns or assigns a fixed value such as `None`, `-1` or `[]` | catch the exception you can name, raise or return the failure, or give the reason on the clause: `# noqa: BLE001 -- <why>` |
| `test_swallowed_error_gate` says ``# noqa: BLE001` gives no reason`` | a blind-except suppression has no text after its codes | write after the codes why the error may be dropped, or handle it |
| `test_change_comment_gate` says `the comment opens with <phrase>, which reports a change` | the comment tells what changed, not why the code is as it is | rewrite it as the reason, and leave the change to the commit message |
| `make long-scripts` ends with exit 13 (make says `Error 13`) and `no recorded runs, so nothing was judged` | the durations file is absent or holds no run with a duration, which is the state of a fresh clone | run a long script through `scripts/launch.py`, then run it again |
| `make check-docs` names a stale `updated:` | a document changed without its stamp | `make restamp-docs` |
| `make new` refuses | no `DEST`, the template is not a git checkout, or its tree is dirty | see `generate-and-upgrade.md`; `ALLOW_DIRTY=1` overrides the dirty tree only |
| a test target exits 5 | it selected zero tests | add tests, or name its marker in `make_targets.empty_test_selections` |
| a test fails with `IsolationError` and `<nodeid> [<phase>] reached outside its tier '<tier>': <event> <target> (<axis>=<value>). Use tmp_path or the store_copy fixture; or exempt it with a reason in config/project.json tests.isolation.exempt.<axis>."<nodeid>"` | in that phase the test connected, wrote, or opened a sqlite database or a listed store past the rule config/project.json `tests.isolation.tiers` gives its tier; the test fails even when its code caught the error | write scratch to `tmp_path`, ask `store_copy` for a copy of a listed store, or move the test to the tier that allows the reach; exempt it in `tests.isolation.exempt` under that axis with the reason only when the reach is the point of the test |
| a run whose tests all passed exits 1 with `tests.isolation.exempt.<axis>."<nodeid>": the test ran and reached nothing on <axis>; remove the exemption from config/project.json` | the exemption outlived its reason: the test no longer reaches outside its tier on that axis | delete the entry the line names |
| pytest stops before any test runs (exit 4) with `ImportError while loading conftest` and a `config_loader.WrongValue` saying `config/project.json tests.scratch_root is` or KEEL_TEST_SCRATCH, which sets tests.scratch_root is the value, then a reason: it is relative, so it would land in the checkout; it is under the system temporary directory; or it is inside the checkout | test scratch is refused a root the system temporary directory holds, because every program shares it and kept directories pile up there unseen, and one inside the checkout, because the tree walkers would read a kept directory as source | set `tests.scratch_root`, or `KEEL_TEST_SCRATCH`, to a value the line accepts, accepted: an absolute path (`~` allowed) outside the system temporary directory and the checkout |
| the suite runs slowly, or a test that compares file times fails now and then, and pytest's header reads `scratch: <path> (disk: <reason>)` | the session fell back from `tests.memory_scratch_root` to `tests.scratch_root` (`~/.cache/project_keel/tests`), which is under the home directory, and some hosts mount that from a network filesystem whose writes are slow and whose clock may differ from the host's; the reason names the missing parent, the free space under `tests.memory_scratch_min_free_mb`, a parent others may write without the sticky bit, or a directory that is not this user's with mode 0700 (run without `-q` to see the header) | fix what the reason names: free memory or lower the floor; a directory of your own, `chmod 0700` it; one another user made, which the sticky bit stops you removing, ask its owner or an administrator to remove it; on a host with no memory directory, set `KEEL_TEST_SCRATCH` or `tests.scratch_root` to local disk outside the system temporary directory |
| `copier update` stops with exit 2 naming files | a migration found conflict markers in a file it imports, or in a fixed project file one of its modules declares reading (`config/project.json`, the `Makefile`) | resolve each named file, then run the command the message prints: under an update it is `<python> scripts/jobs/finish_update.py`, which runs the migrations copier never reached |
| a migration names `scripts/exit_codes.py` as conflicted and then stops with exit 1 on a `SyntaxError` traceback, or `scripts/check_structure.py` stops on that traceback alone | the conflicted file is the exit helper itself, which every script imports to end with a chosen status, so nothing can exit 2; a project that added its own `ExitCode` member is the one an update conflicts here | resolve the hunk in `scripts/exit_codes.py`, keeping your members and the template's, run `make exit-codes`, then run the command the refusal line prints |
| a command stops with `config/project.json holds a merge-conflict hunk at line N` | an update left the manifest conflicted, so `scripts/child_env.py` has no allowlist and lets no child start | resolve the hunk, then finish the update as `generate-and-upgrade.md` says |
| stderr shows `[using default] child_env.login_name_schemes = []` and the run goes on | the key is absent from config/project.json, as in a project that deleted it or kept its own side of an update | nothing, if the default is what you want; otherwise, or to silence the line, set the key ([settings.md](../reference/settings.md) gives its meaning) |
| a script stops with exit 14 after `[not set] evidence.schema` | config/project.json lacks a key the script requires, which has no default | add each key a `[not set]` line names, then run it again |
| a script stops with exit 14 after a line ending `accepted: <what>` | a config/project.json key, or the environment variable a line opening `the environment:` names, holds a value of the wrong type or out of its range | set the key or the variable to a value the line accepts, then run it again |
| `scripts/apply_refactor.py` stops with exit 2 and `edit N: P is protected by agents.protected_paths.X (<reason>); an agent edit may not reach the code that judges it`, or `edit N: P is protected by agents.protected_names.X (<reason>)` for a protected file name, and an agent lists the chunk as skipped | the edit reached a file config/project.json `agents` protects: a check, a test, config, an ADR, an AGENT.md, the Makefile | propose the change to that file's owner; only a human edit of config/project.json removes the entry, and no flag lifts it |
| `scripts/apply_refactor.py` stops with exit 2 and `spec names a gate ('verify'); the gate is the caller's --gate, never the spec's` | the edit spec carries a `gate` key, as an older caller wrote it | drop the field from the spec and pass `--gate <target>` |
| `scripts/apply_refactor.py` stops with exit 2 and `edit N: P is not a file this run was bound to (--allow F)` | the run passed `--allow` and the edit names another file; an agent binds each run to its chunk's own file | edit only a bound file, or pass one `--allow` for each file a person means to change |
| `scripts/apply_refactor.py` stops with exit 2 and `edit N: P is not a file git tracks; an agent edits only tracked source, never git's own state, an ignored file or the toolchain the gate runs` | the edit names a file git does not track: something under `.git`, an ignored file such as one in `.venv` or `node_modules`, or a new file not yet added | edit a tracked file; a person who means the agent to edit a new file runs `git add` on it first |
| `scripts/apply_refactor.py` stops with exit 2 and `edit N: P: git cannot say whether it is tracked (...); an agent edits only a file git tracks` | the root is not a git work tree, or git is not installed or failed; the doer refuses rather than guess | run it in a git work tree with git on the PATH; the parenthesis names git's own failure |
| `scripts/apply_refactor.py` stops with exit 14 and ``apply_refactor: the edit policy in config/project.json `agents` could not be used`` | a key of the `agents` block is absent, holds a blank reason, is an empty `agents.protected_paths` or `agents.protected_names` (an empty `agents.editable_names` is valid), or `agents.protected_paths` does not cover config/project.json | fix the key the message names; nothing was changed |
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
| `make eval-live` refuses, or `get_model("openai-compatible", ...)` raises `ValueError`, saying `base_url` uses `http` to a host that is not a loopback address | the adapter would send its credential in clear text over a network; http is admitted only to a loopback address literal, 127.0.0.0/8 or `[::1]`, and a name such as `localhost` is refused because it resolves through DNS or a hosts file | use https, or for a server on this machine write its address, `http://127.0.0.1:<port>` or `http://[::1]:<port>`, and list that `host:port` in `models.allowed_hosts.openai-compatible` |
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
| `make test-fe-e2e` fails with `Error: No tests found` | the app's journey directory holds no `*.spec.ts`; this is the intended red for a stack with zero journeys | add a journey under the app's `e2e/` |
| `make test-fe-e2e` fails with `browserType.launch: Executable doesn't exist at ...` and a box saying `npx playwright install` | the browser cache lacks the chromium revision the pinned `@playwright/test` expects, or config/project.json `layers.frontend.journey.browser_executable` names a path that does not exist; a cache that `PLAYWRIGHT_BROWSERS_PATH` relocates reaches each `make verify` goal only while config/project.json `child_env.names` lists that variable | outside the gate, run `make fe-browsers` (it downloads into the user's browser cache, not the tree), or set `layers.frontend.journey.browser_executable` (`null` as shipped) to a chromium on the host |
| `make test-fe-e2e` fails with `http://<host>:<port> is already used` | another process holds config/project.json `layers.frontend.journey.port` (`4391` as shipped); the journey refuses to test a server it did not start | stop that process, or set `layers.frontend.journey.port` to a free port |
| `make test-fe-e2e` fails with `Timed out waiting <n>ms from config.webServer` | the build or the preview server took longer than config/project.json `layers.frontend.journey.server_timeout_ms` (`120000` as shipped), or never answered on the journey's URL | run the app's `npm run build` and `npm run preview` by hand to see why, or raise `layers.frontend.journey.server_timeout_ms` |
| `make test-fe-e2e` fails naming `layers.frontend.journey.<key> must be ...` | config/project.json lacks that key or holds the wrong type for it | restore the key; [settings.md](../reference/settings.md) gives each key's type and shipped default |
