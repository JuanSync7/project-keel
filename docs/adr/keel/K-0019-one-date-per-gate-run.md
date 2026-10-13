---
title: "ADR-K-0019: one gate run has one date, handed to every goal through the child-environment allowlist"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, gate, freshness, verify, child-env, evidence]
summary: "A make verify that crossed midnight turned red on every document touched that day, because the freshness judge read the clock again late in the run. The gate's driver now reads the clock once, before the first goal, and hands that date to every goal in the variable config/project.json evidence.run_date.env names. The judge reads the variable after --today and SOURCE_DATE_EPOCH and before the clock, which adds one step to the order ADR-K-0010 decision 5 states. A supplied date is checked on every read: it may be earlier than the clock by at most evidence.run_date.max_age_days and never later. A commit the test suite makes inside a run is dated by the run as well, so the date git records agrees with the stamps the run wrote. The same slice makes two more gate rules fail closed: a git command that ran and failed is refused rather than read as no git, and the driver refuses an evidence path reached through a symlink."
id: docs-adr-0019-one-date-per-gate-run
created: 2026-10-12
updated: 2026-10-13
visibility: internal
canonical: true
---

# ADR-K-0019: one gate run has one date

**Status:** proposed. It adds one step to the order of date sources in
decision 5 of [ADR-K-0010](K-0010-generation-needs-trust-to-stamp-docs.md), and
it adds two refusals to the driver
[ADR-K-0017](K-0017-gate-evidence-record.md) describes. Both ADRs stand
otherwise, and neither file is edited.

## Context

`updated:` means *touched in this repository*.
`scripts/jobs/review_docs.py` `stale_findings` fails a document that differs
from `HEAD` when its stamp is earlier than today, and `resolve_today` decided
what today is: `--today`, then `SOURCE_DATE_EPOCH`, then
`datetime.date.today()`.

`make verify` runs its goals in sequence, and two of them ask that question
late: `make check-docs` inside `check-all`, and
`tests/integration/test_doc_freshness.py` inside `test`. Each is its own
process and read the clock when it started. A run that began before midnight
with a document stamped that day reached the judge after midnight, and the
judge found the stamp one day old. The gate was red and nothing in the tree
was wrong. Restamping by hand and running again was the only remedy.

Two other gate rules were weaker than their own documents said.

- `scripts/git_tree.py` raised `NoGitError` for every failure of a git
  command. Its callers read that as "there is no repository, so nothing can be
  dirtied" and wrote without the ignore check. git exits 128 for "not a
  repository" and also for a repository it cannot read, so an unreadable
  repository took the permissive path.
- `scripts/gate_evidence.py` checked config/project.json `evidence.dir` as
  text and against the ignore rule. Neither looks at a symlink, so a record
  written, or a stale junit report deleted, under a symlinked component could
  land outside the project. `scripts/run_evals.py` and
  `scripts/trace_requirements.py` already called
  `scripts/git_tree.py` `through_symlink` for their own paths.

## Decision

1. **The driver fixes the date.** `scripts/gate_evidence.py` calls
   `scripts/run_date.py` `for_run` once, before the dry-run branch and before
   the first goal, and passes the answer to every goal through
   `build_child_env(extra=...)`. It is the same hand-off the driver already
   uses for the junit report path: one value, decided once, given to each
   goal.
2. **Config names the channel.** config/project.json `evidence.run_date` holds
   `env` (`KEEL_GATE_RUN_DATE`), the variable the date travels in, and
   `max_age_days` (`1`), how many days before the clock a supplied date may
   be. No script holds either value. `scripts/run_date.py` `policy` refuses a
   block whose `env` is not in `child_env.names`, because
   `scripts/child_env.py` would then drop the variable at the first process
   below the driver and the checks would silently read the clock again.
3. **The judge reads it third.** `review_docs.resolve_today` now ends in
   `scripts/run_date.py` `today`: `--today`, then `SOURCE_DATE_EPOCH` in UTC,
   then the run's date, then the clock. The run's date comes after the two
   pins because each pin is a caller's explicit choice of day, and the run's
   date only stands in for the clock. `scripts/jobs/restamp_docs.py` and
   `scripts/audit_project.py` share `resolve_today`, so the writer and the
   judge still stand on one day.
4. **A supplied date is checked on every read.** It must be written
   `YYYY-MM-DD`, be a calendar date, be no later than the reader's clock and
   no more than `max_age_days` days before it. Anything else is a refusal that
   names the variable and the key. The driver refuses with exit 2 before any
   goal, and a check refuses with its own exit 2. Neither falls back to the
   clock: a fallback would hide the wrong value and bring back the defect.
5. **An outer run's date is kept.** A driver that finds a valid date already
   in the variable hands that date on, so a gate started inside a gate is
   still one run.
6. **A missing block switches the channel off.** With no `evidence.run_date`,
   or no config/project.json, the driver sets nothing and every check reads
   the clock, as before. That is the strict side of the rule.
