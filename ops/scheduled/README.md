---
title: Scheduled triggers
kind: ops
layer: n/a
status: template
owner: TBD
public_api: none
tags: [scheduled, cron, triggers, automation]
summary: Thin schedule adapters — when to fire a job. The job itself lives in scripts/jobs/.
id: ops-scheduled-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Scheduled triggers

Thin schedule adapters — when to fire a job. The job itself lives in scripts/jobs/.

The **when**, not the **what**. Each file here is a thin,
vendor-specific adapter that records a cadence ("trigger in 2 days",
"02:00 daily") and points at a doer in `scripts/jobs/`. No application
logic lives here. Pick whichever scheduler your environment uses
(cron / systemd timers / CI cron / a cloud routine) — the doer never
changes; a second scheduler is a new thin file, not a forked job.
