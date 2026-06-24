#!/usr/bin/env python3
"""
title: Generic-solution advisor
kind: script
layer: n/a
summary: Read-only advisory. Flags "answer keys" - a distinctive literal a test asserts as its expected value AND hardcoded in src/ logic (the overfit-to-the-eval smell). Advisory only; never fails the build. Stdlib only; runs on Python 3.6+.
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

# Directories we never descend into.
IGNORE_DIRS = set([
    ".git", "node_modules", ".venv", "__pycache__", "dist", "build",
    ".mypy_cache", ".ruff_cache", ".pytest_cache",
])

# Trivial strings are never "answer keys" - too common to be a memorized result.
# Compared case-insensitively against value.strip().
_TRIVIAL_STR = set([
    "", "true", "false", "null", "none",
    "id", "name", "path", "kind", "type", "title", "summary", "owner",
    "status", "error", "ok",
    "get", "post", "put", "patch", "delete", "head", "options",
    "application/json", "text/plain", "utf-8", "localhost",
    "__main__", "__name__", "/", ".", "-", "_",
])
# Numeric goldens (counts, limits, HTTP codes) are excluded by default; numbers
# are only considered under --strict, and then only when they have >= 4 digits -
# so no explicit small-int allowlist is needed.

_ALLCAPS_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_PRAGMA_RE = re.compile(r"^#\s*generic-ok\b\s*:?\s*(.*)$")
_SPECIAL = set(list("-_./:"))
_ASSERT_EQ_FUNCS = set([
    "assertEqual", "assertEquals",
    "assertDictEqual", "assertListEqual",
])

_STR_THRESHOLD = 12
_STR_THRESHOLD_STRICT = 8


def _literal(node):
    """str/int/float value of a literal node, else None. 3.6 (Str/Num) + 3.8 (Constant)."""
    if isinstance(node, ast.Constant):           # 3.8+
        v = node.value
        if isinstance(v, bool):                  # bools are not answer keys
            return None
        return v if isinstance(v, (str, int, float)) else None
    if isinstance(node, ast.Str):                # 3.6
        return node.s
    if isinstance(node, ast.Num):                # 3.6
        return node.n
    return None                                  # NameConstant (bool/None) -> not tracked


def is_distinctive(value, strict):
    """True when a value is specific enough to be a plausible memorized answer key."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        if not strict or isinstance(value, float):
            return False
        return len(str(abs(int(value)))) >= 4
    if not isinstance(value, str):
        return False
    s = value.strip()
    if s.lower() in _TRIVIAL_STR:
        return False
    threshold = _STR_THRESHOLD_STRICT if strict else _STR_THRESHOLD
    if len(s) < threshold:
        return False
    # Looks like an identifier / path / sentence, not a plain word.
    if any(ch.isdigit() for ch in s):
        return True
    if any(ch in _SPECIAL for ch in s):
        return True
    return " " in s


def _read(path):
    try:
        # utf-8-sig strips a leading BOM, so BOM-saved files still parse.
        with io.open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


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
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(os.path.join(dirpath, fn))
    return out


def _is_data_module(path):
    """A declared data/registry/value-object module - literals there are data, not logic."""
    base = os.path.basename(path)
    if base.endswith("_data.py") or base.endswith("_models.py"):
        return True
    if base in ("data.py", "conftest.py", "registry.py"):
        return True
    if base == "fixtures.py" or base.endswith("_fixtures.py"):
        return True
    parts = path.replace(os.sep, "/").split("/")
    return "data" in parts or "fixtures" in parts


def _pragma_lines(text):
    """Map line number -> suppression reason for every `# generic-ok[: reason]` comment.

    Uses tokenize, so a `#` inside a string literal is part of a STRING token,
    never a COMMENT, and so cannot be mistaken for a pragma."""
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


def _suppressed(node, value, pragma):
    """True if a `# generic-ok` pragma sits anywhere on the literal's line span.

    A multiline string's AST lineno differs by interpreter (3.6 reports the
    closing line, 3.8+ the opening line), and the trailing pragma can only live
    on the closing line — so match the whole span, not a single line."""
    if not pragma:
        return False
    line = getattr(node, "lineno", 0)
    end = getattr(node, "end_lineno", None)
    if end is not None:                       # 3.8+: real end line
        lo, hi = line, end
    elif isinstance(value, str):              # 3.6: lineno is the closing line
        lo, hi = line - value.count("\n"), line
    else:
        lo, hi = line, line
    for ln in range(lo, hi + 1):
        if ln in pragma:
            return True
    return False


def _docstring_ids(tree):
    """Node ids of module/class/function docstrings (a leading bare-string Expr)."""
    ids = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body:
            continue
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(_literal(first.value), str):
            ids.add(id(first.value))
    return ids


