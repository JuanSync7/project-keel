---
title: Template ADRs
kind: doc
layer: n/a
status: template
owner: TBD
public_api: none
tags: [adr, decisions, template]
summary: The architecture decisions the template ships into every project, numbered in their own space as K-NNNN-<slug>.md and cited as ADR-K-NNNN.
id: docs-adr-keel-readme
created: 2026-10-07
updated: 2026-10-08
visibility: internal
canonical: true
---

# Template ADRs

The architecture decisions the template ships into every project it
generates. Each one is `K-NNNN-<slug>.md` and is cited as `ADR-K-NNNN`; the
`K-` prefix is `config/project.json` `adr.template_prefix`, and check_Y in
`scripts/check_structure.py` holds every file here to that grammar and to
`adr.template_adrs`, the list of the files the template ships. A
project's own decisions do not belong here, and a file here that the list does
not name is an error: they live one directory up, in
the project's number space ([../README.md](../README.md)). The template
updates these files on `copier update`; a project that edits one keeps a
copy the update names, as the parent README describes.

## What ships here

| Member | Decision | Not for |
|--------|----------|---------|
| `K-0001-record-architecture-decisions.md` | Decisions are recorded as numbered, immutable ADRs, superseded rather than edited. | Which number space an ADR is numbered in: `K-0013-template-and-project-adr-number-spaces.md` decides that. |
| `K-0002-agent-surface-and-discovery.md` | A vendor-neutral agent surface, with AAD as the first adapter. | How an agent's control flow runs: `K-0003-agent-control-flow-runtime.md`. |
| `K-0003-agent-control-flow-runtime.md` | Agent control flow is a neutral Runtime in `runtimes/`; LangGraph is one adapter. | How an agent is exposed to callers: `K-0002-agent-surface-and-discovery.md`. |
| `K-0004-project-templating-copier.md` | Projects are generated and updated with copier, with the repository root as the template. | Retiring a declined answer's files: `K-0006-answer-retirement-via-migrations.md` amends this for that. |
| `K-0005-external-environment-manifest.md` | Proposed: declare what a project needs from outside its container in `config/environment.json`. | The environment a child process inherits: `K-0012-child-process-environment-allowlist.md`. |
| `K-0006-answer-retirement-via-migrations.md` | Files of a declined answer are retired by `_migrations`, accepting `--trust` on update. | The trust `copier copy` needs: `K-0010-generation-needs-trust-to-stamp-docs.md`. |
| `K-0007-optional-showcase-and-project-owned-identity.md` | The showcase is optional, and a project's identity comes from its manifest. | The mechanics of removing the showcase on update: `K-0006-answer-retirement-via-migrations.md`. |
| `K-0008-gated-module-contract-for-agent-interpretability.md` | Every module carries a gated `title:`/`summary:` header, symbols are documented, and the corpus stays current. | How Python is written beyond that floor: `docs/guides/python-style.md`. |
| `K-0009-release-identity-and-the-tag-ordering-rule.md` | A release is a tag on a commit no descendant is ahead of, and every dated changelog heading has its tag. | Which version the next breaking change takes: `K-0013-template-and-project-adr-number-spaces.md` sets 0.2.0. |
| `K-0010-generation-needs-trust-to-stamp-docs.md` | Generation runs the doc-stamping task, so `copier copy` needs `--trust`. | The freshness rule the stamp serves: `scripts/jobs/review_docs.py` judges it. |
| `K-0011-make-target-effect-labels.md` | Every annotated make target declares its effect, and the gate runner runs only a read-only one. | A child process's environment: `K-0012-child-process-environment-allowlist.md`. |
| `K-0012-child-process-environment-allowlist.md` | Every child process gets an allowlisted environment built by `scripts/child_env.py`. | What a make target may change: `K-0011-make-target-effect-labels.md`. |
| `K-0013-template-and-project-adr-number-spaces.md` | Template and project ADRs live in separate number spaces, guarded by check_Y and kept on update by `scripts/jobs/keep_edited_retired.py`. | Whether an ADR's decision is still in force: its own `status:` says that. |
| `K-0014-project-owned-structure-checks.md` | Proposed: a project adds structure checks as modules in a directory it owns, named by `structure.project_checks`, never as an edit to `scripts/check_structure.py`; every `after` migration stops with exit 2 over a conflicted import. | Waiving or narrowing a template check: no key does that, and the disagreement belongs upstream. |
