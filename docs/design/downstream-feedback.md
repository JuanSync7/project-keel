---
title: Downstream feedback — what the first generated project found wrong with keel
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The bounded-convergence record for the defects bedrock-platform, the first real project generated from keel, reported back — a red gate on arrival, unknown directories the gate never sees, make targets whose effect nobody declares, and child processes that inherit every credential — plus the command that checks any keel-generated project for all of them. One slice per defect, five passes, each landed as one commit on a green `make verify`.
id: docs-design-downstream-feedback
created: 2026-10-06
updated: 2026-10-06
visibility: internal
canonical: true
---

# Downstream feedback — what the first generated project found wrong with keel

bedrock-platform was generated from keel at `7f0a68b` and reported five defects.
Each was reproduced in keel before it was accepted. This document is the worklist:
the status table is authoritative, the per-slice notes record the measurement and
the decision.

## Status

| Slice | Defect | Status |
|-------|--------|--------|
| 1 | A generated project fails its own doc-freshness test on arrival | done — `make verify` green (776 passed); ADR-0010 proposed, awaiting acceptance |
| 2 | An unknown directory is invisible to the structure gate | done — `make verify` green (807 passed) |
| 3 | A make target's effect is declared nowhere, so a "check" can write | done — `make verify` green (987 passed); ADR-0011 proposed |
| 4 | Every child process inherits every credential in the environment | done — `make verify` green (1124 passed); ADR-0012 proposed |
| 5 | No command checks an existing keel project for slices 1–4 | done — `make verify` green (1178 passed); 7 of 8 review findings confirmed and fixed |

The cap is these five passes. A concern found mid-slice is queued at the end of
this document, not started.

## Ground rules

- Each slice lands as one commit, test-first, on a green `make verify`.
- A slice is not done until it holds downstream: it is exercised in a project
  generated from the working tree, not only in keel.
- No project fact is hardcoded in a check. A list a check consults lives in
  `config/` or is read from the document that owns it.
- Every writer a slice adds is declared to check_V and proven to reach its fixed
  point (`docs/guides/idempotency.md`).

## Slice 1 — freshness on arrival

**Measured.** Keel's 31 governed documents, committed once into a fresh
repository, are 31 of 31 stale under `tests/integration/test_doc_freshness.py`:
every `updated:` is a literal from keel's history, and the arrival commit is newer.

**Not only arrival.** The same failure recurs on every `copier update` that brings
a document in: the upstream stamp is older than the commit that lands it.

**Decision.** `updated:` means touched *in this repository*, so a document that
arrives from the template is touched on the day it arrives. A restamping doer sets
`updated:` to today on every governed document that is new or modified in the
working tree and leaves every other byte alone, so a second run is a no-op. Copier
runs it after copy and after update, and the project can run it by hand. The
freshness rule itself is not weakened.

**Built.** The writer is `scripts/jobs/restamp_docs.py` (`make restamp-docs`),
recorded in `docs/adr/0010-generation-needs-trust-to-stamp-docs.md`. Its cost is
that `copier copy` now needs `--trust`. A project generated from the working
tree measured 112 of 112 governed documents stale before the writer and 0 after.
The tests are `tests/unit/scripts/test_restamp_docs.py`,
`tests/integration/test_doc_restamp.py`, and the arrival and update cases in
`tests/integration/test_copier_generation.py` and
`tests/integration/test_copier_update.py`.

**Hardened.** A review found the copy task skipped two shapes: generating into a
repository with history (105 of 113 documents stale after the first commit) and
`copier update --conflict rej` (one `.rej` per document). The task now carries no
mode flag. The writer and the judge share one clock
(`review_docs.resolve_today`), the writer's target is never earlier than the last
commit, and both read changed paths with `git diff --relative`, so a project
below its repository's top is judged on its own documents. Each shape has a case
in the files above, and `tests/integration/test_copier_generator_contract.py`
holds every copier invocation of the writer to one argument list.

## Slice 2 — the directory taxonomy is closed

