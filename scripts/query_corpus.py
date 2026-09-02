#!/usr/bin/env python3
"""
title: Query corpus
kind: script
layer: n/a
summary: Read-only retrieval over wiki/corpus.json — the wiki_navigator's tool.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CORPUS = os.path.join("wiki", "corpus.json")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,}")


# Light stemming, longest suffix first: enough that `idempotency` and
# `idempotent`, `sections` and `section`, `linking` and `links` compare equal.
# Deliberately crude (no Porter): the corpus is small, ranking is by overlap
# count, and a false merge costs one extra candidate, not a wrong answer.
_SUFFIXES = (
    "ization",
    "isation",
    "ency",
    "ence",
    "ancy",
    "ance",
    "ent",
    "ant",
    "ies",
    "ing",
    "ed",
    "es",
    "s",
)


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            if suffix == "s" and word.endswith("ss"):
                continue
            return word[: -len(suffix)]
    return word


def _tokens(text: str) -> set:
    out = set()
    for w in _WORD_RE.findall(text or ""):
        out.add(_stem(w.lower()))
        if w.isupper():
            out.add(w)  # keep acronyms (AXI) matchable verbatim
    return out


def query(corpus: dict, question: str, max_nodes: int = 8) -> list:
    """Return up to max_nodes candidate nodes for the question, best first.

    Deterministic retrieval: score each node by stemmed query-token overlap
    with its tags/title/summary (weight 2) and with its body excerpt (weight 1,
    so a body-only match never outranks a summary match), then pull in each
    hit's parent and linked nodes so the caller gets a connected neighbourhood
    (tree + links) to reason over.
    """
    nodes = {n["node_id"]: n for n in corpus.get("nodes", [])}
    q = _tokens(question)
    if not q:
        return []
    scored = []
    for nid, n in nodes.items():
        core = (
            {_stem(t.lower()) for t in n.get("tags", [])}
            | _tokens(n.get("title", ""))
            | _tokens(n.get("summary", ""))
        )
        body = _tokens(n.get("text_excerpt", "")) - core
        overlap = 2 * len(q & core) + len(q & body)
        if overlap:
            scored.append((overlap, nid))
    scored.sort(key=lambda s: (-s[0], s[1]))
    chosen, order = set(), []
    # Pass 1: guarantee every genuine keyword hit (best-first) before any filler.
    for _, nid in scored:
        if len(order) >= max_nodes:
            break
        if nid not in chosen:
            chosen.add(nid)
            order.append(nid)
    # Pass 2: expand the neighbourhood (parent + links) to fill the remainder,
    # so a top hit's zero-overlap neighbours never starve a real lower-ranked hit.
    for _, nid in scored:
        if len(order) >= max_nodes:
            break
        for related in [nodes[nid].get("parent")] + [
            e["to"] for e in nodes[nid].get("links", [])
        ]:
            if related and related in nodes and related not in chosen:
                chosen.add(related)
                order.append(related)
                if len(order) >= max_nodes:
                    break
    return [nodes[nid] for nid in order[:max_nodes]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Read-only retrieval over wiki/corpus.json."
    )
    ap.add_argument("question", help="the question / keywords to retrieve for")
    ap.add_argument(
        "--corpus",
        default=DEFAULT_CORPUS,
        help="corpus path (default: wiki/corpus.json)",
    )
    ap.add_argument("--max-nodes", type=int, default=8, help="max candidate nodes")
    args = ap.parse_args(argv)
    path = (
        args.corpus if os.path.isabs(args.corpus) else os.path.join(ROOT, args.corpus)
    )
    if not os.path.exists(path):
        print("[]")  # graceful: empty retrieval when no corpus yet
        return 0
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    hits = query(corpus, args.question, max_nodes=args.max_nodes)
    json.dump(hits, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
