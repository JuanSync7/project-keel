---
title: ADR-0001: Record architecture decisions
kind: adr
layer: n/a
status: accepted
owner: TBD
summary: We will record architecturally significant decisions as ADRs.
id: docs-adr-0001-record-architecture-decisions
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---
# ADR-0001: Record architecture decisions

**Status:** accepted

## Context
Architecturally significant decisions get lost in chat and commits.

## Decision
Record each as a numbered, immutable ADR in `docs/adr/`. Supersede
rather than edit.

## Consequences
A durable, reviewable decision log. New ADRs reference the ones they
supersede.
