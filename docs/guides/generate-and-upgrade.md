---
title: Generate and upgrade
kind: doc
layer: n/a
status: template
owner: TBD
tags: [copier, generate, update, migrations, adoption, guide]
summary: How a project is generated from keel, what arrives and what never does, what `make new` refuses, how to adopt keel into an existing repository, and how `copier update` pulls template changes — with one checklist row per task and migration an update runs, how to finish an update a migration stopped, and how keel's release canary proves a fresh project and an updated one pass their own `make verify`.
id: docs-guides-generate-and-upgrade
created: 2026-10-09
updated: 2026-10-23
visibility: internal
canonical: true
---

# Generate and upgrade

A keel project is made by `copier` from the keel template and kept current by
`copier update`. This guide covers both, in the order you meet them.
`tests/integration/test_doc_drift.py` holds this guide to `copier.yml`: the
exclusion table names every `_exclude` entry; the update checklist gives every
`_tasks` and every `_migrations` entry a row of its own, in the order copier
runs them, with each script's exit codes; and the copier version floor below is
the template's `_min_copier_version`.

## Generate

You need copier 9.3.0 or newer, the floor the template sets in its
`_min_copier_version`; an older copier stops with its own message before it
renders anything.

```bash
pipx install copier
copier copy --trust gh:JuanSync7/project-keel my-project
```

copier asks for the project name, whether to keep the bundled showcase demo
(`showcase`), the frontend stack (`react-vite`, `astro` or `none`; `astro`
needs the showcase), the backend's minimum Python (`backend_python`), the
Python release CI installs (`toolchain_python`, which must satisfy
`backend_python`, or copier refuses the pair before writing a file), the
optional transports (`grpc`, `edge_nginx`) and the domain profiles (`ai`,
`cuda`, `langgraph`). `--defaults` takes every default without asking, and
`--data name=value` answers one question on the command line:

```bash
copier copy --trust --defaults --data project_name=my_service --data frontend_stack=none gh:JuanSync7/project-keel my-project
```

`--trust` is required. The template runs a task as it renders: it stamps
every document's `updated:` with the generation day, so the project passes its
own freshness gate on its first commit, and copier refuses a template that runs
a task unless you pass `--trust`
([ADR-K-0010](../adr/keel/K-0010-generation-needs-trust-to-stamp-docs.md)).
copier accepts any git URL or local path in place of `gh:JuanSync7/project-keel`.

With a frontend stack, run `make fe-install` and then `make fe-browsers` before
the first `make verify`. A fresh project has no `node_modules`, so
`make test-fe` exits 2 naming the app and `make fe-install` rather than pass
over tests that never ran, and the browser journey fails until
`make fe-browsers` has downloaded its browser. With `frontend_stack` `none`,
`make test-fe` exits 0 and says nothing.
`tests/integration/test_copier_generation.py` generates each stack and checks
both behaviours.

Commit the project, then run `make secrets-install`, before the first
`make verify`. Its history scan judges commits, so before the first one
`scripts/scan_secrets.py --history` exits 13 (`NOTHING_JUDGED`); with no
recorded scanner it exits 11 (`BACKEND_ABSENT`) naming `make secrets-install`,
never a skip. The README Quickstart runs both in that order, and
`tests/integration/test_copier_generation.py` checks the order under every
frontend answer.

## What arrives and what never does

Every template file arrives except the ones below. An entry with a condition is
left out only when the answer matches it.
`tests/integration/test_copier_shipping.py` holds this table to what copier
does. It judges every file git tracks, and every untracked file git does not
ignore, with copier's own path matcher under every answer set the template
allows. A file left out of a project needs a row here with a reason in its Why
cell. A row that names no `_exclude` entry fails, because the file it explains
in fact arrives. An entry that leaves out no file under any answer set fails
too, unless `.gitignore` names its path or it is one of copier's own defaults
that `copier.yml` re-lists. `tests/integration/test_copier_generation.py`
renders three answer sets with copier and checks that each project holds
exactly the files this judgment says arrive.

