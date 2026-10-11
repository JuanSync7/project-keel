---
title: Example feature — requirements
kind: spec
layer: backend
status: template
owner: TBD
summary: The requirements of src/backend/example_feature, written the way `make trace` reads them. Replace it with your own first spec. Deleting it instead takes the three follow-up edits docs/specs/README.md lists (the tests that name its ids, the link to it, and a `traceability.no_requirements` reason).
id: docs-specs-example-feature
created: 2026-10-11
updated: 2026-10-11
visibility: internal
canonical: true
---

# Example feature — requirements

This spec states what `src/backend/example_feature` must do.
`make trace` reads each heading that opens with an id as one requirement and
each `- AC-<n>: <text>` line below it as one numbered criterion.
[`README.md`](README.md) gives the grammar, the rule a test must meet, and
the three edits that deleting this file needs before `make verify` is green.

## REQ-0001 A thing is made from a name and a value

- AC-1: `do_thing(name, value)` returns a `Thing` that holds that name and that value.
- AC-2: `do_thing(name)` with no value returns a `Thing` whose value is zero.

## REQ-0002 A thing cannot be changed after it is made

Assigning to a field of a `Thing` raises an error and leaves the field as it was.
