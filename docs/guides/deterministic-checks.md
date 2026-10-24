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
updated: 2026-10-26
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
make verify       # check-all + secret-scan + lint + typecheck + test + trace + eval + test-fe + test-sh (the everything gate)
```

Wire them once and forget:

```bash
pip install -e ".[dev]" && pre-commit install   # run the fast checks on every commit
make secrets-install                           # build the pinned secret scanner, once per machine
# CI already runs `make check-all` and `make secret-scan` (.github/workflows/ci.yml)
```

## Two interpreters, on purpose

The host's pre-commit `python3` may be **old** (as old as 3.6 on a supported
host), so the checks split in two:

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
| Structure & frontmatter | `scripts/check_structure.py` | error | 3.6-safe | Labels, taxonomy, package boundaries, tool/agent governance, project facts, agent-rules symlinks, owned-exception & frozen-config boundaries, naked-tensor domain warn, lint/type ruleset parity, template twin parity, Makefile help parity, cross-reference resolution, check-catalogue parity, rosters, practice mechanisms, policy reachability, writer rerun declarations, make-target effect labels, child-process environment, ADR number spaces, work naming (checks A–Z), then the project's own checks (`structure.project_checks`) |
| Interpreter floor | `scripts/check_python_version.py` | error | any | `$(PY)` satisfies `pyproject.toml`'s `requires-python`, said plainly before a newer-syntax check fails with a traceback — runs first in every target whose recipe needs the project interpreter, as a prerequisite or, in `audit-project`, as the recipe line after its usage checks; `tests/integration/test_gate_scope.py` derives which targets need it from the recipes and fails one that does not reach it. `PY` defaults to `.venv/bin/python` when it exists, else `python3` |
| Venv holds the declared packages | `scripts/check_venv.py` | error | >=3.8 | every requirement of `pyproject.toml`'s core dependencies, of config/project.json `venv.extras` and of the extra each enabled transport names in `transports.extras` is installed at a version its specifier allows, judged from installed metadata with no network — the first prerequisite of `make check-all`, which is `make verify`'s first goal, so a venv older than `pyproject.toml` fails with the pip command before a gate fails late or a test skips; `tests/unit/scripts/test_check_venv.py` |
| Corpus integrity | `scripts/jobs/check_corpus.py` | error | ≥3.7 | the fresh build is a valid, acyclic, reproducible graph whose edge kinds are from the closed set (`keyword`, `link`, `citation`, `mention`, `semantic`) **and** the local `wiki/corpus.json` (what agents query) is current when present — absent is a loud pass, stale is an error naming `make site-data` (ADR-K-0008) |
| OpenAPI drift | `api/rest_fastapi/export_openapi.py --check` | error | FastAPI | Committed `openapi.json` matches the live routes |
| AAD schema drift | `scripts/agent_surface/generate_aad_schema.py --check` | error | pydantic | Committed AAD JSON Schema matches the model |
| Code-doc drift | `scripts/cdmon_sync.py --check` | error* | any | cdmon code↔doc drift — the CONVENTIONS §9 worked example of a thin adapter over an external tool (*a stated skip, exit 0, until `cdmon` is on PATH **and** `config/cdmon/cdmon.yaml` exists; cdmon is not on PyPI). Reached from `check-all` via `make check-cdmon` |
| Exit-code table | `scripts/exit_code_table.py --check` | error | ≥3.10 | The exit-code table in `docs/guides/limits-and-troubleshooting.md` is what `scripts/exit_codes.py` `ExitCode` and the scripts `make verify` runs say: a member with no row, a row with no member and a script row naming other codes each fail it. Reached from `check-all` via `make check-exit-codes`; `make exit-codes` regenerates |
| Accountability | `scripts/accountability_report.py` | report | ≥3.7 | Lists corpus nodes that resolve to no owner, and counts apart those on the default owner and those with a real owner (informational; rides `make advise`) |
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
  `superseded_by` (one rule, two lifecycle vocabularies). A document that
  states a `visibility` less restrictive than a `README.md` above it, such as
  `public` under a `confidential` `README.md`, is an error naming that
  `README.md`: the corpus gives every node the most restrictive visibility on
  its chain (CONVENTIONS §1), so the looser level would be overridden in
  silence. A value outside the vocabulary is the invalid-visibility error
  instead.
- **B. Closed taxonomy** — every non-hidden top-level directory is a §2 row or
  declared in `config/project.json` `structure.extra_toplevel` (§15); a
  declaration names a directory that exists and is not already a row; every
  top-level directory and every directory directly under `agents/` (each
  `agents/<name>/` and `agents/tools/`) carries `README.md` + `CLAUDE.md`. An undeclared symlinked directory is a WARN, because no check
  reads through a link and the gate cannot ask git whether it is tracked.
  `structure.project_checks` is absent, null or a declared name, and a
  declared project-checks directory holds at least one module (section 1's
  "The project's own checks").
- **C. Package boundary** — every `src/` dir with `.py` has an `__init__.py`
  defining `__all__`.
- **D. `__init__` is the API** — no absolute import of another package's
  `_private` module, and no `from pkg import _sub` of a private submodule or
  subpackage from outside `pkg/`; a relative import that climbs out of the
  package is judged as its absolute twin would be. A `.py` file that any check
  reading Python cannot parse is one error, naming the file, however many
  checks read it. The one exception is a `SyntaxError` under an interpreter
  older than the floor of `config/project.json` `layers.backend.python`, as the
  pre-commit hook's host `python3` can be: newer syntax cannot be told from a
  broken file there, so the run prints one warning that counts those files and
  names both versions; `make check-all`, and so `make verify`, which reach `check-python` first (which refuses an interpreter below the floor),
  judge them. `make check` runs `PY`, which is host `python3` when there is no
  `.venv`, so it can defer them too. With no floor to read, the file is the
  error.
- **E. Authored coverage** — every `__all__`-exported symbol defined in-file has
  a docstring: the corpus's symbol summaries (error since ADR-K-0008).
- **F. Tool specs governed** (error) + **accountability** (error) — valid
  `kind: tool` frontmatter with a resolvable `public_api`, a `tool_effect` from
  the closed set, a `tool_command` that invokes the script; and the body
  contract of CONVENTIONS §10: the seven sections in order, `## Side effects`
  opening with the word for the declared effect (`READ-ONLY` / `WRITES` /
  `MODEL-CALL` — the body and the frontmatter are read by different agents and
  must not disagree), and at least one `- NOT ...` bullet under `## When to
  use` — the negative-scope line that names the sibling this tool is not.
  Accountability: check_F reads `config/project.json`
  `accountability.default_owner` through `scripts/config_loader.py` on every
  run, and a value outside the CONVENTIONS §12 owner grammar, or `TBD` or the
  word `null` in any letter case, is an error naming the key, whether or not a
  document needs the default. A `kind: tool` or `kind: agent` document whose frontmatter
  `owner` is `TBD`, in any letter case, inherits the default; with no default
  set (absent or `null`, the loader's default) each such document is an error
  naming it and the key, with no warning first, and with a refused value the
  error says the value was refused. An owner outside the grammar
  `[A-Za-z0-9._@-]+`, such as `"TBD"`, `"alice"` or `TBD # later`, is an
  error naming the document and the grammar in every governed document and
  `README.md`, whatever its `kind`, so a quoted or commented owner is never
  read as no owner in silence; outside tools and agents nothing else about the
  owner is judged. A written null, `null` in any letter case or `~`, is an
  error naming the document, which the default does not cover: YAML reads both
  as null, so neither names an owner, and `null` would otherwise pass the
  grammar as an owner called "null". Any other owner is never judged; a
  missing or empty `owner` is a warning. `scripts/jobs/build_corpus.py` reads
  the same key the same way, so such a `TBD` document is an
  `owner_source: default` node in the corpus (CONVENTIONS §12).
- **G. Tool↔agent binding** — `tools.md` ↔ each spec's `## Used by` agree.
- **H. Project facts** — `config/project.json` agrees with the tree (§15).
  An absent `config/project.json` is an error: copier never prunes it, so a
  tree without it has none of its facts judged.
  Among those facts, `layers.app` (the composition root `make run` runs) must
  name, by `path`, a package with `__main__.py` or a `.py` file, and by
  `module`, the dotted form of that path's trailing components; each problem is
  one error naming `layers.app.path` or `layers.app.module`. `null` declares no
  composition root, and an absent key is silent until `copier update` brings it.
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
  An absent `pyproject.toml` is an error while `rulesets` is declared, since
  copier never prunes it.
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
  *unverified*, never a pass. Silent without a `help` target.
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
  another language is reached through a `.py` adapter (CONVENTIONS §9). It
  catches a row that claims the error tier while `check-all` never runs it.
  Silent without this file; a checks table or Makefile it cannot read is a
  WARN that says *unverified*.
- **S. Roster parity** — a README `config/project.json` `rosters.readmes`
  lists is held to its directory: a pipe table follows the heading, its first column is
  `Member` (each cell a backticked path relative to the README's directory,
  directories with a trailing `/`), every member appears exactly once and
  nothing that is not a member appears (labels and packaging — `README.md`,
  `AGENT.md`, `CLAUDE.md`, `__init__.py`, `__pycache__` — hidden entries,
  ignored dirs and `.jinja` twins are not members), and a `Not for` column exists with every
  cell filled. The list, not the heading, is the switch: a listed README
  without the heading errors, and so does a README carrying the heading that
  the list does not name, so renaming the heading cannot turn the check off;
  an absent `rosters` block lists nothing, so every roster README errors. The
  list is in `config/project.json`, which `agents.protected_paths` keeps out of
  an agent's edit. Keel's list is `config/project.json` `rosters.readmes`. The `Not for` cell is the point: it states
  what a reader must not reach for that member to do and names the sibling
  that does — the discriminator between two things that look alike
  (`rebuild_index.py` and `build_corpus.py` both say "index"; the roster says
  which is the corpus and which is a README list). A member that ships only
  under a copier answer has its row inside `{% if %}` in the README's `.jinja`
  twin, so a generated project's roster matches its pruned tree — the
  generation tests run this check inside every generated project.
- **T. Practice mechanisms resolve** — every `config/practices.json` entry
  carries `enforced_by`, a list in a closed grammar (`check:<LETTER>`,
  `script:<path>`, `test:<path>`, `make:<target>`, `doc:<path>[ §N]`,
  `ruff:<CODE>`, `mypy:<flag>`), and every reference resolves: the check letter
  is defined here, the script/test/doc exists (and has that numbered section),
  the make target is a rule. `ruff:`/`mypy:` codes are accepted as written —
  the tools themselves reject an unknown one. `mechanism` stays as prose for a
  reader; this is the same claim a machine can hold. Silent without a
  registry.
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
  failure). A shaped target that is not a write keeps its label only when
  `make_targets.write_shape_exempt` names it with a reason; an entry naming a
  target no makefile defines, no suffix matches, no label annotates or that is
  already `[write]` is an error, so an exemption cannot outlive its target.
  Conversely, a labelled target whose recipe calls `$(WRITE_GUARD)` anywhere
  in any line (`$(WRITE_GUARD) && cmd` included; a `$$`-escaped reference is
  text, not a call) must be `[write]`: the gate runner would admit a `[read]`
  one and the guard would then kill it. The guard's definition, read as make stores it (a `#` comment
  cut off), must open with `$(if $(findstring i,$(firstword -$(MAKEFLAGS))),$(error ...))`,
  closed, so it stops make under `-i`, `--ignore-errors` or a bare `.IGNORE:`,
  where the shell's `exit 1` is ignored and the write runs; it must then test
  exactly the `make_targets.unattended_vars` names, carry no `-` prefix before
  or after that clause, and `exit 1`. Any `.IGNORE` rule in a makefile make
  reads is an error: `.IGNORE: <target>` ignores that target's errors without
  touching `MAKEFLAGS`, so the clause cannot see it. A target annotated on two rules must carry
  one label on both, since make merges them. The `make_targets` block
  itself is validated: `gate_effects` must hold `local` and must not hold `tree`
  or `write`, `gate_vars` may not name make's own control variables,
  `WRITE_GUARD` or an unattended variable, and each
  `empty_test_selections` key must be a bare marker carrying a reason. An
  `empty_test_selections` key that no recipe selects with `pytest -m <key>` is
  an error reading `stale:`; the recipes are parsed for that, never a list of
  tier names. With `area_dir` set, each `<area>.mk` is included, opens with one
  `##@ <area>` header, and prefixes its public targets `<area>-`. A recursion it
  cannot resolve (`$(MAKE) -C`, a variable target) is a WARN reading
  *unverified*. Measured over keel's Makefile: 38 annotated targets, 33
  `[local]`, 5 carrying `tree`. The label is a static claim; the runtime half is
  `tests/integration/test_make_target_effects.py`, which runs every `[local]`
  target through `scripts/run_make_target.py` and fails one that changed the
  tree or wrote the fresh empty `HOME` it runs under. Each target gets its own
  `HOME`, so a verdict does not depend on the dotfiles of the host or user that
  runs it; `make_targets.effect_proof_kept_dirs` names the XDG base dirs kept
  beside it (the caller's absolute value, else that path under the caller's
  `HOME`, else unset), and the sweep does not see writes there. Before the
  first target the sweep checks that `scripts/child_env.py` hands make that
  `HOME` and each kept value, and raises if it does not. `run` and `smoke` are in that sweep, and only the targets
  `make_targets.effect_proof_skip` names, each with its reason, are not. See [`docs/adr/keel/K-0011-make-target-effect-labels.md`](../adr/keel/K-0011-make-target-effect-labels.md) and, for the exemption and the converse, [`docs/adr/keel/K-0015-write-shape-exemptions-and-guarded-recipe-converse.md`](../adr/keel/K-0015-write-shape-exemptions-and-guarded-recipe-converse.md).
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
  is no waiver. The `config/project.json` `child_env` block,
  `models.credential_env` and `models.allowed_hosts` are validated through
  `child_env.child_env_policy`; an `allowed_hosts` entry must already be in
  the one form `child_env.canonical_host_entry` returns, and must name an
  adapter in `models.available`. `evidence.run_date` is validated through
  `run_date.policy`, the reader scripts/gate_evidence.py uses at the start of
  a run, so a block whose variable `child_env.names` does not list is an error
  before any run instead of a refusal at the start of one.
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
  would show it. A project generated before the key existed fails with
  `child_env.repo_context_names is missing` until `copier update` brings the
  key.
  `child_env.config_injection_names` and `config_injection_prefixes` are
  required and non-empty: they list the variables through which a parent
  hands git configuration (`GIT_CONFIG_PARAMETERS` from `git -c`,
  `GIT_CONFIG_COUNT` with `GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>`, and
  `GIT_CONFIG`), which override `GIT_CONFIG_GLOBAL` and reach every hook.
  `build_child_env` never copies a member, even under `repo_context=True`, and
  the check refuses the same allowlist sources as for `repo_context_names`, a
  prefix matching when either covers the other, and a name in both lists.
  `child_env.credential_value_patterns` is required and maps a lower-case
  label to a regular expression; the check refuses an empty map, a label
  outside `[a-z][a-z0-9-]*`, a pattern that does not compile, and a global
  inline flag after the pattern's start (Python 3.11 refuses it, 3.6 only
  warns), and an error names the label, never the pattern.
  `child_env.login_name_schemes` is optional, defaults to `[]`, and must list
  lower-case URL schemes. A project generated before these keys existed
  fails with `child_env.config_injection_names is missing` (and the pattern
  key) until `copier update` brings the keys.
  `child_env.credentialed_values` is optional and maps a copied variable to
  the reason its value may carry user information. The check refuses an
  entry that is not a variable name, has an empty reason, or names a
  variable no allowlist source copies, with `drop the stale entry` in the
  message. The value itself is judged at run time, not here, because the gate
  never sees the environment a child will get: `build_child_env` raises
  `ChildEnvError` with `build_child_env: HTTPS_PROXY holds user information`
  and the fix, and never the value; a value one of
  `credential_value_patterns` matches is refused the same way, the message
  naming the variable and the label
  (`matched: HTTP_HEADER=authorization-header`). This opt-in is config, not a
  keyword, because an authenticating proxy is a property of the site that
  every child crosses, not of one call.
  It under-reports, never over-reports, in two places: a spawn through a
  receiver it cannot resolve (`self.runner(...)`, `loop.subprocess_exec`,
  `sp = subprocess; sp.run`), and a parent-environment value that reaches the
  helper across a function parameter. It is defence-in-depth, not a sandbox: a
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
  the template's file, which check_A reports as a duplicate id. See
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
  because check_structure reads no git (ADR-K-0009).

