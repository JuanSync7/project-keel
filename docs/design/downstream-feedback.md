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
updated: 2026-10-23
visibility: internal
canonical: true
---

# Downstream feedback — what the first generated project found wrong with keel

bedrock-platform was generated from keel at `7f0a68b` and reported five defects.
Each was reproduced in keel before it was accepted. This document is the worklist:
the status table is authoritative, the per-slice notes record the measurement and
the decision.

Work here is named as CONVENTIONS §20 sets out, and check_Z in
`scripts/check_structure.py` holds every table and mention below to it: a
campaign is `CMP-<n>`, a slice is `CMP-<n>.S<m>`, and a pass is counted, never
named. Campaign 1's slices were numbered 1 to 5 and Campaign 2's C2-1 to C2-5
until CMP-2.S4 renamed them in place; a commit message from before then keeps
the old form.

## CMP-1 — the five defects bedrock-platform reported

| Slice | Defect | Status |
|-------|--------|--------|
| CMP-1.S1 | A generated project fails its own doc-freshness test on arrival | done — `make verify` green (776 passed); ADR-0010 accepted |
| CMP-1.S2 | An unknown directory is invisible to the structure gate | done — `make verify` green (807 passed) |
| CMP-1.S3 | A make target's effect is declared nowhere, so a "check" can write | done — `make verify` green (987 passed); ADR-0011 accepted |
| CMP-1.S4 | Every child process inherits every credential in the environment | done — `make verify` green (1124 passed); ADR-0012 accepted |
| CMP-1.S5 | No command checks an existing keel project for CMP-1.S1 to CMP-1.S4 | done — `make verify` green (1178 passed); 7 of 8 review findings confirmed and fixed |

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

## Slice CMP-1.S1 — freshness on arrival

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

## Slice CMP-1.S2 — the directory taxonomy is closed

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

## Slice CMP-1.S3 — every make target declares its effect

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
nothing in bedrock-platform then; CMP-2.S5 moved it into the template's own
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

## Slice CMP-1.S4 — child processes get an allowlisted environment

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

## Slice CMP-1.S5 — audit an existing keel project

**Measured.** On git 2.43.5, `git diff HEAD`, plain `git status` and
`git describe --dirty` each rewrite `.git/index` when a stat refresh is due, and
`GIT_OPTIONAL_LOCKS=0` does not stop `diff` doing it; `--no-optional-locks status`,
`ls-files`, `log` and `rev-parse` leave the index alone. Before this slice,
`review_docs` and `restamp_docs --check` listed modified files with
`git diff HEAD`, so a read-only freshness check wrote into the project it judged.
A dry run of the CMP-1.S1 to CMP-1.S4 checks over bedrock-platform, before the config merge
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
`run_checks(root, config_overrides)` in `scripts/check_structure.py` (CMP-2.S3
removed `config_overrides`, which only the in-memory merge used);
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
  Template ADRs and project ADRs need separate number spaces; CMP-1.S3's ADR
  must not deepen the collision. Fixed by CMP-2.S5.
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
  import path. Fixed by CMP-3.S1.
- **`make smoke` exits 5** because it selects no tests today, so the sweep skips
  it by reason instead of proving it. Fixed by CMP-3.S1.
- **ADR numbers.** CMP-1.S3's ADR took keel's next free number, 0011; the queued
  number-space item above still decides how template and project ADRs coexist.
  Fixed by CMP-2.S5.
- **`api/grpc/Makefile` is outside the walk.** `check_W` and `check_P` follow
  `include` from the root `Makefile`, so a transport's own makefile, run with
  `make -C`, carries no labels and no guard check.
- **An untagged template skips `_migrations`**, including the update restamp.
  CMP-2.S5 measured the opposite for an untagged `_commit` on copier 9.17:
  dunamai versions project-jarvis's `72fd224` `0.0.0.post17.dev0+72fd224`, and
  its update ran every migration.
- **Nothing pins `TAXONOMY` to the CONVENTIONS §2 table.** The list in
  `scripts/check_structure.py` and the table are kept in step by hand, and since
  CMP-1.S2 a drift between them is an error source. A parity check or test should
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
  CMP-2.S2.
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
  files fixed it. CMP-1.S5 hit it again: the tracked `scripts/README.md` and
  `config/project.json` named the untracked `audit_project.py` and
  `scripts/README.md.jinja`, so check_structure failed in every clone (three
  update tests and the effect sweep), and `git add -N` fixed it again. The
  harness could refuse to run while a non-ignored file under the template is
  untracked, so the failure names its cause. The same
  `git diff HEAD` rewrites keel's own `.git/index` on every run (CMP-1.S5's
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
  CMP-2.S3.
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
  not on its own working directory. Fixed by CMP-2.S1.
- **A restamped doc reads as `template-edited`** after the update's migration,
  so origin overstates the project's edits there.
- **`GIT_CONFIG`, `GIT_CONFIG_COUNT` and `GIT_CONFIG_PARAMETERS` reach a
  child.** CMP-2.S1 left them out of `repo_context_names` because they carry
  configuration, not a repository. A hook still exports a `git -c` value
  through `GIT_CONFIG_PARAMETERS`, so a policy could refuse the three in
  `child_env.names` and hold them back by default.
- **A git or make run that does not start through `build_child_env` keeps the
  hook's repository.** copier runs git through plumbum with its own environment,
  and a hook can start `make` directly rather than through the gate runner.
  CMP-2.S1 covers only processes started through the helper and the test
  suite.

## Campaign result

CMP-1.S1 to CMP-1.S4 landed as `3bc2f8a`, `860b9e4`, `6cea98a` and `094dbca`, each on a
green `make verify`. CMP-1.S5 adds `make audit-project DEST=` on a green
`make verify` (1178 passed).
ADR-0010, ADR-0011 and ADR-0012 were accepted on 2026-10-06. Everything
found along the way and not fixed is in Queued above.

## CMP-2 — the ranked queue

The maintainer accepted ADR-0010, ADR-0011 and ADR-0012 on 2026-10-06 and asked
for the Queued list above to be worked in risk order before bedrock-platform's
next round of feedback. The cap is five slices, each one commit on a green
`make verify`. v0.2.0 was tagged after CMP-2.S5, whose number-space move is the first
breaking change to the generated-project contract (ADR-K-0013). A concern found mid-slice joins Queued.

| Slice | Defect | Status |
|-------|--------|--------|
| CMP-2.S1 | A child inherits `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`, so its git acts on the parent's repository | done — `make verify` green (1206 passed); 3 review findings confirmed and fixed |
| CMP-2.S2 | A proxy URL with embedded credentials reaches every child | done — `make verify` green (1288 passed); 8 of 9 review findings confirmed and fixed |
| CMP-2.S3 | The audit reads the `Makefile` and `config/practices.json` before the merge, so an old project reports a false W error | done — `make verify` green (1308 passed); 4 review findings confirmed and fixed |
| CMP-2.S4 | A campaign, slice or pass has no fixed name, so a commit, a plan row and a ledger entry cannot name the same unit of work | done — `make verify` green (1436 passed); 7 review findings confirmed and fixed; replaced the `make smoke` slice, which moved to CMP-3 as CMP-3.S1 |
| CMP-2.S5 | A downstream project's ADR numbers collide with the template's | done — `make verify` green (1356 passed); 6 of 7 review findings confirmed and fixed; ADR-K-0013 accepted 2026-10-07 by the maintainer |

### Slice CMP-2.S1 — a child does not inherit the parent's repository

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
merge leaves an allowlist; CMP-2.S3 replaced that merge with copier's own
update, which the audit now runs and reads. Before this slice the list was
atomic. A project from before CMP-2.S1 that had
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

### Slice CMP-2.S2 — a credential in an allowlisted value does not reach a child

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

**Config, not keyword.** CMP-2.S1's opt-in is a keyword because acting on the
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

### Slice CMP-2.S3 — the audit judges the tree the update leaves

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
unchanged, and no `keel-audit-*` directory was left behind. CMP-1.S5's count of
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

### Slice CMP-2.S4 — campaigns and slices carry one checked name

**Measured.** Before this slice, this document named the same units of work in
four spellings: a bare number for the first campaign's slices ("Slice 1", 12
uses), `C2-n` for the second (26 uses), `C3-n` and `C4-n` in the draft of the
next two (17 uses), and "Campaign n" in prose (6 uses). keel's 67 commits carry
no trailer that names a slice. project-jarvis's 343 commits carry none either,
and jarvis already uses `C0` to `C8` for its risk classes, so a `C2-4` in a
jarvis ledger reads as a risk class.

**The rule.** CONVENTIONS §20. A campaign is `CMP-<n>` and a slice
`CMP-<n>.S<m>`; a pass is counted against its cap, not named. A plan doc (a
`kind: design` document with a `Slice` table) declares the ids, a commit that
delivers a slice ends with a `Slice:` trailer, and another repository's slice
is `<project>:CMP-<n>.S<m>`, with `<project>` from that repository's
`config/project.json` `name`.

**Decision: the grammar is config.** `config/project.json` `work_naming` holds
the plan kinds, the slice column, both id templates, the backlog pattern, both
trailer keys and the adoption boundary, and ships in `config/project.json.jinja`
unchanged. check_Z reads only the block, apart from two fallback constants
(`design`, `Slice`) used to find a plan doc when the block is missing; a test
holds them equal to the block.

**Decision: the git half is a test.** check_Z judges the plan docs, and
`tests/integration/test_work_trailers.py` judges the trailers, because
check_structure reads no git (ADR-K-0009). A trailer key in another case, a
second `Slice:`, a prefixed or undeclared id, a malformed `Backlog:`, and a
`Slice:` or `Backlog:` line above the trailer block whose value has the id's
shape are findings; a line such as `slice: split the parser` is prose. A
boundary that does not resolve, or is not an ancestor of `HEAD`, fails the
test rather than judging nothing. A history with no trailer is a stated skip
with its commit count.

**Decision: mentions are judged everywhere.** A bare id in the prose of any
Markdown file must name a declared one, so shipped documents write their
examples in code spans. A row's first cell and a code span are not mentions. A
token is read whole, so `CMP-1.S02` is malformed rather than a mention of
`CMP-1`.

**Built.**
- `scripts/check_structure.py` `check_Z`, with `work_naming_policy`,
  `id_grammar`, `parse_plan` and `plan_inventory`.
- `tests/unit/scripts/test_check_z.py` and
  `tests/integration/test_work_trailers.py`.
- The `work_naming` block in `config/project.json` and its twin, and the gate
  practice `work-naming` (row 40).
- CONVENTIONS §20, with a §6 row and a §15 bullet; the root `AGENT.md` rule;
  the naming section of `docs/guides/dev-loops.md`; the Z entry in
  `docs/guides/deterministic-checks.md`.
- This document renamed to the rule: CMP-1 for the five defects, CMP-2 for the
  queue, CMP-3 and CMP-4 for the drafted campaigns that follow.
- `tests/unit/scripts/test_audit_project.py` reads the check letters from
  check_structure's own `def check_<L>` lines instead of a hand-kept range.

**Downstream.**
- A project generated from this tree carries the block and no plan doc, and
  its gate is green with no Z finding. Its first plan doc reds the gate on a
  `| 2 |` row, naming the line, and is green with `CMP-1.S2`
  (`test_generated_project_judges_work_naming`).
- `make audit-project` on a project generated at `7f0a68b`: exit 0, 0 owed,
  0 Z findings, and `work_naming` listed as arriving with the update. The same
  audit from `HEAD` before this slice differs only by the Z row and that
  config entry. Two runs printed byte-identical JSON.
- The bedrock-platform rehearsal clone: exit 1 with 26 owed errors, the same
  26 as the audit from `HEAD` before this slice, and 0 Z findings. With the
  block added, its 166 commits are a stated skip with no trailer.
- project-jarvis, on a scratch clone at `1094ea3` with the block added: 0 Z
  findings, no plan doc, and no other letter's count changed. Its 343 commits
  are a stated skip.

**Adopting in project-jarvis.** jarvis adds the `work_naming` block to its
`config/project.json` and sets `adoption_boundary` to its last commit before
adoption, so its earlier history is not judged. Its ledger then ingests the
`Slice:` trailer of each commit as the slice the commit delivers, and names a
keel slice as `project_keel:CMP-2.S4` (or this repository's own `name`, if it
differs).

**Residual risk.**
- A slice id reused across several commits breaks the one-commit rule of
  CONVENTIONS §20 but is not detected.
- A foreign-prefixed id is not resolved, because the other plan is not in this
  tree.
- A requirement id is not named by the rule; requirements and slices are many
  to many.

### Slice CMP-2.S5 — template and project ADRs live in separate number spaces

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
0001 (CONVENTIONS §19, ADR-K-0013). `config/project.json` `adr`
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
FE-1, FE-6, FE-3; TEST-1 live-store guard; SEC-1 secrets scan) is queued in
CMP-4 below, not worked here.

## CMP-3 — what blocks bedrock-platform's next update

The maintainer approved this campaign on 2026-10-07, to start once CMP-2.S4
lands. The cap is five slices, each one commit on a green `make verify`. CMP-3.S6 is one slice past that cap, by the
maintainer's decision, to finish bedrock-platform's adoption before Campaign 4.

| Slice | Defect | Status |
|-------|--------|--------|
| CMP-3.S1 | `make smoke` passes over zero tests, and `make run` fails with `No module named app` | done — `make verify` green (1517 passed); 5 review findings confirmed and fixed |
| CMP-3.S2 | A document whose only conflict on `copier update` is its `updated:` line is left conflicted for a person to resolve | done — `make verify` green (1562 passed); 1 of 2 review findings confirmed and fixed |
| CMP-3.S3 | A project can add a check only by editing `scripts/check_structure.py`, so its next `copier update` conflicts in the module the restamp task imports | done — `make verify` green (1614 passed); 6 review findings confirmed and fixed; ADR-K-0014 accepted |
| CMP-3.S4 | The `GIT_CONFIG_COUNT`/`GIT_CONFIG_PARAMETERS` variables reach a child, copier's own git calls bypass `build_child_env`, and a bare token or `Authorization` value is not recognised as a credential | done — `make verify` green (1659 passed); 5 review findings confirmed and fixed |
| CMP-3.S5 | Four defects bedrock-platform hit adopting 0.2.0: `make audit-project` under the default `PY=python3` (3.6) dies with a `SyntaxError` (K1); the audit exits 2 when the update's restamp refuses over a conflicted import (K2); a project's `write_shapes` cannot include `-apply` because keel's own `doc-review-apply` is a non-write (K3); and check_W passes a recipe that opens with `$(WRITE_GUARD)` under a non-`[write]` label (K4) | done — `make verify` green (1700 passed); 3 review findings confirmed and fixed; ADR-K-0015 accepted |
| CMP-3.S6 | Three keel tests whose verdict depends on where they run: `tests/integration/test_write_guard.py` copies the `Makefile` without the `make_targets.area_dir` directory it includes (K5); `tests/unit/scripts/test_check_y.py` asserts a project has no ADRs of its own, which fails in any project that records one (K6); and `tests/integration/test_make_target_effects.py` runs each `[local]` target with the caller's `HOME`, so a target that reads it passes on one host and fails on another, and one that writes it is never seen (K7) | done — `make verify` green (1738 passed); 6 of 7 review findings confirmed and fixed |

CMP-3.S3 is the bedrock blocker measured in CMP-2.S3's rehearsal: a real
`copier update` of bedrock-platform left 120 files conflicted and failed in the
restamp task.


### Slice CMP-3.S1 — a tier that ran zero tests fails, and `make run` runs

**Measured.** In a clean shell, `make run` exited 2 with `No module named app`:
the recipe was `$(PY) -m app` with no `PYTHONPATH`, so it worked only where the
caller had already put `src` on the path. `make smoke` exited 5 over 1437
deselected tests, and the effect sweep skipped both targets by reason, the
`run` reason ("serves until stopped") being false. A smoke test that skipped
made `make smoke` exit 0, because pytest exits 5 only when nothing is
collected. A project generated at 28772f1 showed the same two failures.

**The rule.** `make run` sets `PYTHONPATH` and runs `scripts/run_app.py`,
which runs the module config/project.json `layers.app` names. An absent or
null `layers.app` exits 2 naming which. check_H holds `layers.app` to a
package with `__main__.py` or a `.py` file and to a module that is that path's
dotted form; `check_structure.composition_root` is the one rule both apply.
`tests/conftest.py` counts the tests that ran (passed, failed or xfail), and
`tests/selection_guard.py` fails a session where none did, unless its one bare
`-m` marker is in the new `make_targets.empty_test_selections`, read through
`make_targets_policy`. A declared marker whose tests ran fails as stale, and
check_W errors on an entry no `pytest -m` recipe selects, parsing the recipes
rather than listing tiers. `tests/smoke/test_app_runs.py` runs `make run` with
the allowlisted environment, so smoke has a real test. `run` and `smoke` left
`effect_proof_skip`. `src/app/README.md` says what to change when the
directory is deleted, and `test_following_src_apps_delete_advice_leaves_a_green_gate`
follows that advice in a generated project.

**Proof.** The selection guard, check_H's `layers.app` rule, check_W's stale
rule and `scripts/run_app.py` each have unit tests, and
`tests/integration/test_empty_selection.py` runs every pytest tier the
Makefile declares in a scratch project with nothing to select. Breaking the
guard's zero check, the stale check or the module match, or reverting the
recipe to `$(PY) -m app`, each turned a named test red. Projects generated
from this tree (defaults, and no frontend without the showcase) pass `make run` and `make smoke` with one smoke
test. A real `copier update` of a 7f0a68b project and of a 28772f1 project
conflicts nowhere, removes `run` and `smoke` from `effect_proof_skip`, brings
`layers.app` and `empty_test_selections`, and leaves both targets green;
`make audit-project` on the 7f0a68b copy owes 0 errors.

**Review.** Five findings were confirmed and fixed. `--setup-plan` and
`--setup-only` run no test and are left alone, as `--collect-only` is. A run
narrowed by a path or `-k` is named as given and is never exempt, so the
declare-a-marker advice appears only where it can apply. A project that
deleted `src/app` before `layers.app` existed is settled on `copier update`
by the migration `scripts/jobs/declare_no_app.py`, which acts only when the
declared path is absent and the pre-update manifest had no `layers.app`;
check_H's error for an absent path names the null remedy. `src/app/AGENT.md`
names the three manifest edits, pinned by the delete-advice test.
`scripts/run_app.py --help` describes the runner, and `--` passes the app's
own arguments.

**Residual risk.**
- A test file run alone whose tests all skip now exits 5.
  `test_meta_tests_neutralise_themselves_in_a_project_that_still_has_them`
  expects that exit for keel's meta-tests in a generated project.
- `make run` is one-shot. A project that turns its composition root into a
  server must give its smoke test a readiness probe and skip `run` by reason;
  `src/app/README.md` says so, and nothing checks it. A socket-level e2e is
  CMP-4.S6.
