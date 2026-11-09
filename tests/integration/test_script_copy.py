"""
title: Integration — a copied script carries every project module it imports
kind: tests
layer: n/a
summary: tests/script_copy.py copy_with_imports copies the files a fixture lists into a scratch project together with every project module a listed Python file imports, followed to its end, so a script that starts importing a sibling never leaves a fixture's copy unable to start. Over synthetic trees: an import of a sibling, made at module level or inside a function, is carried and an unimported sibling is not; a module under scripts/jobs/ carries what it imports from scripts/; a tests/ helper carries its tests/ sibling; `from scripts import x` and `from scripts.x import y`, resolved against the repo root, are carried; an import of the project that no file holds raises naming the importer and the module, never a silent skip; an import cycle is read once per file; a standard-library or installed name is left out; a listed file that does not exist raises naming it before anything is written; and a second copy into the same destination changes no byte. Over keel's own tree, copying scripts/check_structure.py carries scripts/corpus_level.py, the module whose absence from every hand-kept list once stopped 96 fixtures with ModuleNotFoundError, and copying scripts/run_make_target.py carries scripts/resource_limits.py, which it imports as `from scripts import resource_limits`, and the copy starts. An AST scan follows test imports into helpers and repository-root provenance through assignments and function returns, retaining unresolved rooted sources, and recognizes shutil copies, os and Path links and subprocess cp/rsync argv; configured import layers define code roots. Entry rosters must route through the helper and their copied trees must resolve every project import. Direct copies have reasons in _COPY_EXEMPTIONS keyed by module, enclosing function and source expression; a stale or ambiguous site fails naming its key. Local helper calls bind positional and keyword parameter sources through helper chains with cycle termination; calls retain rooted arguments except in non-leftmost operands of joins on proven pytest scratch roots; path operations resolve import origins instead of bare names. A cached repository scan feeds collection and guards pinned to test_launcher.py::_build and tests/script_copy.py, with bounded diagnostic samples and a scan-count regression.
"""

import ast
import copy
import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from test_scratch_root_gate import child_timeout

