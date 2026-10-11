"""
title: pytest markers read from source — which collected tests a marker call applies to
kind: script
layer: n/a
summary: The one reader of `pytest.mark.<name>(...)` calls, and of `mark.<name>(...)` after `from pytest import mark`, from a test file's syntax tree, shared by the end-to-end coverage gate (tests/integration/test_e2e_coverage.py) and requirement traceability (scripts/traceability.py). collection_rule and full_rule read the names pytest collects from a running session's ini, and collection_rule_from_ini reads the same four ini values (python_functions, python_classes, python_files, norecursedirs) outside a session by starting pytest in process with collection switched off, so nothing under the tests root is imported; it raises MarkerError when pytest is absent, exits with a usage error, or reads an ini file from outside the project. attached_markers says which marker calls sit on a collected test or in a `pytestmark`; marked_tests says which collected tests each call applies to, and an empty list means none; both count a definition only when pytest would collect it: its name matches, no later def, class, assignment, import or `del` of the same name replaces it, its `__test__` is not false, and a class defines neither `__init__` nor `__new__`. dir_recursed says whether pytest enters a directory (`norecursedirs`, a virtual environment, `__pycache__`); marker_ids returns a call's string-literal arguments or the reason they cannot be read. It judges by name, never by importing a test, so a skipped test still counts, a marker reached through any other name is not seen, and what only an import decides (an inherited `__init__`, a conftest's `collect_ignore`) is not seen either; tests/integration/test_requirement_traceability.py compares the reading with pytest's own collection. It writes nothing and is never run.
"""

from __future__ import annotations

import ast
import contextlib
import fnmatch
import io
import os
from typing import NamedTuple

__all__ = [
    "CollectionRule",
    "MarkerError",
    "attached_markers",
    "collected",
    "collection_rule",
    "collection_rule_from_ini",
    "dir_recursed",
    "file_collected",
    "full_rule",
    "is_marker",
    "marked_tests",
    "marker_ids",
]

# pytest's exit codes for "ran, with or without failures or tests": anything
# else means it never got as far as reading the ini (a usage or internal error).
_PYTEST_RAN = (0, 1, 5)


class MarkerError(Exception):
    """The collection rule could not be read: pytest is not importable, did not
    configure, or took its ini from outside the project."""


class CollectionRule(NamedTuple):
    """The four ini values that decide what pytest collects as a test:
    `python_functions`, `python_classes`, `python_files` and `norecursedirs`."""

    functions: tuple[str, ...]
    classes: tuple[str, ...]
    files: tuple[str, ...]
    norecurse: tuple[str, ...]


def is_marker(node, marker):
    """True when *node* is the attribute chain `<anything>.mark.<marker>`, or
    `mark.<marker>` on the bare name `from pytest import mark` binds."""
    if not (isinstance(node, ast.Attribute) and node.attr == marker):
        return False
    base = node.value
    return (isinstance(base, ast.Attribute) and base.attr == "mark") or (
        isinstance(base, ast.Name) and base.id == "mark"
    )


def collected(name, patterns):
    """True when pytest collects *name* under *patterns*: each is a prefix, or
    a glob when it holds a glob character, as pytest's own matcher reads it."""
    return any(
        name.startswith(p) or (any(c in p for c in "*?[") and fnmatch.fnmatch(name, p))
        for p in patterns
    )


_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)
# A class that defines either is one pytest refuses to collect, with a warning.
_CONSTRUCTORS = ("__init__", "__new__")
# The attribute pytest reads on a module, class or function: false means
# "not a test".
_SWITCH = "__test__"


def _bound(stmt):
    """The names *stmt* binds or deletes in its own scope: a def, a class, an
    import, an assignment target, and the same inside an `if`, `try`, `for` or
    `with` block, where whether it runs cannot be read from source. A nested
    def or class binds its own name and nothing from its body."""
    names, stack = set(), [stmt]
    while stack:
        node = stack.pop()
        if isinstance(node, _DEFS + (ast.ClassDef,)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.Lambda):
            pass
        else:
            if isinstance(node, ast.Name) and isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                names.add(node.id)
            stack.extend(ast.iter_child_nodes(node))
    return names


def _plain_assignments(stmt):
    """(target, value) for each target of `<target> = <value>` and of
    `<target>: <type> = <value>`; nothing for any other statement."""
    if isinstance(stmt, ast.Assign):
        return [(target, stmt.value) for target in stmt.targets]
    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        return [(stmt.target, stmt.value)]
    return []


def _on(value):
    # Only a constant can be read from source; anything computed is taken as
    # "off", so the marker under it is reported rather than counted.
    return isinstance(value, ast.Constant) and bool(value.value)