- `pytest_selections` takes the first pytest command in a recipe. A recipe that
  runs pytest twice with different `-m` markers is judged by the first.
- ADR-K-0011 still lists `run` among the targets the effect sweep skips. That
  stopped being true here, since `make run` now exits and the sweep runs it. The
  ADR is accepted and is not edited; `config/project.json`
  `make_targets.effect_proof_skip` is the current list.

### Slice CMP-3.S2 — a conflict on the `updated:` line alone resolves itself

**Measured.** A stamp-only conflict needs the two sides' stamps to differ from
the base. A project generated before `3bc2f8a` (the first commit fresh on
arrival) has that shape. A toy generated at v0.2.0 had no stamp conflicts. A
real `copier update` of the bedrock-platform replica at `22f1bad` left 111
paths unmerged. Of those, 95 were stamp-only, 7 were a stamp plus content, and
9 were content only. The CMP-2.S3 note's figure of 120 was measured on an
earlier template.

**Decision.** `scripts/jobs/resolve_stamp_conflicts.py` runs as a copier
after-migration before the restamp migration. A conflicted Markdown document
whose only hunk is one `updated:` line on each side gets the later of the two
ISO dates, because `updated:` means touched and both sides touched it. Any
other conflict keeps its markers and is named on stderr. A git merge driver
was rejected: copier merges with `git apply --reject` and `git merge-file`,
which never consult `.gitattributes`, and a template cannot register a driver
in `.git/config`. The date grammar comes from `review_docs.updated_span`, the
reader check_Q and the restamp already use, so no config key was added.

**Trajectory.**

| Rehearsal | Unmerged before | Unmerged after | Left by the job |
|-----------|-----------------|----------------|-----------------|
| bedrock-platform replica | 111 | 16 | 7 with more than one hunk, 9 not Markdown |
| project-jarvis replica | 111 | 54 | 15 with more than one hunk, 2 with a multi-line side, 37 not Markdown |
| toy generated at 7f0a68b | 5 | 3 | 3 with more than one hunk |
| toy generated at v0.2.0 | 2 | 2 | none; both are content conflicts |

Every stamp-only path resolved to the before text with the later date. A
second run left the work tree, the index and its mtime byte-identical.

**Residual risk.**
- Both replica updates still exit 1, because the restamp imports a conflicted
  `scripts/check_structure.py`. That is CMP-3.S3. Until it lands,
  `make audit-project` on those replicas also exits 2, so the audit cannot show
  the 111-to-16 drop; the rehearsal above is the evidence.
- A stamp hunk that sits next to a content hunk is left for a person.
- The restamp migration rewrites the project's stamp inside a document that
  still has a content conflict. Fixing that changes `restamp_docs.py` and
  belongs with CMP-3.S3.

### Slice CMP-3.S3 — a project adds a check without editing the gate

**Measured.** Both replicas had edited their copy of
`scripts/check_structure.py`. bedrock-platform added its make-target effect
rules (223 lines added, 13 removed). project-jarvis added a Markdown link
check as `check_N`, widened the owner warning, ignored `.claude` and added
`self` to the taxonomy (115 changed lines). The template later gave the letter
N to twin parity. On a real `copier update`, that module conflicted on both
replicas. Every `after` migration imports it, and the restamp migration died on
a `SyntaxError` traceback (CMP-3.S2's residual risk).

**Decision.** `config/project.json` `structure.project_checks` is absent or
null (off), or names a directory already declared in
`structure.extra_toplevel`. The template never ships the key, because one
shipped beside `extra_toplevel` conflicted on update (the toy rows below). A
project adds it when it adopts. check_structure runs each top-level `*.py`
module there, in sorted order, after every lettered check, and reports each
`(tier, message)` pair the module's `check(root)` returns, prefixed with
`<dir>/<file>.py`. What the module reports through the gate's `err()` and
`warn()` counts as its findings too. The template ships no file in that directory,
so `copier update` never merges one. A project check only adds findings: the
template's findings are collected first and there is no waiver key. Every
failure of a project check is an error naming the module, including a load
error, a conflicted module, a bad return value and a declared directory with no
module, and a `*.py` name that is a dangling symlink.
`scripts/jobs/conflict_guard.py` stops each of the four `after`
migrations, with exit 2 and no traceback, when a module it imports holds
conflict markers. It names each file and line and the command to rerun.
`scripts/jobs/restamp_docs.py` skips a conflicted document and its twin and
names each skip on stderr. `scripts/audit_project.py` never runs a project's
checks, and lists them under what it does not check.
`docs/adr/keel/K-0014-project-owned-structure-checks.md` is the decision.

**Trajectory.** Each row is a real `copier update --vcs-ref HEAD` of a scratch
copy, against a snapshot of this tree.

| Rehearsal | Exit | Unmerged | `scripts/check_structure.py` | What stops it |
|-----------|------|----------|----------------------|---------------|
| bedrock-platform, CMP-3.S2 | 1 | 16 | conflicted | restamp `SyntaxError` traceback |
| bedrock-platform, edits kept | 1 | 16 | conflicted | restamp guard, exit 2, 5 hunks named |
| bedrock-platform, checks adopted first, block appended | 0 | 15 | merged | nothing |
| bedrock-platform, gate restored first, checks after | 0 | 15 | merged | nothing |
| project-jarvis, CMP-3.S2 | 1 | 54 | conflicted | restamp `SyntaxError` traceback |
| project-jarvis, edits kept | 1 | 54 | conflicted | restamp guard, exit 2, 4 hunks named |
| project-jarvis, checks adopted first, block appended | 0 | 53 | merged | nothing |
| project-jarvis, gate restored first, checks after | 0 | 53 | merged | nothing |
| either replica, `structure` block inserted after `name` | 1 | 111 | merged | `keep_edited_retired` exits 2 on the conflicted `config/project.json` |
| toy project with a declared directory, key shipped as null (first draft) | 1 | 1 | merged | `keep_edited_retired` exits 2 on the conflicted `config/project.json` |
| toy project with a declared directory, key not shipped | 0 | 0 | merged | nothing |
| bedrock-platform, gate restored first, key added after the update | 0 | 15 | merged | nothing |

In the adopted copies, bedrock-platform's `checks/guarded_write.py` (a recipe
that opens with `$(WRITE_GUARD)` is labelled `[write]`) reported a planted
target and nothing once it was removed. project-jarvis's `checks/doc_owner.py`
reported 23 warnings. Two gate runs printed byte-identical output, and two
restamp runs left the work tree and the index byte-identical, skipping 7 and 17
conflicted documents. `tests/integration/test_copier_project_checks.py` runs
the same two shapes on a toy project.

In the last bedrock-platform row the project added `"project_checks":
"checks"` beside the `extra_toplevel` the update brought. A planted mislabelled
target was reported as `checks/guarded_write.py`, and the gate reported nothing
from it once the target was removed.

**Proof.** Nineteen mutations each turned a named test red, and each file was
restored byte-identical. They covered running the project checks before the
template's, letting a `SystemExit` through, accepting an empty directory,
skipping the marker scan, dropping the `__main__` alias, skipping the restamp
guard, not asking git for unmerged paths, skipping the restamp marker scan,
returning from `exit_if_conflicted`, not following imports, running the
checks in either audit mode, dropping what a check reported through `err()` or
`warn()`, accepting a non-list left in their place, skipping a dangling
symlink, opening a name that is not a regular file, letting the restamp's
`ChildEnvError` through in either mode, and shipping the key as null.

**Adoption.** Restore `scripts/check_structure.py` to the template's version,
then move each rule into a module under `checks/`. Fill the `structure` block
the update brings, and add `"project_checks": "checks"` beside its
`extra_toplevel`, rather than adding a block: a block inserted where the template
inserts its own conflicts in `config/project.json`, and that conflict stops the
first migration. A block added at the end merges, but leaves two `structure`
keys, and the gate reads the last one without saying so. A rule the template
now enforces belongs in no project check: project-jarvis's link check reported
the same planted link the template's own check did.

**Residual risk.**
- A project check is trusted code that runs inside the gate. It is not a
  sandbox.
- The `checks/` directory sits outside the module-header, export and rerun
  checks (O, E and V), which cover the code roots only.
- A document that quotes a whole conflict hunk is never restamped. This tree has
  none.
- `conflict_guard` covers Python imports only. A conflicted
  `config/project.json` still stops `keep_edited_retired` with exit 2, naming
  the manifest but no rerun command. `scripts/jobs/restamp_docs.py` run by hand
  then names the hunk's line and `make restamp-docs`, exit 2.
- The template's `structure` block is two lines beside the one every adopting
  project edits. A later template edit to its `_comment` conflicts in
  `config/project.json` for each of them. That was already true of every
  project that declared a directory in `structure.extra_toplevel`.
- Not every edit can move: project-jarvis's `.claude` ignore has no config key,
  and its `examples` directory also needs `structure.extra_toplevel`.

**Queued.**
- Upstream the converse `[write]` rule into check_W, so bedrock-platform can
  drop `checks/guarded_write.py`. CMP-3.S5 delivers it (K4 below).
- A config key for directories the walk ignores, for project-jarvis's `.claude`.
- Reject a duplicate key in `config/project.json`.
- Extend the guard to a conflicted `config/project.json` in
  `keep_edited_retired` and `declare_no_app`, naming the rerun.

### Slice CMP-3.S4 — the child_env residuals CMP-2.S1 and CMP-2.S2 left open

**Measured.** The row named three defects; each was measured before a line
changed.
- The `GIT_CONFIG_*` family through `build_child_env`: 0 members copied, so
  the row's first claim is false through the helper. The real gaps were three:
  a manifest could admit a member (`names`, a `GIT_` prefix, a make variable,
  a credential list) and no check refused it; `tests/conftest.py` and
  `tests/hermetic_git.py` stripped the repository variables but not this
  family, so a parent's `git -c` reached the suite's own git and copier; and
  the unit test listed the family in code rather than reading it from config.
- copier's own git calls under `make audit-project`: `scripts/audit_project.py`
  already starts copier through `build_child_env`, so the second claim is false
  for the audit path. The new test is a guard against a regression, not a fix.
- A credential that is not a URL user part: of 9 shapes (an `Authorization`
  header, a bare `Bearer`/`Basic`/`token` value, a JWT, an opaque token, a PEM
  private key), 0 were refused. The row said 4 of 9 were caught; the
  measurement says 0.

**Rule.** `config/project.json` `child_env` gains four keys, read by
`scripts/child_env.py` and nowhere else.
- `config_injection_names` and `config_injection_prefixes` (required,
  non-empty) name the family. `build_child_env` never copies a member, even
  under `repo_context=True` or when a policy admits one, and check_X refuses
  every allowlist source that would admit one, a prefix matching when either
  covers the other.
- `credential_value_patterns` (required, non-empty) maps a label to a regular
  expression searched in every copied value and every gate value. A refusal
  names the variable and the label, never the value; a validation error names
  the label, never the pattern.
- `login_name_schemes` (optional, default `[]`) makes a URL user part a login
  name, refused only with a password. It is scoped to login schemes because
  `https://token@host` must stay refused.

**Proof.**
- RED before the change: 129 of 319 unit tests failed for the stated reasons
  (unknown keys, a shaped value not refused, a refused gate value that had
  still snapshotted the tree). GREEN after: 319 passed; the two integration
  files, 27 passed.
- False positives, counts only: 0 of 7 allowlisted variables and 0 of 83 in a
  whole interactive environment matched a pattern; the scan took under 1 ms.
- Four mutations each turned a named test red and were restored
  byte-identical: no conftest strip, `audit_project._child` handing copier
  `os.environ`, the `http-authorization` look-ahead removed (the ordinary values
  `basic authentication` and `token placeholderstring` were then refused), and
  the copy-path skip deleted together with the policy refusal.
- Downstream, in a project generated from the working tree: `make check` and
  the Python 3.6 gate exit 0; `GIT_CONFIG_PARAMETERS` in `names` is one X error
  naming the fix, `GIT_` in `prefixes` is one X error listing the family it
  admits; `run_make_target.py check PY=tok_...` exits 2 naming `PY` and
  `opaque-token`, the value absent; an `ssh://git@` value is copied and an
  `https://user@` value refused.
- `copier update` of projects generated at 29e45f0 and 7f0a68b: exit 0, 0
  unmerged paths, 0 files with conflict markers, the four keys equal to the
  template's, `make check` exit 0.
- `make audit-project` of a 7f0a68b project: 0 errors owed, 13 resolved by the
  update. Again with a `git` shim first on `PATH` and the family planted in the
  environment: 2128 git calls, none of which saw a family member, and the
  same verdict.

**Review.** An adversarial review confirmed four defects, each reproduced by
an independent refuter and each fixed test-first.
- `authorization-header` read a colon-joined list as a header: a `PATH`
  entry that is a directory named `authorization` (`/opt/sso/authorization:`)
  matched, and since `PATH` is in every allowlist, every `build_child_env`
  call failed closed. The pattern now needs whitespace after the colon, or a
  scheme word and whitespace (`Authorization:Bearer <token>`), so a list's
  next entry is never read as a header value.
- `opaque-token` caught a token with a trailing newline (Python's `$` matches
  before one) but not one padded with a space or a tab. Its anchors now allow
  whitespace, and the leading run cannot backtrack (`(?![\s_~+=-])`), so a
  value of 100 kB of spaces still scans in linear time.
- The four new keys sat on the lines directly above `credentialed_values`.
  git merges adjacent edits as one hunk, so a project that had recorded a
  credentialed value got a conflict in `config/project.json`; the manifest
  then failed to parse and the update's own task refused to start a child,
  leaving the update half applied. The keys now follow the `_comment` line,
  which no project edits; `git merge-file` over the 7dbcc0c layout gives 0
  conflicts for an edited `credentialed_values`, `prefixes`, first name or
  last name, where the old placement conflicted on `credentialed_values`.
- This note did not say which paths stay out of reach; the residual list
  below now does.

Measured after the fixes: 0 of 7 allowlisted variables and 0 of 84 in a whole
interactive environment matched a pattern, counts only. Each fix's test was
red before it and green after (`tests/unit/scripts/test_child_env.py`: three
`PATH` cases, the ordinary-value control with five colon-list values, two
padded tokens; `tests/integration/test_copier_audit.py`: a 7dbcc0c project with
its own `credentialed_values` and `prefixes` updates with nothing unmerged and
audits with no X error owed; red before the move with the update's task
failing on the unparseable manifest). Six pattern mutations each turned a named
test red and were restored byte-identical: the old `authorization-header`, it
without the scheme-word branch, it with an optional space after the colon, the
old `opaque-token` anchors at either end, and a leading run that can backtrack
(the linear-time test failed after 387 s). `make audit-project` on the
reviewer's case (a 7dbcc0c project whose `credentialed_values` names
`HTTPS_PROXY`): exit 0, 0 errors owed, 3 resolved by the update, 0 conflicted
files; on a 7f0a68b project: exit 0, 0 owed, 13 resolved.

**Residual risk.**
- Patterns do not give full coverage. A low-entropy token and a standard base64
  secret holding `/` pass, as does any shape no pattern names.
- `extra=` is the call site's literal and is honoured verbatim, so a call that
  passes a family member on purpose still sends it.
- A `_proxy` variable's user part counts even in a login scheme, because the
  proxy reader sends it.
- Only `audit_project`'s copier is constrained. `make new` runs copier from the
  caller's shell, and a person's own `copier update` runs in theirs, so
  copier's git, run through plumbum, inherits that whole environment,
  `GIT_CONFIG_*` included. keel cannot reach a process it does not start.
- A make recipe a hook starts directly gets the environment the agent tool
  gives the hook, not `build_child_env`'s. keel's shipped hook is a Python
  doer whose own children go through the helper; a project that wires a hook
  to `make` takes this on.
- A same-user child can still read its parent's environment from
  `/proc/$PPID/environ`; the allowlist cannot close that, as
  `docs/adr/keel/K-0012-child-process-environment-allowlist.md` records.
- A list entry such as `authorization:Service bin` (a scheme-shaped word, a
  space, then more text) still matches `authorization-header`; no such value
  was found.

**Queued.**
- Measure the patterns against a second site's environment before adding
  more; each new pattern is a false-positive risk on every child.

### Slice CMP-3.S5 — four defects bedrock-platform hit adopting 0.2.0

**Measured before a line changed.** Each defect was reproduced at b950d25 on a
scratch clone; bedrock-platform itself was only read.
- K1: `make audit-project` in a keel checkout with no `.venv` (so `PY=python3`,
  3.6.8 on the shared hosts) exits 2 on `SyntaxError: future feature
  annotations is not defined` from `scripts/audit_project.py`.
- K2: the audit of a scratch clone of bedrock-platform at its HEAD (c70efc9)
  exits 2, and so does the audit of a project generated at 7f0a68b with an
  edited `scripts/check_structure.py`. In both, the update's restamp
  migration refused over a conflicted `scripts/check_structure.py`, and the
  audit stopped there, judging nothing.
- K3: keel ships `doc-review-apply: ## [tree,cost]`, so a project whose
  `write_shapes` holds `-apply` gets a check_W error on a target that is
  not a write, with no way to say so.
- K4: `platform-look: ## [read] Look` with a recipe that opens with
  `$(WRITE_GUARD)` passes check_W; under `RALPH=1` the gate runner admits it
  and the guard then refuses it.

**Rule.**
- K1: `PY` defaults to `.venv/bin/python` when it exists, else `python3`.
  Every target whose recipe needs the project interpreter reaches
  `check-python` first, and `tests/integration/test_gate_scope.py` derives
  those targets from the recipes.
- K2: an `after` migration that refuses over the update's own conflicts is
  named under not checked, with every migration after it and the command to
  rerun; the audit judges the tree copier leaves and exits by the owed-errors
  verdict. The project README says to keep `--conflict inline`, because
  `--conflict rej` leaves no markers and no unmerged file.
- K3 and K4 are
  `docs/adr/keel/K-0015-write-shape-exemptions-and-guarded-recipe-converse.md`
  (proposed); `docs/adr/keel/K-0011-make-target-effect-labels.md` gains only a
  cross-reference. `make_targets.write_shape_exempt` maps a target to its
  reason, and an entry that matches nothing is a stale error. keel ships it
  empty: its `write_shapes` default is `[]`, so `doc-review-apply` needs no
  exemption in keel itself. A labelled recipe that calls `$(WRITE_GUARD)`
  anywhere in any line must be `[write]`.

**Proof.**
- K1 after, in a scratch snapshot of the working tree with no `.venv`: the
  same command exits 2 on `this project requires Python >=3.10; /bin/python3
  is 3.6`, naming `PY=` and `.venv` as the fixes.
