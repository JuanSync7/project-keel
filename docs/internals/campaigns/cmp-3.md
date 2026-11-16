---
title: CMP-3 — what blocks bedrock-platform's next update
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-3.
id: docs-internals-campaigns-cmp-3
created: 2026-10-07
updated: 2026-11-16
visibility: internal
canonical: true
---

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