**Measured.** `check_B` labelled only directories named in its own `TAXONOMY`
list, so a `parked/` at the root passed with zero errors, in keel and in a
project generated from it. Keel tracks 81 directories, and 45 of them lack
`README.md` or `CLAUDE.md`. That count includes 6 hidden directories
(`.claude/**`, `.github/**`), which CONVENTIONS §5 puts outside the taxonomy.
Of the 75 non-hidden directories, 16 are top-level; all 16 are `TAXONOMY` rows
and all carry both labels. Of the 59 nested ones, 20 carry both labels (6 agent
directories, 4 under `api/`, 6 `src/` layers and stacks, `ops/scheduled`,
`scripts/hooks`, `scripts/jobs`, `demo/aad_reference_agent`). 10 carry
`README.md` only (5 `docs/` subfolders, `test-docs/test-plan`, 4 `tests/`
scenario directories), and 29 carry neither. The 39 that are not fully labelled
are 5 Python packages under `src/backend/` (check_C gates them as packages), 9
frontend source directories, 11 test directories, 8 `docs/` and `test-docs/`
subfolders, 5 config and data subfolders, and `scripts/agent_surface`. An
unlabelled `src/zzz/` passes only while it holds no `.py`; with Python and no
`__init__.py`, check_C already errors. A generation from a dirty keel tree
copies keel's untracked root symlink `project-keel` into the project, because
copier's dirty-HEAD clone runs `git add -A` on the work tree.

**Decision.** The top level is a closed vocabulary. A non-hidden root directory
is a CONVENTIONS §2 row or is declared by name in `config/project.json`
`structure.extra_toplevel`; anything else is an error naming both fixes. The key
is a plain list of names, because the declared directory's own `README.md`
`summary:` already says why it exists, and a second copy in the manifest would
drift. A declaration must exist (else stale), must not repeat a row (else
redundant), and must be a plain top-level name. The nested rule is every
directory directly under `agents/`: each `agents/<name>/`, which CONVENTIONS §13
already makes a "done when" condition, and the shared `agents/tools/` (§10),
which keel already labels; every other nested directory is free, and `AGENT.md`,
CONVENTIONS §2, `CONTRIBUTING.md`, `README.md` and the showcase copy now say
exactly that. An undeclared symlinked directory is a WARN, not an ERROR: no
check reads through a link, and `scripts/check_structure.py` cannot ask git whether the
link is tracked. An ERROR would turn keel's local gate red over the stray
symlink, and every generation from a dirty tree with it. The rule lands as an
ERROR rather than a one-release WARN under the
`docs/adr/0008-gated-module-contract-for-agent-interpretability.md` grace tier,
because keel complies at landing, which is the precedent checks P, Q, R, S and
V set. A downstream project with its own top-level directory goes red on
`copier update`, so the `CHANGELOG.md` upgrade note names the one-line fix.

**Built.** `scripts/check_structure.py` `check_B` with `_declared_toplevel` and
`_require_labels`; the empty `structure.extra_toplevel` key in both
`config/project.json` and its twin; CONVENTIONS §2 ("The taxonomy is closed"),
§6 and §15; `AGENT.md`, `CONTRIBUTING.md`, both `README.md` twins,
`src/backend/showcase/_data.py`, `docs/guides/deterministic-checks.md` and
`CHANGELOG.md`. The tests are `tests/unit/scripts/test_check_b.py` (25 cases:
22 red before the change, 3 guards green) and
`test_an_undeclared_top_level_directory_reds_a_generated_project_until_declared_and_labelled`
in `tests/integration/test_copier_generation.py`. That test failed against the
old `check_B` (a generated project with `parked/` reported 0 errors) and passes
against the new one. Nine mutations of the new `check_B` each turned at least
one unit test red. Keel's own gate reports 0 errors and one WARN, for
`project-keel/`.

## Slice 3 — every make target declares its effect

**Measured.** `scripts/run_make_target.py` validated a target's spelling, not its
effect, and said so. bedrock-platform added effect labels (its
`docs/adr/0010-areas-and-effect-labels.md`) and labels `fmt` and `site-data`
`[local]`, the same as `check`, so the gap it closed for remote writes stays
open for the tree. Run over a read-only copy of bedrock-platform's `Makefile` and
`mk/`, with `area_dir` `mk` and `write_shapes` `-apply`, `-drill`, `-destroy`,
`check_W` reads 81 labelled targets (51 `[local]`, 12 `[read]`, 11 `[write]`,
7 `[cost]`) and reports 2 errors and 0 warnings. Both are one target:
`doc-review-apply`, inherited from keel, is named like a write (`-apply`) but
labelled `[cost]`, and so lacks `$(WRITE_GUARD)`. Its four areas pass the
header, prefix and include rules. Three of its `[local]` targets, `fmt`, `fe-install`
and `agent-surface-schema`, rewrite the tree, which keel labels `tree`; no
static check can see that, and only the runtime sweep would. In keel, `make site-static` in a generated react-vite
project, run through the new runner under the old astro-only `.gitignore`, was
green and changed 12 paths under `src/frontend/react-vite/public/`; under the
new `.gitignore` it changes none.

