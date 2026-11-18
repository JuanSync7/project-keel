"""
title: Integration — the ship set covers every project-rendering test module
kind: tests
layer: n/a
summary: Derives renderer modules from Copier APIs and child processes across test helpers, imports and fixtures, and fails a missing, stale or empty tests.ship_set. Exercises the real test-ship recipe with a scratch selection and an unselected failing module, without rendering a project.
"""

import ast
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from test_scratch_root_gate import child_timeout

import makefile_judge
import script_copy

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="not a copier template — this is a generated project",
    ),
]


_RENDER_APIS = {"run_copy", "run_update", "Worker"}


class RenderScan:
    """Resolve local bindings and render sites without executing test code."""

    def __init__(self, root, path):
        self.root = root
        self.path = path
        self.rel = path.relative_to(root).as_posix()
        self.tree = ast.parse(path.read_text(encoding="utf-8"), filename=self.rel)
        self.parents = {}
        self.containers = {}
        self.bindings = {}
        self.imports = []
        self.functions = {}
        self.sites = set()
        self._index(self.tree, self.tree)

    def fail(self, node, detail):
        raise ValueError(f"{self.rel}:{node.lineno}: {detail}")

    def _bind(self, scope, name, value):
        self.bindings.setdefault((scope, name), []).append(value)

    def _index(self, node, scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self.functions.setdefault(node.name, []).append(node)
            scope = node
        self.parents[node] = scope
        if isinstance(node, ast.Import):
            self.imports.append(node)
            for alias in node.names:
                self._bind(scope, alias.asname or alias.name.split(".")[0], alias)
        elif isinstance(node, ast.ImportFrom):
            self.imports.append(node)
            for alias in node.names:
                self._bind(scope, alias.asname or alias.name, (node, alias))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and node.value is not None:
                    self._bind(scope, target.id, node.value)
        for child in ast.iter_child_nodes(node):
            self.containers[child] = node
            self._index(child, scope)

    def values(self, node):
        scope = self.parents[node]
        local = self.bindings.get((scope, node.id), [])
        if local:
            return local
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            arg.arg == node.id
            for arg in scope.args.posonlyargs + scope.args.args + scope.args.kwonlyargs
        ):
            return []
        return self.bindings.get((self.tree, node.id), [])

    def qualified(self, node, seen=frozenset()):
        if node in seen:
            return None
        seen = seen | {node}
        if isinstance(node, ast.alias):
            return node.name if node.asname else node.name.split(".")[0]
        if isinstance(node, tuple):
            origin, alias = node
            return (origin.module or "") + "." + alias.name
        if isinstance(node, ast.Name):
            names = {self.qualified(value, seen) for value in self.values(node)}
            if len(names) > 1 and any(self.is_copier(name) for name in names):
                self.fail(node, "ambiguous Copier binding " + node.id)
            return next(iter(names)) if len(names) == 1 else None
        if isinstance(node, ast.Attribute):
            base = self.qualified(node.value, seen)
            return base + "." + node.attr if base else None
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if (
                (
                    name in {"importorskip", "import_module"}
                    or (
                        isinstance(node.func, ast.Name) and node.func.id == "__import__"
                    )
                )
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                return (
                    node.args[0].value if isinstance(node.args[0].value, str) else None
                )
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and node.args
                and self.is_copier(self.qualified(node.args[0], seen))
            ):
                if len(node.args) == 2 and isinstance(node.args[1], ast.Constant):
                    return (
                        self.qualified(node.args[0], seen)
                        + "."
                        + str(node.args[1].value)
                    )
                self.fail(node, "unresolved dynamic Copier attribute")
        return None

    @staticmethod
    def is_copier(name):
        return isinstance(name, str) and (
            name == "copier" or name.startswith("copier.")
        )

    def text(self, node, seen=frozenset()):
        if node in seen:
            return None
        seen = seen | {node}
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            values = {self.text(value, seen) for value in self.values(node)}
            return next(iter(values)) if len(values) == 1 else None
        return None

    def vectors(self, node, seen=frozenset()):
        """Keep known argv prefixes even when paths or trailing flags vary."""
        if node in seen:
            return []
        seen = seen | {node}
        if isinstance(node, ast.Name):
            return [
                vector
                for value in self.values(node)
                for vector in self.vectors(value, seen)
            ]
        if isinstance(node, (ast.List, ast.Tuple)):
            vectors = [[]]
            for item in node.elts:
                parts = (
                    self.vectors(item.value, seen)
                    if isinstance(item, ast.Starred)
                    else [[self.text(item)]]
                )
                vectors = [
                    prefix + part for prefix in vectors for part in parts or [[None]]
                ]
            return vectors
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self.vectors(node.left, seen)
            right = self.vectors(node.right, seen)
            return [a + b for a in left or [[None]] for b in right or [[None]]]
        return []

    def render_call(self, node):
        name = self.qualified(node.func)
        tail = name.rsplit(".", 1)[-1] if name else ""
        if self.is_copier(name) and tail in _RENDER_APIS:
            return True
        spelling = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else (node.func.id if isinstance(node.func, ast.Name) else "")
        )
        if spelling in _RENDER_APIS and not self.is_copier(name):
            self.fail(
                node, "unresolved Copier render binding: " + ast.unparse(node.func)
            )
        for arg in node.args + [
            kw.value for kw in node.keywords if kw.arg in {"args", "argv"}
        ]:
            vectors = self.vectors(arg)
            if name and name.startswith("subprocess.") and self.text(arg) is not None:
                vectors = [shlex.split(self.text(arg))]
            for vector in vectors:
                for index, token in enumerate(vector):
                    if not isinstance(token, str) or Path(token).name != "copier":
                        continue
                    # A Copier argv needs a statically named operation. Unknown
                    # path/flag arguments after it do not hide that operation.
                    rest = vector[index + 1 :]
                    if any(
                        word in {"copy", "update"}
                        for word in rest
                        if isinstance(word, str)
                    ):
                        return True
                    if not rest or None in rest:
                        self.fail(arg, "unresolved Copier child-process operation")
        return False

    def scan(self):
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.ImportFrom)
                and self.is_copier(node.module)
                and any(alias.name == "*" for alias in node.names)
            ):
                self.fail(node, "unresolved Copier wildcard import")
            if isinstance(node, ast.Call) and self.render_call(node):
                self.sites.add(self.parents[node])
            if isinstance(node, (ast.Name, ast.Attribute)):
                name = self.qualified(node)
                if (
                    not self.is_copier(name)
                    or name.rsplit(".", 1)[-1] not in _RENDER_APIS
                ):
                    continue
                parent = self.containers[node]
                if isinstance(parent, ast.Call) and parent.func is node:
                    continue
                if (
                    isinstance(parent, ast.Assign)
                    and parent.value is node
                    and all(isinstance(target, ast.Name) for target in parent.targets)
                ):
                    continue
                if (
                    isinstance(parent, ast.AnnAssign)
                    and parent.value is node
                    and isinstance(parent.target, ast.Name)
                ):
                    continue
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    continue
                self.fail(node, "unresolved use of Copier render binding")


