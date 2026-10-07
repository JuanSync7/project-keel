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
updated: 2026-10-07
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
| 1 | A generated project fails its own doc-freshness test on arrival | done — `make verify` green (776 passed); ADR-0010 accepted |
| 2 | An unknown directory is invisible to the structure gate | done — `make verify` green (807 passed) |
| 3 | A make target's effect is declared nowhere, so a "check" can write | done — `make verify` green (987 passed); ADR-0011 accepted |
| 4 | Every child process inherits every credential in the environment | done — `make verify` green (1124 passed); ADR-0012 accepted |
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
recorded in `docs/adr/keel/K-0010-generation-needs-trust-to-stamp-docs.md`. Its cost is
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
`docs/adr/keel/K-0008-gated-module-contract-for-agent-interpretability.md` grace tier,
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
and area directory. The ADR is `docs/adr/keel/K-0011-make-target-effect-labels.md`,
status proposed. It took keel's next free number, which collided with
nothing in bedrock-platform then; slice C2-5 moved it into the template's own
number space as ADR-K-0011.

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
`docs/adr/keel/K-0012-child-process-environment-allowlist.md`, status proposed.

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
`run_checks(root, config_overrides)` in `scripts/check_structure.py` (slice
C2-3 removed `config_overrides`, which only the in-memory merge used);
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
  must not deepen the collision. Fixed by slice C2-5.
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
  Fixed by slice C2-5.
- **`api/grpc/Makefile` is outside the walk.** `check_W` and `check_P` follow
  `include` from the root `Makefile`, so a transport's own makefile, run with
  `make -C`, carries no labels and no guard check.
- **An untagged template skips `_migrations`**, including the update restamp.
  Slice C2-5 measured the opposite for an untagged `_commit` on copier 9.17:
  dunamai versions project-jarvis's `72fd224` `0.0.0.post17.dev0+72fd224`, and
  its update ran every migration.
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
  names are allowlisted, so such a value still reaches every child. Fixed by
  slice C2-2.
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
  the one owed error a pristine `7f0a68b` project still reports. Fixed by
  slice C2-3.
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
  not on its own working directory. Fixed by slice C2-1.
- **A restamped doc reads as `template-edited`** after the update's migration,
  so origin overstates the project's edits there.
- **`GIT_CONFIG`, `GIT_CONFIG_COUNT` and `GIT_CONFIG_PARAMETERS` reach a
  child.** Slice C2-1 left them out of `repo_context_names` because they carry
  configuration, not a repository. A hook still exports a `git -c` value
  through `GIT_CONFIG_PARAMETERS`, so a policy could refuse the three in
  `child_env.names` and hold them back by default.
- **A git or make run that does not start through `build_child_env` keeps the
  hook's repository.** copier runs git through plumbum with its own environment,
  and a hook can start `make` directly rather than through the gate runner.
  Slice C2-1 covers only processes started through the helper and the test
  suite.

## Campaign result

Slices 1–4 landed as `3bc2f8a`, `860b9e4`, `6cea98a` and `094dbca`, each on a
green `make verify`. Slice 5 adds `make audit-project DEST=` on a green
`make verify` (1178 passed).
ADR-0010, ADR-0011 and ADR-0012 were accepted on 2026-10-06. Everything
found along the way and not fixed is in Queued above.

## Campaign 2 — the ranked queue

The maintainer accepted ADR-0010, ADR-0011 and ADR-0012 on 2026-10-06 and asked
for the Queued list above to be worked in risk order before bedrock-platform's
next round of feedback. The cap is five slices, each one commit on a green
`make verify`. v0.2.0 is tagged after slice C2-1, because C2-1 closes a hole in
ADR-0012's own guarantee. A concern found mid-slice joins Queued.

| Slice | Defect | Status |
|-------|--------|--------|
| C2-1 | A child inherits `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`, so its git acts on the parent's repository | done — `make verify` green (1206 passed); 3 review findings confirmed and fixed |
| C2-2 | A proxy URL with embedded credentials reaches every child | done — `make verify` green (1288 passed); 8 of 9 review findings confirmed and fixed |
| C2-3 | The audit reads the `Makefile` and `config/practices.json` before the merge, so an old project reports a false W error | done — `make verify` green (1308 passed); 4 review findings confirmed and fixed |
| C2-4 | `make smoke` passes over zero tests, and `make run` fails with `No module named app` | planned |
| C2-5 | A downstream project's ADR numbers collide with the template's | done — `make verify` green (1356 passed); 6 of 7 review findings confirmed and fixed; ADR-K-0013 proposed, awaiting the maintainer |

