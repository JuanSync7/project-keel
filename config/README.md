---
title: Config
kind: config
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: Committed configuration defaults and examples (no secrets).
id: config-readme
created: 2026-06-17
updated: 2026-10-10
visibility: internal
canonical: true
---

# Config

Committed configuration defaults and examples (no secrets).

Commit runtime defaults (`default.*`, `*.example.*`) and committed governance
manifests (`project.json`, `practices.json`, generated `*.schema.json`) — never
secrets, which live in `*.local.*` or `.env` (gitignored). No loader for the
example TOMLs ships: they are a pattern for the one your `app/` layer writes,
and nothing in the template reads them. The checker reads the manifests
(CONVENTIONS §15).

`practices.json` is the vendor-neutral registry of the coding practices Keel
promotes (gate/advisory/doc, universal/domain) — read by path, never imported.
See `docs/guides/coding-practices.md`.

`evidence/gate-record.schema.json` is the typed, versioned shape of the
record a gate writes; `scripts/gate_evidence.py` finds it through
`project.json` `evidence.schema` and stamps its `schema_version.const` into
every record. It is written by hand, not generated, and a field it does not
name is an error (`additionalProperties: false`).
