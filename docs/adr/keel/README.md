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
updated: 2026-10-22
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
| `K-0014-project-owned-structure-checks.md` | A project adds structure checks as modules in a directory it owns, named by `structure.project_checks`, never as an edit to `scripts/check_structure.py`; every `after` migration stops with exit 2 over a conflicted import. | Waiving or narrowing a template check: no key does that, and the disagreement belongs upstream. |
| `K-0015-write-shape-exemptions-and-guarded-recipe-converse.md` | A write-shaped target that is not a write keeps its label under a named reason in `make_targets.write_shape_exempt`, and a labelled recipe that calls `$(WRITE_GUARD)` must be `[write]`. | Which effect labels exist or what the gate runner admits: `K-0011-make-target-effect-labels.md` decides that. |
| `K-0016-release-order-tag-before-verify.md` | Tag locally before the release verify; push main and the tag only on green. | Whether a version heading needs a tag: `K-0009-release-identity-and-the-tag-ordering-rule.md` decision 3. |
| `K-0017-gate-evidence-record.md` | `make verify` runs its goals through `scripts/gate_evidence.py` and writes one canonical, schema-versioned evidence record to config/project.json `evidence.dir`. | Keeping a history of runs: each run replaces the record, and the ledger is project-jarvis's. |
| `K-0018-model-endpoint-host-allowlist.md` | A model adapter sends its credential only to a `host` or `host:port` config/project.json `models.allowed_hosts` lists for it, matched exactly in one canonical form; the list ships empty, and a redirect is refused. | Which variable an adapter may send: `K-0012-child-process-environment-allowlist.md`. |
| `K-0019-one-date-per-gate-run.md` | A gate run reads the clock once and hands that date to every goal in the variable config/project.json `evidence.run_date.env` names; a git command that ran and failed is refused, never read as no git; the driver refuses an evidence path reached through a symlink. | What the record holds or where it is written: `K-0017-gate-evidence-record.md`. Which variables a child inherits: `K-0012-child-process-environment-allowlist.md`. |
| `K-0020-shared-compute-launcher.md` | One launcher, `scripts/launch.py`, decides where a long script runs from the host kind, the script length and the farm, and says why in one line; a host is shared unless a git-ignored local pattern file matches it, a script is long unless a recorded success proves it short, and the farm is a config adapter that ships as `none`. | Which variables a child inherits: `K-0012-child-process-environment-allowlist.md`. How the gate itself runs: `K-0017-gate-evidence-record.md`. |
| `K-0021-imports-flow-up-a-configured-layer-order.md` | config/project.json `import_layers.order` lists the layers bottom to top and `tests/integration/test_import_layers_gate.py` fails an import into a higher layer; check_D fails `from pkg import _sub` from outside `pkg/`; a module another project module imports never ends the process outside its entry block. | Where a long script runs: `K-0020-shared-compute-launcher.md`. |
| `K-0022-one-config-loader.md` | `scripts/config_loader.py` is the one reader of config/project.json, config/practices.json and the variables they declare; a variable wins over the file only where a `KEYS` row names it; a missing or wrong value exits 14, `CONFIG`, and `tests/integration/test_config_reads_gate.py` fails a direct read. | Which variables a child process inherits: `K-0012-child-process-environment-allowlist.md`. Where a module may import from: `K-0021-imports-flow-up-a-configured-layer-order.md`. |
| `K-0023-canary-gates-a-release-not-a-commit.md` | Proposed: `make canary` renders each configured answer set fresh and as an update from the previous release tag and runs that project's `make verify`, before a release push, weekly and on demand, never in `make verify`; a red canary blocks the release push and nothing else. | The release order it adds a step to: `K-0016-release-order-tag-before-verify.md`. What `make verify` itself runs: `K-0017-gate-evidence-record.md`. |
| `K-0024-what-a-test-may-reach.md` | Proposed: a test's network, write and store rule is a row of config/project.json `tests.isolation.tiers` its closest tier marker picks; `tests/isolation_guard.py`, an audit hook `tests/conftest.py` installs, fails a test that reaches past it, an exemption is per test and axis with a reason and an unused one is red, and test scratch lives under `tests.scratch_root`. | What a child process inherits: `K-0012-child-process-environment-allowlist.md`. The one config reader it reads through: `K-0022-one-config-loader.md`. |
| `K-0025-committed-secrets-keyed-gate-and-scanner.md` | Proposed: a keyed gate test fails a committable file that gives a secret `KEYS` name a value, and a scanner adapter, `scripts/scan_secrets.py` behind config/project.json `secrets.scanner` (the gitleaks adapter, the scanner installed by the pinned pre-commit hook), scans the staged diff at commit and every commit in `make verify` and CI; a missing or unrecorded scanner, or one that gave no verdict, is exit 11 and a scan over zero files exit 13, never a skip. | What a child process inherits, the scanner included: `K-0012-child-process-environment-allowlist.md`. Which config keys are secret, and how a value is read: `K-0022-one-config-loader.md`. |
| `K-0026-agent-edits-cannot-reach-the-judge.md` | Proposed: `scripts/apply_refactor.py` refuses, before any write, an agent edit to a path config/project.json `agents` protects, judged case-folded on the path and its realpath, to a file git does not track, or to a file the run did not `--allow`; the block protects itself, and the gate is the caller's `--gate`, never the spec's. | Which make targets a gate may run: `K-0011-make-target-effect-labels.md`. The one config reader the policy is read through: `K-0022-one-config-loader.md`. |
| `K-0027-a-project-s-own-code-warns-until-a-hard-date.md` | Proposed: a gate test that adopts the expiring tier hands its findings to `scripts/expiring_tier.py`; in the template repository every finding is red, and in a generated project a finding config/project.json `expiring_tier.baseline` records warns until `expiring_tier.expires`, no later than keel's `CEILING`, while an unrecorded finding and an entry no finding matches are red; `make gate-baseline` grows the record only when `_commit` moves. | The one config reader: `K-0022-one-config-loader.md`. The one date a run judges by: `K-0019-one-date-per-gate-run.md`. The target's effect label: `K-0011-make-target-effect-labels.md`. |
