---
title: Evals
kind: eval
layer: n/a
status: template
owner: TBD
public_api: evals
tags: []
summary: The eval harness — typed JSONL cases, deterministic scorers, replay of recorded responses as a verify gate, and a live run capped by config.
id: evals-readme
created: 2026-06-17
updated: 2026-10-22
visibility: internal
canonical: true
---

# Evals

The eval harness — typed JSONL cases, deterministic scorers, replay of recorded responses as a verify gate, and a live run capped by config.

A unit test asserts that code does what it was written to do. An eval asserts
that an **answer is good enough**: it judges an actual model response against a
rule, and gates on how many cases pass. `tests/` is for the first; this
directory is for the second.

`make eval` replays every case: it runs the case's real doer (the code that
builds the prompt) against a backend that answers with the response recorded
in the case, hashes the prompt the code sends today, and scores the recorded
answer. It makes no model call and needs no credential, so it runs in
`make verify` and in CI. `make eval-live` sends the same cases to the model
config/project.json `evals.live.model` names, under a call cap that defaults
to 0. `README_run.md` is the how-to.

## What ships here

| Member | Purpose | Not for |
|--------|---------|---------|
| `README_run.md` | The how-to: running replay and live, reading the report, authoring a case and its two hashes, promoting a live candidate, the exit codes | The design and its reasons — this README; the settings' defaults — `docs/reference/settings.md` |
| `_config.py` | `load_config`/`parse_config`: the config/project.json `evals` block as a frozen `EvalConfig`, each fault a `ConfigError` naming its dotted key; reads each schema's version from its `schema_version` const | Reading a dataset — `_dataset.py`; choosing or building a model — `models/` (`get_model`), which `_run.py` calls with the configured name |
| `_dataset.py` | `parse_cases`/`load_suites`: one suite per `.jsonl` file, every line held to `config/evals/eval-case.schema.json` plus the rules a schema cannot state (a repeated JSON key, a response hash that does not match, a repeated id); every fault a `DatasetError` naming `path:line` | Judging an answer — `_scorers.py`; running a doer — `_run.py` |
| `_doers.py` | `DOERS`, the closed registry of code paths a case drives (`prompt`, `triage`, and one per other agent named after its package, whose case text is a JSON object holding exactly that agent's model-step inputs), and `prompt_sha256`, which runs a doer against a capturing backend so a prompt hash always comes from the code | A model backend — `models/`; the agent's reasoning — the agent package under `agents/`, whose step a doer calls and never copies |
| `_report.py` | `verdict` (the threshold rule), `aggregate`, the `Report` shape and `render` (canonical JSON); `OUTCOMES`, `REASONS` and `RESULTS`, the closed vocabularies `config/evals/eval-report.schema.json` is held equal to | Writing the file — `scripts/run_evals.py`; scoring one case — `_scorers.py` |
| `_run.py` | `replay` and `run_live`: drive each case's doer through a recording backend or the counted live one, mark a changed prompt stale, refuse a null model or an over-cap run before any backend is built, stop at an absent backend | Judging rules — `_scorers.py` and `_report.py`; the command line and the files — `scripts/run_evals.py` |
| `_scorers.py` | `SCORERS`, the closed registry of deterministic judges (`exact`, `contains`, `regex`, `json_fields`), each refusing bad parameters when the dataset loads | Judging with a model (LLM-as-judge) — not built; a scorer added here also needs its branch in the case schema's `scorer.oneOf` |
| `datasets/` | The suites: one `<suite>.jsonl` per suite, one canonical case per line; `example.jsonl` ships four authored cases covering every scorer and the `prompt` and `triage` doers, and one suite per other agent (`doc-reviewer`, `index-enforcer`, `practice-refactor`, `wiki-navigator`) ships two authored cases, each holding a known-good response; `tests/integration/test_evals_gate.py` fails an agent with no doer or no case, and a case whose scorer passes an empty answer | Run reports or live candidates — those go under config/project.json `evals.report_dir`, which git ignores; fixtures for unit tests — `tests/` |

## Why it is built this way

- **JSONL, one canonical case per line.** Keys sorted, compact separators, so a
  re-recorded case diffs as one line and review sees exactly what changed.
- **A closed scorer vocabulary.** A case names a scorer from `SCORERS`, and the
  case schema has one branch per scorer, held equal by
  `tests/integration/test_evals_schema.py`. A typo in a scorer name or a
  parameter refuses the dataset; it never scores as zero.
- **The threshold rule.** A suite passes when `passed / total >= threshold`,
  compared as exact fractions, so a score equal to the threshold passes
  (config/project.json `evals.threshold`, default `1.0`: every case must pass).
  A case that errored or whose prompt went stale fails its suite whatever the
  score, because a stale recording was judged against a prompt the code no
  longer sends.
- **Replay by default, live on request.** Replay is deterministic and free, so
  it can gate every commit. Live costs money, so it is a separate `[read,cost]`
  target, its cap (`evals.live.max_calls`, default `0`) is checked before any
  call, and it only proposes candidates; a person promotes one into the dataset
  by hand.
- **Absent, failed and refused stay distinct.** A backend that cannot run here
  is `absent` (exit 11, `BACKEND_ABSENT`); an answer that does not pass is `fail` (exit 1); input
  the harness cannot judge, such as bad config, a malformed dataset or an
  over-cap run, is `refused` (exit 2). Zero cases is refused, never a pass.
- **The report is per run.** `<evals.report_dir>/<mode>.json` is replaced whole
  each run and holds no clock or host. The dataset in git is the history.

Judging with a model (LLM-as-judge) is the queued follow-up; every scorer that
ships is deterministic.
