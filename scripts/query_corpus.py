#!/usr/bin/env python3
"""
title: Query corpus
kind: script
layer: n/a
summary: Read-only retrieval over wiki/corpus.json — the wiki_navigator's, practice_refactor's and doc_reviewer's tool — that prints only nodes at a level in config/project.json corpus.served_visibilities.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Collection

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import config_loader  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

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


def query(
    corpus: dict, question: str, max_nodes: int = 8, *, served: Collection[str]
) -> list:
    """Return up to max_nodes candidate nodes for the question, best first,
    from the nodes at a level in *served*.

    Deterministic retrieval: score each node by stemmed query-token overlap
    with its tags/title/summary (weight 2) and with its body excerpt (weight 1,
    so a body-only match never outranks a summary match), then pull in each
    hit's parent and linked nodes so the caller gets a connected neighbourhood
    (tree + links) to reason over. A node at any other level, one that states
    none included, is cut before scoring, so it is neither a hit nor a
    neighbour.
    """
    nodes = {
        n["node_id"]: n
        for n in corpus.get("nodes", [])
        if config_loader.is_served(n, served)
    }
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
    try:
        served = config_loader.served_visibilities(ROOT)
    except config_loader.ConfigError as exc:
        # resolve has already written a refused value's own line; a file that
        # cannot be read is named here. Nothing is printed to stdout either way.
        return report(
            ExitCode.CONFIG,
            "query_corpus: the levels a served node may carry cannot be read",
            "; ".join(exc.lines)
            or "corpus.served_visibilities in %s"
            % (exc.path or config_loader.CONFIG_FILE),
            "set corpus.served_visibilities to members of %s, then rerun"
            % ", ".join(config_loader.VISIBILITY_ORDER),
        )
    path = (
        args.corpus if os.path.isabs(args.corpus) else os.path.join(ROOT, args.corpus)
    )
    if not os.path.exists(path):
        print("[]")  # graceful: empty retrieval when no corpus yet
        return ExitCode.SUCCESS
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    hits = query(corpus, args.question, max_nodes=args.max_nodes, served=served)
    json.dump(hits, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