| Path | Arrives | Why |
|------|---------|-----|
| `copier.yml` | never | the template's own settings |
| `copier.yaml` | never | the same, by its other name |
| `~*` | never | editor backup files |
| `*.py[co]` | never | compiled Python |
| `__pycache__` | never | compiled Python |
| `.git` | never | the template's history is not the project's |
| `.DS_Store` | never | operating-system clutter |
| `.svn` | never | another tool's metadata |
| `.venv` | never | the template's own interpreter |
| `tmp` | never | a person's scratch at the root, ignored by `.gitignore`; the entry keeps a force-added file out of every generated project |
| `docs/design/keel-hardening-plan.md` | never | the template's own plan |
| `docs/design/documentation-quality.md` | never | the template's own design note |
| `docs/design/downstream-feedback.md` | never | the template's own design note |
| `docs/design/make-next-steps.md` | never | the template's own design note |
| `wiki/corpus.json` | absent; `make site-data` builds it | a generated view of the tree |
| `wiki/llms.txt` | absent; `make site-data` builds it with the showcase | a generated view of the corpus |
| `wiki/llms-full.txt` | absent; `make site-data` builds it with the showcase | a generated view of the corpus |
| `wiki/.runtime` | never | runtime state |
| `api/rest_fastapi/openapi.json` | absent; `api/rest_fastapi/export_openapi.py` writes it | generated from the app |
| `tests/integration/test_copier_*.py` | never | tests of the template itself |
| `tests/render_cache.py` | never | serves only a test of the template itself |
| `tests/unit/test_render_cache.py` | never | its test |
| `scripts/audit_project.py` | never | runs from a template checkout only |
| `tests/unit/scripts/test_audit_project.py` | never | its test |
| `scripts/canary.py` | never | renders the template checkout, so it runs from one only |
| `scripts/template_snapshot.py` | never | serves only the audit and the canary |
| `tests/unit/scripts/test_canary.py` | never | its test |
| `tests/unit/scripts/test_template_snapshot.py` | never | its test |
| `tests/integration/test_canary_wiring.py` | never | a test of the template itself |
| `.github/workflows/canary.yml` | never | runs `make canary`, which a project answers with a stub |
| `src/frontend/react-vite` | only when `frontend_stack` is `react-vite` | the stack you did not choose |
| `src/frontend/astro` | only when `frontend_stack` is `astro` | the stack you did not choose |
| `src/frontend` | not when `frontend_stack` is `none` | no frontend |
| `.github/workflows/pages.yml` | only when `frontend_stack` is `astro` | publishes the Astro site |
| `api/grpc` | only when `transports` has `grpc` | an optional transport |
| `tests/unit/api/test_grpc_server.py` | only when `transports` has `grpc` | the test of that transport's server |
| `api/edge_nginx` | only when `transports` has `edge_nginx` | an optional transport |
| `src/backend/showcase` | only with `showcase` | the showcase demo |
| `api/rest_fastapi/showcase_api.py` | only with `showcase` | the showcase demo |
| `scripts/jobs/export_showcase_static.py` | only with `showcase` | the showcase demo |
| `scripts/jobs/build_llms_txt.py` | only with `showcase` | the showcase demo |
| `tests/unit/backend/test_showcase.py` | only with `showcase` | the showcase demo |
| `tests/integration/test_showcase_repo.py` | only with `showcase` | the showcase demo |
| `tests/integration/test_showcase_api.py` | only with `showcase` | the showcase demo |
| `tests/e2e/test_showcase_journey.py` | only with `showcase` | the showcase demo |
| `docs/guides/showcase-site.md` | only with `showcase` | the showcase demo |

Some files arrive tailored to your answers. Each is rendered from a `.jinja`
twin that `config/project.json` `template.twins` declares, and check_N holds
each twin to its plain file:

- `pyproject.toml`, `config/project.json`, `README.md`,
  `docs/guides/README.md`, `scripts/jobs/README.md` and `scripts/README.md`
  differ from keel's only in templated lines;
- `.gitignore` and `CHANGELOG.md` differ by design;
- `.copier-answers.yml` is generated: it records your answers and the template
  commit, and `copier update` reads it.

## `make new` from a template checkout

In a checkout of keel, `make new DEST=../my-project` runs the same `copier copy`
against the checkout. `VCS_REF` picks the commit and defaults to `HEAD`. It
refuses, with exit 2:

- without `DEST` (it prints the usage line);
- when the checkout is not a git checkout, because copier would record no
  `_commit` and the project could never update;
- when the checkout's tree is dirty, because copier would record a commit that
  exists only in its throwaway clone. `ALLOW_DIRTY=1` overrides this refusal
  only.

It records the checkout's absolute local path as `_src_path`, so
`copier update` then works only where that path exists. Generate from a git URL
for a project you will share. A generated project ships the `new` target too,
where it has no template to run; refusing it there is queued for a decision.

## Adopting keel into an existing repository

Generate into the repository's own directory. copier asks before it replaces
each file that already exists, and `--overwrite` replaces them all without
asking. Your history survives: keel's own template tests, which never ship to a
project, generate into a repository with commits and hold the gate green once
the generation is committed.

Then move your code under `src/` and make the checks green in this order, each
step on top of the last:

1. check_B and check_A: every top-level directory is a taxonomy row or named in
   `structure.extra_toplevel`, and carries a labelled `README.md` and
   `CLAUDE.md`.
2. check_H: `config/project.json` says what the project is.
3. check_C, check_D and check_E: package boundaries (`__init__.py` and
   `__all__`), no import of a private module, and a docstring on every
   exported symbol.
4. ruff and mypy: hold a module that is not yet strict under
   `rulesets.mypy.ratchet` and `rulesets.mypy.scope` in `config/practices.json`
   rather than switching a rule off.

