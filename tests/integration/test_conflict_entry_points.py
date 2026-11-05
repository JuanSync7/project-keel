"""
title: Integration — manifest refusals stop every discovered reader
kind: tests
layer: n/a
summary: Discover Python entry points directly under scripts/, scripts/jobs/, scripts/hooks/ and evals/ by their main guard, then discover readers by auditing opens of config/project.json while running their smallest valid invocation. Readers must report one line and exit 2 for a conflict or 14 for another refusal. The invocation table supplies arguments and setup, never the reader roster; exceptions name their reason and fail when no longer discovered. The audit covers this process, not its children.
"""

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402
from git_tree import NoGitError, candidate_files  # noqa: E402

pytestmark = pytest.mark.integration

_DIRS = ("scripts", "scripts/jobs", "scripts/hooks", "evals")
_MANIFEST = "config/project.json"
_HUNK = (
    "{\n"
    + "<" * 7
    + ' before\n"a": 1\n'
    + "=" * 7
    + '\n"a": 2\n'
    + ">" * 7
    + " after\n}\n"
)
_DUPLICATE = '{"a": 1, "a": 2}\n'
_ARGV = {
    "scripts/apply_refactor.py": ("--dry-run",),
    "scripts/audit_project.py": (".",),
    "scripts/check_toolchain.py": ("versions",),
    "scripts/child_exec.py": ("probe.sh",),
    "scripts/config_get.py": ("tests.child_timeout_seconds",),
    "scripts/doc_review.py": ("--execute",),
    "scripts/hooks/on_stop_doc_review.py": ("--execute",),
    "scripts/hooks/on_stop_triage.py": ("--execute",),
    "scripts/gate_evidence.py": ("--gate", "probe", "--", "make", "lint"),
    "scripts/install_sources.py": ("python_index",),
    "scripts/jobs/keep_edited_retired.py": ("--template", ".", "--from", "HEAD"),
    "scripts/launch.py": ("--", "true"),
    "scripts/query_corpus.py": ("what",),
    "scripts/refactor_practice.py": ("x", "--execute"),
    "scripts/run_make_target.py": ("lint",),
    "scripts/scan_secrets.py": ("--staged",),
    "scripts/shell_gate.py": ("lint",),
}
_EXCUSED = {
    "scripts/check_structure.py": "S1 owns the gate: findings exit 1, rather than a CLI refusal",
    "scripts/jobs/build_llms_txt.py": "showcase's legacy JSON reader is KEEL-JSONDUP-2, outside this loader slice",
}

_WRAP = r"""
import os, runpy, sys
manifest, mark, script = sys.argv[1:4]
def opened(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        if os.path.realpath(os.fsdecode(args[0])) == manifest:
            with open(mark, "w") as handle:
                handle.write("read")
sys.addaudithook(opened)
sys.argv = [script] + sys.argv[4:]
sys.path[0] = os.path.dirname(os.path.abspath(script))
runpy.run_path(script, run_name="__main__")
"""


def _files():
    try:
        return candidate_files(str(_ROOT))
    except NoGitError:
        return [str(p.relative_to(_ROOT)) for p in _ROOT.rglob("*") if p.is_file()]


def _entry_points(files):
    found = []
    for rel in files:
        if os.path.dirname(rel) not in _DIRS or not rel.endswith(".py"):
            continue
        tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and any(
                isinstance(v, ast.Constant) and v.value == "__main__"
                for v in node.test.comparators
            )
            for node in tree.body
        ):
            found.append(rel)
    return sorted(found)


def _prepare(root, rel):
    # Reach reads hidden behind optional-tool and generated-project checks.
    (root / "probe.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if rel == "scripts/record_gate_baseline.py":
        (root / "copier.yml").unlink(missing_ok=True)
        # Existing generated answers carry a real template ref; only the
        # template copy needs a minimal generated-project identity.
        if not (root / ".copier-answers.yml").is_file():
            (root / ".copier-answers.yml").write_text(
                "_commit: probe\n", encoding="utf-8"
            )
    if rel == "scripts/cdmon_sync.py":
        shim = root / "cdmon"
        shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        shim.chmod(0o755)
        cfg = root / "config/cdmon/cdmon.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("# probe\n", encoding="utf-8")


def _assert_refusal(tmp_path, payload, expected):
    files = _files()
    entries = _entry_points(files)
    assert entries, "discovered zero entry points"
    timeout_key = ("tests", "child_timeout_seconds")
    timeout = config_loader.resolve(
        config_loader.read(str(_ROOT)), config_loader.rows(timeout_key), _MANIFEST
    )[timeout_key]
    env = build_child_env(root=str(_ROOT), extra=hermetic_git.git_env_vars(tmp_path))
    readers, failures = [], []
    for index, rel in enumerate(entries):
        root = tmp_path / str(index)
        for name in files:
            src = _ROOT / name
            if src.is_symlink() or not src.is_file() or "__pycache__" in src.parts:
                continue
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        _prepare(root, rel)
        (root / _MANIFEST).write_text(payload, encoding="utf-8")
        mark = tmp_path / ("opened-%d" % index)
        child_env = dict(env, PATH=str(root) + os.pathsep + env.get("PATH", ""))
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                _WRAP,
                str(root / _MANIFEST),
                str(mark),
                str(root / rel),
                *_ARGV.get(rel, ()),
            ],
            cwd=root,
            env=build_child_env(root=str(_ROOT), extra=child_env),
            input='{"practice":"p","edits":[{"file":"README.md"}]}',
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if "usage:" in result.stderr and "error:" in result.stderr:
            failures.append(
                "%s: supply its smallest valid arguments in _ARGV: %s"
                % (rel, result.stderr)
            )
        if mark.exists():
            readers.append(rel)
            if rel not in _EXCUSED and not (
                result.returncode == expected
                and len(result.stderr.splitlines()) == 1
                and _MANIFEST in result.stderr
                and "Traceback" not in result.stdout + result.stderr
            ):
                failures.append(
                    "%s: rc %s (wanted %s), stderr=%r"
                    % (rel, result.returncode, expected, result.stderr)
                )
        shutil.rmtree(root)
    assert readers, "discovered zero manifest readers"
    # Copier deliberately prunes the showcase script with its domain. In the
    # template, removing even that file must leave its excuse red.
    applicable = {
        rel
        for rel in _EXCUSED
        if (_ROOT / "copier.yml").is_file() or (_ROOT / rel).is_file()
    }
    assert not (applicable - set(readers)), "stale excuses: %s" % (
        applicable - set(readers)
    )
    assert not failures, "\n".join(failures)


def test_every_entry_point_that_reads_the_manifest_ends_a_conflict_hunk_at_2(tmp_path):
    _assert_refusal(tmp_path, _HUNK, 2)


def test_every_entry_point_that_reads_the_manifest_ends_a_duplicate_key_at_14(tmp_path):
    _assert_refusal(tmp_path, _DUPLICATE, 14)
