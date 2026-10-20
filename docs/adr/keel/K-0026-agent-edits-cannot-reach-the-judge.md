---
title: "ADR-K-0026: an agent edit cannot reach the code that judges it"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, agents, refactor, safety, gate, policy]
summary: "scripts/apply_refactor.py refuses, before any write, an agent edit to a path config/project.json agents protects (agents.protected_paths, agents.protected_names, with agents.editable_names carving a name back out; a name may be a glob), judged case-folded on the path and on its realpath, and an edit to any file git does not track; the block must protect config/project.json itself, and which READMEs are rosters is config/project.json rosters.readmes, not a heading an edit could drop. Each agent run binds its edit to the chunk's own file with --allow. The gate is the caller's --gate, default verify, and a spec that names a gate is refused. It does not reach an interactive agent's direct edit, which needs hooks or permission rules."
id: docs-adr-0026-agent-edits-cannot-reach-the-judge
created: 2026-10-19
updated: 2026-10-20
visibility: internal
canonical: true
---

# ADR-K-0026: an agent edit cannot reach the code that judges it

**Status:** proposed. It edits no other ADR. It is numbered K-0026, not
K-0025, because a sibling change may take K-0025; whichever merges second
renumbers. It takes the stance of
[ADR-K-0012](K-0012-child-process-environment-allowlist.md), which is
accepted: a rule enforced inside the process is defence-in-depth, not a
sandbox, and says so. It reads its block through the one loader of
[ADR-K-0022](K-0022-one-config-loader.md).

## Context

Two rules say what an agent may edit: an agent may not edit the code that
judges its work (R-AGT-7), and an agent proposes a change to approved text to
its owner rather than making it (R-AGT-33). Nothing enforced either.

- `scripts/apply_refactor.py` `plan_edits` refused only a path that escaped
  `--root`. A spec that `agents/practice_refactor/` or `agents/doc_reviewer/`
  drafted could rewrite a check under `scripts/`, a test, the `Makefile` or
  config/project.json, and the gate that then ran was the one the edit had
  just changed.
- The gate could be the spec's. `apply_and_gate` took the spec's `gate`
  whenever its caller gave none, and the tool card documented `--gate` as
  defaulting to the spec's, so a model-written spec with `"gate": "none"`,
  run as the card showed, applied its edit with no gate at all. Both agents'
  brains also copied a reply's `gate` into the spec with
  `setdefault("gate", ...)`; their own non-empty `--gate` won, so that path
  was latent, not open.
- An edit was not bound to the chunk the model was shown, so a reply about
  one file could edit another.

## Decision

1. **A deny floor in the root's own config.** config/project.json `agents`
   holds three maps, each from a key to a non-blank reason:
   - `agents.protected_paths`: a repo-relative path that covers itself and
     everything under it;
   - `agents.protected_names`: a file name, or a glob over one such as
     `*.test.*`, covered in any directory;
   - `agents.editable_names`: a file name or glob carved back out of a
     protected directory (`README.md`); it may be empty, the setting with no
     carve-out.

   A protected name refuses first, else an editable name allows, else a
   protected path refuses. Parts are compared case-folded, and an edit is
   judged on the path as written and again on its realpath, so neither a case
   variant nor a symlink launders a judge file. A `..` part, an absolute path
   and a file with more than one hard link are refused outright. The floor
   protects itself: `agents.protected_paths` must cover config/project.json,
   or the block is a config fault (exit 14). No flag lifts an entry; only a
   human edit removes one. The shipped list covers the judges the default
   project ships, the frontend ones included: `*.test.*` and `*.spec.*`
   (the Vitest unit test and the Playwright e2e specs), `tsconfig*.json`,
   `package-lock.json`, `conftest.py`, `.gitignore`, `.gitattributes`, `.git`,
   `api/rest_fastapi/export_openapi.py` (the `make check-openapi` checker) and
   the `.jinja` twin of each protected file.
2. **Beneath the list, only tracked files.** An edit to a file git does not
   track is refused whatever the list says (`scripts/git_tree.py` `tracked`),
   and so is an edit in a root where git cannot say. What git does not track
   is judge-shaped by default: git's own state (`.git/config` can set
   `core.fsmonitor`, which runs inside the gate's own `git status`), the
   toolchain the gate runs (`.venv`, `node_modules`) and every ignored file.
   An agent refactors tracked source, so the rule costs it nothing. Edits are
   planned by the resolved path, so `src/m.py` and `./src/m.py` are one file.
3. **A README carve-out switches no gate.** check_S holds a README to its
   directory when config/project.json `rosters.readmes` lists it, not when the
   README carries `## What ships here`: a listed README without the heading,
   and a headed README the list does not name, are errors. An agent may fix a
   roster row but cannot turn the roster check off.
4. **Each run binds its edit.** `--allow FILE` (repeatable) names the files a
   run may edit, and each agent passes its chunk's own path, so an edit to any
   other file is refused even where no entry protects it.
5. **The gate is the caller's.** `--gate` defaults to `verify`. A spec is a
   closed vocabulary (`practice`, `edits`; an edit's `file`, `find`,
   `replace`, `content`): an unknown key is refused, and a `gate` key is
   refused by name rather than dropped, so an old caller learns its gate was
   never used. `--gate none` is a human caller's flag; no agent passes it.

All of it is checked in `plan_edits`, before any write, so a dry run is
refused too.

## Consequences

- `agents/doc_reviewer/` declines a finding in CONVENTIONS.md, an AGENT.md, an
  ADR or a tool card: it is a protected file, so the edit is refused and the
  chunk is skipped. A `README.md` under a protected directory stays fixable.
- A protected chunk still costs one model call: `agents/` cannot import
  `scripts/apply_refactor.py` under config/project.json `import_layers.order`,
  so the brain cannot filter the chunk before it asks the model.
- The brains keep `apply_refactor`'s exit and drop its refusal text, so a
  refused chunk shows only as skipped. Recording the reason needs a rejection
  ledger, which is not built.
- A tracked judge a project adds under a name the list does not cover (the
  directory `structure.project_checks` names, the `make_targets.area_dir`
  makefiles) is protected only once the project lists it. The frontend tests
  and configs the default project ships are listed.
- An agent cannot create a file: a new file is untracked until a person adds
  it with `git add`.
- A project that adds its own roster README lists it in `rosters.readmes`,
  or check_S errors on it; a project from before the `rosters` block errors
  on every roster README until `copier update` brings the block.
- `scripts/git_tree.py` does not pass `-c core.fsmonitor=false` to its own
  git calls; the tracked rule keeps an agent edit off `.git/config`, and a
  human edit there is outside this decision.
- An interactive agent's own Edit or Write tool, outside
  `scripts/apply_refactor.py`, is not refused.

## Alternatives considered

- **A per-agent allow list.** Rejected: `agents/doc_reviewer/` fixes any
  Markdown file, so its list would be every `.md`, protected ones included;
  a deny floor names the few judges once for every agent.
- **Hooks or permission rules on the agent host.** Deferred: they would also
  cover an interactive agent's direct edit, but they are tied to one agent
  host's configuration, and the doer is the one path both shipped agents
  already write through.
- **A hand-written regular expression over the path.** Rejected: it would
  miss a case variant, a symlink or a `..` part that the part-wise,
  realpath-judged rule refuses, and its intent would not be readable as data.

## Scope cuts

Not built:
- hooks or permission rules for an interactive agent's direct edit;
- a rejection ledger that records why a chunk was refused;
- a pre-filter that drops a protected chunk before the model call.
