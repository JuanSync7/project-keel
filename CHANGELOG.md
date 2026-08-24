# Changelog

All notable changes. Format: Keep a Changelog.

Generated projects record the template ref they came from in
`.copier-answers.yml` (tracked, not ignored — see 0.1.0). Generate a **named**
version rather than a bare commit:
`copier copy --vcs-ref v0.1.0 gh:JuanSync7/project-keel my-project`.

## [Unreleased]

### Added
- **`docs/guides/python-style.md`** — the canonical "how Python is written
  here": readability and loud failure modes outrank speed; docstrings say what,
  comments say why (a reason or a measurement, never a restatement); the
  absent-vs-broken split; how a code agent works in this repo; and the same
  contract scaled from a one-off EDA script to a full product. Linked from
  `AGENT.md`'s Always rules and registered doc-tier in `config/practices.json`
  (`readability-over-speed`, `absent-vs-broken`). Ships verbatim, so every
  generated project inherits it.
- **The machine-readable module contract is gated** (ADR-0008). Every code-root
  module must carry explicit `title:`/`summary:` docstring lines — the corpus's
  input grammar, pinned to `build_corpus` by a parity test (new `check_O`);
  `check_E` (exported symbols have docstrings) is promoted WARN → ERROR at zero
  findings. `build_corpus` now imports its walk scope from `check_structure`
  instead of re-typing it — the private copy had omitted `runtimes/`, leaving
  six modules invisible to every corpus query. And `make check-corpus` now gates
  the **local** `wiki/corpus.json` agents actually query: absent is a loud pass,
  stale is an error naming `make site-data`, with staleness judged on the
  deterministic projection so `index_enforcer`'s `"generated"` enrichment never
  reads as rot (measured before the fix: 33 nodes behind the tree at a green
  gate). Five modules gained explicit headers, including `check_structure.py`
  itself.
- **Formatting is now gated.** `make lint` runs a new `make fmt-check`
  (`ruff format --check`) over the same `CODE_ROOTS` the linter and `make fmt`
  use, so CI reports layout drift instead of leaving it to review. Declared as
  the `consistent-formatting` practice in `config/practices.json`; the scope is
  imported from `check_structure.CODE_ROOTS` by
  `tests/integration/test_gate_scope.py` rather than re-typed, and a companion
  test proves the corpus is clean, not merely that the recipe exists.

### Changed
- The whole Python corpus is `ruff format`-clean (109 files reformatted in one
  behaviour-neutral commit). `make fmt` had shipped from the start but nothing
  required it to have been run, so the tree had drifted while the gate stayed
  green. The formatter keeps its **defaults**: the point of this tier is that
  layout stops being a judgment call. It reflows code only, so the deliberate
  `E501` deferral for long docstring summaries is untouched.

### Fixed
- **Declining the showcase shipped a test that asserted on the routes it had just
  deleted.** `tests/e2e/test_showcase_journey.py` was in neither prune list, so a
  project generated with `showcase=false` carried it and failed its own CI on day
  one (measured: 2 failed — the walk hits `/api/overview`, `/api/features`, …,
  which no longer exist). It survived because the guard test —
  `test_declining_the_showcase_prunes_the_whole_surface_and_leaves_a_green_gate` —
  asserted "green gate" through `check_structure` alone, which reads layout and
  never executes anything. It now runs the generated project's **whole suite**
  (~4s, measured), so a prune list is only as honest as the run that follows it.
  The retirement-pairing test was tightened in the same pass: it checked that some
  migration names the pruned path, not that it does so under the *same condition* —
  a path retired on the wrong answer reads as a pairing and behaves as none.