**The project's own checks.** After the last letter, the gate runs each
top-level `*.py` module in the directory config/project.json
`structure.project_checks` names, in file-name order
(`docs/adr/keel/K-0014-project-owned-structure-checks.md`). A module defines
`check(root)` and returns `(tier, message)` pairs, the tier `error` or
`warning`; each finding is reported as `project:<stem>`, its message prefixed
with the module's path. A module may `import check_structure` and use the
gate's readers, such as `walk_makefiles` and `make_target_rules`, and its
`err()` and `warn()`: what a module reports through those is its own finding
at that tier, so a rule moved out of the gate unchanged still fails it. The
key is absent or null (off) or a name already in `structure.extra_toplevel`;
the template never ships it, so a project adds it when it adopts. check_B
errors on any other value and on a declared directory that holds no module. Every way a
module can fail is an ERROR naming it, and such a module is never executed
when it holds a conflict hunk:
- a `*.py` name that is not a regular file, such as a dangling symlink
- unreadable, not UTF-8, conflicted or not compiling
- raising or exiting while loading
- no callable `check`
- a `check` that raises, exits or returns a malformed value
- leaving the gate's `errors` or `warnings` as anything but a list

The template's findings are complete before the first module loads, and each
module runs against fresh `errors` and `warnings` lists, so a project check
can only add findings. The template itself declares none.

**When to run.** Every commit (pre-commit) and in CI; any time you add a
directory, package, doc, tool, or agent.

**Run.** `make check` · `python3 scripts/check_structure.py`

**Changing it.** A project adds a rule through `structure.project_checks`
(above), never by editing this script. Only the template's maintainer changes
the scheme or a lettered check, and then updates **both** this script and
`CONVENTIONS.md`.

