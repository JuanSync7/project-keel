---
title: CMP-11 — parallel slices stop colliding in the shared files
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-11.
id: docs-internals-campaigns-cmp-11
created: 2026-10-06
updated: 2026-11-17
visibility: internal
canonical: true
---

## CMP-11 — parallel slices stop colliding in the shared files

The maintainer moved KEEL-FRAG-1 to queue position 4 on 2026-10-22 so that
slices built in parallel worktrees stop conflicting. CMP-11 builds the part of
that row a test can hold, in keel itself. A slice that adds a campaign to this
plan, an entry to the settings or features reference, or a row to the changelog
writes it in a file of its own, which no other slice writes. A reference or the
changelog is then assembled from its entry files in sorted order, and assembling
it twice writes the same bytes. Two lanes can still conflict in an assembled
file, because each lane commits its own assembly. The lane that lands second
takes either side of that conflict and runs the assembly target again, which
writes the file from the union of both lanes' entry files. Each slice's starting
test runs that workflow on two branches.

CMP-11 leaves three things out. A generated project keeps its references and
changelog written by hand, exactly as today: the entry folders do not ship, and
the generated project's config lists no fragment set. Adopting fragments in a
generated project needs a migrate step the user runs on purpose, which turns the
rows they wrote into entry files, and that is a separate item. Two slices of
the same campaign still edit that campaign's one file, so the CMP-6.S3 and
CMP-6.S6 collision in the queue below is not removed. `config/project.json`, its
twin and `docs/adr/keel/README.md` stay one file each. CMP-11 therefore does not
finish KEEL-FRAG-1.

The cap is three passes, one slice each in the order S1 to S3, and a slice's
review gets at most three fix rounds. The stop point is CMP-11.S3 green or the
cap, whichever comes first. CMP-11 builds only after CMP-9 and CMP-10 land,
because S1 moves the plan sections both of them edit.

The opening pass read `main` at `25de8e2` and counted each shared file's lines
and how many of the last 60 commits touch it: `CHANGELOG.md` 2803 lines and 9
commits, this plan 3686 and 13, `config/project.json` 623 and 2, its twin 633
and 2, `docs/adr/keel/README.md` 60 and 0, `docs/reference/settings.md` 536 and
3, `docs/reference/features.md` 359 and 5. check_Z already reads every
`kind: design` document with a `Slice` table as a plan doc, so a campaign in its
own file needs no new rule. `tests/integration/test_copier_generation.py` reads
slice rows from this plan by its path, and `copier.yml` `_exclude` names this
plan by its path. The config file and its twin were touched by 2 of 60 commits
and the ADR index by none, so they are not in CMP-11. The counts are one
measurement, not a gate's.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-11.S1 | This plan holds every campaign in one file, so two lanes that each add a campaign edit the same lines, and the file grows without bound. A campaign gets its own `kind: design` document under `docs/design/campaigns/`, and this plan keeps the queue table, written by hand as now. The plan keeps no list of campaign documents, because a hand-kept list is the one line every new campaign would edit; the folder is the list. No slice id, campaign heading or queue row is lost or changed in the move. Add `tests/integration/test_copier_generation.py::test_split_campaign_plans_preserve_ids_and_never_ship` first: its first assertion fails today because `docs/design/campaigns/` does not exist, and it also fails when a moved section loses a slice id or a campaign document ships to a generated project. Its second case starts from a baseline on which both campaign ids are already opened, as the plan commit that opens a campaign does today, adds slice rows to each campaign on its own branch, merges them, and shows neither branch touched a line the other did and check_Z passes on the merge | implemented — delivered by d547291c, 31b6d875 and 3a4042ff; review FIX in round 1, its one STOP (the campaign-id fixture shipped) fixed in 31b6d875; the first landing verify went red on the fixture's missing upgrade-guide exclusion row, added in 3a4042ff |
| CMP-11.S2 | Every slice that adds a setting or a feature edits one row table in `docs/reference/settings.md` or `docs/reference/features.md`, so two slices conflict on adjacent rows. An entry becomes one file in a fragment folder beside its reference, and `scripts/assemble_fragments.py` writes the reference from its head and its entry files in sorted order. Its `--check` mode fails a reference that differs from what it would write, so a second run writes nothing. Add `tests/integration/test_reference_fragments.py::test_two_independent_entries_survive_assembly` first: its first assertion fails today because `scripts/assemble_fragments.py` does not exist. It adds one entry on each of two branches, merges them, takes either side of the assembled file, reassembles, and shows both entries present and `--check` passing. A second case deletes the newest entry on a later pinned date, assembles, runs `scripts/jobs/restamp_docs.py`, and shows `--check` and the freshness rule both pass with no repair loop. `tests/integration/test_reference_drift.py`, `tests/integration/test_config_default_lines_docs.py`, `tests/integration/test_ci_pipeline_gate.py`, `tests/integration/test_edit_policy_docs.py`, `tests/integration/test_isolation_docs.py` and `tests/unit/backend/test_showcase.py` read the assembled file and stay unchanged | planned |
| CMP-11.S3 | Every slice adds its row under `## [Unreleased]` in `CHANGELOG.md`, so two slices conflict on the same heading. An unreleased entry becomes one file under `changelog.d/<section>/`, where the section is `added`, `changed`, `fixed` or `security`, and S2's assembler writes the `[Unreleased]` section from those files in sorted order; a dated section stays as it is. Releasing rotates `[Unreleased]` into a dated heading and opens a fresh empty one, as ADR K-0016 orders: the assembler's release mode writes the entry files' text under the dated heading and deletes the entry files in the same change. Add `tests/integration/test_changelog_fragments.py::test_independent_entries_render_without_leaking_template_history` first: its first assertion fails today because `changelog.d/` does not exist. A second case rotates, runs `--check`, assembles twice with no change, adds one entry, and shows it only under `[Unreleased]`. A third generates a project and shows it has no `changelog.d/`, its `CHANGELOG.md` is the one `CHANGELOG.md.jinja` writes, and the check passes there before any write. `tests/integration/test_release_identity.py`, `scripts/canary.py` and `CHANGELOG.md.jinja` stay unchanged, and `tests/integration/test_copier_generation.py::test_generated_project_starts_its_own_changelog` still passes | planned |

