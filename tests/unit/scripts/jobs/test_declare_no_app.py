"""
title: Confined declare_no_app mutations
summary: External sentinel preservation, usable internal links and explicit output policy.
"""

import json

import declare_no_app as job
import pytest
from exit_codes import ExitCode

pytestmark = pytest.mark.unit


def test_external_output_preserved(escaped, monkeypatch):
    root, outside = escaped
    (root / "config").symlink_to(outside, target_is_directory=True)
    sentinel = outside / "project.json"
    before = json.dumps(
        {
            "layers": {"app": {"path": "src/app"}},
            "make_targets": {"empty_test_selections": {}, "effect_proof_skip": {}},
        }
    ).encode()
    sentinel.write_bytes(before)
    monkeypatch.setattr(job, "head_manifest", lambda root: {})
    rc = job.main(["--root", str(root)])
    assert sentinel.read_bytes() == before
    assert rc == ExitCode.USAGE


def test_internal_parent_link(tmp_path, monkeypatch):
    root = tmp_path / "project"
    real = root / "real"
    real.mkdir(parents=True)
    (root / "config").symlink_to(real, target_is_directory=True)
    manifest = real / "project.json"
    manifest.write_text(
        json.dumps(
            {
                "layers": {"app": {"path": "src/app"}},
                "make_targets": {"empty_test_selections": {}, "effect_proof_skip": {}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(job, "head_manifest", lambda root: {})
    assert job.main(["--root", str(root)]) == ExitCode.SUCCESS
    assert json.loads(manifest.read_text(encoding="utf-8"))["layers"]["app"] is None