### 2. Corpus integrity & reproducibility — `scripts/jobs/check_corpus.py`

**Purpose.** `wiki/corpus.json` is the generated "one-brain" index (CONVENTIONS
§11). This check validates the graph — unique `node_id`s, resolvable
`parent`/`children`/`links`, valid `kind`/`owner_source` (`frontmatter`, `marker`, `inherited`, `default` or `none`)/`visibility` and a link `kind` from the closed set, owner
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
(`owner_source: none`, CONVENTIONS §12), so ownership gaps are visible. On its
own line it counts the nodes that answer to `accountability.default_owner`
(`owner_source: default`), listed by the `TBD` each answers to, since writing
the real owner there repairs every node under it. Another line counts, and
lists, the nodes that name no owner source (missing, null, or outside the
CONVENTIONS §12 set): their owner is unknown, which is not `none`, and rebuilding the
corpus repairs them. A last line counts the nodes with a real owner. `--json` lists the unowned nodes only, the shape
`agents/index_enforcer` reads as its owner gaps. Does not fail the build.

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
never moves a stamp backwards. Copier runs it as a task in every render, at
generation and in every update, and again as the last update migration
(`docs/adr/keel/K-0010-generation-needs-trust-to-stamp-docs.md`).

**Tier.** A *report* under `make advise` (exit 0). The same rule is a **gate**
in `tests/integration/test_doc_freshness.py`, beside the release-identity test
and for the same reason (ADR-K-0009): a check that shells to git does not belong
in the 3.6 pre-commit hook. The work-naming rule has the same git half:
`tests/integration/test_work_trailers.py` judges each commit's `Slice:` and
`Backlog:` trailers after `work_naming.adoption_boundary`, and check_Z judges
the plan docs. The shipped-doc rule has a pytest half too:
`tests/integration/test_doc_drift.py` refuses, in a shipped document's prose,
a concrete campaign or slice id, a `doc_drift.forbidden_phrases` pattern, a
loopback port no non-Markdown file declares, and a citation of a document
copier.yml never ships (CONVENTIONS §15, `doc_drift`). The same test holds the
newcomer documents `doc_drift` names: each `one_hop` entry document links
directly to its listed documents, the README tree under `layout_heading` lists
every top-level directory that ships, each `roster` row names its audiences,
the `limits_guide` names every waiver and every exit code of the scripts
`gate_target` runs, and the `upgrade_guide` gives every copier task and
migration its own row in copier's order, every exclusion a row, and the copier
version floor. It reads copier.yml through yaml and the file list through git,
so it runs under `make verify` and `make test`, not in pre-commit. Its sibling
`tests/integration/test_reference_drift.py` holds the settings reference that
`doc_drift.settings_reference` names: the reference has one row for each JSON
key path, copier question, make variable, environment variable and
command-line flag the code reads, and each literal default it states is the
code's, character for character. The same test holds the feature catalogue
that `doc_drift.features_reference` names: it has one row for each check
letter, make target, checker script, copier job, gate test, scripts module
another module outside `tests/` imports, agent, MCP server, model and
runtime adapter, workflow and skill the tree declares, each make target's row
carries the effect label its help opens with, and every row's Limits cell is
non-empty.

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

### 9. End-to-end coverage — `tests/integration/test_e2e_coverage.py`

**Purpose.** A gate run by `make test`, not by `make check-all`: it fails when
an endpoint an enabled transport serves is named by no scenario. It derives the
endpoints from the code, never from a list: the REST app's OpenAPI document
(written by the exporter `config/project.json` `e2e.openapi_exporter` names),
each `__main__`-guarded MCP server's `tools/list` asked over its stdio, and each
`rpc` of a `.proto` service. `e2e.sources` in `config/project.json` maps each
transport to one of those kinds, or to `none`. A scenario under
`e2e.scenario_dir` names an endpoint with `@pytest.mark.endpoint("<id>")`, and
`e2e.exempt` maps an endpoint id to the reason it has no scenario. A marker or
an exemption that names no endpoint, an exemption a scenario makes redundant,
an exemption with a blank reason, a marker that applies to no collected test,
and a route the app serves that its OpenAPI document cannot list (a websocket,
a mount, a plain Starlette route, a route hidden from the schema, wherever it
is defined) are each red. The last is an allowlist over the routes the app
loads, walked in a child: only an API route in the schema, or a documentation
route the app's own settings name, passes. Every rule
has a fault-injection twin in the same module.

**What it does not prove.** That a scenario asserts anything meaningful: the
gate reads markers, and review judges the assertions. A transport whose extra
is not installed is skipped locally and red in CI
([limits-and-troubleshooting.md](limits-and-troubleshooting.md)).

**Run.** `make test` · `pytest tests/integration/test_e2e_coverage.py tests/e2e`

---

### 10. Replayed evals — `scripts/run_evals.py`

**Purpose.** A gate run by `make eval`, a `make verify` goal of its own, not by
`make check-all`, so it has no row in the table above. It judges actual
responses: every case in config/project.json `evals.dataset_dir`
(`evals/datasets`) runs its real doer against a backend that answers with the
response recorded in the case, and the recorded answer is scored by a
deterministic scorer. A suite passes when passed/total >= `evals.threshold`
(`1.0`, so every case must pass), compared exactly. A case whose prompt
changed since it was recorded is stale and fails its suite, because its
answer was judged against a prompt the code no longer sends. A malformed
dataset, zero cases, or a report directory git does not ignore is refused
(exit 2), never a pass.

**Why replay.** It makes no model call and reads no credential, so it is
deterministic, free, and safe to run on every commit. `make eval-live` sends
the same cases to a real model under the call cap `evals.live.max_calls`
(`0`), and is never part of `make verify`.

**What it does not prove.** That a model would still give the recorded answer
today: only `make eval-live` asks. That the scorers capture quality: a
deterministic scorer checks a shape or a substring, and review judges whether
the cases are the right ones (`evals/README.md`).

**Run.** `make eval` · `make eval-live` · `evals/README_run.md`

---

### 11. Requirement traceability — `scripts/trace_requirements.py`

**Purpose.** A gate run by `make trace`, a `make verify` goal of its own, not
by `make check-all`, so it has no row in the table above. It fails when a
requirement a spec states is named by no test and excused by no gap. It reads
every `kind: spec` document under config/project.json `traceability.specs_root`
(`docs/specs`): a heading whose first word is an id defines a requirement, and
a `- AC-<n>: <text>` line below it defines a numbered criterion. It reads
every `@pytest.mark.req("<id>")` call, the marker `traceability.marker` names,
from the test files pytest collects under `traceability.tests_root` (`tests`),
and counts a marker only on a definition pytest collects: not one a later
definition of the same name replaces, not one in a class pytest refuses, and
not one below a directory `norecursedirs` skips. The gate test compares that
reading with a child `pytest --collect-only` and fails when they differ.
Each unit, a criterion or a requirement that has none, gets one verdict:
`covered`, `gap` (a `traceability.gaps` row with a reason) or `uncovered`. A
bare requirement id never covers a requirement that has numbered criteria.
`scripts/traceability.py` holds the one parser of an id and the verdict rule;
`traceability.id_prefixes` is the closed list of prefixes it accepts, and an
unlisted prefix is refused rather than guessed at.

**What it writes.** One file, `traceability.matrix_path`
(`.evidence/traceability/matrix.json`), replaced whole by each run:
every requirement, its units, verdicts and naming tests, the findings, and a
`result` from `pass`, `fail`, `incomplete` and `refused`.
`config/traceability/matrix.schema.json` (`traceability.matrix_schema`) fixes
its shape, its version and the length caps on a cited id and a gap reason.
The command writes an `incomplete` matrix before it reads a spec, so a run
that stops leaves no earlier `pass` standing. It refuses, before any read or
write, a `matrix_path`, `specs_root`, `tests_root` or `matrix_schema` reached
through a symlink, and a `matrix_path` git does not ignore.

**What it does not prove.** That a test asserts what its requirement says: the
gate reads marker calls from source and imports no test, and review judges the
assertions. That a spec states the right requirements. `make trace` alone does
not see a marker reached through a name other than `pytest.mark` or an
imported `mark`, or one built at run time; the gate test's comparison with
pytest's collection does.

**Run.** `make trace` · `pytest tests/integration/test_requirement_traceability.py`

---

### 12. Exit helper and exit-code table — `scripts/exit_code_table.py --check`

**Purpose.** Two gates hold one rule: a process ends through
`scripts/exit_codes.py`, with a code from its `ExitCode` enum.
`tests/integration/test_exit_gate.py` reads the syntax tree of every Python
file `scripts/check_structure.py` walks. It fails `sys.exit`, `os._exit`, an
argparse `.exit(...)`, `raise SystemExit`, a SystemExit subclass, the builtins
`exit` and `quit`, and an import that renames one of them, anywhere but in the
helper. It fails an entry block whose `finish(...)` is handed anything
`scripts/exit_code_table.py` `read_script` cannot follow to a member: a bare
integer, a failure member returned without `report`, a function that can
reach its end without returning. It fails a `report` or `fail` call that
lacks one of the three message parts or holds a blank literal one. It fails
a `fail` or `finish` call outside the entry block of a module another project
module imports, because only an entry point may end the process; config/project.json
`import_layers.may_end_the_process` names the one module that may, with its
reason, and a stale entry fails. `passthrough` ends nothing and is allowed.
`scripts/exit_code_table.py --check` compares the region between the
`<!-- exit-codes:begin -->` and `<!-- exit-codes:end -->` lines of
`docs/guides/limits-and-troubleshooting.md` with what it would write: one row
per enum member, and one row per script a recipe reachable from `make verify`
runs.

