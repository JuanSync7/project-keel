"""
title: Assertion quality — a test function shows it can fail
summary: Judges test functions without executing them: reports missing assertions, any tautology in a test or reachable helper, and handlers in the test that drop errors. Folds bounded literal arithmetic, comparisons and boolean operations through the AST, respects lexical and comprehension scopes, counts raises/warns expectations only as entered with items or callable checks, and follows every helper within the configured roots and depth, deduplicating cycle findings. Credits deferred generator calls only when consumed by iteration, unpacking, delegation or configured bare callees in their declared argument position; resolves TestCase receivers by single lexical bindings, instance parameters and receiver displays. Collects inherited and nested tests and TestCase assertions, and rejects empty roots, zero tests and stale exemptions; comparisons of calls remain real checks.
"""

import ast
import builtins
import operator
import os
import sys
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402

import source_tree  # noqa: E402
from bounded_cache import bounded  # noqa: E402

__all__ = [
    "CONSUMERS",
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
    "test_functions",
    "verdict",
]

ROOTS = ("test_quality", "assertions", "roots")
DEPTH = ("test_quality", "assertions", "helper_depth")
EXEMPT = ("test_quality", "assertions", "exempt")
CONSUMERS = ("test_quality", "assertions", "consumers")

NO_ASSERTION = "no assertion"
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
_EXPECTS = ("raises", "warns", "fail")
# Regex expectations take a pattern before the callable; log checks only
# support the context-manager form.
_UNITTEST_EXPECTS: Dict[str, Optional[int]] = {
    "assertRaises": 1,
    "assertRaisesRegex": 2,
    "assertWarns": 1,
    "assertWarnsRegex": 2,
    "assertLogs": None,
    "assertNoLogs": None,
}
# A mock's own assertions: assert_called_with, assert_not_called and the rest.
_MOCK_ASSERT_PREFIX = "assert_"
# The comparisons that hold whenever both sides are the same object.
_ALWAYS_TRUE = (ast.Eq, ast.Is, ast.LtE, ast.GtE)
_SELF_NAMES = ("self", "cls")
# Test syntax is input to the gate: bound intermediate allocations before a
# literal power, shift or sequence repetition can exhaust the scanner.
_LITERAL_LIMIT = 4096
_UNKNOWN = object()
_BINARY: Dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_,
    ast.BitXor: operator.xor,
}
_COMPARE: Dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}


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
    """The gate's settings, as config/project.json holds them."""

    roots: Tuple[str, ...]
    helper_depth: int
    exempt: Dict[str, str]
    consumers: Dict[str, str]


def policy(root: str) -> Policy:
    """config/project.json `test_quality.assertions` under *root*. Raises
    config_loader.ConfigError, naming the key, for a value the loader
    refuses."""
    values = config_loader.resolve(
        config_loader.read(root),
        config_loader.rows(ROOTS, DEPTH, EXEMPT, CONSUMERS),
        config_loader.CONFIG_FILE,
    )
    return Policy(
        tuple(values[ROOTS]),
        int(values[DEPTH]),
        dict(values[EXEMPT]),
        dict(values[CONSUMERS]),
    )


def _under(path: str, roots: Tuple[str, ...]) -> bool:
    return any(path == r or path.startswith(r.rstrip("/") + "/") for r in roots)


def _is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.endswith(".py") and (
        name.startswith(_FILE_PREFIX) or name.endswith(_FILE_SUFFIX)
    )


def test_files(root: str, roots: Tuple[str, ...]) -> List[str]:
    """Every test file under *roots*, as sorted relative posix paths, from
    the walk tests/source_tree.py `python_files` makes. Raises SourceTreeError
    naming each missing root or root with no test file."""
    files = [
        p
        for p in source_tree.python_files(root)
        if _under(p, roots) and _is_test_file(p)
    ]
    for configured in roots:
        if not os.path.isdir(os.path.join(root, configured)) or not any(
            _under(path, (configured,)) for path in files
        ):
            raise source_tree.SourceTreeError(
                "%s: configured root %s must exist and yield at least one test file"
                % (".".join(ROOTS), configured)
            )
    return files


_Function = ast.FunctionDef | ast.AsyncFunctionDef


