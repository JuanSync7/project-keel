#!/usr/bin/env python3
"""
title: Accountability report
kind: script
layer: n/a
summary: Read-only: list corpus nodes with no resolved owner (the accountability gaps).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CORPUS = os.path.join("wiki", "corpus.json")


def unowned(corpus: dict) -> list:
    """Return nodes whose owner could not be resolved (owner_source == 'none')."""
    return [n for n in corpus.get("nodes", []) if n.get("owner_source") == "none"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Report corpus nodes with no resolved owner.")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS, help="corpus path (default: wiki/corpus.json)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)
    path = args.corpus if os.path.isabs(args.corpus) else os.path.join(ROOT, args.corpus)
    if not os.path.exists(path):
        print("no corpus at %s; run build_corpus.py first." % args.corpus)
        return 0
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    gaps = unowned(corpus)
    if args.json:
        json.dump([{"node_id": n["node_id"], "kind": n["kind"], "path": n["path"]}
                   for n in gaps], sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    total = len(corpus.get("nodes", []))
    print("accountability: %d of %d nodes have no resolved owner" % (len(gaps), total))
    for n in sorted(gaps, key=lambda n: n["node_id"]):
        print("  %-9s %s  (%s)" % (n["kind"], n["node_id"], n["path"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