- K2 trajectory, the same two trees, the template a snapshot of the working
  tree:

  | Tree | Exit before | Exit after | Owed | Resolved by the update | Conflicted, not judged |
  |------|-------------|------------|------|------------------------|------------------------|
  | bedrock-platform at c70efc9 | 2 | 1 | 26 | 12 | 17 |
  | 7f0a68b project, `scripts/check_structure.py` edited | 2 | 0 | 0 | 13 | 1 |

  bedrock-platform's adoption report counted 121 conflicted files, 103 of
  them only on `updated:`. The audit now leaves 17. None of the 26 owed
  errors is a K1 to K4 rule: they are bedrock's own adoption work, such as
  `mk/` areas with `make_targets.area_dir` null, project ADRs outside
  `docs/adr`, and `subprocess.run` calls with no `env=`.
- K2, `--conflict rej` on the 7f0a68b project: 1 `.rej` file
  (`scripts/check_structure.py.rej`), 0 unmerged paths and 0 files with
  conflict markers. The restamp migration ran, over a module that silently
  holds keel's version.
- K4 on a project generated from the working tree, under host python3 3.6.8:
  `$(WRITE_GUARD)` with a trailing blank, `$(WRITE_GUARD); true` and
  `$(WRITE_GUARD) && true` under `[read]` are each one check_W error;
  `@echo '$$(WRITE_GUARD)'` is none.

**Review.** An adversarial review confirmed three findings, each reproduced by
an independent refuter and each fixed. The first two were one defect.
- The converse compared whole recipe lines with `$(WRITE_GUARD)`, so
  `$(WRITE_GUARD) && cmd`, `$(WRITE_GUARD); cmd` and a guard with a trailing
  blank passed under `[read]`; make still ran the guard (`make look RALPH=1`
  printed `refusing look`, rc 2). check_W now searches each recipe command for
  a guard reference, skipping a `$$`-escaped one. Five new cases in
  `tests/unit/scripts/test_check_w.py` were red before the change. Two
  mutations were each red and then restored byte-identical: whole-line
  equality turned the five red, and a plain substring search turned the two
  escaped-reference controls red.
- This note did not exist, so the measurements and the `make setup` decision
  were recorded nowhere.

**Residual risk.**
- A guard in an unlabelled prerequisite's recipe is not a converse error. check_W
  warns that the prerequisite has a recipe and no label, and stops there.
- A guard reached through a `$(MAKE)` recursion, or through a variable that
  expands to `$(WRITE_GUARD)`, is not read as a call.

**Queued.**
- bedrock-platform's `make setup` (`scripts/setup_venv.py`) is not adopted.
  Only its `PY` default is. As it stands, it is not generic: its install list
  names bedrock's `api/rest_fastapi/requirements.txt`, which a keel project
  has only when that transport is chosen. It names uv in the doer instead of
  behind an adapter. Its `[local]` label is narrower than what it does: a
  package install from an index reads a remote service, which check_W's
  vocabulary calls `[read]`. Adopting it needs the install list in config,
  the installer behind an adapter, and a label that covers the download.

### Slice CMP-3.S6 — keel's own tests give the same verdict anywhere

**Measured before a line changed.** A project generated from keel before this
slice's changes gained what bedrock-platform has: an area makefile (`mk/demo.mk`,
`make_targets.area_dir` set to `mk`), a project ADR (`docs/adr/0001-...`) and a
`child_env.credentialed_values` entry for `HTTPS_PROXY`. Its
`scripts/check_structure.py` reported 0 errors. keel's test files that copy a Makefile
or read a project list, run there, gave 18 failed and 354 passed:
- K5: 15 failures, every one a scratch copy of the root Makefile without the
  `mk/demo.mk` it includes (`tests/integration/test_write_guard.py` 8,
  `test_empty_selection.py` 4, `test_gate_scope.py` 2,
  `test_child_process_environment.py` 1).
- K6: 3 failures, each a keel-only fact asserted of the project.
  `tests/unit/scripts/test_check_y.py` asserted the project ADR space is
  empty, `tests/unit/scripts/test_child_env.py` asserted keel's empty
  `credentialed_values`, and the credentialed-proxy case of
  `tests/integration/test_child_process_environment.py` planted `HTTPS_PROXY`,
  which the project had opted in.
- K7: `tests/integration/test_make_target_effects.py` ran every target with the
  caller's `HOME` and compared only what git sees.

**Rule.**
- K5: a test copies a Makefile with `tests/makefile_copy.py` `copy_makefiles`,
  which copies the include closure `scripts/check_structure.py`
  `walk_makefiles` reports. It raises, naming the include, only where a copy
  would differ from the source in a way it can see: a required include through
  a variable or wildcard, an optional wildcard that matches a file, or an
  include outside the root. An include the gate only WARNs about otherwise
  stays as make sees it, so make gives the copy the source's verdict.
- K6: a test reads a list from the project's own config, never keel's value of
  it, and runs once on keel's tree and once on a fixture that adds what a
  project adds.
- K7: the sweep runs each `[local]` target under its own fresh empty `HOME`
  and fails a target that writes it. The new required key
  `make_targets.effect_proof_kept_dirs` names the XDG base dirs kept beside it
  (the caller's absolute value, else that path under the caller's `HOME`, else
  unset); check_W validates it. Before the first target, the sweep checks that
  `scripts/child_env.py` hands make the sandbox `HOME` and each kept value.

**Proof.**
- Those files, with `tests/integration/test_makefile_copy.py` and the
  fixture cases of `test_make_target_effects.py`, in a project generated the
  same way after the change: 404 passed. The sweep there ran 27 targets (keel's 26 and
  `demo-hello`) and none wrote its `HOME`; with a planted `demo-poke` target
  writing `$HOME/x` it failed on exactly that target, `home_changed: ["x"]`.
- keel's own sweep ran 26 targets, each under a fresh `HOME`, all green.
- Mutations, each red and then restored byte-identical: dropping the `HOME`
  comparison (2 tests red), one `HOME` shared by every target (1), no
  derivation under the caller's `HOME` (2), no child cross-check (2), following
  links in the `HOME` snapshot (1), `copy_makefiles` ignoring an unresolved
  include (3) or copying the root alone (4), check_W accepting `..` (2) or
  `HOME` as a kept name (1), `test_check_y.py` not comparing the project
  listing (1), and `test_child_env.py` taking keel's empty opt-ins (1).
- The downstream run caught one more case of K5's class in this slice's own new
  test, which built its source from keel's root Makefile; it now copies the
  project's own makefiles first.
- Review found four more cases of the class, each now red-then-green:
  `copy_makefiles` raised on an include the gate only WARNs about (an optional
  include through a variable, and a required include behind a false
  conditional; 4 cases red, the source and the copy now give make one
  verdict); the `HOME` snapshot opened a FIFO a target left and blocked with no
  timeout, and raised on a socket (1 red, now each is recorded by its type and
  fails the target); check_W accepted `.` and `a/..` as a kept dir, which name
  `HOME` itself (3 red); and the `test_child_env.py` opt-in and the
  credentialed-proxy case named a proxy variable a project may not allowlist
  (red on a manifest with the proxy names dropped; the opt-in now takes a name
  the manifest allowlists, and the proxy case skips, naming why, when none is
  left).

**Residual risk.**
- A target that reads a kept XDG dir still sees the caller's files there, so a
  verdict can depend on the host through a cache or a config file under them.
- The gate runner itself does not sandbox `HOME`: only the sweep does.
- `_tiers()` in `tests/integration/test_empty_selection.py` and `_floor_report`
  in `tests/integration/test_gate_scope.py` parse the root Makefile alone, so a
  tier target an area defines is not seen.
- `copy_makefiles` does not copy an optional include named through a variable,
  so a copy runs without that makefile when the source has it; a required
  include named that way raises instead.

**Queued.**
- bedrock-platform's `keel_known_failures` entries for K5 and K6 become XPASS
  once it updates, and come out then.
- npm writes `~/.npm`, which is not an XDG dir: a `[local]` target that runs npm
  under the sweep would be failed for its cache. None does in keel today.

## CMP-4 — keel enforces what it claims, and emits evidence jarvis can read

**Why.** A generated project is told to work test-first, in bounded passes, with
end-to-end coverage and checked responses. On 2026-10-07 the maintainer asked
which of those keel enforces. Measured against the tree:

| Practice | What ships | Enforced by |
|----------|------------|-------------|
| Idempotency | `docs/guides/idempotency.md`, `effect:`/`rerun:` headers | check_V and `tests/integration/test_idempotence.py` |
| TDD | `docs/guides/dev-loops.md`, the mirror-test rule | the mirror rule only; nothing proves a test can fail |
| Ralph loop | `docs/guides/dev-loops.md` | check_Z on plan tables and `tests/integration/test_work_trailers.py` on `Slice:` commit trailers; neither proves a pass converged |
| E2E, Python | `tests/e2e/`, two scenarios | nothing; both scenarios call the app in process, not over a socket |
| E2E, frontend | eslint and the type check | nothing; neither frontend has a test runner, so zero tests pass the gate |
| Actual responses | an empty `evals/` | nothing |
| SDD | `docs/specs/` | nothing; project-jarvis has requirement ids and a traceability check, keel has neither |
| Test generation | none | none |

**The boundary with project-jarvis.** keel judges one commit from its files
alone and keeps no history. jarvis keeps the ledger across runs and repositories
and starts the agents and workflows. A rule that can be judged from the files is
a keel check that jarvis reads; a feature that needs history, a schedule or a
database is jarvis's. jarvis monitors keel's own development by tracking keel as
one of its projects, not by keel carrying the spine.

**Cap.** Eight slices, each one commit on a green `make verify`, in this order.
The two documentation slices, S1 and S3, were added at the maintainer's request
to audit documentation before Campaign 4's enforcement work. The maintainer
chose to insert S2 to fix a defect a downstream project hit updating to 0.2.1,
to be released as 0.2.2.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-4.S1 | A newcomer cannot learn what keel offers, its limits, or how to adopt and upgrade it from docs that cannot silently drift | done — `make verify` green (1771 passed); 11 of 12 review findings confirmed and fixed |
| CMP-4.S2 | An update whose config/project.json holds a merge conflict stops with a JSON error from the first migration, and no later migration runs | done — `make verify` green (1822 passed); 3 of 4 review findings confirmed and fixed |
| CMP-4.S3 | No catalogue lists every feature and no reference lists every setting, so a newcomer cannot see what exists or how to configure it | done — `make verify` green (1841 passed); 10 of 10 review findings confirmed and fixed |
| CMP-4.S4 | `make verify` reports only an exit code and log text, so nothing outside the repo can read which gate ran, on which commit, with what result | done — `make verify` green (1906 passed); 6 of 6 review findings confirmed and fixed (two reviewers found the same defect) |
| CMP-4.S5 | A frontend has no test runner, so it ships with zero tests and the gate is green | done — `make verify` green (1924 passed); 6 of 7 review findings confirmed and fixed |
| CMP-4.S6 | The e2e scenarios call the app in process, and nothing checks that a route has a scenario | done — `make verify` green (1973 passed); 4 of 5 review findings confirmed and fixed |
| CMP-4.S7 | Nothing calls a real model or a running server and judges what comes back | done — `make verify` green (2149 passed); 5 of 5 review findings confirmed and fixed |
| CMP-4.S8 | A spec's requirements are not tied to tests, so an uncovered requirement passes the gate | done — `make verify` green (2465 passed); 13 of 13 review findings confirmed and fixed |

- **CMP-4.S1, documentation truth.** Every stale claim the documentation audit
  verified is fixed in place, and a drift test refuses a shipped document that
  names a slice id, a host-specific phrase, an undeclared loopback port, or a
  document the template never ships. The README is reworked for a newcomer.
- **CMP-4.S2, a conflicted manifest stops an update by name, and the update
  can be finished.** Every copier job refuses over a conflict hunk in a fixed
  project file its modules declare reading, naming the file, the line and the
  command that finishes the update; `scripts/jobs/finish_update.py` is that
  command, replaying the after-migrations copier never reached. The
  downstream update is replayed end to end in a template-only test, and the
  finish command's `--dry-run` is checked against the migrations copier runs.
  Review found the guard's union over a job's imports refused the restamp
  over files only check_structure reads (a conflicted Makefile stopped the
  last migration); the restamp no longer imports check_structure, and a test
  fails a job whose imports hold a reading module it takes only constants
  from.
- **CMP-4.S3, the feature catalogue and settings reference.**
  `docs/reference/features.md` lists every feature and
  `docs/reference/settings.md` every setting, each held to the tree by a drift
  test.
- **CMP-4.S4, the evidence contract.** `make verify` writes a canonical JSON
  record next to its exit: commit, gate targets run, per-target result, test
  counts, check letters and their findings. It is written under an ignored path
  and is byte-identical on a second run of the same commit. The schema is typed
  and versioned, and a test holds the record to it. This is the format
  project-jarvis ingests; the ingest itself is jarvis work.
- **CMP-4.S5, frontend tests.** Each shipped stack gets a unit runner (Vitest)
  and a browser journey (Playwright, run headless against the built site),
  wired into the gate behind the existing `node_modules` skip. A stack with a
  runner and zero tests fails the gate.
- **CMP-4.S6, Python e2e over a socket.** One scenario starts the real server on
  a free loopback port, drives it over HTTP and stops it. A check fails when a
  route or transport endpoint has no scenario naming it (CONVENTIONS §17).
- **CMP-4.S7, evals that judge actual responses.** A dataset format, a scorer
  and a threshold gate in `evals/`. The default mode replays recorded responses,
  so `make verify` needs no network and no credential; a `[cost]` target runs it
  live through `models/` and the `child_env` allowlist.
- **CMP-4.S8, spec-to-test traceability.** A generic requirement-id grammar and
  a check that every requirement in `docs/specs/` is named by a test or by a
  documented gap, lifted from project-jarvis's `scripts/traceability_matrix.py`.
  jarvis's own copy is then retired in favour of keel's on update; that is a
  jarvis change and needs the maintainer's yes. The live status of each
  requirement stays in jarvis's ledger.
  The maintainer narrowed S8 to requirement-level coverage, with ids ready for
  acceptance criteria. An id is `<requirement-id>` or
  `<requirement-id>#AC-<n>`, where `n` is a positive integer with no leading
  zero. A spec defines a criterion with a line `- AC-<n>: <text>`. A bare id does
  not cover a requirement that has numbered criteria: each criterion needs its
  own test marker or a gap row. Which prefixes name a requirement comes from a
  `traceability.id_prefixes` registry in config/project.json; an unlisted
  prefix fails closed and the longest prefix wins. keel copies the registry's
  key and family list from project-jarvis, which lands it first. A test file
  names a requirement and is never itself evidence that the requirement is
  built, and each requirement gets exactly one verdict. Coverage
  statuses, a requirement hierarchy and mutation evidence are out of S8.

**Queued for Campaign 5.**
- `make new-test MODULE=` writes a mirror test that fails until it is filled in.
- Proof that a test can fail: mutation testing over changed code.
- The vault backlog: KEEL-FE-2, then FE-1, then FE-6; FE-3; TEST-1 (no test
  touches a live store); SEC-1 (secrets scan).
- The agent and playbook contract, the seed of keel-lite: a design document
  and an ADR before any code.
- project-jarvis side, in jarvis's repository: register keel as a tracked
  project and ingest CMP-4.S4's record and the `Slice:` trailers.
- The D0 decisions the documentation audit left open: each dead key is wired
  or deleted; the manifest defaults (`runtimes.default`, `models.default`)
  drive the registries or stay declarative; the example TOMLs are labelled as
  patterns or get a loader; each gate that passes on a skip fails closed or
  stays a stated skip; check_D's scope, and whether it takes a waiver.
- `make new` is not refused in a generated project, where it has no template
  to copy.
- Every installed value comes from config, and a doc states it beside its
  key: the REST port the Makefile `run-api` and `run-web` recipes spell out,
  the Astro proxy fallback, and the registry defaults move into
  `config/project.json`; a drift test reds a reference default with no source.
- Left by CMP-4.S5. A frontend suite whose tests are all skipped exits 0,
  because neither runner reports a count the gate reads. CI runs no
  `test-fe`. Whether a missing browser stays red, rather than a stated skip, is
  the maintainer's call. react-vite ships no lockfile, so its resolved versions
  float within its ranges. A copier copy from a dirty tree also copies
  untracked files, such as a stray symlink at the repo root, into the
  generated project.
- Left by CMP-4.S6. A generated project with the `grpc` transport ships
  `grpc /thing.v1.ThingService/CreateThing` in `e2e.exempt`, because no gate
  generates the gRPC stubs or installs `grpcio`; a gate that does both, a
  scenario that calls the method, and deleting the exemption close it. A
  test run killed by SIGKILL still orphans its uvicorn server, because only
  SIGTERM and SIGHUP are caught and nothing asks the kernel to end the server
  with its parent.
- Lane and gate tooling ships from keel: clone the commit, run the gate
  through a neutral batch-scheduler adapter (local by default; the farm's
  submit command and limits in config), and merge fast-forward only on a
  green gate of that exact commit, off unless a project turns it on.
- conflict_guard precision (a union over the import closure); finish_update
  gaps (StrictUndefined, `_jinja_extensions`, private-remote credentials); a
  conflicted entry module or conflict_guard itself still tracebacks.
- Left by CMP-4.S7. The shipped recordings are hand-authored
  (`recorded.source: authored`); no model output is recorded until the
  maintainer approves a first paid `make eval-live` run and promotes its
  candidates by hand. One threshold, `evals.threshold`, governs replay and
  live; a separate live threshold has no consumer until that run. A
  JSON-Schema scorer and a model-as-judge scorer are not built. A refused `evals.report_dir`
  cannot be given a red placeholder report, so an earlier report can stand
  beside a red gate.
- Left by CMP-4.S8. A requirement heading with a colon after its id
  (`## REQ-0001: Title`) is refused with exit 2; whether the one parser takes
  an optional colon is the maintainer's call. `make trace` reads what pytest
  collects from source, so `collect_ignore`, `--ignore` and a collection hook
  are seen only by the comparison in `make test`. A refused `traceability`
  block leaves an earlier matrix standing, because the command cannot know
  the matrix path. `docs/specs/example-feature.md` arrives on `copier update`
  and reds `make trace` in a project that deleted the example test.
  project-jarvis holds its own `traceability` block with a `kind_evidence`
  key this loader refuses, so sharing one registry waits for a mapping
  decision. `scripts/gate_evidence.py` writes under `evidence.dir` without the
  symlink check `scripts/git_tree.py` now holds, and `scripts/run_evals.py`
  takes its `--help` text from the wrong docstring line. The mutation proof is
  hand-written mutants, not a mutation runner.
