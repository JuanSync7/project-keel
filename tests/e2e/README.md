---
title: E2E tests
kind: tests
layer: n/a
status: template
owner: TBD
summary: Full-system user journeys end to end.
id: tests-e2e-readme
created: 2026-06-17
updated: 2026-10-11
visibility: internal
canonical: true
---

# E2E tests

Full-system user journeys end to end. Do **not** mirror source files — one file per scenario.

## Naming the endpoint a scenario drives

`tests/integration/test_e2e_coverage.py` fails when an endpoint an enabled
transport serves is named by no scenario here. A scenario names each endpoint
it drives with the marker `config/project.json` `e2e.marker` names, its one
argument a string literal `"<transport> <id>"`:

| Transport | Id | Example |
|-----------|----|---------|
| `rest` | an upper-case method, a space, the OpenAPI path | `@pytest.mark.endpoint("rest GET /health")` |
| `mcp` | the server's name, a slash, the tool | `@pytest.mark.endpoint("mcp keel-wiki-qa/wiki_answer")` |
| `grpc` | `/<package>.<Service>/<Rpc>` | `@pytest.mark.endpoint("grpc /thing.v1.ThingService/CreateThing")` |

A marker the gate cannot read (a name argument, an f-string, a lower-case
method, trailing space, no argument, a file outside this directory) is red, not
ignored. So is a marker that applies to no test pytest collects: put it on a
test function or test class, or in a module- or class-level `pytestmark`, not
on a helper, a nested function, a `pytest.param`, or under an `if`.

## Fixtures

`conftest.py` gives a scenario the real transport, never an in-process client:

- `rest_server` starts the REST app under uvicorn on a loopback port the OS
  picks, once per session, and stops its process group on the way out, a
  failing scenario and a SIGTERM or SIGHUP to the test run included. `.request(method, path, body)` returns the status,
  the headers and the body; `.json(...)` returns the status and the parsed
  body. It skips, naming the `transport` extra, without uvicorn or FastAPI.
- `mcp_session` returns a callable that starts one MCP server, writes JSON-RPC
  messages to its stdio and returns its replies, with `e2e.mcp_env` added to
  its environment and `e2e.list_timeout_s` bounding it.

## Exemptions

An endpoint no scenario can reach yet goes in `config/project.json`
`e2e.exempt`, mapped to the reason. An entry that names no endpoint, one a
scenario already names, or one whose reason is blank is red. The gate checks
that a scenario names each endpoint, not what it asserts: assert on what the
caller sees.
