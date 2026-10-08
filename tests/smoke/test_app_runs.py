"""
title: Smoke — `make run` starts the composition root
kind: tests
layer: n/a
summary: Liveness of the one entrypoint every project ships: `make run`, started with the allowlisted environment (no inherited PYTHONPATH, no outer make's flags), runs the module config/project.json `layers.app` declares and exits 0. A project that declares no composition root (layers.app null) skips it, and so declares `smoke` in make_targets.empty_test_selections; a host without make skips it.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.smoke


def test_make_run_starts_the_composition_root():
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    layers = manifest.get("layers") or {}
    if "app" not in layers:
        pytest.fail(
            "config/project.json declares no layers.app; declare the composition "
            "root as {path, module}, or null when the project has none"
        )
    if layers["app"] is None:
        pytest.skip("no composition root declared (layers.app is null)")
    if shutil.which("make") is None:
        pytest.skip("make not installed")
    r = subprocess.run(
        ["make", "--no-print-directory", "PY=" + sys.executable, "run"],
        cwd=str(_ROOT),
        env=build_child_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, "make run exited %d:\n%s%s" % (
        r.returncode,
        r.stdout[-2000:],
        r.stderr[-2000:],
    )