- The maintainer's coding rules get a kernel and checks, in this order: one
  config loader every value comes through (a default applies only when a key
  is not set and prints one `[using default]` line naming the key and the
  config file; a key that is set and wrong fails; a secret, a host or a
  live-store path has no default); one exit helper with a closed list of
  codes and a table held equal to it; checks for what a helper cannot carry
  (text matching as a last resort with a stated reason, the import boundary,
  a bare `except`, a comment that reports a change); typed inputs read once
  at the edge and a log helper that writes fields. The existing pattern
  matches are listed in config and that list may only shrink.
- Proposed by project-jarvis from its own lanes and reviews. A write path
  never migrates a store: it refuses one below the current schema and names
  the migrate step, and a test holds the store's bytes unchanged on every
  refused or failed write. Every list of guarded things has a test that fails
  when an entry is removed. A module docstring's claim about behaviour is
  asserted by a named test. Every persisted field is a closed list, an open
  list or a validated format. A grammar with one home is imported, never
  copied. Time bounds in tests take their load margin from config. A
  git-ignored config the gate needs ships as an example, and the gate's first
  step names the copy command. A tool resolves lane placeholders at land and
  merges the changelog and the ledger without conflict (with the lane and gate
  tooling above). The template `.gitignore` covers the directory a browser
  automation server leaves at the repo root.

## CMP-5 — the coding rules move from text an agent reads into code the gate runs

Campaign 4 delivered its eight slices. The maintainer approved this campaign's
order on 2026-10-12. The cap is five slices, each one commit on a green
`make verify`.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-5.S1 | A script exits with a bare integer from any line, so nothing holds the rule that every exit has a code from one closed list and a message saying what failed, on which input and what to do next | done |
| CMP-5.S2 | `scripts/gate_evidence.py` writes under `evidence.dir` without the symlink check `scripts/git_tree.py` holds; `scripts/run_evals.py` reads any git failure as "no git"; a full verify on a dirty tree turns red when the date changes during the run; exit code 3 has one name for two meanings; the `openai-compatible` adapter sends a credential to any host config names; a project's own scripts that call `sys.exit` are rewritten by hand after an update | done, except the rewriter, which is queued (below) |
| CMP-5.S3 | A long script runs wherever it is called, so on a shared host it takes the CPU other people are using; nothing in the tree submits it to a job farm or limits it | done |
| CMP-5.S4 | The rules a helper cannot carry (the import boundary, a bare `except`, text matching without a stated reason, a comment that reports a change) are held by review alone | done, except the `re` allowlist and the warn-then-fail tier, which are unstarted (below) |
| CMP-5.S5 | A module reads config, the environment and its own defaults directly, so no one place applies a default, reports it, or refuses a wrong value | done — `make verify` green (3260 passed); 7 of 7 review findings confirmed and fixed; ADR-K-0022 accepted |

**CMP-5.S1, the exit helper.** A closed enum of exit codes, one helper that is
the only place a process exits with an error, the exit-code table in
`docs/guides/limits-and-troubleshooting.md` generated from the enum, and two
gate checks that read the syntax tree: an exit outside the helper is red, and
an enum member the table does not name is red. It reuses the per-script
exit-code reader in `tests/integration/test_doc_drift.py`. The slice chose three
points the maintainer can still change: a script that returns a wrapped tool's
own code says so with `passthrough(...)`; `main` returns an `ExitCode` member
and the entry line is `finish(main())`, for every script; and the two checks are
the gate test `tests/integration/test_exit_gate.py`, not structure-gate letters.
The helper is stdlib-only and runs under the old interpreter
`scripts/gate_evidence.py` supports.

Left by CMP-5.S1:

- The gate test does not reach an exit through `getattr`, `os.abort`, `os.kill`
  or an uncaught exception, argparse's own `--help` and usage exits in a script
  that does not catch them, or a `python -c` line in a makefile.
- The hand-written `| Script | When |` table below the generated region of the
  limits guide is compared with nothing.
- The gate test fails a blank message part, not a useless one, and the migrated
  messages were not read one by one for advice repeated between `on` and
  `next_step`.
- A conflict in `scripts/exit_codes.py` itself ends an update-finishing job with
  exit 1 on a `SyntaxError`, not the one-line exit 2 every other conflicted
  file gets.
- A project's own script that calls `sys.exit` is red after `copier update`
  until it ends through the helper, and no migration rewrites it. Whether that
  arrives as a failure or as a warning for one release is the maintainer's
  decision before the release that ships it.

**CMP-5.S2, the gate residuals.** Ranked second because three of its parts are
security findings. It closes the three residuals in its row. It splits exit
code 3 into two members, one for a red evidence record and one for an absent
live backend, each with its own number; neither script that returns 3 is in a
released version, so no released caller reads the number. A test drives each
script through its command line and reads the exit status and the message. It
adds a host allowlist for the adapter's `base_url` in config, where an empty
list refuses every host. It adds a rewriter that moves a script whose entry
line is `sys.exit(main())` to the helper, and lists by file and line the exits
it cannot move. Whether a project's remaining exits fail on arrival or warn
first is still the maintainer's decision; the slice keeps the failure.

**The rewriter is not built in CMP-5.S2, and is queued on its own.** Rewriting
`sys.exit(main())` to `finish(main())` does not preserve what a script exits
with. A script that has not adopted the helper returns bare integers or `None`
from `main`, and `finish` in `scripts/exit_codes.py` exits 2 for any value that
is not an `ExitCode` member: `finish(0)`, `finish(1)` and `finish(None)` each
exit 2, measured on the working tree. The rewrite also leaves the gate red:
`tests/integration/test_exit_gate.py` reports `finish(main())` over a
`main` that returns `0` as "returns a value that is not an exit code", so the
finding only moves from the entry line to the `return`. A rewriter limited to
the scripts whose every return is already a member would move almost none of
the 37 plain-form exits measured in one generated project. The shape
`finish(passthrough(main()))` passes the gate and exits 0 for a `0`, but it
labels a script's own status as a wrapped tool's, and it exits 1 with a
traceback when `main` returns `None`. Building it needs one decision first:
(a) also rewrite `return 0`, a bare `return` and falling off the end to
`ExitCode.SUCCESS`, and list every other return, because no tool can write the
three message parts of a failure; (b) give the helper a bridge for a legacy
integer, which weakens the contract CMP-5.S1 gated; or (c) accept the
`passthrough` shape and its mislabel. Its make targets are `[tree]` for the
writer and `[local]` for the check, not `[write]`: it changes only working-tree
files, like `make exit-codes`, and
`docs/adr/keel/K-0011-make-target-effect-labels.md` reserves `[write]` for
shared remote state. Until it lands, the steps under "Your own scripts end through the exit
helper" in `docs/guides/generate-and-upgrade.md` are the upgrade path.

Left by CMP-5.S2:

- `models.allowed_hosts` admitted a listed host over `http` as well as
  `https`. Decided since: `http` is refused unless the host is a loopback
  address literal, `docs/adr/keel/K-0018-model-endpoint-host-allowlist.md`
  Decision 8.
- `tests/integration/test_exit_gate.py` accepted `finish(passthrough(main()))`
  over a `main` that returns a script's own integers, so a script could pass
  the gate without returning members. Closed in CMP-5.S4 (see the CMP-5.S4
  note).
- `scripts/trace_requirements.py` refuses a missing `git` inside a repository,
  while `scripts/gate_evidence.py` and `scripts/run_evals.py` take the no-git
  path. The two readings are not unified.
- Every commit the test suite makes inside one gate run carries the same
  moment, so a test that needs commits in date order sets its own dates.
- The behaviour of the run date's local offset across a daylight-saving change
  is not tested.
- A gate that runs longer than `evidence.run_date.max_age_days` (1 day in
  `config/project.json`) has its later checks refuse with exit 2.

**CMP-5.S3, the launcher.** One neutral launcher in `scripts/` decides where a
long script runs: on a host that is one person's own it runs as normal; on a
shared host it submits to a job farm through an adapter, sized from config; a
full farm means wait, or run on the shared host only when that host has spare
compute; with no farm it runs limited. It says in one line what it decided and
why. Which scripts are long comes from a list in the repo, a search script
that proposes entries, and the recorded duration of each script's last run.
This is the "neutral batch-scheduler adapter" of the lane and gate tooling
item in the Campaign 4 queue, without the lane and merge parts. Open for the
maintainer: how a host is known to be shared without a host name in the repo,
and which scripts are local only because they need a credential, a network
route or a lock the farm does not have.

As built, a host is shared unless a pattern in a git-ignored local file
matches it, and `launcher.local_only` ships empty: a project lists its own
local-only scripts with a reason. The farm adapter ships as `none`, so a
generated project runs a long script here at a lower CPU priority until it
names a farm. Recorded residuals are in
`docs/adr/keel/K-0020-shared-compute-launcher.md` "Consequences": a command
that exits a reserved farm status is read as the farm's, the run record is
last writer wins, and a farm job's seconds include its queue time.

Left by CMP-5.S3:

- A run interrupted with Ctrl-C (exit 130) is a measured run, so a short
  interrupted run replaces an earlier long record and `make long-scripts`
  stops proposing that key until it runs long again. A farm that never starts
  the job and a killed run keep the earlier long record.
- `make long-scripts` exited 1 when it judged no run, the same code as "it
  proposes a key". Decided since: it exits 13, `ExitCode.NOTHING_JUDGED`, a
  member of its own that is still non-zero (see the CMP-5.S4 note).
- The CONVENTIONS §2 note says `scripts/` holds two importable modules and
  only these two, while the tree now imports more shared modules from
  `scripts/` (the exit helper, `git_tree.py`, `run_date.py` and the launcher).
  The note and the list in `scripts/AGENT.md` are not reconciled.
- `tests/hermetic_git.py` `clone_including_worktree` replays only
  `git diff HEAD`, so a new file not added with `git add -N` is missing from
  the clone the copier audit tests read, and those tests fail on a fresh
  branch until it is.
- `KEEL-TEST-1` (a test cannot reach a live store) and `KEEL-SEC-1` (a secrets
  scan) head Campaign 6; the choice of scanner is the maintainer's.

**CMP-5.S4 and S5** are the tree-wide checks and then the config loader. The
checks come first because they count the direct config reads the loader has to
replace. S4 also takes one rule from CMP-5.S1: a shipped gate test or a shared
helper module with no row of its own in `docs/reference/features.md` is red.

**CMP-5.S4, done.** Two gate holes close first. `$(WRITE_GUARD)` opens with
a make-level `$(error)` when `i` is among make's flags (`-i`,
`--ignore-errors`, `MAKEFLAGS=i` or a bare `.IGNORE:`), because make expands
it before the recipe's first line and an ignored shell `exit 1` stops
nothing; check_W fails any `.IGNORE` rule, since a `.IGNORE: <target>` rule
leaves MAKEFLAGS untouched. `tests/integration/test_write_guard.py` drives
each form. `make test-fe-unit` and `make test-fe-e2e` exit 2 when an app is
declared and `npm` or its `node_modules` is missing, `make fe-browsers` fills
the browser cache, and `.github/workflows/ci.yml` runs both before
`make test-fe` (`tests/integration/test_gate_scope.py`). This closes open
items 1 and 2.

Three of the four tree-wide checks are gate tests
under `tests/integration/`, sharing one reader, `tests/source_tree.py`:

- `test_import_layers_gate.py` holds imports to config/project.json
  `import_layers.order`, and check_D also fails `from pkg import _sub` of a
  private submodule from outside `pkg`. A module another project module
  imports never calls `fail` or `finish`, which `test_exit_gate.py` enforces.
  `docs/adr/keel/K-0021-imports-flow-up-a-configured-layer-order.md` is the
  decision, and it is accepted.
- `test_swallowed_error_gate.py` fails a bare `except:` or a broad `except`
  that only drops the error, unless its `# noqa: BLE001` or `# noqa: E722`
  gives a reason.
- `test_change_comment_gate.py` fails a comment that opens with a phrase in
  config/project.json `change_comments.phrases`.

The allowlist of modules that may match text with `re` (open item 88) is
unstarted, and stays so until it has a slice of its own. A measurement found
45 modules that import `re`, 24 of them under `tests/`, so the list needs a
written reason for each entry. Its entries for the files copier prunes go
stale in every generated project, a project's own `re` calls turn red on
arrival, and the warn-then-fail tier it leans on was unbuilt then (CMP-6.S4
built it).

The exit gate also closes open item 10. `scripts/exit_code_table.py`, which
`test_exit_gate.py` reads through, finds a `passthrough` handed the script's
own status: the entry function's result, directly or through a plain-assigned
name, an int literal, a member, a `report`, or a call to a function of the
module whose every return is one of those, also under a sign (`-1`), combined
with `or` or arithmetic, or through a builtin the module does not rebind
(`int(main())`). It finds an entry line
`finish(passthrough(...))` too. A helper that converts another process's
status, such as `scripts/run_app.py` `_app_status`, passes by design, and so
does a function some of whose returns are the script's own literals and
others a tool's status; the gate cannot tell those apart from the tree.
`ExitCode.NOTHING_JUDGED` is 13, and `scripts/long_scripts.py` exits with it
when no recorded run carries a duration; a proposal stays exit 1.
`tests/unit/scripts/test_exit_codes.py` holds 13 outside the bands other
programs use, the launcher's reserved statuses and every farm status
config/project.json configures.

The features-row rule taken from CMP-5.S1 is in place.
`tests/integration/test_reference_drift.py` `derived_features` adds two
groups: each `tests/integration/test_*_gate.py`, and each `scripts/` module
another module outside `tests/` imports, read from the import graph through
config/project.json `import_layers.search_roots`. `docs/reference/features.md`
carries a row for each in its `Gate tests` and `Shared script modules`
sections, or under another role the module plays, and the test fails a
member with no row. The CONVENTIONS §2 note now states no count and cites
that derivation, which the same test checks, closing open item 98. A
generated project has fewer shared modules than the template, because copier
prunes `scripts/audit_project.py`, so no count is pinned anywhere.

The warn-then-fail tier for a project's own code (B1, open item 11) was
unstarted then, with nothing of it in the tree; CMP-6.S4 built it. Its rule needs a project's gate
to tell a file keel ships from one the project wrote, and the one place that
fact is derived is `scripts/audit_project.py` `origin_of`, which lists the
template's git tree at the project's `_commit` through `_tree_at`, run in the
template checkout. copier's `_exclude` prunes that script and every
`tests/integration/test_copier_*.py`, and a generated project carries no list
of the files keel shipped: `.copier-answers.yml` records only the answers,
`_commit` and `_src_path`. Building the tier therefore needs one of three
things the maintainer has not chosen: a shipped manifest of keel's files (a
third rule beside the audit and the copier tests), a fetch of the template
inside `make verify` (a network dependency in the gate), or the rule "a
finding in the template repository is red, a finding in a generated project
warns until the date", read from whether `copier.yml` exists. The last needs
no manifest, and a fresh project is green under every answer set
(`tests/integration/test_copier_generation.py`), so a finding after an update
is in a file the project wrote or edited. It is still a third rule, and it
also warns on a keel file the project edited. The date is not ruled either:
the brief proposed 2027-01-31, and no config key carries it, because a key
nothing reads is a key with no consumer.

Left by CMP-5.S4:

- The `re` allowlist (open item 88) and the B1 warn-then-fail tier (open
  item 11) are unstarted; the note above gives what each needs. CMP-6.S4
  built the tier.
- Under a recursive `$(MAKE)` with `-i` on the outer make, the inner guard
  stops the write, but the outer make ignores that error and exits 0.
- `make lint-fe` and `make typecheck-fe` still print a skip and exit 0 when
  `npm` or an app's `node_modules` is missing.
- keel's own `make verify` on a fresh checkout is red at `test-fe-unit` until
  `make fe-install` has run, by design. CI downloads the browser on every run
  with no cache.
- The change-comment check reads only the phrase that opens a comment, so a
  change reported mid-sentence or in other words passes; two such comments
  remain (`mcp/protocol.py`, `tests/integration/test_copier_generation.py`).
- copier's `run_copy` with `vcs_ref=HEAD` on a dirty tree copies untracked
  files, so a local untracked file at the template root reaches a project
  generated from a working tree.
- `tests/integration/test_copier_generation.py` and
  `tests/integration/test_copier_audit.py` run near a 90-minute farm job's
  limit when run on their own on one CPU.

Left by CMP-5.S5:

- Twelve files still read config directly, each named with its reason in
  config/project.json `config_reads.allowed`, and
  `tests/integration/test_config_reads_gate.py` `_CEILING` keeps the map from
  growing. Nine are queued for a later CMP-5 slice: `scripts/check_structure.py`,
  `scripts/launch.py` with `scripts/long_scripts.py`, `scripts/run_app.py`,
  `scripts/trace_requirements.py`, `scripts/jobs/export_showcase_static.py`,
  `src/backend/showcase/_repo.py`, `src/backend/shared/__init__.py` and
  `agents/practice_refactor/_brain.py`. Three are not config reads and stay:
  `scripts/audit_project.py`, `scripts/jobs/declare_no_app.py` and
  `scripts/jobs/restamp_docs.py`. Until a module moves, its config fault exits
  2, not 14.
- The gate tells keel's files from a project's own by where it runs, as the
  B1 ruling reads it: in the template repository a finding is red, and in a
  generated project, which carries no list of keel's files, its two finding
  tests skip and name each direct read in the skip reason. That skip is the
  B1 residual (open item 11): the warn-then-fail tier turns it into a warning
  that goes red on the ruled date. CMP-6.S4 replaced the skip with the tier. A project's own reader needs no room under
  `_CEILING`, since nothing there turns red.
- `scripts/config_loader.py` has no rows for the `launcher`, `traceability`
  and `layers` blocks, so the modules that read them cannot move yet.
- Defaults that are code literals remain: the `models/openai_compatible.py`
  constructor's `base_url`, `model`, `api_key_env` and `timeout`, and the
  `.get(key, default)` calls `scripts/check_practices.py` makes on each
  config/practices.json list item. Neither is a `KEYS` row, so neither writes a
  `[using default]` line.
- `mcp/qa_server.py` ends with a traceback, not a `report(...)` line, when
  `KEEL_MCP_MODEL` holds a blank value: its `__main__` block calls
  `configured_model` with no handler.
- Importing `scripts/child_env.py` now puts config/practices.json among the
  files `scripts/jobs/conflict_guard.py` refuses a copier job over, because
  the loader declares both files in `PROJECT_READS`.
- [ADR-K-0021](../adr/keel/K-0021-imports-flow-up-a-configured-layer-order.md)
  names the bottom layer's members as "the exit helper and the
  child-environment allowlist"; the configured order now holds
  `scripts/config_loader.py` there too. The ADR is accepted, so it is not
  edited; [ADR-K-0022](../adr/keel/K-0022-one-config-loader.md), accepted,
  states the placement.