import script_copy
import source_tree
from bounded_cache import bounded

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
    ): "Endpoint discovery copies the whole transport directory to plant a routing fault; an entry import closure cannot preserve that directory.",
    (
        "integration/test_e2e_coverage.py",
        "_shadow_root",
        "entry",
    ): "The shadow root links whole repository entries around a fault-injected directory; copying an import closure would replace the link layout under test.",
    (
        "integration/test_e2e_coverage.py",
        "_copy_scenarios",
        "str(_ROOT / e2e['scenario_dir'])",
    ): "Marker discovery needs the whole configured scenario directory as source data, including tests outside any entry import closure.",
    (
        "integration/test_e2e_coverage.py",
        "test_a_route_form_the_gate_cannot_derive_is_red",
        "str(_ROOT / rest)",
    ): "Route syntax inspection needs the whole configured transport directory with planted faults, not an entry import closure.",
    (
        "unit/test_isolation_guard.py",
        "test_copying_a_tree_with_an_outbound_link_reaches_nothing",
        "_ROOT",
    ): "The outbound link itself is isolation-guard input; copying files would remove the link behavior being measured.",
    (
        "integration/test_evals_gate.py",
        "test_a_report_dir_through_a_symlink_writes_and_deletes_nothing",
        "link",
    ): "The scratch base comes from an unpacked helper return, beyond structural scratch proof; the symlink is the refusal input, not an executable entry.",
    (
        "integration/test_gate_evidence_record.py",
        "test_a_real_gate_refuses_an_evidence_dir_that_is_a_symlink",
        "repo / _EVIDENCE['dir']",
    ): "The scratch base comes from an unpacked helper return, beyond structural scratch proof; the evidence symlink is the refusal input, not an executable entry.",
    (
        "integration/test_ci_pipeline_gate.py",
        "_copy",
        "str(_ROOT / ci_adapters.CONFIG)",
    ): "The configured manifest is pipeline gate input data, not a Python entry with imports.",
    (
        "integration/test_exit_codes_through_make.py",
        "gate",
        "str(_ROOT / _EVIDENCE['schema'])",
    ): "The configured evidence schema is JSON validation data; an import closure cannot derive this runtime data dependency.",
    (
        "integration/test_gate_evidence_record.py",
        "_build",
        "str(_ROOT / _EVIDENCE['schema'])",
    ): "The configured evidence schema is JSON validation data; an import closure cannot derive this runtime data dependency.",
    (
        "integration/test_gate_evidence_record.py",
        "test_evidence_dir_is_ignored_in_keel_and_its_template",
        "str(_ROOT / name)",
    ): "Gitignore files are copied verbatim as gate input data, not executable entries needing an import closure.",
    (
        "integration/test_install_sources_gate.py",
        "test_the_gitlab_adapter_install_steps_are_judged_too",
        "str(_ROOT / ci_adapters.CONFIG)",
    ): "The configured manifest is installer gate input data, not a Python entry with imports.",
    (
        "integration/test_requirement_traceability.py",
        "build_scratch",
        "str(_ROOT / tree)",
    ): "Traceability scans whole configuration and specification directories as data; an entry import closure would omit unread specifications.",
    (
        "integration/test_requirement_traceability.py",
        "build_scratch",
        "str(_ROOT / name)",
    ): "Gitignore and project metadata are traceability gate input data, not executable entries needing an import closure.",
    (
        "integration/test_toolchain_gate.py",
        "_fe_install_copy",
        "str(_ROOT / config_loader.CONFIG_FILE)",
    ): "The configured manifest is frontend installation input data, not a Python entry with imports.",
    (
        "unit/evals/test_config.py",
        "_project",
        "str(_ROOT / 'config' / 'evals' / name)",
    ): "The eval schemas are JSON validation data, not executable entries needing an import closure.",
    (
        "integration/test_evals_gate.py",
        "build_scratch",
        "str(_ROOT / tree)",
    ): "Replay evals require complete packages with their runtime datasets and adapters.",
}
_COPY_FUNCTIONS = {"copy", "copy2", "copyfile", "copytree", "copy_with_imports"}
# Import-layer prefixes declare every Python code root, including optional
# transports; structure.extra_toplevel only names additions to the taxonomy.
_CODE_ROOTS = {
    prefix.split("/")[0]
    for layer in source_tree.import_layers(_ROOT)["order"]
    for prefix in layer
}

# Only resolved import origins (or pytest-injected fixture parameters) prove
# these path operations. A local function with the same spelling proves nothing.
_PATH_OPERATIONS = {
    "pathlib.Path": "construct",
    "builtins.str": "construct",
    "os.path.dirname": "parent",
    "os.path.abspath": "absolute",
    "os.path.realpath": "absolute",
    "os.path.join": "join",
    "pytest.tmp_path": "scratch",
    "pytest.tmp_path_factory": "factory",
    "pytest.tmp_path_factory.mktemp": "scratch",
}


def _origin(expr, definitions):
    """Resolve imported names, respecting local bindings and fixture parameters."""
    if isinstance(expr, ast.Attribute):
        owner = _origin(expr.value, definitions)
        return owner + "." + expr.attr if owner else None
    if not isinstance(expr, ast.Name):
        return None
    values = definitions.get(expr.id, [])
    if not values:
        return "builtins.str" if expr.id == "str" else None
    origins = set()
    for value in values:
        if isinstance(value, ast.arg) and "pytest." + value.arg in _PATH_OPERATIONS:
            origins.add("pytest." + value.arg)
        elif isinstance(value, ast.Import):
            origins.update(
                alias.name if alias.asname else alias.name.split(".")[0]
                for alias in value.names
                if (alias.asname or alias.name.split(".")[0]) == expr.id
            )
        elif isinstance(value, ast.ImportFrom):
            origins.update(
                value.module + "." + alias.name
                for alias in value.names
                if value.module and (alias.asname or alias.name) == expr.id
            )
        else:
            return None
    return origins.pop() if len(origins) == 1 else None


def _join_operands(expr, definitions):
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return [expr.left, expr.right]
    if isinstance(expr, ast.Call) and not expr.keywords:
        if _PATH_OPERATIONS.get(_origin(expr.func, definitions)) == "join":
            return expr.args
        if isinstance(expr.func, ast.Attribute) and expr.func.attr == "joinpath":
            return [expr.func.value, *expr.args]
    return []