def import_modules(scan, node, scans):
    """Resolve test-local absolute, package and relative imports to source files."""
    parent = scan.path.parent
    if isinstance(node, ast.ImportFrom) and node.level:
        for _ in range(node.level - 1):
            parent = parent.parent
        stems = [parent.joinpath(*(node.module or "").split("."))]
    else:
        names = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
        stems = []
        for name in names:
            parts = name.split(".")
            candidates = [
                parent.joinpath(*parts),
                (scan.root / "tests").joinpath(*parts),
                scan.root.joinpath(*parts),
            ]
            resolved = [
                stem
                for stem in candidates
                if stem.with_suffix(".py") in scans or stem / "__init__.py" in scans
            ]
            if resolved:
                stems.append(resolved[0])
            elif len(parts) == 1:
                # Pytest adds test directories to sys.path. A unique helper
                # there is resolvable; two candidates need an explicit import.
                helpers = [path.with_suffix("") for path in scans if path.stem == name]
                if len(helpers) > 1:
                    scan.fail(node, "ambiguous test helper import: " + name)
                stems.extend(helpers or candidates)
            else:
                stems.extend(candidates)
    if isinstance(node, ast.ImportFrom):
        stems += [stem / alias.name for stem in list(stems) for alias in node.names]
    return {
        candidate
        for stem in stems
        for candidate in (stem.with_suffix(".py"), stem / "__init__.py")
        if candidate in scans
    }