class _Module:
    """One parsed file: its functions, its classes' methods and the names
    its imports bind to project files."""

    def __init__(self, root: str, path: str, search_roots: List[str]) -> None:
        self.path = path
        self.tree = source_tree.parse(root, path)
        self.binding_index = _BindingIndex(self.tree)
        self.functions: Dict[str, _Function] = {}
        self.methods: Dict[str, Dict[str, _Function]] = {}
        self.classes: Dict[str, ast.ClassDef] = {}
        self.class_names: Dict[ast.ClassDef, str] = {}
        self.parents: Dict[_Function, List[_Function]] = {}
        self.local_functions: Dict[_Function, Dict[str, str]] = {}
        self.definitions: Dict[str, Tuple[_Function, Optional[str]]] = {}
        self._index(self.tree, "", None, [])
        for cls, methods in self.methods.items():
            if self.is_testcase(cls):
                for func in methods.values():
                    self.binding_index.mark_receiver(func)
        self.root = root
        self.search_roots = search_roots
        # A helper walk resolves many calls in the same finite AST; keep its
        # tables only for the bounded parsed module's lifetime.
        self._symbols: Dict[
            Optional[_Function], Dict[str, Tuple[str, Optional[str]]]
        ] = {}

    def _index(
        self,
        scope: ast.Module | ast.ClassDef | _Function,
        prefix: str,
        cls: Optional[str],
        parents: List[_Function],
    ) -> None:
        local = {}
        for node in source_tree.scope_nodes(scope):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = prefix + node.name
                self.definitions[qual] = (node, cls)
                self.parents[node] = parents
                local[node.name] = qual
                if isinstance(scope, ast.Module):
                    self.functions[node.name] = node
                elif isinstance(scope, ast.ClassDef) and cls is not None:
                    self.methods[cls][node.name] = node
                self._index(node, qual + "::", cls, [node] + parents)
            elif isinstance(node, ast.ClassDef):
                qual = prefix + node.name
                self.classes[qual] = node
                self.class_names[node] = qual
                self.methods[qual] = {}
                self._index(node, qual + "::", qual, parents)
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.local_functions[scope] = local

    def symbols(
        self, func: Optional[_Function] = None
    ) -> Dict[str, Tuple[str, Optional[str]]]:
        """Bindings visible to a function: its locals, enclosing functions,
        then the module. Unknown local values shadow imported names too."""
        if func in self._symbols:
            return self._symbols[func]
        scopes: List[ast.Module | _Function] = [self.tree]
        if func is not None:
            scopes += list(reversed(self.parents[func])) + [func]
        out: Dict[str, Tuple[str, Optional[str]]] = {}
        for scope in scopes:
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in (
                    scope.args.posonlyargs
                    + scope.args.args
                    + scope.args.kwonlyargs
                    + [a for a in (scope.args.vararg, scope.args.kwarg) if a]
                ):
                    _shadow(out, arg.arg)
            for node in source_tree.scope_nodes(scope):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    _shadow(out, node.id)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qual = (
                        self.local_functions.get(scope, {}).get(node.name, node.name)
                        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))
                        else node.name
                    )
                    out[node.name] = (self.path, qual)
                elif isinstance(node, ast.ClassDef):
                    _shadow(out, node.name)
                    out[node.name] = (self.path, "@class:" + self.class_names[node])
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports = source_tree.bindings(
                        self.root,
                        self.path,
                        ast.Module(body=[node], type_ignores=[]),
                        self.search_roots,
                    )
                    for alias in node.names:
                        local = alias.asname or alias.name.split(".")[0]
                        out[local] = ("", None)
                        if isinstance(node, ast.Import) and alias.name == "pytest":
                            out[local] = ("@pytest", None)
                        elif (
                            isinstance(node, ast.ImportFrom)
                            and node.module == "pytest"
                            and not node.level
                        ):
                            out[local] = ("@pytest", alias.name)
                        elif local in imports:
                            out[local] = imports[local]
                    out.update(
                        {
                            name: binding
                            for name, binding in imports.items()
                            if "." in name
                        }
                    )
        self._symbols[func] = out
        return out

    def bases(self, cls: str) -> List[str]:
        """Local base classes, resolving nested siblings in their parent."""
        prefix = cls.rpartition("::")[0]
        out = []
        for base in self.classes[cls].bases:
            name = (_chain(base) or "").replace(".", "::")
            nested = prefix + "::" + name if prefix else name
            if nested in self.classes:
                out.append(nested)
            elif name in self.classes:
                out.append(name)
        return out

    def linearization(self, cls: str, seen: Optional[Set[str]] = None) -> List[str]:
        """Python's C3 method order for bases defined within this module."""
        if cls in (seen or set()):
            raise source_tree.SourceTreeError(
                "%s: inheritance cycle at %s" % (self.path, cls)
            )
        bases = self.bases(cls)
        pending = [
            self.linearization(base, (seen or set()) | {cls}) for base in bases
        ] + [bases[:]]
        out = [cls]
        while any(pending):
            pending = [order for order in pending if order]
            candidate = next(
                (
                    order[0]
                    for order in pending
                    if not any(order[0] in other[1:] for other in pending)
                ),
                None,
            )
            if candidate is None:
                raise source_tree.SourceTreeError(
                    "%s: inconsistent inheritance at %s" % (self.path, cls)
                )
            out.append(candidate)
            for order in pending:
                if order[0] == candidate:
                    order.pop(0)
        return out

    def all_methods(self, cls: str) -> Dict[str, _Function]:
        """Methods inherited within the module, with Python's override order."""
        out = {}
        for owner in reversed(self.linearization(cls)):
            out.update(self.methods[owner])
        return out

    def is_testcase(self, cls: str, seen: Optional[Set[str]] = None) -> bool:
        seen = (seen or set()) | {cls}
        aliases = {}
        for node in source_tree.scope_nodes(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "unittest":
                        aliases[alias.asname or alias.name] = "unittest"
            elif isinstance(node, ast.ImportFrom) and node.module == "unittest":
                for alias in node.names:
                    aliases[alias.asname or alias.name] = "unittest." + alias.name
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = _chain(node.value) if node.value is not None else None
                head, _, tail = (value or "").partition(".")
                resolved = aliases.get(head, head) + ("." + tail if tail else "")
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for target in targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = resolved
        for base in self.classes[cls].bases:
            chain = (_chain(base) or "").split(".")
            if (
                ".".join([aliases.get(chain[0], chain[0])] + chain[1:])
                == "unittest.TestCase"
            ):
                return True
        return any(
            self.is_testcase(base, seen) for base in self.bases(cls) if base not in seen
        )

    def lookup(self, qual: str) -> Optional[Tuple[_Function, Optional[str]]]:
        """The function *qual* names (`name` or `Class::name`) and its class."""
        if qual in self.definitions:
            return self.definitions[qual]
        owner, _sep, name = qual.rpartition("::")
        method = self.all_methods(owner).get(name) if owner in self.classes else None
        return (method, owner) if method else None


def test_functions(
    root: str, path: str, search_roots: List[str]
) -> List[Tuple[str, _Function, Optional[str]]]:
    """`(qualified name, function, class)` for each function pytest collects
    from the file *path* under *root*, found exactly as this gate finds them;
    *search_roots* resolve the imports that name a TestCase base."""
    return _tests(_Module(root, path, search_roots))


def _tests(module: _Module) -> List[Tuple[str, _Function, Optional[str]]]:
    """`(qualified name, function, class)` for each function pytest collects
    from *module*: module-level functions, nested test classes, inherited
    methods and unittest.TestCase subclasses, including compound statements."""
    out: List[Tuple[str, _Function, Optional[str]]] = []

    def walk(body: Sequence[ast.stmt], prefix: str, cls: Optional[str]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith(_FUNCTION_PREFIX):
                    out.append((prefix + node.name, node, cls))
            elif isinstance(node, ast.ClassDef):
                qual = prefix + node.name
                if node.name.startswith(_CLASS_PREFIX) or module.is_testcase(qual):
                    for name, func in module.all_methods(qual).items():
                        if name.startswith(_FUNCTION_PREFIX):
                            out.append((qual + "::" + name, func, qual))
                    nested = [
                        n
                        for n in source_tree.scope_nodes(node)
                        if isinstance(n, ast.ClassDef)
                    ]
                    walk(nested, qual + "::", qual)

    walk(
        [
            n
            for n in source_tree.scope_nodes(module.tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ],
        "",
        None,
    )
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


def _shadow(symbols: Dict[str, Tuple[str, Optional[str]]], name: str) -> None:
    """An unknown local hides the imported name and its dotted submodules."""
    for key in list(symbols):
        if key.startswith(name + "."):
            del symbols[key]
    symbols[name] = ("", None)


def _is_tautology(test: ast.expr) -> bool:
    truth = _truth(test)
    if truth is not None:
        return truth
    if isinstance(test, ast.Compare):
        operands = [test.left] + test.comparators
        return any(
            isinstance(op, _ALWAYS_TRUE)
            and not any(
                isinstance(node, ast.Call)
                for expr in (left, right)
                for node in ast.walk(expr)
            )
            and ast.dump(left) == ast.dump(right)
            for left, op, right in zip(
                operands[:-1], test.ops, operands[1:], strict=True
            )
        )
    return False


def _literal(expr: ast.expr) -> Any:
    """Fold only literal values and operators; unsupported or costly input raises."""
    value: Any
    if isinstance(expr, ast.Constant):
        value = expr.value
    elif isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
        items = [_literal(item) for item in expr.elts]
        value = (
            tuple(items)
            if isinstance(expr, ast.Tuple)
            else (set(items) if isinstance(expr, ast.Set) else items)
        )
    elif isinstance(expr, ast.Dict):
        if any(key is None for key in expr.keys):
            raise ValueError("dictionary unpacking is not literal")
        value = {
            _literal(key): _literal(item)
            for key, item in zip(expr.keys, expr.values, strict=True)
            if key is not None
        }
    elif isinstance(expr, ast.UnaryOp):
        operand = _literal(expr.operand)
        if isinstance(expr.op, ast.Not):
            value = not operand
        elif isinstance(expr.op, ast.UAdd):
            value = +operand
        elif isinstance(expr.op, ast.USub):
            value = -operand
        elif isinstance(expr.op, ast.Invert):
            value = ~operand
        else:
            raise ValueError("unsupported unary operator")
    elif isinstance(expr, ast.BinOp) and type(expr.op) in _BINARY:
        left, right = _literal(expr.left), _literal(expr.right)
        if isinstance(expr.op, (ast.Pow, ast.LShift, ast.RShift)):
            if abs(right) > _LITERAL_LIMIT:
                raise ValueError("literal exponent or shift exceeds folding bound")
            if (
                isinstance(expr.op, ast.Pow)
                and isinstance(left, int)
                and isinstance(right, int)
                and left.bit_length() * max(right, 0) > _LITERAL_LIMIT
            ):
                raise ValueError("literal power exceeds folding bound")
        if isinstance(expr.op, ast.Mult):
            for sequence, count in ((left, right), (right, left)):
                if (
                    isinstance(sequence, (str, bytes, tuple, list))
                    and isinstance(count, int)
                    and len(sequence) * count > _LITERAL_LIMIT
                ):
                    raise ValueError("literal repetition exceeds folding bound")
        if isinstance(expr.op, ast.Mod) and isinstance(left, (str, bytes)):
            raise ValueError("formatting is not literal arithmetic")
        value = _BINARY[type(expr.op)](left, right)
    elif isinstance(expr, ast.Compare):
        left = _literal(expr.left)
        for op, comparator in zip(expr.ops, expr.comparators, strict=True):
            right = _literal(comparator)
            if not _COMPARE[type(op)](left, right):
                return False
            left = right
        return True
    elif isinstance(expr, ast.BoolOp):
        for item in expr.values:
            value = _literal(item)
            if isinstance(expr.op, ast.Or) == bool(value):
                break
    else:
        raise ValueError("expression is not literal arithmetic or logic")
    if isinstance(value, int) and value.bit_length() > _LITERAL_LIMIT:
        raise ValueError("literal integer exceeds folding bound")
    if (
        isinstance(value, (str, bytes, tuple, list, set, dict))
        and len(value) > _LITERAL_LIMIT
    ):
        raise ValueError("literal collection exceeds folding bound")
    return value


def _constant_value(expr: ast.expr) -> object:
    if any(
        isinstance(node, (ast.Name, ast.Attribute, ast.Call)) for node in ast.walk(expr)
    ):
        return _UNKNOWN
    try:
        return _literal(expr)
    except (ValueError, TypeError, ArithmeticError):
        # An expression that would raise is a failing check, not a tautology.
        return _UNKNOWN


def _truth(expr: ast.expr) -> Optional[bool]:
    """Known truth from bounded literal folding or boolean structure, else None."""
    constant = _constant_value(expr)
    if constant is not _UNKNOWN:
        return bool(constant)
    if isinstance(expr, ast.Constant):
        return bool(expr.value)
    if isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
        if any(isinstance(item, ast.Starred) for item in expr.elts):
            return (
                True
                if any(not isinstance(item, ast.Starred) for item in expr.elts)
                else None
            )
        return bool(expr.elts)
    if isinstance(expr, ast.Dict):
        return (
            True
            if any(key is not None for key in expr.keys)
            else (None if expr.keys else False)
        )
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        value = _truth(expr.operand)
        return not value if value is not None else None
    if isinstance(expr, ast.BoolOp):
        values = [_truth(value) for value in expr.values]
        if isinstance(expr.op, ast.Or):
            return (
                True
                if True in values
                else (False if all(v is False for v in values) else None)
            )
        return (
            False
            if False in values
            else (True if all(v is True for v in values) else None)
        )
    return None


def _is_expectation(
    call: ast.Call, symbols: Dict[str, Tuple[str, Optional[str]]], *, entered: bool
) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr.startswith(_MOCK_ASSERT_PREFIX):
        return True
    chain = _chain(func)
    if chain is None:
        return False
    head, _, attr = chain.partition(".")
    bound = symbols.get(head)
    return (
        bound is not None
        and bound[0] == "@pytest"
        and (attr or bound[1]) in _EXPECTS
        and ((attr or bound[1]) == "fail" or entered or len(call.args) > 1)
    )


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
    tautology: List[int]
    swallowed: List[int]
    calls: List[ast.Call]


class _Binding(NamedTuple):
    value: Optional[ast.expr]
    scope: "_Scope"
    kind: str


class _Scope:
    """All bindings of each name in a function or comprehension."""

    def __init__(
        self, parent: Optional["_Scope"] = None, *, kind: str = "function"
    ) -> None:
        self.parent = parent
        self.kind = kind
        self.globals: Set[str] = set()
        self.nonlocals: Set[str] = set()
        self.bindings: Dict[str, List[_Binding]] = {}

    def bind(
        self, name: str, value: Optional[ast.expr] = None, kind: str = "unknown"
    ) -> None:
        self.owner(name).bindings.setdefault(name, []).append(
            _Binding(value, self, kind)
        )

    def owner(self, name: str) -> "_Scope":
        if name in self.globals:
            module = self
            while module.parent is not None:
                module = module.parent
            return module
        if name in self.nonlocals:
            scope: Optional[_Scope] = self.parent
            while scope is not None:
                if scope.kind == "function" and name in scope.bindings:
                    return scope
                scope = scope.parent
        return self

    def lookup(self, name: str) -> Optional[_Binding]:
        if name in self.bindings:
            entries = self.bindings[name]
            return entries[0] if len(entries) == 1 else None
        return self.parent.lookup(name) if self.parent else None

    def binds(self, name: str) -> bool:
        # Module consumers have their own policy; only lexical locals shadow here.
        if self.kind == "module":
            return False
        return name in self.bindings or (
            self.parent is not None and self.parent.binds(name)
        )

    def receiver(self, value: ast.expr, seen: Optional[Set[_Binding]] = None) -> bool:
        if not isinstance(value, ast.Name):
            return False
        binding = self.lookup(value.id)
        if binding is None or binding in (seen or set()):
            return False
        if binding.kind == "receiver":
            return True
        if binding.value is None:
            return False
        seen = (seen or set()) | {binding}
        if binding.kind == "alias":
            return binding.scope.receiver(binding.value, seen)
        if binding.kind == "display" and isinstance(
            binding.value, (ast.Tuple, ast.List)
        ):
            return bool(binding.value.elts) and all(
                binding.scope.receiver(element, seen) for element in binding.value.elts
            )
        return False


_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_Comprehension = ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp


class _BindingIndex:
    """Index every binding, routing nested global/nonlocal writes to its owner."""

    def __init__(self, node: ast.Module) -> None:
        self.scope = _Scope(kind="module")
        self.scopes: Dict[ast.AST, _Scope] = {}
        self.pending: List[
            Tuple[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, _Scope]
        ] = []
        self._body(node, self.scope)

    def _body(self, node: ast.Module | _Function | ast.ClassDef, scope: _Scope) -> None:
        self.scopes[node] = scope
        # Declarations apply to the entire scope, including preceding text.
        for child in source_tree.scope_nodes(node):
            if isinstance(child, ast.Global):
                scope.globals.update(child.names)
            elif isinstance(child, ast.Nonlocal):
                scope.nonlocals.update(child.names)
        if isinstance(node, _Function):
            for arg in (
                node.args.posonlyargs
                + node.args.args
                + node.args.kwonlyargs
                + [a for a in (node.args.vararg, node.args.kwarg) if a]
            ):
                scope.bind(arg.arg)
        for statement in node.body:
            self._index(statement, scope)
        # Finish the enclosing scope before resolving any nested nonlocal.
        pending, self.pending = self.pending, []
        for child, parent in pending:
            # Class namespaces never supply a method's or nested class's free names.
            while parent.kind == "class" and parent.parent is not None:
                parent = parent.parent
            self._body(
                child,
                _Scope(
                    parent,
                    kind="class" if isinstance(child, ast.ClassDef) else "function",
                ),
            )

    @staticmethod
    def _elements(node: _Comprehension) -> List[ast.expr]:
        return [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]

    def _target(
        self,
        target: ast.expr,
        scope: _Scope,
        value: Optional[ast.expr] = None,
        kind: str = "unknown",
        value_scope: Optional[_Scope] = None,
    ) -> None:
        if isinstance(target, ast.Name):
            scope.owner(target.id).bindings.setdefault(target.id, []).append(
                _Binding(value, value_scope or scope, kind)
            )
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._target(element, scope)
        elif isinstance(target, ast.Starred):
            self._target(target.value, scope)

    def _index(self, node: ast.AST, scope: _Scope) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope.bind(
                node.name, kind="function" if isinstance(node, _Function) else "class"
            )
            self.pending.append((node, scope))
            for decorator in node.decorator_list:
                self._index(decorator, scope)
            if isinstance(node, ast.ClassDef):
                for expression in [*node.bases, *node.keywords]:
                    self._index(expression, scope)
            else:
                self._index(node.args, scope)
                if node.returns is not None:
                    self._index(node.returns, scope)
            return
        if isinstance(node, ast.Lambda):
            self._index(node.args, scope)
            return
        if isinstance(node, _COMPREHENSIONS):
            inner = _Scope(scope, kind="comprehension")
            self.scopes[node] = inner
            for index, generator in enumerate(node.generators):
                owner = scope if index == 0 else inner
                self._target(generator.target, inner)
                # The iterable is evaluated outside its first target's scope.
                if isinstance(generator.target, ast.Name):
                    inner.bindings[generator.target.id][-1] = _Binding(
                        generator.iter, owner, "display"
                    )
                self._index(generator.iter, owner)
                for condition in generator.ifs:
                    self._index(condition, inner)
            for element in self._elements(node):
                self._index(element, inner)
            return
        if isinstance(node, ast.NamedExpr):
            owner = scope
            while owner.kind == "comprehension" and owner.parent is not None:
                owner = owner.parent
            self._target(node.target, owner, node.value, "alias", scope)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                self._target(target, scope, node.value, "alias")
        elif isinstance(node, ast.AugAssign):
            self._target(node.target, scope)
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                self._target(target, scope)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            self._target(node.target, scope, node.iter, "display")
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            self._target(node.optional_vars, scope)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            scope.bind(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                scope.bind(alias.asname or alias.name.split(".")[0], kind="import")
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            scope.bind(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            scope.bind(node.rest)
        for child in ast.iter_child_nodes(node):
            self._index(child, scope)

    def mark_receiver(self, func: _Function) -> None:
        """Seed a direct TestCase instance method's receiver in its lexical scope."""
        positional = func.args.posonlyargs + func.args.args
        decorators = {
            (_chain(d.func if isinstance(d, ast.Call) else d) or "").split(".")[-1]
            for d in func.decorator_list
        }
        receiver = (
            positional[0]
            if positional
            and len(func.args.defaults) < len(positional)
            and not decorators.intersection({"staticmethod", "classmethod"})
            else None
        )
        if receiver is not None:
            entries = self.scopes[func].bindings[receiver.arg]
            entries[0] = _Binding(None, self.scopes[func], "receiver")


class _Execution:
    """Bindings and nodes that can run, with generator consumption propagated."""

    def __init__(
        self,
        func: _Function,
        consumers: Dict[str, str],
        bindings: _BindingIndex,
    ) -> None:
        # Reuse the outer index so closure values keep their defining scopes.
        self.scope = bindings.scopes[func]
        self.scopes = bindings.scopes
        self.module_bindings = bindings.scope
        self.active: Dict[ast.AST, _Scope] = {}
        self.consumed: Set[Tuple[ast.expr, _Scope, bool]] = set()
        self.consumers = consumers
        for statement in func.body:
            self._walk(statement, self.scope)

    @staticmethod
    def _async_generator(value: ast.GeneratorExp) -> bool:
        """Whether iteration of this generator requires the async protocol."""
        if any(generator.is_async for generator in value.generators):
            return True
        # The first iterable runs in the enclosing scope at construction;
        # only suspension in the generator's own body makes it async.
        pending: List[ast.AST] = [value.elt]
        for index, generator in enumerate(value.generators):
            if index:
                pending.append(generator.iter)
            pending.extend(generator.ifs)
        while pending:
            node = pending.pop()
            if isinstance(node, ast.Await):
                return True
            if isinstance(node, ast.Lambda):
                # Defaults run here; the lambda's body has its own scope.
                pending.append(node.args)
                continue
            if isinstance(node, ast.GeneratorExp):
                pending.append(node.generators[0].iter)
                continue
            if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)) and any(
                generator.is_async for generator in node.generators
            ):
                # Eager async comprehensions suspend their enclosing scope.
                return True
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            pending.extend(ast.iter_child_nodes(node))
        return False

    def _consume(
        self, value: ast.expr, scope: _Scope, *, asynchronous: bool = False
    ) -> None:
        if (value, scope, asynchronous) in self.consumed:
            return
        self.consumed.add((value, scope, asynchronous))
        if isinstance(value, ast.Name):
            binding = scope.lookup(value.id)
            if binding and binding.kind == "alias" and binding.value is not None:
                self._consume(binding.value, binding.scope, asynchronous=asynchronous)
        elif isinstance(value, ast.GeneratorExp):
            if self._async_generator(value) != asynchronous:
                return
            self._comprehension(value, scope, consumed=True)

    def _comprehension(
        self, node: _Comprehension, scope: _Scope, *, consumed: bool
    ) -> None:
        inner = self.scopes[node]
        for index, generator in enumerate(node.generators):
            if index and not consumed:
                break
            owner = scope if index == 0 else inner
            self._walk(generator.iter, owner)
            if consumed:
                self._consume(
                    generator.iter, owner, asynchronous=bool(generator.is_async)
                )
                self._walk(generator.target, inner)
                for condition in generator.ifs:
                    self._walk(condition, inner)
        if consumed:
            for element in _BindingIndex._elements(node):
                self._walk(element, inner)

    def _walk(self, node: ast.AST, scope: _Scope) -> None:
        self.active[node] = scope
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            return
        if isinstance(node, _COMPREHENSIONS):
            self._comprehension(
                node, scope, consumed=not isinstance(node, ast.GeneratorExp)
            )
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            entries = self.module_bindings.bindings.get(name, [])
            # Builtin policies describe the builtin itself. Custom consumers
            # may have one module definition/import, but no local binding.
            module_ok = not entries or (
                not hasattr(builtins, name)
                and len(entries) == 1
                and entries[0].kind in ("function", "import")
            )
            position = (
                self.consumers.get(name)
                if module_ok and not scope.binds(name)
                else None
            )
            if (
                position is not None
                and node.args
                and not node.keywords
                and not any(isinstance(arg, ast.Starred) for arg in node.args)
                and (position == "first" or len(node.args) == 1)
            ):
                self._consume(node.args[0], scope)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, (ast.Tuple, ast.List)) for target in node.targets
        ):
            self._consume(node.value, scope)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            self._consume(node.iter, scope, asynchronous=isinstance(node, ast.AsyncFor))
        elif isinstance(node, (ast.Starred, ast.YieldFrom)):
            self._consume(node.value, scope)
        for child in ast.iter_child_nodes(node):
            self._walk(child, scope)


def _unittest_assertion(call: ast.Call, scope: _Scope) -> bool:
    """Whether a call uses TestCase's assertion contract on a bound receiver."""
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and scope.receiver(func.value)
        and (
            func.attr == "fail"
            or (func.attr.startswith("assert") and func.attr[6:7].isupper())
        )
    )


