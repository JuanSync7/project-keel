---
title: CMP-7 — a document answers for the features it serves
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-7.
id: docs-internals-campaigns-cmp-7
created: 2026-10-22
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-7 — a document answers for the features it serves

The maintainer approved this campaign on 2026-10-22. It is KEEL-DOC-1, the first campaign-sized item in the queue. The cap is five slices, the read-only opening pass included. If "Open decisions for CMP-7" item 9 is taken as recommended, four slices are built, CMP-7.S1 to CMP-7.S4, each one commit on a green `make verify`. CMP-7.S1 is the defence record, because every later documentation check reads it. The opening pass ran on 2026-10-23 as a design pass with no code. It checked each candidate in "KEEL-DOC-1, the candidate slices" against the tree at `dc0ad1f` and against the vault's documentation-system study, and wrote rows CMP-7.S2 to CMP-7.S4, which stay proposed until the maintainer approves them. The stop point is CMP-7.S4 green or the cap, whichever comes first. It starts after queue positions 1 to 9.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-7.S1 | KEEL-DOC-1: a design or spec document can describe itself without meeting its features; nothing records which questions it answers and which it leaves open (DT-1 to DT-7 below) | planned |
| CMP-7.S2 | KEEL-DOC-1: a document's kind is not bound to the folders it may sit in, and its status is checked against one list every kind shares: check_A reads the flat `KINDS` and `STATUSES` sets in `scripts/check_structure.py`, so a `kind: spec` file under `docs/guides/` passes while `make trace` never reads it (`read_specs` reads only `traceability.specs_root`), and an ADR marked `stable` passes; only an ADR's folder is bound, by check_Y | proposed |
| CMP-7.S3 | KEEL-DOC-1: the headings of a root README, a new ADR and a folder README that holds a kind are read by no check. check_F reads a tool spec's, and check_S reads `## What ships here` in the 10 READMEs `config/project.json` `rosters.readmes` lists and refuses it in any other; 3 of keel's 27 template ADRs have no `## Alternatives considered`, and of the folder READMEs only `docs/specs/README.md` shows the skeleton of the document it holds | proposed |
| CMP-7.S4 | KEEL-DOC-1: the freshness judge reads a git that ran and failed as no git, so a corrupt `.git` skips the gate rather than stopping it: `scripts/jobs/review_docs.py` `_git` returns None for any failed call, and does not use `scripts/git_tree.py`, whose `GitFailedError` ADR-K-0019 made the other gates refuse on; and `test-docs/coverage/register.md` is a hand copy of what `make trace` derives, which no test holds to the matrix | proposed |

### What each CMP-7 slice builds

Each slice is one capability through every layer it needs: the registry or
rule, the check, keel's own tree fixed in the same commit, the template twin
and the generated project, and the docs that name the check. Each new
project-facing check is a pytest gate test under `tests/integration/` that
prints the finding grammar, `<file>:<line>: <rule> — <fix>`, and hands its
findings to `scripts/expiring_tier.py` `apply` under one `CHECKS` row in
`scripts/expiring_tier_data.py` (rulings 3, 6, 9 and 10). In the template every
finding is red, so each check lands as an error in the change that makes keel's
tree pass it; in a generated project a recorded finding warns until
`expiring_tier.expires`. ADR-K-0027 is unchanged: check_structure findings stay
outside the tier, so a slice adds no new check letter (the letters A to Z are
taken) and moves no existing check_structure error into the tier.

Each done-condition below includes a hand mutation of the check
(R-CODE-34): each comparison the check makes is broken in turn,
the suite must go red for each, and the slice reports which mutations it ran.

The slices touch shared files, so their order is fixed:

