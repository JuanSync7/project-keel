"""
title: Integration — a copied script carries every project module it imports
kind: tests
layer: n/a
summary: tests/script_copy.py copy_with_imports copies the files a fixture lists into a scratch project together with every project module a listed Python file imports, followed to its end, so a script that starts importing a sibling never leaves a fixture's copy unable to start. Over synthetic trees: an import of a sibling, made at module level or inside a function, is carried and an unimported sibling is not; a module under scripts/jobs/ carries what it imports from scripts/; a tests/ helper carries its tests/ sibling; `from scripts import x` and `from scripts.x import y`, resolved against the repo root, are carried; an import of the project that no file holds raises naming the importer and the module, never a silent skip; an import cycle is read once per file; a standard-library or installed name is left out; a listed file that does not exist raises naming it before anything is written; and a second copy into the same destination changes no byte. Over keel's own tree, copying scripts/check_structure.py carries scripts/corpus_level.py, the module whose absence from every hand-kept list once stopped 96 fixtures with ModuleNotFoundError, and copying scripts/run_make_target.py carries scripts/resource_limits.py, which it imports as `from scripts import resource_limits`, and the copy starts.
"""

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