def _unittest_expression(call: ast.Call) -> Optional[ast.expr]:
    """Translate simple TestCase assertions for the shared tautology judge."""
    assert isinstance(call.func, ast.Attribute)
    name = call.func.attr
    if len(call.args) >= 1:
        if name == "assertTrue":
            return call.args[0]
        if name == "assertFalse":
            return ast.UnaryOp(op=ast.Not(), operand=call.args[0])
    if name == "assertEqual" and len(call.args) >= 2:
        return ast.Compare(
            left=call.args[0], ops=[ast.Eq()], comparators=[call.args[1]]
        )
    return None


def _read(
    func: _Function,
    symbols: Dict[str, Tuple[str, Optional[str]]],
    consumers: Dict[str, str],
    bindings: _BindingIndex,
) -> _Body:
    """What *func*'s body asserts, the handlers in it that swallow, and the
    calls it makes in its own scope, including nested blocks; a nested
    function contributes assertions only when called as a helper."""
    real, tautology, swallowed = 0, [], []
    calls: List[ast.Call] = []
    execution = _Execution(func, consumers, bindings)
    nodes = execution.active
    # A call through a comprehension's own name cannot reach a helper of
    # this scope, but an assertion method called through it still asserts.
    shadowed = source_tree.shadowed_calls(func)
    entered = {node.context_expr for node in nodes if isinstance(node, ast.withitem)}
    for node in nodes:
        if isinstance(node, ast.Assert):
            if _is_tautology(node.test):
                tautology.append(node.lineno)
            else:
                real += 1
        elif isinstance(node, ast.Call):
            if _unittest_assertion(node, nodes[node]):
                assert isinstance(node.func, ast.Attribute)
                if node.func.attr in _UNITTEST_EXPECTS:
                    before_callable = _UNITTEST_EXPECTS[node.func.attr]
                    if node not in entered and (
                        before_callable is None or len(node.args) <= before_callable
                    ):
                        continue
                expression = _unittest_expression(node)
                if expression is not None and _is_tautology(expression):
                    tautology.append(node.lineno)
                else:
                    real += 1
            elif _is_expectation(node, symbols, entered=node in entered):
                real += 1
            elif node not in shadowed:
                calls.append(node)
        elif isinstance(node, ast.ExceptHandler) and _swallows(node):
            swallowed.append(node.lineno)
    return _Body(real, tautology, swallowed, calls)


