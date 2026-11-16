---
title: CMP-2 — the ranked queue
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-2.
id: docs-internals-campaigns-cmp-2
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-2 — the ranked queue

The maintainer accepted ADR-0010, ADR-0011 and ADR-0012 on 2026-10-06 and asked
for the Queued list above to be worked in risk order before bedrock-platform's
next round of feedback. The cap is five slices, each one commit on a green
`make verify`. v0.2.0 was tagged after CMP-2.S5, whose number-space move is the first
breaking change to the generated-project contract (ADR-K-0013). A concern found mid-slice joins Queued.

| Slice | Defect | Status |
|-------|--------|--------|
| CMP-2.S1 | A child inherits `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`, so its git acts on the parent's repository | done — `make verify` green (1206 passed); 3 review findings confirmed and fixed |
| CMP-2.S2 | A proxy URL with embedded credentials reaches every child | done — `make verify` green (1288 passed); 8 of 9 review findings confirmed and fixed |
| CMP-2.S3 | The audit reads the `Makefile` and `config/practices.json` before the merge, so an old project reports a false W error | done — `make verify` green (1308 passed); 4 review findings confirmed and fixed |
| CMP-2.S4 | A campaign, slice or pass has no fixed name, so a commit, a plan row and a ledger entry cannot name the same unit of work | done — `make verify` green (1436 passed); 7 review findings confirmed and fixed; replaced the `make smoke` slice, which moved to CMP-3 as CMP-3.S1 |
| CMP-2.S5 | A downstream project's ADR numbers collide with the template's | done — `make verify` green (1356 passed); 6 of 7 review findings confirmed and fixed; ADR-K-0013 accepted 2026-10-07 by the maintainer |

### Slice CMP-2.S1 — a child does not inherit the parent's repository

**Measured.** git 2.43.5 exports repository-location variables to a hook. A
`pre-commit` hook in a plain checkout receives `GIT_INDEX_FILE` and
`GIT_PREFIX`; with `git commit <paths>` the index is an absolute
`.git/next-index-<pid>.lock`. The same hook in a linked worktree also receives
an absolute `GIT_DIR`. Four reproductions followed, each before the fix:

- `review_docs --strict`, started in another repository under a hook's
  `GIT_DIR`, judged "0 governed document(s), 0 stale" and exited 0. Without
  the variable it reported 1 stale document and exited 1.
- A gate that `scripts/run_make_target.py` ran in another checkout printed the
  hook repository's `.git` from `git rev-parse --absolute-git-dir`, and the
  runner reported PASS.
- `tests/hermetic_git.py` `clone_including_worktree`, called under a parent
  `GIT_DIR` and `GIT_INDEX_FILE`, wrote into the parent's index. Afterwards
  `git status` failed with "unable to read" and `git fsck` reported an invalid
  sha1 pointer in the index's cache-tree.
- A generated project's own `review_docs --strict` under the same variables
  judged 0 documents and exited 0.

**The list.** `child_env.repo_context_names` is `git rev-parse
--local-env-vars` minus `GIT_CONFIG`, `GIT_CONFIG_COUNT` and
`GIT_CONFIG_PARAMETERS`, plus `GIT_NAMESPACE` and `GIT_QUARANTINE_PATH`. The
three config names are left out because they carry configuration, such as a
`git -c` value, not a repository. The two additions bind a ref namespace and
a receive-time object directory to one repository. The names live in config
so that a later git release that adds a name is a manifest edit. The test
`test_keels_policy_holds_back_every_repository_variable_git_names` compares
the list with the installed git's own list.

**Keyword, not config.** `build_child_env` drops the names unless the call
passes `repo_context=True`, and the keyword must be a real `bool`. A config
switch would apply to every child in the project. Acting on the parent's
repository is a property of one call site, so the call site declares it.
`child_env_policy`, and so check_X, refuses any allowlist source that admits
a listed name: `child_env.names`, a `child_env.prefixes` entry,
`make_targets.unattended_vars`, `make_targets.gate_vars` and
`models.credential_env`. A missing `repo_context_names` is an error. An older
project's `make check` names that key until it takes the update, and the same
message says to move git's repository variables out of `child_env.names` and
lists the `GIT_`-prefixed names it holds, so one round of `make check` carries
the whole fix. The `GIT_` prefix only picks the names to show; the set that is
held back is still `repo_context_names`.