def _scratch_path(expr, definitions, seen=frozenset(), *, kind="scratch"):
    """Prove a pytest scratch base; unknown or mixed bindings never prove it."""
    if isinstance(expr, ast.Name):
        if expr.id in seen:
            return False
        if _PATH_OPERATIONS.get(_origin(expr, definitions)) == kind:
            return True
        values = definitions.get(expr.id, [])
        return bool(values) and all(
            _scratch_path(value, definitions, seen | {expr.id}, kind=kind)
            for value in values
        )
    if kind != "scratch":
        return False
    if isinstance(expr, ast.Call):
        if _PATH_OPERATIONS.get(_origin(expr.func, definitions)) == "scratch":
            return True
        if (
            isinstance(expr.func, ast.Attribute)
            and expr.func.attr == "mktemp"
            and _scratch_path(expr.func.value, definitions, seen, kind="factory")
        ):
            return True
    operands = _join_operands(expr, definitions)
    return (
        len(operands) > 1
        and _scratch_path(operands[0], definitions, seen)
        and not any(
            isinstance(part, ast.Constant)
            and isinstance(part.value, str)
            and Path(part.value).is_absolute()
            for part in operands[1:]
        )
    )


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
        }
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
        operation = _PATH_OPERATIONS.get(_origin(expr.func, definitions))
        args = [_path_value(a, definitions, root, rel, seen) for a in expr.args]
        if args and isinstance(args[0], (str, Path)):
            if operation == "construct":
                return Path(args[0])
            if operation == "parent":
                return Path(args[0]).parent
            if operation == "absolute":
                return Path(args[0]).resolve()
            if operation == "join" and all(isinstance(a, (str, Path)) for a in args):
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