class _Judge:
    """Resolves helpers across one scan with a configured bounded parse cache."""

    def __init__(
        self,
        root: str,
        roots: Tuple[str, ...],
        depth: int,
        search_roots: List[str],
        consumers: Dict[str, str],
    ) -> None:
        self.root = root
        self.roots = roots
        self.depth = depth
        self.search_roots = search_roots
        self.consumers = consumers
        self.module = bounded(root)(self._module)

    def _module(self, path: str) -> _Module:
        return _Module(self.root, path, self.search_roots)

    def callee(
        self, call: ast.Call, module: _Module, cls: Optional[str], caller: _Function
    ) -> Optional[Tuple[str, str]]:
        """`(file, qualified name)` of the helper *call* names, when it is a
        function of *module* or of a module under the roots it imports."""
        func = call.func
        symbols = module.symbols(caller)
        found: Optional[Tuple[str, str]] = None
        if isinstance(func, ast.Name):
            bound = symbols.get(func.id)
            if bound and bound[1] is not None:
                found = (bound[0], bound[1])
        elif isinstance(func, ast.Attribute) and (owner := _chain(func.value)):
            bound = symbols.get(owner)
            if owner in _SELF_NAMES and cls is not None:
                found = (module.path, "%s::%s" % (cls, func.attr))
            elif (
                bound
                and bound[0] == module.path
                and bound[1] is not None
                and bound[1].startswith("@class:")
            ):
                found = (
                    module.path,
                    "%s::%s" % (bound[1][len("@class:") :], func.attr),
                )
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
        caller: _Function,
        level: int,
        seen: Set[Tuple[str, str]],
    ) -> Tuple[bool, Set[Tuple[str, int]]]:
        """Real assertions and every tautology's source within the depth cap.

        Each path stops at a cycle; source sites are deduplicated across paths
        so repeated calls do not multiply a test's findings.
        """
        real = False
        tautologies: Set[Tuple[str, int]] = set()
        if level > self.depth:
            return real, tautologies
        for call in calls:
            target = self.callee(call, module, cls, caller)
            if target is None or target in seen:
                continue
            helper_module = self.module(target[0])
            found = helper_module.lookup(target[1])
            if found is None:
                continue
            body = _read(
                found[0],
                helper_module.symbols(found[0]),
                self.consumers,
                helper_module.binding_index,
            )
            tautologies.update((target[0], line) for line in body.tautology)
            deeper_real, deeper = self.helpers_assert(
                body.calls,
                helper_module,
                found[1],
                found[0],
                level + 1,
                seen | {target},
            )
            real = real or bool(body.real) or deeper_real
            tautologies.update(deeper)
        return real, tautologies

    def judge(self, path: str) -> Tuple[int, List[Finding]]:
        module = self.module(path)
        tests = _tests(module)
        findings: List[Finding] = []
        for name, func, cls in tests:
            body = _read(
                func,
                module.symbols(func),
                self.consumers,
                module.binding_index,
            )
            real, tautologies = self.helpers_assert(
                body.calls, module, cls, func, 1, {(path, name)}
            )
            tautologies.update((path, line) for line in body.tautology)
            findings.extend(
                Finding(
                    path,
                    line if source == path else func.lineno,
                    name,
                    TAUTOLOGY,
                    "an assertion is statically true or compares a value with itself"
                    + (" (helper %s:%d)" % (source, line) if source != path else ""),
                )
                for source, line in sorted(tautologies)
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
            if not (body.real or real or tautologies):
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
    *,
    settings: Optional[Policy] = None,
) -> Tuple[int, List[Finding]]:
    """`(test functions read, findings)` over *files* under *root*, sorted by
    file and line. Raises source_tree.SourceTreeError naming a file it cannot
    parse. Uses *settings*' consumers when supplied; otherwise reads policy
    once and can raise config_loader.ConfigError naming a refused key."""
    consumers = (
        settings.consumers
        if settings is not None
        else config_loader.resolve(
            config_loader.read(root),
            config_loader.rows(CONSUMERS),
            config_loader.CONFIG_FILE,
        )[CONSUMERS]
    )
    judge = _Judge(root, roots, depth, search_roots, consumers)
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