### Slice C2-1 — a child does not inherit the parent's repository

**Measured.** git 2.43.5 exports repository-location variables to a hook. A
`pre-commit` hook in a plain checkout receives `GIT_INDEX_FILE` and
`GIT_PREFIX`; with `git commit <paths>` the index is an absolute
`.git/next-index-<pid>.lock`. The same hook in a linked worktree also receives
an absolute `GIT_DIR`. Four reproductions followed, each before the fix:

- `review_docs --strict`, started in another repository under a hook's
  `GIT_DIR`, judged "0 governed document(s), 0 stale" and exited 0. Without
  the variable it reported 1 stale document and exited 1.
- A gate that `scripts/run_make_target.py` ran in another checkout printed the
  hook repository's `.git` from `git rev-parse --absolute-git-dir`, and the
  runner reported PASS.
- `tests/hermetic_git.py` `clone_including_worktree`, called under a parent
  `GIT_DIR` and `GIT_INDEX_FILE`, wrote into the parent's index. Afterwards
  `git status` failed with "unable to read" and `git fsck` reported an invalid
  sha1 pointer in the index's cache-tree.
- A generated project's own `review_docs --strict` under the same variables
  judged 0 documents and exited 0.

**The list.** `child_env.repo_context_names` is `git rev-parse
--local-env-vars` minus `GIT_CONFIG`, `GIT_CONFIG_COUNT` and
`GIT_CONFIG_PARAMETERS`, plus `GIT_NAMESPACE` and `GIT_QUARANTINE_PATH`. The
three config names are left out because they carry configuration, such as a
`git -c` value, not a repository. The two additions bind a ref namespace and
a receive-time object directory to one repository. The names live in config
so that a later git release that adds a name is a manifest edit. The test
`test_keels_policy_holds_back_every_repository_variable_git_names` compares
the list with the installed git's own list.

**Keyword, not config.** `build_child_env` drops the names unless the call
passes `repo_context=True`, and the keyword must be a real `bool`. A config
switch would apply to every child in the project. Acting on the parent's
repository is a property of one call site, so the call site declares it.
`child_env_policy`, and so check_X, refuses any allowlist source that admits
a listed name: `child_env.names`, a `child_env.prefixes` entry,
`make_targets.unattended_vars`, `make_targets.gate_vars` and
`models.credential_env`. A missing `repo_context_names` is an error. An older
project's `make check` names that key until it takes the update, and the same
message says to move git's repository variables out of `child_env.names` and
lists the `GIT_`-prefixed names it holds, so one round of `make check` carries
the whole fix. The `GIT_` prefix only picks the names to show; the set that is
held back is still `repo_context_names`.

**The audit.** This slice made `scripts/audit_project.py` merge a list of
distinct strings that both sides edited item by item, as copier's line-level
merge leaves an allowlist; slice C2-3 replaced that merge with copier's own
update, which the audit now runs and reads. Before this slice the list was
atomic. A pre-C2-1 project that had
added its own `child_env.names` entry was then judged on its old list. The
audit reported an owed X error for `GIT_DIR` and predicted a copier conflict,
but the real `copier update` merged cleanly and `make check` was green.
`tests/integration/test_copier_audit.py` generates a project at `a70a7b5` and
checks that it owes no X error, with and without an added name.

**The suite.** `tests/hermetic_git.py` and copier run git without the helper.
For that reason `tests/conftest.py` strips the same names from `os.environ` at
import, before plumbum snapshots the environment, and `git_env` never carries
them.

**Residual risk.** The `GIT_CONFIG*` names still reach a child. copier's own
git, run through plumbum, and a make recipe that a hook starts directly do
not pass through `build_child_env`. Both are in Queued.

### Slice C2-2 — a credential in an allowlisted value does not reach a child

**Measured.** Before the fix, with `HTTPS_PROXY=http://u:<password>@127.0.0.1:9`
and `LC_X=https://tok@host` in the parent, `build_child_env` returned both
values verbatim, and a child running `echo $HTTPS_PROXY` printed the password.
`scripts/run_make_target.py` also quoted a refused gate variable with `%r`, so
a `PY` holding a password with a space in it was echoed in the refusal, and a
one-word one was put on make's command line before any check ran.

**The rule.** Whether a value carries user information depends on who reads
it, so `carries_credential(name, value)` in `scripts/child_env.py` applies
three readings, and a value any of them flags is a credential:

1. Every value: each URL authority in it, after `scheme://` or a leading `//`,
   up to the first `/`, `?` or `#` (RFC 3986 section 3.2). Whitespace does not
   end it, because `urllib.parse.urlsplit` keeps `u:p x@h` in the netloc. Any
   non-empty text before its last `@` counts, because a token rides there with
   no password.