**What it does not prove.** That a message part helps its reader: the gate
sees a blank literal, not a vague one, and `report` refuses a blank value at
run time. It does not see an exit reached through `getattr`, `os.abort`,
`os.kill` or an uncaught exception, argparse's own `--help` (exit 0) and
usage (exit 2) exits, or a `python -c` line in a makefile. The hand-written
table below the generated region is compared with nothing.

**Run.** `make check-exit-codes` · `make exit-codes` · `pytest tests/integration/test_exit_gate.py`

---

### 13. Tree-wide source gates — `tests/source_tree.py`

**Purpose.** Four gate tests judge the Python files the structure gate
walks, through one shared reader, `tests/source_tree.py`, so no two of them
disagree about which files are the project's, what an import points at, or
what a comment is. None is a `scripts/check_structure.py` letter, because
the letters A to Z are taken; `make test` runs them.

- `tests/integration/test_import_layers_gate.py` resolves every import
  through config/project.json `import_layers.search_roots` and fails one that
  points into a higher layer of `import_layers.order`, a file no prefix
  places, and a prefix on disk that places no file.
  `docs/adr/keel/K-0021-imports-flow-up-a-configured-layer-order.md` is the
  decision.
- `tests/integration/test_swallowed_error_gate.py` fails a bare `except:`, and
  an `except Exception` or `except BaseException` with no `raise` whose body
  only passes, continues, breaks, or returns or assigns a fixed value such
  as `None`, `-1` or `[]`, unless a `# noqa: BLE001` or `# noqa: E722` on
  its clause gives a reason after its codes. It fails
  every such suppression whose reason is blank.
- `tests/integration/test_change_comment_gate.py` fails a comment that opens a
  thought with a config/project.json `change_comments.phrases` phrase as a
  whole word, and skips one that opens with a `change_comments.directives`
  entry. It reads comments through tokenize, so a `#` inside a string is never
  one.
- `tests/integration/test_config_reads_gate.py` walks the directories
  config/project.json `config_reads.roots` names, `scripts/config_loader.py`
  left out, and fails an open or read of a file the loader's `PROJECT_READS`
  declares and a read of a variable the config declares, outside the loader.
  It follows a path through constants, names bound to them, a starred split,
  a path constant of another project module (read as `mod.NAME` or imported
  with `from mod import NAME`) and a helper of the same module. A file that
  still reads directly is excused only by a `config_reads.allowed` entry with
  a reason; a stale entry is red, and the test's `_CEILING` caps the count.
  In the template repository, which holds `copier.yml`, a finding is red; in a
  generated project, which cannot tell keel's files from its own, the two
  finding tests skip and name each direct read they saw.
  `docs/adr/keel/K-0022-one-config-loader.md` is the decision.

Each fails, never passes, on a malformed config block, a walk with no Python
file, and a walk with nothing to judge.

**What it does not prove.** The layer gate cannot see an import made through
`importlib`, `__import__` or a `sys.path` entry no search root names. The
swallowed-error gate judges a handler by its body's shape, so a handler that
does work but never looks at the error, and `contextlib.suppress`, pass. The
comment gate is a heuristic: a phrase in mid-sentence, or a change reported in
other words, passes. The config-reads gate is a heuristic too: a path handed in
as a parameter, an attribute of a module imported inside a function or
relatively, a function of another module that opens what it is given, a
method called through an object, a variable name held in a variable, and a
read through `subprocess` or `importlib` pass; in a generated project it
judges nothing, it names.

**Run.** `pytest tests/integration/test_import_layers_gate.py tests/integration/test_swallowed_error_gate.py tests/integration/test_change_comment_gate.py tests/integration/test_config_reads_gate.py`

---

### 14. Toolchain versions and lockfiles — `scripts/check_toolchain.py`

**Purpose.** A lockfile is the dependency tree one npm, under one Node, resolved
for one `package.json`. CI that installs without it, or under another Node
major, installs a tree nobody tested. So each version has one home,
config/project.json `toolchain`, and three checks hold the tree to it:

- `scripts/check_toolchain.py node` runs `node --version` and exits 1 when its
  major is not `toolchain.node_major`, or when node is absent, exits non-zero
  or prints no `v<major>.<minor>.<patch>`. `make fe-install` runs it before
  any `npm install`, and only when the Makefile's `FE_APPS` names an app.
  `scripts/check_toolchain.py versions` prints `node=<toolchain.node_major>`
  and `python=<toolchain.python>`; every workflow job that installs either
  runs it first as the step with id `toolchain`, appending to
  `$GITHUB_OUTPUT`.
- `tests/integration/test_toolchain_gate.py` fails a workflow job whose
  `runs-on` is not in `toolchain.runner_images` (a `-latest` label, which
  moves under the project, is refused there by the loader), a setup-node or
  setup-python step whose version is not `${{ steps.toolchain.outputs.node }}`
  or `${{ steps.toolchain.outputs.python }}` from an earlier `toolchain` step
  of the same job, a `toolchain.python` below `layers.backend.python` or
  `pyproject.toml` `requires-python` (judged by `packaging`, the specifier
  library pytest depends on), and an `fe-install` recipe that reaches
  `npm install` before the Node check; it then runs `make fe-install` in a
  scratch copy against a stub `node` of the wrong major and of the configured
  one, and holds that the first never reaches npm.
- `tests/integration/test_frontend_lockfile_gate.py` asks git, through
  `git ls-files`, for every `package.json` the Makefile's `FE_APPS` glob names
  and fails one whose `package-lock.json` is untracked or absent, whose
  `lockfileVersion` is below 2, or whose root entry `packages[""]` records
  other `dependencies`, `devDependencies`, `optionalDependencies` or
  `peerDependencies` than the manifest; a set `layers.frontend.stack` git
  tracks no app for is a fault too.

Each gate test also judges planted faults, so a check that judges nothing
cannot pass. The checker is not in the catalogue table above: `make check-all`
does not run it, because it judges the host's Node, which `make fe-install`
needs and the tree's gate does not.

**What it does not prove.** The checker compares the major only, so another
minor or patch passes. The toolchain gate reads the workflow files; a version
set inside a reusable workflow or an action passes. The lockfile gate compares
the manifest with the lockfile's root entry, not with the resolved tree below
it, and it skips in a tree outside any git repository, and in a project with no
frontend app and no stack, saying which.

**Run.** `make fe-install` · `python3 scripts/check_toolchain.py versions` · `pytest tests/integration/test_toolchain_gate.py tests/integration/test_frontend_lockfile_gate.py`

---

### 15. Committed secrets: the keyed gate and the scanner — `tests/integration/test_committed_secrets_gate.py`, `scripts/scan_secrets.py`

**Purpose.** A credential that reaches a commit is exposed to everyone who can
read the repository, and deleting it later leaves it in history. Two layers
judge what a commit carries, and each is for what the other cannot see.

- **The keyed gate** is keel's own rule, with no outside tool.
  `tests/integration/test_committed_secrets_gate.py` takes its secret names
  from the `scripts/config_loader.py` `KEYS` rows marked `secret=True`, reads
  every file a commit could carry (`scripts/git_tree.py` `candidate_files`:
  tracked, staged, and untracked but not ignored, a force-added ignored file
  included) and judges a basename matching config/project.json
  `secrets.json_files` as JSON at any depth and one matching
  `secrets.dotenv_files` as `KEY=VALUE` lines, the work-tree copy and the index
  copy both. A value under a secret name is red, naming the file, the line and
  the key and never the value. The empty value is the only placeholder,
  because `.env.example` ships a secret name with nothing after it: in a
  dotenv file `changeme` or `${OTHER}` is a value, and in JSON only `""` and
  `null` pass. A leading byte order mark, which a Windows editor writes and
  a dotenv loader skips, hides no key, and a bare CR ends a line as LF does.
  A committed symlink is judged at its target's own path, never as the link's
  text. It also fails a `models.credential_env` name with no secret
  row, so a new credential cannot pass by having no row. It is **not** for a
  credential's shape: a value under a name no row declares, or in a file type
  it does not parse, is the scanner's.
- **The scanner** is a thin adapter behind that rule.
  `scripts/scan_secrets.py` is the gitleaks adapter: it runs the gitleaks
  release `make secrets-install` installed and recorded, and refuses any other
  config/project.json `secrets.scanner.name` with exit 14, because its flags, rules file and
  report fields are gitleaks's own. Another scanner is a second adapter, not
  an edit to the gate test. It judges shapes, such as an access-key prefix and
  its alphabet, whatever the name or the file. It is **not** for a value whose
  shape no rule knows: the keyed gate judges names.

The scanner runs in three places, each running the one recorded program
(`tests/integration/test_gate_scope.py` holds all three to config):

