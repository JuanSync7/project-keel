#!/usr/bin/env python3
"""
title: Accountability report
kind: script
layer: n/a
summary: Read-only: list corpus nodes with no resolved owner and those that name no owner source, and count those on the default owner.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JOBS = os.path.join(ROOT, "scripts", "jobs")
if _JOBS not in sys.path:
    sys.path.insert(0, _JOBS)

from check_corpus import OWNER_SOURCES  # noqa: E402
from exit_codes import ExitCode, finish  # noqa: E402

DEFAULT_CORPUS = os.path.join("wiki", "corpus.json")

# What the text report prints for a field a corpus row does not carry; the
# `--json` report gives such a field as null.
MISSING = "(missing)"


def _rows(corpus: dict) -> list:
    """The corpus's node rows; a row that is not an object stands as a row
    with every field missing, so it is counted and listed, not dropped."""
    return [n if isinstance(n, dict) else {} for n in corpus.get("nodes", [])]


def _shown(node: dict, field: str) -> str:
    """*field* of *node* as the text report prints it: MISSING when the row
    does not carry it."""
    return str(node[field]) if field in node else MISSING


def _by_id(nodes: list) -> list:
    """*nodes* sorted by node_id as printed, so a row missing it sorts too."""
    return sorted(nodes, key=lambda n: _shown(n, "node_id"))


def unowned(corpus: dict) -> list:
    """Return nodes whose owner could not be resolved (owner_source == 'none')."""
    return [n for n in _rows(corpus) if n.get("owner_source") == "none"]


# The CONVENTIONS §12 sources that name a real owner: check_corpus's closed
# set less `none` (no owner) and `default` (the stand-in for a TBD).
_REAL_SOURCES = tuple(sorted(OWNER_SOURCES - {"none", "default"}))


def unknown(corpus: dict) -> list:
    """Return nodes that name no CONVENTIONS §12 owner source (missing, null,
    empty or outside the set), whose owner is unknown: neither owned nor
    `none`."""
    return [n for n in _rows(corpus) if n.get("owner_source") not in OWNER_SOURCES]


def defaulted(corpus: dict) -> list:
    """Return nodes that answer to accountability.default_owner because a TBD
    stands in their owner chain (owner_source == 'default')."""
    return [n for n in _rows(corpus) if n.get("owner_source") == "default"]


def _listed(node: dict) -> tuple:
    """The (kind, node_id, path) a listed node's line prints."""
    return tuple(_shown(node, f) for f in ("kind", "node_id", "path"))


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
            [{f: n.get(f) for f in ("node_id", "kind", "path")} for n in gaps],
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return ExitCode.SUCCESS
    total = len(_rows(corpus))
    print("accountability: %d of %d nodes have no resolved owner" % (len(gaps), total))
    for n in _by_id(gaps):
        print("  %-9s %s  (%s)" % _listed(n))
    held = defaulted(corpus)
    # A default node is listed by its TBD, not one line per node: writing the
    # real owner at that one place is the repair for every node under it.
    tbds = sorted({_shown(n, "owner_origin") for n in held})
    print(
        "accountability: %d of %d nodes answer to the default owner until a real "
        "one is named, from %d TBD%s"
        % (len(held), total, len(tbds), ":" if tbds else ".")
    )
    for origin in tbds:
        print("  %s" % origin)
    blind = unknown(corpus)
    print(
        "accountability: %d of %d nodes name no owner source, so their owner is "
        "unknown -- repair the unreadable README.md above it (or state an owner "
        "on the node), then run scripts/jobs/build_corpus.py%s"
        % (len(blind), total, ":" if blind else ".")
    )
    for n in _by_id(blind):
        print("  %-9s %s  (%s)" % _listed(n))
    real = [n for n in _rows(corpus) if n.get("owner_source") in _REAL_SOURCES]
    print("accountability: %d of %d nodes have a real owner" % (len(real), total))
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
