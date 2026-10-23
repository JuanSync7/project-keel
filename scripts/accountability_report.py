#!/usr/bin/env python3
"""
title: Accountability report
kind: script
layer: n/a
summary: Read-only: list corpus nodes with no resolved owner, and count those on the default owner.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from exit_codes import ExitCode, finish  # noqa: E402

DEFAULT_CORPUS = os.path.join("wiki", "corpus.json")


def unowned(corpus: dict) -> list:
    """Return nodes whose owner could not be resolved (owner_source == 'none')."""
    return [n for n in corpus.get("nodes", []) if n.get("owner_source") == "none"]


def defaulted(corpus: dict) -> list:
    """Return nodes that answer to accountability.default_owner because a TBD
    stands in their owner chain (owner_source == 'default')."""
    return [n for n in corpus.get("nodes", []) if n.get("owner_source") == "default"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Report corpus nodes with no resolved owner, and those on "
        "the default owner."
    )
    ap.add_argument(
        "--corpus",
        default=DEFAULT_CORPUS,
        help="corpus path (default: wiki/corpus.json)",
    )
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)
    path = (
        args.corpus if os.path.isabs(args.corpus) else os.path.join(ROOT, args.corpus)
    )
    if not os.path.exists(path):
        print("no corpus at %s; run build_corpus.py first." % args.corpus)
        return ExitCode.SUCCESS
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    gaps = unowned(corpus)
    if args.json:
        json.dump(
            [
                {"node_id": n["node_id"], "kind": n["kind"], "path": n["path"]}
                for n in gaps
            ],
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return ExitCode.SUCCESS
    total = len(corpus.get("nodes", []))
    print("accountability: %d of %d nodes have no resolved owner" % (len(gaps), total))
    for n in sorted(gaps, key=lambda n: n["node_id"]):
        print("  %-9s %s  (%s)" % (n["kind"], n["node_id"], n["path"]))
    held = defaulted(corpus)
    # A default node is listed by its TBD, not one line per node: writing the
    # real owner at that one place is the repair for every node under it.
    tbds = sorted({n["owner_origin"] for n in held})
    print(
        "accountability: %d of %d nodes answer to the default owner until a real "
        "one is named, from %d TBD%s"
        % (len(held), total, len(tbds), ":" if tbds else ".")
    )
    for origin in tbds:
        print("  %s" % origin)
    print(
        "accountability: %d of %d nodes have a real owner"
        % (total - len(gaps) - len(held), total)
    )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