| Where | Command | What it judges |
|-------|---------|----------------|
| every commit | the `.pre-commit-config.yaml` hook `secret scan (staged, or every commit when nothing is staged)`: `python3 scripts/scan_secrets.py --staged-or-history` | the staged diff, in the index git hands the hook (`GIT_INDEX_FILE`, so `git commit -a` is judged too); under `pre-commit run --all-files`, which stages nothing, every commit `secrets.scanner.history_log_opts` reaches |
| `make verify` | `make secret-scan`: `scripts/scan_secrets.py --history` | every commit `secrets.scanner.history_log_opts` (`--all`) reaches |
| CI | `make secrets-install`, then `make secret-scan`, before `make test` | the same, over the full-history checkout |

The adapter fixes the scanner's flags in code, because each one closes a way
past it: `--redact`, so no report holds a value; `--ignore-gitleaks-allow`,
so an inline allow comment in the file under judgement excuses nothing; an
empty ignore directory and a rules file that only extends the default rules,
so a file in the tree cannot change what is judged; and a finding status of
`secrets.scanner.leak_exit_code` with a JSON report, so the scanner's own
crash cannot read as a clean scan or as a finding. A scan beside a file named in
`secrets.scanner.refused_files` (the scanner's own config and ignore file) is
exit 14 before the scanner runs. Every scan runs the recorded program only,
never one found on PATH: `make secrets-install` records its path, rev and
sha256 in the git-ignored `secrets.scanner.record_file`, and no record,
another rev, a path that is gone or a changed digest is exit 11 naming
`make secrets-install`, never a skip.

**Install.** `make secrets-install` runs `scripts/install_scanner.py`, which
needs no Go toolchain and no build. It picks this platform's entry in
`secrets.scanner.release_assets` (the key is the lowercased
`<system>-<machine>`, such as `linux-x86_64`), fetches that file name joined to
`secrets.scanner.release_url`, and installs the archive's one program under
`secrets.scanner.install_root`, a per-user directory outside the checkout, only
when the archive's sha256 is the pinned one; the pins are copied from the
vendor's checksums file for `secrets.scanner.rev`. The archive stays beside the
program, so a second run proves the program from bytes whose sha256 is the
pin: it fetches nothing and rewrites nothing only when the kept archive's
sha256 is the pinned one and the program is that archive's member, byte for
byte, and otherwise installs again (`tests/unit/scripts/test_install_scanner.py`).
A `secrets.scanner.rev` or `secrets.scanner.name` that is not one path part,
and a program path a link leads into the checkout, are exit 14 before any
fetch; a local file the installer cannot read or write is exit 2 naming it.
An unlisted platform is exit 14 naming the platforms the map lists; a sha256
that differs is exit 1 and installs nothing. A host that cannot reach the
vendor points `secrets.scanner.release_url` at a mirror holding the same files
(an https URL, or `file:///` for a directory the host already holds); the
sha256 check does not change.

**Exclusions.** A fake credential kept on purpose, such as a test fixture, is
a `secrets.scanner.exclusions` entry: one exact repo-relative path mapped to
one rule id and a non-empty reason. A glob, a `..` part or an absolute path is
refused (exit 14), and an entry the history scan did not use is exit 14, so a
stale one cannot sit there waiting for a real value. An entry excuses every
finding of that rule in that file, a later real one included: keep fixtures
in a file of their own.

**Exit codes.** 0: clean, or every finding excused. 1: a finding, one
`file:line rule` line each (a history finding with its commit after it), and
nothing else, so 1 always means "rotate or excuse a value". 2: a git command
that ran and failed, or a bad command line. 11: no scanner, no matching
record, or a scanner whose status and report disagree, so it gave no verdict.
13: no repository, no commit, `git log` options that reach no commit, or a
`--staged` scan of a stage that adds or changes no file, because a scan over
zero files or commits proves nothing. 14: a config fault, an unused exclusion
or a scanner name with no adapter included. `docs/guides/limits-and-troubleshooting.md` gives each script's
codes and each message's fix.

**What each layer does not catch.** Each row but the one marked "not tried"
and the two marked "unit-tested" was tried in a generated project against the
real scanner (gitleaks v8.30.1), and is caught, refused, or not caught and
accepted; the two are tried by `tests/unit/scripts/test_install_scanner.py`
against a fixture archive:

| Way past | Outcome |
|----------|---------|
| `git commit --no-verify`, or `SKIP=secret-scan` | the staged hook does not run; `make secret-scan` in `make verify` and in CI is red on the commit |
| `git commit -a` of an edited tracked file | caught: the hook judges the index git hands it |
| an inline `gitleaks:allow` comment | caught: `--ignore-gitleaks-allow` |
| a `.gitleaksignore` or `.gitleaks.toml` in the tree | refused, exit 14, before the scanner runs |
| an access key base64-encoded in a source file | caught by the scanner's decoding |
| an access key split across two string literals | not caught: no rule sees the joined value |
| a weak password under a name no secret row declares (`db_password = "<value>"`) | not caught: no rule knows its shape and no secret row its name |
| an access key under a non-secret JSON key | caught by the scanner; the keyed gate does not see it |
| a secret name with a value in a `.env.production` added with `git add -f` | caught by the keyed gate |
| an access key in a file the scanner's default allowlist skips (`package-lock.json`, `go.sum`, `*.svg`, `*.pdf`, under `node_modules/`) | not caught |
| an exclusion naming a file and rule | excuses every later finding of that rule in that file |
| a program named like the scanner, first on PATH, that writes an empty report | caught: no scan runs a program from PATH, and `make secrets-install` installs only the archive whose sha256 config pins |
| the record file edited by hand to name another program | not caught: the record is git-ignored and per machine, so it proves the program has not changed since it was recorded, not who recorded it; CI installs its own |
| the installed program swapped, with a note beside it forged to match | unit-tested, caught at the next `make secrets-install`: it proves the program from the kept archive, whose sha256 must be the config pin, and installs again |
| a user who can write `secrets.scanner.install_root` (or the record) swaps the program after the install | unit-tested, not caught until `make secrets-install` runs again: a scan checks the program against the record's sha256, not against the archive, so whoever can write both runs their own program; the install root is per user for that reason, and CI installs its own |
| a commit pushed with CI skipped (`[skip ci]`) | not tried, because it is the CI provider's behaviour: CI does not run on that commit, and `make verify` on any clone, and the next CI run, scan it |
| a value already pushed | the history scan is red, and the value stays exposed: rotate it (`docs/guides/limits-and-troubleshooting.md`, "A credential was committed") |

The keyed gate also cannot see a value already in history, which is the
history scan's, or a file outside both basename patterns.

**Cost.** The first `make secrets-install` on a machine fetches one release
archive of a few megabytes and installs one program; later runs with the same
pins fetch nothing. The history scan of a project's own history takes seconds. The scanner
is not in the catalogue table above, and `make check-all` does not run it,
because it needs the recorded build, which a fresh clone does not have.

**Run.** `make secrets-install` · `make secret-scan` · `pytest tests/integration/test_committed_secrets_gate.py tests/integration/test_secret_scan.py`

---

### 16. Dependency audit and accepted risks — `scripts/audit_dependencies.py`

**Purpose.** `npm audit` reports every advisory against an app's locked
dependency tree, and some stay open for a reason: the only fix is a breaking
downgrade, or the vulnerable code never sees outside input. A reason kept in a
note expires silently, and a fixed advisory leaves the note behind.
config/project.json `dependency_audit.accepted` is where the reason lives, and
`make fe-audit` judges every app's audit against it on every run. It runs
`npm audit --json` in each app the Makefile's `FE_APPS` names, under the
allowlisted child environment and `dependency_audit.timeout_seconds`, and it
fails, listing every failure before one closing line, on four things:

- a finding at or above `dependency_audit.fail_at` (`high` by default, so a
  critical or a high) that no row names with the same advisory id and the
  same package;
- a row whose `review_by` day has passed, judged on the date
  `scripts/run_date.py` `today` reads (the gate run's date when it is set,
  else the clock);
- a row whose `review_by` is more than `dependency_audit.max_review_days`
  (90 by default) days after that date: a parked acceptance, renewed rather
  than set far out;
- a row whose advisory and package the app's audit no longer reports, or
  whose app is not one the run audits: a stale acceptance, removed rather than
  kept.

A moderate or low finding no row covers is listed on stdout and does not
fail. That is the rule the frontend audit's queue rows already follow: a
weaker finding is tracked as owned work with its own row, not as a red gate,
and `dependency_audit.fail_at` lowers the floor for a project that wants it
red. A covered finding is listed with its reason and day.

**How to accept a risk.** Run `make fe-audit`, take the advisory id and the
package from the failing line, and add a row under the app's directory name:

```json
"dependency_audit": {
  "accepted": {
    "astro": {
      "GHSA-rj75-hqrm-r3gf": {
        "package": "postcss-selector-parser",
        "reason": "the only fix is a breaking downgrade; the parser reads the project's own stylesheets",
        "review_by": "2027-01-21"
      }
    }
  }
}
```

The reason says why the finding stays open, in terms a reviewer can check.
`review_by` is the last day the acceptance holds; from the next day the row
fails as expired. To keep it, look again and write a new date; to drop it,
fix the package and delete the row, which the stale rule otherwise forces.
The date may be at most `dependency_audit.max_review_days` days after the
run's date: exactly that many passes, one more fails, so keel's own row,
written 90 days out, passes the default cap on the day it was written. The
loader refuses a row that is not exactly `package`, `reason` and `review_by`,
an id not written `GHSA-xxxx-xxxx-xxxx`, a blank reason and a date not
written `YYYY-MM-DD`, with exit 14.

A generated astro project inherits keel's accepted row and its `review_by`
date, so on or after that day the project's own `make fe-audit` fails until
its owner renews the row or fixes the advisory; that is intended, because an
acceptance is a per-owner decision.

**What it does not prove.** It judges the advisories the registry knows on the
day it runs, so a pass today can fail tomorrow with no change in the tree; that
is why `make verify` does not run it. It judges `npm audit`'s own reading of
the lockfile and does not inspect `node_modules`. It reads a finding's
severity from the report and never weighs whether the vulnerable code is
reached; the reason is the human's claim, not a proof. It refuses a report it
cannot trust rather than pass it: one that is not JSON or not `npm audit
--json` version 2, a `via` item that is neither an advisory nor the name of
another entry, `metadata.vulnerabilities` counts that disagree with the
entries, and a `metadata.dependencies.total` of 0 or none while the app's
`package.json` declares a dependency, which is what an empty or root-only
lockfile audits as. A `package.json` declares one when any of `dependencies`,
`devDependencies` or `optionalDependencies` is non-empty, when
`peerDependencies` names a peer that `peerDependenciesMeta` does not mark
`optional: true`, or when `workspaces` names a package glob, as a list or as
an object's `packages` list. When `workspaces` names one, the refusal's next
step names a pattern that matches no directory beside `make fe-install`, since
either leaves the report empty. Such a report is exit 2 from a saved `--report` file and
exit 11 from a run, as is npm exiting 1 with no finding, and npm that cannot
start, overruns the timeout, exits other than 0 or 1 or answers an `error`
object is exit 11; none of these is a pass. An exit 11 line carries npm's own
diagnostic: the `error` object's `message` or `summary`, else the top-level
`message` npm 11 writes, with `error` left blank, when the registry cannot be
reached or refuses the request (a 401 adds `statusCode`, `uri` and `headers`
beside it), else npm's last stderr line other than its `A complete log of
this run can be found in:` pointer. That diagnostic is first cut to
`dependency_audit.max_shown_chars` characters (500 by default); the word the
cut lands in is dropped, because a token's fragment can be too short for the
last rule below, and the line ends `<cut to N characters>`. The next step is
chosen from the whole diagnostic, not the cut one. A registry or proxy writes
this text, so every redaction pattern bounds a character run unless a literal
fixes where it starts or it is the whole pattern;
`tests/unit/scripts/test_audit_dependencies.py` fails when redacting a
16 000-character line takes a second, which the unbounded key rule took nine
times over, and so does a 50 000-character one such as `token` repeated,
which took four seconds while each glued key opened a clause that read to
the line's end. A key followed by a letter or digit opens no clause, and
that is what keeps such a line fast. A clause word is also read at most 300
characters at a time, so its runs are bounded as every other pattern's are;
`tests/unit/scripts/test_audit_dependencies.py` fails when that cap is
raised. A longer word is judged in 300-character parts, so a part after the
first shows when it is a vocabulary word or up to three marks, and a part
that is a secret word, `Bearer` or `Basic` opens its own clause, as one after
a space does, a scheme name's realm included. So `password` then 300 `x` and
`required` reads `password <hidden>required`, with `token` in place of
`required` it reads `password <hidden>token`, and with `Basic realm="<value>"`
it reads `password <hidden>Basic realm="<value>"`, the realm kept as the
scheme rule below keeps one. The line is redacted by structure, not by a list
of token shapes, because a list leaks every shape it does not name; each rule
rewrites only its own span, so the cause (`ENOTFOUND`, `E401`, `Unable to
authenticate`) stays readable.

- **A URL** keeps its scheme, host and port, a bracketed IPv6 host included,
  and loses its userinfo: everything before the authority's last `@`, so a
  raw `@` in a password shows no part of it. A port is at most five digits,
  and whatever follows the host and port, a longer number included, becomes
  `<path hidden>` unless it opens with a comma or semicolon, which end the
  URL. The path runs up to a space, quote, `<` or `>`, so a query or a token
  glued on past a `)` goes with it: npm masks only a userinfo password, and a
  registry token can sit in the userinfo or the path. A URL's scheme is one
  npm reaches: `http` and `https` (npm-registry-fetch), `socks`, `socks4`,
  `socks4a`, `socks5` and `socks5h` (socks-proxy-agent), `git`, `git+http`,
  `git+https`, `git+ssh`, `git+file` and `file` (npm-package-arg) and `ssh`
  (hosted-git-info), listed in `_NPM_SCHEMES`. Text glued before a scheme is
  no part of it. After any other `://` the userinfo and path are hidden the
  same way and the name before it stays.
