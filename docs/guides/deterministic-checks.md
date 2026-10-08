---
title: Deterministic checks (the template linter)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [checks, ci, linter, determinism, pre-commit, hooks, guide]
summary: Catalogue of every deterministic check that keeps a project-template repo honest — purpose, when to run, and how to wire as a hook.
id: docs-guides-deterministic-checks
created: 2026-06-19
updated: 2026-10-08
visibility: internal
canonical: true
---

# Deterministic checks (the template linter)

This template is meant to stay **structurally honest** as it grows and as
agents edit it. A normal linter checks *code style*; the scripts catalogued
here check the **conventions of the template itself** — labeling, package
boundaries, the doc/code corpus, and the published contracts — so that any
project created from this template keeps a guaranteed level of structure.

Every check here is **deterministic**: same inputs → same verdict, no model,
no network, reproducible in CI and on a teammate's laptop. They are *doers*
(CONVENTIONS §7): the logic lives in `scripts/` and thin triggers (pre-commit,
CI) call them. Each script is self-describing (`--help`) and safe to re-run.

## TL;DR

```bash
make check        # fast structural gate — runs anywhere, incl. Python 3.6
make check-all    # the full deterministic suite (needs the project interpreter)
make verify       # check-all + lint + typecheck + test (the everything gate)
```

Wire them once and forget:

```bash
pip install pre-commit && pre-commit install   # run the fast checks on every commit
# CI already runs `make check-all` (.github/workflows/ci.yml)
```

## Two interpreters, on purpose

The host's pre-commit `python3` may be **old** (this repo's is 3.6), so the
checks split in two:

- **3.6-safe, stdlib-only** — run on *every commit* via pre-commit and need no
  dependencies: `check_structure.py`. It never uses
  f-strings/`from __future__ import annotations`, so it parses under 3.6.
- **Project-interpreter (≥3.10 / app deps)** — the corpus jobs (need ≥3.7) and
  the contract checks (need FastAPI/pydantic). They run in **CI** (Python 3.11)
  and locally under your venv. The contract checks **skip gracefully** (exit 0
  with a note) when their dependency is absent, so they are safe in pre-commit
  too; the corpus check is CI-only because it imports the ≥3.7 corpus builder.

`make check` only runs the 3.6-safe set; `make check-all`/`make verify` run
everything and therefore expect the project interpreter.

## The checks

| Check | Script | Gate? | Interpreter | What it guarantees |
|-------|--------|:-----:|-------------|--------------------|
| Structure & frontmatter | `scripts/check_structure.py` | error | 3.6-safe | Labels, taxonomy, package boundaries, tool/agent governance, project facts, agent-rules symlinks, owned-exception & frozen-config boundaries, naked-tensor domain warn, lint/type ruleset parity, template twin parity, Makefile help parity, cross-reference resolution, check-catalogue parity, rosters, practice mechanisms, policy reachability, writer rerun declarations, make-target effect labels, child-process environment, ADR number spaces, work naming (checks A–Z) |
| Interpreter floor | `scripts/check_python_version.py` | error | any | `$(PY)` satisfies `pyproject.toml`'s `requires-python`, said plainly before a newer-syntax check fails with a traceback — runs before every check that needs the project interpreter (`check-corpus`, `test`) |
| Corpus integrity | `scripts/jobs/check_corpus.py` | error | ≥3.7 | the fresh build is a valid, acyclic, reproducible graph whose edge kinds are from the closed set (`keyword`, `link`, `citation`, `mention`, `semantic`) **and** the local `wiki/corpus.json` (what agents query) is current when present — absent is a loud pass, stale is an error naming `make site-data` (ADR-K-0008) |
| OpenAPI drift | `api/rest_fastapi/export_openapi.py --check` | error | FastAPI | Committed `openapi.json` matches the live routes |
| AAD schema drift | `scripts/agent_surface/generate_aad_schema.py --check` | error | pydantic | Committed AAD JSON Schema matches the model |
| Code-doc drift | `scripts/cdmon_sync.py --check` | error* | any | cdmon code↔doc drift — the CONVENTIONS §9 worked example of a thin adapter over an external tool (*a stated skip, exit 0, until `cdmon` is on PATH **and** `config/cdmon/cdmon.yaml` exists; cdmon is not on PyPI). Reached from `check-all` via `make check-cdmon` |
| Accountability | `scripts/accountability_report.py` | report | ≥3.7 | Lists corpus nodes that resolve to no owner (informational; rides `make advise`) |
| Doc review | `scripts/jobs/review_docs.py` | report | any (git) | Freshness — every governed document's `updated:` is no earlier than its last commit, and a document modified in the working tree carries today's date (gated by `tests/integration/test_doc_freshness.py`, `--strict`) — and the advisory that stays advisory: backticked repository paths that resolve to nothing. No git is a stated skip. The fix it names is `make restamp-docs` (`scripts/jobs/restamp_docs.py`) |
| Generic-solution advisor | `scripts/check_generic.py` | report | 3.6-safe | Distinctive literals asserted as golden in tests **and** hardcoded in `src/` logic (the "answer-key" overfit smell, §18). Advisory only — never fails the build |
| Coding-practices advisor | `scripts/check_practices.py` | report | 3.6-safe | Coding-practice smells (a provider constructed inline instead of injected, a ≥3-branch `isinstance` chain, a `# hot-path` class without `__slots__`, a resource acquired outside a `with`). Reads `config/practices.json`; advisory only — never fails the build (see [coding-practices](coding-practices.md)) |

All gates exit **0 = clean, 1 = failure**. Warnings (e.g. a missing `owner`)
print but never fail the build.

---

### 1. Structure & frontmatter — `scripts/check_structure.py`