**Cut from this campaign.** Typed inputs with a log helper, planned here
before, is queued again to make room for the launcher. Everything else in the
Campaign 4 queue stays queued: the lane and merge parts of the lane and gate
tooling, the frontend backlog, the mutation runner,
`make new-test`, the agent and playbook contract, the D0 decisions,
project-jarvis's proposals, and the residuals of CMP-4.S5 to S8 not named in
CMP-5.S2. The header fields per code file are accepted after CMP-5.S4 and queued
for Campaign 6.

## CMP-6 — a generated project is proven whole, and the two high gaps close

The maintainer approved this campaign on 2026-10-17. The cap is five slices,
each one commit on a green `make verify`. Slices 1 to 3 are what a project
using keel relies on; slices 4 and 5 hold keel's own rules. After this
campaign the low open items are triaged in one read-only pass, and the next
work comes from dogfooding a real project rather than from the backlog.

On 2026-10-18 the maintainer asked for the rest of the campaign to run under
keel's rules and the vault rule packages at 0.10.0, with safeguards added
where they raise code quality. The cap becomes six slices: CMP-6.S6 is
KEEL-AGT-1, the one high gap the 0.10.0 audit found, because an agent edit
that can reach its own judge undoes every other safeguard. The stop point is
CMP-6.S6 green or the sixth slice reached, whichever comes first.

On 2026-10-20 the maintainer replaced CMP-6.S5 with the gap the first full
`make verify` on the farm found. That run started from a clean checkout and
from a parent `make`, which no earlier run had done, and two tests failed. The
header fields and the `re` reason move to the queue as KEEL-HDR-1.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-6.S1 | Each part of a generated project is tested on its own, but no test runs a generated project's full `make verify`, or `make verify` after `copier update` from the previous tag; nothing checks that each frontend app commits its lockfile, or that CI's Node version is the one the gate is run with | done — `make verify` green (3321 passed); the real canary passed both answer sets, fresh and updated from v0.3.0; 9 of 10 review findings confirmed and fixed; ADR-K-0023 proposed |
| CMP-6.S2 | KEEL-TEST-1: a test can reach a live store; nothing in the suite refuses it | done — `make verify` green (3456 passed) with `KEEL_TEST_SCRATCH` on local disk; the guard caught four tests in keel's own suite, all fixed; 13 of 13 review findings confirmed and fixed; ADR-K-0024 proposed |
| CMP-6.S3 | KEEL-SEC-1: nothing scans the tree for a committed secret | done — `make verify` green (3662 passed, with CMP-6.S5 and CMP-6.S6); the keyed gate, the scanner adapter and the wiring are built; 9 of 11 review findings confirmed and fixed; the targeted gates are green (337 passed, check-docs, check-exit-codes, mypy); the scanner installs through the pinned pre-commit hook here and is not yet run in GitHub CI; ADR-K-0025 proposed |
| CMP-6.S4 | B1: a generated project's own code that breaks a keel gate check is red on `copier update` (the exit gate) or not judged at all (the config-reads gate skips); the ruled warn-then-fail tier is not built | done — full `make verify` green on the tree rebased onto main 2b7e8c3 |
| CMP-6.S5 | The audit's suite is not hermetic: from a dirty template checkout the audit never takes copier's three-way path, so a clean checkout reaches untested code; when an `after` migration refuses over a fault the audit already reports as owed, the audit exits 2 instead of reporting it; and a test that drives `make` inherits the parent `make`'s `MAKEFLAGS` (K-0011) | done — `make verify` green (3662 passed); the old audit fails the hermetic fixture exactly as the farm run did, and the fixed audit passes it |
| CMP-6.S6 | KEEL-AGT-1: an agent's edit can reach the code that judges it; `scripts/apply_refactor.py` refuses only a path outside the repo root | done — `make verify` green (3544 passed); an agent edit to a protected or untracked file, or a spec that names its own gate, is refused before any write; 10 of 10 review findings confirmed and fixed; ADR-K-0026 proposed |

**CMP-6.S3, the scanner.** The maintainer ruled on 2026-10-17: keel's own
rule is a gate test, and a scanner is a thin adapter behind it. The gate test
fails a committed file that holds a value under a key
`scripts/config_loader.py` `KEYS` marks secret. The scanner covers the shapes
no key names; gitleaks is its default, chosen in config, and another scanner
is a second adapter, not an edit to the test.

**CMP-6.S1, the release canary.** `make canary` (`scripts/canary.py`) renders
each config/project.json `canary.answer_sets` set from a snapshot of the
checkout, fresh and as a `copier update` from the newest released tag that is a
strict ancestor of HEAD, and runs the project's own `make verify`, after
`fe-install` and `fe-browsers`, which exit 0 with no frontend app. A pass is deleted and a
failure is kept with its log. CONTRIBUTING.md's Release steps run it on the farm
before the push, `launcher.long_scripts."make canary"` sizes the farm job, and
`.github/workflows/canary.yml` runs it weekly and on demand. The audit and the
canary share one snapshot, `scripts/template_snapshot.py`, lifted out of
`scripts/audit_project.py`.

`tests/integration/test_frontend_lockfile_gate.py` fails a frontend app whose
lockfile git does not track or whose lockfile root entry disagrees with its
manifest. config/project.json `toolchain` holds the Node major, the Python and
the runner images; `tests/integration/test_toolchain_gate.py` holds every
workflow and the `fe-install` recipe to it, and `scripts/check_toolchain.py`
prints the versions for CI and refuses another Node major before npm runs.

Left by CMP-6.S1 so far:

- The first farm run of every set and path passed: `default` (react-vite, the
  showcase, every transport) fresh in 454 s and as an update from `v0.3.0` in
  494 s, and `skeleton` (no frontend, no showcase, gRPC only) in 404 s and
  441 s. One job per set, `canary.workers` 1, so the whole canary is about 31
  minutes in one job. `launcher.long_scripts."make canary"` asks for 360
  minutes, 8 cores and 16 GB, which is provisional: each job used under one core
  on average (12 and 15 CPU-minutes over 14 and 16 minutes) and peaked near
  320 MB of resident memory.
- The farm nodes' CA bundle lacks the root the site's TLS interception signs
  with, so a browser download there fails; the measured `default` run used a
  copy of the browser build through `PLAYWRIGHT_BROWSERS_PATH`, and `fe-install`
  may have been served from npm's cache. A browser download on the farm is not
  proven; the workflow, which installs the browser's system libraries first, is
  where it is.
- The astro stack is in no answer set, so no canary renders it.
- config/project.json `launcher.farm.adapter` is `none` in the template, so
  `scripts/launch.py -- make canary` runs the canary on this host, limited, until
  a maintainer configures a farm adapter; the measured runs were submitted to the
  farm by hand, sized as the `launcher.long_scripts` entry says.
- `make canary` is `[read]` and has no `make_targets.effect_proof_skip` entry:
  it writes only under the git-ignored `canary.scratch_root`, so the local-target
  proof would judge a target the gate runner never runs, and a skip entry for a
  target that is not local would fail `test_every_skip_names_a_local_target`.
- The workflows read the Node major and the Python from config/project.json
  `toolchain` through a `toolchain` step, and `make fe-install` refuses another
  Node major before npm runs. CI moved from Node 22 to 24 with it, to the
  major the maintainer's host runs. Node 24 on the runner is not proven by a CI
  run in this slice, and the lockfile gate compares each manifest with its
  lockfile's root entry, not the tree npm resolves under a given major.
- `backend_python` is a specifier, not a release, so the template cannot
  derive the release CI installs from it; copier asks `toolchain_python` for
  it instead, and its validator refuses a release the floor does not allow.
  The validator judges plain releases only: a floor clause with a pre-release,
  a post-release or `===` is refused as one it cannot judge, not passed.
- The release order in
  [ADR-K-0016](../adr/keel/K-0016-release-order-tag-before-verify.md) does not
  name the canary step CONTRIBUTING.md's Release section now carries between
  the verify and the push. The ADR is accepted, so it is not edited;
  [ADR-K-0023](../adr/keel/K-0023-canary-gates-a-release-not-a-commit.md),
  proposed, records where the canary runs and that a red one blocks the release
  push and nothing else. It waits for the maintainer's acceptance.
- The guides are held to the canary by
  `tests/integration/test_canary_wiring.py`: the step table of
  `docs/guides/generate-and-upgrade.md` names each step a canary line can
  report as failed, found by failing each call into a project in turn, and the
  symptom table of `docs/guides/limits-and-troubleshooting.md` quotes the
  words of every `report(...)` message `scripts/canary.py` holds.
- Out of scope, and not yet a row of the open-items table: CI has no Python
  below `requires-python`, so the old-interpreter tests skip there. Three
  tests look for one: `tests/unit/scripts/test_exit_codes.py`
  `test_the_helper_runs_on_an_old_host_interpreter_when_there_is_one`, and
  `tests/integration/test_gate_scope.py`
  `test_precommit_python3_entries_actually_execute_on_an_old_interpreter` and
  `test_needy_targets_fail_with_the_floor_message_on_an_old_python3`. The CI
  run of 2026-10-17 (39053838083) reported 7 skipped in all; it runs pytest
  without `-rs`, so its log does not name the other four.

**CMP-6.S2, what a test may reach.** `tests/isolation_guard.py`, a Python
audit hook `tests/conftest.py` installs, fails a test that reaches past its
tier's row of config/project.json `tests.isolation.tiers` on the network,
writes or stores axis, even when the test caught the error. An exemption is
a reasoned entry in `tests.isolation.exempt`, and an unused one is red; the
`store_copy` fixture copies a store `tests.isolation.stores` lists into the
test's own directory. Test scratch goes under `tests.scratch_root`, never the
system temporary directory or the checkout.
`tests/integration/test_isolation_gate.py` and
`tests/integration/test_scratch_root_gate.py` prove both on planted cases, and
`tests/integration/test_isolation_docs.py` holds the docs to the guard.
[ADR-K-0024](../adr/keel/K-0024-what-a-test-may-reach.md) is proposed.

Left by CMP-6.S2 so far:

- The guard caught four tests in keel's own suite, all in
  `tests/integration/test_practice_refactor.py`: each wrote refactor
  checkpoints under the checkout's `wiki/.runtime`. Each now checkpoints
  under its own `tmp_path`, so `tests.isolation.exempt` ships empty on every
  axis. It is one class of reach, a default output path in the checkout,
  which the guard now catches for every test.
- The guard does not see a child process. `real_corpus` writes
  `wiki/corpus.json` through a child, and the gate tests that run make, git,
  copier or a nested pytest are unjudged inside it. A `sitecustomize` that
  installs the guard in every child Python is the candidate; it is not built.
- A nested pytest a gate test starts takes no `--basetemp`, so each makes its
  own numbered session directory under the inherited root, and pytest's
  retention count rotates them; one measurement found 74 MB of them under the
  root.
- The shipped `tests.scratch_root`, `~/.cache/project_keel/tests`, is under
  the home directory, which on this site is a network mount: the suite is
  slower there, and a directory's modification time moved between two
  snapshots with no write, which made `tests/unit/scripts/test_audit_project.py`
  flake until it stopped comparing directory times. `KEEL_TEST_SCRATCH` on
  local disk is the documented fix; no default is derived from the host.
- Keel's own `make verify` with scratch on that network home did not finish
  inside a 240-minute farm job, three times; with `KEEL_TEST_SCRATCH` on the
  node's local disk it took 2 hours 31 minutes of tests. A farm run of keel's
  gate sets the variable.
- A run killed by SIGTERM or SIGKILL leaves its session directory behind until
  pytest's count of 3 rotates it. `PYTEST_DEBUG_TEMPROOT` moves the basetemp
  past the root, and a `--basetemp` the caller gives is only checked against
  the system temporary directory.
- `tests/conftest.py` reads the basetemp through pytest's private
  `config._tmp_path_factory`, so a pytest release that renames it breaks the
  session start loudly, not silently.
- `store_copy` has no consumer in keel, which has no live store;
  `tests/integration/test_isolation_gate.py` proves it on a planted store.
  pytest-xdist is not used by the suite, so a judgement under its workers is
  not exercised.
- Three reaches no audit event decides. `os.mkfifo` and `os.mknod` raise no
  event, so a FIFO or device node outside the roots is not seen. The `open`
  event carries no `dir_fd`, so an `os.open` with a relative path and a
  `dir_fd` is judged against the working directory; a shim over `os.open` was
  rejected because `shutil` tests `os.open in os.supports_dir_fd` by identity.
  The `sqlite3.connect` event does not say whether `uri=True` was passed, so a
  `file:` name is judged both ways, and a `file:` URI opened while the working
  directory is outside the roots is refused even for a memory database.
- A metadata event does not say whether the call follows a link, so the
  guard judges both ends, except when the Python caller is `shutil.copystat`
  or `shutil._copyxattr` and its local says it stays on the link: without
  that, `shutil.copytree(symlinks=True)` of a tree holding a link that points
  outside was refused (six copier tests, through an untracked link at the
  checkout root). The exception reads CPython's local names; if a release
  renames them, both ends are judged again and such a copy is refused, loudly.
- A name lookup is not judged, by choice: library code such as
  `email.utils.make_msgid` looks a name up without reaching anywhere, and the
  connect that follows is judged.
- The gate tests this slice adds read their child timeout from
  config/project.json `tests.child_timeout_seconds`; 23 older `timeout=`
  literals in the suite are the existing pattern and are not moved.
- `scripts/jobs/finish_update.py` still clones under the system temporary
  directory: it is a copier job, not a test, and the half of KEEL-RES-1 it
  holds stays queued.

**CMP-6.S3, built as ruled.** The keyed layer,
`tests/integration/test_committed_secrets_gate.py`, takes its secret names from
the `scripts/config_loader.py` `KEYS` rows marked secret and judges every file
`scripts/git_tree.py` `candidate_files` lists. The scanner layer,
`scripts/scan_secrets.py`, the gitleaks adapter, runs the scanner
config/project.json `secrets.scanner` pins; the pre-commit hook pinned at `secrets.scanner.rev`
builds it, and `make secrets-install` records it. The commit hook
scans what a commit adds or changes, or every commit when nothing is staged, and `make secret-scan`, a `make
verify` goal, and CI scan every commit.
[ADR-K-0025](../adr/keel/K-0025-committed-secrets-keyed-gate-and-scanner.md) is
proposed.

Left by CMP-6.S3 so far:

- The record is trust on first use: a program named `gitleaks` that is first
  on `PATH` when `make secrets-install` runs is the one recorded, and a fake
  that writes an empty report passed the history scan by hand. The record
  catches a later swap, not the first.
- Measured by hand in a generated project, and not caught by either layer: a
  value split across two string literals; a weak password with no known
  shape; a credential in `package-lock.json`, an `.svg`, `go.sum`, a PDF or
  under `node_modules/`, which the scanner's default rules allow. A
  `--no-verify` or `SKIP=gitleaks` commit passes the hook and is red in the
  history scan. docs/guides/deterministic-checks.md lists every bypass tried.
- `make canary` runs `make secrets-install` in each project with
  `XDG_CACHE_HOME` inside the run, so pre-commit builds the scanner once per
  run. `GOPROXY` and the CA bundle variables are not in `child_env.names`, so
  on a host whose TLS is intercepted the canary's install may fail; the
  canary was not run in this slice.
- The README Quickstart does not install `api/rest_fastapi/requirements.txt`,
  so a generated project's first `make verify` was red in `typecheck`
  (fastapi and uvicorn not found) before it reached the secret scan, which
  passed. It is older than this slice and not fixed here.
- CI's two new steps are written and not yet run on GitHub. A commit whose
  message asks the provider to skip CI is not scanned there; the history scan
  in the next run's `make verify` sees it.
- One history scan of keel's 113 commits took 7.4 seconds on the network home
  directory, so the scan is of the whole history, not the pushed range.
- With `secrets` in `KEEL_REQUIRED_EXTRAS`, as CI declares it, the suite a
  generation test runs inside a just-generated project inherited the
  declaration and failed its scanner cases, because that project has run no
  `make secrets-install`. `tests/integration/test_copier_generation.py` now
  drops `secrets` for those runs; a project's own CI installs the scanner
  before its suite.

Left by CMP-6.S6 so far:

- An interactive agent's direct Edit or Write tool, outside
  `scripts/apply_refactor.py`, is not refused: config/project.json `agents`
  binds only edits that land through the doer. Closing it needs hooks or
  permission rules on the agent host, which are not built.
- A refusal's reason is not surfaced: the brains keep `apply_refactor`'s exit
  and drop its stderr, so a protected chunk shows as skipped like any other.
  Recording why needs a rejection ledger, not built and not queued under an id
  (the queue below gives KEEL-AGT-2 to the spend cap).
- A protected chunk is not filtered out before the model call, so a
  `doc_reviewer` finding in a protected document costs one call before the
  edit is refused: `agents/` sits below `scripts/` in config/project.json
  `import_layers.order` and cannot import `scripts/apply_refactor.py`
  `protected_by`.
- The frontend tests and configs the default project ships (`*.test.*`,
  `*.spec.*`, `tsconfig*.json`, `package-lock.json`) are listed in
  `agents.protected_names`, and a file git does not track is refused; a
  tracked judge a project adds under another name (the directory
  `structure.project_checks` names, the `make_targets.area_dir` makefiles) is
  protected only once listed in `agents.protected_paths` or
  `agents.protected_names`.
- `scripts/git_tree.py` does not pass `-c core.fsmonitor=false` to its own
  git calls: the tracked rule keeps an agent edit off `.git/config`, and the
  extra layer was left out of a file another slice also edits.
- A project that adds its own roster README must list it in
  config/project.json `rosters.readmes`, or check_S errors on it.
- `scripts/README.md.jinja` is a protected path while `scripts/README.md` is
  editable, and a run binds one file, so `doc_reviewer` cannot fix a twinned
  roster row in both: the edit to the twin is refused.

### Slice CMP-6.S4 — a project's own code warns until a hard date, from a record that only shrinks

**The gap.** A keel gate check judges every file under its roots. In a
generated project, a finding in a file the project wrote is red on the first
`make test` after `copier update` (`tests/integration/test_exit_gate.py`). The
other case is a finding that is never judged at all: the two finding tests of
`tests/integration/test_config_reads_gate.py` skip and only name what they saw.
Neither is the ruled tier. The maintainer's rulings (B1 and R-AGT-32 above, and
the two of 2026-10-22 below) fix its shape.

**What is judged.** A gate test that adopts the tier hands it every finding
line it computed, in the house grammar `<file>:<line>: <rule> — <fix>`, under a
check id. The tier gives back two lists: the lines that are red and the lines
that warn. The test asserts the red list is empty and raises one warning
carrying the warned list. Four tests adopt it in this slice:

| Check id | Test |
|----------|------|
| `config-reads-file` | `tests/integration/test_config_reads_gate.py::test_no_code_root_reads_a_config_file_outside_the_loader` |
| `config-reads-variable` | `tests/integration/test_config_reads_gate.py::test_no_code_root_reads_a_declared_variable_outside_the_loader` |
| `exit-helper` | `tests/integration/test_exit_gate.py::test_no_process_in_the_tree_ends_outside_the_helper` |
| `exit-shared-module` | `tests/integration/test_exit_gate.py::test_a_shared_module_never_ends_the_process` |

