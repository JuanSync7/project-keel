"""
title: Integration — a copied script carries every project module it imports
kind: tests
layer: n/a
summary: tests/script_copy.py copy_with_imports copies the files a fixture lists into a scratch project together with every project module a listed Python file imports, followed to its end, so a script that starts importing a sibling never leaves a fixture's copy unable to start. Over synthetic trees: an import of a sibling, made at module level or inside a function, is carried and an unimported sibling is not; a module under scripts/jobs/ carries what it imports from scripts/; a tests/ helper carries its tests/ sibling; `from scripts import x` and `from scripts.x import y`, resolved against the repo root, are carried; an import of the project that no file holds raises naming the importer and the module, never a silent skip; an import cycle is read once per file; a standard-library or installed name is left out; a listed file that does not exist raises naming it before anything is written; and a second copy into the same destination changes no byte. Over keel's own tree, copying scripts/check_structure.py carries scripts/corpus_level.py, the module whose absence from every hand-kept list once stopped 96 fixtures with ModuleNotFoundError, and copying scripts/run_make_target.py carries scripts/resource_limits.py, which it imports as `from scripts import resource_limits`, and the copy starts. An AST scan follows test imports into helpers, resolves repository-root names and bound source paths, and recognizes shutil copies, os links and subprocess cp/rsync argv; entry rosters must route through the helper and their copied trees must resolve every project import. Direct copies have reasons in _COPY_EXEMPTIONS keyed by module, enclosing function and source expression; a stale or ambiguous site fails naming its key.
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
# data. Function and source anchors survive line movement; duplicate sites fail.
_COPY_EXEMPTIONS = {
    (
        "integration/test_preflight.py",
        "project",
        "_ROOT / 'scripts'",
    ): "Preflight exercises arbitrary make recipes against the entire scripts tree.",
    (
        "integration/test_toolchain_gate.py",
        "_fe_install_copy",
        "str(_ROOT / 'scripts')",
    ): "Frontend installation exercises make recipes with the entire scripts tree.",
    (
        "integration/test_gate_scope.py",
        "test_needy_targets_fail_with_the_floor_message_on_an_old_python3",
        "str(_ROOT / 'scripts')",
    ): "Interpreter-floor checks exercise every needy recipe, including optional jobs.",
    (
        "integration/test_install_sources_gate.py",
        "_copy",
        "str(_ROOT / 'scripts')",
    ): "Installer make/CI recipes require a complete scripts tree, not selected entries.",
    (
        "integration/test_install_sources_gate.py",
        "_run_step",
        "str(_ROOT / 'scripts')",
    ): "Installer make/CI recipes require a complete scripts tree, not selected entries.",
    (
        "unit/scripts/test_audit_project.py",
        "test_the_restamp_rerun_the_audit_names_is_the_one_the_restamp_prints",
        "str(_ROOT / 'scripts')",
    ): "Conflict refusal is measured after fault injection into a complete scripts tree.",
    (
        "unit/scripts/test_conflict_guard.py",
        "test_every_after_migration_job_refuses_a_conflicted_import",
        "str(_ROOT / 'scripts')",
    ): "All migration jobs are fault-injected in a complete scripts tree.",
    (
        "unit/scripts/test_manifest_refusals.py",
        "test_job_entry_guard_classifies_manifest",
        "_ROOT / 'scripts'",
    ): "All job entry guards are exercised against a malformed manifest.",
    (
        "unit/scripts/test_restamp_docs.py",
        "test_conflicted_import_exits_2_cleanly",
        "str(_ROOT / 'scripts')",
    ): "Conflicts are planted in read and unread modules of a complete scripts tree.",
    (
        "unit/scripts/test_restamp_docs.py",
        "test_a_conflict_in_a_file_the_restamp_never_reads_does_not_stop_it",
        "str(_ROOT / 'scripts')",
    ): "Conflicts are planted in read and unread modules of a complete scripts tree.",
    (
        "unit/scripts/test_restamp_docs.py",
        "test_conflicted_manifest_exits_2_cleanly",
        "str(_ROOT / 'scripts')",
    ): "Conflicts are planted in read and unread modules of a complete scripts tree.",
    (
        "unit/scripts/test_restamp_docs.py",
        "test_a_conflict_in_a_file_the_restamp_never_reads_does_not_stop_it",
        "str(_ROOT / rel)",
    ): "Declared unread inputs are copied as conflict-injection data, not entry scripts.",
    (
        "integration/test_check_structure_manifest_refusal.py",
        "populated_tree",
        "_ROOT",
    ): "Structure checks require the real documents, twins and manifests of a whole repo.",
    (
        "integration/test_conflict_entry_points.py",
        "_assert_refusal",
        "src",
    ): "Every candidate file is preserved to measure refusals across all entry points.",
    (
        "integration/test_exit_gate.py",
        "_tree",
        "str(_ROOT / et.HELPER)",
    ): "The exit helper has no project imports and is isolated in minimal protocol fixtures.",
    (
        "integration/test_exit_gate.py",
        "_sh_tree",
        "str(_ROOT / et.HELPER)",
    ): "The exit helper has no project imports and is isolated in minimal protocol fixtures.",
    (
        "integration/test_requirement_traceability.py",
        "build_scratch",
        "str(path)",
    ): "Marked test sources are gate input data and are never executed in the copy.",
    (
        "integration/test_copier_generation.py",
        "test_cabinet_exclusion_omits_planted_descendants",
        "clean_template",
    ): "The complete clean template is copied to test render exclusions.",
    (
        "integration/test_copier_generation.py",
        "test_meta_tests_neutralise_themselves_in_a_project_that_still_has_them",
        "str(meta)",
    ): "Old meta-tests are restored verbatim to prove they skip in generated projects.",
    (
        "integration/test_isolation_gate.py",
        "_project",
        "str(_CASES / ('case_%s.py' % case))",
    ): "Fault-injection test cases are copied verbatim; the harness imports use the helper.",
    (
        "unit/api/test_rest_serve.py",
        "_run_symlinked_entry",
        "_SERVE.parent / name",
    ): "API transport files form a minimal symlinked entry fixture with malformed config.",
    (
        "integration/test_copier_job_conflict_refusal.py",
        "test_the_completeness_check_goes_red_when_a_declaration_is_removed",
        "str(project)",
    ): "The complete generated project is preserved for conflict and read tracing.",
    (
        "integration/test_copier_job_conflict_refusal.py",
        "test_every_file_a_job_opens_is_imported_declared_or_worklist",
        "str(project)",
    ): "The complete generated project is preserved for conflict and read tracing.",
    (
        "integration/test_e2e_coverage.py",
        "_shadow_root",
        "str(real)",
    ): "Endpoint discovery inspects a complete transport tree with a planted routing fault.",
    (
        "integration/test_evals_gate.py",
        "build_scratch",
        "str(_ROOT / tree)",
    ): "Replay evals require complete packages with their runtime datasets and adapters.",
}
_COPY_FUNCTIONS = {"copy", "copy2", "copyfile", "copytree", "copy_with_imports"}


def _path_value(expr, definitions, root, rel, seen=frozenset()):
    """Resolve literal path construction without evaluating project code."""
    if isinstance(expr, ast.Name):
        if expr.id == "__file__":
            return root / rel
        if expr.id in seen:
            return None
        values = {
            _path_value(value, definitions, root, rel, seen | {expr.id})
            for value in definitions.get(expr.id, [])
        } - {None}
        return values.pop() if len(values) == 1 else None
    if isinstance(expr, ast.Constant) and isinstance(expr.value, (str, int)):
        return expr.value
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        left = _path_value(expr.left, definitions, root, rel, seen)
        right = _path_value(expr.right, definitions, root, rel, seen)
        if isinstance(left, (Path, str)) and isinstance(right, str):
            return Path(left) / right
    if isinstance(expr, ast.Attribute) and expr.attr == "parent":
        value = _path_value(expr.value, definitions, root, rel, seen)
        if isinstance(value, (Path, str)):
            return Path(value).parent
    if (
        isinstance(expr, ast.Subscript)
        and isinstance(expr.value, ast.Attribute)
        and expr.value.attr == "parents"
    ):
        value = _path_value(expr.value.value, definitions, root, rel, seen)
        index = _path_value(expr.slice, definitions, root, rel, seen)
        if isinstance(value, (Path, str)) and isinstance(index, int):
            parents = Path(value).parents
            if -len(parents) <= index < len(parents):
                return parents[index]
    if isinstance(expr, ast.Call):
        callee = ast.unparse(expr.func)
        args = [_path_value(a, definitions, root, rel, seen) for a in expr.args]
        if args and isinstance(args[0], (str, Path)):
            if callee in {"Path", "pathlib.Path", "str"}:
                return Path(args[0])
            if callee in {"os.path.dirname", "dirname"}:
                return Path(args[0]).parent
            if callee in {"os.path.abspath", "os.path.realpath", "abspath", "realpath"}:
                return Path(args[0]).resolve()
            if callee in {"os.path.join", "join"} and all(
                isinstance(a, (str, Path)) for a in args
            ):
                return Path(*args)
        if (
            isinstance(expr.func, ast.Attribute)
            and expr.func.attr in {"resolve", "absolute"}
            and not args
        ):
            value = _path_value(expr.func.value, definitions, root, rel, seen)
            if isinstance(value, (str, Path)):
                return Path(value).resolve()
    return None


def _source_tokens(expr, definitions, imports, root, rel, seen=frozenset()):
    """Conservative path provenance, including rosters and loop variables.

    Follow assignments and imported constants without importing test modules or
    executing calls. Unknown expressions contribute their literal path parts;
    this is a source audit, not a general Python data-flow interpreter.
    """
    value = _path_value(expr, definitions, root, rel)
    if isinstance(value, (str, Path)) and Path(value).is_relative_to(root):
        relative = Path(value).relative_to(root).as_posix()
        return {"<repo>"} if relative == "." else {"<repo>", relative}
    if isinstance(expr, ast.Name):
        name = expr.id
        if name in seen:
            return set()
        if name in definitions:
            return set().union(
                *(
                    _source_tokens(
                        value, definitions, imports, root, rel, seen | {name}
                    )
                    for value in definitions[name]
                )
            )
        if name in imports:
            path, attribute = imports[name]
            if attribute and path + ":" + attribute not in seen:
                tree = source_tree.parse(root, path)
                return _source_tokens(
                    ast.Name(id=attribute),
                    _definitions(tree),
                    source_tree.bindings(root, path, tree, _search(path)),
                    root,
                    path,
                    seen | {path + ":" + attribute},
                )
        return set()
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        imported = imports.get(expr.value.id)
        if imported and imported[1] is None:
            path = imported[0]
            if path + ":" + expr.attr in seen:
                return set()
            tree = source_tree.parse(root, path)
            return _source_tokens(
                ast.Name(id=expr.attr),
                _definitions(tree),
                source_tree.bindings(root, path, tree, _search(path)),
                root,
                path,
                seen | {path + ":" + expr.attr},
            )
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return {expr.value}
    return set().union(
        *(
            _source_tokens(child, definitions, imports, root, rel, seen)
            for child in ast.iter_child_nodes(expr)
        )
    )


def _definitions(scope):
    out = {}

    def bind(target, value):
        if isinstance(target, ast.Name):
            out.setdefault(target.id, []).append(value)
        elif isinstance(target, (ast.Tuple, ast.List)) and isinstance(
            value, (ast.Tuple, ast.List)
        ):
            for item, part in zip(target.elts, value.elts, strict=False):
                bind(item, part)

    for node in source_tree.scope_nodes(scope):
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            targets, value = [node.target], node.value
        elif isinstance(node, (ast.For, ast.comprehension)):
            targets, value = [node.target], node.iter
        if value is not None:
            for target in targets:
                bind(target, value)
    return out


def _search(path):
    return [
        str(Path(path).parent) + "/",
        "tests/integration/",
        "tests/",
        "scripts/",
        "",
    ]


def _consumer_modules(root):
    """Test modules and their transitive helpers under tests/, including fixtures."""
    todo = {
        path.relative_to(root).as_posix()
        for pattern in ("test_*.py", "conftest.py")
        for path in (root / "tests").rglob(pattern)
    }
    seen = set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        for _importer, _line, imported in source_tree.import_edges(
            root, [rel], _search(rel)
        ):
            if imported.startswith("tests/") and imported not in seen:
                todo.add(imported)
    return sorted(seen)


def _bound_expressions(expr, definitions, seen=frozenset()):
    """Possible expressions behind a local argv or executable binding."""
    if isinstance(expr, ast.Name) and expr.id not in seen:
        return [
            resolved
            for value in definitions.get(expr.id, [])
            for resolved in _bound_expressions(value, definitions, seen | {expr.id})
        ]
    return [expr]


def _copy_arguments(callee, node, definitions):
    """Source expressions and the optional roster for supported copy operations."""
    owner, _, method = callee.rpartition(".")
    if (owner in {"shutil", "script_copy"} and method in _COPY_FUNCTIONS) or (
        owner == "os" and method in {"link", "symlink"}
    ):
        params = (
            ("dest", "root", "relpaths")
            if method == "copy_with_imports"
            else ("src", "dst")
        )
        args = dict(zip(params, node.args, strict=False))
        args.update((k.arg, k.value) for k in node.keywords)
        source = args.get("root" if method == "copy_with_imports" else "src")
        return [(source, args.get("relpaths"))] if source is not None else []
    if owner != "subprocess" or method not in {
        "run",
        "call",
        "check_call",
        "check_output",
        "Popen",
    }:
        return []
    argv = (
        node.args[0]
        if node.args
        else next((k.value for k in node.keywords if k.arg == "args"), None)
    )
    if argv is None:
        return []
    sources = []
    for value in _bound_expressions(argv, definitions):
        if not isinstance(value, (ast.List, ast.Tuple)) or not value.elts:
            continue
        commands = _bound_expressions(value.elts[0], definitions)
        if not any(
            isinstance(command, ast.Constant)
            and isinstance(command.value, str)
            and Path(command.value).name in {"cp", "rsync"}
            for command in commands
        ):
            continue
        # The final operand is the destination; flags contribute no provenance.
        sources.extend((source, None) for source in value.elts[1:-1])
    return sources


def _copy_sites(root=_ROOT):
    """Discover source copies throughout the test modules' helper import graph."""
    sites = []
    for rel in _consumer_modules(root):
        path = root / rel
        if path == Path(__file__):
            # This module tests the copier itself on synthetic and real trees;
            # its real-tree calls have dedicated behavioral assertions above.
            continue
        tree = source_tree.parse(root, rel)
        imports = source_tree.bindings(root, rel, tree, _search(rel))

        def scan(scope, inherited, inherited_aliases, inherited_imports, anchor, rel):
            definitions = dict(inherited, **_definitions(scope))
            aliases = dict(inherited_aliases)
            imports = dict(
                inherited_imports,
                **source_tree.bindings(root, rel, scope, _search(rel)),
            )
            for node in source_tree.scope_nodes(scope):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        aliases[alias.asname or alias.name] = alias.name
                elif isinstance(node, ast.ImportFrom) and node.module:
                    for alias in node.names:
                        aliases[alias.asname or alias.name] = (
                            node.module + "." + alias.name
                        )
            for node in source_tree.scope_nodes(scope):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    scan(
                        node,
                        definitions,
                        aliases,
                        imports,
                        ".".join(filter(None, (anchor, node.name))),
                        rel,
                    )
                if not isinstance(node, ast.Call):
                    continue
                parts = ast.unparse(node.func).split(".")
                callee = ".".join([aliases.get(parts[0], parts[0]), *parts[1:]])
                for source, roster in _copy_arguments(callee, node, definitions):
                    tokens = _source_tokens(source, definitions, imports, root, rel)
                    key = (
                        Path(rel).relative_to("tests").as_posix(),
                        anchor or "<module>",
                        ast.unparse(source),
                    )
                    code = any(
                        token.split("/")[0]
                        in {"scripts", "src", "tests", "api", "agents", "mcp", "evals"}
                        or token.endswith(".py")
                        for token in tokens
                    )
                    if key in _COPY_EXEMPTIONS or (
                        "<repo>" in tokens
                        and (
                            callee == "script_copy.copy_with_imports"
                            or code
                            or tokens == {"<repo>"}
                        )
                    ):
                        sites.append((rel, node.lineno, callee, roster, key))

        scan(tree, {}, {}, imports, "", rel)
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


