"""
title: Integration — test packages cannot shadow project imports
summary: Fail when a test package shadows a module or package in scripts, src or a root a test module or conftest adds to sys.path; unresolved path expressions fail with their source location.
"""

import ast
from itertools import product
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]


def _dotted(node, aliases):
    """Return an attribute chain with its imported leading name expanded."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return _dotted(node.value, aliases) + "." + node.attr
    return ""


def _path_values(node, bindings, aliases, resolving=()):
    """Evaluate path syntax only; never execute a test module or its calls."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)):
        return [node.value]
    if isinstance(node, ast.Name) and node.id in bindings:
        if node.id in resolving:
            raise ValueError("cyclic path binding: " + node.id)
        alternatives = [
            _path_values(value, bindings, aliases, (*resolving, node.id))
            for value in bindings[node.id]
        ]
        # A later write cannot stand in for the value live at an earlier call.
        keys = [
            {
                Path(value).resolve() if isinstance(value, (str, Path)) else value
                for value in values
            }
            for values in alternatives
        ]
        if len(keys) > 1 and (
            any(key != keys[0] for key in keys[1:]) or len(keys[0]) != 1
        ):
            raise ValueError("ambiguous path binding: " + node.id)
        return alternatives[0]
    if isinstance(node, ast.IfExp):
        return _path_values(node.body, bindings, aliases, resolving) + _path_values(
            node.orelse, bindings, aliases, resolving
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return [
            Path(left) / right
            for left, right in product(
                _path_values(node.left, bindings, aliases, resolving),
                _path_values(node.right, bindings, aliases, resolving),
            )
        ]
    if isinstance(node, ast.Attribute) and node.attr in {"parent", "parents"}:
        return [
            Path(value).parent if node.attr == "parent" else Path(value).parents
            for value in _path_values(node.value, bindings, aliases, resolving)
        ]
    if isinstance(node, ast.Subscript):
        return [
            value[index]
            for value, index in product(
                _path_values(node.value, bindings, aliases, resolving),
                _path_values(node.slice, bindings, aliases, resolving),
            )
        ]
    if isinstance(node, ast.Call) and not node.keywords:
        name = _dotted(node.func, aliases)
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"resolve", "absolute"}
            and not node.args
        ):
            return [
                Path(value).resolve()
                for value in _path_values(node.func.value, bindings, aliases, resolving)
            ]
        values = []
        for args in product(
            *[_path_values(arg, bindings, aliases, resolving) for arg in node.args]
        ):
            if name == "str" and len(args) == 1:
                values.append(str(args[0]))
            elif name == "pathlib.Path" and len(args) == 1:
                values.append(Path(args[0]))
            elif name == "os.path.abspath" and len(args) == 1:
                values.append(Path(args[0]).absolute())
            elif name == "os.path.dirname" and len(args) == 1:
                values.append(str(Path(args[0]).parent))
            elif name == "os.path.join" and args:
                values.append(str(Path(*args)))
            else:
                raise ValueError("unsupported path call: " + ast.unparse(node))
        return values
    raise ValueError("unsupported path expression: " + ast.unparse(node))