2. Every value: a whole value that is a scheme-less `user[:password]@host:port`.
   The port separates it from ordinary values. A glibc `LANGUAGE` list
   (`sr_RS:sr@latin`), `USER`'s `name@domain` and `git@host:org/repo` never end
   in `@host:digits`.
3. A variable whose lower-cased name ends `_proxy`, which is how
   `urllib.request.getproxies_environment` picks the variables it reads as
   proxies: the user information urllib's `_parse_proxy` finds. That parser
   reads a scheme-less value as a whole authority, and a URL's authority up to
   the first `/` after its first `@`. So `#`, `?`, `/` or a space in a
   password, a scheme-less `token@proxy`, and even `http://h:8080/p?q=a@b`
   (user `h` on 3.11) all reach `Proxy-Authorization`. Each case was measured.

A scheme-less value outside a proxy name is not read as an address, so rule 3
is scoped to proxy names. The first cut judged every value as if it were a
proxy (`x:y@z`). That refused a Serbian-Latin or Valencian user's `LANGUAGE`
and stopped every child, while it passed `token@proxy:8080`, `//u:p@proxy` and
passwords containing `#`, `?`, `/` or a space. The independent review
reproduced all of these. The scan is linear: about 0.02 s on a 128 kB
adversarial value under 3.6.8. It anchors on the literal `://`, because a
pattern that matched the scheme took 0.40 s on a 20 kB value.

**Refuse, not strip or drop.** Stripping the user information would hand the
child a proxy that answers 407, and dropping the variable would send the child
around the proxy. Both fail later and far from the cause. `build_child_env`
raises one `ChildEnvError` that names every such variable, sorted, and never
quotes the value. The error carries no chained exception that could hold the
value.

**Config, not keyword.** C2-1's opt-in is a keyword because acting on the
parent's repository is one call site's decision. An authenticating proxy is a
property of the site, and every child crosses it, so the opt-in is
`config/project.json` `child_env.credentialed_values`: an optional object that
maps a copied variable to a non-empty reason. `child_env_policy`, and so
check_X, refuses an entry that is not a variable name, has no reason, or names
a variable no allowlist source copies (`drop the stale entry`).

**Exemptions.** A name in `credentialed_values` passes its value through. A
name in the called adapter's `models.credential_env` is not judged, because
that list already declares a credential for that child alone; it is not
exempt for any other call. A key the caller replaces through `extra=` is not
judged, because the parent's value never reaches the child.

**The runner.** `scripts/run_make_target.py` builds the child environment
before it forwards a gate variable. It judges every gate value, explicit or
forwarded, with `carries_credential`, and refuses one that carries a credential
even when `credentialed_values` opts it in, because make hands its command line
to every recipe through `MAKEFLAGS` and `ps` shows it. No refusal quotes a
value, so a credential in a form no rule recognises still never reaches a log.

**The audit.** `tests/integration/test_copier_audit.py` generates a project at
`29e45f0`, before this slice. The audit reports `child_env.credentialed_values`
as an `info` arrival with the template default `{}`, and the project owes no X
error.

**Residual risk.**
- A credential in another form is not detected: a bare token, an
  `Authorization` header value, or a `user:password@host` with no port outside
  a proxy name.
- `ssh://git@host` is refused although it carries a user name only.
- A proxy value with an `@` after its host (`http://h:8080/p?q=a@b`) is refused,
  although only urllib, not an RFC 3986 reader, would send it.
- The runner judges the environment against keel's own config, not the
  `--dir` project's.
- copier's git, and a make recipe a hook starts directly, still bypass the
  helper.
- A same-user child can still read `/proc/$PPID/environ`.

### Slice C2-3 — the audit judges the tree the update leaves

**Measured.** Before the fix, the audit merged the JSON configs in memory and
read every other file as it stood in DEST. On a project generated at `7f0a68b`
it reported 1 owed error and exit 1: config/project.json W, because the merged
`effect_proof_skip` names `audit-project` and the unmerged Makefile lacks that
target. A real `copier update` of the same project followed by
`check_structure.py` reports 0 errors. The old audit also marked 49 errors
resolved, because it marked every error in a template-unedited file resolved,
whether or not the update fixes it.