- **An `Authorization`, `Bearer` or `Basic` scheme** keeps its name and its
  `realm="..."` and loses its value. `Bearer` and `Basic` are then keys as a
  secret word is, so the words after the hidden value are judged by the next
  rule: `Bearer <value> <value>` shows neither. A `realm=` parameter right
  after `Bearer` or `Basic`, quoted or not and up to 256 characters, is kept
  as written, so npm-registry-fetch's `Unable to authenticate, need: Basic
  realm="Sonatype Nexus Repository Manager"` reads in full, and the words
  after it are judged. An unquoted realm longer than 256 characters shows its
  first 256 and the rest is judged as a word glued to it, so a realm of
  letters reads its first 256 and then `<hidden>`. A quoted one whose closing
  quote lies past 256 characters is read as an empty unquoted realm: `realm=`
  is kept and the clause after it is judged, so a quoted word there is hidden
  to its closing quote (`realm=<hidden>`) and a secret word opening it starts
  its own clause (`realm="password <hidden>`). Inside a kept realm no secret
  word is read, in prose, after `:` or after `=`: `realm="password <value>"`,
  `realm="password: <value>"` and `realm="password=<value>"` show the value.
  Only the last rule below reaches inside a kept realm, so a run of 20 or more
  token characters there that mixes letters and digits is hidden, and an
  unquoted realm of that shape longer than 256 characters is hidden whole
  (`Basic <hidden><hidden>`).
- **A secret word** (`auth`, `token`, `password`, `passwd`, `secret`, `key`,
  `credential` or `cookie`, in any case, inside a longer key too) hides the
  value after it, by how the value is stated. After `=` or `:`, up to two
  linking words before it allowed, the value is an assignment and is hidden
  whatever it is: a value another rule already hid, or a scheme name with
  its `realm=` parameter, is kept, and the rest of the value is still hidden
  (`auth=<hidden> <value>` reads `auth=<hidden>`). It runs to the end of the
  line or to the next `name=` after
  a space, through any quote, comma, `;` or `name:` inside it, because a
  passphrase has spaces and any of those can sit in one; a `name=` after `; `
  or `, ` is a cookie's next pair and is hidden with it, and a quoted value is
  hidden at least to its closing quote. After whitespace or any mark
  (`password,`, `password's`, `[token]:`, `(password)`, `password/`, a dash)
  the secret word is prose. The clause after it runs to the end of its
  sentence or of the line. A sentence ends at `!`, `?` or a period, with any
  closing quote or bracket, when the next word opens with a capital or the
  line ends; a period after a single letter (`e.g.`, `i.e.`, `a.m.`) and a
  word of marks alone end none. The clause is read word by word against a closed
  vocabulary in `scripts/audit_dependencies_data.py`: `LINKING_WORDS`
  (`is`, `was`, `set`, `to`, `for`, `the`, `not`, ...) and `CAUSE_WORDS`
  (`required`, `expired`, `invalid`, `incorrect`, `missing`, `denied`,
  `self-signed`, `forbidden`, ...), each cause word mapped to the npm or
  Node.js message it was read from, which holds it (the unit test checks
  that). The cause words include the HTTP
  methods `GET`, `HEAD`, `POST`, `PUT`, `PATCH` and `DELETE`, because
  npm-registry-fetch writes an HTTP error as `status statusText - METHOD uri`
  and the secret word `auth` inside `Unauthorized` opens a clause there, so
  `401 Unauthorized - POST <url>` keeps its method. A word in the vocabulary, matched
  without case and without the punctuation around it, is kept, so
  `password required`, `PASSWORD REQUIRED` and `the token is invalid` read
  as written. A word of three marks or fewer, such as npm-registry-fetch's
  ` - ` separator, is kept too, and so is a word that starts with a URL the
  first rule wrote. That word ends where the URL does: at a space, quote,
  `<` or `>`, or at a comma or semicolon right after its host and port, and
  up to three marks after it stay with it. So text glued before the URL, or
  after that comma or semicolon (`https://host:8080,<value>`), is a word of
  its own and is judged as any word is. The URL's host is kept only when it
  is a named host: a dotted name whose last label is letters, an IPv4
  address or a bracketed IPv6 address. Any other host there, a single label
  such as `localhost` included, is `<hidden>`, so `password https://<value>`
  reads `password https://<hidden>`.
  Every other word is hidden, a run of them as one `<hidden>`, so
  `the password was set to <value>` and `the password for bob is <value>`
  show neither name nor value. A quoted word is a value whatever it says and
  is hidden to its closing quote, and another secret word, `Bearer` or
  `Basic` starts its own clause. A `<hidden>` another rule wrote is kept and
  the clause goes on after it, so `password <hidden> and <value>` shows no
  value. The clause judges at most `CLAUSE_WORDS` (16) words one at a time,
  three more than npm's longest such clause, and hides the rest of a longer
  sentence whole. A quoted value with no closing quote, which is what the cut
  leaves when it lands inside one, is hidden from its quote to the end of the
  line. The costs:
  - A cause word the vocabulary lacks is hidden, so a new npm message after a
    secret word reads less well until its word is added.
  - A password that is a vocabulary word is shown.
  - A secret of three marks or fewer is shown.
  - A value written as the `realm=` parameter right after `Bearer` or
    `Basic` is shown, as the registry's realm is.
  - A value written as a URL's named host after a secret word
    (`password https://<value>.example`) is shown, and a single-label
    registry host after one (`token for http://localhost:4873/`) is hidden.
  - A value that opens with a capital after a real sentence end is read as
    the next sentence and is shown.
  - A value joined by `-`, `.`, `_` or nothing to a key word (`auth`,
    `token`, `password`, `passwd`, `secret`, `key`, `credential`, `cookie`,
    `Bearer`, `Basic` or `Authorization`), as in `password-<value>` and
    `Bearer<value>`, reads as part of the key's name and is shown, unless the
    last rule hides the joined run.
  - A secret word inside a longer word (`monkey`, `Unauthorized`, `Basically`) opens a
    clause, so the words after it are hidden unless the vocabulary holds them.
  - Cause text after an assignment on the same line is hidden with its value.

  The next step is chosen from the raw text, so the advice is the same either
  way.
