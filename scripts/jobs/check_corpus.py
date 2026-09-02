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

from build_corpus import build_corpus  # noqa: E402
from link_corpus import link_corpus  # noqa: E402

# Allowed enum values for the corpus contract (CONVENTIONS section 11/12).
KINDS = {"doc", "section", "module", "symbol"}
OWNER_SOURCES = {"frontmatter", "marker", "inherited", "none"}
SUMMARY_SOURCES = {"authored", "generated", ""}
VISIBILITIES = {"public", "internal", "confidential", "restricted"}
LINK_SOURCES = {"deterministic", "generated"}
REQUIRED_FIELDS = (
    "node_id",
    "kind",
    "title",
    "path",
    "anchor",
    "lineno",
    "summary",
    "summary_source",
    "text_excerpt",
    "owner",
    "owner_source",
    "owner_origin",
    "tags",
    "visibility",
    "updated",
    "parent",
    "children",
    "links",
)
SCHEMA_VERSION = 1


def _dumps(corpus: dict) -> str:
    """Canonical serialization (matches build_corpus/link_corpus on-disk form)."""
    return json.dumps(corpus, indent=2, sort_keys=True) + "\n"


def _load_corpus(path: str) -> tuple:
    """Read the JSON corpus at *path*; return (corpus, reason) with reason "" on
    success. Callers own the ABSENT case (it means different things to the gate
    and to --corpus); this owns present-but-broken — bad permissions, a
    directory, a dangling symlink, malformed JSON — because every one of those
    escaped as a traceback from `make verify` when only ValueError was caught."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh), ""
    except (OSError, ValueError) as exc:
        return None, str(exc)


def _deterministic_projection(corpus: dict) -> dict:
    """The corpus with LLM enrichment stripped back to its deterministic base:
    links keep only source 'deterministic', and a summary filled as 'generated'
    resets to the empty not-yet-authored state. Staleness (ADR-0008) is judged
    on THIS projection, so index_enforcer's legitimate fills (it only ever
    targets EMPTY summaries) — and any future enricher appending 'generated'
    links, which LINK_SOURCES already anticipates — never read as rot, while
    any drift in what the tree deterministically yields still does."""
    proj = json.loads(_dumps(corpus))
    for n in proj.get("nodes", []) or []:
        if not isinstance(n, dict):
            continue
        if n.get("summary_source") == "generated":
            n["summary"] = ""
            n["summary_source"] = ""
        n["links"] = [
            ln
            for ln in n.get("links", []) or []
            if isinstance(ln, dict) and ln.get("source") == "deterministic"
        ]
    return proj


def validate(corpus: dict) -> list:
    """Return a list of human-readable integrity errors ([] when the graph is valid)."""
    errs = []

    def e(msg):
        errs.append(msg)

    if not isinstance(corpus, dict):
        return ["corpus is not a JSON object"]
    if corpus.get("schema_version") != SCHEMA_VERSION:
        e(
            "schema_version is %r, expected %d"
            % (corpus.get("schema_version"), SCHEMA_VERSION)
        )
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
            e(
                "node %r has invalid kind %r (expected %s)"
                % (nid, n.get("kind"), sorted(KINDS))
            )
        if n.get("owner_source") not in OWNER_SOURCES:
            e("node %r has invalid owner_source %r" % (nid, n.get("owner_source")))
        if n.get("summary_source") not in SUMMARY_SOURCES:
            e("node %r has invalid summary_source %r" % (nid, n.get("summary_source")))
        if n.get("visibility") not in VISIBILITIES:
            e("node %r has invalid visibility %r" % (nid, n.get("visibility")))
        # owner/owner_source coherence (CONVENTIONS section 12)
        if n.get("owner_source") == "none":
            if n.get("owner"):
                e(
                    "node %r: owner_source 'none' but owner is %r"
                    % (nid, n.get("owner"))
                )
            if n.get("owner_origin") is not None:
                e("node %r: owner_source 'none' but owner_origin is set" % nid)
        else:
            if not n.get("owner"):
                e(
                    "node %r: owner_source %r but owner is empty"
                    % (nid, n.get("owner_source"))
                )
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
                e(
                    "node %r: parent %r does not list it as a child (broken tree edge)"
                    % (nid, parent)
                )
        for c in n.get("children", []) or []:
            if c not in by_id:
                e("node %r: child %r does not resolve" % (nid, c))
            elif by_id[c].get("parent") != nid:
                e(
                    "node %r: child %r has a different parent (broken tree edge)"
                    % (nid, c)
                )
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
        "(deterministic; CONVENTIONS section 11)."
    )
    ap.add_argument("--root", default=ROOT, help="tree to index (default: repo root)")
    ap.add_argument(
        "--corpus",
        default=None,
        help="validate this existing corpus file instead of a fresh "
        "build; also warns if it is stale vs a fresh build",
    )
    ap.add_argument("--max-links", type=int, default=8, help="max edges per node")
    args = ap.parse_args(argv)

    rc = 0
    if args.corpus:
        path = (
            args.corpus
            if os.path.isabs(args.corpus)
            else os.path.join(args.root, args.corpus)
        )
        if not os.path.exists(path):
            sys.stderr.write("ERROR check_corpus: no corpus at %s\n" % args.corpus)
            return 1
        corpus, why = _load_corpus(path)
        if why:
            sys.stderr.write(
                "ERROR check_corpus: %s could not be read (%s)\n" % (args.corpus, why)
            )
            return 1
        errs = validate(corpus)
        for m in errs:
            sys.stderr.write("ERROR check_corpus: %s\n" % m)
        rc = 1 if errs else 0
        # Manual-inspection mode keeps staleness a warning; the DEFAULT mode
        # (the gate) errors on it — see the local-corpus block in main(). Same
        # projection as the gate, or every legitimately enriched corpus would
        # WARN forever and tell its owner to discard the enrichment — and same
        # `not errs` guard, because projecting a non-graph raises where the
        # designed ERROR was already printed.
        if not errs and _dumps(_deterministic_projection(corpus)) != _dumps(
            _fresh(args.root, args.max_links)
        ):
            print(
                "WARN check_corpus: %s is stale vs a fresh build "
                "(regenerate with `make site-data`)" % args.corpus
            )
        if rc == 0:
            print(
                "check_corpus: %s valid (%d nodes)"
                % (args.corpus, len(corpus.get("nodes", [])))
            )
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
        sys.stderr.write(
            "ERROR check_corpus: build is NOT deterministic (two builds differ)\n"
        )
        rc = 1

    # The LOCAL corpus is what the agents actually query (wiki/corpus.json, a
    # gitignored generated view) — and until ADR-0008 nothing here ever read it,
    # so it could rot silently while this check rebuilt fresh copies (measured:
    # 33 nodes behind the tree at a green gate). Absent is a real state, not a
    # drift — a fresh clone, CI, and a day-one generated project have none — so
    # say it loudly and stay green (the ADR-0007 absent-vs-drifted split).
    # Present-but-stale is an ERROR naming the repair; a check that writes is
    # not a check, so nothing here regenerates anything.
    local = os.path.join(args.root, "wiki", "corpus.json")
    if not os.path.exists(local):
        print(
            "check_corpus: no local wiki/corpus.json yet (generated view) -- "
            "agents build one with `make site-data`"
        )
    else:
        # Parse -> validate -> only THEN compare staleness: a corpus that is
        # `null`, a list, or {"nodes": 5} is ROT and must take the designed
        # ERROR path — running the projection over a non-graph would crash
        # with a traceback (and `null` slipped a `is not None` guard entirely,
        # exit 0 — found by the ADR-0008 review pass).
        committed, why = _load_corpus(local)
        if why:
            sys.stderr.write(
                "ERROR check_corpus: wiki/corpus.json could not be read (%s) -- "
                "regenerate with `make site-data`\n" % why
            )
            rc = 1
        else:
            shape_errs = validate(committed)
            for m in shape_errs:
                sys.stderr.write("ERROR check_corpus: wiki/corpus.json: %s\n" % m)
                rc = 1
            if not shape_errs and _dumps(
                _deterministic_projection(committed)
            ) != _dumps(first):
                sys.stderr.write(
                    "ERROR check_corpus: wiki/corpus.json is stale vs the tree "
                    "-- the corpus the agents query is not the project they "
                    "are in; regenerate with `make site-data`\n"
                )
                rc = 1

    if rc == 0:
        print(
            "check_corpus: fresh build valid + deterministic (%d nodes, %d edges)"
            % (
                len(first["nodes"]),
                sum(len(n.get("links", [])) for n in first["nodes"]),
            )
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