**Decision.** Port the labels, the `$(WRITE_GUARD)` refusal under CI and Ralph
loops and the labelled `make help` as check_W, letter-compatible with
bedrock-platform's, and split the read-only targets from the ones that rewrite
the tree with a fifth word, `tree`. The gate runner refuses a target whose
closed label is outside `make_targets.gate_effects` and fails a read-only one
that dirtied the tree. A composite's label must cover what its prerequisites
reach, so the runner and the check close labels the same way
(`check_structure.target_effects`). The policy is data in `config/project.json`
`make_targets`, so a project names its own unattended variables, write shapes
and area directory. The ADR is `docs/adr/0011-make-target-effect-labels.md`,
status proposed; its number is the next free one in keel and collides with
nothing in bedrock-platform today, which the queued number-space item still
owns.

**Built.** `scripts/check_structure.py` `check_W` with `parse_effect_labels`,
`make_targets_policy`, `target_effects` and `walk_makefiles`;
`scripts/make_help.py` and the labelled `help` recipe; `scripts/run_make_target.py`
rewritten as the read-only gate runner, and `scripts/apply_refactor.py` gating
through it; the `make_targets` block in `config/project.json` and its twin;
`$(WRITE_GUARD)` and a label on every one of keel's 37 annotated targets (32
`[local]`, 5 carrying `tree`); both `.gitignore` twins; the practice
`make-target-declares-its-effect`; CONVENTIONS §6, §7, §15 and §17, `AGENT.md`,
and the guides, tool specs and rosters that describe the runner. The tests are
`tests/unit/scripts/test_check_w.py`, `test_make_help.py`,
`test_run_make_target.py` and `test_apply_refactor.py`,
`tests/integration/test_write_guard.py`, `test_make_target_effects.py` and
`test_a_generated_project_gates_only_on_targets_that_leave_its_tree_alone` in
`test_copier_generation.py`. Before the change 113 of them failed and 2 errored
at collection; three mutations (the runner's dirty-tree verdict, check_W's
cover rule, the guard's `exit 1` rule) each turned at least one test red. The
runtime sweep runs 24 `[local]` targets, including `doc-review`, and skips 8 by
reason.

**Review.** An independent review found eleven defects, each reproduced by a
second agent, and each is fixed test-first with a mutation that turns its test
red. check_W accepted `-$(WRITE_GUARD)`, which make ignores (`Error 1
(ignored)`, rc 0, the recipe ran under `CI=1`), and a `-` at the head of the
guard's definition; both are errors now. A target annotated `[local]` on one
rule and `[write]` on another kept only the first label, so the gate runner ran
it; check_W and `target_effects` now refuse a target with two different labels.
The guard's definition was read with its make `#` comment, so `@true # $(CI)
$(RALPH) exit 1` passed; the comment is cut off first. The names the guard
tests are now checked against `make_targets.unattended_vars` in both directions,
and ADR-0011 records the two copies as a deliberate departure from "define once".
The gate runner accepted any `NAME=VALUE`: `PY=make deploy-apply RALPH= CI= ;
true` ran a `[write]` target through a `[local]` one, and `MAKEFILES=` or
`WRITE_GUARD=` reached make. It now accepts only the new
`make_targets.gate_vars` (keel: `PY`), never make's control variables, the
guard or an unattended variable, with a one-word path-like value. Its snapshot
dropped the porcelain status, so `git add` in a `[local]` target passed, and
read a worktree rename (` R`) as garbage paths; it now keys on status and
content and reads the source in either column. `tests/integration/test_write_guard.py`
went red whenever the suite ran under the runner, because make hands `RALPH=1`
to children through `MAKEFLAGS`; its make calls now drop the inherited make
variables, and a test runs its attended cases through the runner. The CHANGELOG
now tells a project to re-audit its `[local]` labels, and CONVENTIONS §7, the
CHANGELOG and the ADR say a label is one bracket of one or more words.

## Slice 4 — child processes get an allowlisted environment

**Measured.** No spawn in keel passed `env=`. check_X, run over the tree before
conversion, reports 11 spawn calls in 10 modules: the model adapter
`models/claude_code_headless.py`, the four agent brains' `_run`,
`mcp/action_server.py`, `scripts/run_make_target.py` (make and git),
`scripts/jobs/review_docs.py`, `scripts/jobs/restamp_docs.py` and
`scripts/cdmon_sync.py`. The model adapter handed the `claude` CLI every
variable in the parent's environment, cloud credentials included. On Slurm job
3302705, `env -i PATH=$PATH HOME=$HOME make PY=.venv/bin/python test` gave 987
passed in 14m15s, and lint, typecheck, check-openapi, check-aad, check-cdmon and
check-docs were green with only `PATH` and `HOME`; so `make verify` alone
justifies two names, and every other name in `child_env` carries a non-verify
reason in the block's `_comment`. make 4.2.1 carries command-line variables to
a child in `MAKEFLAGS`, and an agent calls the gate runner without
`--make-arg`, so an allowlist that drops `MAKEFLAGS` also drops the `PY` and
`RALPH` a caller chose. A child started with only `PATH` read a variable planted
in its parent from `/proc/$PPID/environ` on the development host, where
`kernel.yama.ptrace_scope` is 0.

**Decision.** One helper, `build_child_env` in `scripts/child_env.py`, builds a
child's environment from an empty dict and the names `config/project.json`
declares: `child_env.names` and `child_env.prefixes`, the
`make_targets.unattended_vars` and `make_targets.gate_vars`, and, for a model
adapter, its `models.credential_env` entry. A missing or malformed manifest is
an error, never a fall-back to the parent's environment. check_X holds every
spawn under the code roots to the helper, with no waiver. The gate runner
forwards a gate variable it finds in its environment onto make's command line
under the `--make-arg` rule. It is defence-in-depth, not a sandbox; the ADR is
`docs/adr/0012-child-process-environment-allowlist.md`, status proposed.

**Built.** `scripts/child_env.py` (stdlib-only, legal on the 3.6 hook
interpreter); `check_X` and `spawn_findings` in `scripts/check_structure.py`;
the `child_env` block and `models.credential_env` in `config/project.json` and
its twin; `env=build_child_env(...)` at all 11 spawn calls; gate-variable
forwarding in `scripts/run_make_target.py`; the practice
`child-gets-an-allowlisted-environment`; CONVENTIONS §6, §7, §8 and §15,
`AGENT.md`, `scripts/AGENT.md`, `models/AGENT.md`, the guides, tool specs and
rosters that name the A–X check range. The tests are
`tests/unit/scripts/test_child_env.py`, `test_check_x.py`, the new cases in
`test_run_make_target.py` and `tests/unit/models/test_claude_code_headless.py`,
`tests/integration/test_child_process_environment.py`, the sibling-import and
old-interpreter cases in `tests/integration/test_gate_scope.py`, and
`test_a_generated_project_starts_children_only_through_the_allowlist` in
`test_copier_generation.py`. Before the change 67 of them failed and one test
module errored at collection. Seven mutations each turned at least one test
red: the helper copying all of `os.environ`, check_X skipping a spawn without
`env=`, dropping the gate variables, dropping the unattended variables, the
runner ignoring `PY` in its environment, `main` not calling check_X (the
generated-project test), and a `from __future__ import annotations` in the
helper (the old-interpreter test). The README's recipe for deleting `models/`
now also clears `models.credential_env`, because a credential declaration for an
adapter that is not in `models.available` is an error;
`test_deleting_a_manifest_declared_dir_is_caught_and_the_documented_fix_works`
follows the recipe as written.

## Slice 5 — audit an existing keel project

**Measured.** On git 2.43.5, `git diff HEAD`, plain `git status` and
`git describe --dirty` each rewrite `.git/index` when a stat refresh is due, and
`GIT_OPTIONAL_LOCKS=0` does not stop `diff` doing it; `--no-optional-locks status`,
`ls-files`, `log` and `rev-parse` leave the index alone. Before this slice,
`review_docs` and `restamp_docs --check` listed modified files with
`git diff HEAD`, so a read-only freshness check wrote into the project it judged.
A dry run of slices 1–4's checks over bedrock-platform, before the config merge
was built, gave B 1 error, F 6 warnings, V 9 warnings, W 1 error and X 18 errors.

**Decision.** `make audit-project DEST=<path>`, backed by
`scripts/audit_project.py`, runs every check_structure letter in-process over
DEST's files and reports what DEST would fail once `copier update` lands; it
writes nothing in DEST and runs none of DEST's code, make targets or hooks.
The stakeholder is a project owner deciding whether to update. The alternatives
were `copier update --pretend`, which lists files and runs no gate, and a trial
update in a scratch clone followed by `make verify`, which has full fidelity but
runs the project's code. The verdict: the audit is the pre-flight, and the trial
update is the confirmation. The audit is keel-only: `copier.yml` `_exclude`
keeps it out of a generated project, whose `make audit-project` stub exits 2
and names the template checkout recorded in `_src_path`. The stub guard runs
before the `DEST` usage guard, so a generated project gets the pointer even
without `DEST`.

Each JSON config the checks read is replaced in memory by a key-level 3-way
merge with copier's replay semantics: base is the template at DEST's `_commit`,
ours is DEST, theirs is this checkout, and base and theirs are rendered from the
`.jinja` twin with DEST's answers. A key the template dropped and the project
never edited is removed, as copier's replay removes it. Without a resolvable
`_commit` the merge falls back to 2-way and reports arrivals only. Every finding
carries an origin evidence kind read from git at `_commit`: `template-rendered`
when the template ships a `.jinja` twin (checked first, because copier renders
the twin and never copies its plain sibling), `template-unedited` or
`template-edited` by byte comparison, `project` for a path the template does not
ship, and `unknown` otherwise, including a file that cannot be read. A letter
error in a `template-unedited` file is reported as resolved by the update,
because the update replaces that file; every other letter error is owed. The
exit code is 1 when a letter error is owed or no file was seen, 2 on a usage
error, a refusal (malformed answers included), a render error (answers of the
wrong type included) or a missing extra, and 0 otherwise. Its "not checked" section names every proof it
does not run. `CONVENTIONS.md`, `AGENT.md` and `config/practices.json` need no
change: the audit adds no rule, only a way to run the existing ones elsewhere.

**Built.** `scripts/audit_project.py`; `--root PATH` and
`run_checks(root, config_overrides)` in `scripts/check_structure.py`;
`modified_paths` in `scripts/jobs/review_docs.py` (`status` plus `ls-files`)
and `git_argv`, which builds every git call of the audit and both doc jobs with
`--no-optional-locks` and fsmonitor, signature verification and each configured
filter driver switched off, used by `scripts/jobs/restamp_docs.py`, whose `pending`
the audit reads; the `audit-project` target and stub in the `Makefile`, with its
`make_targets.effect_proof_skip` entry in `config/project.json` and its twin;
the `_exclude` entries in `copier.yml`; `scripts/README.md.jinja`, so a
generated project's roster does not list the audit; the `--root` row in
`agents/tools/structure_check.tool.md`; and the read-only rule for doers in
`docs/guides/idempotency.md`. The tests are
`tests/unit/scripts/test_audit_project.py` (31 cases),
`tests/unit/scripts/test_check_structure_root.py`, the index cases in
`test_review_docs.py` and `test_restamp_docs.py`, and
`tests/integration/test_copier_audit.py`, which generates a fresh project, plants
one defect each for B, W and X plus a stale doc, audits it twice and proves the
tree, the index and the porcelain status unchanged, then audits a project
generated at `7f0a68b`. Each test failed before its code existed, the origin
test against the plain-path-first order it replaced. Sixteen unit mutations,
among them a merge that element-merges lists and a freshness finding counted
toward the exit code, each turned a test red; in the integration suite an audit
that runs `git diff HEAD` in DEST failed tree equality, and a dropped X plant
failed the group set. An adversarial review then confirmed seven findings, and
each fix has a test that failed first: errors the update resolves were counted
as owed; a clean filter, a long-running process filter and a `showSignature`
gpg program configured in DEST ran during the audit; an unreadable file crashed
origin and the restamp list (`restamp_docs` now names it and exits 1); a
non-string answer key or a wrongly typed answer gave a traceback; the
stub printed a relative `DEST`; and the `--root` documentation said the configs
are this checkout's. Ten further mutations (group sort, the unreadable-file
reset, the override copy, the zero-files exit, the `-` commit guard, the
resolved label, the owed count, the unreadable-origin catch, the answer-type
catch and the key check) each turned a test red.

**Bedrock result.** Against bedrock-platform (`_commit` v0.1.0-14-g7f0a68b, which
resolves to `7f0a68b`) the audit exits 1 with 26 letter errors and 17 warnings
over 507 files; after the review fixes, rerun on the replica, 9 of those errors
are resolved by the update and 17 are owed: B 1 error (`mk/`, origin project), W 6 errors (4 project, 1
template-edited, 1 template-rendered), X 19 errors (9 project, 1 template-edited,
9 template-unedited), F 6 warnings (unknown), V 10 warnings (project), and
config 4 arrivals (`structure`, `make_targets`, `child_env`,
`models.credential_env`) plus 1 `config/practices.json` conflict warning. The V
and X counts are one higher than the dry run because bedrock-platform changed in
between. One W error is the template's own `effect_proof_skip` entry for
`audit-project`, which the old Makefile does not define (queued below). Under
strace, `make audit-project` made 329 write-capable calls, all to `/dev/null` or
the terminal, and none under bedrock-platform's real path. Another session was
editing bedrock-platform at the time, so the tree proof ran on a `cp -a` replica:
the tree hash, the index mtime and the porcelain status were equal before and
after, and two JSON runs were byte-identical. On the same replica, `git diff
HEAD` moved the index mtime, so the proof can fail.

## Queued

Found during the slices and deliberately not started:

- **ADR numbers collide downstream.** Keel's ADR-0010 and bedrock-platform's own
  ADR-0010 share a number, so `copier update` would bring keel's in beside it.
  Template ADRs and project ADRs need separate number spaces; slice 3's ADR
  must not deepen the collision.
- **`review_docs` path forms in a nested repository.** Porcelain paths and
  `ls-files` paths can disagree when the project is below its repository's top.
- **`_SKIP_DIRS` and the `_git` helper are duplicated** between
  `review_docs.py` and `restamp_docs.py`.
- **`make new ALLOW_DIRTY=1` copies untracked files** from a dirty template,
  including a stray symlink at the root.
- **The copier 9.3.0 floor is unverified** for `_tasks` with `_copier_python`.
- **`FE_APPS` order is the filesystem's.** `make site-static` writes into
  `$(firstword $(FE_APPS))`, and `$(wildcard)` does not promise an order, so a
  project that keeps two frontend stacks can snapshot into either. Sort it.
- **react-vite ships no lockfile**, so `make fe-install` there is not
  reproducible, and the sweep cannot prove `lint-fe` or `typecheck-fe` against
  installed dependencies in that stack.
- **`make run` needs `PYTHONPATH`** to find `src/` outside the test harness;
  the sweep skips it as a server, so nothing exercises the composition root's
  import path.
- **`make smoke` exits 5** because it selects no tests today, so the sweep skips
  it by reason instead of proving it.
- **ADR numbers.** Slice 3's ADR took keel's next free number, 0011; the queued
  number-space item above still decides how template and project ADRs coexist.
- **`api/grpc/Makefile` is outside the walk.** `check_W` and `check_P` follow
  `include` from the root `Makefile`, so a transport's own makefile, run with
  `make -C`, carries no labels and no guard check.
- **An untagged template skips `_migrations`**, including the update restamp.
- **Nothing pins `TAXONOMY` to the CONVENTIONS §2 table.** The list in
  `scripts/check_structure.py` and the table are kept in step by hand, and since
  slice 2 a drift between them is an error source. A parity check or test should
  read one from the other.
- **make can ignore errors outside a recipe line's prefix.** A `.IGNORE:` special
  target, or `-i` in a `MAKEFLAGS` set in the environment rather than through
  the gate runner, makes make carry on past `$(WRITE_GUARD)`'s `exit 1`. check_W
  reads neither; a `.IGNORE` that covers a `[write]` target should be an error.
- **A gate variable still names a program.** `make_targets.gate_vars` keeps
  make's control surface out of a gate run, but `PY=` chooses the interpreter a
  recipe runs; the tree snapshot is the only backstop for what that program does
  outside the tree.
- **Keel's copier `_exclude` names a root `tmp/`.** Under the closed taxonomy
  a scratch directory at the root cannot be declared (stale while absent) or left
  undeclared (error while present); scratch belongs in a dot-directory.
- **A declared extra directory is outside `CODE_ROOTS`.** Python in it is not
  read by check_D, E, O or V, by lint or by typecheck.
- **A `TAXONOMY` directory that is itself a symlink** passes check_B through the
  link while every walking check skips its contents.
- **Gitignored tool output at the root** (`site/`, `logs/`, `out/`) not in
  `IGNORE_DIRS` now reds a local `make check`; the gate cannot read
  `.gitignore` semantics without git.
- **`models/config/default.example.toml` has no consumer.** No adapter reads it,
  so it cannot be the home of an adapter's credential names; they live in
  `config/project.json` `models.credential_env`.
- **ADR-0005 overlaps `child_env`.** Its proposed `config/environment.json`
  records environment variables; if it is built, its records can subsume
  `child_env.names` and the two lists must not drift.
- **check_X does not see a spawn through an unresolvable receiver**
  (`self.runner(...)`, `loop.subprocess_exec`, `sp = subprocess; sp.run`),
  nor a parent-environment value that reaches the helper across a function
  parameter. It under-reports, never over-reports.
- **`src/` cannot import `scripts.child_env`**, so the first spawn site under
  `src/` must move the helper there first, keeping it 3.6-safe for the hook
  interpreter.
- **A proxy URL can embed credentials** (`https://user:pass@proxy`); the proxy
  names are allowlisted, so such a value still reaches every child.
- **`BASH_FUNC_*` and `PYTHONPATH` are not passed.** Environment Modules export
  shell functions that way; a caller that needs one passes it with `extra=`.
- **A child can read its parent's environment** from `/proc/$PPID/environ`
  while `kernel.yama.ptrace_scope` is 0; closing that is an OS-identity or
  container control, outside keel.
- **The generation and update suites cannot see a file that was never
  staged.** `tests/hermetic_git.py` `clone_including_worktree` replays
  `git diff HEAD`, which omits untracked files, so this slice's new
  `scripts/child_env.py` was absent from every clone and 24 tests failed on
  `ModuleNotFoundError: No module named 'child_env'`. `git add -N` on the new
  files fixed it. Slice 5 hit it again: the tracked `scripts/README.md` and
  `config/project.json` named the untracked `audit_project.py` and
  `scripts/README.md.jinja`, so check_structure failed in every clone (three
  update tests and the effect sweep), and `git add -N` fixed it again. The
  harness could refuse to run while a non-ignored file under the template is
  untracked, so the failure names its cause. The same
  `git diff HEAD` rewrites keel's own `.git/index` on every run (slice 5's
  measurement); `review_docs.modified_paths` is the read-only replacement.