- **`_min_copier_version` is `9.3.0`, not `9.1.0`.** The `command:`/`when:`
  `_migrations` form this release adds landed in copier 9.3.0 ("add simpler
  migrations configuration syntax", #1510). Measured in 9.2.0's own source rather
  than assumed: its `migration_tasks` does `parse(migration["version"])` with no
  guard, so an entry carrying `command:` instead of `version:` is a bare
  `KeyError` mid-update — exactly the unhandled traceback this floor exists to
  turn into copier's own clear message. Second time this line has been wrong for
  the same reason, so `_FEATURE_FLOORS` now carries both features and the floor
  each one needs.
- Keel's own hardening plan (`docs/design/keel-hardening-plan.md`) no longer ships
  into generated projects. It is this repo's in-flight worklist — passes,
  measurements, deferrals, `status: draft` — and verbatim it arrived as a new
  project's design document describing work its authors never did. Pruned as a
  single file, with a mirroring migration; `docs/design/README.md` stays, because
  it is the labeled placeholder a project writes its own design notes into.
- Reformatting orphaned three suppression pragmas — one `# noqa: PERF401` in
  `scripts/check_practices.py` and two `# type: ignore[arg-type]` in
  `scripts/apply_refactor.py` — by moving them off the lines whose diagnostics
  they silenced. All re-anchored (the `apply_refactor` pair by joining once into
  a named local, so the pragma cannot drift off its expression again). Worth
  knowing generally: `RUF100` is deferred here and `scripts/` is outside
  `[tool.mypy] files`, so an orphaned pragma is not flagged by itself — the
  ignores were dead and the real errors unsuppressed, waiting for the day the
  declared mypy ratchet pulls `scripts` in.
- A `wiki/corpus.json` that exists but **cannot be read** — bad permissions, a
  directory, a dangling symlink — escaped `make check-corpus` as a raw
  `OSError` traceback, because only `ValueError` was caught. That is the
  absent-vs-broken split this check exists to hold, so both reads now go
  through one `_load_corpus` helper that reports present-but-broken on the
  designed ERROR path. Its twin: `--corpus` mode ran the staleness projection
  without the shape guard the gate branch got, so a `null`, a list, or
  `{"nodes": 5}` printed the correct error and *then* died with an
  `AttributeError`.
- A UTF-8-BOM markdown file was silently dropped from the corpus: read as plain
  utf-8 the BOM survives into the string, `_parse_frontmatter` never sees a
  leading `---`, and the doc simply is not there. The `.py` readers moved to
  `utf-8-sig` in the ADR-0008 pass; the markdown ones had not, re-opening the
  drop class for the node kind that dominates the graph. (`utf-8-sig` is
  byte-identical for BOM-less files; the corpus **writer** stays `utf-8`.)
- `test_lint_gates_formatting_over_every_code_root` was the one `make`-invoking
  test in `tests/integration/test_gate_scope.py` without the
  `skipif(shutil.which("make") is None)` guard its siblings carry, so on a host
  without `make` it raised `FileNotFoundError` instead of skipping.
- `docs/guides/deterministic-checks.md` still described check E as "warn until
  ADR-0008", which reads as *currently* warn. It is an error.
- `_min_copier_version` is `9.1.0`, not `9`. `multiselect:` questions landed in
  copier 9.1.0, so 9.0.1 passed the declared gate and *then* died on
  `Could not convert [] to string` — the mystery error the gate exists to
  pre-empt. A floor that admits a copier which crashes is worse than no floor,
  because the user is told the version was checked. Pinned to the features
  `copier.yml` actually uses by a contract test.
- A generated project starts **its own** `CHANGELOG.md` (new `.jinja` divergence
  twin) instead of inheriting keel's release history — previously a new project
  shipped with a dated `[0.1.0]` it never released, describing keel's internals
  as if they were its changes. The twin keeps the attribution and the
  `.copier-answers.yml` provenance note.
- `test_generated_project_commits_its_copier_answers` is hermetic against the
  developer's machine. `git add -A` honours global excludes, and git reads
  `~/.config/git/ignore` with no config entry at all — so a single `*.yml` line
  there failed the tracked-answers assertion on someone else's laptop.
- `copier.yml`'s note on how twins render was wrong (and predates these passes):
  the plain file is *not* copied-then-overwritten. For any path with a
  `<name>.jinja` sibling copier's `_render_path` returns early, so the plain twin
  is never copied and walk order is irrelevant.
- `make new` now hands copier an **absolute** template path. Copier records that
  argument verbatim as `_src_path`, so the old literal `.` was re-resolved against
  the *generated project* on `copier update` — copier cloned the project as if it
  were the template and git died with `pathspec '<keel sha>' did not match any
  file(s) known to git`, a raw traceback with no diagnostic.
- `make new` also refuses a **dirty** keel tree (`ALLOW_DIRTY=1` overrides): from a
  dirty template copier records a WIP commit that exists only in its throwaway
  clone, so the generated project could never resolve `_commit` either.
- CI installs the optional `template` extra (`.[dev,template]`) and declares it
  required via `KEEL_REQUIRE_TEMPLATE=1`. The copier tests `importorskip`ped, so
  keel's own generation gates had **never run in CI**; a missing copier is now a
  hard collection error there, while a bare local clone still skips gracefully.
  CI also checks out full history (`fetch-depth: 0`) so a `--vcs-ref v0.1.0` pin
  can resolve — a depth-1 checkout carries no tags.
- Generated projects no longer ship keel's template **meta-tests**
  (`tests/integration/test_copier_*.py`). They assert on `copier.yml` and the
  `.jinja` twins, which a generated project does not have, and `ci.yml` ships
  verbatim — so with the extra now installed they would have turned every
  descendant's CI red.
- **`make verify` gated 2 of the repo's 9 Python roots.** `Makefile:72` linted
  `src tests` and `pyproject.toml:79` typed `files = ["src"]`, while
  `scripts/check_structure.py:74` already declared all nine in `CODE_ROOTS` —
  three unreconciled scope lists. Outside the gated two sat 6,571 Python lines
  (58% of the repo's Python) and **101 ruff errors**, among them a `B904` at
  `runtimes/langgraph_adapter.py:158` that breaks keel's own *gate-tier*
  `exception-chaining` practice: `ruff check --select B904 runtimes` reports it
  while `ruff check src tests` said *All checks passed!*. An agent told "let the
  gate decide done" was being lied to across most of the repo. `lint-py`/`fmt`
  now use `$(wildcard $(CODE_ROOTS))` — the wildcard because ruff exits 1 with
  `E902 No such file or directory` on a root copier pruned downstream — and
  `typecheck-py` passes mypy **no paths at all**, since an explicit path argument
  overrides `[tool.mypy] files` and would have made widening the config inert.
  Ruff is now clean over all nine roots: of the 101, 41 T201 entrypoint prints
  became declared per-file ignores, 55 were fixed in code, 5 carry a reasoned
  inline `# noqa`.
- mypy checked 19 files and now checks 36: `files = ["src"]` →
  `["src", "models", "demo", "agents"]`, with `explicit_package_bases` and
  `mypy_path` (without the first mypy does not start at all) and per-module
  overrides that relax only measured flags — never `strict = false`. Full strict
  over all nine roots is 1,411 errors, so the remaining roots are declared, with
  a measured cost and a removal condition each, in `config/practices.json`
  `rulesets.mypy.ratchet`; a test fails if a code root is in neither place, so a
  root can no longer be silently unmentioned.
- `make lint-fe` / `make typecheck-fe` printed *"npm not found; skipping"* and
  then hard-failed anyway: each recipe **line** is its own shell, so the guard's
  `|| exit 0` ended only the guard, and make ran the loop on the next line into
  `npm: command not found` (measured on the old Makefile with an empty PATH:
  exit 2 at `Makefile:75`). The Makefile ships verbatim, so every generated
  project's `make lint` broke on any host without node. Guard and loop are one
  logical line now, and `FE_APPS` is tested first so a `frontend_stack: none`
  project is silent rather than told about npm.
- `scripts/cdmon_sync.py` could not be **parsed** by the interpreter its own
  pre-commit hook runs it with. `language: system` hooks exec the committing
  shell's ambient `python3` (3.6.8 here), where line 8's
  `from __future__ import annotations` is `SyntaxError: future feature
  annotations is not defined` — the flagship external-tool adapter aborted the
  commit instead of skipping gracefully. Deleting that line alone is not enough:
  the evaluated `list[str] | None` annotation then raises `TypeError` at def
  time. Both are gone; `/usr/bin/python3 scripts/cdmon_sync.py --check` exits 0.
- The gate's config readers could not tell **absent** from **unreadable**. A
  present-but-malformed `config/practices.json` turned check_K, check_L and
  check_M — the meta-gate whose whole job is proving `pyproject.toml` cannot
  silently loosen the declared lint/type policy — into no-ops while
  `check_structure.py` still printed `0 error(s)` and exited 0 (reproduced at
  `fca1ae5`). One shared reader pair makes the split once: absent stays silent
  (copier legitimately prunes files), unreadable is reported once and exits 1.
  All 16 blind `except Exception:` clauses in `check_structure.py` are gone — 8
  deleted with the readers they guarded, 8 narrowed to two named exception
  tuples.
- `scripts/agent_surface/generate_aad_schema.py --check` reported success on a
  broken model: `except Exception: return 0` was meant as a graceful skip for an
  old interpreter or absent pydantic, but it also swallowed every real failure,
  so the AAD drift guard was green while verifying nothing. Only `ImportError`
  and `SyntaxError` — the two ways the *environment* cannot run the check — still
  skip; anything else means the check ran and the model is broken, and now fails
  in both modes.
- `pyproject.toml.jinja` had drifted from `pyproject.toml`, and a generated
  project's pyproject comes **entirely** from the twin (`_render_path` returns
  early for any path with a `.jinja` sibling). Since `Makefile` ships verbatim,
  widening one side and not the other handed every descendant a gate red on
  arrival — measured in a freshly generated project: **40 T201 errors, exit 1** —
  plus a mypy scope narrower than keel's own (19 files against 36) and therefore
  silently green, re-opening downstream the exact blind spot this pass closes.
  The twin was regenerated from `pyproject.toml` and is now text-pinned to it.
- `api/rest_fastapi/showcase_api.py`'s `/api/wiki/node` handler bound its query
  parameter to the builtin name `id` (ruff `A002`). Renamed to `node_id` with
  `alias="id"`, so the published wire name is unchanged: `export_openapi.py
  --check` still says *openapi.json up to date* and the committed contract is
  byte-identical.

- **`copier update` can never retire a file, so `_exclude` is a generation-time
  filter only.** copier renders the old template copy with the UNION of the old and
  new excludes, deliberately, "to prevent deletion" (`copier/_main.py`). Two
  consequences were measured. A project generated before the meta-test prune keeps
  those tests forever, while `copier update` *does* deliver the newer `ci.yml` that
  installs the `template` extra and sets `KEEL_REQUIRE_TEMPLATE=1` — so the update
  meant to fix CI is what turns an older descendant red (6 of 8 failed). And changing
  an answer (`--data frontend_stack=astro` on a react-vite project) leaves the old
  stack on disk while the answers file says otherwise: that project's own gate then
  reports 13 errors. The meta-tests now neutralise themselves wherever no `copier.yml`
  exists, pinned end to end by generating a project, copying them back in, and running
  them the way CI does. The answer-change half needs `_migrations` and is the
  redesign of pass 4 (see the plan); `_exclude` cannot fix it.
- `.github/workflows/pages.yml` shipped verbatim while hardcoding
  `src/frontend/astro` — the stack `_exclude` prunes under the **default** answer. The
  first push to `main` of a default-generated project failed its `pages` build on
  `npm ci` (`EUSAGE ... can only install with an existing package-lock.json`). Exactly
  the class pass 2 fixed for `ci.yml`, left standing in the sibling workflow; it is now
  answer-pruned too. Two more shipped surfaces named the same directory: `make run-web`
  (advertised in the generated README's quickstart) died with ENOENT, and
  `scripts/jobs/export_showcase_static.py` defaulted its output there — **creating** it,
  so `make site-static` silently resurrected a stack the user had declined. Both now
  discover the frontend instead of naming it. A new test scans every shipped
  Makefile/workflow/script of a generated project for a pruned frontend path, so the
  next hardcode fails at the source rather than in someone's CI.
- `make new` passed copier no `--vcs-ref`, and copier resolves `self.ref or
  get_latest_tag(...)` — the newest **tag**, not HEAD. Harmless only while keel has no
  tags: the moment `v0.1.0` is cut, `make new` silently generates from the tag, so a
  maintainer smoke-testing a template change gets a project without it (reproduced on a
  minimal tagged template: the generated file held the tag's content, and the post-tag
  commit was absent). `VCS_REF ?= HEAD` is now explicit and overridable. This also makes
  the dirty-tree refusal's stated reason true again rather than merely reworded —
  copier's dirty-include branch is gated on `ref == "HEAD"` (verified both ways).
- `make new` read a **non-git** template as clean: `git status --porcelain 2>/dev/null`
  prints nothing and discards rc=128 outside a repository, so a ZIP download or an
  `rsync --exclude=.git` copy generated happily and copier recorded no `_commit` at
  all — a project that looks fine and can never update. Now refused by its own check;
  `ALLOW_DIRTY` deliberately does not override it, because no amount of it makes a
  non-repo resolvable.
- `test_copier_update.py`'s hermetic git config omitted `core.excludesFile`, which git
  reads from `$XDG_CONFIG_HOME/git/ignore` as that key's DEFAULT — so the three
  `GIT_CONFIG_*` vars never reached it. A single `*.yml` line in a developer's global
  ignore produced a **false red** on a correct tree (measured: 1 failed, 6 passed, with
  the assertions about the feature under test all passing). Fixing it exposed a larger
  half: copier drives git through `plumbum`, which snapshots `os.environ` at import, so
  `monkeypatch.setenv` is inert for every git subprocess copier spawns. When keel's own
  tree is dirty copier stages the working tree with `git add -A`, and under that same
  ignore line the throwaway clone lost `copier.yml` itself — every `_exclude` and every
  answer silently stopped applying, and the generated project shipped keel's meta-tests
  (measured: control 0 shipped, hostile 3 shipped). Both modules now share one
  `tests/hermetic_git.py`, applied session-wide from `tests/conftest.py` before plumbum
  is imported. Verified under two hostile ignore patterns: 19 passed each.
- `test_copier_test_modules_hard_fail_when_the_extra_is_required` matched **itself** —
  it scanned for the literal `importorskip("copier")`, which is its own filter string —
  so its "did the guard move?" backstop could never fire. Deleting both real copier test
  modules left it green (`1 passed`); it now skips its own file and names the modules it
  requires (same mutation: `1 failed`).

- **check_M could be switched off through exactly the two mechanisms pass 3's
  carve-outs and ratchet use.** It read `tool.ruff.lint.extend-select` and
  `tool.mypy.<flag>` and nothing else, so (a) `config/practices.json`
  `rulesets.ruff.per_file_ignores` had **no consumer at all** — a single
  `"**/*.py" = ["B904", "BLE001"]` line silenced a family corpus-wide and the
  parity gate reported success — and (b) `[[tool.mypy.overrides]]` was invisible,
  because `_toml_targets` normalises every block to the one dotted key
  `tool.mypy.overrides.<flag>`, so the blocks aliased onto each other and only the
  last would have been read anyway. Both measured at zero findings, exit 0, before
  the fix; both now error. Per-module relaxations are legitimate — the type ratchet
  is built on them — so the rule is that they must be *declared*, per module, in
  `rulesets.mypy.overrides`. Relaxing a **component** of `strict`
  (`disallow_untyped_defs`, `warn_return_any`, …) rather than `strict` itself
  counts: mypy's `--strict` is exactly that set, and switching the pieces off is
  the same loosening spelled differently. What check_M reads is bounded, and the
  bound is stated where it is declared: the flags this ruleset declares, plus
  `strict`'s components, plus `ignore_errors`. `ignore_missing_imports`,
  `disable_error_code` and `follow_imports` are outside it — import and diagnostic
  scoping rather than strictness — and stay a review matter.
- **`copier update` could never retire what an answer declined, so re-answering a
  question broke the project's own gate.** `_exclude` is a *generation-time* filter:
  on update copier renders the old template copy with the **union** of the old and
  new excludes, on purpose ("to prevent deletion", `copier/_main.py`), so an excluded
  path is never removed — only never created. A project generated with `react-vite`
  that re-answered `astro` therefore kept the react-vite tree while
  `.copier-answers.yml` said otherwise, and its own `check_structure` reported
  **13 errors** (dangling `CLAUDE.md -> AGENT.md` symlinks plus an undeclared stack) —
  red through no act of its own, caused by the update we advertise. Every
  answer-driven prune now has a mirroring `_migrations` entry, and the *pairing* is
  asserted for the whole class, so a prune added later without its retirement fails
  here rather than downstream. See ADR-0006.
- **The template meta-tests are now retired on update, not just pruned at
  generation.** Pruning never helped a project generated *before* the prune existed;
  `copier update` was precisely what handed it the newer `ci.yml` that runs them. The
  self-neutralising skip stays as the belt to this braces, for a project that never
  updates.
- **`tests/integration/test_copier_update.py` tested a different tree than the one
  being edited.** Its fixtures cloned keel with `git clone`, which carries only HEAD,
  so an uncommitted `copier.yml` change was invisible to the template under test — a
  new `_migrations` block appeared to "silently do nothing" when it simply was not
  there. The clone now replays the working-tree diff as a real commit, so what you
  edit is what gets tested; on a clean tree it is exactly a plain clone.

- **The AAD schema-validation assertion had never executed anywhere.**
  `jsonschema` was in no extra and in no requirements file, so
  `test_descriptor_validates_against_committed_schema` `importorskip`ped on every
  machine and in CI — for its whole life — while the suite reported success. Its
  only visible trace was a `1 skipped` that read like the deliberate langgraph
  skip. `jsonschema` is now in the `dev` extra, and the assertion passes (checked
  by mutation that it also *bites*: a dropped `aad_version`, a non-string slug and
  a bogus transport protocol are each caught).
- **The same silent-skip hole, closed for the whole class.** `fastapi`, `httpx`
  and `copier` were all `importorskip`ped too — CI installs them, but nothing
  made a broken install *fail* rather than skip. The skip-or-fail decision now
  lives in one place (`tests/optional_deps.py`): CI declares the surfaces it
  installed via `KEEL_REQUIRED_EXTRAS`, a declared surface is a real import whose
  `ImportError` fails collection, and an undeclared one still skips so a bare
  local clone works. A `test_gate_scope.py` scan fails any test module that
  reaches for a raw `pytest.importorskip` outside the declared opt-in set
  (langgraph, which stays deliberately optional). Verified both directions with
  `jsonschema` blocked at import: undeclared → skip, declared → hard failure. A
  typo in the CI declaration (`tempalte`) is an error, not a silent no-op —
  otherwise the guard could be switched off by a slip in the one file that arms
  it. This replaces the per-extra `KEEL_REQUIRE_TEMPLATE` flag.
- **The README's own "delete what you don't need" advice reddened the gate.** It
  listed `models/` among the optional dirs, but `config/project.json` declares
  the adapters that live there, so following the instruction produced 3 errors
  and exit 1 on a project whose owner had done nothing wrong — the first thing a
  new user does is exactly what the README told them to. The advice now excludes
  `models/` and documents the manifest change that makes dropping it clean. Both
  halves are pinned by tests that read the sentence out of the *generated*
  project's README, so adding a directory to it is covered rather than trusted.

### Added
- **A `showcase` question.** The bundled demo — `src/backend/showcase`, its
  `/api/*` router, the static exporter, the `llms.txt` renderer, its tests and its
  guide — is **1,205 of a generated project's 1,433 Python lines (84%)** against a
  30-line `example_feature`, and until now there was no way to decline it.
  `showcase: false` prunes the whole surface at generation and retires it on
  `copier update --trust` (the pairing gate added with ADR-0006 forced the
  migration to exist). ADR-0007.
- What it does **not** take with it, measured rather than assumed: nothing under
  `api/rest_fastapi/aad/`, `mcp/`, `agents/` or `scripts/query_corpus.py` imports
  `backend.showcase` — they read `wiki/corpus.json`, which the showcase reads too
  but does not own, and which `mcp/qa_server.py` and three of the four bundled
  agents need. ADR-0004's claim that they were inseparable is superseded. A new
  gate fails any migration naming a path every project needs, so the tidy-looking
  over-reach cannot land later.
- `showcase: false` with `frontend_stack: astro` is **refused** with a message
  naming the working answers, not silently coerced. The astro app *is* the
  showcase UI (all seven pages fetch `/api/*`, `pages.yml` builds it, and
  `make site-static` snapshots it through the exporter that answer prunes).
  react-vite is unaffected — it makes no API call at all.
- ADR-0007 (accepted): an optional showcase, and project identity from the
  manifest. Supersedes ADR-0004's "no-showcase mode is out of scope".

### Fixed
- **A generated project no longer serves the template's name.**
  `api/rest_fastapi/app.py` was `FastAPI(title="Project Keel API")` and the
  showcase overview hardcoded `title="project_keel"` — one line below a `name`
  field that was correctly tailored, which is why neither was noticed, and
  `make check-openapi` kept the wrong title *green* downstream. Both now derive
  from `config/project.json` via `backend.shared.display_title`, so a rename stays
  correct where a copier answer would have frozen at generation. Scanned as a
  class, not as the two known lines: the scan found six more (the showcase
  summary and setup steps, the exporter's `--base-url` example,
  `config/default.example.toml`, `config/practices.json`).
- **`api/rest_fastapi/openapi.json` no longer ships verbatim.** It names keel and
  lists the showcase routes, so `make check-all` was **red on arrival** in any
  project with a different name or without the showcase — through no act of the
  user's. It is now treated as the generated view it is (the rule
  `wiki/corpus.json` already followed), and `export_openapi.py --check`
  distinguishes *no contract published yet* (exit 0, printing how to publish one)
  from *the committed contract has drifted* (exit 1). Both branches are tested;
  keel's own title is unchanged, so self-parity holds.
- `make site-data` / `site-static` test for the showcase scripts before calling
  them. They ship verbatim and cannot be answer-aware any other way — the same
  shipped-verbatim class as the `pages.yml` hardcode fixed in pass 3.5.

### Changed
- `backend.showcase.SUMMARY` is now `SUMMARY_TEMPLATE` and carries a
  `{title}` placeholder the read model fills from the manifest. A deliberate
  public-API break: a constant that must be formatted should not be named as
  if it were finished text, and the old one hardcoded keel's name into every
  generated project's own overview page.
- **`copier update` now requires `--trust`** (`copier update --trust`). Retirement
  needs `_migrations`, migrations run commands, and copier refuses an unattended
  unsafe template rather than skipping them silently. Generation is unaffected —
  copier only counts migrations on update — so `make new` and `copier copy` still
  need no flag. Pinned by a test, not by prose. Note that changing an answer now
  **deletes** the directory it declined: commit first, and `git checkout -- <path>`
  recovers it (copier already refuses to update a dirty project, so the history
  always exists).

### Added
- ADR-0006 (accepted): retire declined answers with `_migrations`, amending
  ADR-0004's update consequences — including the `--trust` requirement and the
  rule that a migration must never name a path a project could have authored
  from scratch.
- **`check_N` — template twin parity**, the general gate that passes 1–3 kept
  adding one-off pytest pins in place of. `grep -rn 'jinja\|copier' scripts/*.py`
  used to return nothing: no structural check knew the six `.jinja` twins existed.
  Each is now declared in `config/project.json` `template.twins` with its kind —
  `parity`, `divergence` (`.gitignore.jinja` deliberately does NOT reproduce
  keel's file; it drops the `.copier-answers.yml` ignore so a descendant keeps its
  upgrade channel) or `generated`.
  **Render-free by necessity, which bounds the claim honestly:**
  `check_structure.py` is stdlib-only and 3.6-safe because it runs in pre-commit
  on old hosts, so it cannot import jinja2 and cannot byte-compare a rendered
  twin. What it does prove: no twin is undeclared (a seventh cannot appear
  unnoticed — the precondition ADR-0005 was told to wait for), no `parity` twin
  carries a non-templated line the plain file has lost, no `divergence` twin has
  quietly stopped diverging, and no `generated` twin has a committed plain file.
  The byte-exact rendered comparison stays in `tests/integration`, where jinja2
  exists. Verified by mutation: re-narrowing the twin's mypy scope (the exact
  pass-3 regression), copying `.gitignore` over its twin, and adding a seventh
  twin each produce an error, and all three were silent before.

