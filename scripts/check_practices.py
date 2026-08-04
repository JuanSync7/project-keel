#!/usr/bin/env python3
"""
title: Coding-practices advisor
kind: script
layer: n/a
summary: Read-only advisory. Flags coding-practice SMELLS - a concrete backend constructed inline instead of injected, a long isinstance chain that wants singledispatch, a hot-path class without __slots__, a resource acquired outside a context manager. Judgment calls that over/under-flag, so advisory only; never fails the build. Stdlib only; runs on Python 3.6+.
"""
import argparse
import ast
import io
import json
import os
import re
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The doer/domain code an advisory should look at. Transport adapters (api/, mcp/)
# and tests/ are intentionally excluded - speaking a framework's dialect there is
# correct, and test code is not a boundary.
SCAN_ROOTS = ["src", "agents"]

IGNORE_DIRS = {
    ".git", "node_modules", ".venv", "__pycache__", "dist", "build",
    ".mypy_cache", ".ruff_cache", ".pytest_cache",
}

_PRAGMA_RE = re.compile(r"^#\s*practice-ok\b\s*:?\s*(.*)$")
_HOTPATH_MARKER = "hot-path"


# --- io helpers (stdlib, 3.6-safe) --------------------------------------------

def _read(path):
    try:
        with io.open(path, encoding="utf-8-sig") as fh:   # strips a BOM if present
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def _read_json(path):
    try:
        with io.open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _parse(text):
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def _py_files(base):
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in IGNORE_DIRS and not d.startswith(".")]
        # Stays INSIDE the walk loop: hoisting it out would drop the prune above.
        out.extend(os.path.join(dirpath, fn)
                   for fn in filenames if fn.endswith(".py"))
    return out


def _comment_lines(text, needle):
    """Line numbers of `# ...<needle>...` comments (tokenize, so a `#` inside a
    string is never mistaken for a comment)."""
    out = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT and needle in tok.string:
                out.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    return out


def _pragma_lines(text):
    """line number -> reason for every `# practice-ok[: reason]` comment."""
    out = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                m = _PRAGMA_RE.match(tok.string.strip())
                if m:
                    out[tok.start[0]] = m.group(1).strip()
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    return out


def _suppressed(line, pragma):
    return line in pragma


# --- config -------------------------------------------------------------------

def load_registry():
    """The vendor-neutral practices registry (config/practices.json), or {}."""
    return _read_json(os.path.join(ROOT, "config", "practices.json"))


def profiles_on():
    """Set of domain profiles a repo has enabled in config/project.json."""
    proj = _read_json(os.path.join(ROOT, "config", "project.json"))
    prof = (proj.get("practices") or {}).get("profiles") or {}
    return {k for k, v in prof.items()
            if v is True and not k.startswith("_")}


# --- smell detectors (pure: take an AST, return findings) ---------------------

def _callee_name(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_true(node):
    if isinstance(node, ast.Constant):                    # 3.8+
        return node.value is True
    return node.__class__.__name__ == "NameConstant" and getattr(node, "value", None) is True


def find_di_inline(tree, provider_names):
    """A registered provider constructor called anywhere (not passed in)."""
    prov = set(provider_names or [])
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _callee_name(node.func)
            if name and name in prov:
                out.append({"kind": "dependency-injection",
                            "line": getattr(node, "lineno", 0),
                            "message": "provider '%s' constructed inline; "
                                       "inject it via a parameter instead" % name})
    return out


def _isinstance_subject(test):
    """The dumped first-arg of an ``isinstance(x, ...)`` test, else None."""
    if isinstance(test, ast.Call) and _callee_name(test.func) == "isinstance" and test.args:
        return ast.dump(test.args[0])
    return None


def find_isinstance_chains(tree, min_branches=3):
    """An if/elif chain with >= min_branches isinstance tests on ONE subject."""
    out = []
    consumed = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or id(node) in consumed:
            continue
        subj = _isinstance_subject(node.test)
        if subj is None:
            continue
        count, cur = 1, node
        while len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If) \
                and _isinstance_subject(cur.orelse[0].test) == subj:
            cur = cur.orelse[0]
            consumed.add(id(cur))
            count += 1
        if count >= min_branches:
            out.append({"kind": "singledispatch-over-isinstance",
                        "line": getattr(node, "lineno", 0),
                        "message": "%d isinstance branches on one value; "
                                   "consider functools.singledispatch" % count})
    return out


def _has_slots(cls):
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
        elif isinstance(stmt, ast.AnnAssign):
            targets = [stmt.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "__slots__" for t in targets):
            return True
    return False


