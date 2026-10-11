---
title: Running evals
kind: eval
layer: n/a
status: template
owner: TBD
summary: How to replay the eval suites, run them live under the call cap, read the report, author a case with its hashes, and promote a live answer into the dataset.
id: evals-readme-run
created: 2026-06-17
updated: 2026-10-11
visibility: internal
canonical: true
---

# Running evals

`README.md` in this directory says what the harness is and why. This page is
the how-to. Every setting named here is a config/project.json `evals` key;
`docs/reference/settings.md` lists each one with its default.

## Replay: `make eval`

```sh
make eval            # scripts/run_evals.py --mode replay
```

It reads every `.jsonl` file in `evals.dataset_dir` (`evals/datasets`), runs
each case's doer against its recorded response, and writes the report to
`<evals.report_dir>/replay.json` (`.evidence/evals/replay.json`). It makes no
model call and reads no credential. `make verify` runs it after `test`.

It refuses to run (exit 2) when `evals.report_dir` is a path git does not
ignore, because a report there would dirty the tree.

## Reading the report

The report follows `config/evals/eval-report.schema.json`.

- `result` is `pass`, `fail`, `absent` or `refused`. A report whose result is
  `incomplete` was left by a run that crashed. A run that refuses the
  config/project.json `evals` block writes no report and deletes the earlier
  one, so a missing report after exit 2 is that refusal; the message names the
  key.
- `reasons` says why, from a closed list: `below-threshold`, `case-error`,
  `stale-recording`, `backend-absent`, `cap-exceeded`, `refused`, `incomplete`.
- `suites[].cases[]` gives each case's `outcome` and a one-line `detail`.

A `stale` outcome means the code now sends a different prompt than the one the
response was recorded for. Its detail names the new prompt hash.

## Authoring a case

One line per case, keys sorted, no spaces after separators:

```json
{"id":"my-case","input":{"doer":"prompt","text":"Reply ACK."},"recorded":{"model":null,"prompt_sha256":"sha256:…","response":"ACK","sha256":"sha256:…","source":"authored"},"schema_version":1,"scorer":{"name":"exact","params":{"expected":"ACK"}}}
```

Compute both hashes with the library, never by hand:

```sh
PYTHONPATH=. python -c 'from evals import prompt_sha256, sha256_text; print(prompt_sha256("prompt", "Reply ACK.")); print(sha256_text("ACK"))'
```

`prompt_sha256` runs the real doer, so the hash matches what replay will send.
Alternatively, write the case with any valid hash, run `make eval`, and copy
the new hash from the stale case's detail.

## Live: `make eval-live`

```sh
make eval-live       # scripts/run_evals.py --mode live
```

Before the first live run, set three keys:

1. `evals.live.model`: a name from `models.list_models()` (default `null`, which
   refuses the run).
2. `evals.live.model_options`: keyword arguments for that adapter, such as
   `base_url` and `model` for `openai-compatible`. These options choose where
   the adapter's credential is sent, so `openai-compatible` refuses (exit 2,
   before any call) an `api_key_env` that config/project.json
   `models.credential_env.openai-compatible` does not list, and a `base_url`
   that is not an http or https URL with a host and no user part. Anyone who
   can edit `config/project.json` can still point `base_url` at a host of
   their choosing and receive the declared key: review a change to this block
   as you would a change to a credential.
3. `evals.live.max_calls`: at least the number of cases. The default is `0`,
   which approves no calls. The cap is checked before any call, and a run that
   would exceed it is refused (exit 2).

The cost of one case is unknown in advance: it depends on the model, the
endpoint and the prompt length. The report counts the calls made in `calls`.

A live run deletes `<evals.report_dir>/live-candidates/` and then writes one
candidate line per answered case to
`<evals.report_dir>/live-candidates/<suite>.jsonl`. It never edits the
dataset. A case detail in the report has the value of each variable
`models.credential_env` lists for the model replaced by `<hidden>`; a
candidate line holds the model's response whole, so read it before you share
it.

## Promoting a live answer

1. Copy one line from `.evidence/evals/live-candidates/<suite>.jsonl` over the
   line with the same id in `evals/datasets/<suite>.jsonl`.
2. Review the diff. It is one line, and its `recorded.source` is `model`.
3. Run `make eval`.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Every suite passed |
| 1 | A suite failed: `below-threshold`, `case-error` or `stale-recording` |
| 2 | Refused: bad config, a malformed or empty dataset, the call cap, a null or unknown model, or a `evals.report_dir` git does not ignore |
| 3 | The live backend is absent (live only) |
