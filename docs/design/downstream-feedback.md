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
updated: 2026-10-08
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
lands. The cap is five slices, each one commit on a green `make verify`.

| Slice | Defect | Status |
|-------|--------|--------|
| CMP-3.S1 | `make smoke` passes over zero tests, and `make run` fails with `No module named app` | done — `make verify` green (1517 passed); 5 review findings confirmed and fixed |
| CMP-3.S2 | A document whose only conflict on `copier update` is its `updated:` line is left conflicted for a person to resolve | done — `make verify` green (1562 passed); 1 of 2 review findings confirmed and fixed |
| CMP-3.S3 | A project can add a check only by editing `scripts/check_structure.py`, so its next `copier update` conflicts in the module the restamp task imports | done — `make verify` green (1614 passed); 6 review findings confirmed and fixed; ADR-K-0014 accepted |
| CMP-3.S4 | The `GIT_CONFIG_COUNT`/`GIT_CONFIG_PARAMETERS` variables reach a child, copier's own git calls bypass `build_child_env`, and a bare token or `Authorization` value is not recognised as a credential | done — `make verify` green (1659 passed); 5 review findings confirmed and fixed |
| CMP-3.S5 | Four defects bedrock-platform hit adopting 0.2.0: `make audit-project` under the default `PY=python3` (3.6) dies with a `SyntaxError` (K1); the audit exits 2 when the update's restamp refuses over a conflicted import (K2); a project's `write_shapes` cannot include `-apply` because keel's own `doc-review-apply` is a non-write (K3); and check_W passes a recipe that opens with `$(WRITE_GUARD)` under a non-`[write]` label (K4) | done — `make verify` green (1700 passed); 3 review findings confirmed and fixed; ADR-K-0015 proposed |

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
  CMP-4.S3.
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

**Cap.** Five slices, each one commit on a green `make verify`, in this order.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-4.S1 | `make verify` reports only an exit code and log text, so nothing outside the repo can read which gate ran, on which commit, with what result | planned |
| CMP-4.S2 | A frontend has no test runner, so it ships with zero tests and the gate is green | planned |
| CMP-4.S3 | The e2e scenarios call the app in process, and nothing checks that a route has a scenario | planned |
| CMP-4.S4 | Nothing calls a real model or a running server and judges what comes back | planned |
| CMP-4.S5 | A spec's requirements are not tied to tests, so an uncovered requirement passes the gate | planned — approved by the maintainer |

- **CMP-4.S1, the evidence contract.** `make verify` writes a canonical JSON
  record next to its exit: commit, gate targets run, per-target result, test
  counts, check letters and their findings. It is written under an ignored path
  and is byte-identical on a second run of the same commit. The schema is typed
  and versioned, and a test holds the record to it. This is the format
  project-jarvis ingests; the ingest itself is jarvis work.
- **CMP-4.S2, frontend tests.** Each shipped stack gets a unit runner (Vitest)
  and a browser journey (Playwright, run headless against the built site),
  wired into the gate behind the existing `node_modules` skip. A stack with a
  runner and zero tests fails the gate.
- **CMP-4.S3, Python e2e over a socket.** One scenario starts the real server on
  a free loopback port, drives it over HTTP and stops it. A check fails when a
  route or transport endpoint has no scenario naming it (CONVENTIONS §17).
- **CMP-4.S4, evals that judge actual responses.** A dataset format, a scorer
  and a threshold gate in `evals/`. The default mode replays recorded responses,
  so `make verify` needs no network and no credential; a `[cost]` target runs it
  live through `models/` and the `child_env` allowlist.
- **CMP-4.S5, spec-to-test traceability.** A generic requirement-id grammar and
  a check that every requirement in `docs/specs/` is named by a test or by a
  documented gap, lifted from project-jarvis's `scripts/traceability_matrix.py`.
  jarvis's own copy is then retired in favour of keel's on update; that is a
  jarvis change and needs the maintainer's yes. The live status of each
  requirement stays in jarvis's ledger.

**Queued for Campaign 5.**
- `make new-test MODULE=` writes a mirror test that fails until it is filled in.
- Proof that a test can fail: mutation testing over changed code.
- The vault backlog: KEEL-FE-2, then FE-1, then FE-6; FE-3; TEST-1 (no test
  touches a live store); SEC-1 (secrets scan).
- The agent and playbook contract, the seed of keel-lite: a design document
  and an ADR before any code.
- project-jarvis side, in jarvis's repository: register keel as a tracked
  project and ingest CMP-4.S1's record and the `Slice:` trailers.
