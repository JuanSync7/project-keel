---
title: tests — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside tests/.
id: tests-agent
created: 2026-06-17
updated: 2026-10-21
visibility: internal
canonical: true
---

# Agent rules — `tests/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- A new `src/<pkg>/<mod>.py` REQUIRES a mirrored `tests/unit/<pkg>/test_<mod>.py`.
- A new user-facing flow (route, page, or transport endpoint) gets a `tests/e2e/` scenario that drives it through the public surface — author it alongside the change, not later (CONVENTIONS §17). Name each endpoint the scenario drives with `@pytest.mark.endpoint("<transport> <id>")`: `tests/integration/test_e2e_coverage.py` fails an endpoint no scenario names unless `config/project.json` `e2e.exempt` gives the reason.
- A test that is evidence for a requirement names it: `@pytest.mark.req("REQ-0001#AC-1")`, string literals only, on the test function, its class or a `pytestmark` (CONVENTIONS §17). Name each numbered criterion by its own id; the bare requirement id covers only a requirement that has no criteria. Write the marker as `pytest.mark.req(...)`, or `mark.req(...)` after `from pytest import mark`; through any other name `make trace` does not read it. `make trace` (`scripts/trace_requirements.py`) fails a unit no collected test names unless `config/project.json` `traceability.gaps` gives the reason, and fails a marker that names no defined unit.
- A fixture or golden value is an EXAMPLE of the contract, not the contract itself — assert the general behavior across edge/empty/boundary cases and keep golden values in the test or a fixture, so a hardcoded answer in `src/` cannot pass the suite (an answer key in `src/` is the overfit smell `scripts/check_generic.py` flags; CONVENTIONS §18).
- Do NOT mirror integration/e2e/smoke to source files — name them by the scenario under test.
- A test reaches the network, the disk and the stores only as its tier allows. `tests/isolation_guard.py`, installed by `conftest.py` as a Python audit hook, judges each test's setup, call and teardown on three axes, `network`, `writes` and `stores`, against the row of `config/project.json` `tests.isolation.tiers` its closest tier marker names; an unmarked test gets the strictest value on each axis. A reach outside the rule fails the test, named, even when the test catches the error. Write scratch to `tmp_path`; reach a live store `tests.isolation.stores` lists only through the `store_copy` fixture; a reach the test truly needs gets a reason in `tests.isolation.exempt` under its axis and node id, and an exemption whose test reaches nothing on that axis fails the run. A test that needs a wider tier is a different tier of test: move it, do not widen `unit`.
- Test scratch lives under `KEEL_TEST_SCRATCH` when it is set; else `tests.memory_scratch_root` with `-<uid>` appended, when its parent exists, its file system has `tests.memory_scratch_min_free_mb` megabytes free, and the directory is this user's with mode 0700; else `tests.scratch_root`. Memory comes first because scratch needs no durability; pytest's `scratch:` header line, which `-q` hides, names the root in use and why memory was passed over. No root is ever in the system temporary directory or the checkout. A root that holds the checkout is accepted, and the checkout stays outside it. A passed test's directory is removed and a failed one's is kept, named after the test. A test that starts a child process passes `timeout=` the seconds `tests.child_timeout_seconds` names, read through `scripts/config_loader.py`.
- The guard is defence-in-depth, not a sandbox: it does not see a child process, a C extension's own file or socket calls, a FIFO or device node, or the directory an `os.open` with a relative path and a `dir_fd` lands in; it does not judge a name lookup, by choice, because the connect that follows is judged. A sqlite name that starts `file:` is judged as a URI and as a file of that name in the working directory, so a test that opens a `file:` URI changes directory to `tmp_path` first. `docs/guides/dev-loops.md` states the rule; `docs/adr/keel/K-0024-what-a-test-may-reach.md` is the decision.
- Test through the package's public API (`__init__`), not its `_*` internals — tests are callers too.
