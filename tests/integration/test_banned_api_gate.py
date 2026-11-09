"""
title: Integration — literal reflection cannot bypass the banned API policy
kind: tests
layer: n/a
summary: Walks every Python file tests/source_tree.py lists, using the structure gate's walk and ignored directories. Literal getattr calls on imported modules and wildcard imports cannot expose pyproject.toml banned APIs unless a TID251 suppression supplies a reason. Dynamic names and unrelated objects are outside this check; ruff owns ordinary imports and attribute access. An empty policy or tree fails loudly.
"""

import ast
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # before 3.11; pytest itself depends on tomli there
    import tomli as tomllib

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))

import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration


def banned_policy(root):
    """The banned dotted names and messages from ruff's own policy."""
    path = Path(root) / "pyproject.toml"
    policy = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        banned = policy["tool"]["ruff"]["lint"]["flake8-tidy-imports"]["banned-api"]
    except KeyError as exc:
        raise st.SourceTreeError("pyproject.toml: no banned-api policy") from exc
    if not isinstance(banned, dict) or not banned:
        raise st.SourceTreeError("pyproject.toml: empty or malformed banned-api policy")
    for name, entry in banned.items():
        if "." not in name or not isinstance(entry, dict) or not entry.get("msg"):
            raise st.SourceTreeError("pyproject.toml: malformed banned-api %r" % name)
    return banned


def _dotted(node, bindings):
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value, bindings)
        return base + "." + node.attr if base else None
    return None


class _Bypasses(ast.NodeVisitor):
    def __init__(self, banned):
        self.banned = banned
        self.bindings = {"getattr": "builtins.getattr"}
        self.found = []

    def visit_Import(self, node):
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self.bindings[bound] = alias.name if alias.asname else bound

    def visit_ImportFrom(self, node):
        if node.level or not node.module:
            return
        for alias in node.names:
            if alias.name == "*":
                names = sorted(
                    n for n in self.banned if n.startswith(node.module + ".")
                )
                if names:
                    self.found.append((node, ", ".join(names)))
            else:
                self.bindings[alias.asname or alias.name] = (
                    node.module + "." + alias.name
                )

    def visit_Call(self, node):
        if (
            _dotted(node.func, self.bindings) == "builtins.getattr"
            and len(node.args) >= 2
        ):
            module = _dotted(node.args[0], self.bindings)
            name = node.args[1]
            if (
                module
                and isinstance(name, ast.Constant)
                and isinstance(name.value, str)
            ):
                dotted = module + "." + name.value
                if dotted in self.banned:
                    self.found.append((node, dotted))
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        # Defaults and decorators run in the enclosing scope, before parameters bind.
        for expr in (
            node.decorator_list
            + node.args.defaults
            + [d for d in node.args.kw_defaults if d is not None]
        ):
            self.visit(expr)
        outer = self.bindings
        self.bindings = dict(outer)
        args = node.args
        parameters = args.posonlyargs + args.args + args.kwonlyargs
        parameters += [a for a in (args.vararg, args.kwarg) if a is not None]
        for arg in parameters:
            self.bindings.pop(arg.arg, None)
        for child in st.scope_nodes(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                self.bindings.pop(child.id, None)
        for statement in node.body:
            self.visit(statement)
        self.bindings = outer
        self.bindings.pop(node.name, None)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        outer = self.bindings
        self.bindings = dict(outer)
        self.generic_visit(node)
        self.bindings = outer
        self.bindings.pop(node.name, None)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.bindings.pop(node.id, None)


def banned_findings(root):
    """Named literal-reflection, wildcard-import and blank-waiver findings."""
    banned = banned_policy(root)
    files = st.python_files(root)
    if not files:
        raise st.SourceTreeError("no Python file to judge -- zero items")
    findings = []
    for path in files:
        visitor = _Bypasses(banned)
        visitor.visit(st.parse(root, path))
        reasons = st.noqa_reasons(root, path)
        for line, (codes, reason) in reasons.items():
            if "TID251" in codes and st.blank(reason):
                findings.append(
                    "%s:%d: TID251 suppression needs a reason" % (path, line)
                )
        for node, name in visitor.found:
            lines = range(node.lineno, node.end_lineno + 1)
            if any("TID251" in reasons.get(line, ((), ""))[0] for line in lines):
                continue
            findings.append("%s:%d: TID251 banned API %s" % (path, node.lineno, name))
    return sorted(findings)


def _project(tmp_path, text):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    # The fixture uses the real policy too: adding a banned API must exercise it.
    (root / "pyproject.toml").write_bytes((_ROOT / "pyproject.toml").read_bytes())
    (root / "src" / "probe.py").write_text(text, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "text",
    [
        'import functools\ngetattr(functools, "cache")\n',
        'import functools as ft\ngetattr(ft, "lru_cache")\n',
        "from functools import *\n",
        'import functools\ngetattr(functools, "cache", None)\n',
        'import functools\ngetattr(\n functools, "cache"\n)\n',
        'import functools\ngetattr(functools, "cache")  # noqa: TID251\n',
    ],
)
def test_literal_bypasses_are_findings(tmp_path, text):
    findings = banned_findings(_project(tmp_path, text))
    assert len(findings) == 1 and "src/probe.py:" in findings[0], findings


@pytest.mark.parametrize(
    "text",
    [
        "import functools\ngetattr(functools, name)\n",
        'getattr(obj, "cache")\n',
        'import functools\ngetattr(functools, "reduce")\n',
        'import functools\ngetattr(functools, "cache")  # noqa: TID251 -- tests the adapter\n',
        "from functools import *  # noqa: TID251 -- tests wildcard compatibility\n",
        "text = 'getattr(functools, \"cache\")'\n",
    ],
)
def test_dynamic_names_objects_and_reasoned_waivers_are_clean(tmp_path, text):
    assert banned_findings(_project(tmp_path, text)) == []


def test_policy_is_read_from_pyproject(tmp_path):
    root = _project(tmp_path, 'import example\ngetattr(example, "blocked")\n')
    (root / "pyproject.toml").write_text(
        "[tool.ruff.lint.flake8-tidy-imports.banned-api]\n"
        '"example.blocked".msg = "fixture policy"\n',
        encoding="utf-8",
    )
    findings = banned_findings(root)
    assert len(findings) == 1 and "example.blocked" in findings[0], findings


def test_tree_has_no_literal_banned_api_bypasses():
    findings = banned_findings(_ROOT)
    assert not findings, "\n".join(findings)
