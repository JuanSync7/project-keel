"""
title: Test helper — the one reader of the Python tree the gate tests judge
kind: tests
layer: n/a
summary: The walk, the parse and the token readers every tree-wide gate test shares, so no two gates own a different idea of which files are the project's or of what an import points at. `python_files` lists every `*.py` that scripts/check_structure.py `walk` reaches (its IGNORE_DIRS keep vendored and installed code out); `parse` reads one into a syntax tree and raises SourceTreeError naming the file it cannot; `import_edges` resolves every `import` and `from ... import` to the project file it loads, through an ordered list of search roots, skipping a name the standard library owns; `comment_starts` lists the comments that open a thought, read through tokenize so a `#` inside a string is never one; `noqa_reasons` reads each `# noqa: CODE <sep> reason` suppression, taking the codes separated by commas or spaces as ruff does. It cannot see an import made through importlib, `__import__` or a `sys.path` entry no search root names: such a name does not resolve and is treated as external.
"""

import ast
import io
import json
import os
import sys
import tokenize

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import check_structure as cs  # noqa: E402

_PY = ".py"
_INIT = "__init__.py"
# A comment that ends a sentence, so the comment line after it opens a new one.
_SENTENCE_ENDS = (".", ":", ";", "?", "!")
_NOQA = "noqa:"
# The separators a suppression's reason may follow its codes with: an em dash,
# two hyphens or a colon. A reason written straight after the codes is read too.
_REASON_SEPARATORS = ("—", "--", ":")


class SourceTreeError(AssertionError):
    """The gate cannot judge: nothing to walk, or a file it cannot parse."""


def python_files(root):
    """Every `*.py` under *root* the structure gate walks, as sorted relative
    posix paths."""
    found = []
    for dirpath, _dirnames, filenames in cs.walk(str(root)):
        for name in filenames:
            if name.endswith(_PY):
                full = os.path.join(dirpath, name)
                found.append(os.path.relpath(full, str(root)).replace(os.sep, "/"))
    return sorted(found)


def read(root, relpath):
    """The UTF-8 text of *relpath* under *root*, or SourceTreeError naming it."""
    try:
        with open(os.path.join(str(root), relpath), encoding="utf-8") as fh:
            return fh.read()
    except cs.UNREADABLE as exc:
        raise SourceTreeError("%s: cannot be read (%s)" % (relpath, exc)) from exc


def parse(root, relpath):
    """The syntax tree of *relpath* under *root*, or SourceTreeError naming it."""
    text = read(root, relpath)
    try:
        return ast.parse(text, filename=relpath)
    except cs.UNPARSEABLE as exc:
        raise SourceTreeError("%s: cannot be parsed (%s)" % (relpath, exc)) from exc


# --- the import policy ------------------------------------------------------------

CONFIG = "config/project.json"
LAYERS_BLOCK = "import_layers"


def import_layers(root):
    """config/project.json `import_layers` under *root*, validated:
    {search_roots, order, may_end_the_process}. Raises SourceTreeError naming
    what is malformed, because a gate that cannot read its policy must not
    pass."""
    path = os.path.join(str(root), CONFIG)
    try:
        with open(path, encoding="utf-8") as fh:
            block = json.load(fh).get(LAYERS_BLOCK)
    except (OSError, ValueError) as exc:
        raise SourceTreeError("%s: cannot be read (%s)" % (CONFIG, exc)) from exc
    if not isinstance(block, dict):
        raise SourceTreeError("%s: no `%s` block" % (CONFIG, LAYERS_BLOCK))
    roots = block.get("search_roots")
    if not isinstance(roots, list) or not all(
        isinstance(r, str) and (r == "" or r.endswith("/")) for r in roots
    ):
        raise SourceTreeError(
            "%s: %s.search_roots is not a list of '' or 'dir/' strings"
            % (CONFIG, LAYERS_BLOCK)
        )
    order = block.get("order")
    layers = order if isinstance(order, list) else []
    entries = [e for layer in layers if isinstance(layer, list) for e in layer]
    if (
        not layers
        or not all(isinstance(layer, list) and layer for layer in layers)
        or not all(isinstance(e, str) and e and not e.endswith("/") for e in entries)
        or len(entries) != len(set(entries))
    ):
        raise SourceTreeError(
            "%s: %s.order is not a non-empty list of non-empty lists of distinct "
            "path prefixes" % (CONFIG, LAYERS_BLOCK)
        )
    enders = block.get("may_end_the_process", {})
    if not isinstance(enders, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and not blank(v)
        for k, v in enders.items()
    ):
        raise SourceTreeError(
            "%s: %s.may_end_the_process is not a map of module path to a "
            "non-blank reason" % (CONFIG, LAYERS_BLOCK)
        )
    return {"search_roots": roots, "order": order, "may_end_the_process": enders}


# --- imports -----------------------------------------------------------------------


def _resolve(root, search_roots, parts):
    """The relative path of the project file the dotted *parts* name, from the
    first search root holding `<parts>.py` or `<parts>/__init__.py`; None when
    no root holds it, which makes the name external."""
    if not parts:
        return None
    tail = "/".join(parts)
    for search_root in search_roots:
        for candidate in (search_root + tail + _PY, search_root + tail + "/" + _INIT):
            if os.path.isfile(os.path.join(str(root), candidate)):
                return candidate
    return None


def _package_parts(importer):
    """The directory segments of *importer*: the package a relative import
    in it starts from."""
    return importer.split("/")[:-1]


