---
title: Feature catalogue
kind: doc
layer: n/a
status: template
owner: TBD
summary: Every feature keel ships, with what it does and why, how to run it, the settings it reads, where it stops and what it is not for, the guide that explains it, and which projects receive it. The rows of the shapes the tree declares are derived-equal to the tree by tests/integration/test_reference_drift.py.
id: docs-reference-features
created: 2026-10-09
updated: 2026-10-10
visibility: internal
canonical: true
---

# Feature catalogue

This page lists every feature keel ships, one row each, with its limits.
`config/project.json` `doc_drift.features_reference` names this page, and
`tests/integration/test_reference_drift.py` holds its rows to the tree. Every
section's table has the same seven columns, and the first code span in the
Feature cell is the row's key. The `## Conventions` section at the end says
which keys the test derives and what the Ships column means.

## Deterministic checks

`scripts/check_structure.py` runs one check per letter. Each check reads the
tree and writes nothing; `make check` runs all of them.
[deterministic-checks.md](../guides/deterministic-checks.md) explains each one.

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `check_A` frontmatter | Refuses a governed document without valid frontmatter labels or with a duplicate `id`, so every document can be found and owned. | `make check` | — | Not a prose review: it reads the labels, not the body. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_B` closed taxonomy | Refuses a top-level directory that is not a CONVENTIONS §2 row or declared, and a labelled directory without `README.md` and `CLAUDE.md`. | `make check` | [`structure.extra_toplevel`](settings.md#configprojectjson) | Does not judge nested directories, except each one directly under `agents/`. An undeclared symlinked directory is a WARN. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_C` package boundary | Refuses a `src/` directory holding Python without an `__init__.py` that defines `__all__`. | `make check` | — | Only `src/`; it does not judge what `__all__` exports. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_D` private imports | Refuses an absolute import of another package's `_private` module, so `__init__.py` stays the API. | `make check` | — | It also flags the stdlib `_thread` and `_pytest` internals, and has no waiver. A file that does not parse is a WARN. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `check_E` authored coverage | Refuses an `__all__`-exported symbol with no docstring, because the corpus uses it as the symbol's summary. | `make check` | — | Judges presence only, not whether the docstring is true. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_F` tool specs | Refuses a malformed `kind: tool` spec, and warns when a tool or agent document has no real owner. | `make check` | — | The owner rule is a WARN, not an error. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_G` tool and agent binding | Refuses a tool that an agent's `tools.md` lists without the spec's `## Used by` naming that agent, or the reverse. | `make check` | — | Judges the two lists agree; it does not run the tool. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_H` project facts | Refuses a `config/project.json` fact the tree contradicts, such as a stack, a transport or `layers.app`. | `make check` | [`layers.app`](settings.md#configprojectjson), [`frontend`](settings.md#configprojectjson) | `models.default` and `runtimes.default` are checked for shape only, not against the registry constants. A missing manifest is a WARN. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `check_I` agent-rules symlink | Refuses a `CLAUDE.md` that is not a symlink to its sibling `AGENT.md`, so every agent tool reads one file. | `make check` | — | Not for the content of the rules. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_J` owned exceptions | Refuses a `raise` of an exception type imported from a foreign module in `src`, `models`, `runtimes` and `agents`. | `make check` | [a practice's `status`](settings.md#configpracticesjson) | Waivable with `# practice-ok: <reason>`. Other code roots are not judged. | [coding-practices.md](../guides/coding-practices.md) | always |
| `check_K` frozen config | Refuses a class carrying the frozen-config marker that is not provably immutable. | `make check` | [`tokens.config_marker`](settings.md#configpracticesjson) | Silent when no marker is declared. It reads the marker, never a `*Config` name. | [coding-practices.md](../guides/coding-practices.md) | always |
| `check_L` naked tensors | Warns on a parameter annotated with a bare tensor type and no shape comment. | `make check` | [`practices.profiles`](settings.md#configprojectjson), [`tokens.tensor_base_types`](settings.md#configpracticesjson) | A WARN only, and only with the cuda profile on: a token may name a local class. | [coding-practices.md](../guides/coding-practices.md) | always |
| `check_M` ruleset parity | Refuses a `pyproject.toml` that loosens the ruff or mypy policy `config/practices.json` declares. | `make check` | [`rulesets.ruff.extend_select`](settings.md#configpracticesjson) | Reads `pyproject.toml` as text; it does not run ruff or mypy. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_N` template twin parity | Refuses an undeclared `*.jinja` twin, and a parity twin that stops reproducing its file. | `make check` | [`template.twins.<path>`](settings.md#configprojectjson) | Silent in a generated project, which has no twins. It cannot render jinja, so it proves less than a render. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_O` module headers | Refuses a code-root module without the `title:` and `summary:` header lines the corpus reads. | `make check` | — | Judges the lines exist, not that the summary is true. | [python-style.md](../guides/python-style.md) | always |
| `check_P` make help parity | Refuses a `## `-annotated target that the `help` recipe's own pattern cannot list. | `make check` | — | Reads included makefiles; an include named through a variable or a wildcard is not read and is a WARN. Silent without a `help` target. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_Q` cross-references | Refuses a relative Markdown link or a `§N` citation that names nothing. | `make check` | — | A link inside a code span is not a link. It does not fetch URLs. | [doc-style.md](../guides/doc-style.md) | always |
| `check_R` catalogue parity | Refuses a disagreement between the checks catalogue and the Makefile and pre-commit triggers that run the checks. | `make check` | — | Silent without a catalogue; the shapes it cannot read are WARNs. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_S` roster parity | Refuses a README `## What ships here` table that disagrees with its directory or has an empty `Not for` cell. | `make check` | — | Opt-in: a README without the heading is not judged. | [doc-style.md](../guides/doc-style.md) | always |
| `check_T` practice mechanisms | Refuses a practice whose `enforced_by` names a mechanism that does not exist. | `make check` | [a practice's `enforced_by`](settings.md#configpracticesjson) | Silent without a practices registry. It proves the mechanism exists, not that it enforces the practice. | [coding-practices.md](../guides/coding-practices.md) | always |
| `check_U` policy reachability | Refuses a practice whose policy document is more than one hop from the root `AGENT.md`. | `make check` | [a practice's `enforced_by`](settings.md#configpracticesjson) | Silent without a practices registry or without `AGENT.md`. | [coding-practices.md](../guides/coding-practices.md) | always |
| `check_V` writer declarations | Refuses a module that writes to the filesystem without `effect: writes` and a `rerun:`, or a `fixed-point` claim without a proof that resolves. | `make check` | — | Silent over `tests/`. A write it cannot see is a WARN when declared and invisible when not. | [idempotency.md](../guides/idempotency.md) | always |
| `check_W` effect labels | Refuses an annotated make target without a well-formed effect label, or a `[write]` recipe that does not open with `$(WRITE_GUARD)`. | `make check` | [`make_targets.write_shapes`](settings.md#configprojectjson) | A label is a claim; `tests/integration/test_make_target_effects.py` measures it. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_X` child environment | Refuses a Python spawn without `env=build_child_env(...)`, and an allowlist that admits a credential or repository-context name. | `make check` | [`child_env.names`](settings.md#configprojectjson), [`models.credential_env.<adapter>`](settings.md#configprojectjson) | Python spawns only: a recipe that runs `npm` hands it make's whole environment. Defence-in-depth, not a sandbox. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `check_Y` ADR number spaces | Refuses an ADR file outside its number space, a malformed name, or a number used twice in one space. | `make check` | [`adr.project_dir`](settings.md#configprojectjson), [`adr.template_adrs`](settings.md#configprojectjson) | Judges names and numbers, not the decision. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `check_Z` work naming | Refuses a plan doc's slice cell that is not a slice id, and a slice table under no single campaign heading. | `make check` | [`work_naming.plan_kinds`](settings.md#configprojectjson) | Judges plan docs; commit trailers are `tests/integration/test_work_trailers.py`'s. | [dev-loops.md](../guides/dev-loops.md) | always |
| `structure.project_checks` | Runs a project's own structure checks, from modules in a declared directory, after A–Z. | `make check` | [`structure.project_checks`](settings.md#configprojectjson) | Not for editing `scripts/check_structure.py`, which `copier update` merges and may conflict. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |

## Checker scripts

Each script below is one row of the checks catalogue or is reached from
`make check-all`.

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `scripts/check_structure.py` | Runs checks A–Z and the project's own checks on a bare `python3`, so pre-commit can gate without a virtual environment. | `make check` | [`scripts/check_structure.py --only`](settings.md#command-line-flags) | Stdlib only and 3.6-safe, so it cannot read TOML or YAML through a parser. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `scripts/check_python_version.py` | Fails early, with a plain message, when the interpreter is older than `requires-python`. | `make check-python` | [`PY`](settings.md#make-variables) | Assumes a 3.10 floor when `pyproject.toml` declares none. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `scripts/jobs/check_corpus.py` | Proves a fresh corpus build is valid, acyclic and reproducible, and that a local `wiki/corpus.json` is current. | `make check-corpus` | — | Passes when no local corpus has been built; it then judges a fresh build only. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `api/rest_fastapi/export_openapi.py` | Fails when the committed `openapi.json` differs from the live routes, and writes it without `--check`. | `make check-openapi` | [`api/rest_fastapi/export_openapi.py --check`](settings.md#command-line-flags) | Skips when FastAPI is not installed. A missing `openapi.json` means no contract is published yet. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `scripts/agent_surface/generate_aad_schema.py` | Fails when the committed AAD JSON Schema differs from the model, and writes it without `--check`. | `make check-aad` | [`scripts/agent_surface/generate_aad_schema.py --check`](settings.md#command-line-flags) | Skips when pydantic is not installed. | [agent-surface.md](../guides/agent-surface.md) | always |
| `scripts/cdmon_sync.py` | Runs the external cdmon code-to-doc drift check, as the worked example of a thin adapter over an external tool. | `make check-cdmon` | — | A stated skip until `cdmon` is on PATH and `config/cdmon/cdmon.yaml` exists; cdmon is not on PyPI. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `scripts/accountability_report.py` | Lists corpus nodes that resolve to no owner. | `make advise` | — | Informational: it never fails the build. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `scripts/jobs/review_docs.py` | Judges every governed document's `updated:` stamp against its last commit, and lists backticked paths that resolve to nothing. | `make check-docs` | [`scripts/jobs/review_docs.py --strict`](settings.md#command-line-flags) | Stale stamps fail only under `--strict`; unresolved mentions stay advisory. No git is a stated skip. | [doc-style.md](../guides/doc-style.md) | always |
| `scripts/check_generic.py` | Flags a distinctive literal that a test asserts and `src/` hardcodes, the answer-key smell. | `make advise` | — | Advisory only: it never fails the build, and it over- and under-flags. | [generic-solution.md](../guides/generic-solution.md) | always |
| `scripts/check_practices.py` | Flags coding-practice smells, such as a provider constructed inline or a long `isinstance` chain. | `make advise` | [a practice's `status`](settings.md#configpracticesjson) | Advisory only: these are judgment calls. | [coding-practices.md](../guides/coding-practices.md) | always |

## Make targets

Each annotated target, with the effect label its `## ` help opens with. `make
help` lists them; `make help EFFECT=<word>` filters by label.

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `make help` `[local]` | Lists every annotated target with its effect label. | `make help` | [`EFFECT`](settings.md#make-variables), [`AREA`](settings.md#make-variables) | Lists annotated targets only. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `make check-python` `[local]` | Fails early when the interpreter is older than `requires-python`. | `make check-python` | [`PY`](settings.md#make-variables) | Judges the version, not the installed packages. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `make new` `[local]` | Generates a new project from this checkout with copier's questions. | `make new DEST=../my-project` | [`DEST`](settings.md#make-variables), [`ALLOW_DIRTY`](settings.md#make-variables) | Refuses a checkout without git or with a dirty tree; needs the `template` extra. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |
| `make audit-project` `[local]` | Reports what another keel project would fail under this template's gates after `copier update`, on a scratch copy. | `make audit-project DEST=../my-project` | [`DEST`](settings.md#make-variables) | Runs from the template checkout only; in a generated project it names that checkout. It never writes `DEST`. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |
| `make check` `[local]` | Runs checks A–Z and the project's own checks. | `make check` | — | Structure only: no lint, types or tests. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `make check-all` `[local]` | Runs every gating deterministic check on the project interpreter. | `make check-all` | [`PY`](settings.md#make-variables) | Not the whole gate: lint, types and tests are `make verify`'s. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `make check-corpus` `[local]` | Proves the corpus build is valid and reproducible. | `make check-corpus` | — | Passes when no local corpus exists. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `make check-openapi` `[local]` | Fails when `openapi.json` differs from the live routes. | `make check-openapi` | — | Skips without FastAPI. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `make check-aad` `[local]` | Fails when the AAD schema differs from the model. | `make check-aad` | — | Skips without pydantic. | [agent-surface.md](../guides/agent-surface.md) | always |
| `make check-cdmon` `[local]` | Runs the cdmon code-to-doc drift check. | `make check-cdmon` | — | A stated skip until cdmon and its config exist. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `make check-docs` `[local]` | Runs the structure gate and the strict freshness review, which every doc-review edit is gated on. | `make check-docs` | — | Judges stamps and structure, not prose quality. | [doc-style.md](../guides/doc-style.md) | always |
| `make restamp-docs` `[tree]` | Sets a stale `updated:` to today on each document that needs it, the fix `make check-docs` names. | `make restamp-docs` | [`scripts/jobs/restamp_docs.py --today`](settings.md#command-line-flags) | Changes the stamp only; it does not review the change. | [idempotency.md](../guides/idempotency.md) | always |
| `make doc-review` `[local]` | Lists the doc review's findings, rules and baseline without a model. | `make doc-review` | — | A dry run: it writes nothing. | [doc-style.md](../guides/doc-style.md) | always |
| `make doc-review-apply` `[tree,cost]` | Applies one model-made edit per doc-review finding, each gated on `make check-docs`. | `make doc-review-apply` | [`models.default`](settings.md#configprojectjson) | Spends model calls; an edit that reds the gate is rolled back. | [doc-style.md](../guides/doc-style.md) | always |
| `make advise` `[local]` | Runs the advisory checks: answer keys, practice smells, unowned nodes and stale stamps. | `make advise` | — | Never fails the build. | [generic-solution.md](../guides/generic-solution.md) | always |
| `make check-generic` `[local]` | An alias for `make advise`. | `make check-generic` | — | The same advisory run; not a gate. | [generic-solution.md](../guides/generic-solution.md) | always |
| `make verify` `[local]` | Runs every gate: checks, lint, types and tests. "Done" means this exits 0. | `make verify` | [`PY`](settings.md#make-variables) | The frontend gates exit 0 when no frontend app or `node_modules` is found. | [dev-loops.md](../guides/dev-loops.md) | always |
| `make test` `[local]` | Runs the whole test suite. | `make test` | [`PYTHONPATH`](settings.md#make-variables) | Not lint or types. | [dev-loops.md](../guides/dev-loops.md) | always |
| `make unit` `[local]` | Runs the unit tests only. | `make unit` | — | Unit tests touch no network, disk or process. | [dev-loops.md](../guides/dev-loops.md) | always |
| `make integration` `[local]` | Runs the integration tests only. | `make integration` | — | Some skip without git or an optional dependency. | [dev-loops.md](../guides/dev-loops.md) | always |
| `make e2e` `[local]` | Runs the end-to-end tests only. | `make e2e` | — | Python scenarios; a frontend journey needs its own runner. | [dev-loops.md](../guides/dev-loops.md) | always |
| `make smoke` `[local]` | Runs the smoke tests only. | `make smoke` | — | A quick health signal, not the gate. | [dev-loops.md](../guides/dev-loops.md) | always |
| `make lint` `[local]` | Lints Python and the frontend, and checks Python formatting. | `make lint` | — | The frontend half exits 0 without `npm` or `node_modules`. | [python-style.md](../guides/python-style.md) | always |
| `make lint-py` `[local]` | Lints Python with ruff. | `make lint-py` | — | Ruff's rules only; review holds the rest of the house style. | [python-style.md](../guides/python-style.md) | always |
| `make lint-fe` `[local]` | Lints each frontend app with ESLint. | `make lint-fe` | [`FE_APPS`](settings.md#make-variables) | Exits 0 when no frontend app, `npm` or `node_modules` is found. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `make fmt` `[tree]` | Formats Python with ruff. | `make fmt` | — | Writes the tree; the gate runs `make fmt-check` instead. | [python-style.md](../guides/python-style.md) | always |
| `make fmt-check` `[local]` | Checks Python formatting without writing. | `make fmt-check` | — | Python only. | [python-style.md](../guides/python-style.md) | always |
| `make typecheck` `[local]` | Type-checks Python and the frontend. | `make typecheck` | — | The frontend half exits 0 without `node_modules`. | [python-style.md](../guides/python-style.md) | always |
| `make typecheck-py` `[local]` | Type-checks Python with mypy in strict mode, over the files `pyproject.toml` names. | `make typecheck-py` | — | Only the files `[tool.mypy] files` lists. | [python-style.md](../guides/python-style.md) | always |
| `make typecheck-fe` `[local]` | Type-checks each frontend app. | `make typecheck-fe` | [`FE_APPS`](settings.md#make-variables) | Exits 0 when no frontend app or `node_modules` is found. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `make fe-install` `[tree,read]` | Installs each frontend app's npm dependencies. | `make fe-install` | [`FE_APPS`](settings.md#make-variables) | Reads the network; its dependencies are outside the child-process allowlist. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `make run` `[local]` | Runs the composition root `config/project.json` `layers.app` declares. | `make run` | [`layers.app`](settings.md#configprojectjson) | Refuses when `layers.app` is `null`. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |
| `make site-data` `[local]` | Rebuilds the corpus, and the agent `llms.txt` files where the showcase ships. | `make site-data` | — | Without the showcase it builds the corpus only and says so. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `make site-static` `[local]` | Snapshots the showcase to static files for a static site build. | `make site-static` | [`BASE_URL`](settings.md#make-variables) | Without the showcase it skips and says so. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |
| `make run-api` `[local]` | Serves the REST API with uvicorn on port 8000, reloading on change. | `make run-api` | — | A development server, not a deployment. | [agent-surface.md](../guides/agent-surface.md) | always |
| `make run-web` `[local]` | Serves the first frontend app's dev server; the Astro app's dev server proxies `/api` and `/health` to the REST API. | `make run-web` | [`API_PROXY_TARGET`](settings.md#environment-variables) | Refuses a project with no frontend app. The react-vite app, the default `frontend_stack`, makes no API call and its `vite.config.ts` has no `/api` proxy, although the target's `## ` help says it proxies for every stack. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |
| `make demo` `[local]` | Runs the demo in `demo/`. | `make demo` | — | An illustration, not a test. | [agent-runtimes.md](../guides/agent-runtimes.md) | always |
| `make agent-surface-schema` `[tree]` | Regenerates the committed AAD JSON Schema from the model. | `make agent-surface-schema` | — | Writes the tree; `make check-aad` is the gate. | [agent-surface.md](../guides/agent-surface.md) | always |

## Copier jobs

Each job runs under `copier copy` or `copier update` and refuses, naming the
file, the line and the command that finishes the update, when a file it reads
holds a conflict hunk.

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `scripts/jobs/keep_edited_retired.py` | Restores a file the update deleted that the project had edited, because copier deletes a retired file before any migration runs. | runs under `copier update` | — | Restores edited files only; an unedited retired file stays deleted. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |
| `scripts/jobs/declare_no_app.py` | Declares `layers.app` `null` when the update brings a composition root the project deleted. | runs under `copier update` | [`layers.app`](settings.md#configprojectjson) | Acts only when the path is absent and the old manifest had no `layers.app`. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |
| `scripts/jobs/resolve_stamp_conflicts.py` | Resolves a conflict in a document's `updated:` stamp, where both sides touched the file. | runs under `copier update` | — | Resolves the stamp line only; any other hunk stays for you. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |
| `scripts/jobs/restamp_docs.py` | Sets a stale `updated:` to today, so a fresh render passes the freshness rule. | runs under `copier copy` and `copier update`; `make restamp-docs` | [`scripts/jobs/restamp_docs.py --today`](settings.md#command-line-flags) | Changes no byte but the stamp. | [idempotency.md](../guides/idempotency.md) | always |
| `scripts/jobs/finish_update.py` | Replays the migrations copier never reached after a refusal, which is the command each refusal names. | `python3 scripts/jobs/finish_update.py` | [`scripts/jobs/finish_update.py --dry-run`](settings.md#command-line-flags) | Not a copier job copier runs itself; you run it after fixing the conflict. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |
| `copier copy` and `copier update` | Generates a project from the template and later merges the template's changes into it. | `copier copy --trust <template> <dest>` | [`project_name`](settings.md#copier-questions), [`showcase`](settings.md#copier-questions) | Needs `--trust` because the template runs migrations. An update can conflict with your edits to template files. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | always |

## Agents

Each agent directory holds a brain and its prompt; tools are thin specs over
`scripts/` doers.

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `agents/doc_reviewer/` | Reviews the documentation against the doc style: deterministic findings first, then one judged edit per chunk, each gated on `make check-docs`. | `make doc-review`; `make doc-review-apply` | [`models.default`](settings.md#configprojectjson) | Applying spends model calls; an edit that reds the gate is rolled back. | [doc-style.md](../guides/doc-style.md) | always |
| `agents/index_enforcer/` | Enforces conventions and builds the accountable wiki corpus. | through `runtimes/` | — | No command line of its own. | [agent-runtimes.md](../guides/agent-runtimes.md) | always |
| `agents/practice_refactor/` | Refactors code toward one named practice, a corpus neighbourhood at a time, gating every edit on `make verify`. | `python3 scripts/refactor_practice.py` | [a practice's `id`](settings.md#configpracticesjson) | One practice per run; it cannot mark a chunk done while the gate is red. | [coding-practices.md](../guides/coding-practices.md) | always |
| `agents/triage/` | An example brain that summarises an event payload. | through `runtimes/` | — | An example: its Stop hook script is not wired by default. | [agent-runtimes.md](../guides/agent-runtimes.md) | always |
| `agents/wiki_navigator/` | Answers questions from the wiki corpus, with citations and provenance. | through `mcp/qa_server.py` | — | Answers from the built corpus only; run `make site-data` first. | [agent-runtimes.md](../guides/agent-runtimes.md) | always |
| `agents/tools/` | The shared tool specs: how an agent invokes a `scripts/` doer, its effect and when not to use it. | read by the agents | — | Specs, not code; check_F and check_G hold them. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |

## Model and runtime adapters

A provider is a thin adapter behind a registry, so no doer names a vendor.

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `model:claude-code-headless` | Runs a prompt through a coding-agent CLI in headless mode, with the allowlisted environment. | `get_model("claude-code-headless")` | [`models.default`](settings.md#configprojectjson), [`models.credential_env.<adapter>`](settings.md#configprojectjson) | Needs the CLI installed; a missing binary is `ModelUnavailable`. | [agent-runtimes.md](../guides/agent-runtimes.md) | always |
| `model:fake` | A deterministic, offline model for tests and disconnected development. | `get_model("fake")` | [`models.available`](settings.md#configprojectjson) | Not a real model: its answers are canned. | [agent-runtimes.md](../guides/agent-runtimes.md) | always |
| `model:openai-compatible` | Talks to any endpoint that speaks the chat-completions API. | `get_model("openai-compatible")` | [`models.available`](settings.md#configprojectjson) | Needs a reachable endpoint and its key in the environment. | [agent-runtimes.md](../guides/agent-runtimes.md) | always |
| `runtime:inprocess` | The default, dependency-free Plan executor, with dry-run, durability, human-in-the-loop, fan-out and streaming. | `get_runtime("inprocess")` | [`runtimes.default`](settings.md#configprojectjson) | One process: a checkpoint survives a restart, not a lost host. | [agent-runtimes.md](../guides/agent-runtimes.md) | always |
| `runtime:langgraph` | Compiles a neutral Plan into a LangGraph state graph. | `get_runtime("langgraph")` | [`runtimes.available`](settings.md#configprojectjson) | Needs the `langgraph` profile's dependencies installed. | [agent-runtimes.md](../guides/agent-runtimes.md) | always |

## Transports, MCP servers and workflows

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `mcp/qa_server.py` | Read-only MCP tools that answer questions from the corpus through the wiki navigator. | `python3 mcp/qa_server.py` | — | Read-only; it answers from the built corpus. | [agent-surface.md](../guides/agent-surface.md) | always |
| `mcp/action_server.py` | State-changing MCP tools that delegate to `scripts/jobs/` doers, dry-run by default. | `python3 mcp/action_server.py` | — | A dry run unless the caller asks to execute. | [agent-surface.md](../guides/agent-surface.md) | always |
| `REST API` | A thin FastAPI app over `src/`, with a health route and an example resource. | `make run-api` | [`transports.enabled`](settings.md#configprojectjson) | Holds no domain logic; `api/` stays thin. | [agent-surface.md](../guides/agent-surface.md) | always |
| `REST CORS default` | The REST app allows any origin, `GET` only, so a browser frontend can read it in development. | `make run-api` | — | Not a production policy: narrow the origins before you deploy. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `gRPC transport` | A gRPC edge over the same `src/` logic. | see `api/grpc/` | [`transports`](settings.md#copier-questions) | Present only when the project chose it. | `api/grpc/` | when transports=grpc |
| `edge nginx` | An nginx edge in front of the REST app. | see `api/edge_nginx/` | [`transports`](settings.md#copier-questions) | Present only when the project chose it; a config, not a hardened deployment. | `api/edge_nginx/` | when transports=edge_nginx |
| `.github/workflows/ci.yml` | Runs `make check-all`, lint, types, `make site-data` and the tests on every push and pull request. | push or open a pull request | — | One runner image and one Python version. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `.github/workflows/scheduled.yml` | Runs the doc review nightly and uploads its JSON as an artifact, the same doer `ops/scheduled/` runs from cron. | the schedule, or a manual run | — | Reports only: it changes nothing in the repository. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `.github/workflows/pages.yml` | Builds the static showcase and deploys it to GitHub Pages on a push to `main`. | push to `main` | [`frontend_stack`](settings.md#copier-questions) | Present only with the astro stack, and only useful with the showcase. | `docs/guides/showcase-site.md` | when frontend_stack=astro |

## Frontends and the showcase

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `react-vite frontend` | A React and Vite app under `src/frontend/react-vite/`. | `make run-web` | [`frontend_stack`](settings.md#copier-questions) | One stack per project; switching stacks on update deletes the old app. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | when frontend_stack=react-vite |
| `astro frontend` | An Astro site under `src/frontend/astro/`, which can build to static files. | `make run-web` | [`frontend_stack`](settings.md#copier-questions) | One stack per project; switching stacks on update deletes the old app. | [generate-and-upgrade.md](../guides/generate-and-upgrade.md) | when frontend_stack=astro |
| `showcase` | A site that presents the project from its own corpus: features, principles, checks, models and the wiki. | `make run-api` and `make run-web` | [`showcase`](settings.md#copier-questions) | A presentation of the repository, not a product feature of yours. | `docs/guides/showcase-site.md` | when showcase |
| `agent llms.txt` | Writes `llms.txt` and `llms-full.txt` from the corpus for agents to read. | `make site-data` | [`showcase`](settings.md#copier-questions) | Generated, never hand-edited, and not committed. | `docs/guides/showcase-site.md` | when showcase |

## Corpus, hooks and environment

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `corpus pipeline` | Compiles documents, modules and symbols into one knowledge graph that agents query. | `make site-data` | — | Edges come from a closed set of kinds; a stale local corpus fails `make check-corpus`. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |
| `agent surface (AAD)` | Lets a service describe itself as a discoverable agent through a typed description. | `make agent-surface-schema` | — | A reference demo, not a registry or a discovery service. | [agent-surface.md](../guides/agent-surface.md) | always |
| `Stop hook` | Runs the doc review when an agent session stops, through `.claude/settings.json`. | automatic | — | Vendor wiring: one agent tool's hook format. It reviews; it does not apply edits. | [doc-style.md](../guides/doc-style.md) | always |
| `.claude/skills/doc-review/` | An agent skill that runs the doc review and, when asked, applies gated edits. | ask the agent to review the docs | — | Dry-run by default. | [doc-style.md](../guides/doc-style.md) | always |
| `.claude/skills/practice-refactor/` | An agent skill that refactors toward one named practice, gating every edit on `make verify`. | ask the agent to apply a practice | [a practice's `id`](settings.md#configpracticesjson) | One practice per run. | [coding-practices.md](../guides/coding-practices.md) | always |
| `child_env` | Starts every Python child process from an allowlisted environment, never the parent's whole one. | automatic in each spawn | [`child_env.names`](settings.md#configprojectjson) | Defence-in-depth, not a sandbox: a same-user child can still read its parent's environment. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `gate runner` | Runs only a gate-labelled make target and fails a run that changed what git sees. | `python3 scripts/run_make_target.py <target>` | [`make_targets.gate_effects`](settings.md#configprojectjson) | Sees only what git lists: a write to an ignored path passes. | [limits-and-troubleshooting.md](../guides/limits-and-troubleshooting.md) | always |
| `domain profiles` | Turns on domain practices, such as the cuda naked-tensor check, per project. | set the flag | [`practices.profiles`](settings.md#configprojectjson), [`profiles`](settings.md#copier-questions) | Off by default, so the template stays domain-neutral. | [coding-practices.md](../guides/coding-practices.md) | always |
| `scheduled jobs` | Runs a `scripts/jobs/` doer on a cadence through a thin cron or systemd adapter in `ops/scheduled/`. | install the example adapter | — | Examples only: nothing is scheduled until you install one. | [deterministic-checks.md](../guides/deterministic-checks.md) | always |

## Disciplines

These are how an agent and a person work here. Review holds most of them;
the row says which mechanism, if any, enforces each.

| Feature | What it does and why | How to run | Settings | Limits / not for | Deep doc | Ships |
|---------|----------------------|------------|----------|------------------|----------|-------|
| `test-first loop` | A new behaviour starts as a failing mirror test, then the smallest change that passes it. | follow the loop | — | A discipline, not a check: `make verify` gates the result, not the order. | [dev-loops.md](../guides/dev-loops.md) | always |
| `vertical slices` | A task is cut into end-to-end slices, each verified and committed alone. | name it in a plan doc | [`work_naming.slice_trailer`](settings.md#configprojectjson) | check_Z holds the names; the slicing itself is review's. | [dev-loops.md](../guides/dev-loops.md) | always |
| `generic solutions` | A change solves the class of inputs, never the example a test names. | `make advise` | — | `make advise` flags answer keys; it never fails the build. | [generic-solution.md](../guides/generic-solution.md) | always |
| `idempotent writers` | A writer declares what a second run does and reaches a fixed point. | `make check` | — | check_V holds the declaration; the proof is a test or a `--check` target. | [idempotency.md](../guides/idempotency.md) | always |
| `doc style` | One checkable claim per sentence, naming the mechanism that enforces it. | `make check-docs` | — | The mechanical floor is gated; the rest is review. | [doc-style.md](../guides/doc-style.md) | always |
| `python style` | Readability and loud failure first, with a gated module header. | `make lint` | — | Ruff, mypy and check_O gate the floor; the rest is review. | [python-style.md](../guides/python-style.md) | always |

## Showcase pillars

The showcase home page shows one card per pillar. Each pillar names the rows
above that deliver it; `tests/unit/backend/test_showcase.py` holds this table
equal to the showcase's curated features, slug and title, where the showcase
ships.

| Pillar slug | Title | Rows |
|-------------|-------|------|
| `deterministic-checks` | Deterministic checks | `make check-all`, `scripts/check_structure.py` |
| `labelled-tree` | Self-describing tree | `check_A`, `check_B` |
| `package-boundary` | Enforced boundaries | `check_C`, `check_D` |
| `vendor-neutral` | Vendor-neutral by design | `model:openai-compatible`, `runtime:inprocess`, `child_env` |
| `one-brain-corpus` | One-brain corpus | `corpus pipeline`, `scripts/jobs/check_corpus.py`, `agents/wiki_navigator/` |
| `polyglot` | Polyglot, layered | `REST API`, `gRPC transport`, `react-vite frontend`, `astro frontend` |
| `edge-adapters` | Tools & providers at the edge | `mcp/qa_server.py`, `mcp/action_server.py`, `model:claude-code-headless`, `scheduled jobs` |
| `coding-practices` | Coding practices, enforced or advised | `check_J`, `check_K`, `scripts/check_practices.py` |
| `agent-surface` | Agent surface | `agent surface (AAD)`, `make check-aad` |
| `agent-runtimes` | Durable agent control flow | `runtime:inprocess`, `runtime:langgraph` |
| `dev-loops` | Disciplined by default | `test-first loop`, `vertical slices`, `make verify` |
| `generic-solution` | Generic by default | `generic solutions`, `make advise`, `scripts/check_generic.py` |

## Conventions

- **Key.** A row's key is the first code span in its Feature cell. The test
  derives every key of these shapes from the tree: `check_<letter>`,
  `make <target>`, `model:<name>`, `runtime:<name>`, a `.py` path, an
  `agents/<name>/` or `.claude/skills/<name>/` directory and a
  `.github/workflows/` file. Any other key is a feature the tree cannot list
  for itself, such as a discipline or a transport.
- **Derived rows.** In the template, the rows of the derived shapes equal the
  tree exactly. In a generated project, every derived feature still needs a
  row, so a project's own new make target, agent or workflow reds the test
  until it has one, and a row for a feature the project's answers pruned must
  say so in Ships.
- **Effect label.** A make target's Feature cell carries the label its `## `
  help opens with, character for character.
- **Settings.** A Settings cell links each setting to its section of the
  [settings reference](settings.md); `—` means the feature reads none.
- **Ships.** `always` means every generated project receives the feature.
  `when <question>[=<value>]` names the copier answer that keeps it.
  `keel maintainers only` means only the template checkout has it. A feature
  that does not ship always is cited by a code span, never a link, so the
  link cannot dangle in a project without it.
- **Limits.** Every row says where the feature stops or what it is not for; an
  empty cell fails the test.