- **check_N caps its report at five lines** with `[:5]` and says nothing about
  the rest; the audit names the cap, but the check should print the count.
- **The audit judges `config/practices.json` and the `Makefile` before the
  merge.** Only JSON configs are merged; a template-shipped file is read as the
  project has it, so an old project's Makefile reads the template's new
  `effect_proof_skip` entry for `audit-project` as stale (bedrock-platform's one
  `template-rendered` W error). Origin is per file, so this mixed view (a
  rendered manifest against a `template-unedited` Makefile) is owed, and it is
  the one owed error a pristine `7f0a68b` project still reports.
- **A filtered file with stale stat data reads as modified.** The audit and the
  doc jobs switch off DEST's filter drivers, so git compares such a file (an LFS
  pointer, say) raw.
- **The audit cannot see a spawn in a shell script**, because check_X reads
  Python with ast.
- **`make audit-project` has no tool card** in `agents/tools/`; add one if an
  agent should run it.
- **Origin cannot see a path the base `_exclude`d.** A project file at a path the
  template carries but excluded reads as `template-edited`, not `project`.
- **`child_env.names` passes `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE`**,
  so a git child of a process started with them set acts on that repository,
  not on its own working directory.
- **A restamped doc reads as `template-edited`** after the update's migration,
  so origin overstates the project's edits there.

## Campaign result

Slices 1–4 landed as `3bc2f8a`, `860b9e4`, `6cea98a` and `094dbca`, each on a
green `make verify`. Slice 5 adds `make audit-project DEST=` on a green
`make verify` (1178 passed).
ADR-0010, ADR-0011 and ADR-0012 are proposed and await acceptance. Everything
found along the way and not fixed is in Queued above.
