"""
title: Integration — a copied script carries every project module it imports
kind: tests
layer: n/a
summary: tests/script_copy.py copy_with_imports copies the files a fixture lists into a scratch project together with every project module a listed Python file imports, followed to its end, so a script that starts importing a sibling never leaves a fixture's copy unable to start. Over synthetic trees: an import of a sibling, made at module level or inside a function, is carried and an unimported sibling is not; a module under scripts/jobs/ carries what it imports from scripts/; a tests/ helper carries its tests/ sibling; `from scripts import x` and `from scripts.x import y`, resolved against the repo root, are carried; an import of the project that no file holds raises naming the importer and the module, never a silent skip; an import cycle is read once per file; a standard-library or installed name is left out; a listed file that does not exist raises naming it before anything is written; and a second copy into the same destination changes no byte. Over keel's own tree, copying scripts/check_structure.py carries scripts/corpus_level.py, the module whose absence from every hand-kept list once stopped 96 fixtures with ModuleNotFoundError, and copying scripts/run_make_target.py carries scripts/resource_limits.py, which it imports as `from scripts import resource_limits`, and the copy starts. An AST scan discovers scratch-copy consumers, requires entry rosters to route through the helper and checks the actual copied files against the source import graph; direct copies have explicit reasons in _COPY_EXEMPTIONS.
"""

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from test_scratch_root_gate import child_timeout

import script_copy
import source_tree

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration


