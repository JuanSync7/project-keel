---
title: Specs
kind: doc
layer: n/a
status: template
owner: TBD
summary: Requirements and their numbered acceptance criteria, written in the grammar `make trace` reads so each one is named by a test or excused as a documented gap in config/project.json `traceability.gaps`.
id: docs-specs-readme
created: 2026-06-17
updated: 2026-10-11
visibility: internal
canonical: true
---

# Specs

Requirements and their numbered acceptance criteria. `make trace`
(`scripts/trace_requirements.py`) reads every document here whose frontmatter
says `kind: spec` and judges each requirement against the tests that name it.
A document of another kind, this one included, defines no requirement. One
that would define a requirement if it were read as a spec is refused (exit 2)
and never skipped, so a requirement cannot go untraced under the wrong `kind`;
an example in such a document goes in a fenced block, as below.
[`example-feature.md`](example-feature.md) is a spec written this way.

Deleting `example-feature.md` takes three more edits before `make verify` is
green again. Delete the tests that name its ids, or `make trace` reports each
marker as `marker-undefined-id`. Delete the link to it in the paragraph above,
which check_P fails once its target is gone. Until the first requirement of
your own is written, set config/project.json `traceability.no_requirements` to
the reason, or `make trace` reports `no-requirements`.

This directory is not for design rationale (`docs/design/`) or decisions
(`docs/adr/`).

## How a requirement is written

A requirement is a heading whose first word is an id:

```markdown
## REQ-0001 A thing is made from a name and a value

- AC-1: `do_thing(name, value)` returns a `Thing` that holds that name and that value.
- AC-2: `do_thing(name)` with no value returns a `Thing` whose value is zero.
```

- **The id** is a prefix followed by a fixed count of ASCII digits. config/project.json
  `traceability.id_prefixes` lists each prefix with its `digits`; the shipped
  row is `REQ-` with `4`, so `REQ-0001` parses and `REQ-1` does not.
- **The longest listed prefix wins, with no fallback.** With `REQ-` and
  `REQ-SELF-` both listed, `REQ-SELF-0001` is read under `REQ-SELF-` only.
- **A criterion** is a line `- AC-<n>: <text>` at the left margin, below its
  requirement's heading and above the next heading of the same or a higher
  level. `<n>` is a positive number with no leading zero.
- **A criterion's id** is the requirement's id, then `#AC-<n>`: `REQ-0001#AC-2`.
- **A fenced block defines nothing**, so the example above is not a requirement.

`scripts/trace_requirements.py` exits 2, naming the file and line, for
anything written like an id or a criterion that does not parse, so a
requirement meant is never a requirement silently dropped:

- **An id that does not parse.** A heading that opens with an unlisted prefix
  followed by a digit (`FOO-0001`), or with a wrong digit count.
- **An id a heading does not open with.** A heading that names a requirement
  id anywhere but its first word (`## Requirement REQ-0001`, `## 3. REQ-0001`),
  or wraps it in Markdown (`## **REQ-0001**`, `` ## `REQ-0001` ``,
  `## [REQ-0001]`). A heading that opens with an id of its own may name others.
- **An id on a heading of another form.** A heading indented by one to three
  spaces, or written as a line of text with `===` or `---` under it.
- **A criterion written as any other list item.** A list item that opens with
  `AC-` and is not exactly `- AC-<n>: <text>` at the left margin: an indented
  one, `*` or `+`, two spaces or a tab after the `-`, `1. AC-1:`,
  `- [ ] AC-1:`, `- **AC-1**:`, `> - AC-1:`.
- **A fenced block that is never closed.** Everything below it is code, so the
  line of the fence is named.
- **A misplaced or repeated definition.** A criterion above any requirement, a
  requirement heading inside another requirement's section, and an id or a
  criterion defined twice.

A table row or a paragraph that names an id defines nothing and is not refused.

A row of `traceability.id_prefixes` also carries a `family` and a `source`.
A heading under a `goal` prefix is read and never traced. A prefix whose
`source` is `spine` has its ids defined by another system, so a spec here that
defines one is refused (exit 2).

## What a test must do

A test names what it is evidence for with the marker config/project.json
`traceability.marker` (`req`) names, as string literals:

```python
@pytest.mark.req("REQ-0001#AC-1")
def test_do_thing_returns_thing(): ...
```

Each unit gets one verdict. A unit is a numbered criterion, or a requirement
that has no criteria.

| Verdict | When |
| --- | --- |
| `covered` | a marker on a test pytest collects names the unit's id exactly; a test in a directory pytest's `norecursedirs` skips, a definition a later one of the same name replaces, and a class pytest refuses (it defines `__init__` or `__new__`, or sets `__test__` false) are not collected |
| `gap` | no test names it, and `traceability.gaps` maps its id to a reason |
| `uncovered` | neither; `make trace` exits 1 and names it |

**A bare requirement id never covers a requirement that has numbered
criteria.** `@pytest.mark.req("REQ-0001")` covers nothing above: each of
`REQ-0001#AC-1` and `REQ-0001#AC-2` needs a test of its own or a gap row. The
matrix lists such a test under `whole_requirement_tests`.

`make trace` reads markers from source and imports no test, so it says a test
names a requirement, not that the test proves it; review holds that.
[`docs/guides/dev-loops.md`](../guides/dev-loops.md) gives the loop, and
[`docs/guides/limits-and-troubleshooting.md`](../guides/limits-and-troubleshooting.md)
gives each failure and its fix.
