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
updated: 2026-06-17
visibility: internal
canonical: true
---

# Config

Committed configuration defaults and examples (no secrets).

Commit runtime defaults (`default.*`, `*.example.*`) and committed governance
manifests (`project.json`, generated `*.schema.json`) — never secrets, which
live in `*.local.*` or `.env` (gitignored). The `app/` layer loads runtime
values from here; the checker reads the manifests (CONVENTIONS §15).
