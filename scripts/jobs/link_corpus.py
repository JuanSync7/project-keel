#!/usr/bin/env python3
"""
title: Link corpus job
kind: script
layer: n/a
summary: Deterministic: add keyword/entity link edges to wiki/corpus.json in place.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CORPUS = os.path.join("wiki", "corpus.json")


def link_corpus(corpus: dict, max_links: int = 8, min_score: float = 0.12) -> dict:
    """Add deterministic keyword/entity link edges (returns the same corpus).

    Two nodes link when they share tags/entities (e.g. both mention "AXI").
    Edges carry the shared token in `via` and a Jaccard `score`, with
    source="deterministic" so an LLM-added semantic edge stays distinguishable.
    Idempotent: existing edges are recomputed from scratch each run.
    """
    nodes = corpus.get("nodes", [])
    tagsets = {n["node_id"]: set(n.get("tags", [])) for n in nodes}
    # invert: tag -> node_ids that carry it
    by_tag = {}
    for nid, tags in tagsets.items():
        for t in tags:
            by_tag.setdefault(t, set()).add(nid)
    for n in nodes:
        nid = n["node_id"]
        mine = tagsets[nid]
        if not mine:
            n["links"] = []
            continue
        candidates = set()
        for t in mine:
            candidates |= by_tag.get(t, set())
        candidates.discard(nid)
        scored = []
        for other in candidates:
            theirs = tagsets[other]
            shared = mine & theirs
            if not shared:
                continue
            score = len(shared) / float(len(mine | theirs))
            if score < min_score:
                continue
            via = sorted(shared)[0]
            scored.append((round(score, 4), via, other))
        # strongest first, then stable by (via, node_id)
        scored.sort(key=lambda s: (-s[0], s[1], s[2]))
        n["links"] = [
            {"to": other, "via": via, "score": score,
             "kind": "keyword", "source": "deterministic"}
            for (score, via, other) in scored[:max_links]
        ]
    return corpus


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Add link edges to wiki/corpus.json (deterministic, in place).")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS, help="corpus path (default: wiki/corpus.json)")
    ap.add_argument("--max-links", type=int, default=8, help="max edges per node")
    args = ap.parse_args(argv)
    path = args.corpus if os.path.isabs(args.corpus) else os.path.join(ROOT, args.corpus)
    if not os.path.exists(path):
        print("no corpus at %s; run build_corpus.py first (skipping)." % args.corpus)
        return 0
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    link_corpus(corpus, max_links=args.max_links)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, indent=2, sort_keys=True)
        fh.write("\n")
    edges = sum(len(n.get("links", [])) for n in corpus.get("nodes", []))
    print("linked %s: %d edges across %d nodes"
          % (args.corpus, edges, len(corpus.get("nodes", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