def _scope_bindings(node):
    """Collect writes without replacing earlier or mutually exclusive values."""
    bindings = {}

    def bind(target, value):
        if isinstance(target, ast.Name):
            bindings.setdefault(target.id, []).append(value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                # Unpacking needs execution semantics; an unknown write must mask globals.
                bind(element, ast.Constant(None))
        elif isinstance(target, ast.Starred):
            bind(target.value, ast.Constant(None))

    def collect(child):
        if isinstance(child, ast.Lambda):
            return
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bind(ast.Name(child.name), ast.Constant(None))
            return
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            for alias in child.names:
                name = alias.asname or alias.name.split(".")[0]
                bind(ast.Name(name), ast.Constant(None))
            return
        if isinstance(child, ast.ExceptHandler) and child.name:
            bind(ast.Name(child.name), ast.Constant(None))
        if isinstance(child, (ast.MatchAs, ast.MatchStar)) and child.name:
            bind(ast.Name(child.name), ast.Constant(None))
        if isinstance(child, ast.MatchMapping) and child.rest:
            bind(ast.Name(child.rest), ast.Constant(None))
        if isinstance(child, ast.If):
            branches = [
                _scope_bindings(ast.Module(body=body))
                for body in (child.body, child.orelse)
            ]
            for name in branches[0].keys() | branches[1].keys():
                left = branches[0].get(name, [ast.Constant(None)])
                right = branches[1].get(name, [ast.Constant(None)])
                if len(left) == len(right) == 1:
                    bindings.setdefault(name, []).append(
                        ast.IfExp(child.test, left[0], right[0])
                    )
                else:
                    # Sequential writes inside a branch remain ambiguous.
                    bindings.setdefault(name, []).extend([*left, *right])
            collect(child.test)
            return
        if isinstance(child, ast.Assign):
            for target in child.targets:
                bind(target, child.value)
            collect(child.value)
            return
        if isinstance(child, (ast.AnnAssign, ast.NamedExpr)):
            bind(child.target, child.value or ast.Constant(None))
            if child.value is not None:
                collect(child.value)
            return
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            bind(child, ast.Constant(None))
        for descendant in ast.iter_child_nodes(child):
            collect(descendant)

    for child in ast.iter_child_nodes(node):
        collect(child)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        for arg in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            *([node.args.vararg] if node.args.vararg else []),
            *([node.args.kwarg] if node.args.kwarg else []),
        ):
            bindings.setdefault(arg.arg, []).append(ast.Constant(None))
    return bindings


def _sys_path_target(node, aliases):
    """Recognize sys.path and item targets, including destructured assignments."""
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_sys_path_target(element, aliases) for element in node.elts)
    if isinstance(node, (ast.Subscript, ast.Starred)):
        return _sys_path_target(node.value, aliases)
    return _dotted(node, aliases) == "sys.path"