The registry is `CHECKS` in `scripts/expiring_tier_data.py`. A line outside the
grammar has no file, so no project wrote it. A stale
`import_layers.may_end_the_process` entry is one such line, and it is always
red. A finding's identity is its line with the line number dropped,
`<file>: <rule> — <fix>`, so an edit above a recorded finding does not turn it
into a new one. Identities are counted, so two equal findings in one file need
two entries.

**How keel's files are told from the project's.** This follows the B1 ruling:
by where the gate runs. When `copier.yml` exists at the root, the gate is in the
template repository. There every finding is red, nothing warns, and a baseline
file there is itself red, so keel gets no grace. Anywhere else is a generated
project. A fresh project is green under every answer set
(`tests/integration/test_copier_generation.py`), so a finding there is in a
file the project wrote or edited. The maintainer accepted that this also warns
on a keel file the project edited.

**New versus existing (ruling 9 below).** A generated project carries a
per-check baseline file. Its path is config/project.json
`expiring_tier.baseline`, and keel ships `config/gate-baseline.json` there. One
make target writes the file after `copier update`: `make gate-baseline`
(`scripts/record_gate_baseline.py`). The writer runs each registered test under
pytest's `--expiring-tier-record PATH` option. `tests/conftest.py` turns the
tier's recorder on for that run and, at the end of the session, writes what each
check saw to PATH. The recorder keeps a multiset, so two byte-identical
findings (two calls on one line) are two entries, and a check judged twice over
the same lines is not counted twice. The tier judges the same way in that run,
so the record is exactly the findings the gate sees. The writer then derives
the whole file:

- A check the run did not record is refused with `NOTHING_JUDGED` (13), and
  nothing is written.
- The file may grow only when `.copier-answers.yml` `_commit` differs from the
  `commit` stamped in the file, or when no file exists. In that case it takes
  every finding the run recorded and stamps the new `_commit`.
- When no file exists, the writer first asks git (scripts/git_tree.py `tracked`
  and `in_head`). A baseline that git's index or HEAD still holds was deleted,
  and a rewrite would lift the only-shrinks rule, so the writer refuses with
  `FAILURE` (1) and says to restore it with `git checkout -- <file>`. When git
  cannot answer (no git, no repository, or git failing), the writer refuses
  with `USAGE` (2) and writes nothing. That is fail-closed by choice: without
  git it cannot tell a first baseline from a deleted one, and `copier update`,
  the step the writer follows, already needs a git repository.
- At the same `_commit`, the file may only shrink. An entry no longer seen is
  dropped. A finding not already recorded is refused with `FAILURE` (1), naming
  each such line, and nothing is written. That finding is the project's own new
  code, and the rule says it is red at once.
- The output is canonical JSON with sorted keys and sorted lists, and no clock
  value. A second run on the same tree writes the same bytes (`rerun:
  fixed-point`).

The gate judges against the file:

- A recorded finding warns.
- A finding with no entry left for it is red. The message names `make
  gate-baseline` and says it records only after a `copier update`.
- An entry no finding matches is red and names the file to delete it from, so
  the record only shrinks.
- A check id that `CHECKS` does not register is red.
- A project with no baseline file has every finding red, and the message names
  the target to run. So `copier update` stays red until `make gate-baseline`
  has run once.

A hand edit of the baseline file is not prevented. Review holds it, as review
holds `config_reads.allowed`.

**The date (ruling 10 below).** config/project.json `expiring_tier.expires` is
the project's date, written `YYYY-MM-DD`. keel ships `2027-01-31`, the ceiling.
The ceiling is `CEILING` in `scripts/expiring_tier_data.py`. This is a
CONVENTIONS §18 data registry, so the date is data and not a literal in logic.
It is a Python module rather than a JSON file because the tier imports it with
no new config reader. It is also a keel file that copier rewrites on every
update, so a project's edit to it shows as a diff, or a conflict, on the next
update. A configured date later than the ceiling, or one that is not a calendar
date, is red in every gate that adopts the tier, in the template repository
too, because `judge` loads the policy before it returns early there; and it is
red in `tests/integration/test_expiring_tier_wiring.py`. An earlier date is the project's own
choice. Nothing inside a repository stops a determined edit of keel's file. The
tier reads today through `scripts/run_date.py` (ADR-K-0019), so one gate run
has one date. From the expiry date on, every finding of an adopting check is
red, recorded or not, and the line says the grace ended on that date and names
the key.

**What a warning looks like.** Each adopting test raises one `ExpiringTierWarning`
(a `UserWarning`) per check with at least one warned line. pytest prints it in
its `warnings summary` at the end of `make test`. Its first line reads, and
each warned finding follows on a line of its own:

```text
2 finding(s) of `config-reads-file` that config/gate-baseline.json records warn until 2027-01-31 (config/project.json expiring_tier.expires) and are red from that day
```

**What the tests prove.**

- `tests/unit/scripts/test_expiring_tier.py` covers the tier itself. A finding
  is red in the template. A recorded finding warns the day before the expiry
  and is red on the date. An unrecorded finding is red, and so is a second copy
  over the recorded count. A stale entry is red, an unregistered check is red,
  and a line outside the grammar is red. A missing baseline makes every finding
  red, naming the target. A date later than the ceiling is refused, and the
  ceiling itself is accepted.
- `tests/unit/scripts/test_record_gate_baseline.py` covers the writer's
  derivation: first record, growth across a `_commit`, shrink-only at one
  `_commit`, refusal of growth, an unrecorded check, the answers file read, the
  template refusal, and byte-identical output on a second run.
- `tests/integration/test_expiring_tier_wiring.py` checks the live tree. The
  configured date is no later than the ceiling. Each `CHECKS` entry names a test
  function that exists. The record target is in the Makefile. The template
  holds no baseline file.
- The generated-project test in `tests/integration/test_copier_generation.py`
  drives it end to end. A planted direct read is red, `make gate-baseline`
  records it, the gate is green with the warning, and an expiry moved to today
  turns it red. Each new comparison is broken by hand to show a test goes red,
  and the mutations are listed with the commit.

**Where it is decided.**
ADR-K-0027,
`docs/adr/keel/K-0027-a-project-s-own-code-warns-until-a-hard-date.md`, is
proposed. It is a new decision rather than an edit, because K-0016 to K-0022
are accepted and the proposed K-0023 to K-0026 decide other things.

**The make target's label.** The 2026-10-22 ruling asked for a `[write]`
target. ADR-K-0011 calls a rewrite of tracked files `[tree]`, and check_W fails
a non-`[write]` recipe that calls `$(WRITE_GUARD)`. The target is
`[tree,write]`. The words are true together: it rewrites a tracked file, and it
opens with the guard, so CI, a Ralph loop and the gate runner never record a
baseline unattended. An agent that could record its own findings would undo the
rule.

**Not built:**

- No other gate adopts the tier in this slice. The swallowed-error, change-comment,
  import-layer and committed-secret gates still fail a project's own code at
  once. Adopting the tier is one `CHECKS` row and one call each. The KEEL-LINT-1,
  KEEL-TESTQ-1 and KEEL-DOC-1 checks take it as they land.
- ruff, mypy and check_structure findings are not under the tier. They are not
  gate tests and do not print the house grammar.
- Nothing stops a hand edit of the baseline file or of `scripts/expiring_tier_data.py`.
- A finding's identity drops its line number, so the tier cannot tell a
  recorded finding fixed and a new one of the same rule added in the same file
  from the recorded one moved. That new finding warns rather than going red.
  Review holds it; the identity stays line-free so that an edit above a
  recorded finding does not turn it red.
- The writer judges no stamp freshness. A project that runs `make gate-baseline`
  before its first `copier update` records its findings at its first `_commit`.
- No fetch of the template and no manifest of keel's files is built. Both were
  rejected in the B1 ruling.

## CMP-7 — a document answers for the features it serves

The maintainer approved this campaign on 2026-10-22. It is KEEL-DOC-1, the first campaign-sized item in the queue. The cap is five slices, the read-only opening pass included, and each slice is one commit on a green `make verify`. CMP-7.S1 is the defence table, because every later documentation check reads it. The opening pass checks the candidate slices below against the tree and writes the next rows into this table; until then they are candidates. The stop point is the fifth slice or the table's last row green, whichever comes first. It starts after queue positions 1 to 9.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-7.S1 | KEEL-DOC-1: a design or spec document can describe itself without meeting its features; nothing records which questions it answers and which it leaves open (DT-1 to DT-7 below) | planned |

## Queued after Campaign 6

A queue id becomes a `CMP-<n>.S<m>` name only when an approved slice table
gives it one (CONVENTIONS §20).

On 2026-10-22 the maintainer approved this order. Positions 1 to 9 come from the move to the personal host and run before CMP-7 starts, because a full `make verify` there takes over three hours and two slices built in parallel conflict in about ten shared files. KEEL-DOC-1 left the queue to become CMP-7.

| Position | Queue id | Gap | Status |
|----------|----------|-----|--------|
| 1 | KEEL-RAM-1 | Test scratch goes to a disk root, and on a network-mounted home every small-file write is a round trip; a session should prefer a per-user memory root and fall back to disk, naming why (K-0024 Decision 5) | done: full `make verify` green on 1d41d04, merged in PR #14 |
| 2 | KEEL-DOC-SETUP-1 | The README does not say what a new machine must rebuild (the venv, `node_modules`, the browser and the scanner record), and its venv line names a `python3` that can predate `pyproject.toml` `requires-python` | done: `make check`, `check-docs`, `check-corpus` and the doc drift, freshness and README generation tests green on 6621c52, merged in PR #15 |
| 3 | KEEL-SPEED-1 | A full `make verify` takes 3 h 12 min on the personal host, and about 85% of it is copier rendering projects: `tests/integration/test_copier_generation.py` renders 52, many from the same answers. Planned: one render per distinct answer set from one clean clone, a private copy per test, a guard that no two tests share a folder, then parallel workers, then the verify tiers written into `docs/guides/dev-loops.md`. Rejected: a render cache across runs (a stale pass) and building one project from another by `copier update` (slower). Done: one render per answer set, a private copy per test and the isolation guard landed, and the merged tree's full verify passed 3756 tests in 1 h 37 min; parallel workers moved to KEEL-XDIST-1 | done |
| 4 | KEEL-FRAG-1 | Every slice appends to the same shared files (`CHANGELOG.md`, this plan, `config/project.json` and its twin, the ADR index, the settings and features references), so two slices built in parallel worktrees conflict in about ten files each time, and this plan grows without bound; CMP-6.S3 and CMP-6.S6 conflicted in ten; moved up on 2026-10-22 so that parallel slices stop conflicting | planned |
| 5 | KEEL-RUN-1 | `scripts/run_make_target.py` gives up after a 1800-second default typed in code, and on that timeout it leaves the processes `make` started running: on a busy host a full `make verify` timed out and its pytest kept writing in the worktree. Done: the limit and the stop grace are `make_targets.gate_timeout_seconds` and `make_targets.gate_stop_grace_seconds`, read through the loader; on a timeout or a signal the runner ends make's whole session with SIGTERM and then SIGKILL, and the merged tree's full verify passed 3844 tests in 1 h 47 min | done |
| 6 | KEEL-VENV-1 | The transport packages fastapi, uvicorn and httpx are installed by hand rather than declared in an extra, so a missing one reads as a skipped test; a venv older than `pyproject.toml`'s dependencies fails late rather than when `make verify` starts. Done: the transport packages are the `transport` extra that `dev` names, `make check-venv` fails a stale venv before any goal runs, and the merged tree's full verify passed 3767 tests in 1 h 33 min | done |
| 7 | KEEL-SEC-2 | Installing the scanner needs Go and GitHub, which a firewalled host lacks; recommended: a pinned release binary checked by sha256, its URL in config. Optional: `.gitleaksignore` and `.gitleaks.toml` join `agents.protected_names` | planned |
| 8 | KEEL-FE-AUDIT-1 | `npm audit` reports 28 findings in the astro app (2 critical, 17 high); each is triaged and its version raised in its own commit, never with `--force` | planned |
| 9 | KEEL-DIST-1 | No install source (PyPI, npm, the browser and scanner downloads) can be pointed at a company mirror by config, and only GitHub CI ships, with no GitLab pipeline beside it | planned |
| 10 | KEEL-NEXT-1 | A `make` target's next step is prose: a failure's `report()` line says what to do in words, a success prints no next step, and nothing checks that a named next step exists or moves the work on. Proposed: one table maps a target and its outcome to the next target or command, the footer is printed from it, and a test walks each declared edge once from the entry targets; a costly edge is checked on paper, and a target no entry reaches is an orphan only with a reason | proposed, not scoped |
| 11 | KEEL-LINT-1 | A rule a tool can decide is still held only by a prompt: a boolean passed by position (R-CODE-18), a cache with no maximum or one typed into code (R-CODE-24), and a narrow error caught and dropped (R-CODE-7) reach no check, and ruff's SIM105 steers a dropped error into `contextlib.suppress`, which the swallowed-error gate cannot see | planned |
| 12 | KEEL-TESTQ-1 | A green suite does not show its tests can fail: nothing measures whether a test uses the real part or a mock, whether its assertions would catch a change, or whether a failure path is tested; the measuring engine, pyverdex, lives outside keel | planned |
| 13 | KEEL-PKG-1 | Keel's checks reach a repository only by generating it from the template; the vault and pyverdex cannot install them on their own | planned |
| 14 | KEEL-SHELL-1 | A generated project supports Python and TypeScript but not shell: a shell script gets no lint, format or test target, and none of the header, exit-code, environment or config rules reaches it | planned |
| 15 | KEEL-ERR-1 | A narrow handler turns a broken result into an empty one: `agents/doc_reviewer/_brain.py` reads unparseable JSON as zero findings, and the swallowed-error gate sees only broad handlers (R-CODE-7); the R-CODE-7 check KEEL-LINT-1 plans fixes it | planned |
| 16 | KEEL-AGT-2 | An agent's `--execute` run has no spend cap, and without `--model` it uses the registry's default without saying so (R-AGT-27, R-AGT-29) | planned |
| 17 | KEEL-RES-2 | The gRPC, REST and MCP entry points have no memory cap and no shutdown owner; a headless model child has no timeout; a network reply is read whole (R-CODE-23, R-CODE-27, R-CODE-28) | planned |
| 18 | KEEL-CFG-3 | Limits are typed in code: the gRPC port and worker count, the in-process runtime's step cap, agent and refactor timeouts (R-CODE-3, R-CFG-1) | planned |
| 19 | KEEL-WARN-1 | Warnings nobody must fix fire on every run: the owner-TBD warning and the fail-open "not found" and "could not parse" warnings in `scripts/check_structure.py` (R-AGT-32) | planned |
| 20 | KEEL-AGT-3 | Four of the five agents have no eval case and no known-good example (R-AGT-4, R-AGT-12, R-AGT-14) | planned |
| 21 | KEEL-DOC-2 | Wrong claims pass every gate (a check letter, counts with no method in `doc-style.md`), and release notes sit in shipped guides that the change-comment phrase list does not read (R-DOC-1, R-DOC-2, R-DOC-14) | planned |
| 22 | KEEL-SHIP-1 | Nothing fails a new file that is neither rendered to a generated project nor excluded from it with a reason: a slice can build a check keel holds itself to and leave every project without it, and only review notices | planned |
| 23 | KEEL-HDR-1 | The three accepted file-header fields are not read by any check, and a call into `re` needs no stated reason; moved from CMP-6.S5 | planned |
| 24 | KEEL-LINK-1 | The untracked `project-keel` link in keel's checkout points into another project's tree, which the personal host does not have; it gets a target or is removed | planned |
| 25 | KEEL-CODEDOC-1 | No per-function implementation documentation is generated from the code (a tree-sitter or code-wiki tool was raised), and no document says how keel's agents are evaluated | raised 2026-10-19, not scoped |
| 26 | KEEL-GRPC-1 | The gRPC transport's packages sit in `api/grpc/requirements.txt` and no `pyproject.toml` extra, so `make check-venv` (KEEL-VENV-1) does not judge them and `transports.extras` has no gRPC entry; found while building KEEL-VENV-1, which kept to REST | planned |
| 27 | KEEL-ASTRO-1 | The astro app is on astro 5, whose critical advisories (AVIF image optimisation, slot-name XSS, Host-header SSRF) are fixed from astro 7.2.8 for the critical and only from 7.3.2 for every astro advisory (`npm audit fix` targets 7.4.2), with sharp and esbuild fixed alongside; a static build with no image service and no SSR adapter does not reach them, a generated project that turns either on does; found by KEEL-FE-AUDIT-1, which proposed a review by 2026-11-05 | planned |
| 28 | KEEL-ESLINT-1 | `braces` under eslint-plugin-astro 1.7 has a high advisory with no fixed release in range; the way out is eslint-plugin-astro 2 or later, which needs ESLint 10; lint time only; found by KEEL-FE-AUDIT-1 | planned |
| 29 | KEEL-RISK-1 | An `npm audit` finding left open for a reason has nowhere to be recorded, so the next audit cannot tell an accepted risk from a new one. Proposed by KEEL-FE-AUDIT-1: accepted rows with a reason and a review date in config, and a `[read]` target that fails an uncovered critical or high, a row past its date and a row whose advisory is gone | proposed, maintainer to decide |
| 30 | KEEL-EXIT-1 | `scripts/exit_codes.py` says codes 10 to 14 let a caller act on the number alone, but GNU make turns every failing recipe status into 2, so the claim holds only when a script runs directly; found by the KEEL-NEXT-1 design pass | planned |
| 31 | KEEL-TOOLT-1 | An agent's tool child has no time limit: `_run` in the four agents' `_brain.py` files and `_run_doer` in `mcp/action_server.py`; found by KEEL-RES-2, which recommends its bounded runner and a configured key | planned |
| 32 | KEEL-MCPCAP-1 | The MCP question-answering server's `answer(execute=True)` makes model calls with no approved cap; found by KEEL-AGT-2, whose cap covers the CLIs and the Stop hooks | planned |
| 33 | KEEL-PROC-1 | Two process-group runners will exist, `scripts/run_make_target.py` (KEEL-RUN-1) and `scripts/resource_limits.py` `run_bounded` (KEEL-RES-2); one should call the other, so a fix to zombie, ignored-signal or held-pipe handling lands once | planned |
| 34 | KEEL-XDIST-1 | After KEEL-SPEED-1, five copier generation tests that run a generated project's own suite take about 1740 of 2584 seconds; parallel workers are the remaining lever, and the isolation guard's unused-exemption check must judge across workers first | planned |
| 35 | KEEL-ROSTER-1 | The `gate_evidence.py` row in `scripts/README.md` and its twin spells `make verify`'s goals without `secret-scan`, and nothing tests the row; found by KEEL-SHELL-1 | planned |
| 36 | KEEL-TYPO-1 | `@tailwindcss/typography` pins postcss-selector-parser 6.0.10, which has a moderate advisory that its range cannot leave; found by KEEL-FE-AUDIT-1; owner: the maintainer, as a fix or a KEEL-RISK-1 accepted row | planned |
| 37 | KEEL-KATEX-1 | mermaid 11 pins katex 0.16, which has a low advisory, and the way out is mermaid 12; neither dompurify nor mermaid has a runtime test, only the build and the bundle; found by KEEL-FE-AUDIT-1; owner: the maintainer | planned |