def _targets(node, importer, root, search_roots):
    """The project files one import statement loads, each resolved through
    the search roots or, for a relative import, from the importer's package."""
    out = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            parts = alias.name.split(".")
            if parts[0] in sys.stdlib_module_names:
                continue
            # `import a.b.c` binds `a` and loads each package down to `a.b.c`;
            # the deepest one the project holds is the edge.
            for size in range(len(parts), 0, -1):
                found = _resolve(root, search_roots, parts[:size])
                if found:
                    out.append(found)
                    break
        return out
    if not isinstance(node, ast.ImportFrom):
        return out
    module_parts = node.module.split(".") if node.module else []
    if node.level == 0:
        if not module_parts or module_parts[0] in sys.stdlib_module_names:
            return out
        roots = search_roots
    else:
        package = _package_parts(importer)
        if node.level - 1 > len(package):
            return out
        package = package[: len(package) - (node.level - 1)]
        # A relative import is anchored at the repository root, never searched.
        roots = [("/".join(package) + "/") if package else ""]
        module_parts = []  # the package path already sits in the anchor
        if node.module:
            module_parts = node.module.split(".")
    for alias in node.names:
        found = None
        if alias.name != "*":
            found = _resolve(root, roots, module_parts + [alias.name])
        if found is None:
            found = _resolve(root, roots, module_parts)
            if found is None and node.level and not module_parts:
                found = _resolve_package(root, roots[0])
        if found:
            out.append(found)
    return out


def _resolve_package(root, anchor):
    """`from . import name` where *name* is no submodule: the edge is the
    package's own `__init__.py`, when it has one."""
    candidate = anchor + _INIT
    if os.path.isfile(os.path.join(str(root), candidate)):
        return candidate
    return None


def import_edges(root, files, search_roots):
    """Every import in *files* that loads another project file, as a sorted
    list of `(importer, lineno, imported)` relative paths. A name the standard
    library owns is never resolved to a project file, and a name no search
    root holds is external and left out; an edge from a file to itself is
    left out too."""
    edges = set()
    for importer in files:
        tree = parse(root, importer)
        for node in ast.walk(tree):
            for imported in _targets(node, importer, root, search_roots):
                if imported != importer:
                    edges.add((importer, node.lineno, imported))
    return sorted(edges)


# --- comments ----------------------------------------------------------------------


def _comment_tokens(root, relpath):
    """`(lineno, text, trailing)` for every COMMENT token in *relpath*;
    *trailing* is True when code stands before it on its line."""
    text = read(root, relpath)
    out = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError) as exc:
        raise SourceTreeError("%s: cannot be tokenized (%s)" % (relpath, exc)) from exc
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            row, col = tok.start
            out.append((row, tok.string, bool(tok.line[:col].strip())))
    return out


def _body(comment):
    """A comment's text after its `#` marks, stripped."""
    return comment.lstrip("#").strip()


def _is_rule(body):
    """True for a comment with no letter or digit: a blank `#` or a ruled line."""
    return not any(ch.isalnum() for ch in body)


def comment_starts(root, relpath):
    """`(lineno, text)` of every comment in *relpath* that opens a thought: a
    trailing comment, the first line of a run of comment lines, or a comment
    line after one that ends a sentence (`. : ; ? !`) or holds no word."""
    out = []
    previous = None  # (lineno, body) of the comment line before this one
    for lineno, text, trailing in _comment_tokens(root, relpath):
        body = _body(text)
        opens = (
            trailing
            or previous is None
            or previous[0] != lineno - 1
            or previous[1].endswith(_SENTENCE_ENDS)
            or _is_rule(previous[1])
        )
        if opens:
            out.append((lineno, text))
        previous = (lineno, body)
    return out


def _noqa_part(comment):
    """The text after `noqa:` when *comment* holds a suppression, else None.
    A suppression opens the comment or follows a `#` inside it."""
    pieces = comment.split("#")
    for index in range(1, len(pieces)):
        if pieces[index].strip().lower().startswith(_NOQA):
            # The reason may itself hold a `#`, so it is everything after.
            rest = "#".join(pieces[index:]).strip()
            return rest[len(_NOQA) :]
    return None


def _code_end(rest, start):
    """The end of the rule code at *start* in *rest*, else *start*. A code is
    ruff's shape: capital letters, then digits (`BLE001`, `E722`)."""
    i = start
    while i < len(rest) and "A" <= rest[i] <= "Z":
        i += 1
    letters_end = i
    while i < len(rest) and "0" <= rest[i] <= "9":
        i += 1
    if letters_end == start or i == letters_end:
        return start
    return i


def _split_codes(rest):
    """`(codes, remainder)`: the rule codes at the start of *rest*, separated
    by commas or spaces as ruff reads them, and the text after the last one.
    A second code is never the start of the reason, because ruff honours it."""
    codes = []
    i = 0
    while i < len(rest) and rest[i] == " ":
        i += 1
    end = _code_end(rest, i)
    while end != i:
        codes.append(rest[i:end])
        i = end
        j = i
        while j < len(rest) and (rest[j] == "," or rest[j].isspace()):
            j += 1
        end = _code_end(rest, j)
        if end != j:
            i = j
    return codes, rest[i:]


def noqa_reasons(root, relpath):
    """{lineno: (codes, reason)} for every `# noqa: CODE[, CODE] <sep> reason`
    in *relpath*; *reason* is the stripped text after the separator, and is
    empty when the suppression gives none."""
    out = {}
    for lineno, text, _trailing in _comment_tokens(root, relpath):
        rest = _noqa_part(text)
        if rest is None:
            continue
        codes, remainder = _split_codes(rest)
        remainder = remainder.strip()
        for separator in _REASON_SEPARATORS:
            if remainder.startswith(separator):
                remainder = remainder[len(separator) :].strip()
                break
        out[lineno] = (tuple(codes), remainder)
    return out


def blank(reason):
    """True when *reason* holds no letter or digit: punctuation is no reason."""
    return not any(ch.isalnum() for ch in reason)