**The audit.** This slice made `scripts/audit_project.py` merge a list of
distinct strings that both sides edited item by item, as copier's line-level
merge leaves an allowlist; CMP-2.S3 replaced that merge with copier's own
update, which the audit now runs and reads. Before this slice the list was
atomic. A project from before CMP-2.S1 that had
added its own `child_env.names` entry was then judged on its old list. The
audit reported an owed X error for `GIT_DIR` and predicted a copier conflict,
but the real `copier update` merged cleanly and `make check` was green.
`tests/integration/test_copier_audit.py` generates a project at `a70a7b5` and
checks that it owes no X error, with and without an added name.

**The suite.** `tests/hermetic_git.py` and copier run git without the helper.
For that reason `tests/conftest.py` strips the same names from `os.environ` at
import, before plumbum snapshots the environment, and `git_env` never carries
them.

**Residual risk.** The `GIT_CONFIG*` names still reach a child. copier's own
git, run through plumbum, and a make recipe that a hook starts directly do
not pass through `build_child_env`. Both are in Queued.

### Slice CMP-2.S2 — a credential in an allowlisted value does not reach a child

**Measured.** Before the fix, with `HTTPS_PROXY=http://u:<password>@127.0.0.1:9`
and `LC_X=https://tok@host` in the parent, `build_child_env` returned both
values verbatim, and a child running `echo $HTTPS_PROXY` printed the password.
`scripts/run_make_target.py` also quoted a refused gate variable with `%r`, so
a `PY` holding a password with a space in it was echoed in the refusal, and a
one-word one was put on make's command line before any check ran.

**The rule.** Whether a value carries user information depends on who reads
it, so `carries_credential(name, value)` in `scripts/child_env.py` applies
three readings, and a value any of them flags is a credential:

1. Every value: each URL authority in it, after `scheme://` or a leading `//`,
   up to the first `/`, `?` or `#` (RFC 3986 section 3.2). Whitespace does not
   end it, because `urllib.parse.urlsplit` keeps `u:p x@h` in the netloc. Any
   non-empty text before its last `@` counts, because a token rides there with
   no password.
2. Every value: a whole value that is a scheme-less `user[:password]@host:port`.
   The port separates it from ordinary values. A glibc `LANGUAGE` list
   (`sr_RS:sr@latin`), `USER`'s `name@domain` and `git@host:org/repo` never end
   in `@host:digits`.
3. A variable whose lower-cased name ends `_proxy`, which is how
   `urllib.request.getproxies_environment` picks the variables it reads as
   proxies: the user information urllib's `_parse_proxy` finds. That parser
   reads a scheme-less value as a whole authority, and a URL's authority up to
   the first `/` after its first `@`. So `#`, `?`, `/` or a space in a
   password, a scheme-less `token@proxy`, and even `http://h:8080/p?q=a@b`
   (user `h` on 3.11) all reach `Proxy-Authorization`. Each case was measured.

A scheme-less value outside a proxy name is not read as an address, so rule 3
is scoped to proxy names. The first cut judged every value as if it were a
proxy (`x:y@z`). That refused a Serbian-Latin or Valencian user's `LANGUAGE`
and stopped every child, while it passed `token@proxy:8080`, `//u:p@proxy` and
passwords containing `#`, `?`, `/` or a space. The independent review
reproduced all of these. The scan is linear: about 0.02 s on a 128 kB
adversarial value under 3.6.8. It anchors on the literal `://`, because a
pattern that matched the scheme took 0.40 s on a 20 kB value.

**Refuse, not strip or drop.** Stripping the user information would hand the
child a proxy that answers 407, and dropping the variable would send the child
around the proxy. Both fail later and far from the cause. `build_child_env`
raises one `ChildEnvError` that names every such variable, sorted, and never
quotes the value. The error carries no chained exception that could hold the
value.

