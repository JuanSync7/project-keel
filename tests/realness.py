"""
title: Realness — what a test function replaces of the dependency it drives
summary: The judge tests/integration/test_realness_gate.py applies to every test function under config/project.json `test_quality.realness.roots`, from pyverdex's static realness classifier and read from the syntax tree, never run. A test is put in the lowest tier among its signals, `mock` < `fake` < `in_process` < `real`, or `unknown` with none, which means whatever it touched ran unreplaced. A signal comes from a use in its decorators or body of a name an import binds to a library tests/realness_data.py `LIBRARIES` tiers (`use:patch`, `use:unittest.mock.patch`) or of a class `NAMES` tiers (`use:TestClient`); from each fixture it requests, by parameter or `@pytest.mark.usefixtures`, resolved as pytest resolves it, the test's own module first and then each `conftest.py` from its directory up to the root, nearest wins, through the fixtures that fixture requests in turn (`fixture:client->fixture:mocker`), never twice round a cycle; from each autouse fixture of the module or of that conftest chain (`autouse:fixture:stub->fixture:monkeypatch`), because an autouse fixture replaces the dependency for every test under it; and from a plugin's fixture `PLUGIN_FIXTURES` tiers. A fixture none of these defines contributes nothing, and a control signal (`tmp_path`, `caplog`, `freezer`) never demotes. Test functions and files are found as tests/assertion_quality.py finds them. `verdict` turns a scan into the gate's failures: a scan over zero test functions, each `mock` test `test_quality.realness.exempt` does not excuse, named with the signals that put it there, and each excuse whose test is not `mock`. A class-level `usefixtures`, a `pytest_plugins` module and a fixture defined in a class are not read. It reads no file outside the scan and its conftest chains, and writes nothing.
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

import assertion_quality  # noqa: E402
import realness_data  # noqa: E402
import source_tree  # noqa: E402

__all__ = [
    "EXEMPT",
    "FAILING_TIER",
    "Policy",
    "ROOTS",
    "Tiered",
    "UNKNOWN",
    "policy",
    "scan",
    "test_files",
    "verdict",
]

ROOTS = ("test_quality", "realness", "roots")
EXEMPT = ("test_quality", "realness", "exempt")

# The one tier the gate fails: a fake or an in-process app is a working
# substitute, a programmed double is an assumption about the dependency.
FAILING_TIER = "mock"
UNKNOWN = "unknown"

_CONFTEST = "conftest.py"
_SELF_NAMES = ("self", "cls")
_FIXTURE = "fixture"
_USEFIXTURES = "usefixtures"

test_files = assertion_quality.test_files

_Function = ast.FunctionDef | ast.AsyncFunctionDef


class _Signal(NamedTuple):
    label: str
    tier: str


class Tiered(NamedTuple):
    """One test function's tier and the signals at that tier."""

    path: str
    line: int
    test: str
    tier: str
    signals: Tuple[str, ...]

    @property
    def node_id(self) -> str:
        """The function-level pytest node id `test_quality.realness.exempt`
        is keyed by."""
        return "%s::%s" % (self.path, self.test)

    def __str__(self) -> str:
        return "%s:%d: %s: %s: %s" % (
            self.path,
            self.line,
            self.test,
            self.tier,
            ", ".join(self.signals),
        )


class Policy(NamedTuple):
    """The gate's two settings, as config/project.json holds them."""

    roots: Tuple[str, ...]
    exempt: Dict[str, str]


def policy(root: str) -> Policy:
    """config/project.json `test_quality.realness` under *root*. Raises
    config_loader.ConfigError, naming the key, for a value the loader
    refuses."""
    values = config_loader.resolve(
        config_loader.read(root),
        config_loader.rows(ROOTS, EXEMPT),
        config_loader.CONFIG_FILE,
    )
    return Policy(tuple(values[ROOTS]), dict(values[EXEMPT]))


