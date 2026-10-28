#!/usr/bin/env python3
"""
title: Query corpus
kind: script
layer: n/a
summary: Read-only retrieval over one checkout's wiki/corpus.json — the wiki_navigator's, practice_refactor's and doc_reviewer's tool. `--root` or `--corpus` names the checkout, never both: scripts/corpus_level.py checkout derives the corpus from the root, or the root from a corpus at some directory's wiki/corpus.json, so a corpus is read only with the files of the checkout that keeps it, and both given, a corpus anywhere else, or a `--corpus` that does not exist, is refused with exit USAGE and nothing printed. It prints only nodes whose file in that checkout may be served at a level in config/project.json corpus.served_visibilities as it stands on disk now (config_loader.is_served_now over corpus_level.stated_now, read once per file), so a file reclassified after the corpus was built, or one whose level cannot be read, is not printed, each printed node with every other node's id cut from its links, children and parent (config_loader.cut_hidden). A root that does not exist is refused with exit USAGE; a checkout with no corpus, named by `--root` or the default, prints `[]`, naming on stderr where its corpus would be; and the count of nodes withheld because their file now states a stricter level, or none that can be read, goes to stderr.
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
import corpus_level  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

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


def served_now(corpus: dict, served: Collection[str], root: str) -> tuple[dict, int]:
    """(the nodes of *corpus* whose file under *root* may be served at a level
    in *served* as it stands on disk now, keyed by node id; the count of nodes
    the corpus itself serves that are withheld because their file now states
    a stricter level, or none that can be read). config_loader.is_served_now
    decides; a node the corpus does not serve is not counted."""
    # A file's sections share its path, so its level is read once.
    stated: dict = {}
    nodes = {}
    withheld = 0
    for n in corpus.get("nodes", []):
        path = n.get("path")
        if path not in stated:
            stated[path] = corpus_level.stated_now(root, path)
        if config_loader.is_served_now(n, served, stated[path]):
            nodes[n["node_id"]] = n
        elif config_loader.is_served(n, served):
            withheld += 1
    return nodes, withheld


def query(
    corpus: dict,
    question: str,
    max_nodes: int = 8,
    *,
    served: Collection[str],
    root: str,
) -> list:
    """Return up to max_nodes candidate nodes for the question, best first,
    from the nodes whose file under *root* may be served at a level in
    *served* as it stands on disk now (config_loader.is_served_now).

    Deterministic retrieval: score each node by stemmed query-token overlap
    with its tags/title/summary (weight 2) and with its body excerpt (weight 1,
    so a body-only match never outranks a summary match), then pull in each
    hit's parent and linked nodes so the caller gets a connected neighbourhood
    (tree + links) to reason over. A node at any other level, a corpus row
    with no `visibility` field included, is cut before scoring, so it is neither a hit nor a
    neighbour, and config_loader.cut_hidden drops its id from every returned
    node's links, children and parent. So is a node whose file now states a
    level outside *served*, or one whose level cannot be read (served_now).
    """
    return rank(served_now(corpus, served, root)[0], question, max_nodes)


def rank(nodes: dict, question: str, max_nodes: int = 8) -> list:
    """Up to max_nodes of *nodes* (served nodes keyed by id) for the question,
    best first, by query's scoring and neighbour expansion, each with every
    id outside *nodes* cut from its links, children and parent."""
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
    return [config_loader.cut_hidden(nodes[nid], nodes) for nid in order[:max_nodes]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Read-only retrieval over wiki/corpus.json."
    )
    ap.add_argument("question", help="the question / keywords to retrieve for")
    ap.add_argument(
        "--corpus",
        default=None,
        help="the corpus, read only at its checkout's %s, whose files are "
        "read with it (a relative one from this directory); one that does not "
        "exist is refused; not with --root" % corpus_level.CORPUS_PATH,
    )
    ap.add_argument("--max-nodes", type=int, default=8, help="max candidate nodes")
    ap.add_argument(
        "--root",
        default=None,
        help="the checkout whose %s is read, and whose files are read for "
        "the level each states now (default: the project this script ships "
        "in); not with --corpus" % corpus_level.CORPUS_PATH,
    )
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
    try:
        root, path = corpus_level.checkout(args.root, args.corpus, ROOT)
    except corpus_level.NotACheckout as exc:
        what, on, next_step = exc.parts
        return report(ExitCode.USAGE, "query_corpus: " + what, on, next_step)
    if not os.path.isdir(root):
        return report(
            ExitCode.USAGE,
            "query_corpus: the checkout whose corpus is read does not exist",
            root,
            "pass --root a checkout that exists, or --corpus its %s, then rerun"
            % corpus_level.CORPUS_PATH,
        )
    if not os.path.exists(path):
        # A checkout with no corpus yet has nothing to retrieve: an empty
        # answer, said on stderr so a mistyped root is not taken for one.
        print(
            "query_corpus: no corpus at %s; `make site-data` builds it" % path,
            file=sys.stderr,
        )
        print("[]")
        return ExitCode.SUCCESS
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)
    nodes, withheld = served_now(corpus, served, root)
    if withheld:
        print(
            "query_corpus: withheld %d node(s) the corpus serves, whose file "
            "under %s now states a stricter level or none that can be read; "
            "`make site-data` rebuilds the corpus on the levels the files state"
            % (withheld, root),
            file=sys.stderr,
        )
    hits = rank(nodes, args.question, max_nodes=args.max_nodes)
    json.dump(hits, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