### Build lanes ahead of the merge line

The maintainer asked on 2026-10-22 for items that share no code to be built
in parallel, each in its own worktree and branch, so a branch reaches the
merge line already reviewed. Building ahead never changes the merge order:
branches merge one at a time in queue order, each rebased onto the new
`main` and passing the full `make verify` on the merged tree.

A lane loops on its own branch gate, which is faster than `make verify`:
`make lint typecheck check check-docs check-exit-codes check-corpus`, the
unit tests, and the integration and generation tests of the area it
touches. A fresh reviewer then tries to break the branch, and the builder
fixes each confirmed finding. At most two full `make verify` runs share
this host, and no two lanes running at once edit the same code file;
the shared files (`CHANGELOG.md`, this plan, `config/project.json` and its
twin, the settings and features references) are resolved at rebase until
KEEL-FRAG-1 removes that conflict.

| Lane | Items, in order | Code it owns | Starts |
|---|---|---|---|
| L1 | KEEL-FE-AUDIT-1 | `src/frontend/*/package.json` and lockfiles | now |
| L2 | KEEL-SEC-2, then KEEL-DIST-1 | the scanner installer and the install sources | now; KEEL-DIST-1 after KEEL-VENV-1 merges |
| L3 | KEEL-LINT-1, then KEEL-ERR-1, then KEEL-HDR-1 | the lint and header checks, `agents/doc_reviewer/_brain.py` | now |
| L4 | KEEL-AGT-3, then KEEL-AGT-2 | the agents' eval cases and their run entry | now |
| L5 | KEEL-CFG-3, then KEEL-RES-2 | the transports' and runtime's limits | now |
| L6 | KEEL-NEXT-1, a design pass only | a design document for review | now |
| L7 | KEEL-SHELL-1 | the shell lint, format and test targets | when a lane frees |
| L8 | KEEL-WARN-1, then KEEL-SHIP-1, then KEEL-DOC-2 | `scripts/check_structure.py` warnings, the render check, doc claims | after KEEL-RUN-1 merges, which edits `scripts/check_structure.py` |
| L9 | CMP-7 opening pass, a design pass only | the defence table | when a lane frees |

KEEL-TESTQ-1, KEEL-PKG-1, KEEL-GRPC-1, KEEL-LINK-1 and KEEL-CODEDOC-1 have
no lane yet: KEEL-LINK-1 and KEEL-CODEDOC-1 need the maintainer's decision,
and KEEL-TESTQ-1 and KEEL-PKG-1 reach outside keel.

**KEEL-DOC-1, the defence table.** This holds the maintainer's document rule
R-DOC-15: before a design is planned, it answers hard questions on behalf of
every feature it must serve, and records each answer. The table is a section
of the design or spec document. It has one row per question, with five
columns: Feature, Question, Answered in, Verdict, and Change or cut. Feature is
a requirement id, or a feature name in a design document, which has no ids.
Answered in is a heading in the same document. Verdict is one of `defended`,
`partly` or `gap`. Beside the requirements sits a "Will not do" list: each
entry is a scope cut with its reason. A gap is closed by a design change or by
an entry in that list. The schema in this paragraph is proposed; the slice
fixes it.

Requirements, in EARS form, for the check the slice builds:

- **DT-1** (ubiquitous): The check shall read every document under `docs/`
  whose frontmatter says `kind: design` or `kind: spec`, through the repo's
  Markdown reader, and never by matching text.
- **DT-2** (unwanted): If such a document has no defence table, then the check
  shall be red, naming the file.
- **DT-3** (event-driven): When a `kind: spec` document defines a requirement
  id, the check shall be red unless the table has a row whose Feature is that
  id. Ids are read by `scripts/traceability.py` `read_specs`, the only parser
  of an id; the slice builds no second one.
- **DT-4** (unwanted): If a row's Answered in is empty or names a heading the
  document does not have, then the check shall be red, naming the file, the
  row and the heading.
- **DT-5** (unwanted): If a row's Verdict is empty or not one of the three
  words, then the check shall be red.
- **DT-6** (unwanted): If a row's Verdict is `gap`, and its Change or cut cell
  names neither a design change nor an entry in the "Will not do" list, then
  the check shall be red.
- **DT-7** (ubiquitous): The check's documentation shall say that it cannot
  judge whether a question is a good one, or whether an answer holds. Review
  holds that, and `make doc-review` is where it is asked.

How it is built, in order:

1. The failing test first. One fixture document per rule DT-2 to DT-6 breaks
   that rule, and the check is shown red on each, then green on a fixture that
   keeps them all.
2. The check is a gate test under `tests/integration/`, the CMP-5.S1
   precedent, since the structure gate's letters A to Z are all used. If the
   repo has a way by then to add a check without a letter, the slice uses it
   and says why.
3. A mutation proof by hand: each rule's comparison is broken in turn, and the
   suite must go red for each. The slice reports which mutations it ran.
4. Docs grounded in code: `docs/guides/doc-style.md` gains the rule and the
   table's shape. `docs/specs/README.md` says where the table goes and what it
   does not judge. `docs/reference/features.md` gains the check's row. Each
   claim names the test that holds it.

The slice must also decide these points, and say what it chose:

- **keel's own design documents.** keel has three `kind: design` documents
  under `docs/design/`, and none has a table. The slice either writes their
  tables, or the check applies only to documents created after it lands. The
  first follows "fail closed"; the second leaves keel's own plans unchecked.
- **A project's documents on arrival.** After `copier update`, a project's own
  design and spec documents have no table, so they turn red. This is the same
  question as B1 for a project's own `sys.exit` scripts, and takes the same
  answer: warn, then fail.
- **What the template ships.** A generated project gets no `kind: design`
  document, only the labelled `docs/design/README.md`, so there is no design
  stub to give an empty table to. It does get `docs/specs/example-feature.md`,
  a spec with requirement ids. The proposal is to give that spec a filled
  example table, with a row for each of its ids. An empty table would fail
  DT-3 on the first run of `make verify`. `docs/design/README.md` would show
  the table's shape inside a fenced block, which no check reads as a table.

**KEEL-DOC-1, the candidate slices.** The ruling below makes the documentation
work one campaign. It merges two lists: the keel documentation inventory's
ten gaps, ranked by value, and the first eight slices of the
documentation-system design study kept in the maintainer's vault (its slices
9 to 18 belong to custodex, pyverdex, jarvis or a trial, not keel). The
opening pass checks each claim against the tree before it keeps a row,
reconciles the two lists, and writes the approved table. Until then this is
a candidate list, not a plan:

| Candidate | Source | What it builds |
|-----------|--------|----------------|
| The defence table | CMP-7.S1 above | DT-1 to DT-7, and R-DOC-16's probe questions as rows |
| Kind-to-folder binding | inventory gap 1 | a `docs.homes` map in `config/project.json` and a check that a document of a kind sits under that kind's folders |
| A genre for `kind: doc` | inventory gap 2 | a closed `genre` vocabulary, used only under `kind: doc` |
| The coverage register | inventory gap 3, study slice 5 | `test-docs/coverage/register.md` deleted or rendered from `make trace` |
| Check ids and registry | study slice 1 | an id per check, and a registered check with no fault-injection twin fails |
| Kinds and status lists | study slice 2 | per-kind allowed status lists, and a backward status move fails |
| Changelog heading and commit message | study slice 3 | an unknown changelog heading fails, a "wip" commit subject fails |
| Heading contracts | study slice 4 | required headings for the root README, a directory README, a new ADR and a design document; lands as an error with the tree fixed in the same change |
| Freshness that fails closed | study slice 5 | the freshness check with no git exits 2, could not run, never a skip |
| House vocabulary | study slice 6 | a reject list run over prose, and an empty list fails |
| Roadmap fields in the features catalogue | study slice 7 | an `implemented` row with no test fails |
| Docstring grammar | study slice 8 | ruff `D` and pydoclint; lands as an error, a baseline only under CMP-6.S4's tier with its hard expiry |
| Placeholders per kind | inventory gap 5 | a fenced skeleton in each kind's folder README |

The study's slices 4 and 8 proposed a warning first; the ruling below lands
them as errors. The cap is five slices with the opening pass, so most rows
here are queued by that pass, not built in this campaign.

**KEEL-SHELL-1, shell as a template language.** The maintainer approved it on
2026-10-17, in three slices, and the 2026-10-19 ruling put it after KEEL-LINT-1,
KEEL-TESTQ-1 and KEEL-PKG-1; it becomes a
`CMP-<n>.S<m>` name only when its slice table is approved. Shell gets the
treatment Python and TypeScript already have, and ships to generated projects:

- A copier question `shell`, on by default, adds the shell targets; a project
  that answers no installs none of the tools. Shell scripts live in
  `scripts/` beside the Python ones, because the taxonomy groups by role.
- Slice 1: `lint-sh` (shellcheck), `fmt-sh` and `fmt-check-sh` (shfmt) and
  `test-sh` (bats-core), run by `make verify`, with generation tests for both
  answers.
- Slice 2: check_O and check_V read a shell script's `# title:` comment
  block, and an exit-code helper generated from `scripts/exit_codes.py` gives
  shell the one exit-code table; the exit gate reads `.sh` files.
- Slice 3: a child process starts from `env -i` and the names in
  `child_env.names`; a configured value is read only through
  `python -m scripts.config_loader`; the bash version floor is a config key;
  `docs/guides/shell-style.md` and the reference rows.
- Not yet checked: whether the shellcheck and shfmt packages on PyPI install
  the binaries into the venv, and how bats-core is installed. This host has
  bash 4.4 and none of the three tools.

**KEEL-LINT-1, the lint checks.** The maintainer ruled on 2026-10-19 that
the rules a tool can decide are built into keel's checks before shell, so
every project generated from keel holds them, and the prompt keeps only the
rules that need judgment. The vault's rule experiments are the evidence: with
the rules loaded, 19 of 20 runs still kept a setting in code as a fallback,
and what made the work production-ready was caught by deterministic checks in
every arm. It is planned as the campaign after CMP-7.

Its opening pass is read-only and writes the slice table. It maps every rule
in the 0.10.0 code package to one of three answers: held by a named keel
check, decidable by a tool but not held, or a judgment rule that stays in the
prompt. For each tool-decidable rule it measures how many places in the tree
break it today, and it names an existing tool's rule before proposing a new
check. The candidates already found, each confirmed by reading the tree:

- R-CODE-18: ruff `FBT003`, which fails a boolean passed by position at a
  call. `FBT001` and `FBT002`, which fail a boolean parameter in a
  definition, are a wider choice the maintainer makes.
- R-CODE-24: a new gate test, because ruff has no rule for a cache's
  maximum (`B019` covers a cached method only). `functools.cache`,
  `lru_cache` with no `maxsize`, `maxsize=None` and a literal maximum fail;
  the maximum comes from config. Two places in the tree break it today:
  `tests/integration/test_e2e_coverage.py` and
  `tests/integration/test_reference_drift.py`.
- R-CODE-7, a narrow error dropped: ruff `S110` and `S112` first; a new
  check covers only what they miss. `SIM105` is disabled, or the
  swallowed-error gate learns `contextlib.suppress`, in the same change.
  KEEL-ERR-1's instance is fixed by this check.
- The allow comment: each check's way of excusing a line names the rule id
  and gives a reason, so an excuse can be read back to the rule it waives.

Every check lands as an error in the change that makes the tree pass it
(R-AGT-32), with a planted break shown red, then green. The cap is five
slices, the opening pass included. The stop point is the slice table done,
or the cap. When it is done, the vault installs keel's checks rather than
keep its own AST gate; how a repository not generated from keel installs
them is KEEL-PKG-1, not this campaign.

Proposed slices, from the opening pass. A slice gets its `CMP-<n>.S<m>` name
only when the maintainer approves this table (CONVENTIONS §20). The campaign
starts after CMP-6.S4, because each check reaches a generated project's own
code through that slice's expiring tier.

| # | Gap | Size | Breaks today |
|---|-----|------|--------------|
| 1 | Opening pass, read-only: the rule map and this table | — | done |
| 2a | R-CODE-7, dropped errors: ruff `S110` and `S112` with `check-typed-exception = true`; the swallowed-error gate widened to `contextlib.suppress` and `rmtree(ignore_errors=True)`; the excuse grammar (rule id and reason) for every code the gate owns; KEEL-ERR-1's `agents/doc_reviewer/_brain.py` instance fixed | M | 39 |
| 2b | R-CODE-7, a narrow handler that returns or assigns a fixed value, `None` included, in place of the error; a function whose documented result for "absent" is `None` carries the excuse | M | 40 fixed values and 31 `None` values |
| 3 | R-CODE-18, a boolean by position: ruff `FBT001`, `FBT002` and `FBT003`; the keyword-only conversion lands as its own mechanical commit | M | 127 |
| 4 | R-CODE-24, a cache maximum: ruff `TID251` bans `functools.cache` and `lru_cache`, a bounded-cache helper reads its maximum from a `KEYS` row; R-CODE-17's `ERA001` added at no cost | S | 2 |
| 5 | A stale excuse is red: `RUF100` selected, check_M reads `ignore` and `extend-ignore`, `practice-ok` takes a rule id and a reason | M | 45 and the `practice-ok` sites |

The cap is five slices with the opening pass, so with 2a and 2b separate,
slice 5 is queued unless a slice comes in under one pass. The counts are the
opening pass's measurement, not a gate's.

**KEEL-TESTQ-1, the test checks.** It follows KEEL-LINT-1. Its source is
pyverdex (`my_rnd/python-verification`), a test-effectiveness engine that
measures line, branch, function-to-function edge, mutation,
assertion-quality, realness (mock, fake, in-process, real) and failure-path
coverage. The maintainer ruled on 2026-10-19 to split it by cost, not to
merge it whole:

| Part of pyverdex | Where it goes | Why |
|---|---|---|
| Realness classifier, assertion-quality checks, failure-path detection | keel, as gate tests in `make verify` | They read the syntax tree with the standard library and run in seconds, so they reach every generated project |
| Mutation and edge or branch measurement | the engine, run by a keel target labelled `[cost]` through a thin adapter, pyverdex by default and chosen in config | They take minutes to hours, so they run on a schedule or before a release; keel holds the thresholds in config |
| The LangGraph pipeline, the judgment nodes and the dashboard | pyverdex only | A template every project inherits carries no model pipeline or web app |

Starting split keeps the choice reversible: a part can move into keel later,
but a part merged into keel leaves every generated project only through
`copier update`. The split assumes pyverdex is worth keeping as a product
that runs on any pytest project; if it only ever runs on keel projects, the
case for the engine staying outside weakens.

A prerequisite sits in pyverdex, not keel: its ten measuring tools are
copies of another repository and are not committed, so a fresh clone does
not run. Before keel depends on any part, those tools are ported, packaged
or installed, decided in pyverdex's own repository.

Its opening pass is read-only and writes the slice table: each pyverdex part
mapped to keel, the engine or pyverdex only; how each keel-side part is
ported to keel's house pattern (the config loader, the exit helper, module
headers, effect labels), since pyverdex predates them; the measured run time
of each engine part on keel's own suite; and the thresholds a gate would
hold. The cap is five slices, the opening pass included.


Proposed slices, from the opening pass, named only on approval
(CONVENTIONS §20). The ruling below moves failure-path detection to the
engine side: its static half found nothing to fail in fail-closed code (132
of 167 boundaries have no handler, by design).

| # | What, end to end | Size |
|---|------------------|------|
| 1 | Opening pass, read-only: the part map, the measured run times and this table | done |
| 2 | Assertion-quality gate test, a standard-library port into `tests/`, shown red on a test with no assertion, a trivial one and an assertion hidden in a helper; `test_quality.*` `KEYS` rows; ships through copier | M |
| 3 | Realness gate test, with a gate that an `e2e` test never mocks | S |
| 4 | The engine adapter and its target: a thin `scripts/` adapter chosen by `test_engine.adapter`, pyverdex the default, runs mutation and branch and edge coverage on a scratch copy; an absent engine and zero mutants each exit non-zero, never a pass; labelled `[cost]` under the wider definition below | L |
| 5 | Failure-path and boot measures from the same coverage run, with thresholds that land as errors at the measured value | S |

Slice 4 is blocked on the pyverdex prerequisite above; slices 2 and 3 are
not.

KEEL-SHELL-1 follows KEEL-TESTQ-1.

**The audit against the rule packages, version 0.10.0.** On 2026-10-17 a
read-only audit compared keel with every rule id in the maintainer's four
rule packages: 33 code rules, 19 document rules and 37 agent rules. It ran
no gate, so a verdict of covered means a check exists that would fail a
violation. The counts:

| Package | Covered | Convention | Partial | Gap | Not applicable |
|---------|---------|------------|---------|-----|----------------|
| Code (R-CODE, R-CFG-1 to 3) | 4 | 1 | 15 | 13 | 0 |
| Documents (R-DOC, R-CFG-4 to 6) | 2 | 0 | 14 | 3 | 0 |
| Agents (R-AGT) | 1 | 1 | 21 | 13 | 1 |

Positions 3 to 11 above are the gaps it ranked highest that no slice already
plans; the secret scan (R-CFG-3, R-CFG-6) is CMP-6.S3. R-DOC-16, the probe
questions, joins KEEL-DOC-1 as rows of the same table, and lands as an error
under the R-AGT-32 ruling below. Two findings wait on a ruling: whether
keel's own ADRs ship to a generated project (R-DOC-11: some name the first
downstream project or one site's estate), and whether a finished plan is
kept (R-DOC-8 against the plan documents kept on purpose).

## Rulings recorded after CMP-5.S3

The maintainer asked for the vault's recommendations to be acted on. These
are settled:

- **The rewriter is option (a).** It rewrites `return 0`, a bare `return` and
  falling off the end of `main` to `SUCCESS`, and lists every other return for
  a person to judge. It never guesses what a return meant.
- **"Nothing judged" gets its own `ExitCode` member, still non-zero.** A pass
  over zero records is a failure, and exit 1 cannot tell it from "a key is
  proposed". This lands in CMP-5.S4, so it costs no full verify of its own.