- `tests/integration/test_copier_update.py` — the upgrade channel ADR-0004 chose
  copier for, tested for the first time: generate → commit downstream work →
  evolve the template → `copier update`, asserting new files arrive, edits land,
  downstream work survives, the `.gitignore` divergence twin holds, `_commit`
  advances, no conflicts are left, and the upgraded tree still passes its own gate.
- `tests/integration/test_copier_generator_contract.py` — pins the `make new`
  recipe and the CI wiring above so neither can silently regress.
- `tests/integration/test_gate_scope.py` (16 tests) — the gate's scope read off
  the real `make -n` expansions, the real `pyproject.toml` and the real
  `.pre-commit-config.yaml`: `lint-py`/`fmt` must cover every `CODE_ROOTS` entry
  (*imported* from `check_structure.py`, never re-typed, so the lists cannot
  drift), `typecheck-py` must pass no paths, mypy's scope and the declared
  ratchet must partition `CODE_ROOTS`, ruff must be clean over it, the FE gates
  must skip-not-fail without npm *and* still fail on a real frontend failure, and
  every bare-`python3` pre-commit entry must be legal at the documented 3.6
  floor. Verified to bite: narrowing the Makefile's `CODE_ROOTS` back to
  `src tests` turns two of them red.
- `tests/unit/scripts/test_config_loaders.py`, `tests/unit/scripts/test_generate_aad_schema.py`
  and `tests/unit/runtimes/test_langgraph_adapter.py` — the absent-vs-unreadable
  split (including that a JSON `null` manifest stays a *shape* error), the AAD
  drift guard failing on a broken model while still skipping on a broken
  environment, and the pause signal keeping its `__cause__` (removing the
  `raise ... from p` turns that one red again).
