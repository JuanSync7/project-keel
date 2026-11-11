"""
title: Integration — imports flow up the configured layer order
kind: tests
layer: n/a
summary: A tree-wide gate over every Python file tests/source_tree.py `python_files` lists (the walk check_structure uses, so vendored and installed code stay out). config/project.json `import_layers.order` lists the layers bottom to top, each a list of path prefixes; a file sits in the layer of its longest prefix, matched by whole path segments (`models` never matches `models_extra/`). Every import `import_edges` resolves through `import_layers.search_roots` must point at the same or a lower layer: an edge into a higher layer is a finding naming the file, the line, both layers and the fix. A file no prefix places, a prefix that is on disk but places no file (stale; a prefix whose path is absent, such as a transport copier pruned, is skipped), a malformed block and a walk that resolved no edge are each red, never a pass. The layer-edge reader cannot see an import made through importlib, `__import__`, or a `sys.path` entry no search root names: such a name is external to it. An import under `TYPE_CHECKING` or inside `try/except ImportError` still counts as an edge. Not a check_* letter: the letters A to Z are taken. docs/adr/keel/K-0021-imports-flow-up-a-configured-layer-order.md is the decision.

The dual-import gate uses one site reader for statements and literal calls to
importlib.import_module, import_module imported from importlib, and __import__.
Relative import_module(".x", "scripts") names scripts.x. A non-literal first
argument is not judged, including in scripts/, tests/integration/ or evals/ files
that also name a scripts/ module: its runtime value cannot be resolved statically
without executing arbitrary code, so guessing could invent or miss an import.
"""

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))

import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration

_CONFIG = st.CONFIG
_BLOCK = st.LAYERS_BLOCK
_FIX = (
    "imports flow up config/project.json import_layers.order, so move the shared "
    "code down or invert the dependency"
)


def placement(relpath, order):
    """(layer index, prefix) of the longest prefix in *order* that holds
    *relpath* by whole path segments, or None."""
    best = None
    for index, layer in enumerate(order):
        for prefix in layer:
            holds = relpath == prefix or relpath.startswith(prefix + "/")
            if holds and (best is None or len(prefix) > len(best[1])):
                best = (index, prefix)
    return best


def _name(order, index):
    return "layer %d (%s)" % (index + 1, ", ".join(order[index]))


def layer_findings(root):
    """{files, edges, findings} for the tree at *root*: one finding per
    upward edge, unplaced file and stale prefix."""
    policy = st.import_layers(root)
    roots, order = policy["search_roots"], policy["order"]
    files = st.python_files(root)
    if not files:
        raise st.SourceTreeError("%s: no Python file to judge -- zero items" % root)
    findings = []
    placed = {}
    for relpath in files:
        where = placement(relpath, order)
        if where is None:
            findings.append(
                "%s:1: no prefix in config/project.json import_layers.order holds "
                "it; add its directory to the layer it belongs in" % relpath
            )
        else:
            placed[relpath] = where
    used = {prefix for _index, prefix in placed.values()}
    findings.extend(
        "%s: import_layers.order names `%s`, which places no Python file; delete "
        "the entry or move it to the files it means" % (_CONFIG, prefix)
        for layer in order
        for prefix in layer
        if prefix not in used and (Path(str(root)) / prefix).exists()
    )
    edges = st.import_edges(root, files, roots)
    for importer, lineno, imported in edges:
        if importer not in placed or imported not in placed:
            continue
        low, high = placed[importer][0], placed[imported][0]
        if high > low:
            findings.append(
                "%s:%d: %s imports %s in the higher %s; %s"
                % (
                    importer,
                    lineno,
                    _name(order, low),
                    imported,
                    _name(order, high),
                    _FIX,
                )
            )
    return {"files": len(files), "edges": len(edges), "findings": sorted(findings)}


# --- the tree itself -------------------------------------------------------------

_RESULT = {}


def _tree_result():
    if not _RESULT:
        _RESULT.update(layer_findings(_ROOT))
    return _RESULT


def test_the_walk_saw_edges():
    result = _tree_result()
    assert result["files"] > 0 and result["edges"] > 0, result


def test_no_import_points_up_the_layer_order():
    findings = [f for f in _tree_result()["findings"] if " imports " in f]
    assert not findings, "\n".join(findings)