def _source_tokens(
    expr,
    definitions,
    imports,
    root,
    rel,
    seen=frozenset(),
    *,
    called=False,
    scratch_operand=False,
):
    """Conservative path provenance, including rosters and loop variables.

    Follow assignments and imported constants without importing test modules or
    executing calls. Unknown expressions contribute their literal path parts;
    this is a source audit, not a general Python data-flow interpreter.
    """
    if scratch_operand and isinstance(expr, ast.Call):
        return set()
    operands = _join_operands(expr, definitions)
    if operands and _scratch_path(expr, definitions):
        return _source_tokens(
            operands[0], definitions, imports, root, rel, seen
        ) | set().union(
            *(
                _source_tokens(
                    part,
                    definitions,
                    imports,
                    root,
                    rel,
                    seen,
                    scratch_operand=True,
                )
                for part in operands[1:]
            )
        )
    value = _path_value(expr, definitions, root, rel)
    if isinstance(value, (str, Path)) and Path(value).is_relative_to(root):
        relative = Path(value).relative_to(root).as_posix()
        return {"<repo>"} if relative == "." else {"<repo>", relative}
    if isinstance(expr, ast.Name):
        name = expr.id
        if name in seen:
            return set()
        if name in definitions and any(
            not isinstance(value, (ast.Import, ast.ImportFrom))
            for value in definitions[name]
        ):
            return set().union(
                *(
                    _source_tokens(
                        value,
                        definitions,
                        imports,
                        root,
                        rel,
                        seen | {name},
                        scratch_operand=scratch_operand,
                    )
                    for value in definitions[name]
                    if not isinstance(value, (ast.Import, ast.ImportFrom))
                    and (
                        called
                        or not isinstance(
                            value, (ast.FunctionDef, ast.AsyncFunctionDef)
                        )
                    )
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
                    called=called,
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
                called=called,
            )
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return {expr.value}
    if isinstance(expr, ast.Call):
        # Calls preserve provenance unless their position in a proven scratch
        # join supplied the structural exception above. Unknown wrappers fail closed.
        return _source_tokens(
            expr.func, definitions, imports, root, rel, seen, called=True
        ) | set().union(
            *(
                _source_tokens(arg, definitions, imports, root, rel, seen)
                for arg in [*expr.args, *(key.value for key in expr.keywords)]
            )
        )
    if isinstance(expr, (ast.FunctionDef, ast.AsyncFunctionDef)):
        local = dict(definitions, **_definitions(expr))
        # Reading configuration from the repository does not make the returned
        # config object a repository root. Only a known path return establishes
        # that a call with no rooted argument supplies repository provenance.
        return {
            "<repo>"
            for node in source_tree.scope_nodes(expr)
            if isinstance(node, ast.Return)
            and node.value is not None
            and _path_value(node.value, local, root, rel) == root
        }
    return set().union(
        *(
            _source_tokens(
                child,
                definitions,
                imports,
                root,
                rel,
                seen,
                scratch_operand=scratch_operand,
            )
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
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.asname or (
                    alias.name.split(".")[0]
                    if isinstance(node, ast.Import)
                    else alias.name
                )
                out.setdefault(name, []).append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, []).append(node)
        elif isinstance(node, ast.Assign):
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
    if method in {"symlink_to", "hardlink_to"} and isinstance(node.func, ast.Attribute):
        target = (
            node.args[0]
            if node.args
            else next((k.value for k in node.keywords if k.arg == "target"), None)
        )
        # Either endpoint can expose a repository path. Keep one site per call
        # even when both endpoints are rooted there.
        return [(expr, None) for expr in (target, node.func.value) if expr is not None]
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


def _replace_names(expr, bindings, seen=frozenset()):
    """Inline local expressions without executing code; cycles stop at the name."""

    class Replace(ast.NodeTransformer):
        def visit_Name(self, node):
            values = bindings.get(node.id, [])
            if node.id in seen or not values:
                return node
            expanded = [
                _replace_names(value, bindings, seen | {node.id}) for value in values
            ]
            return expanded[0] if len(expanded) == 1 else ast.Tuple(elts=expanded)

    return Replace().visit(copy.deepcopy(expr))


def _local_copy_arguments(
    callee, call, definitions, aliases, imports, root, rel, seen=frozenset()
):
    """Propagate a local helper's parameter sources to each calling site."""

    class Bind(ast.NodeTransformer):
        def __init__(self, arguments):
            self.arguments = arguments

        def visit_Name(self, node):
            return (
                copy.deepcopy(self.arguments[node.id][0])
                if node.id in self.arguments
                else node
            )

    functions = [
        value
        for value in definitions.get(callee, [])
        if isinstance(value, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for function in functions:
        if id(function) in seen:
            continue
        parameters = [*function.args.posonlyargs, *function.args.args]
        bound = {
            param.arg: [arg] for param, arg in zip(parameters, call.args, strict=False)
        }
        bound.update((kw.arg, [kw.value]) for kw in call.keywords if kw.arg)
        for param, default in zip(
            parameters[-len(function.args.defaults) :],
            function.args.defaults,
            strict=False,
        ):
            bound.setdefault(param.arg, [default])
        for param, default in zip(
            function.args.kwonlyargs, function.args.kw_defaults, strict=True
        ):
            if default is not None:
                bound.setdefault(param.arg, [default])
        local = _definitions(function)
        # Parameters shadow module bindings, including same-named functions.
        names = {p.arg for p in [*parameters, *function.args.kwonlyargs]}
        environment = dict(definitions, **local)
        for name in names:
            environment.pop(name, None)
        local_aliases = dict(aliases)
        for node in source_tree.scope_nodes(function):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local_aliases[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    local_aliases[alias.asname or alias.name] = (
                        node.module + "." + alias.name
                    )
        for node in source_tree.scope_nodes(function):
            if not isinstance(node, ast.Call):
                continue
            parts = ast.unparse(node.func).split(".")
            target = ".".join([local_aliases.get(parts[0], parts[0]), *parts[1:]])
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "symlink_to",
                "hardlink_to",
            }:
                target = "Path." + node.func.attr
            copies = [
                (target, source, roster)
                for source, roster in _copy_arguments(target, node, environment)
                # Already-rooted sinks are audited at their own definition;
                # propagate only provenance supplied by the caller.
                if "<repo>"
                not in _source_tokens(source, environment, imports, root, rel)
            ]
            copies.extend(
                _local_copy_arguments(
                    target,
                    node,
                    environment,
                    local_aliases,
                    imports,
                    root,
                    rel,
                    seen | {id(function)},
                )
            )
            for sink, source, roster in copies:
                source = _replace_names(source, local)
                if not any(
                    isinstance(n, ast.Name) and n.id in names for n in ast.walk(source)
                ):
                    continue

                # One substitution pass keeps caller names in the caller scope.
                yield (
                    sink,
                    Bind(bound).visit(source),
                    (
                        Bind(bound).visit(_replace_names(roster, local))
                        if roster is not None
                        else None
                    ),
                )


def _copy_sites(root=_ROOT, modules=None):
    """Discover source copies throughout the test modules' helper import graph."""
    sites = []
    for rel in _consumer_modules(root) if modules is None else modules:
        path = root / rel
        if path == Path(__file__):
            # This module tests the copier itself on synthetic and real trees;
            # its real-tree calls have dedicated behavioral assertions above.
            continue
        tree = source_tree.parse(root, rel)
        imports = source_tree.bindings(root, rel, tree, _search(rel))

        def scan(scope, inherited, inherited_aliases, inherited_imports, anchor, rel):
            local_definitions = _definitions(scope)
            definitions = dict(inherited, **local_definitions)
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for param in [
                    *scope.args.posonlyargs,
                    *scope.args.args,
                    *scope.args.kwonlyargs,
                ]:
                    definitions[param.arg] = [
                        param,
                        *local_definitions.get(param.arg, []),
                    ]
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
                path_link = isinstance(node.func, ast.Attribute) and (
                    node.func.attr in {"symlink_to", "hardlink_to"}
                )
                if path_link:
                    callee = "Path." + node.func.attr
                copies = [
                    (callee, source, roster, False)
                    for source, roster in _copy_arguments(callee, node, definitions)
                ]
                copies.extend(
                    (sink, source, roster, True)
                    for sink, source, roster in _local_copy_arguments(
                        callee, node, definitions, aliases, imports, root, rel
                    )
                )
                for sink, source, roster, propagated in copies:
                    path_link = sink in {"Path.symlink_to", "Path.hardlink_to"}
                    tokens = _source_tokens(source, definitions, imports, root, rel)
                    key = (
                        Path(rel).relative_to("tests").as_posix(),
                        anchor or "<module>",
                        ast.unparse(source),
                    )
                    code = any(
                        token.split("/")[0] in _CODE_ROOTS or token.endswith(".py")
                        for token in tokens
                    )
                    if key in _COPY_EXEMPTIONS or (
                        "<repo>" in tokens
                        and (
                            sink == "script_copy.copy_with_imports"
                            or propagated
                            or code
                            or tokens == {"<repo>"}
                            or path_link
                            or _path_value(source, definitions, root, rel) is None
                        )
                    ):
                        sites.append((rel, node.lineno, sink, roster, key))
                        if path_link:
                            break

        scan(tree, {}, {}, imports, "", rel)
    return sites


_REPOSITORY_SCANS = 0


@bounded(str(_ROOT))
def _repository_scan():
    global _REPOSITORY_SCANS
    _REPOSITORY_SCANS += 1
    modules = _consumer_modules(_ROOT)
    return _copy_sites(_ROOT, modules), modules


def _copy_cases():
    sites, _ = _repository_scan()
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
    sites, _ = _repository_scan()
    assert sites, "copy discovery found no sites: %s" % (sites,)
    _assert_exemptions(sites, _COPY_EXEMPTIONS, _ROOT)


def _sample(items):
    return "%d total; sample: %s" % (len(items), items[:10])


def _assert_routed(sites):
    routed = [site for site in sites if site[2] == "script_copy.copy_with_imports"]
    assert any(
        site[4][:2] == ("integration/test_launcher.py", "_build") for site in routed
    ), "copy discovery missed test_launcher.py::_build route; " + _sample(
        [(site[0], site[1], site[2]) for site in sites]
    )


def test_copy_discovery_includes_routed_sites():
    sites, _ = _repository_scan()
    _assert_routed(sites)


def _assert_helpers(modules):
    # Asserting a bare name keeps pytest's assertion rewriting from appending
    # the complete module list at high verbosity, and the assertion-quality
    # gate counts an assert where it would not count a raise.
    scanned = "tests/script_copy.py" in modules
    assert scanned, "copy discovery missed tests/script_copy.py; " + _sample(modules)


def test_copy_discovery_scans_helper_modules():
    _, modules = _repository_scan()
    _assert_helpers(modules)


def test_repository_discovery_runs_once():
    first = _repository_scan()
    second = _repository_scan()
    assert _REPOSITORY_SCANS == 1, (
        "repository scans: %d (expected 1)" % _REPOSITORY_SCANS
    )
    assert second is first


@pytest.mark.parametrize("guard", ["routed", "helpers"])
def test_discovery_guards_require_the_named_consumer_and_bound_the_message(guard):
    modules = ["tests/helper_%02d.py" % i for i in range(30)]
    sites = [
        (rel, 1, "script_copy.copy_with_imports", None, (rel, "fixture", "ROOT"))
        for rel in modules
    ]
    with pytest.raises(AssertionError) as caught:
        if guard == "routed":
            _assert_routed(sites)
        else:
            _assert_helpers(modules)
    message = str(caught.value)
    assert "30 total" in message
    assert "helper_09.py" in message
    assert "helper_10.py" not in message
    assert "helper_29.py" not in message


@pytest.mark.parametrize(
    "invocation",
    [
        "_cp(BASE / 'config/x.json', dest)",
        "_cp(dst=dest, src=BASE / 'config/x.json')",
        "outer(BASE / 'config/x.json', dest)",
        "outer(dst=dest, source=BASE / 'config/x.json')",
    ],
)
def test_discovery_propagates_local_helper_parameters(tmp_path, invocation):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport shutil\n"
                "BASE = Path(__file__).parents[1]\n"
                "def _cp(src, dst):\n    alias = src\n    shutil.copy(alias, dst)\n"
                "def outer(source, dst):\n    _cp(src=source, dst=dst)\n"
                "    outer(source, dst)\n"
                "def fixture(dest):\n    " + invocation + "\n"
            )
        },
    )
    sites = _copy_sites(tmp_path)
    assert [(s[2], s[4][1:]) for s in sites] == [
        ("shutil.copy", ("fixture", "BASE / 'config/x.json'"))
    ]


@pytest.mark.parametrize(
    "source",
    [
        "os.fspath(BASE / 'tests')",
        "os.path.normpath(BASE / 'tests')",
        "os.path.expanduser(BASE / 'tests')",
        "'{}/x'.format(BASE)",
        "(BASE / 'x').relative_to(BASE)",
        "Path(f(BASE))",
        "unknown(BASE)",
        "unknown(root=BASE)",
        "BASE.read_text()",
        "scratch / load_cfg(BASE)",
        "tmp_path / '/abs' / load_cfg(BASE)",
        "tmp_path.joinpath('/abs', load_cfg(BASE))",
        "os.path.join(tmp_path, '/abs', load_cfg(BASE))",
        "join(tmp_path, load_cfg(BASE))",
        "join(BASE, 'config')",
        "mixed / load_cfg(BASE)",
        "tmp_path / BASE",
    ],
)
def test_calls_preserve_rooted_sources_without_scratch_join_proof(tmp_path, source):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport shutil\nimport os\n"
                "BASE = Path(__file__).parents[1]\n"
                "def join(*args):\n    return args[0]\n"
                "def fixture(dest, tmp_path, scratch):\n"
                "    mixed = tmp_path\n    mixed = BASE\n"
                "    shutil.copytree(" + source + ", dest)\n"
            )
        },
    )
    sites = _copy_sites(tmp_path)
    assert len(sites) == 1, source
    assert sites[0][4][1:] == ("fixture", ast.unparse(ast.parse(source).body[0].value))