CMP-11.S1 owns this plan's campaign sections, the new `docs/design/campaigns/`
directory, the `copier.yml` `_exclude` entry for it and that entry's row in
`docs/guides/generate-and-upgrade.md`, which
`tests/integration/test_doc_drift.py::test_the_upgrade_guide_names_every_copier_migration_task_and_exclusion`
holds. S1 also owns the slice-row read in
`tests/integration/test_copier_generation.py`. A section that moves one folder
deeper keeps every relative link working: S1 rewrites each `](../` link in a
moved section (this plan holds six) for its new folder, and check_Q reads every
one of them. The queue table and its `Queued after Campaign 6` heading stay in
this plan, because the queue is the one place the order of work is approved.
check_Z requires campaign ids with no gap, so a campaign id is reserved on
`main` by the plan commit that opens it before any lane branches; S1 states that
order in CONVENTIONS §20's prose and changes no rule. S1 writes no assembler,
because the plan keeps no derived list.

CMP-11.S2 owns `scripts/assemble_fragments.py`, both references, their fragment
folders and the `config/project.json` key that lists the fragment sets: each
set names its output, its head and its folder. The generated project's twin
lists no set. A fragment set's folder that is missing fails the check, and so
does a fragment folder no set names, so a project with no set is checked to
hold no stray folder rather than passing over nothing. An entry file is not a
governed document: it has no frontmatter, its links are written as they read
from the assembled file, and check_Q reads them there. Its suffix is a config
value, and it is not `.md`, so the doc gates and `scripts/jobs/review_docs.py`
do not read it. Each fragment folder gets the roster row
`docs/reference/README.md` requires, and the `copier.yml` `_exclude` entry and
its row in `docs/guides/generate-and-upgrade.md` that keep it out of a generated
project. Because check_S fails a roster row whose member is missing, and the
folders do not ship, S2 adds `docs/reference/README.md.jinja` without those
rows, declares it in `config/project.json` `template.twins` (check_N), and
asserts the generated roster names only `settings.md` and `features.md`. S2 adds a `[tree]` make target that writes the assembled files and a
`[local]` target that runs `--check`, the label ADR K-0011 gives a target that
only reads this machine. The `[local]` target becomes a prerequisite of
`check-all`, which `make verify` runs, so a stale reference fails the gate.
A script `check-all` reaches needs its catalogue row, so S2 adds the
assembler's error-tier row to `docs/guides/deterministic-checks.md`; and it
needs its exit-code rows, so S2 regenerates
`docs/guides/limits-and-troubleshooting.md` with `make exit-codes`, which
`make check-exit-codes` holds. S3 regenerates that table again for the
release mode's exits. A new script needs its roster row, so S2 adds the
assembler's row to `scripts/README.md` and to `scripts/README.md.jinja`, which
check_S compares with the directory in keel and in a generated project.
The settings reference gets a row for each assembler flag and both targets. The
assembler is a writer, so its header carries `effect: writes`,
`rerun: fixed-point` and a `rerun_proof:` that resolves (check_V). A new config
key gets a `KEYS` row in `scripts/config_loader.py` and its line in
`docs/reference/settings.md`. The assembler owns an assembled file's body and
the freshness rule owns its `updated:` line: the assembler reads no clock, keeps
the `updated:` value already in the output (or the head's when the output is
new), and `--check` compares everything but that line. A lane that changes a
fragment restamps the reference with `scripts/jobs/restamp_docs.py`, as it does
for any document it changes. S3 runs after S2 and adds the changelog to the same
assembler, so there is one assembler and one pair of targets.
S2's first commit writes the entry file contract into this section before
any code: how an entry names its section and row key, how the assembler
writes each section's table head once, the filename rule that keeps two
lanes' entries apart, the refusal of a malformed or duplicate entry, and the
configured fragment root that finds an unregistered folder when no set is
listed. Its tests use synthetic fixtures wherever they can, so they ship and
pass in a generated project, and a case that needs keel's own fragments
carries the `copier.yml` guard `test_copier_generation.py` already uses; a
shipped case shows the empty-set check accepts a hand-edited reference and
writes nothing.

