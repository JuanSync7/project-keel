---
title: CMP-9 — a test shows it can fail
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-9.
id: docs-internals-campaigns-cmp-9
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-9 — a test shows it can fail

The maintainer asked for KEEL-TESTQ-1 (queue position 12) to open once the
CMP-8 lanes landed, on the split ruled on 2026-10-19. CMP-9 is slices 2 and 3 of
the table in "KEEL-TESTQ-1, the test checks" below, the two that need nothing
from pyverdex; slices 4 and 5 stay queued behind the pyverdex prerequisite.
The cap is three passes, one per slice and a fix round, and the stop point is
CMP-9.S2 green or the cap, whichever comes first.

It is built in one lane from current `main`, the two slices in order, since
both add `test_quality.*` rows to `scripts/config_loader.py` `KEYS`. Each
check is a standard-library port of an existing scanner into `tests/`, written
test-first against today's tree and rewritten to the house pattern (module
header, the config loader, no literal threshold). The sources are the
maintainer's assertion-quality scanner in their tooling repository and
pyverdex's static realness classifier; neither is imported or vendored.

The counts below are those two scanners run unchanged on `main` at `4f256fa`,
not a gate's measurement. The assertion-quality scanner reads 2993 test
functions and flags 38: 31 with no assertion, 3 tautologies, 4 swallowed
exceptions and 1 bare `isinstance`. Of three of the 31 read by hand, two
assert through a helper in the same module (16 of the 31 sit in
`tests/unit/scripts/test_config_text_leaks.py`, which asserts through
`_hides`) and one passes by not raising. All 3 tautologies compare two calls,
a determinism check. So the port resolves a helper the test calls, and a
comparison of two calls is not a tautology. The realness classifier tiers all 14 test functions under
`tests/e2e/` as replacing no dependency.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-9.S1 | A test that asserts nothing, or only a constant or a tautology, passes `make verify`: a gate test reads every test function under the configured roots and fails one with no assertion (counting `pytest.raises` and an assertion in a helper the test calls in the same module or in `tests/`), a constant or tautological assertion, or a handler that swallows the exception it tests; it is shown red on each, keel's own suite is fixed to pass it, an excuse names the test and a reason in `config/project.json`, and it ships through copier | implemented — on main, delivered by 4568628f, 04b7dd63, 759ea212, 3024a978, 483e73e0, f26577ee, 3e28b1cb, a751c035, 227329db; the done-condition is not re-audited |
| CMP-9.S2 | An `e2e` test may replace the dependency it claims to drive: a gate test tiers every test function under the configured `e2e` roots (mock, fake, in-process, real or none, through its decorators, body and the fixtures it requests, autouse and `conftest.py` ones included) and fails one that mocks, naming the test and the signal; it is shown red on a `mocker` fixture, a `patch` decorator and an autouse `monkeypatch` in a `conftest.py`, and it ships through copier | implemented — on main, delivered by c290bb5a; the done-condition is not re-audited |