**Config, not keyword.** CMP-2.S1's opt-in is a keyword because acting on the
parent's repository is one call site's decision. An authenticating proxy is a
property of the site, and every child crosses it, so the opt-in is
`config/project.json` `child_env.credentialed_values`: an optional object that
maps a copied variable to a non-empty reason. `child_env_policy`, and so
check_X, refuses an entry that is not a variable name, has no reason, or names
a variable no allowlist source copies (`drop the stale entry`).

**Exemptions.** A name in `credentialed_values` passes its value through. A
name in the called adapter's `models.credential_env` is not judged, because
that list already declares a credential for that child alone; it is not
exempt for any other call. A key the caller replaces through `extra=` is not
judged, because the parent's value never reaches the child.

**The runner.** `scripts/run_make_target.py` builds the child environment
before it forwards a gate variable. It judges every gate value, explicit or
forwarded, with `carries_credential`, and refuses one that carries a credential
even when `credentialed_values` opts it in, because make hands its command line
to every recipe through `MAKEFLAGS` and `ps` shows it. No refusal quotes a
value, so a credential in a form no rule recognises still never reaches a log.

**The audit.** `tests/integration/test_copier_audit.py` generates a project at
`29e45f0`, before this slice. The audit reports `child_env.credentialed_values`
as an `info` arrival with the template default `{}`, and the project owes no X
error.

**Residual risk.**
- A credential in another form is not detected: a bare token, an
  `Authorization` header value, or a `user:password@host` with no port outside
  a proxy name.
- `ssh://git@host` is refused although it carries a user name only.
- A proxy value with an `@` after its host (`http://h:8080/p?q=a@b`) is refused,
  although only urllib, not an RFC 3986 reader, would send it.
- The runner judges the environment against keel's own config, not the
  `--dir` project's.
- copier's git, and a make recipe a hook starts directly, still bypass the
  helper.
- A same-user child can still read `/proc/$PPID/environ`.

### Slice CMP-2.S3 — the audit judges the tree the update leaves

**Measured.** Before the fix, the audit merged the JSON configs in memory and
read every other file as it stood in DEST. On a project generated at `7f0a68b`
it reported 1 owed error and exit 1: config/project.json W, because the merged
`effect_proof_skip` names `audit-project` and the unmerged Makefile lacks that
target. A real `copier update` of the same project followed by
`check_structure.py` reports 0 errors. The old audit also marked 49 errors
resolved, because it marked every error in a template-unedited file resolved,
whether or not the update fixes it.

**The rule.** `scripts/audit_project.py` `predict` copies DEST into a
`keel-audit-*` temporary directory and runs copier's own update there, against a
clone of this checkout. It then runs `check_structure.run_checks` on the copy
twice: before the update and after it. A letter error in the after run is owed.
A letter error found only in the before run is `resolved_by` the update. A path
that `git ls-files -u` reports as unmerged in the copy goes to the `conflict`
group, and its findings carry `unjudged: conflict` and are not counted. The
after run then happens twice, with every conflict hunk the project's way and
the template's way (`resolve_conflict` reads copier's markers); a finding only
one of the two has is `unjudged: conflict` as well. The config group compares the
base render, DEST's JSON and the copy's JSON after the update (`classify`).
The audit merges nothing itself. After the fix, the same `7f0a68b` project
reports 0 owed, 12 resolved and 0 conflicts, with exit 0, in 30 s.
`test_predicted_findings_equal_check_structure_on_a_real_update` checks that
the predicted letter findings equal `check_structure.py` on a real update of an
independent clone. It covers projects from `7f0a68b`, `29e45f0`, and `a70a7b5`
both as rendered and with the project's own `child_env.names` entry.

**Decision: copier runs the project's restamp.** keel's copier.yml `_tasks`
and its last `_migrations` entry run `scripts/jobs/restamp_docs.py` from the
merged copy, so the audit runs code the project may have edited. The audit
accepts this. The parity test only means something with copier's real update,
and the project runs the same restamp on every update anyway. Containment is
the scratch copy with no DEST `.git`, `build_child_env`'s allowlisted
environment, a hermetic gitconfig with `core.hooksPath=/dev/null`, and a
check that no finding names the scratch root. The "not checked" list states
it.

