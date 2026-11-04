"""
title: Assertion quality — a test function shows it can fail
summary: The judge tests/integration/test_assertion_quality_gate.py applies to every test function under config/project.json `test_quality.assertions.roots`, ported from the maintainer's assertion-quality scanner and read from the syntax tree, never run. A test fails with one of four kinds. `no assertion`: nothing in its body asserts, and no helper it calls does, followed by name to a function of its own module or of a module under the roots it imports (tests/source_tree.py `bindings`), transitively, at most `test_quality.assertions.helper_depth` calls deep and never twice round a cycle. `only constant assertions`: every assertion it reaches asserts a truthy constant (`assert True`, `assert "text"`). `tautology`: an `assert` in its body compares one name or attribute chain with itself by `==`, `is`, `<=` or `>=`; two calls are never one (`f(x) == f(x)` is a determinism check). `swallowed exception`: a handler in its body only passes, continues or holds `...`. An assertion is an `assert` of anything else, a `pytest.raises` or `pytest.warns` call or block, or a call of a method named `assert_*` (mock's `assert_called_with` and its siblings). A bare `isinstance` assertion counts as one. Test functions and files are found by pytest's default collection names, because pyproject.toml sets none of its own. `verdict` turns a scan into the gate's failures: a scan over zero test functions, each finding `test_quality.assertions.exempt` does not excuse, and each excuse whose test the judge does not fail. It reads no file outside the scan and writes nothing.
"""

import ast
import os
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402

import source_tree  # noqa: E402

__all__ = [
    "CONSTANT",
    "DEPTH",
    "EXEMPT",
    "Finding",
    "NO_ASSERTION",
    "Policy",
    "ROOTS",
    "SWALLOWED",
    "TAUTOLOGY",
    "policy",
    "scan",
    "test_files",
    "verdict",
]

ROOTS = ("test_quality", "assertions", "roots")
DEPTH = ("test_quality", "assertions", "helper_depth")
EXEMPT = ("test_quality", "assertions", "exempt")

NO_ASSERTION = "no assertion"
CONSTANT = "only constant assertions"
TAUTOLOGY = "tautology"
SWALLOWED = "swallowed exception"

# pytest's default python_files, python_classes and python_functions; a
# project that sets its own in pyproject.toml is read by these, not by its own.
_FILE_PREFIX = "test_"
_FILE_SUFFIX = "_test.py"
_CLASS_PREFIX = "Test"
_FUNCTION_PREFIX = "test"
# The names pytest exports for a block or call that fails unless the code
# under it raises or warns.
_EXPECTS = ("raises", "warns")
# A mock's own assertions: assert_called_with, assert_not_called and the rest.
_MOCK_ASSERT_PREFIX = "assert_"
# The comparisons that hold whenever both sides are the same object.
_ALWAYS_TRUE = (ast.Eq, ast.Is, ast.LtE, ast.GtE)
_SELF_NAMES = ("self", "cls")


class Finding(NamedTuple):
    """One test function the judge fails."""

    path: str
    line: int
    test: str
    kind: str
    detail: str

    @property
    def node_id(self) -> str:
        """The function-level pytest node id `test_quality.assertions.exempt`
        is keyed by."""
        return "%s::%s" % (self.path, self.test)

    def __str__(self) -> str:
        return "%s:%d: %s: %s: %s" % (
            self.path,
            self.line,
            self.test,
            self.kind,
            self.detail,
        )


class Policy(NamedTuple):
    """The gate's three settings, as config/project.json holds them."""

    roots: Tuple[str, ...]
    helper_depth: int
    exempt: Dict[str, str]


def policy(root: str) -> Policy:
    """config/project.json `test_quality.assertions` under *root*. Raises
    config_loader.ConfigError, naming the key, for a value the loader
    refuses."""
    values = config_loader.resolve(
        config_loader.read(root),
        config_loader.rows(ROOTS, DEPTH, EXEMPT),
        config_loader.CONFIG_FILE,
    )
    return Policy(tuple(values[ROOTS]), int(values[DEPTH]), dict(values[EXEMPT]))


def _under(path: str, roots: Tuple[str, ...]) -> bool:
    return any(path == r or path.startswith(r.rstrip("/") + "/") for r in roots)


def _is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.endswith(".py") and (
        name.startswith(_FILE_PREFIX) or name.endswith(_FILE_SUFFIX)
    )


