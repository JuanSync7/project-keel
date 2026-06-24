---
title: Jobs
kind: script
layer: n/a
status: template
owner: TBD
public_api: none
tags: [jobs, scheduled, automation, triggers]
summary: Time-triggered doers — the scripts a scheduler fires. The schedule lives in ops/.
id: scripts-jobs-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Jobs

Time-triggered doers — the scripts a scheduler fires. The schedule lives in ops/.

Time-triggered **doers**: the scripts that run *on a schedule*. The
script is the doer; the **schedule** is a thin, vendor-specific
adapter in `ops/scheduled/` (cron/systemd/CI/cloud) that records only
*when* to fire it. Deterministic jobs are self-contained here
(`rebuild_index.py`); LLM-backed jobs call an agent in `agents/`.