**Decision: a conflict does not set the exit.** A conflict is reported and
counted in the text summary, but the exit code still means "a letter error is
owed", as before this slice. A failed `copier update` is exit 2 with copier's
last stderr lines and the scratch root masked as `<scratch>`. No partial report
is printed.

**Rehearsal on bedrock-platform.** A scratch clone at `_commit:
v0.1.0-14-g7f0a68b` audits as exit 2 in 28 s. The update conflicts on
`scripts/check_structure.py`, because the project added its own check W and the
template added a different one. copier's restamp task then imports the
conflicted module and stops on the conflict marker. A real `copier update` on
an independent clone fails the same way (exit 1, same task, in 25 s) and leaves
120 conflicted files, most of them `updated:` frontmatter lines. Two runs
printed byte-identical stderr. The clone's tree, `.git` and index mtime were
unchanged, and no `keel-audit-*` directory was left behind. CMP-1.S5's count of
17 owed errors cannot be compared, because the update itself does not complete.

**Review fixes.** An independent review reproduced two defects, both fixed
test-first.
- The first build restored a conflicted file to DEST's bytes and left every
  other file as the update leaves it, which is the per-file mix this slice
  removes. The `7f0a68b` project with its own target added to the Makefile's
  `.PHONY` line (a line the update also changes) owed the `audit-project`
  error again, exit 1: check_W reads the conflicted Makefile and reports
  against the cleanly merged manifest. With both resolutions the project
  reports 0 owed, 12 resolved and 1 conflicted file, with exit 0. The parity
  test gained that project (`7f0a68b-conflict`). It resolves the real update
  both ways with `git merge-file --ours` and `--theirs` over copier's index
  stages, not with the audit's marker reader, and holds the audit's judged
  findings equal to what both resolutions have outside the conflicted file.
- The scratch copy is committed whatever DEST's state, so a DEST with
  uncommitted changes previewed a clean update that the real `copier update`
  refuses ("Destination repository is dirty"). The config group now warns
  `update-refused` and names each uncommitted path, or says DEST is outside
  git. The exit code does not change.
- `run_checks(root, config_overrides)` lost its last caller with the in-memory
  merge, so the parameter is gone (`run_checks(root)`).

**Residual risk.**
- A finding that neither the all-project nor the all-template resolution of
  the conflicts raises, but a resolution mixing the two hunk by hunk would, is
  not seen; one that both raise but a mix would clear is owed. Only a tree with
  more than one conflict hunk can hit this.
- A finding whose message carries a line number that the update shifts, such
  as `Makefile:42:`, is reported once as resolved and once as owed. The owed
  count and the exit stay correct, but `resolved_by_update` can over-count.
- A failed update gives no partial report. On bedrock-platform the audit names
  the failing task, but not the 120 conflicts the user meets next.
- Files DEST's git ignores are not copied, so neither run judges them.
- A link that leaves DEST is copied as its target's bytes, or dropped when it
  is a directory or dangles. A submodule is not copied. Each is listed in "not
  checked".

### Slice CMP-2.S4 — campaigns and slices carry one checked name

**Measured.** Before this slice, this document named the same units of work in
four spellings: a bare number for the first campaign's slices ("Slice 1", 12
uses), `C2-n` for the second (26 uses), `C3-n` and `C4-n` in the draft of the
next two (17 uses), and "Campaign n" in prose (6 uses). keel's 67 commits carry
no trailer that names a slice. project-jarvis's 343 commits carry none either,
and jarvis already uses `C0` to `C8` for its risk classes, so a `C2-4` in a
jarvis ledger reads as a risk class.

**The rule.** CONVENTIONS §20. A campaign is `CMP-<n>` and a slice
`CMP-<n>.S<m>`; a pass is counted against its cap, not named. A plan doc (a
`kind: design` document with a `Slice` table) declares the ids, a commit that
delivers a slice ends with a `Slice:` trailer, and another repository's slice
is `<project>:CMP-<n>.S<m>`, with `<project>` from that repository's
`config/project.json` `name`.