def test_every_owned_file_has_a_layer():
    findings = [f for f in _tree_result()["findings"] if "no prefix" in f]
    assert not findings, "\n".join(findings)


def test_every_layer_entry_matches_a_file():
    findings = [f for f in _tree_result()["findings"] if "places no Python file" in f]
    assert not findings, "\n".join(findings)


def _import_names(node: ast.AST, importer: str, calls: set[str]) -> list[str]:
    """Absolute module spellings a statement or literal import call can load."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.Call):
        function = ast.unparse(node.func)
        if function not in calls or not node.args:
            return []
        first = node.args[0]
        if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
            return []
        name = first.value
        if name.startswith("."):
            package = (
                node.args[1]
                if len(node.args) > 1
                else next(
                    (kw.value for kw in node.keywords if kw.arg == "package"), None
                )
            )
            if (
                function == "__import__"
                or not isinstance(package, ast.Constant)
                or not isinstance(package.value, str)
                or not package.value
            ):
                return []
            try:
                name = importlib.util.resolve_name(name, package.value)
            except ImportError:
                # An invalid relative name cannot load a module at runtime.
                return []
        return [name]
    if not isinstance(node, ast.ImportFrom):
        return []
    parts = (node.module or "").split(".") if node.module else []
    if node.level:
        parts = importer.split("/")[: -node.level] + parts
    module = ".".join(parts)
    return [module] + [module + "." + alias.name for alias in node.names]


def _import_sites(tree: ast.Module, importer: str) -> list[tuple[str, int]]:
    """Read statements and calls in one walk, resolving imported call bindings."""
    calls = {"__import__"}
    nodes: list[ast.Import | ast.ImportFrom | ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Call)):
            nodes.append(node)
        if isinstance(node, ast.Import):
            calls.update(
                (alias.asname or "importlib") + ".import_module"
                for alias in node.names
                if alias.name == "importlib"
                or (alias.name.startswith("importlib.") and not alias.asname)
            )
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "importlib"
            and not node.level
        ):
            calls.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "import_module"
            )
    # Delay name resolution so nested calls can use bindings elsewhere in the file.
    return [
        (name, node.lineno)
        for node in nodes
        for name in _import_names(node, importer, calls)
    ]


def _calls_registration(tree: ast.Module, *, is_helper: bool = False) -> bool:
    """Recognize the helper's imported binding, including aliases."""
    functions = {"register_module"} if is_helper else set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in (
            "module_identity",
            "scripts.module_identity",
        ):
            functions.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "register_module"
            )
        if isinstance(node, ast.Import):
            modules.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in ("module_identity", "scripts.module_identity")
            )
    # Definitions do not register the module until called at module scope.
    for node in st.scope_nodes(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ast.unparse(node.func)
        if name in functions or name in {m + ".register_module" for m in modules}:
            return [ast.unparse(arg) for arg in node.args] == ["__name__", "__file__"]
    return False


def dual_import_findings(root: Path) -> list[str]:
    """Find dual-imported scripts without registration, naming both sites."""
    trees: dict[str, ast.Module] = {
        path: st.parse(root, path) for path in st.python_files(root)
    }
    scripts = {
        path[8:-3].replace("/", "."): path
        for path in trees
        if path.startswith("scripts/") and not path.endswith("/__init__.py")
    }
    sites: dict[str, str] = {}
    for path, tree in trees.items():
        for name, lineno in _import_sites(tree, path):
            sites.setdefault(name, "%s:%d" % (path, lineno))
    findings = []
    for name, path in scripts.items():
        dotted = "scripts." + name
        if (
            name in sites
            and dotted in sites
            and not _calls_registration(
                trees[path], is_helper=path == "scripts/module_identity.py"
            )
        ):
            findings.append(
                "%s: call module_identity.register_module(__name__, __file__); "
                "%s imported at %s; %s imported at %s"
                % (path, name, sites[name], dotted, sites[dotted])
            )
    return sorted(findings)


def test_dual_imported_scripts_register_one_module() -> None:
    # This belongs beside import layers because both judge the same source walk.
    findings = dual_import_findings(_ROOT)
    assert not findings, "\n".join(findings)


# --- fixtures: each rule can fail ---------------------------------------------------


def _project(
    tmp_path: Path,
    files: dict[str, str],
    order: list[list[str]] | None = None,
    roots: list[str] | None = None,
) -> Path:
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    policy = {
        "search_roots": roots if roots is not None else ["", "src/"],
        "order": order if order is not None else [["src/shared"], ["agents"]],
    }
    (root / _CONFIG).write_text(json.dumps({_BLOCK: policy}), encoding="utf-8")
    for relpath, text in files.items():
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        (root / relpath).write_text(text, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "imports",
    [
        "import fresh\nimport scripts.fresh\n",
        "from fresh import Value\nfrom scripts.fresh import Value\n",
        "import fresh as f\nfrom scripts import fresh as g\n",
    ],
)
def test_dual_import_gate_names_both_sites(tmp_path: Path, imports: str) -> None:
    root = _project(
        tmp_path, {"scripts/fresh.py": "class Value: pass\n", "caller.py": imports}
    )
    assert dual_import_findings(root) == [
        "scripts/fresh.py: call module_identity.register_module(__name__, __file__); "
        "fresh imported at caller.py:1; scripts.fresh imported at caller.py:2"
    ]


@pytest.mark.parametrize(
    ("statement", "dynamic"),
    [
        ("import fresh", 'import importlib\nimportlib.import_module("scripts.fresh")'),
        (
            "import fresh",
            'from importlib import import_module\nimport_module("scripts.fresh")',
        ),
        ("import fresh", '__import__("scripts.fresh")'),
        ("import scripts.fresh", 'import importlib\nimportlib.import_module("fresh")'),
        (
            "import fresh",
            'import importlib\nimportlib.import_module(".fresh", "scripts")',
        ),
        (
            "import fresh",
            'from importlib import import_module as load\nload("scripts.fresh")',
        ),
        (
            "import fresh",
            'import importlib as loader\nloader.import_module("scripts.fresh")',
        ),
    ],
)
def test_dual_import_gate_counts_literal_calls(
    tmp_path: Path, statement: str, dynamic: str
) -> None:
    root = _project(
        tmp_path,
        {
            "scripts/fresh.py": "class Value: pass\n",
            "scripts/caller.py": statement + "\n",
            "tests/integration/caller.py": dynamic + "\n",
        },
    )
    findings = dual_import_findings(root)
    assert len(findings) == 1, findings
    assert "scripts/fresh.py: call module_identity.register_module" in findings[0]
    assert "scripts/caller.py:1" in findings[0]
    assert "tests/integration/caller.py:" in findings[0]


def test_dual_import_gate_accepts_registered_literal_calls(tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        {
            "scripts/fresh.py": "from module_identity import register_module\n"
            "register_module(__name__, __file__)\n",
            "scripts/caller.py": "import fresh\n",
            "evals/caller.py": 'import importlib\nimportlib.import_module("scripts.fresh")\n',
        },
    )
    assert dual_import_findings(root) == []


@pytest.mark.parametrize("caller", ["scripts", "tests/integration", "evals"])
def test_dual_import_gate_leaves_nonliteral_calls_unjudged(
    tmp_path: Path, caller: str
) -> None:
    root = _project(
        tmp_path,
        {
            "scripts/fresh.py": "class Value: pass\n",
            caller + "/caller.py": "import fresh\nimport importlib\n"
            'name = "scripts.fresh"\nimportlib.import_module(name)\n',
        },
    )
    assert dual_import_findings(root) == []


@pytest.mark.parametrize(
    "registration",
    [
        "from module_identity import register_module\nregister_module(__name__, __file__)\n",
        "from .module_identity import register_module as share\nshare(__name__, __file__)\n",
        "import scripts.module_identity as identity\nidentity.register_module(__name__, __file__)\n",
    ],
)
def test_dual_import_gate_accepts_the_shared_helper(
    tmp_path: Path, registration: str
) -> None:
    root = _project(
        tmp_path,
        {
            "scripts/fresh.py": registration,
            "caller.py": "import fresh\nfrom scripts import fresh\n",
        },
    )
    assert dual_import_findings(root) == []


@pytest.mark.parametrize(
    "registration",
    [
        "from module_identity import register_module\n",
        "from unrelated import register_module\nregister_module(__name__, __file__)\n",
        "from module_identity import register_module\ndef later():\n    register_module(__name__, __file__)\n",
    ],
)
def test_dual_import_gate_requires_a_module_scope_call(
    tmp_path: Path, registration: str
) -> None:
    root = _project(
        tmp_path,
        {
            "scripts/fresh.py": registration,
            "caller.py": "import fresh\nimport scripts.fresh\n",
        },
    )
    findings = dual_import_findings(root)
    assert len(findings) == 1 and findings[0].startswith("scripts/fresh.py:"), findings


_UPWARD = {
    "src/shared/__init__.py": "",
    "src/shared/x.py": "import os\n\nfrom agents.y import thing\n",
    "agents/y.py": "thing = 1\n",
}


def test_an_upward_import_is_a_finding_naming_both_layers(tmp_path):
    root = _project(tmp_path, _UPWARD)
    findings = layer_findings(root)["findings"]
    assert findings == [
        "src/shared/x.py:3: layer 1 (src/shared) imports agents/y.py in the higher "
        "layer 2 (agents); " + _FIX
    ], findings


def test_a_downward_or_level_import_is_no_finding(tmp_path):
    files = {
        "src/shared/__init__.py": "",
        "src/shared/x.py": "VALUE = 1\n",
        "src/shared/z.py": "from shared import x\n",
        "agents/y.py": "from shared.x import VALUE\nimport agents.w\n",
        "agents/w.py": "",
    }
    result = layer_findings(_project(tmp_path, files))
    assert result["findings"] == [] and result["edges"] == 3, result


def test_a_prefix_matches_whole_segments_only(tmp_path):
    files = dict(_UPWARD, **{"agents_extra/z.py": ""})
    findings = layer_findings(_project(tmp_path, files))["findings"]
    assert any(f.startswith("agents_extra/z.py:1: no prefix") for f in findings), (
        findings
    )


def test_an_unplaced_file_is_a_finding(tmp_path):
    files = {"src/shared/x.py": "", "tools/t.py": "import shared.x\n"}
    findings = layer_findings(_project(tmp_path, files))["findings"]
    assert findings == [
        "tools/t.py:1: no prefix in config/project.json import_layers.order holds "
        "it; add its directory to the layer it belongs in"
    ], findings


def test_a_stale_prefix_is_a_finding_and_an_absent_one_is_skipped(tmp_path):
    files = {"src/shared/x.py": "", "agents/README.md": "no code here\n"}
    order = [["src/shared"], ["agents", "demo"]]
    findings = layer_findings(_project(tmp_path, files, order=order))["findings"]
    assert findings == [
        "config/project.json: import_layers.order names `agents`, which places no "
        "Python file; delete the entry or move it to the files it means"
    ], findings


def test_a_relative_import_is_resolved_against_its_package(tmp_path):
    files = {
        "src/shared/__init__.py": "",
        "src/shared/x.py": "from ..agents import y\n",
        "src/agents/y.py": "",
    }
    order = [["src/shared"], ["src/agents"]]
    findings = layer_findings(_project(tmp_path, files, order=order))["findings"]
    assert len(findings) == 1 and findings[0].startswith("src/shared/x.py:1:"), findings


def test_a_stdlib_name_never_resolves_to_a_project_file(tmp_path):
    """A project `secrets.py` in a higher layer does not make `import secrets`
    an edge to it."""
    files = {"src/shared/x.py": "import secrets\n", "secrets.py": ""}
    order = [["src/shared"], ["secrets.py"]]
    result = layer_findings(_project(tmp_path, files, order=order))
    assert result["findings"] == [] and result["edges"] == 0, result


@pytest.mark.parametrize(
    "block",
    [
        None,
        {"search_roots": [""], "order": []},
        {"search_roots": [""], "order": [[]]},
        {"search_roots": ["src"], "order": [["src"]]},
        {"search_roots": [""], "order": [["src", "src"]]},
        {"search_roots": [""], "order": [["src/"]]},
    ],
)
def test_a_malformed_block_is_an_error_not_a_pass(tmp_path, block):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "x.py").write_text("", encoding="utf-8")
    manifest = {} if block is None else {_BLOCK: block}
    (root / _CONFIG).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(st.SourceTreeError, match="import_layers"):
        layer_findings(root)


def test_a_tree_with_no_python_file_is_an_error_not_a_pass(tmp_path):
    root = _project(tmp_path, {})
    with pytest.raises(st.SourceTreeError, match="zero items"):
        layer_findings(root)