- **KEEL-DOC-1 holds keel to its own rule.** keel's three `kind: design`
  documents get defence tables, with no exemption for older documents. A
  project's older documents follow the same warn-then-fail as B1.
- **ADRs K-0018, K-0019 and K-0020 are accepted**, and the seven commits up
  to `241c630` are pushed.
- **The three extra file-header fields are accepted** (touches, tests checked
  against existing test files, docs as requirement ids), and "description"
  and "purpose" merge into one field. Campaign 5's cap holds, so this is
  queued for Campaign 6.

- **ADR K-0021, the import layer order, is accepted.**
- **B1 tells keel's files from a project's own by where the gate runs**, the
  third way in the CMP-5.S4 note. A finding in the template repository, read
  from whether `copier.yml` exists, is red. A finding in a generated project
  warns until 2027-01-31 and is red from that date. The date lives in config,
  the warning prints it, and a test drives the run date past it to show the
  warning turn red. The maintainer accepted that this also warns on a keel
  file the project edited. CMP-6.S4 built the tier.
- **ADR-K-0022, one config loader, is accepted** (2026-10-17), and
  CMP-5.S5 with the react-vite lockfile is pushed.
- **Campaign 6 is approved with a cap of five slices** (2026-10-17), in the
  order of its slice table. The secret scanner is ruled under CMP-6.S3.
- **CI runs on a pinned runner image, `ubuntu-24.04`**, so the image changes
  only when the workflows are edited, not when the `ubuntu-latest` label moves.
- **R-AGT-32 and the B1 tier.** The maintainer ruled on 2026-10-17 that
  CMP-6.S4's warning tier stays, with a hard expiry a check enforces: the
  date is one config key, it can move only earlier, the tier turns red on
  that date, a new finding is red at once, and keel itself gets no grace.
  Every other new check lands as an error in the change that makes the tree
  pass it.

## Rulings recorded during CMP-6

On 2026-10-19 the maintainer delegated these to a judgement grounded in the
vault's rules ("make your best judgement on the decision for me based on the
vault's knowledge"). Each names its evidence. The rule packages are now at
version 0.11.1.

1. **R-CODE-7 counts a fixed value as a dropped error.** A narrow handler that
   returns `None`, or any fixed value, in place of the error swallows it:
   R-CODE-7 says a swallowed error turns a failure into a wrong result that
   looks right, and unknown is kept distinct from zero. Where `None` is the
   function's documented result for "absent", the line carries the excuse,
   rule id and reason. It is its own slice, KEEL-LINT-1 2b, so 2a stays one
   pass.
2. **R-CODE-18 takes `FBT001`, `FBT002` and `FBT003` together.** The fix for
   the class is a keyword-only parameter, which `FBT001` and `FBT002` hold;
   `FBT003` alone holds the symptom at each call (R-CODE-30). The keyword-only
   conversion lands as its own mechanical commit.
3. **A downstream project's red on `copier update` takes the B1 answer.** The
   ruling recorded after CMP-5.S3 already answers it: every KEEL-LINT-1,
   KEEL-TESTQ-1 and KEEL-DOC-1 check reaches a generated project's own code
   through CMP-6.S4's expiring tier, a new finding is red at once, and keel
   itself gets no grace. So those three campaigns start after CMP-6.S4.
4. **Failure-path detection moves to the engine side of KEEL-TESTQ-1.** It
   needs a coverage run: the static half found nothing to fail in keel's
   fail-closed code, 132 of 167 boundaries with no handler by design.
5. **`[cost]` widens to "spends a budget the caller approves: money or shared
   compute".** Mutation and coverage runs take that label. A new proposed ADR
   supersedes K-0011's definition, because K-0011 is accepted and is not
   edited. Both kinds of spend are handled the same way, never unattended, so
   they share one label rather than adding a sixth.
6. **No check lands as a warning first.** An engine threshold lands as an
   error set at the measured current value, a ratchet that only tightens
   (R-AGT-32). The same holds for the design study's slices 4 and 8: a
   baseline is allowed only under the B1 expiring tier.
7. **The documentation work is one campaign, KEEL-DOC-1.** It merges the keel
   documentation inventory and the design study's eight keel slices; its
   opening pass reconciles the two lists and checks each claim against the
   tree first.
8. **"Kernel" is kept for build code (R-AGT-6, R-AGT-7).** KEEL-LINT-1 and
   KEEL-TESTQ-1 are "the lint checks" and "the test checks"; their ids do not
   change.

Pushing commits stayed outside that delegation; the maintainer approved it
separately.

On 2026-10-22 the maintainer ruled on the two questions CMP-6.S4's design
raised:

9. **New versus existing is a per-check baseline in the generated project.**
   One `[write]` make target, run after `copier update`, records it. A recorded
   finding warns until the date, an unrecorded one is red at once, and an entry
   no longer seen is red, so the file only shrinks. It may grow only when
   `.copier-answers.yml` `_commit` differs from the commit stamped in it.
   `copier update` stays red until the target runs once, and the failure names
   the target. A hand edit of the baseline is not prevented; review holds it.
10. **The date's ceiling ships in a keel-owned file that copier rewrites on
    every update**, as data, not a code literal. The project's config key may
    set an earlier date and never a later one: a later date is red. An edit to
    keel's file shows as a diff or a conflict on the next update; nothing
    inside a repository stops a determined edit. The ceiling is 2027-01-31. In
    the template repository every finding stays red, with no tier.

## Open items

Every leftover the two plan documents recorded (the residual, queued, "left
by" and cut lists here, and the deferred, non-goal and release lists in
`docs/design/keel-hardening-plan.md`) was checked against the tree at
`55ded1d`. A read-only audit found 143 distinct items: 108 open, 5 unknown,
25 closed and 5 superseded. A closed or superseded item is not repeated; its
commit is the record. The two high items "make -i defeats the write guard"
and "a frontend suite that skips exits 0" were reproduced by hand; the rest
are the audit's reading of the code. Severity is a judgement, not a
measurement. A low item is often a limit recorded on purpose; its kind says
so.

| # | Item | Kind | Severity | Evidence |
|---|------|------|----------|----------|
| 1 | `make -i` or a `.IGNORE` target lets a `[write]` recipe run past `$(WRITE_GUARD)` under CI or a Ralph loop | defect | high | closed in CMP-5.S4: the guard's `$(error)` clause and check_W's `.IGNORE` rule |
| 2 | `test-fe` exits 0 when npm or an app's `node_modules` is missing, and CI never runs `test-fe` | missing-check | high | closed in CMP-5.S4: both targets exit 2, and CI runs `make fe-browsers` and `make test-fe` |
| 3 | KEEL-TEST-1: nothing stops a test reaching a live store | feature | high | closed in CMP-6.S2 |
| 4 | KEEL-SEC-1: nothing scans the tree for a committed secret | missing-check | high | closed in CMP-6.S3 |
| 5 | `credential_value_patterns` covers five token forms | missing-check | medium | `config/project.json`; CMP-6.S3 left it the child-environment guard's list, and the secret scan uses the scanner's own rules instead |
| 6 | A process keel does not start (`make new`'s copier, a hook calling make) gets the caller's whole environment | defect | medium | `Makefile` `new` target |
| 7 | A same-user child can read `/proc/$PPID/environ` | decision | medium | outside keel; K-0012 says defence in depth |
| 8 | The gate runner judges the child environment against keel's config, not the `--dir` project's | defect | medium | `scripts/run_make_target.py` calls `build_child_env()` and `load_policy()` with no root |
| 9 | The gate runner keeps `HOME` and the XDG directories, so host state leaks into a run | defect | medium | `scripts/run_make_target.py` |
| 10 | `test_exit_gate` accepts `finish(passthrough(main()))` over a `main` that returns integers | missing-check | medium | closed in CMP-5.S4: `scripts/exit_code_table.py` finds a passthrough of the script's own status |
| 11 | A project's own `sys.exit` turns red after an update and no rewriter exists | decision | medium | rewriter ruled (a) above; B1 ruled above (the template repository is red, a generated project warns until 2027-01-31); the tier is built in CMP-6.S4 (ADR-K-0027 proposed), full `make verify` green on the merged tree |
| 12 | `structure.extra_toplevel` directories, the project-checks directory among them, are outside `CODE_ROOTS` | missing-check | medium | `scripts/check_structure.py` `CODE_ROOTS` |
| 13 | check_X misses a receiver it cannot resolve, a value passed through a parameter, and a spawn in a shell script | missing-check | medium | stated in `scripts/check_structure.py` |
| 14 | A duplicate key in `config/project.json` is not refused | defect | medium | refused by `scripts/config_loader.py` `read` since CMP-5.S5; `scripts/check_structure.py`, still a direct reader, accepts one |
| 15 | An `rm` migration in `copier.yml` deletes after the keep-edited guard runs | defect | medium | `copier.yml` `_migrations` |
| 16 | The optional surfaces (wiki, evals, containers) have no copier question, and a deleted one returns on update | feature | medium | `copier.yml` questions |
| 17 | `react-vite` ships no lockfile | defect | medium | only astro has `package-lock.json` |
| 18 | `docs/specs/example-feature.md` arrives on update and turns `make trace` red | defect | medium | unchanged |
| 19 | `api/grpc/Makefile` is outside the effect-label walk | missing-check | medium | its `gen` target has no label |
| 20 | The `PY` gate variable names a program | defect | medium | `make_targets.gate_vars` |
| 21 | No mutation runner; mutants are written by hand | feature | medium | queued since Campaign 4 |
| 22 | CMP-5.S4, the tree-wide checks and the features-row rule | feature | medium | done, except open items 11 and 88 |
| 23 | CMP-5.S5, the config loader with a default marker | feature | medium | done; what it leaves is under "Left by CMP-5.S5" |
| 24 | KEEL-DOC-1, the defence table | feature | medium | CMP-7.S1 |
| 25 | pre-commit is not run in CI | missing-check | medium | `.github/workflows/ci.yml` |
| 26 | The coverage floor is not re-measured, so it can fall | missing-check | medium | `tests/integration/test_gate_scope.py` |
| 27 | `review_docs` and `restamp_docs` each keep a skip-directory list | defect | low | `_SKIP_DIRS`, `WALK_SKIP_DIRS` |
| 28 | `ALLOW_DIRTY` copies untracked files | defect | low | `Makefile` `new` |
| 29 | The copier 9.3.0 floor is checked statically, never run | missing-check | low | `tests/integration/test_copier_generator_contract.py` |
| 30 | `FE_APPS` is not sorted, and a target takes its first word | defect | low | `Makefile` |
| 31 | Nothing pins `TAXONOMY` to the CONVENTIONS §2 table | missing-check | low | |
| 32 | `copier.yml` `_exclude` names a root `tmp` | defect | low | |
| 33 | A `TAXONOMY` directory that is a symlink passes check_B | missing-check | low | |
| 34 | Ignored tool output (`site`, `logs`, `out`) turns a local check red | defect | low | `IGNORE_DIRS` |
| 35 | `models/config/default.example.toml` has no reader | decision | low | a D0 decision |
| 36 | ADR-0005 overlaps `child_env`, and its first slice is not built | decision | low | |
| 37 | `src/` cannot import `child_env` | decision | low | nothing in `src/` spawns today |
| 38 | `BASH_FUNC_*` and `PYTHONPATH` never reach a child | decision | low | by design |
| 39 | `hermetic_git.clone_including_worktree` replays only `git diff HEAD` | defect | low | an untracked file is silently missing |
| 40 | check_N reports at most five stale entries | defect | low | |
| 41 | A filtered file with stale stat data reads as modified | defect | low | |
| 42 | `audit-project` has no tool card under `agents/tools/` | doc-drift | low | |
| 43 | `audit_project` `origin_of` ignores `_exclude` and does not discount `updated:` | defect | low | |
| 44 | Restamp moves `updated:` in every ADR an update touches | defect | low | |
| 45 | A proxy value with `@` after its host is refused | decision | low | deliberate |
| 46 | The audit mixes hunks | defect | low | |
| 47 | The audit does not normalise a line number an update shifts | defect | low | |
| 48 | The audit gives no partial report when an update fails | feature | low | narrowed by CMP-3.S5, CMP-4.S2 |
| 49 | The audit does not judge ignored files | missing-check | low | |
| 50 | The audit does not handle links or submodules | missing-check | low | |
| 51 | The slice-name rule does not cover a foreign prefix or a requirement id | missing-check | low | |
| 52 | A `.jinja` file is put back without being judged | missing-check | low | |
| 53 | A bare ADR mention is not checked | missing-check | low | check_Y reads links only |
| 54 | A project can edit `adr.template_adrs` | defect | low | |
| 55 | A test file run alone whose tests all skip exits 5 | decision | low | accepted |
| 56 | `make run` readiness is not checked | missing-check | low | |
| 57 | `pytest_selections` reads only the first pytest line of a recipe | defect | low | |
| 58 | K-0011 lists `run` among the skipped targets; config skips `run-api` and `run-web` | doc-drift | low | K-0011 is accepted: a one-clause fix |
| 59 | A stamp hunk next to a content hunk is left for a person | defect | low | |
| 60 | A project check is trusted code | decision | low | accepted |
| 61 | A document that quotes a conflict hunk is never restamped | defect | low | |
| 62 | The `structure` `_comment` conflicts in every adopting project | defect | low | |
| 63 | The `.claude` ignore has no config key | defect | low | |
| 64 | `build_child_env(extra=...)` is honoured verbatim | decision | low | |
| 65 | `authorization:Service bin` is a false positive | defect | low | |
| 66 | check_W misses a guard in an unlabelled prerequisite, a `$(MAKE)` call or a variable | missing-check | low | |
| 67 | `make setup` is not adopted | feature | low | |
| 68 | `_tiers` and `_floor_report` read only the root Makefile | defect | low | |
| 69 | `copy_makefiles` does not follow an include named by a variable | defect | low | `tests/makefile_copy.py` |
| 70 | npm writes to `~/.npm` | defect | low | |
| 71 | `make new-test` is absent | feature | low | |
| 72 | The agent and playbook contract has no design document | doc-drift | low | |
| 73 | The D0 decisions are not made | decision | low | |
| 74 | `make new` is not refused inside a generated project | defect | low | |
| 75 | Port 8000 is written in the `Makefile`, not read from config | defect | low | |
| 76 | Whether a missing browser stays red | decision | low | |
| 77 | The grpc exemption | decision | low | `config/project.json.jinja` |
| 78 | A SIGKILL orphans the uvicorn test server | defect | low | `tests/live_server.py` |
| 79 | The lane and merge tooling | feature | low | the launcher part is built |
| 80 | `conflict_guard` is imprecise, and a conflicted `scripts/exit_codes.py` ends in a traceback | defect | low | |
| 81 | The evals: authored recordings, one threshold, exact and regex scorers only, a stale report left by a refused `report_dir` | feature | low | |
| 82 | Whether a colon may follow a requirement id | decision | low | |
| 83 | `make trace` collects from source | defect | low | |
| 84 | A refused `traceability` block leaves the earlier matrix standing | defect | low | |
| 85 | jarvis `kind_evidence` | decision | low | |
| 86 | `run_evals.py --help` prints the header's `kind:` line | defect | low | reproduced by the audit |
| 87 | Typed inputs and the log helper | feature | low | cut from Campaign 5 |
| 88 | The pattern-match allowlist may only shrink | missing-check | low | CMP-5.S4, unstarted: see the CMP-5.S4 note |
| 89 | jarvis's proposals (store migration, removal tests, docstring claims named by a test, closed lists, one home per grammar, load margin in config, an example for an ignored config, lane placeholders, the browser-automation ignore) | feature | low | none built |
| 90 | The exit gate cannot see `getattr`, `os.abort`, `os.kill`, an uncaught exception or argparse's own exits | missing-check | low | |
| 91 | The hand-written `\| Script \| When \|` table is compared with nothing | missing-check | low | |
| 92 | A useless message part passes; only a blank one fails | missing-check | low | |
| 93 | `trace_requirements` refuses a missing git; `gate_evidence` and `run_evals` take the no-git path | defect | low | |
| 94 | The suite's commits share one moment | decision | low | accepted |
| 95 | The run date across a daylight-saving change is not tested | missing-check | low | |
| 96 | A gate longer than `evidence.run_date.max_age_days` refuses | defect | low | |
| 97 | A Ctrl-C run replaces a long record | defect | low | |
| 98 | CONVENTIONS §2 says `scripts/` has two importable modules | doc-drift | low | closed in CMP-5.S4: the note names no count and cites `derived_features`, which reads the set from the import graph |
| 99 | K-0020's recorded limits: a reserved farm status, last writer wins, queue time in the seconds | decision | low | |
| 100 | K-0018, K-0019 and K-0020 are proposed | decision | low | closed: accepted after CMP-5.S4 |
| 101 | `__all__` built with `+=` is not read | missing-check | low | |
| 102 | mypy covers five of nine code roots | decision | low | `pyproject.toml` |
| 103 | One slice id on several commits is not detected | missing-check | low | CMP-4.S7 is on four commits, CMP-5.S2 on two |
| 104 | The query-corpus token cost has no budget | feature | low | |
| 105 | The vault's frontend backlog items | feature | unknown | outside this repo |
| 106 | jarvis ingest and registration | feature | unknown | outside this repo |
| 107 | bedrock-platform's known failures list | defect | unknown | outside this repo |
| 108 | The documentation-quality system, phases 4 to 8 | feature | unknown | `docs/design/documentation-quality.md` not read |
| 109 | Whether a release tag is on the remote | decision | unknown | not checked over the network |
| 110 | `scripts/audit_project.py` exits 1 when it judged zero files, the code it uses for a finding, not `ExitCode.NOTHING_JUDGED` | defect | low | left unchanged in CMP-5.S4 |
| 111 | The launcher does not refuse a configured farm status equal to an `ExitCode` member, so a farm's "not allocated" could read as a script's own code | missing-check | low | `scripts/launch.py` refuses only its reserved statuses; `tests/unit/scripts/test_exit_codes.py` holds 13 alone apart from the configured ones |
| 112 | The exit gate passes a `passthrough` over a function whose returns mix the script's own literals with a tool's status | missing-check | low | stated in `tests/integration/test_exit_gate.py` |

Contradictions the audit found, each settled here or listed above:

- The CMP-5.S2 row named the `sys.exit` rewrite, which is not built. The row
  now says so.
- The grace-tier wording differed: `docs/design/keel-hardening-plan.md` and
  K-0008/K-0009 say "warn one release", CMP-5.S1 and S2 kept the failure, and
  KEEL-DOC-1 says "warn, then fail". The ruling is warn, then fail after a set
  date (B1 above).
- The CMP-3.S4 row is done, but its residual says only the audit's copier is
  constrained: item 6.
- CMP-1.S1 to CMP-2.S3 and CMP-2.S5 predate the `Slice:` trailer rule, so
  their commits carry no trailer, and `work_naming.adoption_boundary` is null.
