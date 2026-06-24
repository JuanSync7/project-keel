"""
title: Showcase markdown extraction
layer: backend
public_api: no
summary: Pure helpers that pull a node's renderable markdown body out of source text.
"""
from __future__ import annotations

import ast
import re

_HEADING = re.compile(r"^(#{1,6})\s")


def strip_frontmatter(text: str) -> str:
    """Return the markdown body after a leading --- frontmatter block (if any)."""
    if not text.startswith("---"):
        return text
    lines = text.splitlines()
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:])
    return text  # unterminated block -> treat the whole thing as body


def section_slice(body: str, lineno) -> str:
    """Return the markdown of one section: its heading down to the next heading
    of the same or higher level. ``lineno`` is 1-based within ``body`` (the
    post-frontmatter body), matching build_corpus's section lineno."""
    lines = body.splitlines()
    if not isinstance(lineno, int) or lineno < 1 or lineno > len(lines):
        return body
    start = lineno - 1
    m = _HEADING.match(lines[start])
    level = len(m.group(1)) if m else 6
    out = [lines[start]]
    for ln in lines[start + 1:]:
        hm = _HEADING.match(ln)
        if hm and len(hm.group(1)) <= level:
            break
        out.append(ln)
    return "\n".join(out).strip("\n")


def module_docstring(text: str) -> str:
    """Return a Python module's docstring, or ''."""
    try:
        return ast.get_docstring(ast.parse(text)) or ""
    except (SyntaxError, ValueError):
        return ""


def symbol_docstring(text: str, name: str) -> str:
    """Return the docstring of a top-level def/class named ``name``, or ''."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return ""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.name == name:
            return ast.get_docstring(node) or ""
    return ""


__all__ = [
    "strip_frontmatter", "section_slice", "module_docstring", "symbol_docstring",
]