def fixture_specs(scan):
    """Read fixture names, autouse and static requests with source locations."""
    fixtures = {}
    requests = set()
    for node in ast.walk(scan.tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            requests.update(arg.arg for arg in node.args.args + node.args.kwonlyargs)
            for decorator in node.decorator_list:
                func = decorator.func if isinstance(decorator, ast.Call) else decorator
                if (
                    scan.qualified(func) == "pytest.fixture"
                    or (isinstance(func, ast.Attribute) and func.attr == "fixture")
                    or (isinstance(func, ast.Name) and func.id == "fixture")
                ):
                    name, autouse = node.name, False
                    for kw in (
                        decorator.keywords if isinstance(decorator, ast.Call) else []
                    ):
                        if kw.arg in {"name", "autouse"}:
                            if not isinstance(kw.value, ast.Constant):
                                scan.fail(kw.value, "unresolved fixture " + kw.arg)
                            if kw.arg == "name":
                                name = kw.value.value
                            else:
                                autouse = kw.value.value
                    fixtures[name] = (node, autouse)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"usefixtures", "getfixturevalue"}
        ):
            for arg in node.args:
                requests.update(fixture_request_names(scan, arg))
    return fixtures, requests


def fixture_request_names(scan, arg):
    """Resolve literal requests and statically parametrized fixture names."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return {arg.value}
    scope = scan.parents[arg]
    if isinstance(arg, ast.Name) and isinstance(
        scope, (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        for decorator in scope.decorator_list:
            if not isinstance(decorator, ast.Call) or len(decorator.args) < 2:
                continue
            if (
                not isinstance(decorator.func, ast.Attribute)
                or decorator.func.attr != "parametrize"
            ):
                continue
            names, choices = decorator.args[:2]
            if isinstance(names, ast.Constant) and isinstance(names.value, str):
                parameters = [name.strip() for name in names.value.split(",")]
                if arg.id in parameters and isinstance(choices, (ast.List, ast.Tuple)):
                    selected = []
                    for choice in choices.elts:
                        value = (
                            choice
                            if len(parameters) == 1
                            else (
                                choice.elts[parameters.index(arg.id)]
                                if isinstance(choice, (ast.List, ast.Tuple))
                                else None
                            )
                        )
                        if not isinstance(value, ast.Constant) or not isinstance(
                            value.value, str
                        ):
                            scan.fail(arg, "unresolved parametrized fixture request")
                        selected.append(value.value)
                    return set(selected)
    return scan.fail(arg, "unresolved fixture request")


def visible_fixtures(path, scans, specs):
    """Follow fixture re-exports and conftest ancestry with local overrides."""

    def exported(provider, seen=frozenset()):
        if provider in seen:
            return {}
        seen = seen | {provider}
        fixtures = {}
        for node in scans[provider].imports:
            if not isinstance(node, ast.ImportFrom):
                continue
            for dependency in import_modules(scans[provider], node, scans):
                for name, value in exported(dependency, seen).items():
                    for alias in node.names:
                        if alias.name not in {name, value[1].name, "*"}:
                            continue
                        function = value[1]
                        explicit_name = any(
                            kw.arg == "name"
                            for decorator in function.decorator_list
                            if isinstance(decorator, ast.Call)
                            for kw in decorator.keywords
                        )
                        binding = (
                            name
                            if explicit_name or alias.name == "*"
                            else alias.asname or name
                        )
                        fixtures[binding] = value
        fixtures.update(
            {
                name: (provider, function, autouse)
                for name, (function, autouse) in specs[provider][0].items()
            }
        )
        return fixtures

    providers = sorted(
        (
            provider
            for provider in specs
            if provider.name == "conftest.py" and provider.parent in path.parents
        ),
        key=lambda provider: len(provider.parts),
    )
    visible = {}
    for provider in providers + [path]:
        visible.update(exported(provider))
    return visible


def renderer_modules(root):
    """Derive renderer tests through every tests Python file and fixture request."""
    root = root.resolve()
    scans = {
        path: RenderScan(root, path) for path in sorted((root / "tests").rglob("*.py"))
    }
    imports, specs = {}, {}
    for path, scan in scans.items():
        scan.scan()
        imports[path] = set().union(
            *(import_modules(scan, node, scans) for node in scan.imports)
        )
        specs[path] = fixture_specs(scan)
    visible = {path: visible_fixtures(path, scans, specs) for path in scans}
    rendered = {path for path, scan in scans.items() if scan.sites}
    functions = {(path, node) for path, scan in scans.items() for node in scan.sites}
    changed = True
    while changed:
        before = (set(rendered), set(functions))
        for path, scan in scans.items():
            if imports[path] & rendered:
                rendered.add(path)
            local_names = {
                node.name
                for owner, node in functions
                if owner == path and hasattr(node, "name")
            }
            for nodes in scan.functions.values():
                for function in nodes:
                    if not isinstance(
                        function, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        continue
                    references = {
                        node.id
                        for node in ast.walk(function)
                        if isinstance(node, ast.Name)
                    }
                    requested = {
                        arg.arg for arg in function.args.args + function.args.kwonlyargs
                    }
                    for node in ast.walk(function):
                        if (
                            isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Attribute)
                            and node.func.attr in {"getfixturevalue", "usefixtures"}
                        ):
                            for arg in node.args:
                                requested.update(fixture_request_names(scan, arg))
                    if (
                        references & local_names
                        or any(
                            name in requested and (provider, fixture) in functions
                            for name, (provider, fixture, _) in visible[path].items()
                        )
                        or imports[path] & rendered
                    ):
                        functions.add((path, function))
            if any(
                (name in specs[path][1] or autouse)
                and (provider, function) in functions
                for name, (provider, function, autouse) in visible[path].items()
            ):
                rendered.add(path)
        changed = before != (rendered, functions)
    return {scans[path].rel for path in rendered if path.name.startswith("test_")}


def ship_set_findings(root, configured):
    """Return missing and stale renderers; an empty derivation always fails."""
    derived = renderer_modules(root)
    findings = []
    if not derived:
        findings.append("zero renderer modules: no ship set was judged")
    findings.extend(
        "tests.ship_set misses " + path for path in sorted(derived - set(configured))
    )
    findings.extend(
        "tests.ship_set names no renderer module: " + path
        for path in sorted(set(configured) - derived)
    )
    if len(configured) != len(set(configured)):
        findings.append("tests.ship_set repeats a module")
    return findings


def test_ship_set_equals_every_renderer_module():
    loaded = config_loader.read(_ROOT, config_loader.CONFIG_FILE)
    configured = config_loader.resolve(
        loaded,
        config_loader.rows(("tests", "ship_set")),
        config_loader.CONFIG_FILE,
        environ={},
    )[("tests", "ship_set")]
    assert ship_set_findings(_ROOT, configured) == []


@pytest.mark.parametrize(
    "source",
    [
        "import copier\ncopier.run_copy('template', 'project')",
        "import copier as render\nrender.run_copy('template', 'project')",
        "from copier import run_copy as render\nrender('template', 'project')",
    ],
)
def test_a_new_renderer_must_join_the_set(tmp_path, source):
    tests = tmp_path / "tests"
    tests.mkdir()
    path = tests / "test_added.py"
    path.write_text(source, encoding="utf-8")
    assert ship_set_findings(tmp_path, []) == [
        "tests.ship_set misses tests/test_added.py"
    ]
    assert ship_set_findings(tmp_path, ["tests/test_added.py"]) == []


def test_zero_renderers_and_stale_paths_fail(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_plain.py").write_text(
        '# copier.run_copy("template", "project")\nTEXT = "copier.run_copy()"\n',
        encoding="utf-8",
    )
    assert ship_set_findings(
        tmp_path, ["tests/test_plain.py", "tests/test_absent.py"]
    ) == [
        "zero renderer modules: no ship set was judged",
        "tests.ship_set names no renderer module: tests/test_absent.py",
        "tests.ship_set names no renderer module: tests/test_plain.py",
    ]


@pytest.mark.parametrize(
    "source",
    [
        "engine = deps.importorskip('copier')\nengine.run_copy('t', 'p')",
        "import copier as engine\nengine.run_update('p')",
        "from copier import run_update as render\nrender('p')",
        "from copier import Worker as Render\nRender(src_path='t', dst_path='p')",
        "engine = deps.importorskip('copier')\nengine.Worker(dst_path='p')",
        "import copier as engine\nrender = engine.run_copy\nrender('t', 'p')",
        "subprocess.run([sys.executable, '-m', 'copier', 'copy', 't', 'p'])",
        "argv = [sys.executable, '-m', 'copier', 'update']\n_run(argv + extra)",
        "from subprocess import run as child\nchild(['/bin/copier', 'copy', 't', 'p'])",
        "from subprocess import run as child\nchild('copier update --defaults', shell=True)",
        "command = 'copier'\nsubprocess.run([command, 'copy', 't', 'p'])",
        "argv = ['copier', 'update']\nsubprocess.run([*argv, 'p'])",
        "import subprocess\ncommand = 'copier copy t p'\nsubprocess.run(command, shell=True)",
    ],
)
def test_every_render_api_and_child_process_joins_the_set(tmp_path, source):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_added.py").write_text(source, encoding="utf-8")
    assert renderer_modules(tmp_path) == {"tests/test_added.py"}


@pytest.mark.parametrize(
    ("helper_path", "helper", "consumer"),
    [
        (
            "helpers.py",
            "import copier as c\ndef render():\n    c.run_copy('t', 'p')\n",
            "from helpers import render\ndef test_project():\n    render()\n",
        ),
        (
            "helpers.py",
            "c = deps.importorskip('copier')\ndef render():\n    c.run_update('p')\n",
            "import tests.helpers as helper\ndef test_project():\n    helper.render()\n",
        ),
        (
            "conftest.py",
            "import pytest\nfrom copier import Worker\n@pytest.fixture\n"
            "def project():\n    return Worker(dst_path='p')\n",
            "def test_project(project):\n    assert project\n",
        ),
        (
            "conftest.py",
            "import pytest\nimport copier as c\n@pytest.fixture(name='project')\n"
            "def generated():\n    return c.run_copy('t', 'p')\n",
            "import pytest\n@pytest.mark.usefixtures('project')\n"
            "def test_project():\n    assert True\n",
        ),
        (
            "conftest.py",
            "import pytest\nimport copier as c\n@pytest.fixture(autouse=True)\n"
            "def project():\n    return c.run_copy('t', 'p')\n",
            "def test_project():\n    assert True\n",
        ),
    ],
)
def test_helpers_and_fixtures_make_their_consumers_renderers(
    tmp_path, helper_path, helper, consumer
):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / helper_path).write_text(helper, encoding="utf-8")
    (tests / "test_consumer.py").write_text(consumer, encoding="utf-8")
    assert renderer_modules(tmp_path) == {"tests/test_consumer.py"}


@pytest.mark.parametrize("explicit_name", [False, True])
def test_reexported_fixture_and_helper_chains_reach_every_consumer(
    tmp_path, explicit_name
):
    tests = tmp_path / "tests"
    tests.mkdir()
    symbol = "implementation" if explicit_name else "project"
    fixture_name = "built" if explicit_name else "project"
    decorator = "@pytest.fixture(name='built')" if explicit_name else "@pytest.fixture"
    sources = {
        "renderers.py": "import copier as c\ndef render():\n    return c.run_copy('t', 'p')\n",
        "fixtures.py": "import pytest\nfrom renderers import render\n"
        f"{decorator}\ndef {symbol}():\n    return render()\n",
        "conftest.py": f"from fixtures import {symbol} as built\n",
        "test_consumer.py": "def test_project(built):\n    assert built\n",
        "test_second.py": f"from fixtures import {symbol}\n"
        f"def test_second({fixture_name}):\n    assert {fixture_name}\n",
    }
    for name, source in sources.items():
        (tests / name).write_text(source, encoding="utf-8")
    assert renderer_modules(tmp_path) == {
        "tests/test_consumer.py",
        "tests/test_second.py",
    }


def test_conftest_fixture_scope_and_dependencies(tmp_path):
    tests = tmp_path / "tests"
    nested = tests / "nested"
    nested.mkdir(parents=True)
    (nested / "conftest.py").write_text(
        "import pytest\nimport copier\n@pytest.fixture\n"
        "def rendered():\n    return copier.run_copy('t', 'p')\n"
        "@pytest.fixture\ndef project(rendered):\n    return rendered\n",
        encoding="utf-8",
    )
    for path in (nested / "test_inside.py", tests / "test_outside.py"):
        path.write_text(
            "def test_project(project):\n    assert project\n", encoding="utf-8"
        )
    (nested / "test_unused.py").write_text(
        "def test_plain():\n    assert True\n", encoding="utf-8"
    )
    assert renderer_modules(tmp_path) == {"tests/nested/test_inside.py"}


@pytest.mark.parametrize(
    "source",
    [
        "engine = unknown()\nengine.run_copy('t', 'p')",
        "from copier import *\nrun_update('p')",
        "import copier\nrender = getattr(copier, operation)\nrender('p')",
        "import copier\nengine, other = copier, None\nengine.run_copy('t', 'p')",
        "argv = ['copier', operation]\nsubprocess.run(argv)",
        "import copier\ncallbacks = [copier.run_copy]\ncallbacks[0]('t', 'p')",
        "import copier\nrender, other = copier.run_copy, None\nrender('t', 'p')",
    ],
)
def test_unresolved_render_bindings_fail_with_the_source_location(tmp_path, source):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_unknown.py").write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match=r"tests/test_unknown.py:[1-9][0-9]*:"):
        renderer_modules(tmp_path)


@pytest.mark.parametrize("option", ["-n auto", "--dist worksteal"])
def test_target_requests_workers_and_work_stealing(option):
    command = makefile_judge.dry_run("test-ship")
    assert option in command, command
    assert "--expiring-tier-record" not in command, command


@pytest.mark.parametrize("workers", [0, 2])
@pytest.mark.parametrize("selection", [["tests/test_one.py", "tests/test_two.py"], []])
def test_target_runs_exactly_the_configured_selection(tmp_path, selection, workers):
    script_copy.copy_with_imports(
        tmp_path,
        _ROOT,
        [
            "Makefile",
            "pyproject.toml",
            "config/project.json",
            "tests/conftest.py",
            "scripts/config_get.py",
            "scripts/check_python_version.py",
        ],
    )
    config = tmp_path / "config" / "project.json"
    manifest = json.loads(config.read_text(encoding="utf-8"))
    manifest["tests"]["ship_set"] = selection
    manifest["tests"]["workers"] = workers
    config.write_text(json.dumps(manifest), encoding="utf-8")
    tests = tmp_path / "tests"
    expected_workers = {"gw0", "gw1"} if workers else {"main"}
    for name in ("one", "two"):
        (tests / ("test_" + name + ".py")).write_text(
            "import os\n\n"
            "def test_selected():\n"
            "    worker = os.environ.get('PYTEST_XDIST_WORKER', 'main')\n"
            f"    assert worker in {expected_workers!r}\n",
            encoding="utf-8",
        )
    (tests / "test_unselected.py").write_text(
        "def test_unselected():\n    assert False, 'unselected module ran'\n",
        encoding="utf-8",
    )
    ran = subprocess.run(
        ["make", "test-ship", "PY=" + sys.executable],
        cwd=tmp_path,
        env=build_child_env(),
        capture_output=True,
        text=True,
        timeout=child_timeout(),
    )
    if selection:
        assert ran.returncode == 0, ran.stdout + ran.stderr
        assert "2 passed" in ran.stdout, ran.stdout
        if workers:
            assert "2 workers" in ran.stdout, ran.stdout
    else:
        assert ran.returncode == 2, ran.stdout + ran.stderr
        assert (
            "test-ship: tests.ship_set is empty; configure renderer test modules"
            in ran.stderr
        ), ran.stderr


@pytest.mark.parametrize(
    "value",
    [
        "tests/test_a.py",
        [1],
        ["../test_a.py"],
        ["/test_a.py"],
        ["tests/*.py"],
        ["tests/test a.py"],
        ["-k"],
        ["tests/test_a.py::test_one"],
    ],
)
def test_ship_set_refuses_values_that_are_not_module_paths(value):
    with pytest.raises(config_loader.ConfigError, match="tests.ship_set"):
        config_loader.resolve(
            {"tests": {"ship_set": value}},
            config_loader.rows(("tests", "ship_set")),
            config_loader.CONFIG_FILE,
            environ={},
        )
