---
title: Generate and upgrade
kind: doc
layer: n/a
status: template
owner: TBD
tags: [copier, generate, update, migrations, adoption, guide]
summary: How a project is generated from keel, what arrives and what never does, what `make new` refuses, how to adopt keel into an existing repository, and how `copier update` pulls template changes — with one checklist row per task and migration an update runs.
id: docs-guides-generate-and-upgrade
created: 2026-10-09
updated: 2026-10-09
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

## Update

Commit your work first: copier refuses to update a project whose tree is dirty,
and an update needs git.

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
file they import. `--conflict rej` writes `.rej` files instead, and the
migrations then run over edits that are still waiting there.

`.copier-answers.yml` is tracked. Never edit it by hand; change an answer by
re-answering it in `copier update`.

From a template checkout, `make audit-project DEST=<your project>` previews an
update: it runs a real `copier update` on a scratch copy of the project, judges
the result, never writes the project, and names each edited file the update
would delete. Inside a project, `make audit-project` prints that command.

## Update checklist

An update runs the steps below in this order. The task runs while copier renders
the new files, before it merges them into your project; every other row is an
after-migration, run once the merged files are written. A step with a condition
runs only when it holds. `git checkout -- <path>`
brings back a file a step removed, as long as you committed it first.

| Step | When | Effect | Exit | Recovery |
|------|------|--------|------|----------|
| task: `scripts/jobs/restamp_docs.py` | every generation and every update | stamps with the day the `updated:` of every document git would commit (every document where there is no git), in each copy copier renders | 0, 1, 2 | `make restamp-docs` |
| `scripts/jobs/keep_edited_retired.py` | every update | keeps an edited copy of a template file the update retires or moves, and names it on stderr | 0, 2 | resolve each file it names, then rerun the command it prints |
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
| `scripts/jobs/declare_no_app.py` | every update | when the update introduces `layers.app` for a composition root the project removed, sets it to `null` and declares the smoke marker and run target that need it | 0, 1, 2 | on 1, make the edits its message names by hand; on 2, git could not read the pre-update manifest |
| `scripts/jobs/resolve_stamp_conflicts.py` | every update | settles a conflict whose only difference is a document's `updated:` date, taking the later one, and names every other conflict on stderr | 0, 2 | resolve each conflict it names |
| `scripts/jobs/restamp_docs.py` | every update | restamps the documents the update changed | 0, 1, 2 | `make restamp-docs` once the conflicts are resolved |

Every after-migration that is a script first checks the files it imports for
conflict markers, and stops with exit 2 naming each one and the command to rerun;
copier runs no migration after it.
