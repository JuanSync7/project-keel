---
title: "ADR-K-0020: one launcher decides where a long script runs, and an unknown host counts as shared"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, launcher, shared-compute, farm, child-env, security]
summary: "A long script such as make verify ran wherever it was called and took CPU other people were using on a shared host. One neutral launcher, scripts/launch.py, now decides where a script runs from three facts and prints the decision and its reasons in one line. The facts are the host kind, the script length and the farm. A host is one person's own only when a pattern in a git-ignored local file matches it; an absent, unreadable or unmatched file means shared. A script is long when config lists it or its last recorded run took longer than a threshold, and a script with no record counts as long. The farm is an adapter chosen in config: none ships as the default and Slurm is one interchangeable option, written as an argv list. A local-only script never goes to the farm, and a farm job receives a credential only when config names it for that script. Each run's outcome and whole seconds are recorded, and a read-only search proposes the scripts to list as long. The launcher is defence in depth for shared compute, not a scheduler."
id: docs-adr-0020-shared-compute-launcher
created: 2026-10-13
updated: 2026-10-15
visibility: internal
canonical: true
---

# ADR-K-0020: one launcher decides where a long script runs

**Status:** accepted 2026-10-15 by the maintainer. It adds a doer and a config block, and it edits no
other ADR. Running a child process still follows
[ADR-K-0012](K-0012-child-process-environment-allowlist.md), and every exit
still goes through `scripts/exit_codes.py`.

## Context

Nothing in keel decided where a script runs. The full `make verify` takes
about an hour and three quarters on 8 CPUs. Called on a host many people
share, it takes CPU they are using. On a person's own machine, running it
there is fine. Where a job farm exists, the farm is where it belongs.

Three facts decide the right place, and each can be unknown:

- Whether the host is one person's own. A host name is confidential, so the
  repository cannot list one.
- Whether the script is long. A list in config covers the scripts known to
  be long; a script nobody listed may still be long.
- Whether a farm exists, and whether it starts the job in time.

## Decision

1. **One neutral doer.** `scripts/launch.py -- <command>...` decides where the
   command runs and writes one stderr line that names the decision, the host
   kind, the script length and the farm state, each with its reason. The line
   never names a host or an absolute path.
2. **The host kind fails closed to shared.** The kind is `in-farm-job` when a
   variable the active farm adapter's `inside_env` lists is set. Otherwise it
   is `own` only when the host's name, lower-cased with a trailing dot
   dropped, matches an `fnmatch` pattern in the git-ignored file
   config/project.json `launcher.own_hosts_file` names. fnmatch is the
   pattern language on purpose: the file holds patterns such as
   `workstation-*.example.com`, not names. An absent, unreadable or malformed
   file, an empty list, a blank host name and no match all mean `shared`.
   Keel ships only `config/own-hosts.example.json`, with placeholder names.
3. **A script is long unless a success proves it short.** The launch key is
   the command with variable assignments removed and absolute paths made
   relative to the project. A key `launcher.long_scripts` lists is
   `long-listed`. A key whose last recorded run in the git-ignored
   `launcher.durations_file` took more than `launcher.long_after_seconds` is
   `long-recorded`. Only a run that succeeded within the threshold makes a key
   `short`. A failed or interrupted run within it gives only a lower bound,
   and no record, an unreadable record or a run that did not start leaves the
   key `unknown`. Unknown counts as long.
4. **The decision table.** In order: a farm job, an own host or a short
   script runs here. A long or unknown script on a shared host runs here
   limited when `launcher.local_only` lists it or the active adapter is of
   kind `none`. Otherwise it is submitted to the farm, which may wait up to
   `launcher.farm.wait_seconds` to start it.
5. **Limited means os.nice and nothing else.** A limited run lowers its CPU
   priority by `launcher.limited.niceness`. The standard library cannot cap
   CPU or memory, so the launcher claims neither.
6. **A full farm falls back only to a spare host.** When the farm reports
   that it did not start the job in time, the script runs here limited only
   if max(1-minute, 5-minute) load average per cpu is at most
   `launcher.spare.max_load_per_cpu`. An unknown load is not spare. Otherwise
   the launcher stops with exit 12, `NO_CAPACITY`. A status the farm reserves
   for its own failure is reported with exit 2, never as the script's result.
7. **Vendor-neutral farm adapters.** The farm is the
   `launcher.farm.adapters` entry `launcher.farm.adapter` names. Kind `none`
   means no farm and is the shipped default, so a generated project needs no
   farm. Kind `argv` submits through a command written in config as an argv
   list, run with no shell. Its words may hold only a closed set of
   placeholders, and any other brace is refused. Slurm ships as one argv
   adapter. The adapters live in config, beside the launcher that reads them,
   because an adapter here is data, not code: a second farm is a second entry.
8. **Credentials stay home unless named.** A script `launcher.local_only`
   lists never goes to the farm. A farm job's environment is built by
   `scripts/child_env.py` `build_child_env`, never copied from the caller's.
   It receives a credential only when `launcher.credentials` names it for
   that launch key.
9. **State paths are refused before anything is read.** A state path that a
   symlink reaches, or that git would list, is refused with exit 2, so a host
   pattern or a run record cannot be committed.
