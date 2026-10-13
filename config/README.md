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
updated: 2026-10-13
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

`evals/eval-case.schema.json` is the shape of one eval case, one line of a
suite in `project.json` `evals.dataset_dir`. `evals/_dataset.py` holds every
rule it states by hand, and `tests/integration/test_evals_schema.py` proves
the parser and the schema accept and refuse the same cases. Its
`schema_version.const` is the only owner of the case format's version:
`evals/_config.py` reads it from here. It is written by hand.

`evals/eval-report.schema.json` is the shape of the report
`scripts/run_evals.py` writes to `project.json` `evals.report_dir`. Its
result, reason and outcome enums are held equal to the vocabularies in
`evals/_report.py` by `tests/integration/test_evals_schema.py`, and its
`schema_version.const` is the only owner of the report format's version. It
is written by hand.

`own-hosts.example.json` is the twin of the git-ignored file
`project.json` `launcher.own_hosts_file` names (`config/own-hosts.local.json`):
a copy lists fnmatch patterns for the hosts that are one person's own, and
`scripts/launch.py` runs a long script as normal only on a host one of them
matches. It ships placeholder names only, because a host name is never
committed; with no local copy every host counts as shared
(`docs/adr/keel/K-0020-shared-compute-launcher.md`).

`traceability/matrix.schema.json` is the shape of the matrix
`scripts/trace_requirements.py` writes to `project.json`
`traceability.matrix_path`; the command finds it through
`traceability.matrix_schema`. Its verdict, finding-kind, state and result
enums are held equal to the vocabularies in `scripts/traceability.py` by
`tests/integration/test_requirement_traceability.py`, and its
`schema_version.const` and string bounds are the only owners of the matrix
format's version and of how long an id or a reason may be: the command reads
them from here. It is written by hand.
