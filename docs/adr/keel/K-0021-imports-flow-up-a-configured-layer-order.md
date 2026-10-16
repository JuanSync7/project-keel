---
title: "ADR-K-0021: imports flow up a configured layer order, and a shared module never ends the process"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, imports, layers, exit-codes, gate]
summary: "Keel's layering lived in prose: CONVENTIONS section 3 kept callers outside a package's private modules, and nothing stopped shared code from importing the code that uses it. config/project.json import_layers.order now lists the layers bottom to top, each a list of path prefixes, and tests/integration/test_import_layers_gate.py fails an import into a higher layer, a file no layer holds and a layer entry that places no file. check_D also fails `from pkg import _sub` of a private submodule from outside the package. A module another project module imports never calls fail or finish outside its entry block, which tests/integration/test_exit_gate.py enforces; import_layers.may_end_the_process names the one module that may, with its reason. The order is config, so a project reorders it without editing a test."
id: docs-adr-0021-imports-flow-up-a-configured-layer-order
created: 2026-10-14
updated: 2026-10-16
visibility: internal
canonical: true
---

# ADR-K-0021: imports flow up a configured layer order

**Status:** accepted 2026-10-16 by the maintainer. It adds a config block and gate tests, and it edits no
other ADR. Every exit still goes through `scripts/exit_codes.py`, and the
package boundary of CONVENTIONS §3 still holds.

## Context

CONVENTIONS §3 says a caller imports a package's public names and never its
private modules, and check_D enforced the absolute form,
`from pkg._sub import x`. Three gaps stayed open:

- `from pkg import _sub` reaches the same private module by naming it as an
  attribute of the package, and check_D did not read it.
- Nothing stated which code may import which. A shared module that imports
  the code that uses it makes every change to the user a change to the shared
  code, and a cycle that only shows at run time.
- A module that other modules import could still call `fail`, which ends the
  process from inside a library, so its caller cannot decide what the failure
  means.

A measurement over the template, read with `tests/source_tree.py`
`import_edges`, found 235 Python files and 496 resolved import edges, none of
them pointing up the order below.

## Decision

1. **One configured order.** config/project.json `import_layers.order` lists
   the layers bottom to top, each a list of repo-relative path prefixes. The
   template ships the exit helper and the child-environment allowlist first,
   then `src/shared`, `src/backend`, `src/app`, the model and runtime
   adapters, `agents`, `evals`, the transports and the demo, `scripts` and
   `tests`. A file sits in the layer of its longest prefix, matched by whole
   path segments.
2. **Imports flow up.** `tests/integration/test_import_layers_gate.py`
   resolves every `import` and `from ... import` through
   `import_layers.search_roots`, and fails an edge into a higher layer. It
   fails a file no prefix places and a prefix on disk that places no file,
   and skips a prefix whose path is absent, such as a transport copier
   pruned. A name the standard library owns never resolves to a project file.
3. **A private submodule is private by name too.** check_D fails
   `from pkg import _sub` when `pkg/_sub.py` or `pkg/_sub/__init__.py` exists
   and the importer lies outside `pkg/`; a relative import that climbs out of
   the package is judged as its absolute twin would be.
4. **A shared module never ends the process.** A module another project
   module imports (an import from `tests/` does not count) never calls `fail`
   or `finish` outside its entry block; `tests/integration/test_exit_gate.py`
   fails one that does. `passthrough` only marks a status and returns it, so
   it is allowed. `import_layers.may_end_the_process` names a module that may,
   with a non-blank reason, and an entry naming no such module is a finding.
   The template names one: `scripts/jobs/conflict_guard.py`, whose
   `exit_if_conflicted` runs in a job's entry block before the job imports
   anything else, so there is no `main` to return to yet.
5. **Not a check letter.** The gates are tests under `tests/integration/`,
   because the letters A to Z of `scripts/check_structure.py` are taken, and
   they share one reader, `tests/source_tree.py`, so no two of them disagree
   about which files are the project's.

## Consequences

- A new top-level directory is not done until its prefix sits in a layer,
  as it is not done until it is a CONVENTIONS §2 row.
- A project reorders or adds layers by editing config, in `project.json` and
  its `.jinja` twin, never a test.
- The gate cannot see an import made through `importlib`, `__import__` or a
  `sys.path` entry no search root names, and an import under `TYPE_CHECKING`
  or in `try/except ImportError` counts as a real edge.
- A shared module that must stop a run raises, and the entry point's `main`
  turns the exception into `report(...)`.

## Alternatives considered

- **A third-party import linter.** Rejected: it would be one more pinned
  tool, and the hook interpreter that runs the structure gate cannot import
  it. The reader is about two hundred lines of standard library.
- **Hard-code the order in the test.** Rejected: the order is a project fact,
  and a project that adds a layer would have to edit a shipped test.
- **Exempt `passthrough` by config.** Rejected: it ends nothing, so listing
  each module that returns it would be an exemption for a rule that does not
  apply.
- **Rewrite `conflict_guard.py` to return.** Rejected for now: its caller is
  an entry block that runs before the job imports anything else of the
  project, and the job's next import may be the conflicted file; the
  exemption states that reason where the gate reads it.

## Scope cuts

Not built: an allowlist of single upward edges, a check of imports inside
frontend code, a cycle detector within one layer, and an allowlist of the
modules that may import `re`.
