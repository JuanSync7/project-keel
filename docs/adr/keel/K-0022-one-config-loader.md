---
title: "ADR-K-0022: one config loader in the bottom layer, the environment over the file only where a row names a variable, and its own exit code"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, config, loader, defaults, exit-codes, gate]
summary: "Each script read config/project.json its own way, with its own defaults in `.get(key, default)` calls, so a default was a value nobody chose and nobody saw. scripts/config_loader.py is now the one reader: KEYS is the one table of declared keys, `read` the one open and parse of a config file, `resolve` the one judge of a value, and `env` the one literal-name read of a declared variable. It sits in the bottom import layer, beside the exit helper and the child-environment allowlist. A row that names a variable takes the variable over the file when it is set and not empty, and no other row reads the environment. An unset key with a default says so on stderr; an unset required key or a wrong value is refused by name, and the entry point exits 14, ExitCode.CONFIG. tests/integration/test_config_reads_gate.py fails a direct read outside the loader that config/project.json config_reads.allowed does not excuse."
id: docs-adr-0022-one-config-loader
created: 2026-10-16
updated: 2026-10-17
visibility: internal
canonical: true
---

# ADR-K-0022: one config loader

**Status:** accepted 2026-10-17 by the maintainer. It adds a module, a config block, an exit code and a gate
test, and it edits no other ADR. The child-environment allowlist of
`K-0012-child-process-environment-allowlist.md` keeps its meaning: the loader
decides how a declared variable is read, never which variables a child gets.

## Context

Before this decision each script opened config/project.json itself and read a
key with `.get(key, default)`. Three faults followed from that:

- A default lived in the code that read the key, so two readers of one key
  could hold two defaults, and a project that deleted a key never learned which
  value it was running with.
- An absent key and a key of the wrong type took whatever path the reader
  happened to take: a traceback, a silent fallback, or exit 2 beside a usage
  error.
- A variable the config declares, such as a model credential, was read by
  `os.environ.get` wherever it was needed, so no one place said whether the
  environment or the file wins.

## Decision

1. **One loader, in the bottom layer.** `scripts/config_loader.py` is the one
   module that opens config/project.json or config/practices.json
   (`PROJECT_READS`) and the one literal-name reader of a declared variable.
   Its `KEYS` table gives each key its path, its type from the closed set
   `TYPES`, its default or `NONE` (no default, so the key is required), whether
   it is a secret, its meaning, the variable that may set it, the file it lives
   in and an optional bound. config/project.json `import_layers.order` puts it
   in the bottom layer beside `scripts/child_env.py` and
   `scripts/exit_codes.py`, because `scripts/child_env.py` reads its allowlist
   through it and every layer imports that. It stays stdlib-only and 3.6-safe,
   so the hook interpreter can run it, and
   `tests/integration/test_gate_scope.py` holds every file of that layer to that
   interpreter.
2. **The environment wins only where a row names a variable.** A row that
   names a variable takes it when it is set and not empty, and the file's value
   otherwise. A row with no variable reads the file only, and a variable-only
   row reads its variable only. An empty variable counts as unset. `env(name)`
   refuses a name that neither a `KEYS` row nor the config declares, so a read
   of an undeclared variable cannot pass for a configured value.
3. **A config fault has its own exit code.** An unset key with a default takes
   it and writes `[using default] <key> = <value>` to stderr once per process,
   a secret's value shown as `<hidden>`. An unset required key is a
   `[not set] <key>` line, and a wrong value is one line naming the key, its
   JSON type and what is accepted. The loader writes every such line before it
   raises, and never ends the process: the entry point returns
   `report(ExitCode.CONFIG, ...)`, exit 14. `USAGE` (exit 2) keeps its meaning
   for a bad argument and for a refusal the loader does not make, such as an
   unreadable schema file or a path git would list.
4. **A direct read is red.** `tests/integration/test_config_reads_gate.py`
   walks the code roots config/project.json `config_reads.roots` names and fails
   an open of a `PROJECT_READS` file, or a read of a declared variable, outside
   the loader. config/project.json `config_reads.allowed` names each file that
   still reads directly with its reason, and the test's ceiling only falls.

## Consequences

- During the transition two exit codes mean a config fault. A module that
  `config_reads.allowed` lists still writes its own message and exits 2 until
  it is moved onto the loader; a migrated script exits 14. A wrapper that
  tested for 2 on a bad config value tests for 14 as well.
- A project that deleted a defaulted key sees a `[using default]` line on
  stderr after `copier update`; the exit code does not change.
- Where the gate runs decides whether a finding is red. In the template
  repository, which holds `copier.yml`, every file under `config_reads.roots`
  is keel's and a finding is red. A generated project carries no list of the
  files keel shipped, so there the two finding tests skip and name each
  direct read they saw, until the warn-then-fail tier for a project's own code
  is built.
- A new configured key is not done until it has a `KEYS` row; its default, if
  any, lives there and in its `docs/reference/settings.md` row, where
  `tests/integration/test_config_default_lines_docs.py` holds the quoted line
  to the loader's output.

## Alternatives considered

- **Exit 2 for a config fault.** Rejected: 2 already means a bad argument or a
  refused input file, and a caller could not tell "fix the config" from "fix
  the command line". A narrower meaning for 2 would change every script's
  contract at once; a new member changes only the migrated ones.
- **The environment over the file for every key.** Rejected: any variable in
  a shell would then override a committed value, and the allowlist of
  `K-0012-child-process-environment-allowlist.md` would no longer bound what a
  value may come from. A row names its variable, so the override is declared.
- **A third-party settings library.** Rejected: the hook interpreter cannot
  import one, and the table, the type set and the lines are about eight hundred
  lines of standard library.
- **A loader in `src/shared`.** Rejected: `scripts/child_env.py` and
  `scripts/check_structure.py` run under the hook interpreter, which cannot
  import `src/`.

## Scope cuts

Not built: a schema file generated from `KEYS`, rows for the `launcher`,
`traceability` and `layers` blocks (their readers are in `config_reads.allowed`),
a list of the files keel ships, which would let a generated project judge
keel's files and spare its own, and a warning tier for a generated project.