def _scope(body):
    """(live, off, bound) for the statements of one module or class body.
    *live* holds id() of each statement that is still what one of its names
    holds when the scope ends: a later def, class, assignment, import or `del`
    of the same name replaces an earlier one, and pytest collects only what the
    name holds last. *off* holds each name given a `__test__` that is not a
    true constant, by `<name>.__test__ = ...` or, for the scope itself, under
    the name `__test__`. *bound* is every name the scope binds."""
    last, off = {}, set()
    for stmt in body:
        bound = _bound(stmt)
        for name in bound:
            last[name] = stmt
        for target, value in _plain_assignments(stmt):
            if isinstance(target, ast.Name):
                switched, named = target.id, target.id
            elif isinstance(target, ast.Attribute) and isinstance(
                target.value, ast.Name
            ):
                switched, named = target.value.id, target.attr
            else:
                continue
            if named != _SWITCH:
                continue
            if _on(value):
                off.discard(switched)
            else:
                off.add(switched)
            bound.discard(_SWITCH)
        if _SWITCH in bound:
            # Bound by unpacking or inside a block: its value cannot be read
            # from source, so it is taken as off.
            off.add(_SWITCH)
    return {id(stmt) for stmt in last.values()}, off, set(last)


def _collected_defs(body, functions, classes):
    """(functions, classes, pytestmarks): the def, class and `pytestmark`
    statements of *body* that pytest acts on. A scope whose own `__test__` is
    off holds none. A def or class counts when its name matches the rule, it is
    still what the name holds when the scope ends, and its `__test__` is not
    off; a class also only when it defines neither `__init__` nor `__new__`
    and its own body is not switched off."""
    live, off, _ = _scope(body)
    if _SWITCH in off:
        return [], [], []
    marks = [s for s in body if _is_pytestmark(s) and id(s) in live]
    found, kept = [], []
    for stmt in body:
        if id(stmt) not in live or getattr(stmt, "name", None) in off:
            continue
        if isinstance(stmt, _DEFS) and collected(stmt.name, functions):
            found.append(stmt)
        elif isinstance(stmt, ast.ClassDef) and collected(stmt.name, classes):
            _, inner_off, inner = _scope(stmt.body)
            if _SWITCH not in inner_off and not inner.intersection(_CONSTRUCTORS):
                kept.append(stmt)
    return found, kept, marks


def _mark_items(stmt):
    value = stmt.value
    return value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]


def attached_markers(tree, marker, rule):
    """ids of the `<marker>(...)` calls that apply to a test pytest collects:
    a decorator of a collected test function or class, or an item of a
    module- or class-level `pytestmark`. Anything else marks nothing that
    runs, and so does a definition pytest never collects (_collected_defs)."""
    functions, classes = rule
    attached = set()

    def take(nodes):
        attached.update(
            id(n)
            for n in nodes
            if isinstance(n, ast.Call) and is_marker(n.func, marker)
        )

    def visit(body):
        found, kept, marks = _collected_defs(body, functions, classes)
        for stmt in marks:
            take(_mark_items(stmt))
        for stmt in found:
            take(stmt.decorator_list)
        for stmt in kept:
            take(stmt.decorator_list)
            visit(stmt.body)

    visit(tree.body)
    return attached


def collection_rule(config):
    """(python_functions, python_classes): the names pytest collects as tests,
    read from the running session's ini so a project that renames them is
    judged by its own rule."""
    return (
        tuple(config.getini("python_functions")),
        tuple(config.getini("python_classes")),
    )


def full_rule(config):
    """The CollectionRule of a pytest *config*: collection_rule plus the
    `python_files` patterns that decide which files are test modules and the
    `norecursedirs` patterns that decide which directories are never entered."""
    functions, classes = collection_rule(config)
    return CollectionRule(
        functions,
        classes,
        tuple(config.getini("python_files")),
        tuple(config.getini("norecursedirs")),
    )


def file_collected(rel, patterns):
    """True when pytest collects the file at POSIX path *rel* as a test module:
    a pattern with no `/` is matched against the file name, any other against
    the whole path, as pytest's own matcher does."""
    name = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(rel if "/" in p else name, p) for p in patterns)


def dir_recursed(path, rel, patterns):
    """True when pytest enters the directory at *path* (POSIX path *rel* below
    the project root) while collecting. It never enters `__pycache__`, the root
    of a virtual environment (a `pyvenv.cfg`, or a `conda-meta/history`), or a
    directory a `norecursedirs` pattern in *patterns* matches: a pattern with
    no `/` against the directory's name, any other against the end of its path,
    as pytest's own matcher does."""
    name = rel.rsplit("/", 1)[-1]
    if name == "__pycache__":
        return False
    if os.path.isfile(os.path.join(path, "pyvenv.cfg")) or os.path.isfile(
        os.path.join(path, "conda-meta", "history")
    ):
        return False
    return not any(
        fnmatch.fnmatch("/" + rel, "*/" + p) if "/" in p else fnmatch.fnmatch(name, p)
        for p in patterns
    )