**Purpose.** The core enforcer of `CONVENTIONS.md`. Checks A–Z:

- **A. Frontmatter** — every `README.md` / `AGENT.md` / `CLAUDE.md`, `docs/**`,
  `test-docs/**` markdown, and `agents/**/*.tool.md` has the required keys with
  valid `kind` / `layer` / `status` / `visibility`; `id` is unique; a path-like
  `canonical` resolves; `deprecated` and `superseded` both require
  `superseded_by` (one rule, two lifecycle vocabularies).
- **B. Closed taxonomy** — every non-hidden top-level directory is a §2 row or
  declared in `config/project.json` `structure.extra_toplevel` (§15); a
  declaration names a directory that exists and is not already a row; every
  top-level directory and every directory directly under `agents/` (each
  `agents/<name>/` and `agents/tools/`) carries `README.md` + `CLAUDE.md`. An undeclared symlinked directory is a WARN, because no check
  reads through a link and the gate cannot ask git whether it is tracked.
- **C. Package boundary** — every `src/` dir with `.py` has an `__init__.py`
  defining `__all__`.
- **D. `__init__` is the API** — no absolute import of another package's
  `_private` module.
- **E. Authored coverage** — every `__all__`-exported symbol defined in-file has
  a docstring: the corpus's symbol summaries (error since ADR-K-0008).
- **F. Tool specs governed** (error) + **accountability** (warn) — valid
  `kind: tool` frontmatter with a resolvable `public_api`, a `tool_effect` from
  the closed set, a `tool_command` that invokes the script; and the body
  contract of CONVENTIONS §10: the seven sections in order, `## Side effects`
  opening with the word for the declared effect (`READ-ONLY` / `WRITES` /
  `MODEL-CALL` — the body and the frontmatter are read by different agents and
  must not disagree), and at least one `- NOT ...` bullet under `## When to
  use` — the negative-scope line that names the sibling this tool is not. Six
  of seven specs carried it by discipline; the rule makes every later one carry
  it too. Lands as an error: the one spec without it was fixed in the landing
  commit.
- **G. Tool↔agent binding** — `tools.md` ↔ each spec's `## Used by` agree.
- **H. Project facts** — `config/project.json` agrees with the tree (§15).
- **I. Agent-rules symlink** — every `CLAUDE.md` is a symlink to its sibling
  `AGENT.md`, and every `AGENT.md` has that sibling (§5).
- **J. Owned-exception boundary** — in `src`/`models`/`runtimes`/`agents`, no
  `raise` of an exception type imported from a foreign (non-local, non-stdlib)
  module; wrap it in an owned error or waive with `# practice-ok: <reason>` (§18).
- **K. Frozen-config gate** — a class carrying the declared marker
  (`config/practices.json` `tokens.config_marker`, `# practice: frozen-config`)
  must be provably immutable (frozen dataclass / `NamedTuple` / attrs-frozen).
  Keyed on the author-written marker, never a `*Config` name suffix (§18); it
  resolves aliased imports and honours the 3.6-vs-3.8 class-line model; waivable.
- **L. Naked-tensor domain** (warn) — only when the `cuda` profile is enabled
  (`config/project.json` `practices.profiles`), a parameter annotated with a bare
  tensor base type (`tokens.tensor_base_types`) and no shape comment **warns**.
  An advisory heuristic (a token may name a local class) — never an error.
- **M. Ruleset parity** — `pyproject.toml` must not silently loosen the lint/type
  policy declared in `config/practices.json` `rulesets`: every ruff
  `extend_select` family is selected, every mypy flag is enforced, no `deferred`
  (policy-off) family is selected. Reads `pyproject.toml` as text (no `tomllib`
  on 3.6); multi-line arrays, dotted-key/header forms, `# practice-ok` all handled.
  Also enforces the two declarations that used to have no consumer: every ruff
  `per-file-ignores` pattern must be declared in `rulesets.ruff.per_file_ignores`
  (one `"**/*.py"` line could otherwise silence a family corpus-wide), and every
  `[[tool.mypy.overrides]]` relaxation of a flag the ruleset declares — `strict`,
  the twelve components `--strict` expands to, `warn_unreachable` — or of
  `ignore_errors` must be declared in `rulesets.mypy.overrides` for that module.
  The bound is deliberate and worth knowing: keys outside that set
  (`ignore_missing_imports`, `disable_error_code`, `follow_imports`) scope
  imports or diagnostics rather than strictness, and check_M does not read them.