- Branches not yet merged to `main` edit files these slices edit, measured
  with `git diff --name-only main...<branch>` when this plan was written:
  keel-lint (KEEL-LINT-1: `scripts/check_structure.py`, `scripts/git_tree.py`
  and `scripts/jobs/review_docs.py`), keel-doc2 (KEEL-DOC-2), keel-vis and
  keel-vis2 (KEEL-VIS-1 and KEEL-VIS-2), keel-shell2 (KEEL-SHELL-1), and
  keel-dist, keel-risk and keel-risk2 (`config/project.json` and its twin,
  `docs/guides/deterministic-checks.md`); keel-exit, keel-goals and
  keel-xdist edit `config/project.json` and its twin as well. CMP-7.S1 to
  CMP-7.S4 start after those have merged, and each slice repeats the
  measurement before it starts. keel-lint-pre-rebase is a backup of
  keel-lint and edits the same files; it never merges, and no slice waits
  for it. Every unmerged branch except keel-lint and its backup edits
  `docs/internals/downstream-feedback.md`. Every other unmerged branch except
  keel-vis edits `scripts/config_loader.py`. keel-exit, keel-goals and
  keel-xdist also edit `docs/internals/make-next-steps.md`.
- CMP-7.S1, CMP-7.S2 and CMP-7.S3 each edit `scripts/check_structure.py` (the
  reader, the kind sets, the README rules). They run in series, S1 then S2
  then S3.
- CMP-7.S4 edits `scripts/git_tree.py` and `scripts/jobs/review_docs.py`,
  which no other CMP-7 slice touches, and `test-docs/README.md`, which
  CMP-7.S3 can edit when it renders a folder README's skeleton. S4 may be
  built beside S1 and S2, and is not built beside S3.

**CMP-7.S1, the defence record.** DT-1 to DT-7 under "KEEL-DOC-1, the defence
table" are its requirements. Its gate test is a new file,
`tests/integration/test_defence_record_gate.py`, under the `CHECKS` id
`defence-record`. It writes the record for keel's four `kind: design`
documents and for the example spec the template ships. The record's heading
is `Defence record` (if "Open decisions for CMP-7" items 3 and 4 are taken as
recommended): `## Defence record` in a document with one subject, such as a
spec, and `### Defence record` under each campaign's `##` heading in a plan
that holds several. The reader reads the heading level its targets use.
`_sections` in `scripts/check_structure.py` reads only `## ` headings today,
so S1 either gives it the level as a parameter or adds a sibling reader
beside it in the same module, and names the one it chose (item 5).

- Done when: the gate test is red on one fixture per rule DT-2 to DT-6 and
  green on one that keeps them all; a hand mutation of each rule's comparison
  turns the suite red; `docs/internals/downstream-feedback.md`,
  `docs/internals/keel-hardening-plan.md`, `docs/internals/documentation-quality.md`,
  `docs/internals/make-next-steps.md` and `docs/specs/example-feature.md` pass;
  a case in the gate test, under `scripts/expiring_tier.py` `judge`, shows
  that a generated project's own design document with no record is red while
  the baseline file `expiring_tier.baseline` names does not record it, and
  warns once it does; a generated project passes its own `make verify`;
  `docs/guides/doc-style.md`, `docs/specs/README.md` and
  `docs/guides/deterministic-checks.md` state the rule and name the gate
  test; the "Open
  decisions for CMP-7" this slice owns are ruled.
- Reads a table by the GFM rule: `\|` escapes a pipe, and a fixture holds a
  cell with one. `_pipe_table` in `scripts/check_structure.py` splits on every
  pipe today.
- `docs/internals/make-next-steps.md` already has a
  `## Defence: the hard questions per effect class` section; S1 turns it into
  the record, so the plan carries one defence section, not two.
- Not for: judging whether a question is a good one or an answer holds (DT-7;
  `make doc-review` asks that). Not the design document's other headings;
  CMP-7.S3 holds those.
- Depends on: KEEL-FRAG-1 (queue position 4), which may split this plan into
  files, so the record is written once against the files it leaves; and the
  open branches named above.

