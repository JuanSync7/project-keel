#!/usr/bin/env python3
"""
title: Check corpus job
kind: script
layer: n/a
summary: Deterministic: validate wiki/corpus.json integrity and that build is reproducible.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from build_corpus import build_corpus            # noqa: E402
from link_corpus import link_corpus              # noqa: E402

# Allowed enum values for the corpus contract (CONVENTIONS section 11/12).
KINDS = {"doc", "section", "module", "symbol"}
OWNER_SOURCES = {"frontmatter", "marker", "inherited", "none"}
SUMMARY_SOURCES = {"authored", "generated", ""}
VISIBILITIES = {"public", "internal", "confidential", "restricted"}
LINK_SOURCES = {"deterministic", "generated"}
REQUIRED_FIELDS = (
    "node_id", "kind", "title", "path", "anchor", "lineno", "summary",
    "summary_source", "text_excerpt", "owner", "owner_source", "owner_origin",
    "tags", "visibility", "updated", "parent", "children", "links",
)
SCHEMA_VERSION = 1


def _dumps(corpus: dict) -> str:
    """Canonical serialization (matches build_corpus/link_corpus on-disk form)."""
    return json.dumps(corpus, indent=2, sort_keys=True) + "\n"


def validate(corpus: dict) -> list:
    """Return a list of human-readable integrity errors ([] when the graph is valid)."""
    errs = []

    def e(msg):
        errs.append(msg)

    if not isinstance(corpus, dict):
        return ["corpus is not a JSON object"]
    if corpus.get("schema_version") != SCHEMA_VERSION:
        e("schema_version is %r, expected %d"
          % (corpus.get("schema_version"), SCHEMA_VERSION))
    nodes = corpus.get("nodes")
    if not isinstance(nodes, list):
        return errs + ["'nodes' missing or not a list"]

    by_id = {}
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            e("node[%d] is not an object" % i)
            continue
        nid = n.get("node_id")
        for f in REQUIRED_FIELDS:
            if f not in n:
                e("node %r missing required field '%s'" % (nid, f))
        if nid in by_id:
            e("duplicate node_id %r (primary key must be unique)" % nid)
        else:
            by_id[nid] = n
        if n.get("kind") not in KINDS:
            e("node %r has invalid kind %r (expected %s)"
              % (nid, n.get("kind"), sorted(KINDS)))
        if n.get("owner_source") not in OWNER_SOURCES:
            e("node %r has invalid owner_source %r" % (nid, n.get("owner_source")))
        if n.get("summary_source") not in SUMMARY_SOURCES:
            e("node %r has invalid summary_source %r" % (nid, n.get("summary_source")))
        if n.get("visibility") not in VISIBILITIES:
            e("node %r has invalid visibility %r" % (nid, n.get("visibility")))
        # owner/owner_source coherence (CONVENTIONS section 12)
        if n.get("owner_source") == "none":
            if n.get("owner"):
                e("node %r: owner_source 'none' but owner is %r" % (nid, n.get("owner")))
            if n.get("owner_origin") is not None:
                e("node %r: owner_source 'none' but owner_origin is set" % nid)
        else:
            if not n.get("owner"):
                e("node %r: owner_source %r but owner is empty"
                  % (nid, n.get("owner_source")))
        tags = n.get("tags")
        if not isinstance(tags, list):
            e("node %r: tags is not a list" % nid)
        elif tags != sorted(set(tags)):
            e("node %r: tags must be sorted and unique" % nid)

    # Reference + tree integrity (needs the full id set first).
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("node_id")
        parent = n.get("parent")
        if parent is not None:
            if parent not in by_id:
                e("node %r: parent %r does not resolve" % (nid, parent))
            elif nid not in by_id[parent].get("children", []):
                e("node %r: parent %r does not list it as a child (broken tree edge)"
                  % (nid, parent))
        for c in n.get("children", []) or []:
            if c not in by_id:
                e("node %r: child %r does not resolve" % (nid, c))
            elif by_id[c].get("parent") != nid:
                e("node %r: child %r has a different parent (broken tree edge)"
                  % (nid, c))
        for ln in n.get("links", []) or []:
            if not isinstance(ln, dict):
                e("node %r: a link is not an object" % nid)
                continue
            if ln.get("to") not in by_id:
                e("node %r: link target %r does not resolve" % (nid, ln.get("to")))
            if ln.get("source") not in LINK_SOURCES:
                e("node %r: link source %r invalid" % (nid, ln.get("source")))
            sc = ln.get("score")
            if not isinstance(sc, (int, float)) or not (0.0 <= sc <= 1.0):
                e("node %r: link score %r out of [0,1]" % (nid, sc))

    # Acyclicity of the parent chain.
    for n in nodes:
        if not isinstance(n, dict):
            continue
        seen, cur = set(), n.get("node_id")
        while cur is not None and cur in by_id:
            if cur in seen:
                e("node %r: parent chain has a cycle" % n.get("node_id"))
                break
            seen.add(cur)
            cur = by_id[cur].get("parent")
    return errs


def _fresh(root: str, max_links: int) -> dict:
    return link_corpus(build_corpus(root), max_links=max_links)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate corpus integrity and build reproducibility "
                    "(deterministic; CONVENTIONS section 11).")
    ap.add_argument("--root", default=ROOT, help="tree to index (default: repo root)")
    ap.add_argument("--corpus", default=None,
                    help="validate this existing corpus file instead of a fresh "
                         "build; also warns if it is stale vs a fresh build")
    ap.add_argument("--max-links", type=int, default=8, help="max edges per node")
    args = ap.parse_args(argv)

    rc = 0
    if args.corpus:
        path = args.corpus if os.path.isabs(args.corpus) \
            else os.path.join(args.root, args.corpus)
        if not os.path.exists(path):
            sys.stderr.write("ERROR check_corpus: no corpus at %s\n" % args.corpus)
            return 1
        with open(path, encoding="utf-8") as fh:
            corpus = json.load(fh)
        errs = validate(corpus)
        for m in errs:
            sys.stderr.write("ERROR check_corpus: %s\n" % m)
        rc = 1 if errs else 0
        # The file is a generated view (gitignored); staleness is a warning.
        if _dumps(corpus) != _dumps(_fresh(args.root, args.max_links)):
            print("WARN check_corpus: %s is stale vs a fresh build "
                  "(regenerate via rebuild_index.py)" % args.corpus)
        if rc == 0:
            print("check_corpus: %s valid (%d nodes)"
                  % (args.corpus, len(corpus.get("nodes", []))))
        return rc

    # Default: build fresh, validate integrity, then prove reproducibility.
    first = _fresh(args.root, args.max_links)
    errs = validate(first)
    for m in errs:
        sys.stderr.write("ERROR check_corpus: %s\n" % m)
    if errs:
        rc = 1
    second = _fresh(args.root, args.max_links)
    if _dumps(first) != _dumps(second):
        sys.stderr.write("ERROR check_corpus: build is NOT deterministic "
                         "(two builds differ)\n")
        rc = 1
    if rc == 0:
        print("check_corpus: fresh build valid + deterministic (%d nodes, %d edges)"
              % (len(first["nodes"]),
                 sum(len(n.get("links", [])) for n in first["nodes"])))
    return rc


if __name__ == "__main__":
    sys.exit(main())
