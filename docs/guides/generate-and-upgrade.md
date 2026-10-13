---
title: Generate and upgrade
kind: doc
layer: n/a
status: template
owner: TBD
tags: [copier, generate, update, migrations, adoption, guide]
summary: How a project is generated from keel, what arrives and what never does, what `make new` refuses, how to adopt keel into an existing repository, and how `copier update` pulls template changes — with one checklist row per task and migration an update runs, and how to finish an update a migration stopped.
id: docs-guides-generate-and-upgrade
created: 2026-10-09
updated: 2026-10-13
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

## What arrives and what never does

Every template file arrives except the ones below. An entry with a condition is
left out only when the answer matches it.

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
| `tmp` | never | scratch space |
| `docs/design/keel-hardening-plan.md` | never | the template's own plan |
| `docs/design/documentation-quality.md` | never | the template's own design note |
| `docs/design/downstream-feedback.md` | never | the template's own design note |
| `wiki/corpus.json` | absent; `make site-data` builds it | a generated view of the tree |
| `wiki/llms.txt` | absent; `make site-data` builds it with the showcase | a generated view of the corpus |
| `wiki/llms-full.txt` | absent; `make site-data` builds it with the showcase | a generated view of the corpus |
| `wiki/.runtime` | never | runtime state |
| `api/rest_fastapi/openapi.json` | absent; `api/rest_fastapi/export_openapi.py` writes it | generated from the app |
| `tests/integration/test_copier_*.py` | never | tests of the template itself |
| `scripts/audit_project.py` | never | runs from a template checkout only |
| `tests/unit/scripts/test_audit_project.py` | never | its test |
| `src/frontend/react-vite` | only when `frontend_stack` is `react-vite` | the stack you did not choose |
| `src/frontend/astro` | only when `frontend_stack` is `astro` | the stack you did not choose |
| `src/frontend` | not when `frontend_stack` is `none` | no frontend |
| `.github/workflows/pages.yml` | only when `frontend_stack` is `astro` | publishes the Astro site |
| `api/grpc` | only when `transports` has `grpc` | an optional transport |
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
   it ran.
5. Call `fail(...)`, with the four arguments of `report`, where code outside
   `main` called `sys.exit`.
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