- **N. Template twin parity** — keel is a copier template, and every `*.jinja`
  twin must be declared in `config/project.json` `template.twins` with its kind:
  `parity` (reproduces keel's own file except where templated), `divergence`
  (deliberately does not — `.gitignore.jinja` drops the `.copier-answers.yml`
  ignore so a generated project keeps its upgrade channel), or `generated`
  (copier writes it; keel commits none of its own). Render-free by necessity —
  this script is stdlib-only and 3.6-safe, so it cannot import jinja2 — which
  bounds the claim: it proves no twin is undeclared, no parity twin carries a
  non-templated line the plain file has lost (the drift that shipped a weaker
  gate to every descendant), and no divergence twin has quietly stopped
  diverging. The byte-exact rendered comparison stays in
  `tests/integration/test_copier_generation.py`, where jinja2 exists. Silent in a
  generated project, which has no twins.

- **O. Module header contract** — every code-root module docstring carries
  explicit, non-empty `title:` and `summary:` lines, in exactly the grammar
  `build_corpus` reads (pinned by a parity test, not a shared import — this
  script stays 3.6-safe). Without them the corpus falls back to
  filename/first-prose-line and labels the result `authored`, and an
  undocumented module is silently dropped from the index (ADR-K-0008).
- **P. Makefile help parity** — every target line carrying a `## ` annotation
  is one the `help` recipe's own grep pattern lists. The pattern is read out of
  the recipe (`grep -hE '<pattern>' $(MAKEFILE_LIST)`), not restated in the
  check, so the two cannot agree on a wrong answer; `include`d makefiles are
  read too, as `$(MAKEFILE_LIST)` would. The live instance: `e2e` was annotated
  from the day it existed and never listed, because `[a-zA-Z_-]` has no digits.
  Read only from the file named `Makefile` and what it includes (recursively;
  `-include`/`sinclude` of an absent file is make's own "if present"); a
  `$(VAR)`-named target, a dotted special target and a line naming two targets
  are outside the annotation convention and outside the check. It models a
  `grep -E`/`-P`/`egrep` first stage reading `$(MAKEFILE_LIST)`, `-i`, a
  pattern held in a plain make variable, and later `grep -v` stages (an author
  hiding a target on purpose). Everything else — a grep without `-E` (basic
  regex, which Python cannot run), `-F`, a second selecting grep, a variable or
  wildcard include, a pattern variable it cannot expand — is a WARN that says
  *unverified*, never a pass. Silent without a `help` target. Lands as an error, not a
  release-long warning (the ADR-K-0008 grace rule), because the tree complied the
  moment the recipe was widened — there was nothing to give anyone time for.
- **Q. Cross-references resolve** — every relative Markdown link in prose
  (`[text](path)`, `![alt](path)`, a directory, a `#anchor`) names something
  that exists, and every `§N` citation names a numbered `## N.` heading. The
  citation grammar is closed on purpose: a bare `§N` **always** cites
  `CONVENTIONS.md`; a section of any other document is cited by naming it
  immediately before the sign — `docs/guides/python-style.md §3`, with the
  path in backticks or not, a comma or a line break between them or not
  (root-relative, else the citing file's neighbour; only `.md` names count).
  A bare `§N` never means "this document", because that reading turns
  ambiguous the moment a guide numbers its own sections. A numbered heading
  is `N.` at any level (`##` in `CONVENTIONS.md`, `###` in this file).
  Citations are read from prose *and* from code and config (`.py`, `.toml`,
  `.yml`, `.yaml`, `.jinja`, `.example`, `Makefile`), and from inside fenced
  or inline code too, since a quoted help string's `(§18)` cites the same
  section a sentence does. Links are the other way round: inside fenced code,
  inline code or an HTML comment a link is a syntax illustration and is not
  read; `.jinja` twins are not read for links (their rendered links are the
  generation tests' business). Link targets may be percent-encoded or
  `<angle-bracketed>`; anchors follow GitHub's slug rule on the heading *as
  rendered* (code spans kept, link text kept, emphasis markers dropped;
  lowercase; drop all but word characters, spaces and hyphens; spaces to
  hyphens; repeats numbered `-1`, `-2`), plus setext headings and explicit
  `<a id>`/`<a name>` anchors. Absent is not silent here: a citation to a
  missing `CONVENTIONS.md` is an error, because the file ships verbatim into
  every generated project. What this buys: renumbering `CONVENTIONS.md`, or
  moving a doc, now fails with the full list of citations to update instead of
  leaving the knowledge graph pointing at the wrong sections at exit 0. Lands
  as an error, not the ADR-K-0008 release-long WARN: the tree had no dead
  reference on arrival, so there was nothing to give anyone time for.
- **R. Check catalogue parity** — this file's checks table and the triggers
  that run the checks agree on one membership: every catalogued script exists;
  a row at the `error`/`error*` tier is reachable from `make check-all` (a gate
  nobody runs is a claim); a `report` row is run by *some* make target (a
  report nobody runs is the `make advise` precedent — documented, invoked by
  nothing); every script `check-all` reaches, transitively through
  prerequisites, has a row; and the hooks table below names exactly the hook
  ids `.pre-commit-config.yaml` declares — and neither exists without the
  other. The tier column is a closed vocabulary (`error`, `error*`, `report`);
  a short row is an error, not a skip. The Makefile is read as make reads it
  (continuations unfolded, conditionals transparent, `$(MAKE) target` followed,
  shell comments ignored); catalogued checks are `.py` paths, so a check in
  another language is reached through a `.py` adapter (CONVENTIONS §9). The
  live instance this closed: the cdmon row claimed the error tier for as long
  as it existed while `check-all` never ran it. Silent without this file; a
  checks table or Makefile it cannot read is a WARN that says *unverified*.
  Lands as an error, not the ADR-K-0008 release-long WARN: the four rows it found
  were made true in the landing commit.
- **S. Roster parity** — a README that declares `## What ships here` is held
  to its directory: a pipe table follows the heading, its first column is
  `Member` (each cell a backticked path relative to the README's directory,
  directories with a trailing `/`), every member appears exactly once and
  nothing that is not a member appears (labels and packaging — `README.md`,
  `AGENT.md`, `CLAUDE.md`, `__init__.py`, `__pycache__` — hidden entries,
  ignored dirs and `.jinja` twins are not members), and a `Not for` column exists with every
  cell filled. Opt-in by the heading, so no README is retro-failed; keel
  declares rosters for `agents/`, `agents/tools/`, `docs/guides/`, `mcp/`,
  `scripts/` and `scripts/jobs/`. The `Not for` cell is the point: it states
  what a reader must not reach for that member to do and names the sibling
  that does — the discriminator between two things that look alike
  (`rebuild_index.py` and `build_corpus.py` both say "index"; the roster says
  which is the corpus and which is a README list). A member that ships only
  under a copier answer has its row inside `{% if %}` in the README's `.jinja`
  twin, so a generated project's roster matches its pruned tree — the
  generation tests run this check inside every generated project. Lands as an
  error: every roster was written in the landing commit.
- **T. Practice mechanisms resolve** — every `config/practices.json` entry
  carries `enforced_by`, a list in a closed grammar (`check:<LETTER>`,
  `script:<path>`, `test:<path>`, `make:<target>`, `doc:<path>[ §N]`,
  `ruff:<CODE>`, `mypy:<flag>`), and every reference resolves: the check letter
  is defined here, the script/test/doc exists (and has that numbered section),
  the make target is a rule. `ruff:`/`mypy:` codes are accepted as written —
  the tools themselves reject an unknown one. `mechanism` stays as prose for a
  reader; this is the same claim a machine can hold. Silent without a
  registry. Lands as an error: every entry was annotated in the landing commit.
- **U. Policy documents are reachable** — a practice whose mechanism IS a
  document (`doc:<path>` in `enforced_by`) must name that document within one
  hop of the root `AGENT.md`: named there, or named in a document named there.
  `check_T` proves the path exists; existing is not the same as being found, and
  a rule nobody reads is unenforceable in principle. One hop rather than direct,
  because `AGENT.md` is a rules file and not an index: an agent told to open
  `python-style.md` is handed whatever that points at. Two hops is a treasure
  hunt, not discoverability. References count whether written as a Markdown link
  or as a plain path, and inline code counts because a backticked path is how
  this repository names a document; fenced code does not, being an illustration.
  A `doc:` path absent from the tree is `check_T`'s finding and is not reported
  twice here. Silent without a practices registry or without a root `AGENT.md`.
  The live instance this closed: `docs/guides/doc-style.md` shipped as the
  canonical statement of how documentation is written, was cited by four
  practices, and was named by nothing an agent reads by default.
- **V. Writers declare their second run** — a module that writes to the
  filesystem says so in its header (`effect: writes`, the CONVENTIONS §10
  `tool_effect` vocabulary, reused rather than re-invented) and says what
  re-running it does (`rerun:` from `fixed-point` / `append-only` / `unsafe`); a
  `fixed-point` claim names a `rerun_proof:` in the same closed grammar
  `check_T` holds `enforced_by` to. Every doer here already reached a fixed
  point when it was measured — generation, the corpus, both schemas, the static
  snapshot — and nothing held it there: the property was a habit, and a habit is
  exactly what a generated project does not inherit. The detector resolves the
  base of every call, so `text.replace(...)` is not `os.replace(...)`; measured
  over this repo it found 10 writers and no false positives, which is what makes
  this a gate rather than an advisory. It under-reports by design — a write
  behind `subprocess` is invisible to an AST — so a declared write it cannot see
  is a WARN reading *unverified*, never a silent pass and never an error, since
  the honest declaration must not be the one that fails the build. `check_V`
  proves the claim was made; `tests/integration/test_idempotence.py` re-runs the
  doers that claim it. See [idempotency](idempotency.md).
- **W. Make targets declare their effect** — every `## `-annotated target opens
  its help with one bracketed label from `local`, `tree`, `read`, `cost`,
  `write` (comma-joined in that order, no duplicates, `local` alone, one
  bracket). A composite's label must cover every word its prerequisites and
  `$(MAKE)` calls reach, so `verify` cannot claim `[local]` over a `[tree]`
  prerequisite. A `[write]` target, or one whose name ends in a
  `config/project.json` `make_targets.write_shapes` suffix, opens its recipe
  with `$(WRITE_GUARD)` and no `-` prefix (make would ignore the guard's
  failure), and the guard's definition, read as make stores it (a `#` comment
  cut off), must test exactly the `make_targets.unattended_vars` names, carry no
  `-` prefix of its own, and `exit 1`. A target annotated on two rules must carry
  one label on both, since make merges them. The `make_targets` block
  itself is validated: `gate_effects` must hold `local` and must not hold `tree`
  or `write`, and `gate_vars` may not name make's own control variables,
  `WRITE_GUARD` or an unattended variable. With `area_dir` set, each `<area>.mk` is included, opens with one
  `##@ <area>` header, and prefixes its public targets `<area>-`. A recursion it
  cannot resolve (`$(MAKE) -C`, a variable target) is a WARN reading
  *unverified*. Measured over keel at landing: 37 annotated targets, 32
  `[local]`, 5 carrying `tree`. The label is a static claim; the runtime half is
  `tests/integration/test_make_target_effects.py`, which runs every `[local]`
  target through `scripts/run_make_target.py` and fails one that changed the
  tree. See [`docs/adr/keel/K-0011-make-target-effect-labels.md`](../adr/keel/K-0011-make-target-effect-labels.md).
- **X. Child processes get an allowlisted environment** — every `subprocess`
  (`run`, `Popen`, `call`, `check_call`, `check_output`) or `asyncio`
  (`create_subprocess_exec`, `create_subprocess_shell`) spawn passes `env=`
  built by `build_child_env` from `scripts/child_env.py`, either directly or
  through a name bound only to that call and afterwards only read (`env=`,
  `name[key]`, `.get`, `.copy`, `.items`, `.keys`, `.values`, a comparison).
  Any other use of that name, in any scope, fails it: a store into it, a method
  call, an alias, a nested `def` or lambda, or handing it to a function. The
  scan covers every `.py` at the repo root and under every top-level directory
  except `tests/`, hidden directories, `IGNORE_DIRS` and a symlinked directory,
  so an undeclared directory is scanned too. A spawn with no `env=`, one whose
  `env=` is anything else, and one with `**kwargs` (which cannot be proven) are
  errors; so are `os.system`, `os.popen`, `os.exec*`, `os.spawn*`,
  `os.posix_spawn*`, `os.forkpty`, `pty.spawn` and `subprocess.getoutput`,
  which cannot take an allowlisted environment the gate can verify. A spawn API
  referenced without being called (assigned, passed to `functools.partial`,
  used as a default or put in a list) is an error, because the `env=` it is
  later called with cannot be read; a type annotation and an
  `isinstance`/`issubclass` argument are not. A call is resolved with Python's
  own scope rules (function, lambda, class and comprehension scopes, `global`
  and `nonlocal`), so a name rebound in another scope does not hide a spawn,
  and a name bound both by an import and another way in one scope is an error
  rather than a guess. A helper call whose arguments carry the parent's
  environment is an error: `os.environ` or `os.getenv` directly, or a name
  that a value from them reached within the module, through assignment,
  aliasing, `dict.update`, a subscript store, a loop or a comprehension. There
  is no waiver. The `config/project.json` `child_env` block and
  `models.credential_env` are validated through `child_env.child_env_policy`.
  That includes `child_env.repo_context_names`, which is required and
  non-empty: it lists the variables git binds to the repository it started a
  process in (a hook's `GIT_DIR`, `GIT_INDEX_FILE`, `GIT_PREFIX`, ...).
  `build_child_env` drops them, so a child that runs git in another directory
  acts on that directory's repository and not on the one being committed. The
  check refuses any allowlist source that would copy one anyway: `names`, a
  `prefixes` entry (`GIT_`), `make_targets.unattended_vars` or `gate_vars`,
  and any `models.credential_env` list. The message names the source and the
  fix, for example `child_env.names lists GIT_DIR, which
  child_env.repo_context_names marks as bound to the repository the parent was
  started in -- ...; remove them from child_env.names (a child that must act
  on the parent's repository passes build_child_env(repo_context=True))`. The
  opt-in is a keyword, not a config name, because it is one call's decision,
  visible where that child starts. A name in config would hand the parent's
  repository to every child the project starts, and nothing at the call site
  would show it. A project generated before keel slice project_keel:CMP-2.S1 of
  `docs/design/downstream-feedback.md` fails with `child_env.repo_context_names
  is missing` until `copier update` brings the key.
  `child_env.credentialed_values` is optional and maps a copied variable to
  the reason its value may carry user information. The check refuses an
  entry that is not a variable name, has an empty reason, or names a
  variable no allowlist source copies, with `drop the stale entry` in the
  message. The value itself is judged at run time, not here, because the gate
  never sees the environment a child will get: `build_child_env` raises
  `ChildEnvError` with `build_child_env: HTTPS_PROXY holds user information`
  and the fix, and never the value. This opt-in is config, not a
  keyword, because an authenticating proxy is a property of the site that
  every child crosses, not of one call.
  It under-reports, never over-reports, in two places: a spawn through a
  receiver it cannot resolve (`self.runner(...)`, `loop.subprocess_exec`,
  `sp = subprocess; sp.run`), and a parent-environment value that reaches the
  helper across a function parameter. Measured over keel at landing: 11 spawn
  calls in 10 modules, all converted. It is defence-in-depth, not a sandbox: a
  same-user child can still read the parent's environment from
  `/proc/$PPID/environ`. See
  [`docs/adr/keel/K-0012-child-process-environment-allowlist.md`](../adr/keel/K-0012-child-process-environment-allowlist.md).
- **Y. ADR number spaces** — the ADRs a template ships and the ADRs a project
  writes are numbered in two spaces (CONVENTIONS §19), named by
  `config/project.json` `adr`: `project_dir` (`docs/adr`), `template_dir`
  (`docs/adr/keel`), `template_prefix` (`K-`) and `number_digits` (`4`).
  The check reads every `.md` file directly in each space except
  `README.md`, `AGENT.md` and `CLAUDE.md`. It errors on a project-space ADR
  named with the template prefix (the message names the template space), on
  one that is not `NNNN-<slug>.md`, on a template-space ADR that is not
  `K-NNNN-<slug>.md` (the message names the project space as where it
  belongs), on a number taken twice within one space (both paths named; the
  same number once in each space is clean), on frontmatter `kind` other than
  `adr`, and on a `title` that does not begin `ADR-NNNN:` or `ADR-K-NNNN:` for
  its own file. A missing `adr` block is an error once any Markdown document in
  the tree declares `kind: adr`; a malformed one (a missing or unknown key, the
  two directories equal, a prefix that starts with a digit, a non-integer digit
  count) is always an error naming the key. Both spaces empty is a WARN. A
  template ADR the project edited and `copier update` retired is kept by
  `scripts/jobs/keep_edited_retired.py`; the kept copy shares its `id:` with
  the template's file, which check_A reports as a duplicate id. Measured over
  keel at landing: 13 template ADRs, 0 project ADRs, 0 findings. See
  [`docs/adr/keel/K-0013-template-and-project-adr-number-spaces.md`](../adr/keel/K-0013-template-and-project-adr-number-spaces.md).
- **Z. Work naming** — a campaign is `CMP-<n>` and a slice `CMP-<n>.S<m>`
  (CONVENTIONS §20), with the grammar read from `config/project.json`
  `work_naming`: `plan_kinds`, `slice_column`, `campaign_id`, `slice_id`,
  `backlog_id`, `slice_trailer`, `backlog_trailer` and `adoption_boundary`. A
  plan doc is a Markdown document whose frontmatter `kind` is a plan kind and
  that holds a table whose first header cell is the slice column. The check
  errors on a row whose first cell is not a slice id (the message shows the
  expected form), on a slice table under no campaign heading or under a
  heading that names two campaigns, on a row of another campaign, on a slice
  number taken twice (both lines named), out of document order, or skipped
  (the missing slice named), on a campaign declared by two headings, on a gap
  between campaigns (the first campaign after the gap names the missing one),
  and on a prose mention in any Markdown file, bare or with the project's own
  `name:` prefix, that names no declared campaign or slice, and on an
  id-shaped token the grammar does not accept (`CMP-1.S02` is malformed, not a
  mention of `CMP-1`). Code spans,
  fences, a foreign-prefixed id and a table with another first column (a
  `Phase` or `Pass` table) are not read. A missing block is an error once the
  tree holds a plan doc, the message naming the doc; a malformed block (a
  missing or unknown key, a template without `<n>` or `<m>`, a `slice_id`
  that does not extend `campaign_id`, a `backlog_id` that does not compile) is
  always an error naming the key. A plan doc that declares no slice is a WARN.
  Commit trailers are judged by `tests/integration/test_work_trailers.py`,
  because check_structure reads no git (ADR-K-0009). Measured over keel at
  landing: 1 plan doc, 4 campaigns, 20 slices, 0 findings.

**When to run.** Every commit (pre-commit) and in CI; any time you add a
directory, package, doc, tool, or agent.

**Run.** `make check` · `python3 scripts/check_structure.py`

**Changing it.** If you change the scheme or a check, update **both** this
script and `CONVENTIONS.md`.

### 2. Corpus integrity & reproducibility — `scripts/jobs/check_corpus.py`

**Purpose.** `wiki/corpus.json` is the generated "one-brain" index (CONVENTIONS
§11). This check validates the graph — unique `node_id`s, resolvable
`parent`/`children`/`links`, valid `kind`/`owner_source`/`visibility` and a link `kind` from the closed set, owner
coherence, sorted tags, **acyclic** parent chains — and proves the build is
**deterministic** (builds twice, asserts byte-identical output). It also gates
the **local** corpus — the file the agents actually query: absent is a loud
pass (a fresh clone, CI, and a day-one generated project have none), while
present-but-stale is an **error** naming `make site-data`. Staleness is judged
on the *deterministic projection* — `index_enforcer`'s `"generated"` summary
fills and semantic links are enrichment, not rot (ADR-K-0008).

**When to run.** In CI, and after any change to the corpus builders or to
content that feeds the corpus.

**Run.**
- `python scripts/jobs/check_corpus.py` — fresh build, validate + determinism.
- `python scripts/jobs/check_corpus.py --corpus wiki/corpus.json` — validate the
  on-disk file (and warn if it is stale vs a fresh build; the file is gitignored).

### 3. OpenAPI drift — `api/rest_fastapi/export_openapi.py --check`

**Purpose.** The committed `api/rest_fastapi/openapi.json` is the published REST
contract; keep it generated from the live FastAPI app so it cannot drift from
the routes (the `api/` rules). `--check` exits 1 if the committed file is stale.

**When to run.** Whenever routes/schemas change; in CI. Regenerate with the same
script (no `--check`).

**Run.** `python api/rest_fastapi/export_openapi.py [--check]` · `make check-openapi`
Skips gracefully (exit 0) when FastAPI is absent.

### 4. AAD schema drift — `scripts/agent_surface/generate_aad_schema.py --check`

**Purpose.** Keep the committed AAD wire schema
(`config/agent_surface/aad-v1.0.schema.json`) generated from the `AadDescriptor`
model (CONVENTIONS §14), so the published contract can't drift from the code.

**Run.** `python scripts/agent_surface/generate_aad_schema.py [--check]` ·
`make check-aad` — skips gracefully when pydantic is absent.

### 5. Code-doc drift — `scripts/cdmon_sync.py --check`

**Purpose.** Thin adapter over the optional cdmon code↔doc drift monitor
(CONVENTIONS §9). A no-op until cdmon is installed, then it flags docs that
have drifted from the code they describe.

**Run.** `python3 scripts/cdmon_sync.py --check`

### 6. Accountability report — `scripts/accountability_report.py`

**Purpose.** A *report*, not a gate: lists corpus nodes that resolve to no owner
(CONVENTIONS §12), so ownership gaps are visible. Does not fail the build.

**Run.** `python scripts/accountability_report.py`

### 7. Doc review — `scripts/jobs/review_docs.py`

**Purpose.** The deterministic documentation review: what a rule can decide
about the docs but `check_structure.py` cannot reach without git. Today that is
**freshness** — a governed document (git-tracked Markdown whose frontmatter has
`updated:`) is stamped no earlier than the date of its last commit, and a
document modified in the working tree is stamped today or later. `updated:`
means *touched*: it is a cache of the git date, kept in the file so the corpus
can rank by recency without git (CONVENTIONS §1). The remedy is always one
line, the report says which, and every stale finding names `make restamp-docs`.
That target runs `scripts/jobs/restamp_docs.py`, the writer half of this rule.
It reads the stamp through the same grammar (`review_docs.updated_span`) and
never moves a stamp backwards. Copier runs it at generation and as the last
update migration (`docs/adr/keel/K-0010-generation-needs-trust-to-stamp-docs.md`).

**Tier.** A *report* under `make advise` (exit 0). The same rule is a **gate**
in `tests/integration/test_doc_freshness.py`, beside the release-identity test
and for the same reason (ADR-K-0009): a check that shells to git does not belong
in the 3.6 pre-commit hook. The work-naming rule has the same git half:
`tests/integration/test_work_trailers.py` judges each commit's `Slice:` and
`Backlog:` trailers after `work_naming.adoption_boundary`, and check_Z judges
the plan docs. Landed with every stale stamp normalised in the same
commit — 91 of 117 governed documents — so the tree complied on arrival.

**Run.** `python scripts/jobs/review_docs.py [--json] [--strict] [--today YYYY-MM-DD]`
· `make advise`

### 8. Generic-solution advisor — `scripts/check_generic.py`

**Purpose.** A *report*, not a gate: the advisory backstop for the "solve the
general case" discipline (CONVENTIONS §18). It flags an **answer key in source** —
a distinctive literal that a test asserts as its expected value (an `==` operand
or `assertEqual` argument) **and** that is also hardcoded in non-data `src/`
logic. It excludes data/registry modules (`*_data.py`, fixtures, `conftest.py`),
literals named as `ALL_CAPS` constants, and trivial literals, honours a
`# generic-ok: <reason>` pragma, and **always exits 0** — it draws attention, it
never gates.

**When to run.** Anytime, especially after making a failing eval/golden/case
pass; advisory and outside `make verify`.

**Run.** `make advise` · `python3 scripts/check_generic.py [--json] [--strict]`

---

## How the hooks are wired

### Pre-commit (event trigger)

`.pre-commit-config.yaml` runs the fast, dependency-light checks on every
commit (each hook is a thin trigger that calls a `scripts/` doer):

| Hook id | Calls |
|---------|-------|
| `structure` | `python3 scripts/check_structure.py` |
| `openapi` | `python3 api/rest_fastapi/export_openapi.py --check` (skips if FastAPI absent) |
| `aad-schema` | `python3 scripts/agent_surface/generate_aad_schema.py --check` (skips if pydantic absent) |
| `cdmon` | `python3 scripts/cdmon_sync.py --check` (a stated skip until cdmon and its config exist) |
| `doc-review` | `python3 scripts/jobs/review_docs.py --strict` (stale stamps fail; mentions advisory; no git is a stated skip) |
| `eslint` / `ruff` / `ruff-format` | frontend lint + Python lint + Python formatting |

Enable once: `pip install pre-commit && pre-commit install`.

### CI (event trigger)

`.github/workflows/ci.yml` runs under Python 3.11 and Node 22:

```yaml
- run: make check-all   # structure, python floor, corpus, openapi, aad, cdmon
- run: make lint
- run: make typecheck
- run: make test
```

### Scheduled (time trigger)

The nightly job is the deterministic documentation review: the cadence lives
in `ops/scheduled/` (cron/systemd) and `.github/workflows/scheduled.yml` (CI),
each calling `scripts/jobs/review_docs.py --json` and keeping the report — the
*doer* in `scripts/jobs/`, the *schedule* in `ops/` (CONVENTIONS §7). A
schedule runs the doer, never the doc-review agent: a nightly judgment has no
one to read it, while a nightly list of stale stamps and dangling mentions
does.

## Adding a new deterministic check

1. Write the doer in `scripts/` (or `scripts/jobs/` for unattended jobs).
   Stdlib-only + 3.6-safe if it must run in pre-commit; otherwise it may use
   the project interpreter and **skip gracefully** when a dependency is absent.
2. Give it `--help` and a `--check` mode if it guards a committed artifact.
3. Add a `make` target and, if it should gate commits, a `.pre-commit-config.yaml`
   hook and/or a CI step. New projects generated with `copier` get the file
   automatically (copier ships the real `scripts/` tree — see
   [ADR-K-0004](../adr/keel/K-0004-project-templating-copier.md)).
4. Document it in this file.

## Auditing another project against this template

`make audit-project DEST=<path>` reports what a keel-generated project at
DEST would fail under this checkout's current gates once `copier update` has
landed, before anyone runs the update. It is a preview, not a gate, so it is
not a row in the catalogue above.

**Where it runs.** Only from the template checkout. The doer,
`scripts/audit_project.py`, is excluded from generated projects
(copier.yml `_exclude`), because it imports this checkout's `check_structure`
API and a copy in a project would pair an older doer with newer gates. A
generated project's `make audit-project` is a stub that prints the
`make -C <template> audit-project DEST=...` line to run instead, with DEST
made absolute (the project itself when DEST is not given), so the printed line
works from the template checkout.

**What it runs.** The audit judges one tree, the one the update leaves. It
builds that tree in a scratch directory (`tempfile.TemporaryDirectory`,
prefix `keel-audit-`), which it removes on every exit path:
- a snapshot of this checkout: a `git clone`, with the checkout's modified,
  deleted and untracked files committed on top;
- a copy of DEST: the files git lists there (tracked and untracked, not
  ignored), or every file check_structure walks when DEST is not a git work
  tree, committed in the copy's own repository;
- `copier update --trust --defaults --skip-answered --vcs-ref HEAD
  --conflict inline` of the copy against the snapshot, run as a child
  process.
Every check_structure letter, A–Z, runs in-process through `run_checks` on the
copy twice: before the update and after it. The freshness judge
(`scripts/jobs/review_docs.py`) and the restamp writer's `pending` list
(`scripts/jobs/restamp_docs.py`) run on DEST itself. Each freshness finding
carries `resolved_by`, because the update's last `_migrations` step runs
`restamp_docs` and clears it; the `pending` list names the stamps that
migration will rewrite.

**The predicted tree.** The tree after the update is copier's own merge, so
the audit merges nothing itself. A path copier leaves conflicted (`git
ls-files -u` in the copy) is reported as a warning in the `[conflict]` group,
and its letter findings are marked `unjudged: conflict`. The tree after the
update is then checked twice: once with every conflict hunk as the project had
it, and once as the template brings it (`resolve_conflict` reads copier's own
`before updating` / `after updating` markers, and refuses markers that do not
nest). No check parses a marker, and no conflicted file is put back to DEST's
bytes beside the update's other files; a check that reads one file and reports
against another (check_W reads the Makefile and reports a stale
`effect_proof_skip` entry against `config/project.json`) would judge a mix
again. A finding both runs have is owed, whichever way the project resolves
the conflict. A finding only one run has depends on that choice, and is marked
`unjudged: conflict` too. The `[config]` group names what the update did to
each key of each JSON config a check reads (`JSON_CONFIGS`), by comparing the
template's render at DEST's `_commit` with DEST's file and the file after the
update (`classify` in `scripts/audit_project.py`):
- `arrives`: DEST lacks the key, and the update brings it;
- `updates`: DEST left the key as rendered, and the update changes it;
- `merges`: DEST and the template both changed the key, and copier's merge
  keeps both edits (an allowlist such as `child_env.names`, which the manifest
  renders one item per line);
- `removed-upstream`: the update removes a key DEST has.
A list is one value. A JSON config copier leaves conflicted gets one
file-level `conflict` entry and no key kinds. The group also carries an
`update-refused` warning when the real update would not start on DEST: copier
updates only a project in git with nothing uncommitted, tracked or untracked,
while the scratch copy is committed whatever DEST's state. The warning names
each uncommitted path (`paths`); the prediction stands for the tree once they
are committed, and the exit code does not change.

**No base.** When DEST's `_commit` does not resolve in this checkout (a fork,
a rewritten history), copier cannot update either, so nothing is predicted and
no scratch directory is made. DEST is judged as it stands, every origin is
`unknown`, the `[config]` group compares DEST with this checkout's render
(arrivals and updates only), and the "not checked" section has a `no base`
item.

**Origin.** Each check finding names the evidence about the file it is in.
The audit compares the path the message names in DEST with git at `_commit`:
- `template-unedited`: the bytes match the template's at `_commit`;
- `template-edited`: the file shipped but DEST changed it;
- `template-rendered`: only its `.jinja` twin shipped;
- `template-new`: neither DEST nor the template at `_commit` has the path, and
  the tree the update leaves does;
- `project`: the template never had it;
- `unknown`: there is no base, no path, or the file cannot be read.

**Owed or resolved by the update.** A letter finding in the run after the
update is owed, unless its file is conflicted or only one resolution of the
conflicts has it: the project must act on it, or the update leaves it red. A letter finding only in the run before the update
carries `resolved_by`, because the update itself removes it. The summary
counts resolved errors under `resolved_by_update`, not under `errors`, and the
text report prints both counts and the number of conflicted files. Findings
are matched by their message, so a message carrying a line number the update
shifts reads as one resolved and one owed: the owed count stays right, and
`resolved_by_update` may count one too many.

**What it does not run.** The report always ends with a "not checked"
section. It lists:
- the `[local]` effect sweep, and the project's tests, lint and typecheck,
  which are runtime proofs that run project code;
- the rest of `make check-all`;
- child processes started from shell scripts;
- makefiles outside the include walk;
- files DEST's git ignores, which are not copied, so neither run judges them;
- the code the update runs: copier's `_tasks` and `_migrations` run in the
  scratch copy, and keel's run `scripts/jobs/restamp_docs.py` as the update
  merges it with the project's edits. They run with an allowlisted
  environment, a scratch git config with no hooks, and no DEST `.git`, the
  same step the project's own update runs;
- each path it could not copy as it is: a symlink leaving DEST (copied as its
  target's bytes, or dropped when it dangles), a submodule, an untracked
  symlink in this checkout.

The confirmation is the real `copier update` in the project, then
`make verify` there.

**DEST is never written.** The audit never imports, makes or hooks DEST's code
in its own process. It reads DEST's files with `open()` and `ast`, and its git
only through name-level commands built by `review_docs.git_argv`:
`--no-optional-locks`, `core.fsmonitor=false`, `log.showSignature=false`, and
every filter driver DEST's git config names set to an empty, non-required
command. When git will not list those drivers, the call is not made. `git
status` also passes `--ignore-submodules=all`, so no submodule's config is
consulted. Plain `git status` and `git diff HEAD` rewrite `.git/index`
(measured, git 2.43.5), so the audit and the two doc jobs use neither. The
cost of the switched-off filters: a filtered file (an LFS pointer, say) whose
stat data is stale is compared raw, so it may read as modified. A symlink
leaving DEST is copied as its target's bytes, because copier writes through a
link. This checkout is snapshotted by `git clone`, never handed to copier, so
its index is never refreshed: copier on a dirty local template runs a plain
`git status` there. The scratch copy is removed on exit, so a second run
leaves every tree as the first did. `tests/integration/test_copier_audit.py`
proves this with a whole-tree hash of DEST, `.git` included, the template
copy's index bytes and mtime, and two byte-identical `--json` runs; its parity
test holds the prediction equal to `check_structure.py --root` on a real
update, and, for a project whose Makefile edit conflicts, equal to what that
gate finds on the real update resolved both ways (git's own `merge-file
--ours` and `--theirs` over copier's index stages).

**Exit codes.**
- 0: no letter error is owed.
- 1: a letter error is owed, or the audit saw no file. An error resolved by
  the update or in a conflicted file, a conflict, freshness and config never
  set it.
- 2: a usage error, a refusal (DEST is not a keel project), a template render
  error (DEST's answers included, when one has the wrong type), a failed
  `copier update` of the scratch copy (copier's last lines, the scratch path
  shown as `<scratch>`), or a missing `template` extra.

DEST is a keel project when every one of these holds:
- it is a directory, and not this checkout;
- its `.copier-answers.yml` is a mapping whose keys are all strings, with
  non-empty `_src_path` and `_commit` strings;
- its `config/project.json` is a JSON object.

`--json` prints the same report as canonical JSON, so two runs over the same
DEST on the same day are byte-identical: the scratch git's commit dates and
`SOURCE_DATE_EPOCH` are midnight UTC of the day the audit calls today.
