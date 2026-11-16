---
title: CMP-5 — the coding rules move from text an agent reads into code the gate runs
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-5.
id: docs-internals-campaigns-cmp-5
created: 2026-10-12
updated: 2026-11-16
visibility: internal
canonical: true
---

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

- Ten files still read config directly, each named with its reason in
  config/project.json `config_reads.allowed`, and
  `tests/integration/test_config_reads_gate.py` `_CEILING` keeps the map from
  growing. Seven remain queued for migration:
  `scripts/launch.py` with `scripts/long_scripts.py`,
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
- [ADR-K-0021](../../adr/keel/K-0021-imports-flow-up-a-configured-layer-order.md)
  names the bottom layer's members as "the exit helper and the
  child-environment allowlist"; the configured order now holds
  `scripts/config_loader.py` there too. The ADR is accepted, so it is not
  edited; [ADR-K-0022](../../adr/keel/K-0022-one-config-loader.md), accepted,
  states the placement.

**Cut from this campaign.** Typed inputs with a log helper, planned here
before, is queued again to make room for the launcher. Everything else in the
Campaign 4 queue stays queued: the lane and merge parts of the lane and gate
tooling, the frontend backlog, the mutation runner,
`make new-test`, the agent and playbook contract, the D0 decisions,
project-jarvis's proposals, and the residuals of CMP-4.S5 to S8 not named in
CMP-5.S2. The header fields per code file are accepted after CMP-5.S4 and queued
for Campaign 6.