Four settings exist for an adopting project: `structure.extra_toplevel` for
your own top-level directories, `work_naming.adoption_boundary` for commits
made before keel, `make_targets.empty_test_selections` for a marker with no
tests yet, and `make_targets.effect_proof_skip` for a target the effect sweep
cannot run. `agents/practice_refactor/` brings existing code toward one named
practice at a time. `limits-and-troubleshooting.md` lists every waiver.

If you keep your own `README.md`, as most projects do after its first update
conflict, `tests/integration/test_doc_drift.py` holds it to keel's rules, and
three of them usually fail together:

- it must link every document `config/project.json` `doc_drift.one_hop` lists
  under `README.md`; edit that list, not the test, to drop a target;
- it must carry the heading `doc_drift.layout_heading` names, `## Top-level
  layout`, over a fenced tree that names every shipping top-level directory;
- the guide `doc_drift.limits_guide` names must hold the two marker lines
  `<!-- exit-codes:begin -->` and `<!-- exit-codes:end -->`. `make exit-codes`
  (`scripts/exit_code_table.py`) writes the exit-code tables between them,
  with a row for each of your own gate scripts that `make verify` reaches
  (`doc_drift.gate_target`); never write a row there by hand.

## Update

Commit your work first: copier refuses to update a project whose tree is dirty,
and an update needs git. An untracked file counts as dirty too, so commit it or
ignore it before you update. git treats a symlink as a file, so a `.gitignore`
pattern with a trailing slash, such as `.venv/`, does not ignore a `.venv`
symlink; keel's `.gitignore` names each directory without one, and
`tests/integration/test_ignore_patterns.py` keeps it so.

```bash
copier update --trust
```

copier re-asks each question with your recorded answer as the default;
`--skip-answered` asks only the questions added since. `--vcs-ref <tag>` updates
to a named release instead of the newest one. copier refuses a ref older than
the `_commit` the project records
([ADR-K-0009](../adr/keel/K-0009-release-identity-and-the-tag-ordering-rule.md)).

Keep copier's default `--conflict inline`. It writes conflict markers into a
file both sides changed, and the migrations refuse to run over a conflicted
file they import or a fixed project file they read, such as
`config/project.json`. `--conflict rej` writes `.rej` files instead, and the
migrations then run over edits that are still waiting there.

`.copier-answers.yml` is tracked. Never edit it by hand; change an answer by
re-answering it in `copier update`.

From a template checkout, `make audit-project DEST=<your project>` previews an
update: it runs a real `copier update` on a scratch copy of the project, judges
the result, never writes the project, and names each edited file the update
would delete. Inside a project, `make audit-project` prints that command.

### Your own scripts end through the exit helper

`tests/integration/test_exit_gate.py`, part of `make test`, reads every Python
file the structure gate walks, and that includes the scripts you wrote. It
fails, naming the file and line, a `sys.exit`, a `raise SystemExit`, an
`os._exit`, the builtins `exit` and `quit`, and an argparse `.exit(...)`. No
setting waives a file. A project whose scripts end on `sys.exit(main())` is
therefore red after the update that brings `scripts/exit_codes.py`, until each
script is moved:

1. Import the helper by its bare name, with `scripts/` on `sys.path`:
   `from exit_codes import ExitCode, finish, passthrough, report`.
2. Make the entry line `finish(main())`.
3. Return `ExitCode.SUCCESS` from `main` where it returned `0`, and
   `report(ExitCode.<MEMBER>, <what failed>, <on which input>, <what to do next>)`
   where it returned another number. Keep each number: the first generated
   table in `limits-and-troubleshooting.md` gives every member's value.
4. Return `passthrough(<status>)` where `main` returned the status of a tool
   it ran, read where it ran it. `finish(passthrough(main()))` over a `main`
   that still returns numbers is red: the gate reads `passthrough` over
   `main`'s result, a literal, a member, or a function of the script that
   returns only those as the script's own status, not a tool's, and wrapping
   one in `int(...)`, `or 0` or a sign does not change that.
5. Call `fail(...)`, with the four arguments of `report`, where a function of
   the script itself outside `main` called `sys.exit`. A module another of
   your modules imports raises instead, and its importer's `main` reports.
6. Give a module that has no status to report, such as an app's `__main__`,
   a `main` that returns nothing, and leave its entry line as `main()`.
7. Run `make exit-codes` when `make verify` runs the script, so the generated
   table gains its row.

The last stderr line of a failure is now `<what failed>: <on which input>;
<what to do next>`, so a caller of yours that matched the old text of a keel
script must match the new. To exit with a code the list does not hold, add a
member to `ExitCode` in `scripts/exit_codes.py` and run `make exit-codes`. A
later update that changes the same lines conflicts in that file, and
`limits-and-troubleshooting.md` has the row for what you then see.

