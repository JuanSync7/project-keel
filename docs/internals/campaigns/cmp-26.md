---
title: CMP-26 — changelog headings and commit subjects follow a declared grammar
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-26.
id: docs-internals-campaigns-cmp-26
created: 2026-11-18
updated: 2026-11-18
visibility: internal
canonical: true
---

## CMP-26 — changelog headings and commit subjects follow a declared grammar

KEEL-CHLOG-1 is queue row 46: an unknown `CHANGELOG.md` heading and a `wip` commit subject both pass, and no `commit-msg` hook exists.
The row waited on KEEL-FRAG-1, which changed how the changelog is written; CMP-11 delivered it.
The cap is three slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at CMP-26.S3 green or the cap.
Will not do in CMP-26: rewrite git history, judge a commit body beyond what the trailer gate already judges, judge what a changelog entry says, add release tags, or ship the changelog entry folders into generated projects.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-26.S1 | `scripts/check_structure.py` check_Q refuses, with file and line, a `CHANGELOG.md` heading outside the declared grammar: one depth-one title, depth-two `[Unreleased]` or `[x.y.z] — YYYY-MM-DD` releases, depth-three categories from one closed list, and nothing deeper; a missing changelog or one with no heading is refused, not passed. | implemented — delivered by 396c9302 (Codex), 260c9c03, 3615df9e and ccc299db: check_Q refuses an off-grammar `CHANGELOG.md` heading with file and line, owed only where the manifest declares `changelog` or the file exists; the first fast tier caught 19 failures in toy trees, fixed by that scope, and the Codex review caught a misstated check_Z precedent in four places, fixed as a class |
| CMP-26.S2 | One commit-subject matcher, `scripts/commit_subject.py`, judges a subject against a closed type list and a declared shape; `tests/integration/test_work_trailers.py` judges every non-merge subject after `commit_subject.adoption_boundary` with it, and the script judges one message file for a hook. | implemented — delivered by 2da28a33 (Codex) and 18207c36: `scripts/commit_subject.py` judges a subject against `commit_subject.types` and the declared shape; the history gate judges every non-merge subject after `commit_subject.adoption_boundary` and refuses a repository with no commit |
| CMP-26.S3 | `.pre-commit-config.yaml` runs the S2 matcher at the `commit-msg` stage and `pre-commit install` installs that hook type; a repository given the shipped hook refuses a bad subject through the installed hook, and a generated project refuses one through its own matcher and its history gate. | implemented — delivered by 6273333e (Codex) and 030478b6: the `commit-subject` hook runs at the `commit-msg` stage, `pre-commit install` installs it through `default_install_hook_types`, and the installed hook refuses `wip` in a plain and a linked worktree; the Sonnet review approved with notes only: a hand-edited subject during a merge is not judged, and the merge test relies on `GIT_MERGE_AUTOEDIT=no` |

CMP-26.S1 owns the heading grammar.
check_Q already reads `CHANGELOG.md` for its links, so the heading rule extends check_Q instead of taking a new check letter.
The category list is one list.
`config/project.json` `changelog_fragments.categories` names the keel-only entry folders; the heading vocabulary ships to generated projects too, so it lives in a key both manifests carry, and a test holds the folder names to it so the two cannot drift.
Five headings in keel's released history sit outside the grammar today (`### Known limitation`, `### Earlier in this release — …`, two `####` headings under it, and `## Template foundations (pre-0.1.0)`).
The slice rewrites each heading marker as a bold lead-in line and keeps every content line, so no excuse list is needed.

CMP-26.S2 owns the subject grammar.
A subject is `<type>(<scope>)!: <description>`, where the scope and `!` are optional, the type is one word from `commit_subject.types` and the description neither starts nor ends with a space.
The type list is the ten types keel's history uses: `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `chore`, `style`, `perf`, `release`.
A scope is letters, digits and `_./,-`; 22 of keel's 1069 subjects on 2026-11-18 use a comma or a capital in their scope, so a narrower scope would refuse them.
The matcher is its own module, not part of `scripts/check_structure.py`, because the hook runs it under the host's `python3` and because check_structure.py does not shell to git (ADR-K-0009); it stays stdlib-only and 3.6-safe.
The history gate lives beside the trailer gate and reuses its git reading and its boundary rule: commits reachable from the boundary are not judged, a boundary off the history fails closed, and null means every commit.
Keel pins its boundary at dc195258, which is newer than its two nonconforming subjects (the initial commit and one merge); a generated project ships null and its first commit subject is `chore: generate project`.

CMP-26.S3 owns the hook.
Installing the hook stays a manual step for the developer; no make target and no copier task installs a hook.
`default_install_hook_types` in `.pre-commit-config.yaml` names both hook types, so the existing `pre-commit install` line installs the subject hook and no install line changes.
A checkout that installed its hooks before this re-runs `pre-commit install` once.
`default_stages` keeps the existing hooks at the pre-commit stage, so they do not run a second time on the message.

### Decisions

- Row 48 (KEEL-ROADMAP-1) is not opened with CMP-26. Its status column changes every `features.d/` entry, and the layout of those entries waits on the open owner page "Reference fragment layout"; row 49 builds on row 48.
- The subject types are a closed list in config, not `[a-z]+`, because a closed vocabulary refuses a misspelt type that a pattern accepts.
- The type and scope validators in `scripts/config_loader.py` check shape only, so a project adds a type in config alone; a validator that restated the ten types would make the config list narrow-only.
- The hook does not judge a merge: a `MERGE_HEAD` file beside the message file marks one, which matches the history gate counting merges without judging them.
- The hook passes a subject that starts `fixup! `, `squash! ` or `amend! `, so `git commit --fixup` keeps working; the history gate still judges such a commit if it lands unsquashed.
- A `Revert "…"` subject is judged like any other; the developer edits it to a declared type.
- check_Q owes the heading rule only where `config/project.json` declares a `changelog` block or `CHANGELOG.md` exists, as check_Z is silent in a tree with neither a `work_naming` block nor a plan doc: both manifests declare the block, so a project that loses its changelog is still refused, and a test's toy tree with neither is not judged. A refused manifest adds no changelog error beside its own.
- The subject history gate refuses a repository with no commit yet, where the trailer gate skips: a pass over zero commits judges nothing, as the secret scan refuses an empty range, and the Quickstart commits the project before any gate runs.