10. **A small Farm interface.** `make_farm` returns a `Farm` with three
    methods: `submit_argv(size, cfg)`, the rendered submit words;
    `submit_env_extra(size, cfg)`, the rendered `env`; and `classify(status)`,
    one of `ran`, `not-allocated` and `refused`. `NoFarm` (kind `none`) raises
    on every method, because the decision table never sends it a command.
    `ArgvFarm` (kind `argv`) reads both answers from config. A farm that needs
    more than an argv and a status becomes a third kind, beside these two.
11. **The exact environment of a farm job.** The submit command is started
    with `build_child_env(credentials_for=<the key's model_adapter>,
    extra=<the adapter's rendered env>)`. So it receives the variables the
    allowlist copies from the caller (`child_env.names`, a `child_env.prefixes`
    name and the `make_targets` gate variables), the `models.credential_env`
    names of the model adapter `launcher.credentials` names for the key, and,
    for the shipped Slurm adapter, `SLURM_EXIT_IMMEDIATE=251` and
    `SLURM_EXIT_ERROR=252`. `srun --export=ALL` hands that environment to the
    job, with the variables the farm adds itself. A run here gets the same
    environment without the adapter's env. Before anything runs, a launch is
    refused with exit 2 when that environment holds a credential name (one
    any `models.credential_env` list or `child_env.credentialed_values`
    names) that the key's `launcher.credentials` entry does not list. The
    message names the variables and the config key, never a value.
12. **Every run is recorded whole.** Before the command starts, the launcher
    writes an `incomplete` entry for the launch key; after it ends, the
    outcome (`succeeded`, `failed` or `interrupted`), the whole seconds, the
    status and where it ran (`own-host`, `shared-host` or `farm`). A farm that
    did not start the command with no spare host records `no-capacity` with no
    seconds; a farm that refused, or a submit command that is not installed,
    restores the entry the run replaced. Neither `incomplete` nor
    `no-capacity` replaces an entry whose measured duration is over
    `launcher.long_after_seconds` (`unmeasured_record` in scripts/launch.py):
    no run was measured, so that run stays the last one, and a full farm or a
    killed launch cannot hide a long script from the search in item 13. The
    file is canonical JSON with one entry per key, written to a temporary file
    in the same directory and moved over the old one, so a second identical
    run leaves the same bytes.
13. **A search proposes; a person lists.** `scripts/long_scripts.py`
    (`make long-scripts`) imports the launcher's config loader and record
    reader, and prints a `propose:` line for each key whose last measured run
    took longer than `launcher.long_after_seconds` and that
    `launcher.long_scripts` does not list. It edits nothing. A file with no
    measured run fails, because judging nothing is not "none is long", so the
    target is in neither `make check-all` nor `make verify`, where a fresh
    clone would always fail.

## Consequences

- On a shared host with the shipped config, `scripts/launch.py -- make verify`
  runs the gate here at a lower CPU priority and says so in one line. Moving
  it to a farm takes one config edit: `launcher.farm.adapter`.
- A project that never runs the launcher is unchanged: the `verify` recipe
  does not call it.
- The launcher is defence in depth for shared compute, not a scheduler. It
  does not queue, retry, or cap CPU or memory, and whoever can edit
  `config/project.json` can mark any script short by editing the durations
  file or any host own by writing a pattern.
- An unknown script on a shared host goes to the farm or runs limited, so a
  short script nobody has recorded yet pays the farm's start-up wait once.
- A command that itself exits with the adapter's `not_allocated_status` or
  `farm_error_status` (251 or 252 for Slurm) is read as the farm's status: it
  is re-run here or reported as refused. The statuses are config, so a
  project whose tools use them picks others.
- Because the submit command receives only the allowlist, a Slurm input
  variable the caller set (`SBATCH_*`, `SLURM_*`) does not reach `srun` unless
  `child_env.names` lists it; the size comes from config instead.
- The run record is last writer wins: two launches of one key at once keep
  the entry of whichever ends later, and nothing locks the file. A farm job's
  seconds include its time in the queue, and seconds are rounded to the
  nearest whole second.

## Alternatives considered

- **List host names in config.** Rejected: a host name is confidential and
  would be committed. The local file keeps it out of the repository.
- **Treat an unknown host as own.** Rejected: the harm of running a long
  script on a shared host falls on other people, and the person who left the
  file out would not see it.
- **A Python adapter class per farm, in a new top-level directory.** Rejected
  for now: every farm in reach is driven by a command and its exit status,
  which an argv list in config describes, and a new top-level directory needs
  a CONVENTIONS §2 row for one consumer.
- **Change the `verify` recipe to call the launcher.** Rejected: ADR-K-0017
  fixes what the recipe runs, and a gate that moves itself to a farm cannot
  be run by hand the same way. A person calls the launcher in front of it.
- **Let the search edit `launcher.long_scripts`.** Rejected: a size is a
  judgement about a farm's queues, and a writer to config would be a second
  owner of the block.
- **Cap CPU with cgroups or `taskset`.** Rejected: neither is in the standard
  library, both depend on the host's configuration, and a cap the launcher
  cannot enforce must not be claimed.

## Scope cuts

Not built: queueing or retrying a submission, a lock on the run record,
splitting a farm job's queue time from its run time, a per-farm Python class,
moving a run between farms, and calling the launcher from any make recipe.