def _assert_exemptions(sites, exemptions, root):
    """Every exemption in a shipped module names exactly one current copy site."""
    keys = [site[4] for site in sites]
    for key in exemptions:
        if not (root / "tests" / key[0]).is_file():
            # copier.yml excludes these template tools from generated projects.
            template_module = Path(key[0]).match("integration/test_copier_*.py") or (
                key[0] == "unit/scripts/test_audit_project.py"
            )
            if template_module and not (root / "copier.yml").is_file():
                continue
        count = keys.count(key)
        assert count == 1, "copy exemption %s names %d sites (expected 1)" % (
            key,
            count,
        )
        assert exemptions[key].strip(), "blank copy exemption: %s" % (key,)


def test_copy_discovery_is_nonempty_and_exemptions_still_name_copy_calls():
    sites = _copy_sites()
    assert sites
    _assert_exemptions(sites, _COPY_EXEMPTIONS, _ROOT)


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


@pytest.mark.parametrize(
    ("setup", "copy", "callee"),
    [
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "shutil.copy(REPOSITORY / 'scripts/a.py', dest)",
            "shutil.copy",
        ),
        (
            "REPOSITORY = Path(__file__).parent.parent\nsource = REPOSITORY / 'scripts/a.py'",
            "shutil.copy(source, dest)",
            "shutil.copy",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "alias, unused = REPOSITORY, dest\n    source = alias / 'scripts/a.py'\n    shutil.copy(source, dest)",
            "shutil.copy",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "os.link(REPOSITORY / 'scripts/a.py', dest)",
            "os.link",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "os.symlink(src=REPOSITORY / 'scripts/a.py', dst=dest)",
            "os.symlink",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "subprocess.run(['cp', '-p', str(REPOSITORY / 'scripts/a.py'), dest])",
            "subprocess.run",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "argv = ['/usr/bin/rsync', '-a', REPOSITORY / 'scripts/a.py', dest]\n    subprocess.check_call(args=argv)",
            "subprocess.check_call",
        ),
        (
            "REPOSITORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))",
            "from os import link as copying\n    copying(os.path.join(REPOSITORY, 'scripts', 'a.py'), dest)",
            "os.link",
        ),
    ],
)
def test_discovery_follows_root_names_bound_paths_and_copy_operations(
    tmp_path, setup, copy, callee
):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport os, shutil, subprocess\n"
                + setup
                + "\ndef fixture(dest):\n    "
                + copy
                + "\n"
            )
        },
    )
    sites = _copy_sites(tmp_path)
    assert len(sites) == 1
    assert sites[0][2] == callee
    assert sites[0][4][1] == "fixture"