def _dataclass_slots(cls):
    for dec in cls.decorator_list:
        if isinstance(dec, ast.Call) and _callee_name(dec.func) == "dataclass":
            for kw in dec.keywords:
                if kw.arg == "slots" and _is_true(kw.value):
                    return True
    return False


def find_hotpath_no_slots(tree, marker_lines):
    """A class tagged `# hot-path` that declares neither __slots__ nor
    dataclass(slots=True)."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        start = getattr(node, "lineno", 0)
        dec_lines = [getattr(d, "lineno", start) for d in node.decorator_list]
        top = min([start] + dec_lines)
        marked = any(top - 2 <= ln <= start for ln in marker_lines)
        if not marked or _has_slots(node) or _dataclass_slots(node):
            continue
        out.append({"kind": "slots-hot-path", "line": start,
                    "message": "class '%s' is marked hot-path but has no "
                               "__slots__ / dataclass(slots=True)" % node.name})
    return out


def find_acquire_no_cm(tree, acquire_names):
    """A resource-acquiring call bound by a plain assignment (not a ``with``)."""
    acq = {n.split(".")[-1] for n in (acquire_names or [])}
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            name = _callee_name(node.value.func)
            if name and name in acq:
                out.append({"kind": "resource-context-manager",
                            "line": getattr(node, "lineno", 0),
                            "message": "'%s' acquired outside a `with`; "
                                       "use a context manager" % name})
    return out


# --- scan ---------------------------------------------------------------------

def _enabled(registry):
    """{practice_id: status_string} for the advisory practices in the registry."""
    status = {}
    for p in registry.get("practices") or []:
        if isinstance(p, dict) and p.get("tier") == "advisory":
            status[p.get("id")] = str(p.get("status", ""))
    return status


def scan(registry, on_profiles):
    """Walk SCAN_ROOTS and return (findings, empty_pragmas).

    A practice runs only when its registry status starts with 'on'; a domain
    practice additionally requires its profile to be enabled."""
    tokens = registry.get("tokens") or {}
    providers = tokens.get("provider_constructors") or []
    acquire = tokens.get("acquire_apis") or []
    status = _enabled(registry)

    def on(pid):
        return status.get(pid, "").startswith("on")

    cm = next((p for p in registry.get("practices") or []
               if isinstance(p, dict) and p.get("id") == "resource-context-manager"), {})
    cm_active = on("resource-context-manager") and cm.get("profile") in on_profiles

    findings, empty_pragmas = [], []
    for base_name in SCAN_ROOTS:
        base = os.path.join(ROOT, base_name)
        if not os.path.isdir(base):
            continue
        for path in _py_files(base):
            text = _read(path)
            if text is None:
                continue
            tree = _parse(text)
            if tree is None:
                continue
            rel, pragma = _rel(path), _pragma_lines(text)
            for ln, reason in pragma.items():
                if reason == "":
                    empty_pragmas.append("%s:%d" % (rel, ln))
            raw = []
            if on("dependency-injection"):
                raw += find_di_inline(tree, providers)
            if on("singledispatch-over-isinstance"):
                raw += find_isinstance_chains(tree)
            if on("slots-hot-path"):
                raw += find_hotpath_no_slots(tree, _comment_lines(text, _HOTPATH_MARKER))
            if cm_active:
                raw += find_acquire_no_cm(tree, acquire)
            for f in raw:
                # PERF401 suppressed: an extend+genexp of a 4-key dict literal
                # built from `f` reads worse, and this list is single-digit.
                findings.append({"kind": f["kind"],  # noqa: PERF401
                                 "loc": "%s:%d" % (rel, f["line"]),
                                 "message": f["message"],
                                 "suppressed": _suppressed(f["line"], pragma)})
    return findings, empty_pragmas


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Advisory: flag coding-practice smells (DI-inline, isinstance "
                    "chains, hot-path without __slots__, ...). Never fails the build.")
    ap.add_argument("--json", action="store_true", help="emit active findings as JSON")
    args = ap.parse_args(argv)

    findings, empty_pragmas = scan(load_registry(), profiles_on())
    active = [f for f in findings if not f["suppressed"]]

    if args.json:
        json.dump(active, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    for loc in empty_pragmas:
        print("coding-practices: suppression with no reason at %s" % loc)

    if not active:
        print("coding-practices: no smells found.  (advisory)")
        return 0

    print("coding-practices: scanning for practice smells "
          "(advisory; never fails the build)")
    for f in sorted(active, key=lambda x: (x["kind"], x["loc"])):
        print("  [%s] %s" % (f["kind"], f["loc"]))
        print("      %s" % f["message"])
        print("      fix: apply the practice, or add `# practice-ok: <reason>`")
    print("coding-practices: %d smell(s); %d suppressed.  "
          "(advisory - review, don't obey)" % (len(active), len(findings) - len(active)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
