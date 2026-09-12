"""
title: Integration — the writers that claim a fixed point reach one
kind: tests
layer: n/a
summary: Runs every doer whose header claims `rerun: fixed-point` with this file as its `rerun_proof:` a SECOND time and asserts the second run changed nothing — the behavioural half of check_V, which can only prove that the claim was made. The worklist is derived from the headers themselves, so a new writer that names this file as its proof and adds no case here fails: a proof that silently covers nothing is the exact defect the declaration was introduced to prevent.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

# This file, as a `rerun_proof:` names it.
_THIS_PROOF = "test:tests/integration/test_idempotence.py"


# --- the worklist, derived from the declarations --------------------------------


def _modules_proved_here() -> set[str]:
    """Every module whose header points its fixed-point claim at THIS file."""
    claimed = set()
    for wroot in cs.WRITER_ROOTS:
        base = _ROOT / wroot
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if any(p in cs.IGNORE_DIRS for p in path.parts):
                continue
            try:
                doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8-sig")))
            except (OSError, SyntaxError, ValueError):
                continue
            if not doc:
                continue
            meta = cs._module_meta(doc)
            if meta.get("rerun_proof") == _THIS_PROOF:
                claimed.add(path.relative_to(_ROOT).as_posix())
    return claimed


def _covered_here() -> set[str]:
    """Every module a case below actually re-runs, read from this file's own
    `@covers` marks so the two lists cannot drift apart silently."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    covered = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        doc = ast.get_docstring(node) or ""
        for line in doc.splitlines():
            if line.strip().startswith("@covers "):
                covered.add(line.strip()[len("@covers ") :].strip())
    return covered


def test_every_writer_that_names_this_file_as_its_proof_is_actually_run():
    """The anti-silent-green guard. check_V proves a `rerun_proof:` RESOLVES; only
    this proves the file it resolves to does any work for that module."""
    claimed, covered = _modules_proved_here(), _covered_here()
    assert claimed, (
        "no module names this file as its proof -- has the key been renamed?"
    )
    assert claimed <= covered, (
        "these modules claim `rerun: fixed-point` with this file as the proof, and "
        "nothing here re-runs them: %s" % sorted(claimed - covered)
    )


def test_no_case_here_covers_a_module_that_stopped_claiming_it():
    """The reverse drift: a case kept running a module whose header moved on.

    Judged only over modules that are still PRESENT. This file ships into every
    generated project, and copier prunes the showcase's renderers when the
    showcase is declined — so downstream a case here legitimately covers a module
    that no longer exists, and the case says so by skipping. An absent module is
    not drift; a present one that stopped claiming this proof is.
    """
    claimed, covered = _modules_proved_here(), _covered_here()
    present = {path for path in covered if (_ROOT / path).is_file()}
    assert present <= claimed, (
        "these cases re-run a module that no longer names this file as its proof: %s"
        % sorted(present - claimed)
    )


def _require(script: str) -> None:
    """Skip, out loud, when *script* was pruned from this project.

    Not a silent pass: a declined showcase takes its renderers with it, and a
    suite that quietly reported success over nothing would be the silent-green
    class this whole file exists to close.
    """
    if not (_ROOT / script).is_file():
        pytest.skip(
            "%s is not in this project (an optional surface was declined)" % script
        )


# --- a corpus to render from, built once ----------------------------------------


@pytest.fixture(scope="module")
def rendered_root(tmp_path_factory) -> Path:
    """A minimal repo root the read-model writers can render from: this repo's
    real `config/project.json` plus a corpus built from this repo's real tree.
    Built ONCE and never written to by the cases, so each case's two runs differ
    in nothing but the fact that one came second."""
    root = tmp_path_factory.mktemp("rendered_root")
    (root / "config").mkdir()
    shutil.copy2(_ROOT / "config" / "project.json", root / "config" / "project.json")
    (root / "wiki").mkdir()
    corpus = root / "wiki" / "corpus.json"
    _run("scripts/jobs/build_corpus.py", "--root", str(_ROOT), "--out", str(corpus))
    _run("scripts/jobs/link_corpus.py", "--corpus", str(corpus))
    assert json.loads(corpus.read_text(encoding="utf-8"))["nodes"], "empty corpus"
    return root


def _run(script: str, *args: str) -> str:
    """Run one of this repo's scripts with the test interpreter; fail loudly."""
    proc = subprocess.run(
        [sys.executable, str(_ROOT / script), *args],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
        timeout=600,
    )
    assert proc.returncode == 0, "%s failed: %s%s" % (script, proc.stdout, proc.stderr)
    return proc.stdout


