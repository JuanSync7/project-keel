"""
title: Reclassify a document after the corpus build
summary: The reviewer's repro for a reader that checks a node's file now, shared by the showcase, doc reviewer, practice refactor, query_corpus and wiki navigator tests. `public_project(root, body)` writes a scratch project, an empty config/project.json and `docs/pubguide.md` (id `pubguide`) stating `visibility: public` with *body*, builds its corpus with scripts/jobs/build_corpus.py, writes it to wiki/corpus.json and returns its nodes. `reclassify(path, how)` then changes what the file states on disk, one way per member of HOWS: `own` changes its frontmatter's level to confidential, `readme` puts a confidential README.md beside it, `unreadable` writes bytes that are not UTF-8, `gone` deletes it. The corpus is left as built, so it still says public.
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

HOWS = ("own", "readme", "unreadable", "gone")
GUIDE = "docs/pubguide.md"


def public_project(root, body):
    """Write the scratch project at *root*, build its corpus into
    wiki/corpus.json, and return the corpus nodes."""
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "project.json").write_text("{}", encoding="utf-8")
    guide = root / GUIDE
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text(
        "---\ntitle: Pubguide\nkind: guide\nsummary: About pubguide.\n"
        "id: pubguide\nowner: alice\nvisibility: public\n---\n"
        "# Pubguide\n\n## Part\n\n%s\n" % body,
        encoding="utf-8",
    )
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    import build_corpus

    corpus = build_corpus.build_corpus(str(root))
    (root / "wiki").mkdir(exist_ok=True)
    (root / "wiki" / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    return corpus["nodes"]


def reclassify(path, how):
    """Change what the file at *path* states on disk, as *how* names."""
    if how == "own":
        text = path.read_text(encoding="utf-8")
        assert "visibility: public\n" in text
        path.write_text(
            text.replace("visibility: public\n", "visibility: confidential\n"),
            encoding="utf-8",
        )
    elif how == "readme":
        (path.parent / "README.md").write_text(
            "---\ntitle: Docs\nvisibility: confidential\n---\n# Docs\n",
            encoding="utf-8",
        )
    elif how == "unreadable":
        path.write_bytes(b"---\ntitle: x\n---\n\xff\xfe")
    elif how == "gone":
        path.unlink()
    else:
        raise ValueError("unknown way to reclassify: %r" % how)
