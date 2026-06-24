---
title: Test docs
kind: test-doc
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: Test plans, coverage register, and overall test strategy.
id: test-docs-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Test docs

Test plans, coverage register, and overall test strategy.

Planning *about* tests (the tests themselves live in `tests/`).

- `strategy.md` — what we test, at which level, and why.
- `test-plan/` — one plan per module/feature (loosely mirrors
  `tests/`, not `src/` file-for-file).
- `coverage/` — a living register mapping acceptance criteria →
  scenarios → covered/not.