def _library_tier(dotted: str) -> Optional[str]:
    """The tier of the longest prefix of *dotted* `LIBRARIES` names."""
    parts = dotted.split(".")
    for end in range(len(parts), 0, -1):
        tier = realness_data.LIBRARIES.get(".".join(parts[:end]))
        if tier:
            return tier
    return None


def _dotted(node: ast.expr) -> Optional[str]:
    """`a.b.c` for a name or an attribute chain over one, else None."""
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _import_paths(tree: ast.Module) -> Dict[str, str]:
    """Each module-level name an absolute import binds, mapped to the dotted
    path it stands for."""
    out: Dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    out[alias.asname] = alias.name
                else:
                    head = alias.name.split(".")[0]
                    out[head] = head
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                out[alias.asname or alias.name] = node.module + "." + alias.name
    return out


def _fixture(func: _Function) -> Optional[Tuple[str, bool]]:
    """`(the name it is requested by, autouse)` when *func* is a pytest
    fixture, else None."""
    for decorator in func.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        chain = _dotted(call.func if call else decorator)
        if chain is None or chain.rsplit(".", 1)[-1] != _FIXTURE:
            continue
        name, autouse = func.name, False
        for keyword in call.keywords if call else []:
            if not isinstance(keyword.value, ast.Constant):
                continue
            if keyword.arg == "name" and isinstance(keyword.value.value, str):
                name = keyword.value.value
            elif keyword.arg == "autouse":
                autouse = bool(keyword.value.value)
        return name, autouse
    return None


def _requested(func: _Function) -> List[str]:
    """The fixtures *func* requests: its parameters, and the names a
    `usefixtures` mark on it gives."""
    args = func.args
    names = [
        a.arg
        for a in args.posonlyargs + args.args + args.kwonlyargs
        if a.arg not in _SELF_NAMES
    ]
    for decorator in func.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        chain = _dotted(decorator.func)
        if chain is None or chain.rsplit(".", 1)[-1] != _USEFIXTURES:
            continue
        names.extend(
            a.value
            for a in decorator.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)
        )
    return names


class _Module:
    """One parsed file: the dotted paths its imports bind and its
    module-level fixtures by the name each is requested by."""

    def __init__(self, root: str, path: str) -> None:
        self.path = path
        self.tree = source_tree.parse(root, path)
        self.imports = _import_paths(self.tree)
        self.fixtures: Dict[str, Tuple[_Function, bool]] = {}
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found = _fixture(node)
                if found:
                    self.fixtures[found[0]] = (node, found[1])

    def uses(self, func: _Function) -> List[_Signal]:
        """The tiered names *func*'s decorators, defaults and body use: the
        shortest chain an import binds to a `LIBRARIES` path, else a chain
        whose last part `NAMES` tiers."""
        tiered: Dict[str, str] = {}
        for node in ast.walk(func):
            if not isinstance(node, (ast.Name, ast.Attribute)):
                continue
            chain = _dotted(node)
            if chain is None:
                continue
            head, _sep, rest = chain.partition(".")
            path = self.imports.get(head)
            tier = _library_tier(path + ("." + rest if rest else "")) if path else None
            if tier is None:
                tier = realness_data.NAMES.get(chain.rsplit(".", 1)[-1])
            if tier:
                tiered[chain] = tier
        return [
            _Signal("use:" + chain, tier)
            for chain, tier in sorted(tiered.items())
            if not any(chain.startswith(other + ".") for other in tiered)
        ]


