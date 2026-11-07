"""
title: Integration — test packages cannot shadow project imports
summary: Fail when a test package shadows a module or package in scripts, src or a root a test module or conftest adds to sys.path; unresolved path expressions fail with their source location.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]


def _dotted(node, aliases):
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return _dotted(node.value, aliases) + "." + node.attr
    return ""


def _path_value(node, bindings, aliases, resolving=()):
    """Evaluate path syntax only; never execute a test module or its calls."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)):
        return node.value
    if isinstance(node, ast.Name) and node.id in bindings:
        if node.id in resolving:
            raise ValueError("cyclic path binding: " + node.id)
        return _path_value(bindings[node.id], bindings, aliases, (*resolving, node.id))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return Path(_path_value(node.left, bindings, aliases, resolving)) / _path_value(
            node.right, bindings, aliases, resolving
        )
    if isinstance(node, ast.Attribute) and node.attr in {"parent", "parents"}:
        path = Path(_path_value(node.value, bindings, aliases, resolving))
        return path.parent if node.attr == "parent" else path.parents
    if isinstance(node, ast.Subscript):
        value = _path_value(node.value, bindings, aliases, resolving)
        index = _path_value(node.slice, bindings, aliases, resolving)
        return value[index]
    if isinstance(node, ast.Call) and not node.keywords:
        name = _dotted(node.func, aliases)
        args = [_path_value(arg, bindings, aliases, resolving) for arg in node.args]
        if name in {"str", "pathlib.Path", "os.path.abspath"} and len(args) == 1:
            return str(args[0]) if name == "str" else Path(args[0]).absolute()
        if name == "os.path.dirname" and len(args) == 1:
            return str(Path(args[0]).parent)
        if name == "os.path.join" and args:
            return str(Path(*args))
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"resolve", "absolute"}
            and not args
        ):
            return Path(
                _path_value(node.func.value, bindings, aliases, resolving)
            ).resolve()
    raise ValueError("unsupported path expression: " + ast.unparse(node))


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
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings = bindings.copy()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # A local argument must never inherit an unrelated global value.
                for arg in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                ):
                    bindings.pop(arg.arg, None)
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = node.value
        if isinstance(node, ast.Call):
            name = _dotted(node.func, aliases)
            if name in {"sys.path.insert", "sys.path.append"}:
                index = 1 if name.endswith("insert") else 0
                try:
                    value = _path_value(node.args[index], bindings, aliases)
                    resolved = (root / value).resolve()
                except (ValueError, TypeError, IndexError) as exc:
                    raise AssertionError(
                        "%s:%s: cannot resolve sys.path root: %s"
                        % (path.relative_to(root), node.lineno, exc)
                    ) from exc
                if resolved.is_relative_to(root):
                    roots.add(resolved)
        for child in ast.iter_child_nodes(node):
            scan(child, bindings)

    scan(tree, {"__file__": ast.Constant(str(path))})
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
    ],
)
def test_unresolved_sys_path_root_names_the_source_location(tmp_path, source):
    path = tmp_path / "test_paths.py"
    path.write_text("import sys\n" + source, encoding="utf-8")
    line = next(
        i for i, text in enumerate(source.splitlines(), 2) if "sys.path" in text
    )
    with pytest.raises(
        AssertionError, match=r"test_paths\.py:%s: cannot resolve" % line
    ):
        _sys_path_roots(path, tmp_path)


def test_import_names_exclude_cache_and_nonidentifiers(tmp_path):
    for name in ("__pycache__", "not-a-package", "namespace"):
        (tmp_path / name).mkdir()
    for name in ("not-a-module.py", "module.py", "__init__.py", "readme.md"):
        (tmp_path / name).touch()
    assert _import_names({tmp_path}) == {"namespace", "module"}