def _snapshot(path: Path) -> dict[str, bytes]:
    """Every file under *path*, by relative path -> bytes."""
    return {
        p.relative_to(path).as_posix(): p.read_bytes()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def _assert_second_run_changes_nothing(out: Path, run) -> None:
    run()
    first = _snapshot(out)
    assert first, "the first run wrote nothing -- this proves nothing about the second"
    run()
    second = _snapshot(out)
    assert set(first) == set(second), "the second run changed which files exist"
    differing = sorted(k for k in first if first[k] != second[k])
    assert not differing, "the second run rewrote: %s" % differing


# --- the cases ------------------------------------------------------------------


def test_build_llms_txt_is_a_fixed_point(rendered_root, tmp_path):
    """@covers scripts/jobs/build_llms_txt.py"""
    _require("scripts/jobs/build_llms_txt.py")
    out = tmp_path / "llms"
    _assert_second_run_changes_nothing(
        out,
        lambda: _run(
            "scripts/jobs/build_llms_txt.py",
            "--root",
            str(rendered_root),
            "--out-dir",
            str(out),
        ),
    )


def test_export_showcase_static_is_a_fixed_point(rendered_root, tmp_path):
    """@covers scripts/jobs/export_showcase_static.py"""
    _require("scripts/jobs/export_showcase_static.py")
    out = tmp_path / "static"
    _assert_second_run_changes_nothing(
        out,
        lambda: _run(
            "scripts/jobs/export_showcase_static.py",
            "--root",
            str(rendered_root),
            "--out-dir",
            str(out),
        ),
    )


def test_rebuild_index_is_a_fixed_point(tmp_path):
    """@covers scripts/jobs/rebuild_index.py"""
    _require("scripts/jobs/rebuild_index.py")
    out = tmp_path / "out"
    out.mkdir()
    _assert_second_run_changes_nothing(
        out,
        lambda: _run(
            "scripts/jobs/rebuild_index.py",
            "--root",
            str(_ROOT / "docs"),
            "--out",
            str(out / "index.md"),
        ),
    )


def test_apply_refactor_leaves_the_tree_alone_on_a_second_apply(tmp_path):
    """@covers scripts/apply_refactor.py

    The doer applies a proposal by unique search/replace, so the anchor is gone
    once the edit lands. A second identical apply must therefore REFUSE — before
    writing — rather than find some other occurrence and edit it. Re-running is
    safe here because the refusal is loud, not because the edit is repeatable.
    """
    _require("scripts/apply_refactor.py")
    import apply_refactor

    target = tmp_path / "mod.py"
    target.write_text("x = old_name(1)\n", encoding="utf-8")
    spec = {
        "practice": "t",
        "gate": "none",
        "edits": [{"file": "mod.py", "find": "old_name", "replace": "new_name"}],
    }

    first = apply_refactor.apply_and_gate(spec, str(tmp_path), gate="none")
    assert first["applied"], first
    after_first = target.read_bytes()

    with pytest.raises(apply_refactor.RefactorError):
        apply_refactor.apply_and_gate(spec, str(tmp_path), gate="none")
    assert target.read_bytes() == after_first, "the refused second apply still wrote"


# --- the same property, one level up: generation itself -------------------------


def test_the_corpus_build_is_a_fixed_point(rendered_root, tmp_path):
    """Not a `rerun_proof:` target — `make check-corpus` owns build_corpus and
    link_corpus, and it compares a fresh double build. This asserts the narrower
    thing that check has no reason to: writing to a DIFFERENT path yields the
    same bytes, so the output does not depend on where it lands."""
    elsewhere = tmp_path / "somewhere" / "corpus.json"
    _run("scripts/jobs/build_corpus.py", "--root", str(_ROOT), "--out", str(elsewhere))
    _run("scripts/jobs/link_corpus.py", "--corpus", str(elsewhere))
    assert (
        elsewhere.read_bytes() == (rendered_root / "wiki" / "corpus.json").read_bytes()
    )


def test_no_writer_is_left_undeclared():
    """The gate's own finding, asserted from the suite as well: `make check` runs
    check_V, but a project that only ever runs `pytest` still learns about an
    undeclared writer."""
    saved_errors, saved_warnings = cs.errors, cs.warnings
    cs.errors, cs.warnings = [], []
    try:
        cs.check_V()
        found = list(cs.errors)
    finally:
        cs.errors, cs.warnings = saved_errors, saved_warnings
    assert found == [], found


def test_the_declared_vocabulary_is_the_one_the_guide_documents():
    """One vocabulary, two places it is written down: the check and the guide an
    agent is sent to. Drift here is how a rule stops being followable."""
    guide = (_ROOT / "docs" / "guides" / "idempotency.md").read_text(encoding="utf-8")
    for value in cs._RERUNS:
        assert "`%s`" % value in guide, value
    for value in cs._EFFECTS:
        assert "`%s`" % value in guide, value
