---
title: tests — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside tests/.
id: tests-agent
created: 2026-06-17
updated: 2026-10-11
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
- Unit tests touch no network/disk/process. If you need those, it's an integration test.
- Test through the package's public API (`__init__`), not its `_*` internals — tests are callers too.