The entry contract is one `.part` file per complete table row, including its
final newline. Its table is the numbered subfolder that contains it. Its key
is the first code span in its first cell, or that whole cell when there is no
code span. A row has the same cell count as its table header. A root holds
`head.part`, sorted table subfolders and `tail.part`; each table subfolder
holds `head.part` for section prose and the two table header lines, followed
by its sorted row files. The tail holds the fixed text after the final table.
A table already sorted by key names each entry with its percent-encoded key.
An unsorted table keeps its historical order with a six-digit prefix and the
encoded key. A new entry takes the next prefix; two lanes may share a prefix
because their distinct keys keep their filenames independent. The assembler
refuses an entry whose name does not encode its key, and a table that mixes
the two forms. The non-Markdown suffix is configured. Fragments have no frontmatter and links read relative
to the assembled file, where check_Q judges them; check_A and the freshness
rule judge only the assembled Markdown.

CMP-11.S3 owns `CHANGELOG.md`, `changelog.d/`, the assembler's changelog and
release modes, and the release steps in `CONTRIBUTING.md`. `changelog.d/` is a
new top-level directory, so S3 declares it in `config/project.json`
`structure.extra_toplevel` and gives it a `README.md` and a `CLAUDE.md` link to
its `AGENT.md` (check_B, check_I); the twin keeps an empty list, because the
folder does not ship. S3 adds its `copier.yml` `_exclude` entry and that entry's
row in `docs/guides/generate-and-upgrade.md`, and the assembler reads only the
four section folders, so the folder's `README.md` and `AGENT.md` are never
entries. A dated section keeps the heading ADR K-0009 requires, and rotation
follows ADR K-0016, which supersedes K-0009's release order. S3 converts every
current `[Unreleased]` line to an entry file, including the bullets above the
first category, which go to a fifth folder whose name is a config value, and
its starting test compares the assembled section with the hand-written one
line for line. S3 changes no
accepted ADR text; if the fragment layout would need such a change, the slice
is parked for the maintainer.

