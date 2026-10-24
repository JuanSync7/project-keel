"""
title: corpus_vocabulary — the closed sets a corpus row's fields are judged by
kind: script
layer: n/a
summary: OWNER_SOURCES is the closed set of CONVENTIONS §12 owner sources a corpus node may carry: frontmatter, marker, inherited, default and none. scripts/jobs/check_corpus.py refuses a node outside it, and scripts/accountability_report.py counts by it, so the two cannot drift. It imports nothing, so a reader of the corpus takes the set without loading the corpus gate, build_corpus or check_structure. It is not where build_corpus decides a node's source (that is CONVENTIONS §12, in build_corpus), and it reads no config.
effect: read-only
"""

__all__ = ["OWNER_SOURCES"]

OWNER_SOURCES = frozenset({"frontmatter", "marker", "inherited", "default", "none"})
