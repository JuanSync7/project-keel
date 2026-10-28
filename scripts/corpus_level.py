"""
title: corpus_level — the levels a file states, read the way the corpus build reads them
kind: script
layer: n/a
summary: The one reader of the visibility a file states on disk. `split_frontmatter` and `docstring_meta` are the corpus build's frontmatter and module-docstring grammars. `read_readme` is the one read of the level a README.md states, a README that cannot be read standing for UNREADABLE_README, whose UNREADABLE_VISIBILITY is a value outside CONVENTIONS §1's vocabulary. `readmes_upward` names each README.md from a directory up to the root, and `readme_chain` is the chain a file takes its level from: its walked directory's, then, for a symlink to a file elsewhere in the root, its real directory's. scripts/check_structure.py re-exports these, so check_A and scripts/jobs/build_corpus.py, which ranks a node over check_structure served_chain, judge a README.md by the same reader. `stated_now(root, relpath)` reads the file at *relpath* again and returns its own level followed by each README.md's on its readme_chain, or None when the file cannot be read, is a Markdown file with no frontmatter, a Python file that does not parse or has no docstring, or any other kind of file, so a reader that reads a body from disk decides with `config_loader.is_served_now` on the level the file states now as well as the corpus's. It imports nothing of the project, so the module reached as `corpus_level` and as `scripts.corpus_level` holds the same pure functions; ranking the levels is scripts/config_loader.py's. Stdlib-only and 3.6-safe; it reads files and writes none.
effect: read-only
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no
# walrus, no `list[str]` or `X | None` annotations: it sits in the bottom
# import layer, which the 3.6 hook interpreter runs
# (tests/integration/test_gate_scope.py `_bottom_import_layer`).

import ast
import os
from typing import Dict, List, Optional, Tuple

__all__ = [
    "UNREADABLE_README",
    "UNREADABLE_VISIBILITY",
    "docstring_meta",
    "read_readme",
    "readme_chain",
    "readmes_upward",
    "split_frontmatter",
    "stated_now",
]

# The ways a file on disk can fail to be read: ValueError covers
# UnicodeDecodeError. scripts/check_structure.py UNREADABLE is the same set.
_UNREADABLE = (OSError, ValueError)

# The visibility a README.md that cannot be read passes on. It is outside
# scripts/config_loader.py VISIBILITY_ORDER on purpose, so it outranks every
# level and check_corpus refuses each node it reaches.
UNREADABLE_VISIBILITY = "unreadable-readme"
# The frontmatter a README.md that cannot be read stands for. Matched by
# identity, so a README that writes `visibility: unreadable-readme` is still
# a readable README with an invalid level, for check_A to refuse.
UNREADABLE_README = {"visibility": UNREADABLE_VISIBILITY}

# The module-docstring keys the corpus reads; any other `key:` line is prose.
_DOCSTRING_KEYS = ("title", "summary", "layer", "public_api", "owner", "visibility")


def split_frontmatter(text: str) -> Tuple[Optional[Dict[str, str]], str]:
    """(frontmatter dict or None, body after the closing `---`) of a document's
    *text*: None when it does not open with `---`, and every top-level
    `key: value` up to the end of the text when the block never closes. The
    corpus's parse, which build_corpus reads every document by. Pure."""
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    data = {}  # type: Dict[str, str]
    body_start = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        line = lines[i]
        if line[:1] in (" ", "\t"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    return data, "\n".join(lines[body_start:])


def docstring_meta(doc: str) -> Tuple[Dict[str, str], str]:
    """(the title:/summary:/layer:/public_api:/owner:/visibility: lines of
    module docstring *doc*, its first other non-blank line)."""
    meta = {}  # type: Dict[str, str]
    first = ""
    for line in doc.splitlines():
        s = line.strip()
        if not s:
            continue
        if ":" in s and s.split(":", 1)[0] in _DOCSTRING_KEYS:
            k, _, v = s.partition(":")
            meta[k.strip()] = v.strip()
        elif not first:
            first = s
    return meta, first


def read_readme(path: str) -> Tuple[Optional[Dict[str, str]], Optional[Exception]]:
    """(frontmatter, fault) of the README.md at *path*, the one read of the
    level a README states: build_corpus ranks a node by it and check_A judges
    a README.md the walk skips by it, so the two cannot disagree. (None, None)
    when no name is at *path*; ({}, None) for a file with no frontmatter
    block. A name that is there but cannot be read (a dangling or looping
    link, a directory, a permission or decode fault) is (UNREADABLE_README,
    the fault): it may state any level, so it is never absent. utf-8-sig, so
    a BOM-saved README states the level it shows."""
    if not os.path.lexists(path):
        return None, None
    try:
        with open(path, encoding="utf-8-sig") as fh:
            fm, _ = split_frontmatter(fh.read())
    except _UNREADABLE as e:
        return UNREADABLE_README, e
    return fm or {}, None


def readmes_upward(dirpath: str, root: str) -> List[str]:
    """The README.md path of each directory from *dirpath* up to *root*,
    nearest first, each joined the way *dirpath* is and whether or not it
    exists; a caller keeps the ones it can find. Pure."""
    chain = []
    d = dirpath
    while True:
        chain.append(os.path.join(d, "README.md"))
        if os.path.abspath(d) == os.path.abspath(root):
            return chain
        parent = os.path.dirname(d)
        if parent == d:
            return chain
        d = parent


def readme_chain(path: str, root: str) -> List[str]:
    """The README.md paths a node at *path* takes its visibility from,
    nearest first: readmes_upward of the path the walk reached it by, then,
    when *path* is a symlink to a file elsewhere inside *root*, readmes_upward
    of the file it really is, each spelled under *root* as given.
    build_corpus ranks a node by this chain and check_A judges a file by it,
    so the two cannot disagree. A link into an open directory therefore
    cannot publish a confidential file; a target outside *root* adds nothing,
    so the walk never climbs out of the tree."""
    chain = readmes_upward(os.path.dirname(path), root)
    real_root = os.path.realpath(root)
    real_dir = os.path.dirname(os.path.realpath(path))
    walked_dir = os.path.realpath(os.path.dirname(path))
    # A target in the root directory itself adds nothing: the root README.md
    # ends every walked chain already.
    if real_dir != walked_dir and real_dir.startswith(real_root + os.sep):
        under_root = os.path.join(root, os.path.relpath(real_dir, real_root))
        chain += readmes_upward(under_root, root)
    return chain


def stated_now(root: str, relpath: Optional[str]) -> Optional[List[Optional[str]]]:
    """The level the file at *relpath* under *root* states itself on disk
    now (None for none), followed by the level each README.md on its
    readme_chain states, read by read_readme and nearest first, or None when
    no level can be read: no path, a file that cannot be read or decoded, a
    Markdown file with no frontmatter, a Python file that does not parse or
    has no docstring, or a file of any other kind. None is never a level, so
    a reader that gets it serves nothing. The corpus also ranks a node by the
    chain of every other path the walk reaches its file by (check_structure
    served_chain); this reads the one path the corpus keeps."""
    if not relpath:
        return None
    path = os.path.join(root, relpath)
    try:
        # utf-8-sig, as the corpus build reads: a BOM'd file states its level.
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except _UNREADABLE:
        return None
    if relpath.endswith(".md"):
        fm, _ = split_frontmatter(text)
        if fm is None:
            return None
        own = fm.get("visibility")
    elif relpath.endswith(".py"):
        try:
            doc = ast.get_docstring(ast.parse(text, filename=path))
        except (ValueError, SyntaxError):  # NUL byte / bad syntax
            return None
        if not doc:
            return None
        own = docstring_meta(doc)[0].get("visibility")
    else:
        return None
    levels = [own]  # type: List[Optional[str]]
    for readme in readme_chain(path, root):
        fm, _ = read_readme(readme)
        if fm is not None:
            levels.append(fm.get("visibility"))
    return levels
