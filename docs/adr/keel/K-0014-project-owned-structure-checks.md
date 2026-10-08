---
title: "ADR-K-0014: A project adds structure checks in a directory it owns, not by editing the gate"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, copier, update, check-structure, extension]
summary: "A generated project adds its own structure checks as modules in a top-level directory it owns, named by config/project.json `structure.project_checks`, and never as an edit to scripts/check_structure.py. The gate runs each module's `check(root)` after every lettered check, in file-name order, reports each finding as `project:<stem>`, and turns every way a module can fail into an ERROR naming it. A project check only adds findings: no knob waives a template check. Every `copier update` after-migration refuses to run over a conflicted module it imports, exit 2, and the restamp leaves a conflicted document for the merge."
id: docs-adr-0014-project-owned-structure-checks
created: 2026-10-08
updated: 2026-10-08
visibility: internal
canonical: true
---

# ADR-K-0014: A project adds structure checks in a directory it owns

**Status:** proposed.

## Context

The structure gate, `scripts/check_structure.py`, is template-owned. Until
this decision, a project that wanted one more rule had nowhere to put it but
that file. Both measured downstream projects did so:

- **bedrock-platform** added an effect-label check for its make targets (223
  lines inserted, 13 removed), including a reader of every makefile that
  `check_P` now shares.
- **project-jarvis** added a Markdown-link check, widened the owner roll-up
  from tools and agents to every governed document, added `.claude` to the
  ignored directories and `self` to the taxonomy (115 changed lines).

The template kept changing the same file. On `copier update`, copier 9.x
merges a file both sides changed with `git merge-file`, and leaves markers in
it where the two edits overlap. Every `after` migration in `copier.yml`
imports `check_structure` (directly, or through
`scripts/jobs/review_docs.py`). In the rehearsal of keel slice project_keel:CMP-3.S2 the restamp migration
died on a `SyntaxError` traceback at the first marker in that file, on both
replicas. The traceback named neither the file to fix nor the command to run
afterwards, and the update exited 1
(keel slice project_keel:CMP-3.S2 in `docs/design/downstream-feedback.md`).

## Decision

1. **A project check is a module in a directory the project owns.**
   `config/project.json` `structure.project_checks` is absent or null (off,
   and silent), or the name of a directory already declared in
   `structure.extra_toplevel`. Reusing that declaration gives the directory
   check_B's guarantees: it sits at the top level, it is outside the §2
   taxonomy, it carries a `README.md` and `CLAUDE.md`, and the template never
   ships a file into it, so `copier update` never merges one. Any other value
   is a check_B ERROR. A declared directory that holds no module is an ERROR,
   because a pass over zero checks proves nothing. The template never ships
   the key, not even as null: the shipped `structure` block is two lines, and
   a key the template inserted beside `extra_toplevel` conflicted on update
   with every project that had declared a directory there (measured on this
   decision's own first draft). A project adds the key when it adopts.
2. **The contract is one function.** Every top-level `*.py` name in that
   directory, in sorted file-name order, is a check module, a symlink
   included. Dot-files, subdirectories and other files are not. A module defines `check(root)`,
   which returns an iterable of `(tier, message)` pairs, with the tier
   `"error"` or `"warning"`. The gate runs each check after every lettered
   check and reports each finding as `project:<stem>`, its message prefixed
   with the module's root-relative path. A module may `import check_structure`
   and gets the running gate, with its `ROOT`, its readers and its `err()` and
   `warn()`: what a module reports through those is its own finding at that
   tier, beside what it returns, so a rule moved out of the gate unchanged
   still fails it.
3. **Every failure is an ERROR naming the module.** These are all errors:
   - a name that is not a regular file, such as a dangling symlink (it is
     never opened)
   - a file that cannot be read, is not UTF-8, holds a conflict hunk (it is
     then never executed) or does not compile
   - a module that raises or exits while loading
   - a missing or non-callable `check`
   - a `check` that raises, exits, or returns a malformed value
   - a module that leaves the gate's `errors` or `warnings` as anything but a
     list
   A `SystemExit` counts as a raise, so `sys.exit(0)` cannot end the gate
   green. Each module is compiled from the bytes the gate read, and is never
   put in `sys.modules` or cached.
4. **A project check only adds.** The template's findings are complete before
   the first project module loads, and each module runs against fresh
   `errors` and `warnings` lists that are put back afterwards, so a module that
   empties or rebinds them hides nothing. There is no key that waives or downgrades a template
   check. A project that disagrees with one changes the template or carries a
   documented edit, and owns that edit's conflicts.
5. **The audit never runs them.** `scripts/audit_project.py` judges another
   project with this template's checks only. Its not-checked section names the
   project checks, because they are that project's code.
6. **An update stops cleanly over a conflicted import.**
   `scripts/jobs/conflict_guard.py` follows a job's imports through the
   project's own modules. Before importing anything from the project, each
   `after` migration (`keep_edited_retired`, `declare_no_app`,
   `resolve_stamp_conflicts`, `restamp_docs`) asks it whether any of them
   holds a conflict hunk. If one does, the job names each file and line and the
   command to rerun once they are resolved, and exits 2 with no traceback.
   `scripts/jobs/restamp_docs.py` leaves a document git lists as unmerged, or
   one that holds a hunk, together with its twin, names each skip on stderr,
   and still exits 0. It never rewrites a stamp inside a conflict a person has
   yet to resolve.

## Consequences

1. **The conflict the gate caused moves out of the gate.** A project that
   moves its rules into its own directory receives the template's
   `scripts/check_structure.py` on its next update with nothing to merge. A project that keeps its
   edits still conflicts there, and is now told which file and which command,
   instead of reading a traceback.
2. **The project-check directory is not under the code-root checks.**
   check_O, check_E and check_V cover `CODE_ROOTS`, which do not include a
   project's extra top-level directories, so a module there needs no gated
   header. check_X still holds every spawn in it to `build_child_env`, and
   check_Q still reads it as text.
3. **A project check is trusted code.** It runs inside the gate's process, with
   the same trust as the project's Makefile. This is not a sandbox.
4. **Not every edit moves.** An add-only check cannot narrow what a template
   check scans or widen the taxonomy. project-jarvis's `.claude` exclusion is
   such an edit. Its `self` directory belongs in `structure.extra_toplevel`.
5. **The template's `structure` block stays put.** A project that adopts
   edits `structure.extra_toplevel`, so a later template edit to the lines
   around it (the block's `_comment`) conflicts in `config/project.json` for
   every such project. That was already true of every project that declared a
   directory there. The update then stops at `keep_edited_retired`, exit 2,
   naming the manifest, and `scripts/jobs/restamp_docs.py` run by hand names
   the manifest's hunk and `make restamp-docs`, exit 2, with no traceback.

## Alternatives considered

- **Entry points or a plugin registry.** Rejected. The gate is stdlib-only and
  3.6-safe, and runs before a project has a virtualenv. A directory and a
  manifest key need neither a package nor an install step.
- **A merge driver for `scripts/check_structure.py`.** Rejected for the reason
  keel slice project_keel:CMP-3.S2 measured: copier merges with `git apply --reject` and
  `git merge-file`, which never consult `.gitattributes`.
- **A waiver list beside the project checks.** Rejected. A key that turns a
  template check off makes the gate's verdict mean something different in
  every project. A disagreement belongs upstream.
- **Exclude `scripts/check_structure.py` from updates (`_skip_if_exists`).**
  Rejected. The project would then never receive a new template check, and
  later template changes that rely on the gate's helpers would break against
  the frozen copy.
