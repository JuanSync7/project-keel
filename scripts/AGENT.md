---
title: scripts — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside scripts/.
id: scripts-agent
created: 2026-06-17
updated: 2026-10-28
visibility: internal
canonical: true
---

# Agent rules — `scripts/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Scripts are entrypoints, not libraries — if `src/` needs it, it moves to `src/`.
  The exception is a module here that another module outside `tests/`
  imports. That set is derived, never listed here:
  `tests/integration/test_reference_drift.py` `derived_features` reads it from
  the import graph and fails until `docs/reference/features.md` has a row for
  each member (the `Shared script modules` section; the CONVENTIONS §2 note).
  Each shared module keeps its own rule:
  - `child_env.py` is imported from `models/`, `agents/`, `mcp/` and `evals/`
    as `scripts.child_env` because it must run under the 3.6 hook
    interpreter, which cannot import `src/`.
  - `resource_limits.py` is imported from `models/`, `api/` and `mcp/` as
    `scripts.resource_limits`, so it sits in the bottom import layer with
    `child_env.py` and `config_loader.py`, the two modules it imports, and
    stays stdlib-only and 3.6-safe. It is never run. `run_bounded` reads no
    config: each caller names its own limits and the keys that set them;
    `serve_limits` reads the servers' `transports.serve` block. Its child
    supervisor (`ChildSession`, `start_child`, `supervised`) is the only
    one: `run_make_target.py` runs make on it rather than keeping a second.
  - `jobs/conflict_guard.py` is never run, so it has no `--help`. The
    `copier update` jobs in `jobs/` import it before anything else from the
    project, to refuse a job over a conflicted module it imports and the data
    files the job's modules declare reading.
  - `git_tree.py` is never run either: it is the one definition of what git
    lists, `candidate_files` included: the files a commit could carry, which
    the committed-secrets gate judges, and `staged_paths`: the files the
    next commit adds or changes, which the staged secret scan needs to be
    non-empty, so a second listing of that set
    anywhere else is a defect. It raises `NoGitError` only when git is not
    installed or there is no repository, and `GitFailedError` for every other git failure: catch the
    first to take a no-git path, and never catch the second to take one. It
    stays 3.6-safe so the evidence writer can import it under an interpreter
    older than requires-python and still leave a red record.
  - `scan_secrets.py` is the one place the secret scanner runs: the commit
    hook, `make secret-scan` and CI all call it, and the scanner's own flags
    live only here and in config/project.json `secrets.scanner`, so another
    scanner is a second adapter beside it and never an edit to
    `tests/integration/test_committed_secrets_gate.py`. It never prints or
    logs a value: a finding is `file:line rule`, and the scanner is handed
    `--redact`. A scan that judged nothing is `NOTHING_JUDGED`, never a pass,
    and exit 1 is a finding and nothing else: a scanner that gave no
    verdict is `BACKEND_ABSENT` and a git failure is `USAGE`. It adapts gitleaks only, and refuses another
    `secrets.scanner.name` with `CONFIG` rather than hand it gitleaks flags.
    It stays stdlib-only and 3.6-safe, because the hook runs it under the
    host's `python3`; `git_tree.py` `staged_paths` is how it knows the stage
    is empty, and the hook then scans every commit instead.
    Every scan runs only the program the record names, never one on PATH:
    `write_record` is the record's one writer, so `install_scanner.py`
    imports it rather than write the file itself.
  - `install_scanner.py` is the one place the scanner is fetched. It installs
    only an archive whose sha256 config/project.json
    `secrets.scanner.release_assets` pins, under the per-user
    `secrets.scanner.install_root` and never inside the checkout, so
    `make secrets-install` stays `[read]`. The download URL is
    `secrets.scanner.release_url` and nothing else, so a mirror repoints it
    there; a test of it serves a fixture archive over a `file://` URL and
    never reaches the network.
  - `traceability.py` and `pytest_markers.py` are never run.
    `traceability.py` is the one home of the requirement-id grammar and the
    verdict rule, imported by `trace_requirements.py` and
    `tests/integration/test_requirement_traceability.py` so the command and
    the gate test cannot judge by different rules. `pytest_markers.py` is the
    one reader of marker calls from test source, imported by
    `traceability.py` and `tests/integration/test_e2e_coverage.py`. Both need
    the project interpreter and are not 3.6-safe. A second parser of an id
    anywhere else is a defect.
  - `exit_codes.py` is never run: the closed list of exit codes (`ExitCode`)
    and the one place a process ends. Import it by its bare name, never as
    `scripts.exit_codes`; it stays stdlib-only and 3.6-safe, because the hook
    interpreter runs scripts that import it.
  - `run_date.py` is never run: the one definition of the date a gate run
    calls today, imported by `gate_evidence.py`, which fixes it,
    `jobs/review_docs.py`, which reads it, and `check_structure.py`, whose
    check X reads its `policy` before any run. It stays stdlib-only, beside
    `config_loader.py`, and 3.6-safe for the reason `git_tree.py` does. A second reader of the
    variable config/project.json `evidence.run_date.env` names anywhere else
    is a defect.
  - `config_loader.py` is never run: the one way a configured value enters a
    process. A module reads config/project.json, config/practices.json or a
    variable they declare through its `read`, `resolve` or `env`, and a
    default lives in its `KEYS` row, never in a `.get(key, default)`;
    `tests/integration/test_config_reads_gate.py` fails a direct read that
    config/project.json `config_reads.allowed` does not excuse. It raises and
    never ends the process: the entry point returns
    `report(ExitCode.CONFIG, ...)`. `child_env.py` loads it by path, because
    `child_env.py` itself is imported under two names. It stays stdlib-only and
    3.6-safe, because the hook interpreter reaches it through `child_env.py`.
  - `corpus_level.py` is never run: the one reader of the level a file states
    on disk. `jobs/build_corpus.py` builds each node's level through it, and a
    reader that checks a node's level on disk now (CONVENTIONS §1 lists them)
    asks its `stated_now` and decides with `config_loader.is_served_now`, so the build and the reader
    cannot parse a level two ways. A second parser of frontmatter or module
    docstring levels anywhere else is a defect. It imports nothing of the
    project and stays stdlib-only and 3.6-safe, because it sits in the bottom
    import layer.
  - `launch.py` is the one place that decides where a long script runs and
    the one writer of `launcher.durations_file`; `long_scripts.py` imports its
    config loader and record reader, so the proposal and the decision cannot
    read the block by different rules. A second reader of the `launcher`
    block anywhere else is a defect. Both stay stdlib-only and 3.6-safe.
  - `template_snapshot.py` is never run: the one way a keel doer renders from
    the checkout as it stands. It clones the checkout into a scratch directory
    and commits the uncommitted and untracked files there, so copier never
    touches the checkout's own index; `audit_project.py` and `canary.py` import
    it, and all three are keel-only (copier.yml `_exclude`). It raises
    `SnapshotError` and never ends the process.
  - `check_structure.py` is the gate the tests and jobs import.
