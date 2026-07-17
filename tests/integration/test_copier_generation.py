"""
title: Integration — copier generates a structurally valid, tailored project
kind: tests
layer: n/a
summary: `copier` renders keel's root template into a new project — the manifest is tailored to the answers, the un-chosen frontend stack is pruned, CLAUDE.md->AGENT.md symlinks are preserved, and check_structure passes. Skipped when the optional `copier` dep is absent (the langgraph pattern), so keel's default CI stays dependency-free.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

copier = pytest.importorskip("copier")  # optional 'template' extra — skip when absent

_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def _generate(dest, **data):
    """Render the keel template (from git HEAD) into dest with the given answers."""
    copier.run_copy(str(_ROOT), str(dest), data=data, defaults=True,
                    vcs_ref="HEAD", unsafe=False, quiet=True)


@pytest.mark.parametrize("stack", ["react-vite", "astro", "none"])
def test_generated_project_is_tailored_and_valid(stack, tmp_path):
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack=stack)

    # 1. the manifest is tailored to the answers (and valid JSON)
    manifest = json.loads((dest / "config" / "project.json").read_text())
    assert manifest["name"] == "demo_proj"
    frontend = manifest["layers"].get("frontend")
    if stack == "none":
        assert frontend is None
        assert not (dest / "src" / "frontend").exists()      # pruned entirely
    else:
        assert frontend["stack"] == stack
        assert frontend["available"] == [stack]              # only the chosen one
        assert (dest / "src" / "frontend" / stack).is_dir()
        other = "astro" if stack == "react-vite" else "react-vite"
        assert not (dest / "src" / "frontend" / other).exists()  # un-chosen pruned

    # 2. CLAUDE.md -> AGENT.md symlinks are preserved (check_I depends on it)
    assert (dest / "tests" / "CLAUDE.md").is_symlink()

    # 3. copier recorded the answers so `copier update` works later
    assert (dest / ".copier-answers.yml").exists()

    # 4. the structural gate passes on the generated tree (the real judge of "valid")
    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(dest), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_generated_manifest_reflects_enabled_transports(tmp_path):
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj")   # default transports = rest, mcp
    manifest = json.loads((dest / "config" / "project.json").read_text())
    assert manifest["transports"]["enabled"] == ["rest", "mcp"]
    # all transport dirs still ship (dir-pruning is a later slice); enabled is the choice
    assert set(manifest["transports"]["available"]) == {"rest", "grpc", "edge_nginx", "mcp"}


def test_nondefault_name_and_python_propagate_and_stay_valid(tmp_path):
    """A free-text name + a non-default requires-python must reach *every* file that
    declares them — else check_H fails (layers.backend.python != requires-python) or
    the 'tailored' name is a lie. This is the case defaults masked: with backend_python
    left at '>=3.10' the pyproject already matched by luck, so the twin was never
    exercised. Guards the project_slug/project_title derivation and the pyproject twin."""
    dest = tmp_path / "proj"
    _generate(dest, project_name="Acme Widgets", frontend_stack="astro",
              backend_python=">=3.11", transports=["rest"], profiles=["ai"])

    manifest = json.loads((dest / "config" / "project.json").read_text())
    pyproject = (dest / "pyproject.toml").read_text()
    readme = (dest / "README.md").read_text()

    # identifier form (PEP 508-valid slug) reaches both manifest and package metadata
    assert manifest["name"] == "acme_widgets"
    assert 'name = "acme_widgets"' in pyproject
    # the non-default python reaches both, so check_H's equality holds (the gating bug)
    assert manifest["layers"]["backend"]["python"] == ">=3.11"
    assert 'requires-python = ">=3.11"' in pyproject
    # display form (title-cased) reaches the README heading + frontmatter title
    assert "\n# Acme Widgets\n" in readme
    assert "\ntitle: Acme Widgets\n" in readme

    # the real judge: the generated tree passes its own structural gate
    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(dest), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