One number carries one fact, so a wrapper of yours can act on the number
alone. `scripts/gate_evidence.py` exits `RED_RECORD` (10) when every goal
passed and the record is red, and `scripts/run_evals.py` exits
`BACKEND_ABSENT` (11) when the live backend did not answer. No keel script
exits 3: a wrapper that tested `$? -eq 3` after either script must test 10 or
11. `scripts/launch.py` exits `NO_CAPACITY` (12) when the farm did not start
the command and the host had no spare compute. `ExitCode` refuses two members
with one value when the module is imported (`enum.unique`), so every script
that imports the helper stops with a `ValueError` naming both members if a
member you added holds a value keel's members hold: 10, 11 or 12 today, and
the generated table in `docs/guides/limits-and-troubleshooting.md` lists every
one. Give yours another value, then run `make exit-codes`.

### The frontend suites refuse an app they cannot run

With a frontend app present, `make test-fe-unit` and `make test-fe-e2e` exit 2
when `npm` or an app's `node_modules` is missing, naming the app and
`make fe-install`, because a suite that ran nothing does not pass. Run
`make fe-install` and `make fe-browsers` after the update, before
`make verify`. The update adds the `make test-fe`,
`test-fe-unit` and `test-fe-e2e` entries to config/project.json
`make_targets.effect_proof_skip`, because the effect sweep's fresh clone has
no `node_modules`. Its CI workflow gains a `make fe-browsers` step and a
`make test-fe` step after `make eval`.

### `make verify` scans the history for committed secrets

The update adds `make secret-scan` to `make verify` and a staged secret-scan
hook to `.pre-commit-config.yaml`. An existing project's `make verify` is red,
its `secret-scan` goal exiting 11 (`BACKEND_ABSENT`), until
`make secrets-install` has installed the scanner config pins and recorded it.
Run it once in each checkout after the update, before the next commit: the
commit hook runs only the recorded program, so it exits 11 until then too. The hook needs no reinstall: the
script `pre-commit install` wrote reads `.pre-commit-config.yaml` on every
commit. A finding in history is not fixed by an
exclusion: `docs/guides/limits-and-troubleshooting.md`, "A credential was
committed", is the procedure. The update adds `secret-scan` to
config/project.json `make_targets.effect_proof_skip`, because the effect
sweep's fresh clone has no record, and its CI workflow gains a
`make secrets-install` step and a `make secret-scan` step before `make test`.

### A gate run has one date, and a git failure stops it

The update brings three stricter rules to `make verify`. Each is an exit 2
before any goal runs, and `limits-and-troubleshooting.md` has a row for each
message.

1. **One date.** `scripts/gate_evidence.py` hands every goal the date the run
   began in `KEEL_GATE_RUN_DATE` (config/project.json
   `evidence.run_date.env`), and `child_env.names` gains that name. If you
   keep your own `child_env.names`, the merge keeps your list: check that the
   name is in it, because the gate refuses an `evidence.run_date.env` the
   allowlist does not carry. A gate that runs longer than
   `evidence.run_date.max_age_days` (`1`) days needs a larger bound. Removing
   `evidence.run_date` returns every check to the clock.
2. **git failures.** A project in a repository git cannot read used to run
   its gates as if there were no git. `scripts/gate_evidence.py`,
   `scripts/run_evals.py`, `scripts/trace_requirements.py` and
   `scripts/run_make_target.py` now refuse and quote git's status. A project
   with no repository, or a host with no git, runs as before. A script of
   yours that imports `scripts/git_tree.py` and catches `NoGitError` no longer
   catches a failed git command: that is `GitFailedError`, and it should stop
   your script too.
3. **Symlinks under `evidence.dir`.** A project whose `.evidence` is a symlink
   to another disk is refused. Point config/project.json `evidence.dir` at a
   real directory inside the project.

### A model adapter sends its credential only to a listed host

The update brings config/project.json `models.allowed_hosts`, with
`openai-compatible` mapped to an empty list. An empty list allows no host, so
a project that calls `openai-compatible` must add its endpoint's host before
the adapter will start: `get_model("openai-compatible", ...)` raises a
`ValueError` naming `models.allowed_hosts.openai-compatible` and the entry to
add, and `make eval-live` refuses with exit 2 before any call. Write the
entry as `host`, or `host:port` for a port other than the scheme's default,
in the form `models/README.md` gives. A project that keeps its own `models`
block keeps it through the merge: add the key yourself, because check_X
reads a missing one as an empty list. The adapter also refuses a redirect
now; a `base_url` that answered with one must point at the URL the endpoint
serves from. [ADR-K-0018](../adr/keel/K-0018-model-endpoint-host-allowlist.md)
is the decision.

### Your imports, handlers, comments and shared modules meet new gate tests

The update brings five rules that `make test` holds your own Python to, each
naming the file it fails on, and `limits-and-troubleshooting.md` has a row for
each message.

