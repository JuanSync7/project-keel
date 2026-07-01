"""
title: Showcase value objects
layer: backend
public_api: no
summary: Frozen, framework-free value objects describing the template as a product.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Link:
    """A labelled pointer to a repo path or corpus node."""

    label: str
    href: str


@dataclass(frozen=True)
class Layer:
    """One architectural layer (frontend/backend) from config/project.json."""

    name: str
    language: str
    path: str = ""
    stack: str = ""
    available: tuple[str, ...] = ()


@dataclass(frozen=True)
class Transport:
    """One API transport (rest/grpc/mcp/...) and whether it is enabled."""

    name: str
    directory: str
    enabled: bool


@dataclass(frozen=True)
class Stats:
    """Headline counts the overview page renders."""

    docs: int
    modules: int
    sections: int
    symbols: int
    directories: int
    checks: int


@dataclass(frozen=True)
class Overview:
    """The product pitch: identity, layers, transports, and headline counts."""

    name: str
    title: str
    tagline: str
    summary: str
    conventions: tuple[str, ...]
    layers: tuple[Layer, ...]
    transports: tuple[Transport, ...]
    stats: Stats


@dataclass(frozen=True)
class Feature:
    """One product feature for the features page."""

    slug: str
    title: str
    summary: str
    detail: str
    icon: str
    links: tuple[Link, ...] = ()


@dataclass(frozen=True)
class Principle:
    """One governing convention for the conventions page: the rule + how it holds.

    Complements ``Feature`` (what you get) with the rule behind it (why/how),
    each linking out to the exact CONVENTIONS section it summarises.
    """

    slug: str
    title: str
    essence: str   # the rule in one line
    detail: str    # how it works / how it's enforced, 2-3 sentences
    links: tuple[Link, ...] = ()


@dataclass(frozen=True)
class Check:
    """One deterministic check in the catalogue (mirrors the checks guide)."""

    slug: str
    name: str
    script: str
    purpose: str
    gate: str          # error | warn | report
    interpreter: str   # "3.6-safe" | ">=3.7" | "FastAPI" | "pydantic" | "any"
    command: str
    when: str
    present: bool = True   # script exists on disk (honesty flag, set at load)


@dataclass(frozen=True)
class Step:
    """One step in the 'use it in your own project' guide."""

    title: str
    body: str
    command: str = ""


@dataclass(frozen=True)
class NodeRef:
    """A light reference to a corpus node (for trees, neighbours, hits)."""

    node_id: str
    kind: str
    title: str
    path: str
    summary: str = ""


@dataclass(frozen=True)
class DocGroup:
    """Docs under one top-level directory, for the wiki sidebar."""

    directory: str
    docs: tuple[NodeRef, ...]


@dataclass(frozen=True)
class NodeDetail:
    """A corpus node plus its resolved neighbours, for the node page."""

    node_id: str
    kind: str
    title: str
    path: str
    summary: str
    excerpt: str
    owner: str
    tags: tuple[str, ...]
    anchor: str
    lineno: int
    parent: NodeRef | None
    children: tuple[NodeRef, ...]
    related: tuple[NodeRef, ...]


@dataclass(frozen=True)
class SearchHit:
    """A search result: a node reference and its match score."""

    node: NodeRef
    score: float


def to_jsonable(obj: object) -> object:
    """Recursively convert dataclasses/tuples to JSON-ready dict/list structures."""
    from dataclasses import is_dataclass

    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj


__all__ = [
    "Link", "Layer", "Transport", "Stats", "Overview", "Feature", "Principle",
    "Check", "Step", "NodeRef", "DocGroup", "NodeDetail", "SearchHit",
    "to_jsonable",
]