**CMP-7.S2, kinds bound to homes and status lists.** One registry row per
kind gives its allowed folders and its own status list, in a stdlib-only
`*_data.py` module that check_A and the gate test both import. check_A keeps
its membership errors and reads the kind and status names from the registry,
so the flat `KINDS` and `STATUSES` sets are removed and the kind list has one
home. The binding of a kind to its folders and to its own status list is new,
so it is a new gate test, `tests/integration/test_document_kinds_gate.py`,
under the `CHECKS` id `document-kind-home`. check_Y keeps the ADR folder rule.
A project may add a kind of its own, or a home for a kind of its own, through
`config/project.json`, the way `structure.extra_toplevel` adds a top-level
directory. It may not rebind a kind keel ships: an entry that names a kind in
keel's registry, to give it another folder or another status list, is red. This is the study's
slice 2 (its PLC-01 and the membership half of PLC-02) and the inventory's
gap 1.

- Done when: a fixture with `kind: spec` under `docs/guides/` and one with an
  ADR marked `stable` are each red, naming the file, the kind and the allowed
  list; every governed document in keel's tree and in a generated project
  passes; a kind with no registry row is red, never a pass; a fixture
  `config/project.json` that adds a kind with its home is green, and one that
  gives `spec` a second folder is red, naming the kind as keel's; a hand
  mutation of the folder comparison, of the status comparison and of the
  rebind comparison each turns the suite red;
  CONVENTIONS §1 and `docs/guides/deterministic-checks.md` name the registry
  and the gate test.
- Not for: a status transition, which needs the previous version from git
  (PLC-02's other half, queued as KEEL-STATUS-1); new kinds such as `plan` or
  `research` ("Will not do in CMP-7"); the `genre` facet (queued as
  KEEL-GENRE-1).
- Depends on: CMP-7.S1, because the registry row for `design` and `spec`
  records that the kind carries a defence record.

**CMP-7.S3, heading contracts per kind.** A kind's registry row names the
headings a document of that kind must have, in order. Its gate test is a new
file, `tests/integration/test_heading_contract_gate.py`, under the `CHECKS` id
`heading-contract`. check_S stays the one check of `## What ships here`: a
README `rosters.readmes` lists must have it and no other README may, and S3
neither requires nor forbids that heading anywhere, so the two never disagree
on a README the list leaves out. What S3 adds beyond check_S is three
contracts: the root README's headings; a new ADR's headings, `## Alternatives
considered` among them; and, for a folder README that holds a kind (such as
`docs/specs/README.md`, `docs/adr/README.md` and `docs/design/README.md`), a
skeleton of that kind rendered from the same row inside a fenced block, which
a drift test holds equal to the row, so the shape a writer copies is the shape
the check demands. A design document's defence record heading is S1's, and S3
does not judge it a second time. This is the study's slice 4 without the
five-W header and the module header fields, and the inventory's gap 5.

The ADR contract is judged per number space (CONVENTIONS §19). An accepted
ADR is immutable (`docs/adr/README.md`, ADR-K-0001). So in keel's template
space, `adr.template_dir` with the `K-` prefix, an ADR numbered below a
cut-off is not judged. Keel's three ADRs that lack the heading (K-0001,
K-0003 and K-0004) are exempt by number. The cut-off is K-0005, the first
`K-` number after the last ADR that lacks the heading. It is not the next
free number. Judging K-0002 and K-0005 to K-0027 costs nothing today,
because an accepted ADR never changes, and it holds them to the contract.
The cut-off is a new key,
`adr.template_contract_from` (5), which sits beside `adr.template_prefix` in
both `config/project.json` and its `config/project.json.jinja` twin, so it
renders into every generated project; it is read through
`scripts/config_loader.py` with a `KEYS` row, and only for the `K-` space.
It is not a cut-off a project uses for its own ADRs: no key names one for the
project's `NNNN` space in `adr.project_dir`, which is judged from 0001.