1. **Layers.** config/project.json `import_layers.order` lists the layers
   bottom to top, and `tests/integration/test_import_layers_gate.py` fails an
   import into a higher layer and a Python file no layer's prefix holds. A
   top-level directory you added is such a file's home: add its prefix to the
   layer it belongs in, in `config/project.json`. A prefix for a directory you
   do not have is skipped.
2. **Shared modules return.** A module another of your modules imports never
   calls `fail` or `finish` outside its entry block;
   `tests/integration/test_exit_gate.py` fails one that does. Raise instead,
   and let the importer's `main` return `report(...)`. Name a module that must
   end the process, with its reason, in
   `import_layers.may_end_the_process`.
3. **Swallowed errors.** `tests/integration/test_swallowed_error_gate.py`
   fails a bare `except:`, and an `except Exception` whose body only passes,
   continues, breaks, or returns or assigns a fixed value such as `None`,
   `-1` or `[]`, unless its `# noqa: BLE001` or `# noqa: E722` gives a reason
   after the codes; a second code is not a reason. A suppression you already
   carry with no reason is red too.
4. **Change-reporting comments.** `tests/integration/test_change_comment_gate.py`
   fails a comment that opens with a `change_comments.phrases` phrase such as
   `now` or `fixed`. Rewrite it as the reason the code is as it is; add a
   phrase or a directive to the block when your project needs one.
5. **Features rows.** `tests/integration/test_reference_drift.py` derives
   every `tests/integration/test_*_gate.py` and every `scripts/` module that
   a module outside `tests/` imports from your tree, not from keel's file
   list, and fails one with no row in `docs/reference/features.md`. Add a row
   for each of your own under the `Gate tests` or `Shared script modules`
   section; the failure names the file.

check_D also fails `from pkg import _sub` of a private submodule from outside
`pkg/`; import the name `pkg/__init__.py` exports instead.

Rule 2, and the exit gate's rule that a process ends through
`finish(main())`, judge through the expiring tier the section "Your own gate
findings warn until a date" below describes: a finding you record warns until
a date. Rules 1, 3, 4 and 5 fail your own code from the first `make test` after
the update, with no warning period; run `make test` right after the update and
fix each finding they name. `make audit-project` does not preview these
findings: it judges the structure gate's letters, check_D among them, and runs
none of the gate tests.

`make long-scripts` exits 13, `ExitCode.NOTHING_JUDGED`, when no recorded run
carries a duration, which is a fresh clone's state; it exited 1 before, the
status it keeps for a proposal. A caller that read 1 as "nothing recorded"
reads 13.
[ADR-K-0021](../adr/keel/K-0021-imports-flow-up-a-configured-layer-order.md)
is the decision.

### Your config is read through one loader

The update brings `scripts/config_loader.py`, the one reader of
config/project.json, config/practices.json and the variables they declare, and
the config/project.json `config_reads` block. You may meet it three ways.

1. **Default lines on stderr.** A key with a declared default that your
   config/project.json lacks is now named once per process, and the run goes
   on with the default. A project that deleted `evidence.run_date` to switch
   the date channel off sees `[using default] evidence.run_date = null`. The
   exit code does not change. Set the key to silence the line; each defaulted
   key's row in [settings.md](../reference/settings.md) quotes its line, and
   `limits-and-troubleshooting.md` says what each kind of line means.
2. **Exit 14 for a config fault.** A missing or wrong value read by
   `scripts/gate_evidence.py`, `scripts/exit_code_table.py`,
   `scripts/check_practices.py` or `scripts/run_evals.py` exits 14
   (`CONFIG`) where it exited 2. A wrapper or CI step that tested for 2 tests
   for 14 as well. `scripts/check_practices.py` also refuses a
   config/practices.json it cannot parse, where it scanned with no practices
   and exited 0.
3. **Your own direct readers warn until a date.**
   `tests/integration/test_config_reads_gate.py` walks the directories
   `config_reads.roots` names for an open of either config file, or a read of a
   variable the config declares, outside the loader. Its two finding tests
   judge through the expiring tier the next section describes, so a direct
   read is red until `make gate-baseline` records it, and then warns until
   `expiring_tier.expires`. Move such a reader onto the loader before that day:
   `read` the file, then pass `resolve` your own `Key` rows, built with the
   type set `TYPES` and the default in the row.

[ADR-K-0022](../adr/keel/K-0022-one-config-loader.md) is the accepted decision.

### Your own gate findings warn until a date

The update brings the config/project.json `expiring_tier` block,
`scripts/expiring_tier.py`, `scripts/expiring_tier_data.py`,
`scripts/record_gate_baseline.py` and the `make gate-baseline` target. Four
gate tests judge their findings through the tier: the two finding tests of
`tests/integration/test_config_reads_gate.py`, and the two of
`tests/integration/test_exit_gate.py` that fail an exit outside the helper and
a shared module that ends the process. Each judges by these rules.