def test_files(root: str, roots: Tuple[str, ...]) -> List[str]:
    """Every test file under *roots*, as sorted relative posix paths, from
    the walk tests/source_tree.py `python_files` makes."""
    return [
        p
        for p in source_tree.python_files(root)
        if _under(p, roots) and _is_test_file(p)
    ]


_Function = ast.FunctionDef | ast.AsyncFunctionDef


class _Module:
    """One parsed file: its functions, its classes' methods and the names
    its imports bind to project files."""

    def __init__(self, root: str, path: str, search_roots: List[str]) -> None:
        self.path = path
        self.tree = source_tree.parse(root, path)
        self.functions: Dict[str, _Function] = {}
        self.methods: Dict[str, Dict[str, _Function]] = {}
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self.methods[node.name] = {
                    item.name: item
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
        self.bindings = source_tree.bindings(root, path, self.tree, search_roots)

    def lookup(self, qual: str) -> Optional[Tuple[_Function, Optional[str]]]:
        """The function *qual* names (`name` or `Class::name`) and its class."""
        owner, _sep, name = qual.rpartition("::")
        if not owner:
            found = self.functions.get(name)
            return (found, None) if found else None
        method = self.methods.get(owner, {}).get(name)
        return (method, owner) if method else None


def _tests(tree: ast.Module) -> List[Tuple[str, _Function, Optional[str]]]:
    """`(qualified name, function, class)` for each function pytest collects
    from *tree*: a `test*` function at module level or in a `Test*` class,
    nested classes included."""
    out: List[Tuple[str, _Function, Optional[str]]] = []

    def walk(body: List[ast.stmt], prefix: str, cls: Optional[str]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith(_FUNCTION_PREFIX):
                    out.append((prefix + node.name, node, cls))
            elif isinstance(node, ast.ClassDef) and node.name.startswith(_CLASS_PREFIX):
                walk(node.body, prefix + node.name + "::", node.name)

    walk(tree.body, "", None)
    return out


def _chain(node: ast.expr) -> Optional[str]:
    """`a.b.c` for a name or an attribute chain over one, else None."""
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _is_tautology(test: ast.expr) -> bool:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], _ALWAYS_TRUE):
        return False
    left = _chain(test.left)
    return left is not None and left == _chain(test.comparators[0])


def _is_expectation(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr in _EXPECTS or func.attr.startswith(_MOCK_ASSERT_PREFIX)
    return isinstance(func, ast.Name) and func.id in _EXPECTS


def _swallows(handler: ast.ExceptHandler) -> bool:
    return all(
        isinstance(s, (ast.Pass, ast.Continue))
        or (
            isinstance(s, ast.Expr)
            and isinstance(s.value, ast.Constant)
            and s.value.value is Ellipsis
        )
        for s in handler.body
    )


class _Body(NamedTuple):
    real: int
    constant: List[int]
    tautology: List[int]
    swallowed: List[int]
    calls: List[ast.Call]


def _read(func: _Function) -> _Body:
    """What *func*'s body asserts, the handlers in it that swallow, and the
    calls it makes, nested blocks and functions included; its decorators and
    defaults are not its body."""
    real, constant, tautology, swallowed = 0, [], [], []
    calls: List[ast.Call] = []
    for statement in func.body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Assert):
                if isinstance(node.test, ast.Constant) and node.test.value:
                    constant.append(node.lineno)
                elif _is_tautology(node.test):
                    tautology.append(node.lineno)
                else:
                    real += 1
            elif isinstance(node, ast.Call):
                if _is_expectation(node):
                    real += 1
                else:
                    calls.append(node)
            elif isinstance(node, ast.ExceptHandler) and _swallows(node):
                swallowed.append(node.lineno)
    return _Body(real, constant, tautology, swallowed, calls)