- Two tests in `tests/integration/test_copier_generation.py`: a freshly generated
  project must be lint-clean over the roots **its own** shipped `Makefile`
  declares, and `pyproject.toml.jinja` is pinned as text to `pyproject.toml`
  except the three per-answer fields. (General twin parity for all five twins is
  still pass 5 of the hardening plan.)

### Known limitation
- A project made with `make new` records the template's machine-local absolute
  path, so `copier update` works on that machine only. Generate from
  `gh:JuanSync7/project-keel` for a project you intend to share.

## [0.1.0] — 2026-08-04
First named version. Everything below existed before this tag; the tag exists so
a descendant can state which keel it came from and upgrade to a known-good ref
instead of a bare SHA (`docs/design/keel-hardening-plan.md`, pass 1).

### Fixed
- Generated projects now **track** their own `.copier-answers.yml`. Keel's
  `.gitignore` shipped verbatim and ignored it, so while `copier update` worked
  in the directory copier created, any `git clone`, teammate checkout or CI run
  had no answers file and update failed with "Cannot update because cannot
  obtain old template references". A `.gitignore.jinja` divergence twin drops
  that line downstream; keel keeps ignoring its own copy.
- `_min_copier_version: "9"` — an old copier now fails with copier's own message
  instead of a mystery render error.