def _allcaps_value_ids(tree):
    """Node ids of values assigned to an ALL_CAPS name - naming a constant IS the
    generic move, so its literal must not be flagged."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and _ALLCAPS_RE.match(t.id) for t in targets):
            continue
        val = getattr(node, "value", None)
        if val is None:
            continue
        # Everything inside a named constant is "named" data, at any depth.
        for sub in ast.walk(val):
            ids.add(id(sub))
    return ids


def _add_expected(node, bucket, rel):
    """Record a literal (or the one-level leaves of a container) as a test-expected value."""
    v = _literal(node)
    if v is not None:
        bucket.setdefault(v, set()).add("%s:%d" % (rel, getattr(node, "lineno", 0)))
        return
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        elts = node.elts
    elif isinstance(node, ast.Dict):
        elts = node.values
    else:
        return
    for e in elts:
        ev = _literal(e)
        if ev is not None:
            bucket.setdefault(ev, set()).add("%s:%d" % (rel, getattr(e, "lineno", 0)))


def collect_expected(base):
    """value -> {"testfile:line"} for literals a test asserts as the EXPECTED value.

    Equality only: `==`/`assertEqual` operands. Membership (`in`) and identity
    (`is`) compares are excluded - a header asserted with `in` is presentation,
    not an answer key."""
    expected = {}
    for path in _py_files(base):
        text = _read(path)
        if text is None:
            continue
        tree = _parse(text)
        if tree is None:
            continue
        rel = _rel(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                for cmp in ast.walk(node.test):
                    if isinstance(cmp, ast.Compare) and cmp.ops \
                            and all(isinstance(op, ast.Eq) for op in cmp.ops):
                        _add_expected(cmp.left, expected, rel)
                        for c in cmp.comparators:
                            _add_expected(c, expected, rel)
            elif isinstance(node, ast.Call):
                # assertEqual-family signature is (first, second, msg=None):
                # only the two operands are expected values, never the message.
                if getattr(node.func, "attr", None) in _ASSERT_EQ_FUNCS:
                    for a in node.args[:2]:
                        _add_expected(a, expected, rel)
    return expected


def collect_src(base):
    """value -> [(rel, line, suppressed)] for literals in non-data src/ logic, plus
    the locations of any reason-less `# generic-ok` pragmas (an accountability gap)."""
    occ = {}
    empty_pragmas = []
    for path in _py_files(base):
        if _is_data_module(path):
            continue
        text = _read(path)
        if text is None:
            continue
        tree = _parse(text)
        if tree is None:
            continue
        rel = _rel(path)
        pragma = _pragma_lines(text)
        for line, reason in pragma.items():
            if reason == "":
                empty_pragmas.append("%s:%d" % (rel, line))
        skip_ids = _docstring_ids(tree)
        skip_ids |= _allcaps_value_ids(tree)
        for node in ast.walk(tree):
            val = _literal(node)
            if val is None:
                continue
            if id(node) in skip_ids:
                continue
            line = getattr(node, "lineno", 0)
            occ.setdefault(val, []).append((rel, line, _suppressed(node, val, pragma)))
    return occ, empty_pragmas


def find(strict=False):
    """Return (findings, suppressed_count, empty_pragmas).

    A finding is a distinctive value present both as a test's expected value and
    hardcoded (un-suppressed) in non-data src/ logic."""
    expected = collect_expected(os.path.join(ROOT, "tests"))
    occ, empty_pragmas = collect_src(os.path.join(ROOT, "src"))
    findings = []
    suppressed = 0
    for value in expected:
        if value not in occ or not is_distinctive(value, strict):
            continue
        active = [(r, ln) for (r, ln, supp) in occ[value] if not supp]
        if not active:
            suppressed += 1
            continue
        findings.append({
            "value": value,
            "tests": sorted(expected[value]),
            "src": sorted("%s:%d" % (r, ln) for (r, ln) in active),
        })
    findings.sort(key=lambda f: str(f["value"]))
    return findings, suppressed, empty_pragmas


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Advisory: flag answer-key literals (a value a test asserts as "
                    "expected that is also hardcoded in src/ logic). Never fails the build.")
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    ap.add_argument("--strict", action="store_true",
                    help="experimental: lower the string threshold and include 4+ digit "
                         "numbers (noisier; not wired into any make target)")
    args = ap.parse_args(argv)
    findings, suppressed, empty_pragmas = find(strict=args.strict)

    if args.json:
        json.dump(findings, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    for loc in empty_pragmas:
        print("generic-solution: suppression with no reason at %s" % loc)

    if not findings:
        print("generic-solution: no hardcoded answer keys found.  (advisory)")
        return 0

    print("generic-solution: scanning for hardcoded answer keys "
          "(advisory; never fails the build)")
    files = set()
    for f in findings:
        value = f["value"]
        disp = ('"%s"' % value[:60]) if isinstance(value, str) else str(value)
        print("  %s" % disp)
        print("      expected in  %s" % ", ".join(f["tests"]))
        print("      hardcoded in %s" % ", ".join(f["src"]))
        print("      fix: compute it, move the literal to a *_data.py registry, "
              "or add `# generic-ok: <reason>`")
        for s in f["src"]:
            files.add(s.rsplit(":", 1)[0])
    print("generic-solution: %d possible answer-key(s) across %d src file(s); "
          "%d suppressed.  (advisory - a static check cannot prove code is generic; "
          "review, don't obey)" % (len(findings), len(files), suppressed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