1. **Run `make gate-baseline` once after the update.** Until it runs, a
   finding in your own code is red, and its line names the target. The target
   runs those four gate tests and writes each finding they saw to the file
   `expiring_tier.baseline` names (`config/gate-baseline.json`), stamped with
   `.copier-answers.yml` `_commit`. Commit the file.
2. **A recorded finding warns.** `make test` passes, and pytest's warnings
   summary prints an `ExpiringTierWarning` that names each recorded finding
   and the date. A finding is matched by its file and its message, not its
   line number, so an edit above it does not turn it red. The same rule
   means a recorded finding fixed and a new one of the same rule added in the
   same file still warns; review holds that.
3. **A new finding is red at once.** At the `_commit` the file records,
   `make gate-baseline` refuses to add an entry and writes nothing; the file
   grows only after the next `copier update` moves `_commit`. So fix a finding
   your own change brought.
4. **The file only shrinks.** An entry no finding matches is red, naming the
   entry. Rerun `make gate-baseline`, or delete the entry, once you fix the
   finding. Deleting the file does not reopen it: while git still holds the
   file, `make gate-baseline` refuses and says to restore it with
   `git checkout -- config/gate-baseline.json`.
5. **The grace ends on a date.** From `expiring_tier.expires` every recorded
   finding is red. You may set an earlier date. A date later than
   `scripts/expiring_tier_data.py` `CEILING`, 2027-01-31, is red, and copier
   rewrites that file on every update.

In the template repository, which holds `copier.yml`, there is no tier: every
finding is red, and `make gate-baseline` exits 2. Nothing stops a hand edit of
the baseline or of `scripts/expiring_tier_data.py`; review holds both, and an
edit of the data file shows as a diff on the next update.
[ADR-K-0027](../adr/keel/K-0027-a-project-s-own-code-warns-until-a-hard-date.md)
is the proposed decision.

### Your shell scripts meet the shell gates

The update asks a new question, `shell`, whose default is yes; taking the
default, as `--defaults` does, answers yes. It writes `shell.enabled`, and
the update brings `scripts/shell_gate.py` and four make targets: `make lint`
gains `make lint-sh` and `make fmt-check-sh`, `make verify` gains
`make test-sh`, and the CI workflow gains a `make test-sh` step. Keel installs
none of the tools they run. Answered yes, a project that carries a shell
script (a `shell.script_suffixes` suffix or a `shell.shebang_shells` shebang)
meets three refusals, and `scripts/shell_gate.py` checks them in this order:

1. **The arriving reason is stale.** The update writes `shell.no_scripts`,
   the reason a fresh project has no shell file. Beside a shell file every
   shell target exits 14 naming the files. Set it to `null`.
2. **The scripts have no test.** `make test-sh` exits 13 while no file ends
   in a `shell.test_suffixes` suffix (`.bats`). Add a test for the scripts.
3. **The tools are missing.** `make lint` exits 11 naming the tool
   `shell.linter` or `shell.formatter` names, and `make test-sh` the one
   `shell.test_runner` names. Install it in the interpreter's directory or on
   PATH.

A vendored script goes in `shell.excluded_paths` with its reason instead of
being edited. A project that wants no shell gate answers no
(`--data shell=false`), or sets `shell.enabled` to `false` later: every shell
target then says so and exits 0. A project with no shell file keeps the
arriving reason and stays green.

### Your Node, Python and runner images come from config

The update brings the config/project.json `toolchain` block,
`scripts/check_toolchain.py` and two gate tests. You may meet them three ways.

1. **`make fe-install` checks Node first.** With a frontend app, it stops
   before npm runs when the major of `node --version` is not
   `toolchain.node_major`, naming both majors. Install that major, or set the
   key to the one your lockfiles were resolved under and commit it.
2. **Your workflows read the versions.** The shipped workflows gain a step
   with id `toolchain` and read setup-node's and setup-python's versions from
   it. `tests/integration/test_toolchain_gate.py` fails a workflow of your own
   that spells a version, or uses a `runs-on` label
   `toolchain.runner_images` does not list, and fails a `toolchain.python`
   below your `layers.backend.python` or `requires-python`. The update asks
   `toolchain_python`, the release it renders into `toolchain.python`, and its
   validator refuses one your `backend_python` does not allow: a project that
   raised its floor answers a release that satisfies it (under `--defaults`,
   pass `--data toolchain_python=<release>`).
3. **Your lockfiles are judged.** `tests/integration/test_frontend_lockfile_gate.py`
   fails a frontend app whose `package-lock.json` is not committed or does not
   record the dependencies its `package.json` names. Run `npm install` in the
   app and commit the lockfile.

## Update checklist

An update runs the steps below in this order. The task runs while copier renders
the new files, before it merges them into your project; every other row is an
after-migration, run once the merged files are written. A step with a condition
runs only when it holds. `git checkout -- <path>`
brings back a file a step removed, as long as you committed it first.

