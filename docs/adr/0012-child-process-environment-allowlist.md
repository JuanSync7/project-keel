---
title: "ADR-0012: A child process gets an allowlisted environment, not every credential the parent holds"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, environment, credentials, subprocess, check-x]
summary: "Every process keel's code starts gets `env=build_child_env(...)` from scripts/child_env.py, which starts from an empty dict and copies only the variable names config/project.json `child_env` declares, plus the `make_targets` unattended and gate variables and, for a model adapter, that adapter's `models.credential_env` names. A missing or malformed manifest is an error, never a fall-back to the parent's environment. check_X in scripts/check_structure.py holds every spawn under the code roots to the helper, with no waiver. It is defence-in-depth, not a sandbox."
id: docs-adr-0012-child-process-environment-allowlist
created: 2026-10-06
updated: 2026-10-06
visibility: internal
canonical: true
---

# ADR-0012: A child process gets an allowlisted environment

**Status:** accepted 2026-10-06 by the maintainer.

## Context

No spawn in keel passed `env=`, so every child inherited the whole environment
of the process that started it. On a developer's shell or a CI runner that
environment holds a cloud provider's keys, a forge token and a model API key.
`models/claude_code_headless.py` handed all of them to the `claude` CLI, which
needs one of them at most.

These are the spawn calls this decision converts, 11 calls in 10 modules:

- `models/claude_code_headless.py` (`run`), the model CLI;
- `agents/doc_reviewer/_brain.py`, `agents/index_enforcer/_brain.py`,
  `agents/practice_refactor/_brain.py` and `agents/wiki_navigator/_brain.py`
  (`_run` in each), which call `scripts/` doers through their CLI;
- `mcp/action_server.py` (`_run_doer`);
- `scripts/run_make_target.py` (`_default_runner`, which runs make, and `_git`);
- `scripts/jobs/review_docs.py` (`_git`) and `scripts/jobs/restamp_docs.py`
  (`_git`);
- `scripts/cdmon_sync.py` (`main`), which runs the external `cdmon` binary.

The count is the one check_X reports over the tree. A spawn through an
unresolvable receiver would not be in it (see Consequences).

## Decision

1. **One helper builds every child's environment.** `build_child_env` in
   `scripts/child_env.py` starts from an empty dict and copies, from the
   parent, only a variable that is present and is:
   - named in `config/project.json` `child_env.names` (`PATH`, `HOME`, the
     locale, the proxy and CA-bundle names, the `GIT_` names that select a
     repository, `VIRTUAL_ENV`, the temp and XDG directories);
   - under a `child_env.prefixes` entry (`LC_`);
   - a `make_targets.unattended_vars` name (`CI`, `RALPH`): the write guard
     must still see one across a Python hop between two makes, because make
     hands its command-line variables to a child through `MAKEFLAGS`, which
     the allowlist never carries;
   - a `make_targets.gate_vars` name (`PY`), so the interpreter a caller chose
     survives the same hop;
   - with `credentials_for=<adapter>`, a name in that adapter's
     `models.credential_env` entry.

   A caller adds anything else with `extra=`, the only in-code addition. A
   missing, unreadable or malformed manifest raises `ChildEnvError`, never a
   fall-back to the parent's environment. The helper is stdlib-only and runs
   under the 3.6 pre-commit interpreter, because `check_structure.py` and
   `cdmon_sync.py` import it.
2. **The names live in config, not code.** `child_env` and
   `models.credential_env` are names only; the values stay in the
   environment. make's own control names (`MAKEFLAGS`, `MAKEFILES`,
   `MAKELEVEL`, `MAKEOVERRIDES`, `MFLAGS`) are refused in any list.
3. **check_X holds every spawn to the helper, with no waiver.** Every
   `subprocess` or `asyncio` spawn in a `.py` at the root or under any
   top-level directory except `tests/` passes `env=` built by the helper,
   directly or through a name bound only to that call and afterwards only
   read. A `**kwargs` spawn, `os.system`, `os.popen`, `os.exec*`,
   `os.spawn*`, `os.posix_spawn*`, `os.forkpty`, `pty.spawn` and
   `subprocess.getoutput` are errors. So is a spawn API referenced without a
   call, a spawn name bound both by an import and another way in one scope,
   and a helper call whose arguments carry `os.environ` or `os.getenv`,
   directly or through a name a value from them reached within the module.
   Names resolve with Python's scope rules. check_X also validates both
   config blocks.
4. **The gate runner forwards a gate variable it was given through the
   environment.** An agent calls `scripts/run_make_target.py` without
   `--make-arg`, so the `PY` its own make set arrives only in the environment.
   The runner forwards each `make_targets.gate_vars` name it finds there onto
   make's command line under the same one-word path-like rule as
   `--make-arg`; an explicit `--make-arg` wins, and a value that is not one
   word is refused before make runs.

## What this is not

It is not a sandbox. A child running as the same user can still:

- read credential files: `~/.aws`, `~/.netrc`, the model CLI's own auth file
  under `HOME`;
- use the network;
- read the parent's environment from `/proc/$PPID/environ`. This was measured
  on the development host, where `kernel.yama.ptrace_scope` is 0: a child
  started with only `PATH` read a planted variable from its parent's
  `/proc/<pid>/environ`.

What the allowlist removes is the default: a tool that logs, uploads or
forwards its own environment no longer carries every credential with it.

## Consequences

- A project that needs another variable in its children adds the name to
  `child_env.names`; a model CLI that authenticates through other variables
  adds them to `models.credential_env.<adapter>`. Neither is a code change.
- A project's own spawn without `env=build_child_env(...)` fails `make check`.
- A proxy URL that embeds credentials (`https://user:pass@proxy`) is still
  passed, because the proxy names are allowlisted. That is a residual risk.
- check_X resolves a call through the import that binds its name in the
  scope Python would look it up in, so a spawn through an unresolvable
  receiver (`self.runner(...)`, `loop.subprocess_exec`,
  `sp = subprocess; sp.run`) is under-reported, never over-reported. It
  follows a parent-environment value through names within one module, not
  across a function parameter. Both are the trade check_V makes.
- `src/` cannot import `scripts.child_env`, so the first spawn site under
  `src/` must move the helper first.
- Environment Modules' exported shell functions (`BASH_FUNC_*`) and
  `PYTHONPATH` are not passed. A caller that needs one passes it with `extra=`.

## Alternatives considered

- **A denylist of secret names.** Rejected. It fails open on every secret
  name nobody listed yet.
- **A list per call site in code.** Rejected. The lists are hardcoded and
  drift from each other.
- **`config/environment.json` from
  [docs/adr/0005-external-environment-manifest.md](0005-external-environment-manifest.md).**
  Deferred, not rejected. ADR-0005 is proposed and not built. If it is built,
  its environment-variable records can subsume `child_env.names`.
- **A required-credential flag per adapter that fails when the name is
  absent.** Rejected. The CLI authenticates by a file under `HOME` or by one
  of several environment alternatives, so an absent name is not an error.