def _tree(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _bytes(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


_SIBLINGS = {
    "scripts/a.py": "import json\nimport b\n\nprint(b.VALUE)\n",
    "scripts/b.py": "VALUE = 1\n\n\ndef late():\n    import c\n\n    return c\n",
    "scripts/c.py": "import pytest\n",
    "scripts/unused.py": "VALUE = 2\n",
    "config/project.json": "{}\n",
}


def test_a_sibling_import_is_carried_and_an_unimported_one_is_not(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    _tree(src, _SIBLINGS)
    written = script_copy.copy_with_imports(
        dest, src, ["scripts/a.py", "config/project.json"]
    )
    assert written == [
        "config/project.json",
        "scripts/a.py",
        "scripts/b.py",
        "scripts/c.py",
    ]
    assert sorted(_bytes(dest)) == written
    assert not (dest / "scripts" / "unused.py").exists()


def test_the_copy_starts_where_a_copy_of_the_list_alone_does_not(tmp_path):
    src, dest, bare = tmp_path / "src", tmp_path / "dest", tmp_path / "bare"
    _tree(src, _SIBLINGS)
    script_copy.copy_with_imports(dest, src, ["scripts/a.py"])
    (bare / "scripts").mkdir(parents=True)
    (bare / "scripts" / "a.py").write_bytes((src / "scripts" / "a.py").read_bytes())

    def run(root):
        return subprocess.run(
            [sys.executable, str(root / "scripts" / "a.py")],
            capture_output=True,
            text=True,
            check=False,
            env=build_child_env(),
            timeout=child_timeout(),
        )

    assert run(dest).returncode == 0
    red = run(bare)
    assert red.returncode != 0 and "No module named 'b'" in red.stderr, red.stderr


def test_a_job_carries_what_it_imports_from_scripts(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    _tree(
        src,
        {
            "scripts/jobs/step.py": "import config_loader\n",
            "scripts/config_loader.py": "import exit_codes\n",
            "scripts/exit_codes.py": "",
        },
    )
    assert script_copy.copy_with_imports(dest, src, ["scripts/jobs/step.py"]) == [
        "scripts/config_loader.py",
        "scripts/exit_codes.py",
        "scripts/jobs/step.py",
    ]


def test_a_tests_helper_carries_its_tests_sibling(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    _tree(
        src,
        {
            "tests/conftest.py": "import guard\n",
            "tests/guard.py": "import config_loader\n",
            "scripts/config_loader.py": "",
        },
    )
    assert script_copy.copy_with_imports(dest, src, ["tests/conftest.py"]) == [
        "scripts/config_loader.py",
        "tests/conftest.py",
        "tests/guard.py",
    ]


def test_a_scripts_package_import_is_carried_from_the_repo_root(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    _tree(
        src,
        {
            "scripts/a.py": "from scripts import b\nfrom scripts.c import VALUE\n",
            "scripts/b.py": "",
            "scripts/c.py": "VALUE = 1\n",
        },
    )
    assert script_copy.copy_with_imports(dest, src, ["scripts/a.py"]) == [
        "scripts/a.py",
        "scripts/b.py",
        "scripts/c.py",
    ]


def test_a_project_import_no_file_holds_raises_naming_importer_and_module(
    tmp_path,
):
    src, dest = tmp_path / "src", tmp_path / "dest"
    _tree(src, {"scripts/a.py": "import json\nfrom scripts import gone\n"})
    with pytest.raises(AssertionError, match=r"scripts/a\.py.*scripts\.gone"):
        script_copy.copy_with_imports(dest, src, ["scripts/a.py"])
    assert not dest.exists()


def test_an_import_cycle_reads_each_file_once(tmp_path, monkeypatch):
    src = tmp_path / "src"
    _tree(
        src,
        {
            "scripts/a.py": "import b\n",
            "scripts/b.py": "import a\n",
        },
    )
    read = []
    edges = source_tree.import_edges

    def counted(root, files, search_roots):
        read.extend(files)
        # A walk with no guard never ends; stop it as a failure, not a hang.
        assert len(read) <= 4, read
        return edges(root, files, search_roots)

    monkeypatch.setattr(source_tree, "import_edges", counted)
    assert script_copy.imports_closure(src, ["scripts/a.py"]) == [
        "scripts/a.py",
        "scripts/b.py",
    ]
    assert sorted(read) == ["scripts/a.py", "scripts/b.py"]


def test_a_listed_file_that_does_not_exist_raises_before_writing(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    _tree(src, _SIBLINGS)
    with pytest.raises(AssertionError, match="scripts/gone.py"):
        script_copy.copy_with_imports(dest, src, ["scripts/a.py", "scripts/gone.py"])
    assert not dest.exists()


def test_a_second_copy_changes_no_byte(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    _tree(src, _SIBLINGS)
    first = script_copy.copy_with_imports(dest, src, ["scripts/a.py"])
    before = _bytes(dest)
    assert script_copy.copy_with_imports(dest, src, ["scripts/a.py"]) == first
    assert _bytes(dest) == before


def test_keels_check_structure_carries_corpus_level(tmp_path):
    written = script_copy.copy_with_imports(
        tmp_path, _ROOT, ["scripts/check_structure.py"]
    )
    assert "scripts/corpus_level.py" in written, written
    started = subprocess.run(
        [sys.executable, "-c", "import check_structure"],
        cwd=str(tmp_path / "scripts"),
        capture_output=True,
        text=True,
        check=False,
        env=build_child_env(),
        timeout=child_timeout(),
    )
    assert started.returncode == 0, started.stderr


def test_keels_run_make_target_carries_resource_limits_and_starts(tmp_path):
    written = script_copy.copy_with_imports(
        tmp_path, _ROOT, ["scripts/run_make_target.py"]
    )
    assert "scripts/resource_limits.py" in written, written
    started = subprocess.run(
        [
            sys.executable,
            "-B",
            str(tmp_path / "scripts" / "run_make_target.py"),
            "--help",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=build_child_env(),
        timeout=child_timeout(),
    )
    assert started.returncode == 0, started.stderr


# These fixtures need a complete tree or intentionally inspect copied source as
# data. Keys identify the source expression, not a line number that edits move.
_COPY_EXEMPTIONS = {
    (
        "integration/test_preflight.py",
        "_ROOT / 'scripts'",
    ): "Preflight exercises arbitrary make recipes against the entire scripts tree.",
    (
        "integration/test_toolchain_gate.py",
        "str(_ROOT / 'scripts')",
    ): "Frontend installation exercises make recipes with the entire scripts tree.",
    (
        "integration/test_gate_scope.py",
        "str(_ROOT / 'scripts')",
    ): "Interpreter-floor checks exercise every needy recipe, including optional jobs.",
    (
        "integration/test_install_sources_gate.py",
        "str(_ROOT / 'scripts')",
    ): "Installer make/CI recipes require a complete scripts tree, not selected entries.",
    (
        "unit/scripts/test_audit_project.py",
        "str(_ROOT / 'scripts')",
    ): "Conflict refusal is measured after fault injection into a complete scripts tree.",
    (
        "unit/scripts/test_conflict_guard.py",
        "str(_ROOT / 'scripts')",
    ): "All migration jobs are fault-injected in a complete scripts tree.",
    (
        "unit/scripts/test_manifest_refusals.py",
        "_ROOT / 'scripts'",
    ): "All job entry guards are exercised against a malformed manifest.",
    (
        "unit/scripts/test_restamp_docs.py",
        "str(_ROOT / 'scripts')",
    ): "Conflicts are planted in read and unread modules of a complete scripts tree.",
    (
        "unit/scripts/test_restamp_docs.py",
        "str(_ROOT / rel)",
    ): "Declared unread inputs are copied as conflict-injection data, not entry scripts.",
    (
        "integration/test_check_structure_manifest_refusal.py",
        "_ROOT",
    ): "Structure checks require the real documents, twins and manifests of a whole repo.",
    (
        "integration/test_conflict_entry_points.py",
        "src",
    ): "Every candidate file is preserved to measure refusals across all entry points.",
    (
        "integration/test_exit_gate.py",
        "str(_ROOT / et.HELPER)",
    ): "The exit helper has no project imports and is isolated in minimal protocol fixtures.",
    (
        "integration/test_requirement_traceability.py",
        "str(path)",
    ): "Marked test sources are gate input data and are never executed in the copy.",
    (
        "integration/test_copier_generation.py",
        "clean_template",
    ): "The complete clean template is copied to test render exclusions.",
    (
        "integration/test_copier_generation.py",
        "str(meta)",
    ): "Old meta-tests are restored verbatim to prove they skip in generated projects.",
    (
        "integration/test_isolation_gate.py",
        "str(_CASES / ('case_%s.py' % case))",
    ): "Fault-injection test cases are copied verbatim; the harness imports use the helper.",
    (
        "unit/api/test_rest_serve.py",
        "_SERVE.parent / name",
    ): "API transport files form a minimal symlinked entry fixture with malformed config.",
    (
        "integration/test_copier_job_conflict_refusal.py",
        "str(project)",
    ): "The complete generated project is preserved for conflict and read tracing.",
}
_COPY_FUNCTIONS = {"copy", "copy2", "copyfile", "copytree", "copy_with_imports"}


def _source_tokens(expr, definitions, imports, seen=frozenset()):
    """Conservative path provenance, including rosters and loop variables.

    Follow assignments and imported constants without importing test modules or
    executing calls. Unknown expressions contribute their literal path parts;
    this is a source audit, not a general Python data-flow interpreter.
    """
    if isinstance(expr, ast.Name):
        name = expr.id
        if name == "_ROOT":
            return {"_ROOT"}
        if name in seen:
            return set()
        if name in definitions:
            return set().union(
                *(
                    _source_tokens(value, definitions, imports, seen | {name})
                    for value in definitions[name]
                )
            )
        if name in imports:
            path, attribute = imports[name]
            if attribute and path + ":" + attribute not in seen:
                tree = source_tree.parse(_ROOT, path)
                return _source_tokens(
                    ast.Name(id=attribute),
                    _definitions(tree),
                    source_tree.bindings(_ROOT, path, tree, _search(path)),
                    seen | {path + ":" + attribute},
                )
        return set()
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        imported = imports.get(expr.value.id)
        if imported and imported[1] is None:
            tree = source_tree.parse(_ROOT, imported[0])
            return _source_tokens(ast.Name(id=expr.attr), _definitions(tree), {}, seen)
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return {expr.value}
    return set().union(
        *(
            _source_tokens(child, definitions, imports, seen)
            for child in ast.iter_child_nodes(expr)
        )
    )


def _definitions(scope):
    out = {}
    for node in source_tree.scope_nodes(scope):
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        elif isinstance(node, (ast.For, ast.comprehension)):
            targets, value = [node.target], node.iter
        if value is not None:
            for target in targets:
                if isinstance(target, ast.Name):
                    out.setdefault(target.id, []).append(value)
    return out


def _search(path):
    return [
        str(Path(path).parent) + "/",
        "tests/integration/",
        "tests/",
        "scripts/",
        "",
    ]


def _copy_sites(root=_ROOT):
    """Discover calls, including direct copies after a consumer bypasses the helper."""
    sites = []
    for path in sorted((root / "tests").rglob("test_*.py")):
        if path == Path(__file__):
            # This module tests the copier itself on synthetic and real trees;
            # its real-tree calls have dedicated behavioral assertions above.
            continue
        rel = path.relative_to(root).as_posix()
        tree = source_tree.parse(root, rel)
        imports = source_tree.bindings(root, rel, tree, _search(rel))
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"shutil", "script_copy"}:
                        aliases[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module in {
                "shutil",
                "script_copy",
            }:
                for alias in node.names:
                    aliases[alias.asname or alias.name] = node.module + "." + alias.name

        def scan(scope, inherited, aliases, imports, path, rel):
            definitions = dict(inherited, **_definitions(scope))
            for node in source_tree.scope_nodes(scope):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    scan(node, definitions, aliases, imports, path, rel)
                if not isinstance(node, ast.Call):
                    continue
                parts = ast.unparse(node.func).split(".")
                callee = ".".join([aliases.get(parts[0], parts[0]), *parts[1:]])
                owner, _, method = callee.rpartition(".")
                if (
                    owner not in {"shutil", "script_copy"}
                    or method not in _COPY_FUNCTIONS
                ):
                    continue
                params = (
                    ("dest", "root", "relpaths")
                    if method == "copy_with_imports"
                    else ("src", "dst")
                )
                args = dict(zip(params, node.args, strict=False))
                args.update((k.arg, k.value) for k in node.keywords)
                source = args.get("root" if method == "copy_with_imports" else "src")
                if source is None:
                    continue
                tokens = _source_tokens(source, definitions, imports)
                key = (path.relative_to(root / "tests").as_posix(), ast.unparse(source))
                code = any(
                    token.split("/")[0] in {"scripts", "src"} or token.endswith(".py")
                    for token in tokens
                )
                if key in _COPY_EXEMPTIONS or (
                    "_ROOT" in tokens
                    and (method == "copy_with_imports" or code or tokens == {"_ROOT"})
                ):
                    sites.append((rel, node.lineno, callee, args.get("relpaths"), key))

        scan(tree, {}, aliases, imports, path, rel)
    return sites


def _copy_cases():
    sites = _copy_sites()
    template_only = not (_ROOT / "copier.yml").is_file()
    reason = "template-only: copier.yml prunes tests/integration/test_copier_*.py"
    cases = [
        pytest.param(
            site,
            id="%s:%d" % site[:2],
            marks=pytest.mark.skipif(
                template_only and Path(site[0]).stem == "test_copier_update",
                reason=reason,
            ),
        )
        for site in sites
    ]
    if template_only and not any(
        Path(site[0]).stem == "test_copier_update" for site in sites
    ):
        cases.append(
            pytest.param(
                None,
                id="test_copier_update",
                marks=pytest.mark.skip(reason=reason),
            )
        )
    return cases


@pytest.mark.parametrize("site", _copy_cases())
def test_scratch_script_copies_route_through_the_helper_and_are_import_complete(
    site, tmp_path
):
    rel, line, callee, roster, key = site
    where = "%s:%d" % (rel, line)
    if key in _COPY_EXEMPTIONS:
        assert _COPY_EXEMPTIONS[key].strip(), where
        return
    assert callee == "script_copy.copy_with_imports", (
        "%s copies keel scripts via %s; use copy_with_imports" % (where, callee)
    )
    assert roster is not None, "%s has no roster" % where
    # Only a roster expression is evaluated, never a fixture or its subprocesses.
    allowed = (
        ast.Expression,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.Store,
        ast.Tuple,
        ast.List,
        ast.ListComp,
        ast.comprehension,
        ast.BinOp,
        ast.Add,
    )
    assert all(isinstance(node, allowed) for node in ast.walk(roster)), where
    module = importlib.import_module(Path(rel).stem)
    entries = eval(compile(ast.Expression(roster), rel, "eval"), vars(module))
    script_copy.copy_with_imports(tmp_path, _ROOT, entries)
    assert all((tmp_path / entry).is_file() for entry in entries), where
    copied = sorted(_bytes(tmp_path))
    _assert_complete(_ROOT, copied)
    # Resolve in the actual destination too. Reading only there would mistake a
    # completely absent project module for an installed, external dependency.
    for importer in (rel for rel in copied if rel.endswith(".py")):
        search = [str(Path(importer).parent) + "/", "scripts/", ""]
        expected = source_tree.import_edges(_ROOT, [importer], search)
        assert source_tree.import_edges(tmp_path, [importer], search) == expected, where
        assert not source_tree.unresolved_imports(tmp_path, [importer], search), where


def test_copy_discovery_is_nonempty_and_exemptions_still_name_copy_calls():
    sites = _copy_sites()
    assert sites
    present = {key for key in _COPY_EXEMPTIONS if (_ROOT / "tests" / key[0]).is_file()}
    assert present <= {site[4] for site in sites}


def test_discovery_finds_a_new_consumer_copying_a_roster_with_shutil(tmp_path):
    _tree(
        tmp_path,
        {
            "tests/test_new_consumer.py": (
                "from pathlib import Path\nimport shutil as copying\n"
                "_ROOT = Path(__file__).parents[1]\n"
                "_ENTRIES = ('scripts/entry.py', 'config/project.json')\n"
                "def fixture(dest):\n"
                "    for rel in _ENTRIES:\n"
                "        copying.copy(_ROOT / rel, dest / rel)\n"
            ),
        },
    )
    sites = _copy_sites(tmp_path)
    assert [(site[0], site[1], site[2]) for site in sites] == [
        ("tests/test_new_consumer.py", 7, "shutil.copy")
    ]


def _assert_complete(root, copied):
    missing = {
        imported
        for _importer, _line, imported in source_tree.import_edges(
            root, [rel for rel in copied if rel.endswith(".py")], ["scripts/", ""]
        )
        if imported not in copied
    }
    assert not missing, "copy list misses imports: %s" % sorted(missing)


def test_gate_copy_carries_transitive_shell_gate_and_detects_an_incomplete_list(
    tmp_path,
):
    entry = "scripts/gate_evidence.py"
    transitive = "scripts/shell_gate.py"
    direct = source_tree.import_edges(_ROOT, [entry], ["scripts/", ""])
    assert transitive not in {imported for _src, _line, imported in direct}
    copied = script_copy.copy_with_imports(tmp_path, _ROOT, [entry])
    assert transitive in copied
    _assert_complete(_ROOT, copied)
    with pytest.raises(AssertionError, match=r"copy list misses imports:.*shell_gate"):
        _assert_complete(_ROOT, [rel for rel in copied if rel != transitive])
    assert sorted(_bytes(tmp_path)) == copied