**The rule.** `scripts/audit_project.py` `predict` copies DEST into a
`keel-audit-*` temporary directory and runs copier's own update there, against a
clone of this checkout. It then runs `check_structure.run_checks` on the copy
twice: before the update and after it. A letter error in the after run is owed.
A letter error found only in the before run is `resolved_by` the update. A path
that `git ls-files -u` reports as unmerged in the copy goes to the `conflict`
group, and its findings carry `unjudged: conflict` and are not counted. The
after run then happens twice, with every conflict hunk the project's way and
the template's way (`resolve_conflict` reads copier's markers); a finding only
one of the two has is `unjudged: conflict` as well. The config group compares the
base render, DEST's JSON and the copy's JSON after the update (`classify`).
The audit merges nothing itself. After the fix, the same `7f0a68b` project
reports 0 owed, 12 resolved and 0 conflicts, with exit 0, in 30 s.
`test_predicted_findings_equal_check_structure_on_a_real_update` checks that
the predicted letter findings equal `check_structure.py` on a real update of an
independent clone. It covers projects from `7f0a68b`, `29e45f0`, and `a70a7b5`
both as rendered and with the project's own `child_env.names` entry.

**Decision: copier runs the project's restamp.** keel's copier.yml `_tasks`
and its last `_migrations` entry run `scripts/jobs/restamp_docs.py` from the
merged copy, so the audit runs code the project may have edited. The audit
accepts this. The parity test only means something with copier's real update,
and the project runs the same restamp on every update anyway. Containment is
the scratch copy with no DEST `.git`, `build_child_env`'s allowlisted
environment, a hermetic gitconfig with `core.hooksPath=/dev/null`, and a
check that no finding names the scratch root. The "not checked" list states
it.

**Decision: a conflict does not set the exit.** A conflict is reported and
counted in the text summary, but the exit code still means "a letter error is
owed", as before this slice. A failed `copier update` is exit 2 with copier's
last stderr lines and the scratch root masked as `<scratch>`. No partial report
is printed.

**Rehearsal on bedrock-platform.** A scratch clone at `_commit:
v0.1.0-14-g7f0a68b` audits as exit 2 in 28 s. The update conflicts on
`scripts/check_structure.py`, because the project added its own check W and the
template added a different one. copier's restamp task then imports the
conflicted module and stops on the conflict marker. A real `copier update` on
an independent clone fails the same way (exit 1, same task, in 25 s) and leaves
120 conflicted files, most of them `updated:` frontmatter lines. Two runs
printed byte-identical stderr. The clone's tree, `.git` and index mtime were
unchanged, and no `keel-audit-*` directory was left behind. Slice 5's count of
17 owed errors cannot be compared, because the update itself does not complete.

**Review fixes.** An independent review reproduced two defects, both fixed
test-first.
- The first build restored a conflicted file to DEST's bytes and left every
  other file as the update leaves it, which is the per-file mix this slice
  removes. The `7f0a68b` project with its own target added to the Makefile's
  `.PHONY` line (a line the update also changes) owed the `audit-project`
  error again, exit 1: check_W reads the conflicted Makefile and reports
  against the cleanly merged manifest. With both resolutions the project
  reports 0 owed, 12 resolved and 1 conflicted file, with exit 0. The parity
  test gained that project (`7f0a68b-conflict`). It resolves the real update
  both ways with `git merge-file --ours` and `--theirs` over copier's index
  stages, not with the audit's marker reader, and holds the audit's judged
  findings equal to what both resolutions have outside the conflicted file.
- The scratch copy is committed whatever DEST's state, so a DEST with
  uncommitted changes previewed a clean update that the real `copier update`
  refuses ("Destination repository is dirty"). The config group now warns
  `update-refused` and names each uncommitted path, or says DEST is outside
  git. The exit code does not change.
- `run_checks(root, config_overrides)` lost its last caller with the in-memory
  merge, so the parameter is gone (`run_checks(root)`).

**Residual risk.**
- A finding that neither the all-project nor the all-template resolution of
  the conflicts raises, but a resolution mixing the two hunk by hunk would, is
  not seen; one that both raise but a mix would clear is owed. Only a tree with
  more than one conflict hunk can hit this.
- A finding whose message carries a line number that the update shifts, such
  as `Makefile:42:`, is reported once as resolved and once as owed. The owed
  count and the exit stay correct, but `resolved_by_update` can over-count.
- A failed update gives no partial report. On bedrock-platform the audit names
  the failing task, but not the 120 conflicts the user meets next.
- Files DEST's git ignores are not copied, so neither run judges them.
- A link that leaves DEST is copied as its target's bytes, or dropped when it
  is a directory or dangles. A submodule is not copied. Each is listed in "not
  checked".

### Slice C2-5 — template and project ADRs live in separate number spaces

