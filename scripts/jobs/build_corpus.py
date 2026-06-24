#!/usr/bin/env python3
"""
title: Build corpus job
kind: script
layer: n/a
summary: Deterministic: walk the repo into wiki/corpus.json (the one-brain index).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_VERSION = 1

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".astro", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}
CODE_ROOTS = ["src", "tests", "api", "models", "mcp", "agents", "demo", "scripts"]

# Owner markers use the same token + grammar in both worlds, but a STRUCTURED
# form so prose mentioning "owner:" is never mistaken for a marker: a section
# uses an HTML comment under the heading; a symbol uses a full `owner:` line.
_SECTION_OWNER_RE = re.compile(r"<!--\s*owner:\s*([A-Za-z0-9._@-]+)\s*-->")
_SYMBOL_OWNER_RE = re.compile(r"(?m)^\s*owner:\s*([A-Za-z0-9._@-]+)\s*$")
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
_ACRONYM_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,})\b")        # AXI, DMA, RAG, ...
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "are", "was",
    "not", "but", "you", "your", "use", "used", "uses", "via", "per", "its",
    "all", "any", "one", "two", "how", "what", "when", "where", "which", "who",
    "doc", "docs", "file", "files", "code", "line", "lines", "see", "etc",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "node"


def _path_id(rel: str) -> str:
    """Path-derived id that PRESERVES separators, so distinct paths never collide
    (e.g. 'a/b.md' -> 'a/b-md' vs 'a-b.md' -> 'a-b-md'). _slug alone is not
    injective because it maps '/', '-' and '.' all to '-'."""
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    return "/".join(_slug(p) for p in parts) or "node"


def _rel(path: str, root: str) -> str:
    return os.path.relpath(path, root)


def _walk(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        # Sort dirnames so traversal order (hence cross-dir symlink dedup) is
        # deterministic across hosts/filesystems, not os.walk-entry-order.
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        yield dirpath, dirnames, filenames


def _real_owner(value):
    """A frontmatter/marker owner counts only if present and not the TBD placeholder."""
    if value and value != "TBD":
        return value
    return None


def _keywords(*texts: str) -> list:
    """Lowercased significant words + preserved ACRONYMS, deduped, capped."""
    out = []
    seen = set()
    for t in texts:
        for ac in _ACRONYM_RE.findall(t or ""):
            if ac not in seen:
                seen.add(ac)
                out.append(ac)
    for t in texts:
        for w in _WORD_RE.findall((t or "").lower()):
            # skip stopwords, already-seen words, and the lowercase form of an
            # acronym we already emitted in cased form (AXI -> don't re-add axi).
            if w in _STOP or w in seen or w.upper() in seen:
                continue
            seen.add(w)
            out.append(w)
    return out[:12]


def _parse_frontmatter(text: str):
    """Return (frontmatter dict or None, body string after the closing ---)."""
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    data = {}
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


def _parse_tags(raw) -> list:
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [t.strip() for t in raw.split(",") if t.strip()]


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        return ""
    m = re.search(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text)[:240]


def _docstring_meta(doc: str):
    """Module docstrings in this repo carry title:/summary:/owner: lines."""
    meta = {}
    first = ""
    for line in doc.splitlines():
        s = line.strip()
        if not s:
            continue
        if ":" in s and s.split(":", 1)[0] in (
                "title", "summary", "layer", "public_api", "owner", "visibility"):
            k, _, v = s.partition(":")
            meta[k.strip()] = v.strip()
        elif not first:
            first = s
    return meta, first


# --------------------------------------------------------------------------- #
# node builders
# --------------------------------------------------------------------------- #
def _doc_and_sections(path: str, root: str, nodes: list):
    rel = _rel(path, root)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return
    fm, body = _parse_frontmatter(text)
    if fm is None:
        return  # only frontmatter-bearing markdown is a corpus doc
    doc_id = fm.get("id") or _path_id(rel)
    doc_owner = _real_owner(fm.get("owner"))
    visibility = fm.get("visibility") or "internal"
    title = fm.get("title") or rel
    summary = fm.get("summary") or ""
    tags = _parse_tags(fm.get("tags")) + _keywords(title, summary)
    nodes.append({
        "node_id": doc_id,
        "kind": "doc",
        "title": title,
        "path": rel,
        "anchor": None,
        "lineno": None,
        "summary": summary,
        "summary_source": "authored" if summary else "",
        "text_excerpt": " ".join(body.split())[:400],
        "owner": doc_owner or "",
        "owner_source": "frontmatter" if doc_owner else "none",
        "owner_origin": rel if doc_owner else None,
        "tags": sorted(set(tags)),
        "visibility": visibility,
        "updated": fm.get("updated") or "",
        "parent": None,
        "children": [],
        "links": [],
    })
    _sections(body, doc_id, rel, doc_owner, visibility, nodes)


def _sections(body, doc_id, rel, doc_owner, doc_visibility, nodes):
    lines = body.splitlines()
    blocks = []
    cur = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            if cur:
                blocks.append(cur)
            cur = {"level": len(m.group(1)), "title": m.group(2),
                   "lineno": i + 1, "body": []}
        elif cur is not None:
            cur["body"].append(line)
    if cur:
        blocks.append(cur)

    last_h2 = None
    seen_anchors = {}
    for b in blocks:
        base = _slug(b["title"])
        # disambiguate repeated heading slugs within one doc (Setup, setup-2, ...)
        n = seen_anchors.get(base, 0) + 1
        seen_anchors[base] = n
        anchor = base if n == 1 else "%s-%d" % (base, n)
        sec_id = "%s#%s" % (doc_id, anchor)
        btext = "\n".join(b["body"])
        marker = _SECTION_OWNER_RE.search("\n".join(b["body"][:3]))
        marker_owner = _real_owner(marker.group(1)) if marker else None
        if marker_owner:
            owner, osrc, oorigin = marker_owner, "marker", "%s#%s" % (rel, anchor)
        elif doc_owner:
            owner, osrc, oorigin = doc_owner, "inherited", rel
        else:
            owner, osrc, oorigin = "", "none", None
        parent = doc_id if b["level"] == 2 else (last_h2 or doc_id)
        if b["level"] == 2:
            last_h2 = sec_id
        summ = _first_sentence(btext)
        nodes.append({
            "node_id": sec_id,
            "kind": "section",
            "title": b["title"],
            "path": rel,
            "anchor": anchor,
            "lineno": b["lineno"],
            "summary": summ,
            "summary_source": "authored" if summ else "",
            "text_excerpt": " ".join(btext.split())[:400],
            "owner": owner,
            "owner_source": osrc,
            "owner_origin": oorigin,
            "tags": sorted(set(_keywords(b["title"], btext))),
            "visibility": doc_visibility,   # inherit the doc's visibility (no leaks)
            "updated": "",
            "parent": parent,
            "children": [],
            "links": [],
        })


def _nearest_readme(dirpath: str, root: str):
    """Walk up to the repo root for a README.md; return (owner, origin, visibility)."""
    d = dirpath
    while True:
        readme = os.path.join(d, "README.md")
        if os.path.isfile(readme):
            try:
                with open(readme, encoding="utf-8") as fh:
                    fm, _ = _parse_frontmatter(fh.read())
            except Exception:
                fm = None
            fm = fm or {}
            owner = _real_owner(fm.get("owner"))
            if owner or fm.get("visibility"):
                return owner, _rel(readme, root), fm.get("visibility")
        if os.path.abspath(d) == os.path.abspath(root):
            return None, None, None
        parent = os.path.dirname(d)
        if parent == d:
            return None, None, None
        d = parent


def _module_and_symbols(path: str, root: str, nodes: list):
    rel = _rel(path, root)
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src, filename=path)
    except Exception:
        return
    doc = ast.get_docstring(tree)
    if not doc:
        return  # only documented modules are corpus nodes
    meta, first = _docstring_meta(doc)
    mod_id = _path_id(rel)
    title = meta.get("title") or rel
    summary = meta.get("summary") or first
    # owner + visibility: own docstring owner is the module's "frontmatter"; else
    # inherit the nearest package README (owner_source 'inherited').
    nr_owner, nr_origin, nr_vis = _nearest_readme(os.path.dirname(path), root)
    mod_owner = _real_owner(meta.get("owner"))
    if mod_owner:
        osrc, oorigin = "frontmatter", rel
    elif nr_owner:
        mod_owner, osrc, oorigin = nr_owner, "inherited", nr_origin
    else:
        osrc, oorigin = "none", None
    visibility = meta.get("visibility") or nr_vis or "internal"
    nodes.append({
        "node_id": mod_id,
        "kind": "module",
        "title": title,
        "path": rel,
        "anchor": None,
        "lineno": 1,
        "summary": summary,
        "summary_source": "authored" if summary else "",
        "text_excerpt": " ".join(doc.split())[:400],
        "owner": mod_owner or "",
        "owner_source": osrc,
        "owner_origin": oorigin,
        "tags": sorted(set(_keywords(title, summary))),
        "visibility": visibility,
        "updated": "",
        "parent": None,
        "children": [],
        "links": [],
    })
    exported = _exported_names(tree)
    defs = {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for name in sorted(exported):
        nd = defs.get(name)
        if nd is None:
            continue  # re-exported from elsewhere; indexed where it is defined
        sdoc = ast.get_docstring(nd) or ""
        marker = _SYMBOL_OWNER_RE.search(sdoc)
        marker_owner = _real_owner(marker.group(1)) if marker else None
        if marker_owner:
            owner, so, oo = marker_owner, "marker", "%s::%s" % (rel, name)
        elif mod_owner:
            owner, so, oo = mod_owner, "inherited", oorigin
        else:
            owner, so, oo = "", "none", None
        summ = _first_sentence(sdoc)
        nodes.append({
            "node_id": "%s::%s" % (mod_id, name),
            "kind": "symbol",
            "title": name,
            "path": rel,
            "anchor": name,
            "lineno": getattr(nd, "lineno", None),
            "summary": summ,
            "summary_source": "authored" if summ else "",
            "text_excerpt": " ".join(sdoc.split())[:400],
            "owner": owner,
            "owner_source": so,
            "owner_origin": oo,
            "tags": sorted(set(_keywords(name, summ))),
            "visibility": visibility,       # symbols inherit the module's visibility
            "updated": "",
            "parent": mod_id,
            "children": [],
            "links": [],
        })


def _exported_names(tree) -> list:
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__" \
                        and isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        val = getattr(elt, "s", None)
                        if val is None and isinstance(elt, ast.Constant):
                            val = elt.value
                        if isinstance(val, str):
                            out.append(val)
    return out


def build_corpus(root: str) -> dict:
    """Walk the repo and return the corpus dict (nodes + tree edges, no links).

    Pure + deterministic: authored docstrings/frontmatter become canonical
    summaries; nodes with none are emitted with summary_source == "" (a gap the
    index_enforcer fills later, marking it "generated"). No model is ever called.
    """
    nodes = []
    seen_real = set()
    for dirpath, _, filenames in _walk(root):
        top = _rel(dirpath, root).split(os.sep)[0]
        for f in sorted(filenames):
            full = os.path.join(dirpath, f)
            real = os.path.realpath(full)
            if f.endswith(".md"):
                # Any frontmatter-bearing markdown is a corpus doc (the "one
                # brain" ingests every labeled doc, not just README/AGENT). The
                # realpath dedup collapses the CLAUDE.md -> AGENT.md symlink.
                if real in seen_real:
                    continue
                seen_real.add(real)
                _doc_and_sections(full, root, nodes)
            elif f.endswith(".py") and top in CODE_ROOTS:
                _module_and_symbols(full, root, nodes)

    # denormalize children from parent edges
    by_id = {n["node_id"]: n for n in nodes}
    for n in nodes:
        p = n["parent"]
        if p and p in by_id:
            by_id[p]["children"].append(n["node_id"])
    for n in nodes:
        n["children"].sort()
    nodes.sort(key=lambda n: n["node_id"])
    return {"schema_version": SCHEMA_VERSION, "root": ".", "nodes": nodes}


def _duplicate_ids(nodes):
    seen, dups = set(), set()
    for n in nodes:
        nid = n["node_id"]
        if nid in seen:
            dups.add(nid)
        seen.add(nid)
    return sorted(dups)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build wiki/corpus.json from the repo (deterministic).")
    ap.add_argument("--root", default=ROOT, help="tree to index (default: repo root)")
    ap.add_argument("--out", default=os.path.join("wiki", "corpus.json"),
                    help="output path (default: wiki/corpus.json)")
    args = ap.parse_args(argv)
    corpus = build_corpus(args.root)
    dups = _duplicate_ids(corpus["nodes"])
    if dups:   # node_id is the corpus primary key — fail loudly, never silently collapse
        sys.stderr.write("ERROR build_corpus: duplicate node_id(s): %s\n" % dups)
        return 1
    out = args.out if os.path.isabs(args.out) else os.path.join(args.root, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, indent=2, sort_keys=True)
        fh.write("\n")
    gaps = sum(1 for n in corpus["nodes"] if not n["summary_source"])
    unowned = sum(1 for n in corpus["nodes"] if n["owner_source"] == "none")
    print("wrote %s: %d nodes (%d summary gaps, %d unowned)"
          % (_rel(out, args.root), len(corpus["nodes"]), gaps, unowned))
    return 0


if __name__ == "__main__":
    sys.exit(main())