class _Judge:
    """Resolves helpers across the files of one scan, parsing each once."""

    def __init__(
        self, root: str, roots: Tuple[str, ...], depth: int, search_roots: List[str]
    ) -> None:
        self.root = root
        self.roots = roots
        self.depth = depth
        self.search_roots = search_roots
        self.modules: Dict[str, _Module] = {}

    def module(self, path: str) -> _Module:
        if path not in self.modules:
            self.modules[path] = _Module(self.root, path, self.search_roots)
        return self.modules[path]

    def callee(
        self, call: ast.Call, module: _Module, cls: Optional[str]
    ) -> Optional[Tuple[str, str]]:
        """`(file, qualified name)` of the helper *call* names, when it is a
        function of *module* or of a module under the roots it imports."""
        func = call.func
        found: Optional[Tuple[str, str]] = None
        if isinstance(func, ast.Name):
            bound = module.bindings.get(func.id)
            if func.id in module.functions:
                found = (module.path, func.id)
            elif bound and bound[1] is not None:
                found = (bound[0], bound[1])
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            owner = func.value.id
            bound = module.bindings.get(owner)
            if owner in _SELF_NAMES and cls is not None:
                found = (module.path, "%s::%s" % (cls, func.attr))
            elif owner in module.methods:
                found = (module.path, "%s::%s" % (owner, func.attr))
            elif bound and bound[1] is None:
                found = (bound[0], func.attr)
        if found is None or not _under(found[0], self.roots):
            return None
        return found

    def helpers_assert(
        self,
        calls: List[ast.Call],
        module: _Module,
        cls: Optional[str],
        level: int,
        seen: Set[Tuple[str, str]],
    ) -> Tuple[bool, bool]:
        """`(real, constant)`: whether a helper among *calls*, *level* calls
        below the test, asserts for real, and whether one asserts a constant."""
        constant = False
        if level > self.depth:
            return False, constant
        for call in calls:
            target = self.callee(call, module, cls)
            if target is None or target in seen:
                continue
            helper_module = self.module(target[0])
            found = helper_module.lookup(target[1])
            if found is None:
                continue
            body = _read(found[0])
            constant = constant or bool(body.constant)
            if body.real:
                return True, constant
            real, deeper = self.helpers_assert(
                body.calls, helper_module, found[1], level + 1, seen | {target}
            )
            constant = constant or deeper
            if real:
                return True, constant
        return False, constant

    def judge(self, path: str) -> Tuple[int, List[Finding]]:
        module = self.module(path)
        tests = _tests(module.tree)
        findings: List[Finding] = []
        for name, func, cls in tests:
            body = _read(func)
            findings.extend(
                Finding(
                    path,
                    line,
                    name,
                    TAUTOLOGY,
                    "an assertion compares a value with itself",
                )
                for line in body.tautology
            )
            findings.extend(
                Finding(
                    path,
                    line,
                    name,
                    SWALLOWED,
                    "a handler drops the exception it catches",
                )
                for line in body.swallowed
            )
            if body.real or body.tautology:
                continue
            real, constant = self.helpers_assert(
                body.calls, module, cls, 1, {(path, name)}
            )
            if real:
                continue
            if constant or body.constant:
                findings.append(
                    Finding(
                        path,
                        func.lineno,
                        name,
                        CONSTANT,
                        "every assertion it reaches asserts a truthy constant",
                    )
                )
            else:
                findings.append(
                    Finding(
                        path,
                        func.lineno,
                        name,
                        NO_ASSERTION,
                        "nothing in it, or in a helper it calls up to %d deep, asserts"
                        % self.depth,
                    )
                )
        return len(tests), findings


def scan(
    root: str,
    files: List[str],
    roots: Tuple[str, ...],
    depth: int,
    search_roots: List[str],
) -> Tuple[int, List[Finding]]:
    """`(test functions read, findings)` over *files* under *root*, sorted by
    file and line. Raises source_tree.SourceTreeError naming a file it cannot
    parse."""
    judge = _Judge(root, roots, depth, search_roots)
    count, findings = 0, []
    for path in files:
        read, found = judge.judge(path)
        count += read
        findings.extend(found)
    return count, sorted(findings)


def verdict(
    count: int, findings: List[Finding], exempt: Dict[str, str], roots: Tuple[str, ...]
) -> List[str]:
    """The gate's failures, one line each: no test function read under
    *roots*, each finding *exempt* does not excuse, and each excuse whose
    test the judge does not fail, which has gone stale."""
    if count == 0:
        return [
            "no test function was read under %s: a pass over zero tests is a "
            "failure; check config/project.json %s"
            % (", ".join(roots), ".".join(ROOTS))
        ]
    failed = {f.node_id for f in findings}
    out = [str(f) for f in findings if f.node_id not in exempt]
    out.extend(
        "%s: stale: config/project.json %s excuses a test the gate does not "
        "fail; remove the entry" % (node_id, ".".join(EXEMPT))
        for node_id in sorted(exempt)
        if node_id not in failed
    )
    return out