def _sys_path_roots(path, root):
    """Resolve each test's sys.path mutation in its enclosing lexical scopes."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = node.module + "." + alias.name

    roots = set()

    def scan(node, bindings):
        if isinstance(
            node,
            (
                ast.Module,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Lambda,
            ),
        ):
            bindings = bindings | _scope_bindings(node)
        try:
            targets = []
            if isinstance(node, (ast.Assign, ast.Delete)):
                targets = node.targets
            elif isinstance(
                node, (ast.AnnAssign, ast.AugAssign, ast.For, ast.AsyncFor)
            ):
                targets = [node.target]
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                targets = [item.optional_vars for item in node.items]
            elif isinstance(
                node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
            ):
                targets = [generator.target for generator in node.generators]
            if any(_sys_path_target(target, aliases) for target in targets):
                raise ValueError(
                    "unsupported sys.path assignment: " + ast.unparse(node)
                )
            if isinstance(node, ast.Call):
                name = _dotted(node.func, aliases)
                if name in {"sys.path.insert", "sys.path.append"} or name.endswith(
                    ".syspath_prepend"
                ):
                    index = 1 if name == "sys.path.insert" else 0
                    if node.keywords or len(node.args) != index + 1:
                        raise ValueError(
                            "unsupported sys.path call: " + ast.unparse(node)
                        )
                    for value in _path_values(node.args[index], bindings, aliases):
                        resolved = (root / value).resolve()
                        if resolved.is_relative_to(root):
                            roots.add(resolved)
                elif name.startswith("sys.path.") and name.rsplit(".", 1)[1] not in {
                    # These methods cannot introduce a root that shadows imports.
                    "copy",
                    "count",
                    "index",
                    "pop",
                    "remove",
                    "clear",
                    "reverse",
                    "sort",
                }:
                    raise ValueError(
                        "unsupported sys.path mutation: " + ast.unparse(node)
                    )
        except (ValueError, TypeError, IndexError) as exc:
            raise AssertionError(
                "%s:%s: cannot resolve sys.path root: %s"
                % (path.relative_to(root), node.lineno, exc)
            ) from exc
        for child in ast.iter_child_nodes(node):
            scan(child, bindings)

    scan(tree, {"__file__": [ast.Constant(str(path))]})
    return roots


def _import_names(roots):
    import_names = set()
    for code_root in roots:
        if not code_root.is_dir():
            continue
        for path in code_root.iterdir():
            name = path.stem if path.is_file() else path.name
            if name == "__pycache__" or not name.isidentifier():
                continue
            if path.is_dir() or (
                path.is_file() and path.suffix == ".py" and path.stem != "__init__"
            ):
                import_names.add(name)
    return import_names


def test_test_packages_do_not_shadow_project_imports():
    test_roots = set()
    for path in sorted((_ROOT / "tests").rglob("*.py")):
        if path.name == "conftest.py" or path.name.startswith("test_"):
            test_roots.update(_sys_path_roots(path, _ROOT))
    assert test_roots, "No sys.path roots found in test modules or conftest files"
    import_names = _import_names({_ROOT / "scripts", _ROOT / "src"} | test_roots)
    assert import_names, "No project import names found in the derived import roots"
    collisions = sorted(
        str(init.parent.relative_to(_ROOT))
        for init in (_ROOT / "tests").rglob("__init__.py")
        if init.parent.name in import_names
    )
    assert not collisions, (
        "Test packages shadow project imports; remove their __init__.py and use "
        "flat mirror tests instead:\n" + "\n".join(collisions)
    )


@pytest.mark.parametrize(
    "source, relative_root",
    [
        (
            'sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "jobs"))',
            "scripts/jobs",
        ),
        (
            'ROOT = Path(__file__).parent.parent\nsys.path.append(str(ROOT / "src"))',
            "src",
        ),
        (
            'ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nsys.path.insert(0, os.path.join(ROOT, "scripts", "hooks"))',
            "scripts/hooks",
        ),
        (
            'def check():\n    local = Path(__file__).resolve().parents[1]\n    _sys.path.insert(0, str(local / "other"))',
            "other",
        ),
        ('sys.path.append("relative")', "relative"),
        ('monkeypatch.syspath_prepend("relative")', "relative"),
        ('patch.syspath_prepend(str(Path(__file__).parent.parent / "src"))', "src"),
        ('root = "src"\nsys.path.append(root)\nroot = "src"', "src"),
        ('root = "src"\nroot = "./src"\nsys.path.append(root)', "src"),
        (
            'root = "src"\ndef check():\n    root = "other"\n    sys.path.append(root)',
            "other",
        ),
        ('from sys import path as search_path\nsearch_path.append("src")', "src"),
    ],
)
def test_sys_path_roots_resolve_path_expressions(tmp_path, source, relative_root):
    path = tmp_path / "tests" / "test_paths.py"
    path.parent.mkdir()
    path.write_text(
        "import sys\nimport sys as _sys\nimport os\nfrom pathlib import Path\n"
        + source,
        encoding="utf-8",
    )
    assert _sys_path_roots(path, tmp_path) == {tmp_path / relative_root}


@pytest.mark.parametrize(
    "source",
    [
        "sys.path.insert(0, choose_root())",
        "sys.path.append(unknown)",
        "root = root\nsys.path.append(root)",
        'root = "scripts"\ndef check(root):\n    sys.path.append(root)',
        'root = "first"\nsys.path.append(root)\nroot = "second"',
        'root = "first"\nroot = "second"\nsys.path.append(root)',
        'root = "first"\nalias = root\nsys.path.append(alias)\nroot = "second"',
        'root = "first"\nroot += "second"\nsys.path.append(root)',
        'root = "first"\nroot, other = choose()\nsys.path.append(root)',
        'root = "first"\n*root, other = choose()\nsys.path.append(root)',
        'root = "first"\nfor root in choices:\n    sys.path.append(root)',
        'root = "first"\ndef check(*root):\n    sys.path.append(root)',
        'root = "first"\ndef check(**root):\n    sys.path.append(root)',
        'root = "first"\ncheck = lambda root: sys.path.append(root)',
        'root = "first"\ntry:\n    work()\nexcept Exception as root:\n    sys.path.append(root)',
        'root = "first"\nmatch value:\n    case {"path": root}:\n        sys.path.append(root)',
        'root = "first"\nmatch value:\n    case [*root]:\n        sys.path.append(root)',
        'root = "first"\nmatch value:\n    case {**root}:\n        sys.path.append(root)',
        'root = "first"\nimport other as root\nsys.path.append(root)',
        'root = "first"\nif flag:\n    root = "second"\nsys.path.append(root)',
        'if flag:\n    root = "first"\n    root = "second"\nelse:\n    root = "second"\nsys.path.append(root)',
        'sys.path[:0] = ["first"]',
        'sys.path = ["first"] + sys.path',
        'sys.path.extend(["first"])',
        'sys.path += ["first"]',
        "monkeypatch.syspath_prepend(unknown)",
        'sys.path[0] = "first"',
        'sys.path[:] = ["first"]',
        'sys.path: list = ["first"]',
        'sys.path[:] += ["first"]',
        "sys.path *= 2",
        "sys.path[0] *= 2",
        'sys.path, other = ["first"], None',
        "del sys.path[:0]",
        "for sys.path in roots:\n    pass",
        "for sys.path[:] in roots:\n    pass",
        "with context() as sys.path:\n    pass",
        "[None for sys.path in roots]",
        "sys.path.insert(0, *roots)",
        'sys.path.append(root="first")',
        'import sys as _sys\n_sys.path[:0] = ["first"]',
        'from sys import path as search_path\nsearch_path.extend(["first"])',
    ],
)
def test_unresolved_sys_path_root_names_the_source_location(tmp_path, source):
    path = tmp_path / "test_paths.py"
    path.write_text("import sys\n" + source, encoding="utf-8")
    line = next(
        i
        for i, text in enumerate(source.splitlines(), 2)
        if any(
            form in text for form in ("sys.path", ".syspath_prepend", "search_path.")
        )
    )
    with pytest.raises(
        AssertionError, match=r"test_paths\.py:%s: cannot resolve" % line
    ):
        _sys_path_roots(path, tmp_path)


@pytest.mark.parametrize(
    "source, relative_roots",
    [
        ("sys.path.pop(0)", set()),
        ('sys.path.remove("old")', set()),
        ("sys.path.clear()", set()),
        ("sys.path.reverse()", set()),
        ("sys.path.sort()", set()),
        (
            'if flag:\n    root = "first"\nelse:\n    root = "second"\nsys.path.append(root)',
            {"first", "second"},
        ),
        (
            'if flag:\n    root = "first"\nelse:\n    root = "second"\nsys.path.append(str(Path(root) / "nested"))',
            {"first/nested", "second/nested"},
        ),
        (
            'if flag:\n    root = "first"\nelif other:\n    root = "second"\nelse:\n    root = "third"\nsys.path.append(root)',
            {"first", "second", "third"},
        ),
        (
            'root = "first" if flag else "second"\nsys.path.append(root)',
            {"first", "second"},
        ),
        (
            'root = "first"\nroot = "first"\nsys.path.append(root)',
            {"first"},
        ),
        (
            'def first():\n    root = "first"\n    sys.path.append(root)\ndef second():\n    root = "second"\n    sys.path.append(root)',
            {"first", "second"},
        ),
    ],
)
def test_sys_path_roots_preserve_branches_and_scopes(tmp_path, source, relative_roots):
    path = tmp_path / "test_paths.py"
    path.write_text("import sys\nfrom pathlib import Path\n" + source, encoding="utf-8")
    assert _sys_path_roots(path, tmp_path) == {
        tmp_path / relative_root for relative_root in relative_roots
    }


def test_import_names_exclude_cache_and_nonidentifiers(tmp_path):
    for name in ("__pycache__", "not-a-package", "namespace"):
        (tmp_path / name).mkdir()
    for name in ("not-a-module.py", "module.py", "__init__.py", "readme.md"):
        (tmp_path / name).touch()
    assert _import_names({tmp_path}) == {"namespace", "module"}
