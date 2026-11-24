---
title: CMP-29 — what the vault issues reaches keel by a pinned sync
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-29.
id: docs-internals-campaigns-cmp-29
created: 2026-11-24
updated: 2026-11-24
visibility: internal
canonical: true
---

## CMP-29 — what the vault issues reaches keel by a pinned sync

Issue #39 asks for one source for what keel and the experience vault share.
The vault writes the document formats, the rule package and the playbooks, keel is where they are used, and a project generated from keel receives them with the template.
No config key or gate in keel names a vault version today: `config/project.json` holds no pin, document frontmatter carries no format version, and no gate compares a copy with its source.
The owner approved the campaign on 2026-11-24, with the playbook sync as the first slice and the version stamps as the second (queue row 210).
Issue #40, a `keel` agent on top of the synced playbooks, is a later campaign (queue row 211).
The owner approved S1 and S2; S3 to S5 are this plan's reading of issue #39 and wait for the owner's yes.
The cap is five slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at the done-condition, or at the cap.
Will not do in CMP-29: build the `keel` agent or move an existing agent under it (issue #40), reach the vault from `ci` or from a generated project's gate, write to the vault's repository, or change the vault's own publication checks.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-29.S1 | Keel cannot take a file from the vault and later prove its copy is unchanged. One playbook goes end to end: a pin in `config/project.json`, a sync that copies only the files the pin names and records each file's hash in a lock file, a gate that fails a copy that differs from the lock file, and a generated project that receives the copy and the gate. | planned — the mechanism is built on invented files; the first real sync waits for the owner (see "Open decisions") |
| CMP-29.S2 | A governed document does not say which version of its format it is written in, so a change to the format's fields cannot be told from an old file. Frontmatter carries a `schema:` stamp, check_A refuses a version it does not know, and a proposed ADR records one way to name a format version across keel and the vault. | planned |
| CMP-29.S3 | Issue #39 names the eval and gate schemas as the formats whose definition has one owner file. Each other format keel writes gets one definition file, and the S1 sync pins the vault's version of it. | planned |
| CMP-29.S4 | Keel tracks no copy of the vault's rule package. The S1 sync pins and copies it, and the S1 gate holds the copy. | planned |
| CMP-29.S5 | A fix found in a keel project has no path back to the vault. A keel project writes a report in the vault's feedback format for the vault to review, and one change goes each way through the sync. | planned |

### Done-condition

A slice is done when its landing verify is green.
The campaign is done when a project generated from the template names the vault version of every format it writes, `make verify` checks those pins, and one change has gone each way through the sync (issue #39).

### Decisions

The owner made the first four on 2026-11-24; the fifth and sixth are issue #39's, and the last is a proposal.

- Issue #39 is one campaign and issue #40 is the next, because the agent of #40 is built from playbooks that only this sync delivers.
- S1 is the sync and its gate, proven on one playbook, before the version stamps. Issue #39 orders formats, then rules, then playbooks; the sync comes first because every later slice delivers through it.
- A synced playbook may be public. Keel is a public repository, and the playbooks are shown as an example of how a playbook works in a project.
- `ci` never reaches the vault. The gate compares the copies with the lock file, and both are in the tree; only the sync reads the vault, and a person runs it.
- A sync copies only the files that a published card's `reveal` list names, and copies nothing from a draft card. Issue #39 names the public site's playbook sync as the model, and this is that sync's rule: only the vault's owner adds a file to a card, and a sync never does.
- The sync writes into keel and never into the vault. A change for the vault travels as a report the vault reviews before it changes anything (S5).
- The proposed version name is `family/n`, such as `keel-doc/1`, and not a `schema` path with a separate `schema_version`: one value names the format and its version, and issue #39 gives it as the vault's style. It stays a proposal until the owner accepts the ADR that S2 writes.

### S1 as planned

- The pin names a playbook and the digest in the vault's manifest for it. The sync refuses a vault whose manifest carries another digest, so taking a new version is a change to the pin.
- A copy is the vault's file byte for byte. The site's sync rewrites paths inside one file; keel keeps the playbooks in sibling folders as the vault does, so the paths a playbook names resolve without a rewrite, and a copy's hash is the one the vault's manifest gives.
- The vault's digest covers every file of a playbook, revealed or not, so a gate that sees only the copies cannot recompute it. The sync checks the digest against the vault and records it in the lock file; the gate holds the pin to the lock file and the lock file to the copies.
- The vault's path is an argument of the sync and never a configured value, so no host path enters the tree.
- The gate fails when no playbook is pinned or the lock file records no copy, because a check of nothing is not a pass. S1's branch therefore lands with the first real sync and not before it.

### Open decisions

- **What S1 syncs first.** The card of the review playbook, the one proposed for S1, reveals no file today, and that playbook opens a file of the `agent` playbook, so the two go together. Either the owner adds the files to those two cards in the vault, or S1 is proven first on the vault's rule package and the playbooks follow. S1 copies no vault file before the owner chooses, and before the owner confirms the list by name and count.
- **Where the copies live in keel.** A new top-level directory needs a CONVENTIONS §2 row or a `structure.extra_toplevel` entry (check_B), and a directory under `agents/` would settle a layout that issue #40 owns. S1 decides this with its first failing test.
- **Which keel gates judge a copy.** A copy cannot be edited here to satisfy a keel rule, and keel's walks of the tree would reach it. `scripts/jobs/restamp_docs.py` rewrites `updated:` in any Markdown file that carries one, and `copier.yml` runs it on every render, so a copied document with that key would stop matching the lock file in a generated project; neither proposed playbook holds such a file today. The copies also include check scripts, which ship to every generated project. One choice keeps the copies out of every walk: `scripts/check_structure.py` `IGNORE_DIRS` does that, but it holds names and not paths, check_B refuses a declared top-level directory with such a name, and the exit, banned-API, swallowed-error, child-environment and committed-secrets gates read the tree through the same walk and would stop seeing the scripts. The other keeps the stamper and the style checks off the copies by path and leaves the safety gates on them, so a copy that fails one is refused at the sync. CONVENTIONS §9 rules out vendoring a tool, so either choice is recorded as an ADR for the owner's yes before S1 lands.