- End every script through `exit_codes.py`. The entry line is
  `finish(main())`. `main` returns `ExitCode.SUCCESS`, or
  `report(<member>, <what failed>, <on which input>, <what to do next>)` for a
  failure, or `passthrough(<a wrapped tool's status>)`, read at the call
  site that ran the tool: never `passthrough(main())`, a literal, a member,
  or a function of the script that returns only those, and never
  `finish(passthrough(...))` on the entry line; a function of the
  script itself that is not `main` calls `fail(...)` with the same four
  arguments. A module another project module imports never calls `fail`
  or `finish` outside its entry block: it raises or returns, and the entry
  point ends the process. `passthrough` only marks a status and returns it,
  so a shared module may return it. `jobs/conflict_guard.py` is the one
  exception, named with its reason in config/project.json
  `import_layers.may_end_the_process`; `tests/integration/test_exit_gate.py`
  fails any other. Never write
  `sys.exit`, `raise SystemExit`, `os._exit`, `exit`, `quit` or an argparse
  `.exit(...)`: `tests/integration/test_exit_gate.py` fails each. A name
  `main` returns is bound by plain assignment only (`rc = report(...)`), never
  by a parameter, an unpacking, a loop or `+=`: the same test fails a return
  it cannot follow to a member. After
  adding a member, or a script to `make verify`, run `make exit-codes`;
  `make check-exit-codes` fails a stale table.
- Each script is self-describing (`--help`) and safe to run twice — which
  here means declared: `effect: writes` plus a `rerun:` its header can be held
  to (check_V), built and proven as `docs/guides/idempotency.md` sets out.
