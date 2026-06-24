"""
title: Showcase llms.txt rendering
layer: backend
public_api: no
summary: Render the agent-facing llms.txt map and llms-full.txt from the corpus.
"""
from __future__ import annotations

import urllib.parse

from ._models import Overview


def _link(base_url: str, node_id: str) -> str:
    return "%s/wiki?id=%s" % (base_url.rstrip("/"), urllib.parse.quote(node_id, safe=""))


def render_index(overview: Overview, groups, base_url: str = "",
                 tree_url: str = "/api/wiki/tree") -> str:
    """The llms.txt map: H1 + summary + per-directory link lists + an Optional tail.

    Follows the llms.txt convention: a single H1, a blockquote summary, then H2
    sections each holding a markdown link list (``- [title](url): summary``).

    ``tree_url`` is the corpus-graph link (relative to ``base_url``): the live
    endpoint ``/api/wiki/tree`` by default, or ``/api/wiki/tree.json`` for a
    static export, where only the snapshot file exists.
    """
    base = base_url.rstrip("/")
    out = ["# %s" % overview.title, "", "> %s" % overview.tagline, "",
           overview.summary, ""]
    for g in groups:
        heading = "Root" if g.directory == "." else g.directory
        out.append("## %s" % heading)
        for d in g.docs:
            summ = (": %s" % d.summary) if d.summary else ""
            out.append("- [%s](%s)%s" % (d.title, _link(base, d.node_id), summ))
        out.append("")
    out.append("## Optional")
    out.append("- [Full text](%s/llms-full.txt): every document inlined for one-shot ingestion" % base)
    out.append("- [Machine index](%s%s): the corpus graph as JSON" % (base, tree_url))
    out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_full(overview: Overview, docs) -> str:
    """llms-full.txt: every doc's body inlined, for one-shot agent ingestion.

    ``docs`` is an iterable of ``(NodeRef, markdown_body)`` pairs.
    """
    out = ["# %s — full text" % overview.title, "", "> %s" % overview.tagline, "",
           overview.summary, ""]
    for ref, body in docs:
        out.append("---")
        out.append("")
        out.append("## %s" % ref.title)
        out.append("`%s`" % ref.path)
        out.append("")
        out.append((body or "").strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


__all__ = ["render_index", "render_full"]
