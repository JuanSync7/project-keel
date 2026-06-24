"""
title: Showcase corpus queries
layer: backend
public_api: no
summary: Pure, disk-free navigation and search over an in-memory corpus dict.
"""
from __future__ import annotations

import re

from ._models import DocGroup, NodeDetail, NodeRef, SearchHit

_ACRONYM_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,})\b")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,}")


def _ref(node: dict) -> NodeRef:
    return NodeRef(
        node_id=node.get("node_id", ""),
        kind=node.get("kind", ""),
        title=node.get("title", ""),
        path=node.get("path", ""),
        summary=node.get("summary", ""),
    )


def _index(corpus: dict) -> dict:
    """node_id -> node, for O(1) neighbour resolution."""
    return {n["node_id"]: n for n in corpus.get("nodes", [])}


def count_kinds(corpus: dict) -> dict:
    """Return {kind: count} across the corpus (doc/section/module/symbol)."""
    out: dict = {}
    for n in corpus.get("nodes", []):
        out[n.get("kind", "")] = out.get(n.get("kind", ""), 0) + 1
    return out


def doc_tree(corpus: dict) -> tuple[DocGroup, ...]:
    """Group `doc` nodes by their top-level directory, for the wiki sidebar."""
    groups: dict = {}
    for n in corpus.get("nodes", []):
        if n.get("kind") != "doc":
            continue
        path = n.get("path", "") or ""
        top = path.split("/")[0] if "/" in path else "."   # root-level docs -> "."
        groups.setdefault(top, []).append(_ref(n))
    out = []
    for directory in sorted(groups):
        docs = tuple(sorted(groups[directory], key=lambda r: r.path))
        out.append(DocGroup(directory=directory, docs=docs))
    return tuple(out)


def node_detail(corpus: dict, node_id: str) -> NodeDetail | None:
    """Resolve a node plus its parent, children, and keyword-linked neighbours."""
    idx = _index(corpus)
    n = idx.get(node_id)
    if n is None:
        return None
    parent_id = n.get("parent")
    parent = _ref(idx[parent_id]) if parent_id and parent_id in idx else None
    children = tuple(_ref(idx[c]) for c in n.get("children", []) if c in idx)
    related = tuple(
        _ref(idx[ln["to"]])
        for ln in n.get("links", []) or []
        if isinstance(ln, dict) and ln.get("to") in idx
    )
    return NodeDetail(
        node_id=n.get("node_id", ""),
        kind=n.get("kind", ""),
        title=n.get("title", ""),
        path=n.get("path", ""),
        summary=n.get("summary", ""),
        excerpt=n.get("text_excerpt", ""),
        owner=n.get("owner", ""),
        tags=tuple(n.get("tags", []) or ()),
        anchor=n.get("anchor") or "",
        lineno=n.get("lineno") or 0,
        parent=parent,
        children=children,
        related=related,
    )


def _tokens(text: str) -> set:
    toks = set(_ACRONYM_RE.findall(text or ""))
    toks |= {w.lower() for w in _WORD_RE.findall((text or "").lower())}
    return toks


def search(corpus: dict, query: str, limit: int = 10) -> tuple[SearchHit, ...]:
    """Rank nodes by token overlap of the query against tags/title/summary."""
    q = _tokens(query)
    if not q:
        return ()
    hits = []
    for n in corpus.get("nodes", []):
        hay = set(t.lower() for t in n.get("tags", []) or [])
        hay |= _tokens(n.get("title", ""))
        hay |= _tokens(n.get("summary", ""))
        overlap = q & hay
        if not overlap:
            continue
        score = len(overlap) / float(len(q))
        hits.append(SearchHit(node=_ref(n), score=round(score, 4)))
    # strongest first, then stable by node_id
    hits.sort(key=lambda h: (-h.score, h.node.node_id))
    return tuple(hits[:limit])


__all__ = ["count_kinds", "doc_tree", "node_detail", "search"]
