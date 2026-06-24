"""
title: AAD descriptor (Aion Agent Discovery wire format)
layer: backend
public_api: yes
summary: AAD-specific wire model + renderer that serializes a neutral AgentCard to an AAD descriptor.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # the neutral contract this dialect serializes (no runtime dep)
    from backend.agent_surface import AgentCard

__all__ = ["AadDescriptor", "card_to_aad", "AAD_VERSION"]

# Wire-format version, MAJOR.MINOR. MINOR is additive-only (a reader that knows
# an older minor ignores unknown fields); MAJOR is breaking. Never mutate a
# shipped field — only add (minor) or open a new major. See docs/adr.
AAD_VERSION = "1.0"


class _Aad(BaseModel):
    """Base for every AAD model.

    ``extra="ignore"`` is the forward-compatibility rule: a reader that knows
    only an older AAD minor silently drops fields a newer minor added, instead
    of erroring on them.
    """

    model_config = ConfigDict(extra="ignore")


class AadProtocol(str, Enum):
    """Wire protocols an external agent may declare (no ``function`` — that is
    an in-process transport, not something discovered over a URL)."""

    OPENAPI = "openapi"
    MCP = "mcp"


class AadAuthKind(str, Enum):
    """How the consumer must authenticate. ``none`` is DEV-ONLY."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"


class AadIo(_Aad):
    """Which response field carries which part of the answer — the semantics
    OpenAPI omits."""

    question: str = "question"
    answer: str = "answer"
    meta: str | None = None
    html: str | None = None
    error: str | None = None


class AadOperation(_Aad):
    """Binds a logical role (ask/stream) to an OpenAPI operation + its io map."""

    operationId: str | None = None  # noqa: N815 — mirrors the OpenAPI field name
    path: str | None = None
    method: str | None = None
    sse: bool = False
    io: AadIo = Field(default_factory=AadIo)


class AadOpenApi(_Aad):
    """OpenAPI transport binding: where the spec is and which ops to resolve."""

    spec_url: str = "/openapi.json"
    operations: dict[str, AadOperation] = Field(default_factory=dict)


class AadMcp(_Aad):
    """MCP transport binding (alternative to OpenAPI)."""

    endpoint: str
    tool: str = "ask"


class AadAuth(_Aad):
    """Declares *that* auth is needed; never the secret (that stays consumer-side)."""

    kind: AadAuthKind = AadAuthKind.NONE
    header: str | None = None


class AadTransport(_Aad):
    """How to call the agent: the protocol + its binding + auth declaration."""

    protocol: AadProtocol
    openapi: AadOpenApi | None = None
    mcp: AadMcp | None = None
    auth: AadAuth = Field(default_factory=AadAuth)


class AadHealth(_Aad):
    """Liveness endpoint the consumer may poll."""

    path: str | None = None
    method: str = "GET"


class AadCapability(_Aad):
    """A slash command the agent exposes (rendered on its card)."""

    command: str
    title: str
    arg_hint: str | None = None
    maps_to: str | None = None
    passthrough: str | None = None


class AadIcon(_Aad):
    """Presentation-only monogram/gradient for the agent card."""

    kind: str = "monogram"
    text: str = "AI"
    gradient: list[str] = Field(default_factory=lambda: ["#a8c400", "#40c878"])


class AadAgent(_Aad):
    """The card half of the descriptor — display metadata for the agents UI."""

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    name: str
    kind: str
    tagline: str = ""
    description: str = ""
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    icon: AadIcon = Field(default_factory=AadIcon)
    capabilities: list[AadCapability] = Field(default_factory=list)
    example_prompts: list[str] = Field(default_factory=list)


class AadDescriptor(_Aad):
    """The document an agent serves at ``/.well-known/aion-agent.json`` (AAD v1).

    This is the AAD *dialect* of the neutral agent surface — the version
    envelope, transport binding, and well-known path live here, never in the
    neutral ``AgentCard``. ``AadDescriptor.model_json_schema()`` is the single
    source of truth the committed JSON Schema is generated from.
    """

    aad_version: str
    agent: AadAgent
    transport: AadTransport
    health: AadHealth | None = None


def card_to_aad(card: AgentCard, *, ask_operation_id: str = "ask",
                spec_url: str = "/openapi.json", health_path: str = "/health",
                auth_kind: str = "none") -> dict:
    """Render a neutral ``AgentCard`` into an AAD v1 descriptor dict.

    Every AAD-specific shape — the ``aad_version`` envelope, the OpenAPI
    transport binding, the ``io`` field map, the health pointer — is produced
    HERE. The neutral card knows none of it, which is what lets a second
    dialect (A2A, a plugin manifest) be a sibling renderer, not a rewrite.
    ``auth_kind="none"`` is a DEV default; production must declare real auth.
    """
    capabilities = []
    for c in card.capabilities:
        cap = {"command": c.command, "title": c.title,
               "maps_to": "ask", "passthrough": "rawArgs"}
        if c.arg_hint:
            cap["arg_hint"] = c.arg_hint
        capabilities.append(cap)
    kind = card.kind.value if hasattr(card.kind, "value") else str(card.kind)
    payload = {
        "aad_version": AAD_VERSION,
        "agent": {
            "slug": card.slug,
            "name": card.name,
            "kind": kind,
            "tagline": card.tagline,
            "description": card.description,
            "owner": card.owner,
            "tags": list(card.tags),
            "capabilities": capabilities,
            "example_prompts": list(card.example_prompts),
        },
        "transport": {
            "protocol": "openapi",
            "openapi": {
                "spec_url": spec_url,
                "operations": {
                    "ask": {
                        "operationId": ask_operation_id,
                        "io": {"question": "question", "answer": "answer",
                               "meta": "meta", "html": "html", "error": "error"},
                    },
                },
            },
            "auth": {"kind": auth_kind},
        },
        "health": {"path": health_path, "method": "GET"},
    }
    # Fail EARLY (at router build / import) on a malformed descriptor — e.g. an
    # author slug that breaks AadAgent's pattern — instead of serving a
    # non-conformant document. Validate against the model that is the schema's
    # source of truth, but return the literal dict so the served wire shape is
    # exactly what we control here (no default-field expansion).
    AadDescriptor.model_validate(payload)
    return payload