**Decision: the grammar is config.** `config/project.json` `work_naming` holds
the plan kinds, the slice column, both id templates, the backlog pattern, both
trailer keys and the adoption boundary, and ships in `config/project.json.jinja`
unchanged. check_Z reads only the block, apart from two fallback constants
(`design`, `Slice`) used to find a plan doc when the block is missing; a test
holds them equal to the block.

**Decision: the git half is a test.** check_Z judges the plan docs, and
`tests/integration/test_work_trailers.py` judges the trailers, because
check_structure reads no git (ADR-K-0009). A trailer key in another case, a
second `Slice:`, a prefixed or undeclared id, a malformed `Backlog:`, and a
`Slice:` or `Backlog:` line above the trailer block whose value has the id's
shape are findings; a line such as `slice: split the parser` is prose. A
boundary that does not resolve, or is not an ancestor of `HEAD`, fails the
test rather than judging nothing. A history with no trailer is a stated skip
with its commit count.

**Decision: mentions are judged everywhere.** A bare id in the prose of any
Markdown file must name a declared one, so shipped documents write their
examples in code spans. A row's first cell and a code span are not mentions. A
token is read whole, so `CMP-1.S02` is malformed rather than a mention of
`CMP-1`.

**Built.**
- `scripts/check_structure.py` `check_Z`, with `work_naming_policy`,
  `id_grammar`, `parse_plan` and `plan_inventory`.
- `tests/unit/scripts/test_check_z.py` and
  `tests/integration/test_work_trailers.py`.
- The `work_naming` block in `config/project.json` and its twin, and the gate
  practice `work-naming` (row 40).
- CONVENTIONS §20, with a §6 row and a §15 bullet; the root `AGENT.md` rule;
  the naming section of `docs/guides/dev-loops.md`; the Z entry in
  `docs/guides/deterministic-checks.md`.
- This document renamed to the rule: CMP-1 for the five defects, CMP-2 for the
  queue, CMP-3 and CMP-4 for the drafted campaigns that follow.
- `tests/unit/scripts/test_audit_project.py` reads the check letters from
  check_structure's own `def check_<L>` lines instead of a hand-kept range.

**Downstream.**
- A project generated from this tree carries the block and no plan doc, and
  its gate is green with no Z finding. Its first plan doc reds the gate on a
  `| 2 |` row, naming the line, and is green with `CMP-1.S2`
  (`test_generated_project_judges_work_naming`).
- `make audit-project` on a project generated at `7f0a68b`: exit 0, 0 owed,
  0 Z findings, and `work_naming` listed as arriving with the update. The same
  audit from `HEAD` before this slice differs only by the Z row and that
  config entry. Two runs printed byte-identical JSON.
- The bedrock-platform rehearsal clone: exit 1 with 26 owed errors, the same
  26 as the audit from `HEAD` before this slice, and 0 Z findings. With the
  block added, its 166 commits are a stated skip with no trailer.
- project-jarvis, on a scratch clone at `1094ea3` with the block added: 0 Z
  findings, no plan doc, and no other letter's count changed. Its 343 commits
  are a stated skip.

**Adopting in project-jarvis.** jarvis adds the `work_naming` block to its
`config/project.json` and sets `adoption_boundary` to its last commit before
adoption, so its earlier history is not judged. Its ledger then ingests the
`Slice:` trailer of each commit as the slice the commit delivers, and names a
keel slice as `project_keel:CMP-2.S4` (or this repository's own `name`, if it
differs).

**Residual risk.**
- A slice id reused across several commits breaks the one-commit rule of
  CONVENTIONS §20 but is not detected.
- A foreign-prefixed id is not resolved, because the other plan is not in this
  tree.
- A requirement id is not named by the rule; requirements and slices are many
  to many.

### Slice CMP-2.S5 — template and project ADRs live in separate number spaces

**Measured.** bedrock-platform holds keel's ADR 0001-0009 and its own 0010;
keel's 0010-0012 would land beside it. project-jarvis holds keel's 0001-0004
and its own 0005-0011, so keel's 0005-0011 are seven different decisions under
the same seven numbers. project-jarvis also edited keel's 0001-0004: each
carries `owner: Juan.Kok` where keel ships `owner: TBD`. copier 9.17's
`_remove_old_files` deletes every file the old render had and the new render
lacks, edited or not, before any migration runs, so moving keel's ADRs would
have dropped those edits without a word.

