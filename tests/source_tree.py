"""
title: Test helper — the one reader of the Python tree the gate tests judge
kind: tests
layer: n/a
summary: The walk, the parse and the token readers every tree-wide gate test shares, so no two gates own a different idea of which files are the project's or of what an import points at. `python_files` lists every `*.py` that scripts/check_structure.py `walk` reaches (its IGNORE_DIRS keep vendored and installed code out); `parse` reads one into a syntax tree and raises SourceTreeError naming the file it cannot; `import_edges` resolves every `import` and `from ... import` to the project file it loads, through an ordered list of search roots, skipping a name the standard library owns; `unresolved_imports` lists each import of the project (an absolute name whose first segment a search root holds as a module or a directory, or any relative name) that loads no file, so a caller can fail loudly instead of reading it as external; `comment_starts` lists the comments that open a thought, read through tokenize so a `#` inside a string is never one; `noqa_reasons` reads each `# noqa: CODE <sep> reason` suppression, taking the codes separated by commas or spaces as ruff does. It cannot see an import made through importlib, `__import__` or a `sys.path` entry no search root names: such a name does not resolve and is treated as external.
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


def _is_project_head(root, search_roots, head):
    """True when some search root holds *head* as a module or a directory: an
    import starting with it is the project's, so failing to resolve it is a
    missing file, never an installed name."""
    for search_root in search_roots:
        base = os.path.join(str(root), search_root + head)
        if os.path.isfile(base + _PY) or os.path.isdir(base):
            return True
    return False


def _targets(node, importer, root, search_roots):
    """`(found, missing)` for one import statement: the project files it loads,
    each resolved through the search roots or, for a relative import, from the
    importer's package; and the dotted names it imports from the project that
    resolve to no file."""
    out, missing = [], []
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
            else:
                if _is_project_head(root, search_roots, parts[0]):
                    missing.append(alias.name)
        return out, missing
    if not isinstance(node, ast.ImportFrom):
        return out, missing
    module_parts = node.module.split(".") if node.module else []
    if node.level == 0:
        if not module_parts or module_parts[0] in sys.stdlib_module_names:
            return out, missing
        roots = search_roots
    else:
        package = _package_parts(importer)
        if node.level - 1 > len(package):
            return out, missing
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
        elif node.level or _is_project_head(root, roots, module_parts[0]):
            missing.append("." * node.level + ".".join(module_parts + [alias.name]))
    return out, missing


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
            for imported in _targets(node, importer, root, search_roots)[0]:
                if imported != importer:
                    edges.add((importer, node.lineno, imported))
    return sorted(edges)


def unresolved_imports(root, files, search_roots):
    """Every import in *files* that names the project yet loads no file, as a
    sorted list of `(importer, lineno, dotted name)`. An absolute import names
    the project when a search root holds its first segment as a module or a
    directory; a relative import always does."""
    misses = set()
    for importer in files:
        tree = parse(root, importer)
        for node in ast.walk(tree):
            for name in _targets(node, importer, root, search_roots)[1]:
                misses.add((importer, node.lineno, name))
    return sorted(misses)


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


# --- environment reads -------------------------------------------------------------

_ENVIRON = "environ"
# The environ methods that read a variable by name.
_ENV_CALLS = ("get", "pop", "setdefault")
_GETENV = "getenv"


def module_strings(tree):
    """{NAME: value} for every module-level `NAME = "literal"`."""
    out = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def is_environ(node):
    """True for `environ` or `<anything>.environ`."""
    return (isinstance(node, ast.Attribute) and node.attr == _ENVIRON) or (
        isinstance(node, ast.Name) and node.id == _ENVIRON
    )


def string_of(node, constants):
    """The string *node* spells: a literal, or a name in *constants*; else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def env_reads(tree):
    """`(lineno, name)` for every environment variable *tree* reads by a name
    it spells, sorted: through `environ[...]`, `environ.get/pop/setdefault(...)`,
    `... in environ` or `getenv(...)`, the name a literal or a module-level
    string constant. A name held in any other variable is not seen."""
    constants = module_strings(tree)
    found = set()
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            if is_environ(node.value):
                name = string_of(node.slice, constants)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.args
        ):
            func = node.func
            if (
                func.attr in _ENV_CALLS and is_environ(func.value)
            ) or func.attr == _GETENV:
                name = string_of(node.args[0], constants)
        elif (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.In)
            and is_environ(node.comparators[0])
        ):
            name = string_of(node.left, constants)
        if name:
            found.add((node.lineno, name))
    return sorted(found)


