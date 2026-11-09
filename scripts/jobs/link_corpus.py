#!/usr/bin/env python3
"""
title: Link corpus job
kind: script
layer: n/a
summary: Deterministic: add keyword/entity link edges to wiki/corpus.json, published atomically through a sibling temporary file so readers see only complete JSON. An explicit absolute output file authorizes its parent directory; relative outputs stay under the project root. Escapes exit USAGE before writing. Internal links are allowed; checks judge paths at call time.
effect: writes
rerun: fixed-point
rerun_proof: make:check-corpus
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from atomic_write import write_if_changed  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402
from git_tree import PathEscape, confined_path  # noqa: E402

DEFAULT_CORPUS = os.path.join("wiki", "corpus.json")


def link_corpus(corpus: dict, max_links: int = 8, min_score: float = 0.12) -> dict:
    """Add deterministic keyword/entity link edges (returns the same corpus).

    Two nodes link when they share tags/entities (e.g. both mention "AXI").
    Edges carry the shared token in `via` and a Jaccard `score`, with
    source="deterministic" so an LLM-added semantic edge stays distinguishable.
    Idempotent: the KEYWORD edges are recomputed from scratch each run; the
    authored reference edges build_corpus wrote (kind link / citation /
    mention) are kept as they are — this job owns one kind of edge, not the
    list.
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
        kept = [e for e in n.get("links", []) or [] if e.get("kind") != "keyword"]
        mine = tagsets[nid]
        if not mine:
            n["links"] = kept
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
        n["links"] = kept + [
            {
                "to": other,
                "via": via,
                "score": score,
                "kind": "keyword",
                "source": "deterministic",
            }
            for (score, via, other) in scored[:max_links]
        ]
    return corpus


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Add link edges to wiki/corpus.json (deterministic, atomic replacement)."
    )
    ap.add_argument(
        "--corpus",
        default=DEFAULT_CORPUS,
        help="corpus path (default: wiki/corpus.json)",
    )
    ap.add_argument("--max-links", type=int, default=8, help="max edges per node")
    args = ap.parse_args(argv)
    path = (
        args.corpus if os.path.isabs(args.corpus) else os.path.join(ROOT, args.corpus)
    )
    try:
        boundary = os.path.dirname(path) if os.path.isabs(args.corpus) else ROOT
        path = confined_path(boundary, path)
    except PathEscape as exc:
        return report(
            ExitCode.USAGE,
            "link_corpus: corpus escapes its root",
            str(exc),
            "keep relative --corpus inside the project or choose an explicit absolute corpus",
        )
    if not os.path.exists(path):
        print("no corpus at %s; run build_corpus.py first (skipping)." % args.corpus)
        return ExitCode.SUCCESS
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    link_corpus(corpus, max_links=args.max_links)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_if_changed(
        path, (json.dumps(corpus, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    edges = sum(len(n.get("links", [])) for n in corpus.get("nodes", []))
    print(
        "linked %s: %d edges across %d nodes"
        % (args.corpus, edges, len(corpus.get("nodes", [])))
    )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
