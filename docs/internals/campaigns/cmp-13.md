---
title: CMP-13 — a test gate credits only an assertion that runs, and reads its policy through the loader
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-13.
id: docs-internals-campaigns-cmp-13
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-13 — a test gate credits only an assertion that runs, and reads its policy through the loader

KEEL-TESTQ-2 and KEEL-SRCTREE-CFG-1 came out of the CMP-9.S1 reviews after its
cap. Both are gaps in the test gates CMP-9 shipped, and both waited on
keel-cmp9 landing, because each owns a file that lane changed. The cap is one
pass per slice, with at most three review fix rounds each; the stop point is
CMP-13.S2 green or the cap.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-13.S1 | KEEL-TESTQ-2: `tests/assertion_quality.py` counts a call inside a generator expression whose body never runs, and judges a TestCase receiver by its spelling. A generator expression runs its first iterable when it is built and the rest (its element, its conditions and its later iterables) only when it is consumed. It is consumed when it is the iterable of a `for` statement or of a list, set or dict comprehension that runs, the operand of a `*` or a `yield from`, or the iterable of another generator expression that is itself consumed; or when it is an argument of a call to a bare name that config/project.json `test_quality.assertions.consumers` lists and the scope does not rebind, in the position that entry names: `only` (the call's sole argument) or `first` (its first positional argument, for a callee that iterates it whatever its other positional arguments are), in a call that passes no keyword argument and unpacks nothing with `*` or `**`. A name bound to it by exactly one binding in the scope and consumed in one of those places counts the same. A call in the deferred part of a generator expression nothing consumes counts as nothing: not an assertion, an expectation or a helper call. In a TestCase class, a receiver is the test case when it is the first positional parameter, whatever its spelling, of a function defined directly in the class body that carries no `staticmethod` or `classmethod` decorator, the parameter has no default, and nothing else in the scope binds that name; or a name with exactly one binding in the scope, which assigns it such a receiver (`=` or `:=`) or iterates a tuple or list display of such receivers (a `for` statement or a comprehension target). A name with any other binding, or with more than one, is no receiver: an assignment of something else, a `for` or comprehension over anything but such a display, `with ... as`, `except ... as`, an import or a parameter | implemented — on main, delivered by 73949273, 8991e2e8; the done-condition is not re-audited |
| CMP-13.S2 | KEEL-SRCTREE-CFG-1: `tests/integration/test_config_reads_gate.py` walks no module under `tests/`, so five gate helpers there open `config/project.json` themselves (`tests/source_tree.py` `import_layers`, `tests/selection_guard.py`, `tests/hermetic_git.py`, `tests/live_server.py` and `tests/ci_adapters.py`, six reads). The gate walks the helper modules directly under `tests/`, every Python file there but `conftest.py` and `test_*.py`, named by a configured key. Each of the six reads goes through `scripts/config_loader.py` `read(root)` and `resolve` against a `KEYS` row for the block it reads; each helper keeps its own validation and raises its own named error when the loader refuses | implemented — on main, delivered by 1e4092b0; the done-condition is not re-audited |

CMP-13.S1 owns `tests/assertion_quality.py` and its `summary:`,
`tests/unit/test_assertion_quality.py`, the `test_quality` block of
`config/project.json` and `config/project.json.jinja` (the `consumers` key and
the `_comment` sentence for it), its `scripts/config_loader.py` `KEYS` row,
whose default maps `all`, `any`, `dict`, `frozenset`, `list`, `max`, `min`,
`set`, `sorted`, `sum` and `tuple` to `only` and `next` to `first` (`sum`
refuses a string start before it iterates, so it is not `first`), its
`docs/reference/settings.md` row, the assertion-quality row of
`docs/reference/features.md` (its receiver sentence names `self.` only), the
assertion-quality rows of `docs/guides/deterministic-checks.md` and one
`CHANGELOG.md` row. It works test-first. Each regression case fails on
the base:

- counted on the base and counted as nothing after: an assertion method in a
  generator expression that is a bare statement; one in a generator expression
  bound to a name nothing consumes; one passed to `bool(...)` and to
  `iter(...)`; one passed as `next(it, gen)`, as `dict(saved=gen)` and as
  `max(a, gen)`; one passed as `sum(gen, "")` inside a `try` whose handler
  catches the `TypeError`, as `sum(gen, 0)` and as `max(gen, key=len)`, which
  the slice gives up with the rest of the call shapes it does not judge; one
  that is the iterable of an outer generator expression
  nothing consumes; a helper called in an unconsumed generator expression;
  `[self.assertEqual(...) for self in (dummy,)]`; and `self` rebound by
  `self = other`, `with ... as self` and `except ... as self` before
  `self.assertEqual(...)`; and `self.assertTrue(...)` in a TestCase function
  decorated `@staticmethod` whose `self` parameter has a default;
- not counted on the base and counted after: `case = self` then
  `case.assertEqual(...)`, `(case := self)` then `case.assertTrue(...)`,
  `[c.assertEqual(...) for c in (self,)]`, `for c in (self,):` with
  `c.assertTrue(...)` in its body, and `def test_a(case):` with
  `case.assertTrue(...)` in a TestCase class.

Each control case keeps its verdict on the base and after: the generator
expressions consumed by `all(...)`, by a `for` statement, by `*` and through a
bound name passed to `list(...)`, by `next(gen, None)` and by
`sum(gen)`, and an inner generator expression that a consumed outer one
iterates, counted; an assertion in a generator expression's first iterable,
counted; `case = other`, a display holding
`self` and another name, `case = self` followed by `case = other`, `case =
self` twice, `case.assertTrue(...)` in a `@staticmethod` function whose
`case` parameter has a default, and `cls.assertTrue(...)` in a
`@classmethod` function, not counted. Its acceptance includes the gate's result over keel's own tree before
and after, taken through `tests/assertion_quality.py` `scan` read-only: the
same findings, or the slice names each one that changed and why. A finding the
change adds to keel's own tests is fixed in the test, never excused.

CMP-13.S2 owns the five helpers named in its row,
`tests/integration/test_config_reads_gate.py` (its walk and its `summary:`),
the `config_reads` block of `config/project.json` and
`config/project.json.jinja` (the new key and the `_comment` sentence that says
`tests/` is not walked), a `scripts/config_loader.py` `KEYS` row for the new
key and for each block the six reads take that has none (`import_layers`,
`make_targets`, `e2e`, `ci_pipeline` and `transports.available`, which
`tests/live_server.py` reads for `rest`; `child_env` has a block row and
`toolchain` has one row per key already; a block a helper
refuses when missing has no default; `import_layers.may_end_the_process`
keeps its default of an empty object), `docs/reference/settings.md`,
`tests/README.md`, the config-reads paragraph and its limitation sentence in
`docs/guides/deterministic-checks.md` and one `CHANGELOG.md` row. That
paragraph says a generated project's finding tests skip, and the gate applies
`scripts/expiring_tier.py` instead, so S2 corrects it with the walk.
`tests/ci_adapters.py` gains the type check it lacks and refuses a
`ci_pipeline` that is not an object by name. It works test-first: a gate case
over a scratch copy shows a helper module directly under `tests/` that opens
`config/project.json` red, and a `test_*.py` or `conftest.py` there that does
the same not red. The `allowed` map takes no new entry, and its ceiling does
not rise. A helper the widened walk flags for a write or a read of a scratch
project's file, rather than this project's configuration, is named in the
slice's report before any change to it.

Its acceptance includes how each helper imports the loader where it runs:
`tests/source_tree.py` and `tests/hermetic_git.py` already put `scripts/` on
the path, `tests/selection_guard.py` does so only after its current read, and
`tests/ci_adapters.py` and `tests/live_server.py` do not. Each helper's unit
tests, `tests/selection_guard.py` `declared_empty` called at session end by
`tests/conftest.py`, and the copier render tests pass with the change. A
loader refusal surfaces as the helper's own error (`SourceTreeError`,
`RuntimeError`, `AssertionError`, `LiveServerError`), and a test shows it for
each.

Will not do in CMP-13: walk `test_*.py` files or `conftest.py`, which read and
write config to build fixtures, as the gate's comment states; count a
generator expression handed to a callee off the `consumers` list, or to one
called through an attribute such as `"".join`, as consumed (a project that
consumes through its own function adds the name to the list); judge a
call shape beyond `only` and `first`, a keyword argument or an argument's
value, so `sum(gen, 0)` counts as nothing as `sum(gen, "")` does; or follow a
binding through control flow (two bindings of one name make it no receiver
and no consumed name, whichever runs).

CMP-13's plan commit sits on `keel-cmp12`, because the campaign naming check
refuses a CMP-13 with no CMP-12 before it. That ancestry carries all of
`keel-cmp10` (its plan and its four slices, not yet on main) and the CMP-11
and CMP-12 plans, not their code. Each slice's lane starts from main after CMP-10
lands and is rebased onto main as CMP-11 and CMP-12 land, so its full verify
runs over their code. S1 and S2 share `config/project.json`, its template
twin, `scripts/config_loader.py` and `docs/reference/settings.md`, so S2
starts from S1's commit, not beside it.