def python_env_reads(path):
    """The names of every environment variable the file at *path* reads by a
    name it spells (env_reads)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    return {name for _lineno, name in env_reads(tree)}


# --- config-file reads -------------------------------------------------------------

# The callables that build a path from segments: os.path/posixpath/ntpath
# `join` and the pathlib constructors. `str.join` matches too, harmlessly: its
# one argument is an iterable, never a constant segment.
_JOINERS = ("join", "Path", "PurePath", "PosixPath", "PurePosixPath")
_JOINPATH = "joinpath"
_OPEN = "open"
_SPLIT = "split"
# Methods of a path object that read the file it names.
_PATH_READERS = ("read_text", "read_bytes", "open")


def _split(text):
    """The segments of a path string, either separator, `.` and empty dropped."""
    return [p for p in text.replace("\\", "/").split("/") if p not in ("", ".")]


def _callee(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _segments(node, scope):
    """The path segments *node* spells, None standing for one it cannot read;
    None overall when *node* is no path expression. *scope* is
    {"paths": {name: segments}, "parts": {name: [str]}}: names bound to a path
    expression, and names bound to a tuple of string constants (read only
    through `*name`); "modules" is {name: {NAME: segments}}, the module-level
    path constants (module_paths) of the project module each imported name
    binds."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _split(node.value)
    if isinstance(node, ast.Name):
        return scope["paths"].get(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        found = scope["modules"].get(node.value.id, {}).get(node.attr)
        return None if found is None else list(found)
    if isinstance(node, ast.Call):
        name = _callee(node.func)
        head = []
        if name == _JOINPATH and isinstance(node.func, ast.Attribute):
            head = _segments(node.func.value, scope) or [None]
        elif name not in _JOINERS:
            return None
        out = list(head)
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                parts = _parts(arg.value, scope)
                out.extend(parts if parts is not None else [None])
            else:
                seg = _segments(arg, scope)
                out.extend(seg if seg is not None else [None])
        return out
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _segments(node.left, scope)
        right = _segments(node.right, scope)
        if left is None and right is None:
            return None
        return (left or [None]) + (right or [None])
    return None


def _parts(node, scope):
    """The segments of a tuple of string constants, literal or bound to a
    name; None for anything else."""
    if isinstance(node, ast.Name):
        return scope["parts"].get(node.id)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == _SPLIT
    ):
        # `*TEXT.split("/")`: the segments of the text, which _split takes
        # apart on either separator already.
        seg = _segments(node.func.value, scope)
        return seg if seg is not None and None not in seg else None
    if isinstance(node, (ast.Tuple, ast.List)) and all(
        isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts
    ):
        return [p for e in node.elts for p in _split(e.value)]
    return None


def _declared(segments, declared):
    """The declared path whose segments end *segments*, else None."""
    if not segments:
        return None
    for path, parts in declared:
        n = len(parts)
        if len(segments) >= n and segments[-n:] == parts:
            return path
    return None


def _read_paths(call):
    """The expressions a call reads a file from: the argument of `open`,
    `io.open` and the like, and the object of `.read_text()`, `.read_bytes()`
    and `.open()`."""
    func = call.func
    out = []
    first = call.args[0] if call.args else None
    if first is None:
        first = next((k.value for k in call.keywords if k.arg == "file"), None)
    if isinstance(func, ast.Name) and func.id == _OPEN and first is not None:
        out.append(first)
    elif isinstance(func, ast.Attribute):
        if func.attr in _PATH_READERS:
            out.append(func.value)
        if func.attr == _OPEN and first is not None:
            out.append(first)
    return out


def _bind(scope, target, value):
    """Record or forget *target* in *scope* by what *value* is."""
    if not isinstance(target, ast.Name):
        return
    name = target.id
    scope["paths"].pop(name, None)
    scope["parts"].pop(name, None)
    parts = _parts(value, scope)
    if parts is not None and not isinstance(value, ast.Name):
        scope["parts"][name] = parts
        return
    seg = _segments(value, scope)
    if seg is not None:
        scope["paths"][name] = seg