def _is_pytestmark(stmt):
    return isinstance(stmt, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets
    )


def marked_tests(tree, marker, rule):
    """{id(call): [test, ...]} for every `<marker>(...)` call in *tree* that
    sits where pytest reads a marker: the collected tests it applies to, each
    as `function` or `Class::method`, sorted. A decorator on a collected
    function names that function; on a collected class, every collected test
    under it; an item of a module- or class-level `pytestmark`, every collected
    test in that scope. An empty list means the call applies to no test pytest
    collects: it decorates a helper, a definition a later statement replaces or
    a class pytest does not collect (_collected_defs), or its scope holds no
    collected test. A call anywhere else (a function body, an argument of
    another call) has no entry."""
    functions, classes = rule[0], rule[1]
    out = {}

    def tests_in(body, prefix):
        found, kept, _ = _collected_defs(body, functions, classes)
        names = [prefix + stmt.name for stmt in found]
        for stmt in kept:
            names.extend(tests_in(stmt.body, prefix + stmt.name + "::"))
        return names

    def take(nodes, tests):
        for node in nodes:
            if isinstance(node, ast.Call) and is_marker(node.func, marker):
                out[id(node)] = sorted(set(out.get(id(node), [])) | set(tests))

    def visit(body, prefix):
        found, kept, marks = _collected_defs(body, functions, classes)
        acted = {id(stmt) for stmt in found + kept + marks}
        for stmt in body:
            if _is_pytestmark(stmt):
                take(
                    _mark_items(stmt),
                    tests_in(body, prefix) if id(stmt) in acted else [],
                )
            elif isinstance(stmt, _DEFS):
                take(
                    stmt.decorator_list,
                    [prefix + stmt.name] if id(stmt) in acted else [],
                )
            elif isinstance(stmt, ast.ClassDef) and id(stmt) in acted:
                inner = prefix + stmt.name + "::"
                take(stmt.decorator_list, tests_in(stmt.body, inner))
                visit(stmt.body, inner)
            elif isinstance(stmt, ast.ClassDef):
                take(stmt.decorator_list, [])
                # Its methods and `pytestmark` sit where pytest would read a
                # marker, on a class it never collects: each applies to no test.
                visit_dead(stmt.body)

    def visit_dead(body):
        for stmt in body:
            if _is_pytestmark(stmt):
                take(_mark_items(stmt), [])
            elif isinstance(stmt, _DEFS + (ast.ClassDef,)):
                take(stmt.decorator_list, [])
                if isinstance(stmt, ast.ClassDef):
                    visit_dead(stmt.body)

    visit(tree.body, "")
    return out


def marker_ids(call):
    """(ids, None) when every argument of the marker *call* is a positional
    string literal and there is at least one; ([], reason) otherwise. An
    f-string, a name, a keyword or a non-string constant cannot be read from
    source, so it is an error rather than a guess."""
    if call.keywords:
        return [], "takes no keyword argument"
    if not call.args:
        return [], "names no id"
    ids = []
    for arg in call.args:
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            return [], "takes string literals only"
        ids.append(arg.value)
    return ids, None


class _Probe:
    """A pytest plugin that records the collection rule once pytest has read
    its ini, then reports collection as already done so no test file is read."""

    rule = None
    inipath = None

    def pytest_configure(self, config):
        self.rule = full_rule(config)
        self.inipath = config.inipath

    def pytest_collection(self, session):
        return True


def collection_rule_from_ini(root, tests_root):
    """The CollectionRule pytest would use for the tests under
    *root*/*tests_root*, read without a running session: pytest starts in
    process, reads its ini as it would for that directory, and collects
    nothing. Raises MarkerError when pytest is not importable, did not
    configure, or found its ini outside *root* (a parent directory's file would
    judge this project by another project's rule)."""
    try:
        import pytest
    except ImportError as exc:
        raise MarkerError(
            "pytest is not importable (%s); install the `dev` extra" % exc
        ) from None
    probe = _Probe()
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        code = pytest.main(
            [
                "--collect-only",
                "-q",
                "--noconftest",
                "-p",
                "no:cacheprovider",
                "--rootdir",
                str(root),
                os.path.join(str(root), tests_root),
            ],
            plugins=[probe],
        )
    if probe.rule is None or int(code) not in _PYTEST_RAN:
        raise MarkerError(
            "pytest could not read its collection rule for %s (exit %d)"
            % (tests_root, int(code))
        )
    if probe.inipath is not None:
        real_root = os.path.realpath(str(root))
        ini = os.path.realpath(str(probe.inipath))
        if os.path.commonpath([real_root, ini]) != real_root:
            raise MarkerError(
                "pytest read its ini from outside the project (%s); give the "
                "project its own [tool.pytest.ini_options]" % os.path.basename(ini)
            )
    return probe.rule