- Done when: a fixture root README missing a contract heading is red; a new
  `K-` ADR fixture, numbered at the cut-off, with no
  `## Alternatives considered` is red, and a `K-` fixture numbered below it is
  not judged; K-0002 and K-0005 to K-0027 pass; a project-space fixture
  `0001-…` with no `## Alternatives considered` is red whatever
  `adr.template_contract_from` holds; every rendered skeleton equals its
  kind's row; a hand mutation of the
  heading comparison, of the cut-off comparison and of the space test each
  turns the suite red; keel's tree and a generated project pass;
  CONVENTIONS §2, `docs/guides/doc-style.md` and
  `docs/guides/deterministic-checks.md` name the gate test.
- Not for: `## What ships here`, which is check_S's; the order or wording
  inside a section; the five-W header and the module header fields ("Open
  decisions for CMP-7", items 6 and 7).
- Depends on: CMP-7.S2, whose registry carries the contract rows, and
  CMP-7.S1, whose reader it uses.

**CMP-7.S4, freshness fails closed on a broken git, and the hand register
goes.** The freshness gate already reads the gate-run date through
`scripts/jobs/review_docs.py` `resolve_today`, so the study's slice 5 shrinks
to its other two parts. No git, or not a repository, stays a stated skip:
ADR-K-0019 is accepted and immutable, `docs/guides/generate-and-upgrade.md`
promises that "a project with no repository, or a host with no git, runs as
before", and `tests/integration/test_doc_freshness.py` says the same. S4
extends ADR-K-0019 decision 7 to the freshness judge. It adds one public
read-only git runner to `scripts/git_tree.py`, exported through `__all__`,
which keeps the read-only prefix `scripts/jobs/review_docs.py` `git_argv`
builds today: `GIT_READ_ONLY`, then, for every filter driver the config names,
an empty `filter.<name>.clean`, `filter.<name>.smudge` and
`filter.<name>.process` and `filter.<name>.required=false`. That prefix moves
into `scripts/git_tree.py`, so it has one home; `review_docs.git_argv`
becomes a thin wrapper over it, which `scripts/audit_project.py` and the
other callers keep calling. The runner raises `GitFailedError` on a git that
ran and failed (a corrupt `.git`, a repository git refuses as unsafe), so the
gate stops with git's status quoted rather than skipping. Exit 128 is git's
generic failure and is never an answer. Two non-zero exits are expected, and
each is named at its call (measured). `rev-parse --verify -q HEAD^{commit}`,
as `git_tree.head_commit` runs it, exits 1 with an unborn HEAD. The runner
answers that exit by reusing `git_tree.head_commit`, which returns None, rather
than by a second rule. `config --get-regexp` with no key matched exits 1.
`log -1 --format=%cs -- <file>` over a file never committed, in a repository
with a commit, exits 0 with empty output. That empty output is the answer
"no commit". On main the judge runs `log -1` for every file even with an
unborn HEAD, and reads the 128 as None. S4 makes the judge ask
`git_tree.head_commit` before `ls-files`, and run no `log` when it returns
None. `log -1` with an unborn HEAD exits 128, the same as a corrupt repository.
A corrupt `.git` nested inside another repository does not fail (measured).
Git skips the unreadable `.git` and answers from the parent.
`rev-parse --show-toplevel` then names the parent with exit 0.
S4 makes the judge compare `rev-parse --show-toplevel` with the directory
whose `.git` entry `git_tree.inside_a_repository`'s walk finds first.
On a mismatch the judge raises `GitFailedError` with a message that names
both directories; git's exit 0 is not quoted as a failure status.
The judge's call order is `head_commit`, then the top-level comparison, then
`ls-files`.
S4 makes that walk return the directory it found.
`inside_a_repository` keeps its true-or-false answer over it. A project
generated as a subproject ("Open decisions for CMP-7", item 8) is the layout
that reaches this case.
`scripts/jobs/review_docs.py` calls the runner in place of its own `_git`.
`test-docs/coverage/register.md` is deleted. With `coverage/` empty,
`test-docs/README.md` stops naming a coverage register: its frontmatter
`summary:` (line 9) and its opening line (line 19), which both say "coverage
register", and the `coverage/` bullet, which calls it "a living register",
point at `make trace` and `.evidence/traceability/matrix.json` instead;
`test-docs/coverage/` has no README of its own. A gate test fails a hand
register beside the generated matrix (the study's TST-16).

- Done when: in a scratch copy with `.git` removed, the freshness test skips
  with its stated reason; in a scratch copy whose `.git/HEAD` is overwritten
  with bytes git cannot read, the freshness test fails and quotes git's
  status; a case for each expected answer (an unborn HEAD, a `config
  --get-regexp` that matches nothing, a `log -1` over a never-committed file
  in a repository with a commit, which exits 0 with empty output) returns it
  and does not raise; a case with an unborn HEAD and staged documents passes
  and runs no `log`; the corrupt-`.git` case stops the gate on the first
  git call, `head_commit`'s `rev-parse`, which exits 128; a fault-injected
  runner returns
  128 for `log` alone while `rev-parse`, `ls-files` and `status` answer, the
  gate stops on it, and a hand mutation whose runner accepts exit 128 from
  `log` turns that case red; in a scratch repository holding a nested
  directory whose `.git` is corrupt, with `GIT_CEILING_DIRECTORIES` set to
  the scratch repository's parent so the verdict does not depend on where
  pytest's scratch lives, the judge run over the nested directory stops on
  the top-level mismatch, and a hand mutation that drops the comparison turns
  that case red; a case runs the judge over a
  repository whose config names a filter driver that would write a marker
  file, and shows no marker is written, no `.git/index.lock` appears and
  `.git/index` is unchanged; every case runs under `tests/hermetic_git.py`
  `git_env`, so the home's git config cannot change the verdict; a hand
  mutation that reads a `GitFailedError` as no git, and one that drops the
  read-only prefix, each turns the suite red; a restored `register.md` is
  red; a generated project passes its first `make verify`;
  `docs/guides/deterministic-checks.md`'s Doc review row says a failed git
  stops the gate.
- Not for: a stale `updated:` stamp, which the gate already fails; a project
  with no repository, which stays a skip; the `write-test-coverage` skill
  that writes a hand register, which lives outside keel.
- Depends on: no CMP-7 slice; the open branches named above; and is not
  built beside CMP-7.S3.

### How the candidates were reconciled

The opening pass read each candidate in "KEEL-DOC-1, the candidate slices"
against the tree at `dc0ad1f` and against the study. Each row ends in a slice,
a queue row after CMP-7, another item, or a cut. Every "queued" outcome is a
row of the proposed table under "Queued after Campaign 6", with its own id, a
proposed position the maintainer has not approved, and the state `planned`.

| Candidate | What the tree shows | Outcome |
|-----------|---------------------|---------|
| The defence table | No design or spec document has one under that name; `docs/internals/make-next-steps.md` has a defence section of its own; `scripts/traceability.py` `read_specs` exists as DT-3 says | CMP-7.S1 |
| Kind-to-folder binding | check_A reads one flat `KINDS` set and one flat `STATUSES` set; no key binds a kind to a folder | CMP-7.S2 |
| Kinds and status lists | as above; a transition check needs git, which check_A does not run (ADR-K-0009) | CMP-7.S2 for membership; transitions queued as KEEL-STATUS-1 |
| Heading contracts | check_F reads a tool spec's body and check_S a roster README's `## What ships here`; nothing reads another kind's headings; 3 of 27 template ADRs lack `## Alternatives considered` | CMP-7.S3, beside check_S and without the five-W header |
| Placeholders per kind | only `docs/specs/README.md` shows a skeleton, inside a fenced block | CMP-7.S3, rendered from the contract row |
| Freshness that fails closed | the gate already reads the gate-run date; it calls `pytest.skip` with no git, which ADR-K-0019 keeps, and also when git ran and failed, which it does not | CMP-7.S4, for a git that ran and failed only |
| The coverage register | `test-docs/coverage/register.md` is `status: template`, and no test or script reads it | CMP-7.S4 |
| Check ids and registry | `config/practices.json` holds 44 practices with `enforced_by`, and check_T refuses an unknown mechanism; no check id namespace and no fault-injection twin field exist | queued as KEEL-CHECKID-1, after CMP-7, at the position the maintainer picks |
| A genre for `kind: doc` | 26 tracked `kind: doc` files ending `.md`, 27 with the `.jinja` twin of `docs/guides/README.md`; the study calls the same facet `form`, under guides only | queued as KEEL-GENRE-1; the facet's name is open |
| Changelog heading and commit message | `CHANGELOG.md` has `### Known limitation` and `### Earlier in this release`; no `commit-msg` hook | queued as KEEL-CHLOG-1, after KEEL-FRAG-1, which changes how the changelog is written |
| House vocabulary | `change_comments.phrases` reads code comments only | queued as KEEL-VOCAB-1; overlaps KEEL-DOC-2 (lane L8) |
| Roadmap fields in the features catalogue | `docs/reference/features.md` has no status column; every row is a shipped feature | queued as KEEL-ROADMAP-1 |
| Docstring grammar | ruff `D` and pydoclint are not selected in `pyproject.toml` | moved to KEEL-LINT-1, which owns the rules a tool decides |

The candidate list says the study's slices 9 to 18 are not keel's. Three of
them are: slice 13 (the coverage report schema, keel with pyverdex), slice 15
(the eval run record with its spend basis) and slice 16 (the `docs/internal/`
cabinet and the document index, decision 2 of the study). They are queued
after CMP-7 as KEEL-COVSCHEMA-1, KEEL-EVALREC-1 and KEEL-CABINET-1, not
dropped.

### The defence-record schema: what the study settles

The study, the vault's R-DOC-15 and the study's lane 05 report agree on four
parts, so these are fixed:

- The record is a table in the document it defends, under a heading of its
  own. The study names that heading `## Defence record`; in a plan that holds
  several campaigns it sits one level down, under each campaign's heading
  (items 3 and 4).
- A row carries a feature, a question, the section of the same document that
  answers it, and a verdict.
- A gap row is closed by a design change or by a named scope cut.
- The record applies to a design and to a spec (R-DOC-15's checkable part); a
  spec's feature is a requirement id, which DT-3 reads.

The rest of the proposed schema is not settled by the study, and is listed
under "Open decisions for CMP-7".

### Defence record

This record holds the campaign to R-DOC-15: each question is put to the slice
plan as written above, with R-DOC-16's probes among them. It uses the two
verdict words and the five columns of "Open decisions for CMP-7" items 1 and 2
as if they are taken as recommended; a different ruling rewrites it.

| Feature | Question | Answered in | Verdict | Change or cut |
|---------|----------|-------------|---------|---------------|
| CMP-7.S1 | A cell holds an escaped `\|`: does the reader split the row wrongly? | What each CMP-7 slice builds | gap | Change: S1 reads tables by the GFM rule, with a fixture |
| CMP-7.S1 | A plan document holds seven campaigns: is there one record or one per campaign? | Open decisions for CMP-7 | gap | Change: ruled by the maintainer before S1 (item 4) |
| CMP-7.S1 | Zero design or spec documents: does the check pass over nothing? | Open decisions for CMP-7 | gap | Change: S1 states what zero means with a reason in config, the `traceability.no_requirements` pattern (item 5) |
| CMP-7.S1 | A generated project arrives with older documents and no record: is `copier update` red? | What each CMP-7 slice builds | defended | — |
| CMP-7.S2 | A project needs a kind keel does not ship: must it edit the checker? | What each CMP-7 slice builds | defended | — |
| CMP-7.S2 | The kind list lives in check_A and in the registry: what proves the copies agree? | What each CMP-7 slice builds | gap | Change: S2 removes the flat sets, so the registry is the one list |
| CMP-7.S2 | A kind has no registry row: does the check fail closed? | What each CMP-7 slice builds | defended | — |
| CMP-7.S3 | An accepted ADR breaks the contract, and its body is frozen: does the check force an edit? | What each CMP-7 slice builds | defended | — |
| CMP-7.S3 | A README that check_S does not list: do check_S and the contract disagree on it? | What each CMP-7 slice builds | defended | — |
| CMP-7.S3 | A writer copies a folder README's skeleton: can it drift from the check? | What each CMP-7 slice builds | defended | — |
| CMP-7.S4 | A generated project before its first `git init`: is its first `make verify` red? | What each CMP-7 slice builds | defended | — |
| CMP-7.S4 | A corrupt `.git`: does the freshness gate read it as no git and skip? | What each CMP-7 slice builds | gap | Change: S4 reads git through `scripts/git_tree.py` and stops on `GitFailedError` |
| CMP-7.S4 | A corrupt `.git` nested inside another repository: does git answer from the parent, so the judge judges the wrong repository? | What each CMP-7 slice builds, the nested corrupt-`.git` case | defended | — |
| CMP-7.S4 | Is the judge's git truly read-only: can it take the index lock or run the judged repository's filter? | What each CMP-7 slice builds | gap | Change: S4's runner keeps the read-only prefix, and a case shows no lock file and no filter run |
| CMP-7.S4 | The same tree on another host or a clean home: does the verdict change? | What each CMP-7 slice builds | gap | Change: S4's cases run under `tests/hermetic_git.py` `git_env`. Cut: no case runs on a second host or interpreter |
| The campaign | A month later, a check depends on today's date | What each CMP-7 slice builds | defended | — |
| The campaign | Can a project's own config switch a new check off? | What each CMP-7 slice builds | defended | — |
| CMP-7.S3 | A project edits keel's `adr.template_contract_from` to exempt more `K-` ADRs: does a check see it? | What each CMP-7 slice builds | gap | Cut: nothing inside a repository stops the edit; it shows as a diff on the next `copier update`, and review holds it, as for `scripts/expiring_tier_data.py` |
| The campaign | A new agent opens the repository: which file leads it to these rules? | What each CMP-7 slice builds | defended | — |
| The campaign | Only four slices fit the cap: what happens to the rest? | How the candidates were reconciled | defended | — |

The `copier update` row is defended by S1's done-condition, and the answer
is yes: the first `make verify` after an update is red on a project's own
design document with no record until the owner records a baseline with
`make gate-baseline`, and from then it warns until `expiring_tier.expires`. The first-`git init` row is defended because a
project with no repository stays a stated skip, which ADR-K-0019 keeps and S4
does not change. The date row is defended because the freshness gate and the
expiring tier both read the gate-run date (ADR-K-0019, `scripts/run_date.py`
`today`) and no slice reads the clock itself. The switch-off row is defended
by two bounds, each checked by a case: a project may add a kind or a home but
not rebind a kind keel ships (S2), and a project's own ADR space has no
cut-off and is judged from 0001 (S3). Beyond them, a project gets the expiring
tier with its hard date, not an off switch. The discoverability row is defended because each slice's
done-condition names the document that states its rule: `docs/guides/doc-style.md`
and `docs/specs/README.md` for S1, CONVENTIONS §1 and
`docs/guides/deterministic-checks.md` for S2, CONVENTIONS §2 and
`docs/guides/doc-style.md` for S3, and `docs/guides/deterministic-checks.md`
for S4; the root `AGENT.md` names `docs/guides/doc-style.md` and
`CONVENTIONS.md`, and check_U holds that a practice enforced by a document is
named within one hop of it. The cap row is defended if item 9 is taken as
recommended.

### Will not do in CMP-7

- **No new document kinds**, such as `plan`, `research` or `postmortem`. Moving
  keel's four plans from `kind: design` to `kind: plan` would take them out
  of the defence-record check, against the ruling that they carry one.
- **No `docs/internal/` cabinet and no document index.** Decision 2 of the
  study settles the cabinet, but moving files is a separate slice with its own
  export check; it is queued as KEEL-CABINET-1.
- **No check-id namespace and no fault-injection twin registry.** Keel's
  checks are cited as `check:<LETTER>`, `test:` or `make:` today, which check_T
  already reads; renaming every check is a campaign of its own, queued as
  KEEL-CHECKID-1.
- **No model in a gate.** A check here reads structure only; whether an answer
  holds stays with review (DT-7, decision 15 of the study).
- **No per-project off switch for a new check.** A project's own documents get
  the expiring tier with its hard date; keel's own get no grace (ruling 6).
- **No failure for a tree with no repository.** ADR-K-0019 keeps it a stated
  skip, and a reversal would need a new ADR superseding it.
- **No custodex, pyverdex, jarvis or openwiki work.** openwiki, the concept
  layer the study chose, writes view pages that no gate reads.

### Open decisions for CMP-7

Each is a question for the maintainer, with the opening pass's
recommendation. Items 1 to 5 block CMP-7.S1.

1. **The verdict words.** R-DOC-15 says "defended or gap"; DT-5 adds
   `partly`, and the word "partly" in the deck's R-DOC-15 row marks how far the
   rule can be checked, not a verdict. Recommendation: two words, and a partly
   defended feature gets two rows, one `defended` and one `gap`, so every gap
   has its own change or cut.
2. **The fifth column.** The study's record has four fields; the proposed
   schema adds Change or cut. Recommendation: keep it, because DT-6 then reads
   one cell rather than the prose around the table.
3. **The column and heading names.** The study writes `## Defence record` and
   a Section column; the proposal writes "defence table" and Answered in.
   Recommendation: the heading text `Defence record`, as in the study, at
   `##` in a document with one subject and at `###` under each campaign's
   `##` heading in a plan; and the column Answered in, which says what the cell
   must hold.
4. **Several campaigns in one plan document.** Recommendation: one record per
   campaign heading, at `###` under it, because each campaign is planned and
   approved on its own; this one is written that way.
5. **What zero documents means**, and **the reader DT-1 names.** No shared
   Markdown reader exists: check_structure, traceability and the corpus builder
   each parse headings and tables. Recommendation: zero is `ok` only with a
   reason in config; S1 makes `_pipe_table` and `_sections` in
   `scripts/check_structure.py` the one reader, and since `_sections` reads
   only `##` headings, either gives it a heading level or adds a sibling reader
   beside it in the same module, rather than adding a fourth parser.
6. **The five-W header.** It comes from a draft vault note, not an approved
   rule package. Recommendation: leave it out of CMP-7.S3 until a deck rule
   carries it.
7. **The module header fields.** Study decision 13 puts KEEL-CODE-5's fields
   in its slice 4; the queue already gives them to KEEL-HDR-1 (lane L3).
   Recommendation: KEEL-HDR-1 keeps them.
8. **Freshness before `git init`.** A generated project has no repository
   until its owner makes one, and the freshness test skips with its stated
   reason, as ADR-K-0019 keeps. Recommendation: leave it so; neither a
   `git init` in copier's `_tasks` nor a config key is added. A `git init`
   would create a second repository inside an existing one when a project is
   generated as a subproject, which `copier.yml`'s migration notes allow for;
   a config key would excuse what the skip already states. CMP-7.S4's
   nested corrupt-`.git` case covers a subproject inside a parent repository.
9. **The cap.** Recommendation: read "five slices, the opening pass included"
   as four built slices, so CMP-7.S4 is the last; a fifth needs the
   maintainer's word.