def _assigns(body):
    """The `name = value` pairs a body binds, in source order, not entering a
    nested function or class."""
    out = []
    stack = list(body)
    while stack:
        node = stack.pop(0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Assign):
            out.extend((node.lineno, target, node.value) for target in node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            out.append((node.lineno, node.target, node.value))
        stack.extend(ast.iter_child_nodes(node))
    return sorted(out, key=lambda item: item[0])


def _scope_at(base, assigns, lineno):
    """*base* updated by the *assigns* made before *lineno*."""
    scope = dict(base, paths=dict(base["paths"]), parts=dict(base["parts"]))
    for line, target, value in assigns:
        if line < lineno:
            _bind(scope, target, value)
    return scope


def _mentions(node, names):
    return any(isinstance(n, ast.Name) and n.id in names for n in ast.walk(node))


def _param_names(func):
    args = func.args
    return [a.arg for a in getattr(args, "posonlyargs", []) + args.args]


def _opening_params(functions):
    """{function name: {parameter index}} for each module-level function that
    opens what a parameter names, directly or through another such function,
    to a fixed point."""
    opens = {name: set() for name in functions}
    changed = True
    while changed:
        changed = False
        for name, func in functions.items():
            params = _param_names(func)
            # A local name built from a parameter carries it.
            carriers = {p: {p} for p in params}
            for _line, target, value in _assigns(func.body):
                if isinstance(target, ast.Name):
                    for p in params:
                        if _mentions(value, carriers[p]):
                            carriers[p].add(target.id)
            for node in ast.walk(func):
                if not isinstance(node, ast.Call):
                    continue
                handed = list(_read_paths(node))
                callee = _callee(node.func)
                if isinstance(node.func, ast.Name) and callee in opens:
                    handed += _handed(node, functions[callee], opens[callee])
                for index, p in enumerate(params):
                    if index in opens[name]:
                        continue
                    if any(_mentions(expr, carriers[p]) for expr in handed):
                        opens[name].add(index)
                        changed = True
    return opens


def _handed(call, func, indexes):
    """The arguments *call* passes at the parameter *indexes* of *func*."""
    params = _param_names(func)
    out = []
    for index in sorted(indexes):
        if index < len(call.args) and not isinstance(call.args[index], ast.Starred):
            out.append(call.args[index])
        out.extend(
            keyword.value
            for keyword in call.keywords
            if index < len(params) and keyword.arg == params[index]
        )
    return out


def _calls_by_scope(tree):
    """`(call, function or None)` for every call, with the innermost
    function that holds it."""
    out = []

    def visit(node, func):
        for child in ast.iter_child_nodes(node):
            inner = func
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = child
            if isinstance(child, ast.Call):
                out.append((child, inner))
            visit(child, inner)

    visit(tree, None)
    return out


def module_paths(tree):
    """{NAME: segments} for every module-level name *tree* binds to a path
    expression (a string constant, or a join or pathlib construction of
    constants and of names bound so before it), None standing for a segment
    it cannot read, as _segments spells it."""
    scope = {"paths": {}, "parts": {}, "modules": {}}
    for _line, target, value in _assigns(tree.body):
        _bind(scope, target, value)
    return scope["paths"]


def _import_pairs(node):
    """`(bound name, dotted parts, imported name or None)` for each name a
    module-level absolute import statement binds: `import a.b as n` binds
    the module a.b; `from a import b` binds b, which is either the module
    a.b or the name b of module a, so the imported name rides along."""
    if isinstance(node, ast.Import):
        # `import a.b` binds `a`, not `a.b`, so only an aliased dotted
        # import names the module itself.
        return [
            (alias.asname or alias.name, alias.name.split("."), None)
            for alias in node.names
            if alias.asname or "." not in alias.name
        ]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [
            (
                alias.asname or alias.name,
                node.module.split(".") + [alias.name],
                alias.name,
            )
            for alias in node.names
            if alias.name != "*"
        ]
    return []


def imported_paths(root, tree, search_roots):
    """{"modules": {name: {NAME: segments}}, "names": {name: segments}} for
    the module-level absolute imports in *tree* that reach a project module
    through *search_roots*: "modules" for a name bound to a module (its
    module_paths), "names" for a name bound to one of a module's path
    constants (`from a import NAME [as n]`)."""
    modules = {}
    names = {}
    for node in tree.body:
        for bound, parts, imported in _import_pairs(node):
            if parts[0] in sys.stdlib_module_names:
                continue
            found = _resolve(root, search_roots, parts)
            if found is not None:
                modules[bound] = module_paths(parse(root, found))
                continue
            if imported is None:
                continue
            owner = _resolve(root, search_roots, parts[:-1])
            if owner is not None:
                segments = module_paths(parse(root, owner)).get(imported)
                if segments is not None:
                    names[bound] = segments
    return {"modules": modules, "names": names}


def config_path_reads(tree, declared, imported=None):
    """`(lineno, path)` for every read in *tree* of a file in *declared*
    (repo-relative posix paths), sorted. A read is an `open`/`io.open`/`.open`
    call, or `.read_text`/`.read_bytes`/`.open` on a path object, whose path
    is a string constant naming the file, a join or pathlib construction of
    constants whose last segments are its parts (a `*NAME` of a tuple of
    constants, or `*TEXT.split(...)` of such a string, included), a name bound
    to one at module level or earlier in the same function, a path constant
    of another project module bound by name (`from mod import NAME`), or
    `mod.NAME` of such a constant (*imported* is imported_paths); or a call
    to a module-level function of *tree* that opens the parameter the path is
    handed to. A path handed in from outside, opened by a function of
    another module, or built from a value that is not a constant is not seen;
    neither is a probe such as getmtime or exists, which reads no content."""
    wanted = [(p, _split(p)) for p in sorted(declared)]
    if not wanted:
        raise SourceTreeError("no declared config file to look for -- zero items")
    imported = imported or {}
    module = {
        "paths": dict(imported.get("names", {})),
        "parts": {},
        "modules": dict(imported.get("modules", {})),
    }
    for _line, target, value in _assigns(tree.body):
        _bind(module, target, value)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    opens = _opening_params(functions)
    assigns = {}
    found = set()
    for call, func in _calls_by_scope(tree):
        if func is None:
            scope = module
        else:
            if func not in assigns:
                assigns[func] = _assigns(func.body)
            scope = _scope_at(module, assigns[func], call.lineno)
        exprs = list(_read_paths(call))
        callee = _callee(call.func)
        if isinstance(call.func, ast.Name) and opens.get(callee):
            exprs += _handed(call, functions[callee], opens[callee])
        for expr in exprs:
            path = _declared(_segments(expr, scope), wanted)
            if path is not None:
                found.add((call.lineno, path))
    return sorted(found)
