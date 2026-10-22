"""
title: Unit — model call limits
kind: tests
layer: backend
summary: models/limits.py reads an adapter's time limit from config/project.json `models.timeout_seconds`, refuses an adapter the map does not name rather than leaving its call unbounded, and refuses a limit that is not a number above zero through scripts/config_loader.py, naming the key.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from models import limits  # noqa: E402
from scripts import config_loader  # noqa: E402

pytestmark = pytest.mark.unit


def _project(tmp_path, models_block):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"models": models_block}), encoding="utf-8"
    )
    return str(tmp_path)


def test_an_adapter_s_time_limit_is_its_entry(tmp_path):
    root = _project(tmp_path, {"timeout_seconds": {"a": 7, "b": 2.5}})
    assert limits.timeout_seconds("a", root) == 7.0
    assert limits.timeout_seconds("b", root) == 2.5


def test_an_adapter_the_map_does_not_name_is_refused(tmp_path):
    root = _project(tmp_path, {"timeout_seconds": {"a": 7}})
    with pytest.raises(ValueError, match=r"no entry for 'b'.*\"b\": <seconds>"):
        limits.timeout_seconds("b", root)


@pytest.mark.parametrize("bad", [0, -1, True, "60", None])
def test_a_limit_that_is_not_a_number_above_zero_is_refused(tmp_path, bad):
    root = _project(tmp_path, {"timeout_seconds": {"a": bad}})
    with pytest.raises(config_loader.WrongValue, match=r"models\.timeout_seconds"):
        limits.timeout_seconds("a", root)


def test_every_adapter_that_calls_out_ships_with_a_limit():
    for adapter in ("claude-code-headless", "openai-compatible"):
        assert limits.timeout_seconds(adapter) > 0