| Step | When | Effect | Exit | Recovery |
|------|------|--------|------|----------|
| task: `scripts/jobs/restamp_docs.py` | every generation and every update | stamps with the day the `updated:` of every document git would commit (every document where there is no git), in each copy copier renders | 0, 1, 2 | `make restamp-docs` |
| `scripts/jobs/keep_edited_retired.py` | every update | keeps an edited copy of a template file the update retires or moves, and names it on stderr | 0, 2 | on 2, resolve each file it names, then run the command it prints, which finishes the update |
| `rm -rf src/frontend/react-vite` | `frontend_stack` is not `react-vite` | removes that stack | none | `git checkout -- src/frontend/react-vite` |
| `rm -rf src/frontend/astro` | `frontend_stack` is not `astro` | removes that stack | none | `git checkout -- src/frontend/astro` |
| `rm -rf src/frontend` | `frontend_stack` is `none` | removes the frontend | none | `git checkout -- src/frontend` |
| `rm -f .github/workflows/pages.yml` | `frontend_stack` is not `astro` | removes the site workflow | none | `git checkout -- .github/workflows/pages.yml` |
| `rm -rf api/grpc` | `transports` lacks `grpc` | removes the transport | none | `git checkout -- api/grpc` |
| `rm -f tests/unit/api/test_grpc_server.py` | `transports` lacks `grpc` | removes the transport's test | none | `git checkout -- tests/unit/api/test_grpc_server.py` |
| `rm -rf api/edge_nginx` | `transports` lacks `edge_nginx` | removes the transport | none | `git checkout -- api/edge_nginx` |
| `rm -rf src/backend/showcase` | `showcase` is off | removes the showcase read model | none | `git checkout -- src/backend/showcase` |
| `rm -f api/rest_fastapi/showcase_api.py` `scripts/jobs/export_showcase_static.py` `scripts/jobs/build_llms_txt.py` `tests/unit/backend/test_showcase.py` `tests/integration/test_showcase_repo.py` `tests/integration/test_showcase_api.py` `tests/e2e/test_showcase_journey.py` `docs/guides/showcase-site.md` | `showcase` is off | removes the showcase's files | none | `git checkout -- <path>` |
| `rm -f wiki/llms.txt` `wiki/llms-full.txt` | `showcase` is off | removes the agent front door | none | `make site-data` |
| `rm -f tests/integration/test_copier_generation.py` `tests/integration/test_copier_generator_contract.py` `tests/integration/test_copier_update.py` | every update | removes tests of the template a project generated before they were excluded still has | none | none needed |
| `rm -f docs/design/keel-hardening-plan.md` | every update | removes the template's plan from a project that still has it | none | none needed |
| `scripts/jobs/declare_no_app.py` | every update | when the update introduces `layers.app` for a composition root the project removed, sets it to `null` and declares the smoke marker and run target that need it | 0, 1, 2 | on 1, make the edits its message names by hand; on 2 over a conflicted file, resolve each file it names, then run the command it prints, which finishes the update; on 2 otherwise, git could not read the pre-update manifest |
| `scripts/jobs/resolve_stamp_conflicts.py` | every update | settles a conflict whose only difference is a document's `updated:` date, taking the later one, and names every other conflict on stderr | 0, 2 | on 0, resolve each conflict it names; on 2, resolve each file it names, then run the command it prints, which finishes the update |
| `scripts/jobs/restamp_docs.py` | every update | restamps the documents the update changed | 0, 1, 2 | on 1, fix each stamp it names, then `make restamp-docs`; on 2, resolve each file it names, then run the command it prints, which finishes the update |

Every after-migration that is a script first checks the files it imports, and
the fixed project files those modules declare reading (`PROJECT_READS`, read by
`scripts/jobs/conflict_guard.py`), for conflict markers, and stops with exit 2
naming each one and the command that finishes the update; copier runs no
migration after it. The one exception is a conflict in `scripts/exit_codes.py`
itself: the migration names it the same way and then stops with exit 1 on the
helper's `SyntaxError`, because the helper is what would have exited 2.

## Finish an update that stopped

When a migration stops over a conflicted file, copier has already written the
new files and the new `_commit` into `.copier-answers.yml`, and it runs no later
migration. The project is half updated, and its tree is dirty. The refusal ends
with the command that finishes the update, under the interpreter copier runs
with, which has the YAML and Jinja libraries the command needs:

```bash
/path/to/copiers/python scripts/jobs/finish_update.py
```

1. Resolve each file the refusal names, by hand, and `git add` it.
2. Run the command the refusal prints. It reads the answers file in your tree
   and at `HEAD`, checks out the template at the commit the update reached, and
   runs that version's after-migrations in the update checklist's order, as
   copier would. Pass `--template <path to a clone of the template>` when the
   `_src_path` the answers record no longer resolves; it refuses until you do.
   `--dry-run` lists the commands and runs none.
3. A step that still fails stops it with exit 2, naming the step: fix what that
   step names, then run the command again. Running it twice changes nothing
   the first run did not.