- **A scheme-less userinfo**, `user:pass@` or a bare `user@` before a
  host as the next bullet defines one, a bracketed IPv6 host included
  (`<value>@[::1]:4873/x`), loses everything before its last `@`.
- **A host with no scheme**, as a `.npmrc` key or a fetch line writes one,
  loses its path as a URL does. It is a dotted name whose last label is
  letters, an IPv4 address, a bracketed IPv6 address with its zone id if it
  has one, or any name with a port, at the start of a word or
  after `//` or a userinfo's `@`. A file path whose first part has no dot,
  such as `src/frontend/astro/package-lock.json`, and a host with nothing
  after its `/` are kept.
- **Last, any remaining run of 20 or more token characters** that mixes
  letters and digits is `<hidden>`: that catches a bare token of any shape,
  and it also hides an integrity hash or a timestamped log name, a cost the
  script takes to fail closed. A URL's scheme, one of npm's, and its port
  stay.

A host is judged as one run where one sits: a URL's host with any `+`, `=` or
`%`-escape in it, the host a scheme-less path was hidden after, and the
operand after `ENOTFOUND` or `getaddrinfo` up to a space, quote, comma,
semicolon, `<` or `>`, since a token split at a symbol has pieces too short
for the last rule. The host stays whole when it is a DNS name, two or more
dot-separated labels with at most one trailing dot, or one label, where every
label is letters, digits and hyphens, is no UUID (npm's legacy token shape),
and whose parts that are no word, joined by their hyphens and taken
together, are no run this rule would hide. A word part is two or more
letters, one outside a to f, so a fragment of a hex token is no word; a word
excuses only itself, so a token behind or between word parts, such as a
vendor's token prefix and then random characters cut by hyphens, is
`<hidden>` with the whole host. One run shape
is a name's and stays: one word and then digits and hyphens only, which turns
from letters to digits once, where a random token's characters turn many
times. So `my-domain-111122223333.d.codeartifact.invalid` stays through its
word parts, `acme2024-111122223333.d.codeartifact.invalid` and a dotless
`nexus3` or `artifactory2` stay as a word and then a number, and a mixed run
that turns back to letters, opens with digits or opens with one letter is
`<hidden>`. The cost of that line: a secret that is a word and then a long
number is shown when it stands as a host; in prose the last rule still hides
it. A bracketed address stays, but a zone id longer than 15 characters once a
leading `%25` escape is dropped, which no Linux interface name can be, is
`%<hidden>`, whatever its length, and the host before it stays; no other
`%`-escape is decoded, so a raw `%A1A1...` is judged as written. `%eth0`
stays. Any other host that mixes letters and digits is
`<hidden>` whole; one that mixes in no digit, such as `localhost`, stays.

The next step follows the cause: npm's `ERR_INVALID_URL` or `Invalid URL`,
which it writes before any request when the registry setting is no URL, says
to check the registry URL in `.npmrc` or npm config is a full `http://` or
`https://` URL; else a 401 or 403 status, `E401`, `E403` or "authenticate"
says to check the registry credentials in `.npmrc` (values not shown); else
`ENOTFOUND`, `ECONNREFUSED` or `ETIMEDOUT` says to check the registry is
reachable.
npm runs with `--include=dev --include=optional --include=peer`, which npm
lets win over a user or project `.npmrc` `omit=`; an `.npmrc` can still change
the registry it asks, and the audit trusts that registry's answer. It writes
nothing in the tree; npm writes its own per-user log and cache.

**Cost.** One registry request per app, seconds each. The script is not in the
catalogue table above, and `make check-all` does not run it, because it reads
the network. `tests/unit/scripts/test_audit_dependencies.py` judges saved
reports through `--report NAME=FILE` and never runs npm.

**Run.** `make fe-audit` · `python3 scripts/audit_dependencies.py src/frontend/astro --report astro=audit.json` · `pytest tests/unit/scripts/test_audit_dependencies.py`

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
| `secret-scan` | `python3 scripts/scan_secrets.py --staged-or-history`, running the recorded scanner over the index the commit would carry, or over every commit when `pre-commit run --all-files` stages nothing; pre-commit skips it when a commit adds or changes no file (section 15), and it is exit 11 until `make secrets-install` has run |

Enable once: `pip install -e ".[dev]" && pre-commit install`, then `make secrets-install`.

### CI (event trigger)

`.github/workflows/ci.yml` runs under the Python and the Node major
config/project.json `toolchain.python` and `toolchain.node_major` name, which
its `toolchain` step prints for setup-python and setup-node (section 14):

```yaml
- run: make secrets-install   # build the pinned secret scanner and record it
- run: make secret-scan       # every commit the full-history checkout carries
- run: make check-all   # structure, python floor, corpus, openapi, aad, cdmon
- run: make lint
- run: make typecheck
- run: make test
- run: make trace       # every requirement is named by a test or a documented gap
- run: make eval        # replay every eval suite; no network, no credential
```

### Scheduled (time trigger)

The nightly job is the deterministic documentation review: the cadence lives
in `ops/scheduled/` (cron/systemd) and `.github/workflows/scheduled.yml` (CI),
each calling `scripts/jobs/review_docs.py --json` and keeping the report — the
*doer* in `scripts/jobs/`, the *schedule* in `ops/` (CONVENTIONS §7). A
schedule runs the doer, never the doc-review agent: a nightly judgment has no
one to read it, while a nightly list of stale stamps and dangling mentions
does.

## The gate's evidence record

`make verify` leaves one file saying what it judged: which gate ran, on which
commit, with what result. Something outside the repository, such as
project-jarvis, can read that file instead of scraping a log. The verify
recipe runs `scripts/gate_evidence.py`, which runs each goal (`check-all`,
`secret-scan`, `lint`, `typecheck`, `test`, `trace`, `eval`, `test-fe`, `test-sh`) as its own make, in order. The writer then
writes the record to `<evidence.dir>/<gate>.json`: `.evidence/verify.json`,
with config/project.json `evidence.dir` = `.evidence`.

**What it holds.** `config/evidence/gate-record.schema.json` (config/project.json
`evidence.schema`) defines every field and describes each one, and
`tests/integration/test_gate_evidence_record.py` validates a real record against
it.

| Field | What it says |
|-------|--------------|
| `schema`, `schema_version` | The schema the record follows, and its version. The schema's `schema_version.const` is the version's only owner. |
| `gate` | The gate's name, as `--gate` gave it. |
| `result`, `reasons` | `pass` exactly when the writer exits 0. A `fail` lists its reasons from a closed vocabulary: `target-failed`, `zero-targets`, `no-test-report`, `zero-tests`, `tests-failed`, `tree-changed`, `checks-unavailable`, `incomplete`, `writer-error`. |
| `source` | `commit` (HEAD's sha), `dirty` (git listed any path before the goals ran), `tree_digest` (a sha256 over what git listed, each path's status and content, from `scripts/git_tree.py`), and `tree_changed` (what git lists differed after the goals). |
| `targets` | Each goal in run order, with `result` (`pass`, `fail` or `not-run`), its `returncode` and its test counts. |
| `tests` | `passed`, `failed`, `skipped` and `errors`, summed from pytest's own junit report, each test case counted once. A goal that writes no junit report, such as `trace`, `eval` or `test-fe`, adds no counts: its exit code alone sets its `result`. |
| `checks` | Every `scripts/check_structure.py` check letter, and each project check that reported, with its sorted errors and warnings, the repository root stripped from each message. |

**Why it is ignored.** The record is one tree's verdict, derived on every
run, so it never belongs in a commit. `.gitignore` names `.evidence`. The
writer runs `git check-ignore` before any goal, and refuses with exit 2 a
record path that git would list. So `make verify` keeps its `[local]` label:
`scripts/run_make_target.py` still sees an unchanged tree.

**Where it may write.** Before the ignore check the writer passes the record,
its temporary file and each goal's junit report to `scripts/git_tree.py`
`through_symlink`, and refuses with exit 2 a path that resolves through a
symlink. The config check and the ignore rule both judge the path as text,
and a symlink leads where neither looked. Where git is not installed, or no
repository holds the project, nothing can be dirtied and the writer skips the
ignore check. A git command that ran and failed is not that case: the writer
refuses with exit 2 and quotes git's status and stderr.
`scripts/git_tree.py` tells the two apart: `NoGitError` for the first,
`GitFailedError` for the second.

**One date per run.** The writer reads the clock once, before the first goal,
and hands that date to every goal in `KEEL_GATE_RUN_DATE`, the variable
config/project.json `evidence.run_date.env` names. `scripts/jobs/review_docs.py`
`resolve_today` reads it after `--today` and `SOURCE_DATE_EPOCH` and before
the clock, so a goal that starts after midnight still judges a touched
document by the day the run began. `scripts/run_date.py` checks the value on
every read: it must be a calendar date written `YYYY-MM-DD`, no later than the
clock and at most `evidence.run_date.max_age_days` (`1`) days before it. A
value that fails is refused with exit 2 and is never replaced by the clock.
The date is not written to the record, which still holds no clock.
`tests/integration/test_doc_freshness.py` runs the judge on the day after the
run began, with and without the variable
([ADR-K-0019](../adr/keel/K-0019-one-date-per-gate-run.md)).

**Why it is derived and canonical.** Every byte comes from:

- the commit and what git lists
- each goal's exit code
- pytest's junit report
- the checks

The record holds no clock, duration, host, user or absolute path. It is
written whole, as sorted-key JSON with a two-space indent and one trailing
newline, through a rename. So two runs on the same tree with the same outcome
write identical bytes. `tests/integration/test_gate_evidence_record.py` runs a
real gate twice and compares them.

**How it gets red.** The writer never makes the gate greener.

- **A failing goal.** Its exit code passes through, and the goals after it are
  `not-run` unless make runs with `-k`.
- **Evidence missing although every goal passed.** These make the record red
  and the writer exit `RED_RECORD` (10, by the exit-code table in
  `docs/guides/limits-and-troubleshooting.md`):
  - zero tests ran (an all-skipped suite counts as zero)
  - pytest's report counts a failed or errored test although its goal
    exited 0 (under `make -i`, or a test recipe that ignores pytest's exit)
  - pytest wrote no report
  - the tree changed during the run
  - the checks could not run
  - the writer itself crashed
- **An interrupted run.** A red placeholder (`incomplete`) is written before
  the first goal, so an interrupted run never leaves an earlier green record
  standing.

An unknown value is `null`, never `0`. Outside git, `commit`, `dirty` and
`tree_digest` are null, and the goals alone decide the result. Under
`make -n` the writer passes the dry run to each goal and writes nothing.

**What it is not.** It keeps no history: each run replaces the file whole, and
the ledger across runs and repositories is a consumer's, such as
project-jarvis, which ingests the record
(`docs/adr/keel/K-0017-gate-evidence-record.md`). It is unsigned and sits in a writable directory, so it is evidence, not
attestation (`docs/guides/limits-and-troubleshooting.md`). CI runs `secrets-install`,
`secret-scan`, `check-all`, `lint`, `typecheck`, `test`, `trace`, `eval`,
`test-fe` and `test-sh` as separate steps (`.github/workflows/ci.yml`), so CI writes no
record.

**How a consumer reads it.**

- **Refuse a `schema_version` you do not know.** The format changed.
- **Refuse a null `commit`.** The record cannot be tied to a commit.
- **Refuse a record whose `dirty` is true.** It judged uncommitted files. Its
  `tree_digest` names that tree, but no commit holds it.
- **Match `source.commit` to the commit you are asking about.** A record from
  another commit says nothing about yours.

`docs/adr/keel/K-0017-gate-evidence-record.md` records why the record is built
this way.

## Adding a new deterministic check

A generated project that wants one more structure rule writes a module in its
`structure.project_checks` directory (section 1 above), not an edit to
`scripts/check_structure.py`. That file is the template's, and `copier update`
merges a project's edit to it, which leaves conflict markers when both sides
changed the same lines. The steps below are for the template itself, or for a
new script with its own make target.

1. Write the doer in `scripts/` (or `scripts/jobs/` for unattended jobs).
   Stdlib-only + 3.6-safe if it must run in pre-commit; otherwise it may use
   the project interpreter and **skip gracefully** when a dependency is absent.
2. Give it `--help` and a `--check` mode if it guards a committed artifact.
3. Add a `make` target and, if it should gate commits, a `.pre-commit-config.yaml`
   hook and/or a CI step. New projects generated with `copier` get the file
   automatically (copier ships the real `scripts/` tree — see
   [ADR-K-0004](../adr/keel/K-0004-project-templating-copier.md)).
4. Document it in this file.
5. If the check reads a new setting (a JSON key, an environment variable, a
   make variable or a command-line flag), add its row to
   `docs/reference/settings.md` in the same change;
   `tests/integration/test_reference_drift.py` fails until the row exists.
6. Add the check's row, and its make target's row, with their limits to
   `docs/reference/features.md` in the same change; the same test fails until
   both exist.

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
copy twice: before the update and after it. The project's own checks
(`structure.project_checks`) never run, because they are DEST's code; the
not-checked section names them. The freshness judge
(`scripts/jobs/review_docs.py`) and the restamp writer's `pending` list
(`scripts/jobs/restamp_docs.py`) run on DEST itself. Each freshness finding
carries `resolved_by`, because the update's last `_migrations` step runs
`restamp_docs` and clears it; the `pending` list names the stamps that
migration will rewrite. When the update stops before that step (below), both
name `make restamp-docs` instead, to run once the conflicts are resolved.

**The predicted tree.** The tree after the update is copier's own merge, so
the audit merges nothing itself. The update's `_migrations` include
`scripts/jobs/resolve_stamp_conflicts.py`, which settles a conflict that is
only a document's `updated:` stamp, so a path that conflicted on its stamp
alone is not in this group. A path copier leaves conflicted (`git
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
  symlink in this checkout;
- a migration that refused, and every migration after it (below).

**A migration that refuses over the update's own conflicts.** Every keel
`after` migration first runs `scripts/jobs/conflict_guard.py`, which stops it,
exit 2, when a module it imports, or a fixed project file one of those modules
declares reading in `PROJECT_READS`, holds a conflict hunk, and names the job,
each file and line, and the command to rerun: under an update, the command
that finishes it. `tests/integration/test_copier_job_conflict_refusal.py`
holds those declarations complete: every path literal a job's modules name
that the template ships is declared or exempted with a reason, and an open
trace of each job finds no read the declarations miss. copier stops at the first
failed migration, so the update exits non-zero. The audit reads that line
back (`conflict_guard.read_refusals`). When the update's stderr holds exactly
one refusal and every file it names is one the update left unmerged (`git
ls-files -u`), the real update of DEST will stop the same way: the audit
judges the tree copier leaves, adds a not-checked item `migration <job> and
every migration after it` with the files and the rerun (a finish command
reads `python scripts/jobs/finish_update.py`, whatever interpreter copier
ran it under), and exits on its findings. The migrations never reached are read from the snapshot's
`copier.yml` `_migrations`, in order; when the restamp is among them, or the
list cannot be read, the freshness and restamp groups name `make
restamp-docs`. A refusal over a file the update did not conflict (markers
DEST committed itself), more than one refusal, or any other failure is still
exit 2. Update with `--conflict inline`, as the audit does: under `--conflict
rej` copier writes no markers and leaves no unmerged path, so the migrations
run over the unmerged edits sitting in `.rej` files and this prediction does
not describe that update.

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
  shown as `<scratch>`) other than a migration the real update stops at too,
  or a missing `template` extra. A migration stops the real update too when
  it refuses over files the update leaves conflicted, or when copier names it
  as the failed task (with `--finish-with`, which only a migration passes) and
  what it prints holds verbatim the message of a letter error the audit
  reports as owed (the
  first migration runs the project's `child_env`, so a project that lists
  `GIT_DIR` in `child_env.names` stops there). The audit names that
  migration under not checked with the command that finishes the update, and
  exits 0 or 1 on its findings.

DEST is a keel project when every one of these holds:
- it is a directory, and not this checkout;
- its `.copier-answers.yml` is a mapping whose keys are all strings, with
  non-empty `_src_path` and `_commit` strings;
- its `config/project.json` is a JSON object.

`--json` prints the same report as canonical JSON, so two runs over the same
DEST on the same day are byte-identical: the scratch git's commit dates and
`SOURCE_DATE_EPOCH` are midnight UTC of the day the audit calls today.