def test_discovery_follows_transitive_helpers_and_imported_path_bindings(tmp_path):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": "from helpers import middle\n",
            "tests/helpers/__init__.py": "",
            "tests/helpers/middle.py": "from . import copying\n",
            "tests/helpers/paths.py": "from pathlib import Path\nBASE = Path(__file__).parents[2]\nSOURCE = BASE / 'scripts/a.py'\n",
            "tests/helpers/copying.py": "from .paths import SOURCE\nfrom shutil import copy2 as raw\ndef fixture(dest):\n    raw(SOURCE, dest)\n",
            "tests/unimported.py": "import shutil\nfrom pathlib import Path\nshutil.copy(Path(__file__).parents[1] / 'scripts/a.py', 'unused')\n",
        },
    )
    sites = _copy_sites(tmp_path)
    assert [(s[0], s[2], s[4][1:]) for s in sites] == [
        ("tests/helpers/copying.py", "shutil.copy2", ("fixture", "SOURCE"))
    ]


@pytest.mark.parametrize("copies", [0, 2])
def test_a_stale_or_ambiguous_exemption_fails_naming_its_site(tmp_path, copies):
    key = ("test_consumer.py", "fixture", "BASE / 'scripts/a.py'")
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport shutil\n"
                "BASE = Path(__file__).parents[1]\ndef fixture(dest):\n    pass\n"
                + "    shutil.copy(BASE / 'scripts/a.py', dest)\n"
                * copies
            )
        },
    )
    with pytest.raises(
        AssertionError,
        match=r"test_consumer.py.*fixture.*scripts/a.py.*names %d sites" % copies,
    ):
        _assert_exemptions(_copy_sites(tmp_path), {key: "source data"}, tmp_path)


def test_an_exemption_does_not_cover_the_same_expression_in_another_function(tmp_path):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport shutil\nBASE = Path(__file__).parents[1]\n"
                "def first(dest):\n    shutil.copy(BASE / 'scripts/a.py', dest)\n"
                "def second(dest):\n    shutil.copy(BASE / 'scripts/a.py', dest)\n"
            )
        },
    )
    sites = _copy_sites(tmp_path)
    exemptions = {sites[0][4]: "source data"}
    _assert_exemptions(sites, exemptions, tmp_path)
    assert sites[1][4] not in exemptions


def test_a_deleted_module_leaves_a_stale_exemption(tmp_path):
    key = ("test_removed.py", "fixture", "source")
    with pytest.raises(AssertionError, match="test_removed.py.*fixture.*source"):
        _assert_exemptions([], {key: "source data"}, tmp_path)


def test_a_synthetic_root_named_ROOT_is_not_the_repository(tmp_path):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport shutil\n_ROOT = Path('/synthetic')\n"
                "def fixture(dest):\n    shutil.copy(_ROOT / 'scripts/a.py', dest)\n"
            )
        },
    )
    assert not _copy_sites(tmp_path)


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
