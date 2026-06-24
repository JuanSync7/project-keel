"""Integration: the AAD reference agent is conformant and self-consistent.

Runs the reference agent in-process (TestClient), then proves three things
WITHOUT importing any consumer's discovery stack (a template only *serves* a
descriptor — it does not fetch others'):

  1. the served descriptor validates against the committed JSON Schema
     (`config/agent_surface/aad-v1.0.schema.json`, generated from the model);
  2. the descriptor's `ask` operationId resolves against the agent's OWN
     FastAPI-generated `/openapi.json` (a tiny vendored resolver, ~12 lines);
  3. the resolved endpoint actually answers, with the field names the
     descriptor's `io` map declared.
"""
import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from demo.aad_reference_agent import DESCRIPTOR, app  # noqa: E402

pytestmark = pytest.mark.integration

_SCHEMA_PATH = _ROOT / "config" / "agent_surface" / "aad-v1.0.schema.json"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def served_descriptor(client: TestClient) -> dict:
    r = client.get("/.well-known/aion-agent.json")
    assert r.status_code == 200
    return r.json()


def _resolve_ask(descriptor: dict, openapi: dict) -> tuple:
    """Vendored resolver: descriptor.ask.operationId -> (METHOD, path) in the
    agent's own OpenAPI. Decoupled from any platform's discover()."""
    op_id = descriptor["transport"]["openapi"]["operations"]["ask"]["operationId"]
    for path, methods in openapi["paths"].items():
        for method, op in methods.items():
            if op.get("operationId") == op_id:
                return method.upper(), path
    raise AssertionError("ask operationId %r not in /openapi.json" % op_id)


def test_served_descriptor_matches_exported(served_descriptor: dict):
    """What the agent serves is exactly the DESCRIPTOR it exports."""
    assert served_descriptor == DESCRIPTOR


def test_descriptor_structural(served_descriptor: dict):
    """Always-on sanity (no jsonschema dep): required keys, version, slug shape."""
    for key in ("aad_version", "agent", "transport"):
        assert key in served_descriptor, "missing required key %r" % key
    assert served_descriptor["aad_version"] == "1.0"
    assert _SLUG_RE.match(served_descriptor["agent"]["slug"])
    assert served_descriptor["transport"]["protocol"] in ("openapi", "mcp")


def test_descriptor_validates_against_committed_schema(served_descriptor: dict):
    """The descriptor conforms to the committed, generated JSON Schema."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(served_descriptor, schema)


def test_dotless_fallback_is_served(client: TestClient):
    """Servers that can't serve a dot-directory get the `/aion-agent.json` fallback."""
    assert client.get("/aion-agent.json").status_code == 200


def test_ask_binding_resolves_and_answers(client: TestClient, served_descriptor: dict):
    """The ask operationId resolves in the agent's own OpenAPI and the endpoint answers."""
    method, path = _resolve_ask(served_descriptor, app.openapi())
    assert method == "POST"
    io = served_descriptor["transport"]["openapi"]["operations"]["ask"]["io"]
    r = client.request(method, path, json={io["question"]: "ping"})
    assert r.status_code == 200
    body = r.json()
    assert io["answer"] in body
    assert "ping" in body[io["answer"]]


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_malformed_slug_is_rejected_at_render():
    """An author-supplied slug that breaks the AAD pattern fails fast at render,
    rather than being served as a non-conformant descriptor."""
    import pydantic

    from aad import card_to_aad  # api/rest_fastapi is on sys.path via the demo import
    from backend.agent_surface import AgentCard

    with pytest.raises(pydantic.ValidationError):
        card_to_aad(AgentCard(slug="INVALID_SLUG", name="x"))