class _Tierer:
    """Tiers the test functions of each file it is handed, sharing parsed
    modules across files."""

    def __init__(self, root: str, search_roots: List[str]) -> None:
        self.root = root
        self.search_roots = search_roots
        self.modules: Dict[str, _Module] = {}

    def module(self, path: str) -> _Module:
        if path not in self.modules:
            self.modules[path] = _Module(self.root, path)
        return self.modules[path]

    def scope(self, path: str) -> List[_Module]:
        """*path*'s module, then each `conftest.py` from its directory up to
        the root, nearest first: the order pytest looks a fixture up in."""
        out = [self.module(path)]
        directory = os.path.dirname(path)
        while True:
            conftest = os.path.join(directory, _CONFTEST) if directory else _CONFTEST
            if os.path.isfile(os.path.join(self.root, conftest)):
                out.append(self.module(conftest))
            if not directory:
                return out
            directory = os.path.dirname(directory)

    def fixture(
        self, name: str, scope: List[_Module], stack: Set[str]
    ) -> List[_Signal]:
        """The signals requesting fixture *name* brings, through every
        fixture it requests in turn; *stack* holds the names above it."""
        if name in stack:
            return []
        for module in scope:
            found = module.fixtures.get(name)
            if found is None:
                continue
            func = found[0]
            inner = module.uses(func)
            for dep in _requested(func):
                inner.extend(self.fixture(dep, scope, stack | {name}))
            return [_Signal("fixture:%s->%s" % (name, s.label), s.tier) for s in inner]
        tier = realness_data.PLUGIN_FIXTURES.get(name)
        return [_Signal("fixture:" + name, tier)] if tier else []

    def autouse(self, scope: List[_Module]) -> List[_Signal]:
        """The signals each autouse fixture over *scope* brings; a nearer
        definition of a name hides a farther one."""
        seen: Set[str] = set()
        out: List[_Signal] = []
        for module in scope:
            for name, (_func, autouse) in sorted(module.fixtures.items()):
                if name in seen:
                    continue
                seen.add(name)
                if autouse:
                    out.extend(
                        _Signal("autouse:" + s.label, s.tier)
                        for s in self.fixture(name, scope, set())
                    )
        return out

    def tier(self, path: str) -> List[Tiered]:
        scope = self.scope(path)
        module = scope[0]
        ambient = self.autouse(scope)
        out = []
        for qual, func, _cls in assertion_quality.test_functions(
            self.root, path, self.search_roots
        ):
            signals = module.uses(func) + ambient
            for name in _requested(func):
                signals.extend(self.fixture(name, scope, set()))
            tiers = [s.tier for s in signals]
            tier = min(tiers, key=realness_data.RANKS.__getitem__) if tiers else UNKNOWN
            labels = tuple(sorted({s.label for s in signals if s.tier == tier}))
            out.append(Tiered(path, func.lineno, qual, tier, labels))
        return out


def scan(root: str, files: List[str], search_roots: List[str]) -> List[Tiered]:
    """Every test function of *files* under *root*, tiered, sorted by file
    and line; *search_roots* resolve the imports that name a TestCase base,
    as tests/assertion_quality.py resolves them. Raises
    source_tree.SourceTreeError naming a file it cannot parse."""
    tierer = _Tierer(root, search_roots)
    out: List[Tiered] = []
    for path in files:
        out.extend(tierer.tier(path))
    return sorted(out)


def verdict(
    tiered: List[Tiered], exempt: Dict[str, str], roots: Tuple[str, ...]
) -> List[str]:
    """The gate's failures, one line each: no test function read under
    *roots*, each `mock` test *exempt* does not excuse, and each excuse whose
    test is not `mock`, which has gone stale."""
    if not tiered:
        return [
            "no test function was read under %s: a pass over zero tests is a "
            "failure; check config/project.json %s"
            % (", ".join(roots), ".".join(ROOTS))
        ]
    failed = [t for t in tiered if t.tier == FAILING_TIER]
    failed_ids = {t.node_id for t in failed}
    out = [str(t) for t in failed if t.node_id not in exempt]
    out.extend(
        "%s: stale: config/project.json %s excuses a test the gate does not "
        "fail; remove the entry" % (node_id, ".".join(EXEMPT))
        for node_id in sorted(exempt)
        if node_id not in failed_ids
    )
    return out