### Added
- ADR-0005 (proposed): declare the external environment in
  `config/environment.json` — the parts a container cannot reach.
- `docs/design/keel-hardening-plan.md` — the bounded convergence plan.

## Template foundations (pre-0.1.0)
- Initial template.
- Deterministic-check suite: `jobs/check_corpus.py` (corpus integrity + build
  reproducibility), `check_structure.py` checks A–M (incl. CLAUDE.md↔AGENT.md
  symlinks and the coding-practice gates), and OpenAPI / AAD drift `--check`s.
  Unified via `make check-all`; catalogued in `docs/guides/deterministic-checks.md`;
  wired into pre-commit + CI.
- Project generation: a `copier` template (the repo root is the template) —
  one command runs an interactive Q&A into a tailored skeleton, and `copier
  update` pulls later template improvements. Replaced the hand-authored
  `scaffold.py` generator + its byte-synced embeds + `check_scaffold_sync`
  (parity-proven first; ADR 0004). The Q&A tailors the project name (→ manifest,
  `pyproject` slug, README title), minimum Python, frontend stack (un-chosen stacks
  pruned), add-on transports (`grpc`/`edge_nginx` pruned unless selected; REST+MCP
  are the always-shipped foundation), and domain practice profiles.
- Showcase demo: `backend.showcase` read model + thin REST router
  (`api/rest_fastapi/showcase_api.py`) + a minimalist Astro docs/wiki site
  (`src/frontend/astro`) that renders the template live from the backend.
  See `docs/guides/showcase-site.md`; run with `make run-api` + `make run-web`.
