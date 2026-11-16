---
title: CMP-6 — a generated project is proven whole, and the two high gaps close
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-6.
id: docs-internals-campaigns-cmp-6
created: 2026-10-17
updated: 2026-11-16
visibility: internal
canonical: true
---

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
  minutes, 8 cores and 16 GiB, which is provisional: each job used under one core
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
  [ADR-K-0016](../../adr/keel/K-0016-release-order-tag-before-verify.md) does not
  name the canary step CONTRIBUTING.md's Release section now carries between
  the verify and the push. The ADR is accepted, so it is not edited;
  [ADR-K-0023](../../adr/keel/K-0023-canary-gates-a-release-not-a-commit.md),
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
[ADR-K-0024](../../adr/keel/K-0024-what-a-test-may-reach.md) is proposed.

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
  CMP-6 shipped before the suite ran under pytest-xdist; KEEL-XDIST-1 runs
  `make test` with `-n auto`, and `tests/integration/test_isolation_gate.py`
  exercises the judgement under its workers.
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
config/project.json `secrets.scanner` pins. `make secrets-install`
(`scripts/install_scanner.py`) fetches the release archive
`secrets.scanner.release_assets` pins for this platform from
`secrets.scanner.release_url`, installs its program under the per-user
`secrets.scanner.install_root` only when the archive's sha256 is the pinned
one, keeps the archive beside it, and records the program; it needs no Go
toolchain and no build. The commit hook is the local `secret-scan` hook over
`scripts/scan_secrets.py`, and every scan runs the recorded program only. The
commit hook
scans what a commit adds or changes, or every commit when nothing is staged, and `make secret-scan`, a `make
verify` goal, and CI scan every commit.
[ADR-K-0025](../../adr/keel/K-0025-committed-secrets-keyed-gate-and-scanner.md) is
proposed.

Left by CMP-6.S3 so far:

- Nothing is taken from `PATH`: the installer installs only the archive whose
  sha256 config pins, and a rerun proves the program from the kept archive,
  so a swapped program, a forged file beside it or a swapped archive is
  installed again. A user who can write `secrets.scanner.install_root` or the
  git-ignored record can still swap the program after the install, and no
  scan sees it until `make secrets-install` runs again, because a scan checks
  the program against the record, not the archive;
  docs/guides/deterministic-checks.md lists it as a bypass.
- Measured by hand in a generated project, and not caught by either layer: a
  value split across two string literals; a weak password with no known
  shape; a credential in `package-lock.json`, an `.svg`, `go.sum`, a PDF or
  under `node_modules/`, which the scanner's default rules allow. A
  `--no-verify` or `SKIP=secret-scan` commit passes the hook and is red in the
  history scan. docs/guides/deterministic-checks.md lists every bypass tried.
- `make canary` runs `make secrets-install` in each project before its
  `make verify`, into the real per-user install root
  (`~/.cache/<project_slug>/tools`), outside the run, so the archive is
  fetched once per machine and each later project only records it. The fetch
  needs the release URL reachable; `SSL_CERT_FILE` and the proxy variables
  are in `child_env.names`. The canary was not run in this slice.
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