7. **git's failures are told apart at the source.** `scripts/git_tree.py`
   raises `NoGitError` only when git is not installed or no directory at or
   above the root holds a `.git` entry, decided by walking the filesystem the
   way git does (stopping at `GIT_CEILING_DIRECTORIES` and at a filesystem
   boundary). Every other failure is `GitFailedError`, which is not a
   `NoGitError` and carries git's exit status and its stderr.
   `scripts/gate_evidence.py`, `scripts/run_evals.py`,
   `scripts/trace_requirements.py` and `scripts/run_make_target.py` refuse on
   it and write nothing.
8. **The driver checks its paths for symlinks.** Before the ignore check and
   before the first write, `scripts/gate_evidence.py` passes the record, its
   temporary file and every goal's junit report to `through_symlink` and
   refuses with exit 2 when any resolves through one.
9. **A commit the test suite makes is dated by the run.**
   `tests/hermetic_git.py` `git_env_vars` builds the git environment of every
   test, and `tests/conftest.py` applies it to the whole session. When the
   variable is set it adds `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` from
   `scripts/run_date.py` `git_dates`: one read of the clock to the second,
   held back to 23:59:59 local time on the run's date once the clock has
   passed that day. `hermetic_git.clone_including_worktree` commits the
   working tree before a test judges it, and the copier tests commit the
   project they generate. Each commit dated by the clock after midnight sat a
   day past the stamps the run wrote, and the judge's commit-date floor called
   the documents stale: a `make verify` from 23:18 to 01:08 failed three goals
   that way, with 17 and 133 stale documents (measured).

## Consequences

- **The variable is a new input to the freshness rule, and it is bounded.**
  Whoever can set `KEEL_GATE_RUN_DATE` in the environment of a check can move
  that check's today back by `max_age_days` days and never forward. With the
  shipped bound of `1` a document touched today and stamped yesterday passes
  when the variable says yesterday. `SOURCE_DATE_EPOCH` already let the same
  caller move today back without any bound (ADR-K-0010, "A pinned date can
  lag"), so this adds no power that caller lacked. The commit-date floor is
  untouched: a committed document's stamp is still compared with the date git
  recorded. Only the test suite's own commits take their date from the
  variable (decision 9), and a test that sets `GIT_COMMITTER_DATE` itself
  still wins.
- **The suite's commits share a moment.** Under every `make verify` the
  variable is set, so the commits made under one git environment carry the
  second it was built at. A test that needs commits in a date order sets its
  own dates, as the copier and restamp tests already do.
- **`max_age_days` is how long a run may last.** A gate that runs longer than
  the bound has every later check refuse with exit 2 naming the key, which is
  louder than the old false stale finding. A project with a longer gate raises
  the bound and accepts the wider window above. `0` means a run may not cross
  midnight at all.
- **A check run by hand is unchanged.** Outside a driver the variable is
  unset, so `make check-docs` and a bare pytest read the clock.
- **A caller's stale export is refused, not ignored.** A shell that still
  exports the variable from an earlier day stops the gate before any goal.
  The message names the variable; the fix is to unset it.
- **An unreadable repository now stops the gate.** A corrupt `.git`, a
  repository owned by another user that git refuses as unsafe, or a git that
  cannot start used to be read as "no git". Each is now an exit 2 that quotes
  git's status and the first 400 characters of its stderr
  (`scripts/git_tree.py` `STDERR_MAX`).
- **Two readers of "git is not installed" still differ.** Inside a repository
  with no git on `PATH`, `scripts/trace_requirements.py` refuses, as it did
  before, and `scripts/gate_evidence.py` and `scripts/run_evals.py` take the
  no-git path, as they did before. This decision does not unify them.
- **`scripts/run_date.py` is a shared module.** It is stdlib-only and safe
  under the oldest interpreter the driver supports, because the driver
  imports it. It declares reading `config/project.json`, so the copier job
  that restamps documents refuses over a conflicted manifest, naming it.

## Alternatives considered

- **The driver exports `SOURCE_DATE_EPOCH`.** Rejected. That variable already
  means a pinned, reproducible build, and other tools read it: a driver that
  set it on every run would change what they produce. It is also unbounded,
  and it outranks nothing a caller could use to tell a real pin from the
  driver's own.
- **Pass `--today` down each recipe.** Rejected. The judge is reached through
  make, pytest and a test's own child process; a flag would need a make
  variable in every recipe on the way, and a project's own recipe would lack
  it.
- **Write the date to a file under `evidence.dir`.** Rejected. A file outlives
  the run that wrote it, so every reader would need to prove the file belongs
  to its own run, and a check run by hand the next day would find it.
- **Accept the variable without a bound.** Rejected. An unbounded variable
  would be a second `SOURCE_DATE_EPOCH` with a project-specific name and no
  reason to exist.
- **Let the judge accept yesterday's stamp near midnight.** Rejected. It
  weakens "`updated:` means touched" for every run in order to excuse the few
  that cross midnight.
- **Decide "no repository" from git's stderr text.** Rejected. The text is
  translated by locale and changes between git versions; the status is 128
  for both cases. The filesystem walk asks the same question git asks.
