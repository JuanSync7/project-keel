"""
title: Confined job fixtures
summary: Scratch projects with an external sentinel and an escaping parent link.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))


@pytest.fixture
def escaped(tmp_path):
    root, outside = tmp_path / "project", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    return root, outside