**Measured.** bedrock-platform holds keel's ADR 0001-0009 and its own 0010;
keel's 0010-0012 would land beside it. project-jarvis holds keel's 0001-0004
and its own 0005-0011, so keel's 0005-0011 are seven different decisions under
the same seven numbers. project-jarvis also edited keel's 0001-0004: each
carries `owner: Juan.Kok` where keel ships `owner: TBD`. copier 9.17's
`_remove_old_files` deletes every file the old render had and the new render
lacks, edited or not, before any migration runs, so moving keel's ADRs would
have dropped those edits without a word.

**The rule.** keel's ADRs move to `docs/adr/keel/K-NNNN-<slug>.md` and are
cited as `ADR-K-NNNN`; `docs/adr/` is the project's own space, numbered from
0001 (CONVENTIONS §19, ADR-K-0013, proposed). `config/project.json` `adr`
names both spaces and the template's own ADR file names (`template_adrs`),
and check_Y holds every ADR to its space: a template-space file the list does
not name, and a `kind: adr` document outside both directories, are errors, so
a project's decision cannot take a free `K-` number either. Each moved ADR
keeps its `id:`. `scripts/jobs/keep_edited_retired.py`, the first `after`
migration, puts back a file the update deleted when the project edited it
(any byte but the `updated:` value) and names it with its successor. The
audit's new `retired` group names each edited file the update still deletes.
The next release is 0.2.0, because a generated project's contract breaks.

**Correction during the slice.** The first draft said copier runs no
migration for a `_commit` with no tag ancestry, and so that project-jarvis
would get no guard. A spy on `_remove_old_files` during a real update of a
project-jarvis clone disproved it: copier versions `72fd224` through dunamai
as `0.0.0.post17.dev0+72fd224`, runs every migration, and the guard printed
`kept docs/adr/0001-record-architecture-decisions.md: ... (now
docs/adr/keel/K-0001-record-architecture-decisions.md)` for each of 0001-0004
and for `scripts/README_check_structure.md`. ADR-K-0013, CONVENTIONS §19, the
READMEs, `docs/adr/README.md`, `copier.yml` and the CHANGELOG were reworded to
the measurement.

**Rehearsal.** The audit from this tree, against the rehearsal clones:
- project-jarvis (`_commit: 72fd224`): owed errors 92 before the slice, 99
  after. The new ones are 4 check_A duplicate ids (each kept 0001-0004 shares
  its `id:` with the K- file, as designed), 1 Q, 1 Y (its own `0010` title
  begins `A neutral job-placement seam` rather than `ADR-0010:`) and 1
  `retired`: the named `rm` migration for keel's meta-tests deletes the
  project's edited `tests/integration/test_copier_generation.py`. A second Y
  finding, the missing `adr` block, is resolved by the update. Conflicts stay
  at 110.
- bedrock-platform (`_commit: v0.1.0-14-g7f0a68b`): owed errors 15 before and
  after. Its keel ADRs are unedited, so the update deletes them and nothing is
  kept; the `adr` block's Y finding is resolved by the update. Conflicts fall
  from 119 to 110.

**Residual risk.**
- An `rm` migration runs after the guard and still deletes the path it names.
  The `retired` group reports it before the update; nothing stops it.
- A file the template renders from a `.jinja` source is put back and named,
  not judged: comparing it needs the old answers and a render.
- The guard imports `review_docs` and `child_env` from the project, and
  `build_child_env` reads `config/project.json`. When the update leaves one of
  them conflicted, the guard exits 2 before it can list what was deleted, the
  update fails at that migration, and a deleted file comes back only through
  `git checkout HEAD -- <path>`.
- The restamp `_task` moves `updated:` in every ADR the update touched, so a
  kept ADR shows as modified twice.
- A bare `ADR-NNNN` mention is not checked against the space it names. This
  slice re-pointed the keel mentions in shipped files (scripts, tests, the
  guides, CONVENTIONS) by hand; a review found 21 in the shipped tests that
  the first pass missed. The excluded plan documents keep the old numbers as
  history.
- `adr.template_adrs` is a file a project can edit. check_Y makes adding a
  project ADR to the template space a deliberate edit of that list, not an
  accident; it does not stop a project that edits the list on purpose.
- `audit_project.origin_of` does not discount the `updated:` value the way
  `is_edited` does, so a copy differing only in its stamp reads as
  template-edited there.

The vault backlog for keel (`KEEL-*` items: the frontend contract chain FE-2,
FE-1, FE-6, FE-3; TEST-1 live-store guard; SEC-1 secrets scan) is the next
campaign, not this one.