@pytest.mark.parametrize(
    "source",
    [
        "tmp_path / 'config' / load_cfg(BASE)",
        "scratch / load_cfg(root=BASE)",
        "scratch.joinpath('config', load_cfg(BASE))",
        "os.path.join(scratch, 'config', load_cfg(BASE))",
        "path_ops.join(scratch, load_cfg(BASE))",
        "joining(scratch, load_cfg(BASE))",
        "tmp_path_factory.mktemp('repo') / load_cfg(BASE)",
        "factory_root / load_cfg(BASE)",
        "factory.mktemp('repo').joinpath(load_cfg(BASE))",
    ],
)
def test_only_a_call_inside_a_proven_scratch_join_loses_rooted_arguments(
    tmp_path, source
):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport shutil\nimport os\n"
                "import os.path as path_ops\nfrom os.path import join as joining\n"
                "BASE = Path(__file__).parents[1]\n"
                "def fixture(dest, tmp_path, tmp_path_factory):\n"
                "    scratch = tmp_path\n"
                "    factory_root = tmp_path_factory.mktemp('repo')\n"
                "    factory = tmp_path_factory\n"
                "    shutil.copytree(" + source + ", dest)\n"
            )
        },
    )
    assert _copy_sites(tmp_path) == [], source


def test_a_reassigned_scratch_parameter_does_not_prove_a_scratch_join(tmp_path):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport shutil\n"
                "BASE = Path(__file__).parents[1]\n"
                "def fixture(dest, tmp_path):\n"
                "    tmp_path = BASE\n"
                "    shutil.copytree(tmp_path / load_cfg(BASE), dest)\n"
            )
        },
    )
    assert len(_copy_sites(tmp_path)) == 1


