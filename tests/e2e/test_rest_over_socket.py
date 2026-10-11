"""
title: E2E — the core REST routes answer over a real socket
kind: tests
layer: n/a
summary: A client drives the REST transport's own routes - the health probe and creating a thing - over HTTP against the real server process, not an in-process client. These routes ship in every project, so this scenario survives the showcase prune.
"""

import pytest

pytestmark = [pytest.mark.e2e]


@pytest.mark.endpoint("rest GET /health")
def test_health_answers_over_a_real_socket(rest_server):
    status, body = rest_server.json("GET", "/health")
    assert status == 200
    assert body == {"status": "ok"}


@pytest.mark.endpoint("rest POST /things")
def test_creating_a_thing_returns_it_and_a_bad_body_is_422(rest_server):
    status, body = rest_server.json("POST", "/things", {"name": "n", "value": 3})
    assert (status, body) == (200, {"name": "n", "value": 3})

    status, body = rest_server.json("POST", "/things", {"name": "n"})
    assert (status, body) == (200, {"name": "n", "value": 0})

    status, body = rest_server.json("POST", "/things", {"value": "x"})
    assert status == 422, body