**The rule.** keel's ADRs move to `docs/adr/keel/K-NNNN-<slug>.md` and are
cited as `ADR-K-NNNN`; `docs/adr/` is the project's own space, numbered from
0001 (CONVENTIONS §19, ADR-K-0013). `config/project.json` `adr`
names both spaces and the template's own ADR file names (`template_adrs`),
and check_Y holds every ADR to its space: a template-space file the list does
not name, and a `kind: adr` document outside both directories, are errors, so
a project's decision cannot take a free `K-` number either. Each moved ADR
keeps its `id:`. `scripts/jobs/keep_edited_retired.py`, the first `after`
migration, puts back a file the update deleted when the project edited it
(any byte but the `updated:` value) and names it with its successor. The
audit's new `retired` group names each edited file the update still deletes.
The next release is 0.2.0, because a generated project's contract breaks.

**Correction during the slice.** The first draft said copier runs no
migration for a `_commit` with no tag ancestry, and so that project-jarvis
would get no guard. A spy on `_remove_old_files` during a real update of a
project-jarvis clone disproved it: copier versions `72fd224` through dunamai
as `0.0.0.post17.dev0+72fd224`, runs every migration, and the guard printed
`kept docs/adr/0001-record-architecture-decisions.md: ... (now
docs/adr/keel/K-0001-record-architecture-decisions.md)` for each of 0001-0004
and for `scripts/README_check_structure.md`. ADR-K-0013, CONVENTIONS §19, the
READMEs, `docs/adr/README.md`, `copier.yml` and the CHANGELOG were reworded to
the measurement.

**Rehearsal.** The audit from this tree, against the rehearsal clones:
- project-jarvis (`_commit: 72fd224`): owed errors 92 before the slice, 99
  after. The new ones are 4 check_A duplicate ids (each kept 0001-0004 shares
  its `id:` with the K- file, as designed), 1 Q, 1 Y (its own `0010` title
  begins `A neutral job-placement seam` rather than `ADR-0010:`) and 1
  `retired`: the named `rm` migration for keel's meta-tests deletes the
  project's edited `tests/integration/test_copier_generation.py`. A second Y
  finding, the missing `adr` block, is resolved by the update. Conflicts stay
  at 110.
- bedrock-platform (`_commit: v0.1.0-14-g7f0a68b`): owed errors 15 before and
  after. Its keel ADRs are unedited, so the update deletes them and nothing is
  kept; the `adr` block's Y finding is resolved by the update. Conflicts fall
  from 119 to 110.

**Residual risk.**
- An `rm` migration runs after the guard and still deletes the path it names.
  The `retired` group reports it before the update; nothing stops it.
- A file the template renders from a `.jinja` source is put back and named,
  not judged: comparing it needs the old answers and a render.
- The guard imports `review_docs` and `child_env` from the project, and
  `build_child_env` reads `config/project.json`. When the update leaves one of
  them conflicted, the guard exits 2 before it can list what was deleted, the
  update fails at that migration, and a deleted file comes back only through
  `git checkout HEAD -- <path>`.
- The restamp `_task` moves `updated:` in every ADR the update touched, so a
  kept ADR shows as modified twice.
- A bare `ADR-NNNN` mention is not checked against the space it names. This
  slice re-pointed the keel mentions in shipped files (scripts, tests, the
  guides, CONVENTIONS) by hand; a review found 21 in the shipped tests that
  the first pass missed. The excluded plan documents keep the old numbers as
  history.
- `adr.template_adrs` is a file a project can edit. check_Y makes adding a
  project ADR to the template space a deliberate edit of that list, not an
  accident; it does not stop a project that edits the list on purpose.
- `audit_project.origin_of` does not discount the `updated:` value the way
  `is_edited` does, so a copy differing only in its stamp reads as
  template-edited there.

The vault backlog for keel (`KEEL-*` items: the frontend contract chain FE-2,
FE-1, FE-6, FE-3; TEST-1 live-store guard; SEC-1 secrets scan) is queued in
CMP-4 below, not worked here.

