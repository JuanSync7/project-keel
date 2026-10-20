---
title: "ADR-K-0025: a committed secret meets a keyed gate and a scanner, and a missing scanner fails closed"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, secrets, security, scanner, pre-commit, ci]
summary: "keel's own rule against a committed credential is a gate test with no outside tool: tests/integration/test_committed_secrets_gate.py fails a file a commit could carry that gives a name a secret config_loader KEYS row declares a value. A scanner covers the shapes no name declares, as a thin adapter, scripts/scan_secrets.py, behind config/project.json secrets.scanner, an adapter for gitleaks, installed by the pre-commit hook pinned at the configured rev. The scanner runs on the staged diff at commit and on every commit in make verify and CI. A scanner that is missing or not the recorded build is exit 11, and a scan over zero files is exit 13, never a skip or a pass."
id: docs-adr-0025-committed-secrets-keyed-gate-and-scanner
created: 2026-10-20
updated: 2026-10-20
visibility: internal
canonical: true
---

# ADR-K-0025: a committed secret meets a keyed gate and a scanner, and a missing scanner fails closed

**Status:** proposed. It edits no other ADR. It builds on
[ADR-K-0011](K-0011-make-target-effect-labels.md), whose effect labels the new
targets carry, [ADR-K-0012](K-0012-child-process-environment-allowlist.md),
whose allowlisted environment the scanner runs under, and
[ADR-K-0022](K-0022-one-config-loader.md), whose `KEYS` rows say which names
are secret.

## Context

"No secrets in config" was a written rule in `AGENT.md` and `config/AGENT.md`.
Nothing in keel's pre-commit hooks, `make verify` or CI refused a credential,
so a credential committed to a generated project was caught by nothing until
a person saw it. In a sister repository one such credential needed a history
rewrite.

Two kinds of leak need different tools:
- a value under a name the project itself declares secret, such as a model
  adapter's API key in `config/project.json` or `.env`. keel knows these names
  from `scripts/config_loader.py` `KEYS`, so a test can judge them with no
  outside tool;
- a credential-shaped string under any other name, in any file, which only a
  pattern scanner can see.

## Decision

1. **The keyed gate is keel's rule.**
   `tests/integration/test_committed_secrets_gate.py` takes its secret names
   from the `KEYS` rows with `secret=True`. It judges every file a commit
   could carry (`scripts/git_tree.py` `candidate_files`), its work-tree copy
   and its index copy, when the file's basename matches
   config/project.json `secrets.json_files` or `secrets.dotenv_files`. A value
   other than the empty value under a secret name is red, named by file, line
   and key, never by value. Every name `models.credential_env` lists must have
   a secret row, so a new credential cannot slip past by having none.
2. **The scanner is an adapter behind config.** config/project.json
   `secrets.scanner` names the program (`gitleaks`), the hook repository and
   the release (`rev`) that installs it, the status that means "findings",
   and the exclusions. `scripts/scan_secrets.py` is the one place the
   scanner's own flags are written. Another scanner is a second adapter beside
   it, and never an edit to the gate test.
3. **One declared installer.** The scanner is built by the pre-commit hook
   that `.pre-commit-config.yaml` pins at `secrets.scanner.rev`.
   `make secrets-install` runs that hook's manual `secrets-locate` stage, which
   records the program's path, rev and sha256 in the git-ignored
   `secrets.scanner.record_file`. Commit, `make verify` and CI therefore run
   one build, and none of them downloads anything outside pre-commit.
4. **Where it runs.**
   - At commit, the `secret scan (staged, or every commit when nothing is
     staged)` hook scans the staged diff, with the index the hook commits.
     Run by `pre-commit run --all-files`, which stages nothing, it scans
     every commit instead, so the hook is never a pass over zero files.
   - `make verify` runs `make secret-scan`, a `[local]` goal that scans every
     commit `secrets.scanner.history_log_opts` reaches, so a value a commit
     added and a later commit deleted is still red.
   - CI runs `make secrets-install` and `make secret-scan` before `make
     verify`.
5. **It fails closed.** No record, a record naming another program or rev, a
   recorded program that is gone or whose digest changed is exit 11
   (`BACKEND_ABSENT`), naming `make secrets-install`; so is a scanner whose
   status and report disagree, because it gave no verdict. No repository, no
   commit, history log options that reach no commit, or a hand-run `--staged`
   scan of a stage that adds or changes no file is exit 13
   (`NOTHING_JUDGED`), because a scan over zero files proves nothing. A git
   command that fails is exit 2 (`USAGE`), and a `secrets.scanner.name` the
   script has no adapter for is exit 14 (`CONFIG`). Exit 1 is a finding and
   nothing else. None of them is a skip.
6. **No file under judgement decides what is judged.** The scanner's own
   config and ignore files (`secrets.scanner.refused_files`) make a scan exit
   14 before it runs. Inline allow comments are ignored. An exclusion excuses
   one rule in one exact file and carries a reason, and one the history scan
   did not use is exit 14.
7. **A value is never printed.** A finding is `file:line rule`, a history
   finding adds its commit's first 12 hex digits, and the scanner is handed
   redaction.

## Consequences

- `make verify` in a fresh clone is red with exit 11 until `make
  secrets-install` has run once. The README Quickstart runs it before the
  first `make verify`, and `make secret-scan` is in
  config/project.json `make_targets.effect_proof_skip` for that reason.
- The first install builds the scanner from source through pre-commit, which
  needs Go's module proxy or `GOPROXY=direct` and a CA bundle where TLS is
  intercepted; docs/guides/limits-and-troubleshooting.md names the symptoms.
  A later install reuses pre-commit's cache.
- The record is trust on first use: a program called `gitleaks` that is first
  on `PATH` when `make secrets-install` runs is the one recorded.
- What neither layer sees is listed in
  docs/guides/deterministic-checks.md: a value split across literals, a weak
  password with no known shape, the file types the scanner's default rules
  allow (lockfiles, `go.sum`, images, PDFs, `node_modules/`), and a value
  already pushed. A leaked credential is rotated first, as
  docs/guides/limits-and-troubleshooting.md "A credential was committed"
  says; deleting it is not the fix.

## Alternatives considered

- **The scanner only.** Rejected: a scanner sees shapes, not names, so a
  credential the project declares under its own key but with no known shape
  passes, and keel's rule would live in a third-party tool's config.
- **The keyed gate only.** Rejected: it cannot see a credential under a name
  no `KEYS` row declares, or in a file type it does not parse.
- **Install the scanner as a pip extra or a downloaded binary.** Rejected:
  pre-commit is already in the dev extra and pins the scanner's own
  repository by rev, and either choice would be a second installer to pin and
  audit.
- **Skip the history scan when the scanner is missing.** Rejected: a skip
  reads as green, and a missing scanner is the state a fresh clone starts in.
- **Scan only the pushed range in CI.** Rejected for now: a full history scan
  of keel's 113 commits took 7.4 seconds on a network home directory, and a
  range needs the base the CI provider gives, which differs by event.

## Scope cuts

Not built:
- rewriting history after a leak;
- scanning other repositories;
- a second scanner adapter;
- a check that the CI step ran on a commit the provider skipped, such as one
  whose message asks CI to skip.