def test_a_path_join_on_a_rooted_receiver_is_still_a_rooted_source(tmp_path):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport shutil\n"
                "BASE = Path(__file__).parents[1]\n"
                "def fixture(dest):\n    shutil.copytree(BASE.joinpath(configured()), dest)\n"
            )
        },
    )
    assert len(_copy_sites(tmp_path)) == 1


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
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "source = REPOSITORY / config['directory']\n    shutil.copytree(source, dest)",
            "shutil.copytree",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "source = REPOSITORY / 'config/project.json'\n    if flag:\n        source = REPOSITORY / configured_path()\n    shutil.copy(source, dest)",
            "shutil.copy",
        ),
        (
            "def repository():\n    base = Path(__file__).parents[1]\n    return base",
            "shutil.copytree(repository() / configured_path(), dest)",
            "shutil.copytree",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "dest.symlink_to(REPOSITORY / config['directory'])",
            "Path.symlink_to",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "dest.hardlink_to(target=REPOSITORY / 'config/project.json')",
            "Path.hardlink_to",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "(REPOSITORY / 'config/link').symlink_to(dest)",
            "Path.symlink_to",
        ),
        (
            "REPOSITORY = Path(__file__).parents[1]",
            "(REPOSITORY / 'scripts/link.py').hardlink_to(REPOSITORY / 'scripts/a.py')",
            "Path.hardlink_to",
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


def test_discovery_follows_an_imported_root_returning_function(tmp_path):
    _tree(
        tmp_path,
        {
            "tests/paths.py": "from pathlib import Path\ndef repository():\n    return Path(__file__).parents[1]\n",
            "tests/test_consumer.py": "from paths import repository as base\nimport shutil\ndef fixture(dest):\n    shutil.copytree(base() / configured_path(), dest)\n",
        },
    )
    sites = _copy_sites(tmp_path)
    assert [(s[0], s[2], s[4][1]) for s in sites] == [
        ("tests/test_consumer.py", "shutil.copytree", "fixture")
    ]


def test_discovery_leaves_unrooted_sources_and_literal_metadata_out(tmp_path):
    _tree(
        tmp_path,
        {
            "tests/test_consumer.py": (
                "from pathlib import Path\nimport shutil\n"
                "BASE = Path(__file__).parents[1]\n"
                "def fixture(dest, scratch):\n"
                "    shutil.copytree(configured_path(), dest)\n"
                "    shutil.copytree(scratch / configured_path(), dest)\n"
                "    dest.symlink_to(scratch / 'scripts/a.py')\n"
                "    dest.hardlink_to(scratch / 'scripts/a.py')\n"
                "    shutil.copy(BASE / 'config/project.json', dest)\n"
                "def scratch():\n    return BASE\n"
                "def other(dest, scratch):\n"
                "    shutil.copytree(scratch / configured_path(), dest)\n"
            )
        },
    )
    assert _copy_sites(tmp_path) == []


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