4. Review the changes, then commit them. The command never stages, commits or
   edits the answers file.

Do not commit and run `copier update` again instead. The commit records the
new `_commit`, so copier sees nothing left to update and never runs the
migrations it skipped. If you already committed, undo that commit and keep its
changes with `git reset --soft HEAD~1`, then run the command.

The command exits 2 without running any step when there is no update to
finish (the answers file records the commit `HEAD` does) and when the template
uses something it cannot replay as copier does: `_envops`,
`_jinja_extensions`, another answers file, a migration key other than
`command` and `when`, or a name the migration renders that it does not supply.
In those cases, run the migrations by hand from the template's `copier.yml`.
`tests/integration/test_finish_update.py` holds each of these to its exit.

## How keel proves an update works

Before a release is pushed, keel checks that the projects it generates pass
their own gate, fresh and after an update. In the keel template checkout,
`make canary` runs `scripts/canary.py`. In a generated project, `make canary`
prints the command to run in the template checkout and exits 2, because a
project has no template to render. `make verify` never runs the canary:
`tests/integration/test_canary_wiring.py` fails a `verify` recipe that names
it.

The canary snapshots the checkout as it stands, with its uncommitted and
untracked files, and builds two projects from the snapshot for each answer set
config/project.json `canary.answer_sets` lists. Each key of a set must be a
question copier.yml asks: copier ignores any other key and renders that
question's default, so the canary refuses such a key with exit 14 before it
renders anything.

1. **fresh**: `copier copy` of the snapshot, committed in a new git repository.
2. **update**: `copier copy` of the previous release tag, committed, then
   `copier update --conflict inline` to the snapshot with the set's answers
   given again, committed, so a question the tag did not ask takes the set's
   answer and not its default. The previous release is the newest dated
   `## [X.Y.Z]` heading of `CHANGELOG.md` whose tag exists and is a strict
   ancestor of `HEAD`, so a run on a commit that already carries the new tag
   updates from the release before it. With no such tag the
   canary exits 2 before it renders anything; `CANARY_FLAGS="--path fresh"`
   runs the fresh path alone.

Each project then runs `make fe-install` and `make fe-browsers`, which exit 0
when the project's Makefile `FE_APPS` names no frontend app, `make secrets-install`,
and then its own `make verify`. A step that runs past
`canary.step_timeout_minutes` is killed and fails. Each set and path prints one
line:

```text
default update fe-install fail /path/.canary/all-both/default-update.log 212s
skeleton fresh verify pass /path/.canary/all-both/skeleton-fresh.log 404s
```

The six fields are the answer set, the path, the last step the project
reached, `pass` or `fail`, that project's log, and the elapsed seconds. The
step says what failed:

| Step | A `fail` there means |
|------|----------------------|
| `copy` | copier could not render the snapshot or the tag with the set's answers |
| `commit` | git could not initialise the project or commit it |
| `update` | `copier update` failed, or it left a path git lists as unmerged or a file holding a conflict hunk |
| `fe-install` | `scripts/check_toolchain.py node` refused the Node major, or npm could not install a frontend app |
| `fe-browsers` | the browser the end-to-end suites drive could not be installed |
| `secrets-install` | `scripts/install_scanner.py` could not fetch the pinned secret scanner release, its sha256 differed from the pin, or this platform has no pinned archive |
| `verify` | the project's own `make verify` is red; every `pass` line names this step too |

A passing project is deleted. A failing one is kept at
`<scratch root>/<run>/<set>-<path>`, named on stderr with its log beside it,
and the run exits 1 naming each kept project. Every set runs even after one
fails. The scratch root is config/project.json `canary.scratch_root`, `.canary`
in the checkout, which git ignores; `KEEL_CANARY_SCRATCH` moves it, for
example onto a farm node's local disk. The canary refuses a scratch root under
the system temporary directory, and one inside the checkout that git does not
ignore.

To rerun one failed project, run
`make canary CANARY_FLAGS="--set <set> --path <path>"`. Its run directory is
`<set>-<path>`, not the `all-both` of a full run, so the project kept by the
full run stays. A run replaces its own run directory, so a second run with the
same flags deletes the project the first one kept.

Each line costs a whole project `make verify`. With keel's two answer sets,
measured on the farm on 2026-10-17 with one job per set and
`canary.workers` 1, each project took 404 to 494 seconds and the whole canary
about 31 minutes. That is why the canary runs at three points and no other:
CONTRIBUTING.md's Release steps run it before the push,
`.github/workflows/canary.yml` runs it weekly and on demand, and a maintainer
runs it by hand. The astro frontend stack is in no answer set, so no canary
renders it; `tests/integration/test_frontend_lockfile_gate.py` checks its
lockfile without installing it.

`tests/integration/test_canary_wiring.py` holds this section to the canary: the
step table names each step a line can report as failed and no other, the
example lines have the fields the canary prints, and the section names the
answer-set key and the scratch variable.
