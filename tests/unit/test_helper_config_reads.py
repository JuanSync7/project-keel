"""
title: Test helpers — loader refusals keep the helper's error contract
summary: Each gate helper translates a loader refusal to its own error and names an absent or mistyped required block. The import policy's optional process-ending map keeps the loader's announced empty-object default.
"""

import io
import json
from pathlib import Path

import config_loader
import pytest

import ci_adapters
import hermetic_git
import live_server
import selection_guard
import source_tree

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[2]
_READERS = [
    (source_tree, "import_layers", source_tree.SourceTreeError, "import_layers"),
    (selection_guard, "declared_empty", RuntimeError, "make_targets"),
    (hermetic_git, "repo_context_names", AssertionError, "child_env"),
    (live_server, "load_e2e_config", live_server.LiveServerError, "e2e"),
    (live_server, "rest_dir", live_server.LiveServerError, "transports.available"),
    (ci_adapters, "pipeline", AssertionError, "ci_pipeline"),
    (ci_adapters, "gitlab_document", AssertionError, "ci_pipeline"),
]


def _call(module, name, root, monkeypatch):
    if module is selection_guard:
        monkeypatch.setattr(selection_guard, "_ROOT", str(root))
        return selection_guard.declared_empty()
    return getattr(module, name)(root)


@pytest.mark.parametrize("module, name, error, key", _READERS)
@pytest.mark.parametrize("fault", ["absent", "duplicate", "not-object", "not-utf8"])
def test_loader_refusal_keeps_the_helpers_error(
    tmp_path, monkeypatch, module, name, error, key, fault
):
    path = tmp_path / "config" / "project.json"
    path.parent.mkdir()
    if fault != "absent":
        path.write_bytes(
            {
                "duplicate": b'{"name": 1, "name": 2}',
                "not-object": b"[]",
                "not-utf8": b"\xff",
            }[fault]
        )
    with pytest.raises(error, match=r"config/project\.json") as caught:
        _call(module, name, tmp_path, monkeypatch)
    assert isinstance(caught.value.__cause__, config_loader.ConfigError), (key, fault)


@pytest.mark.parametrize("module, name, error, key", _READERS)
@pytest.mark.parametrize("value", [config_loader.NONE, []])
def test_helpers_refuse_required_blocks_by_name(
    tmp_path, monkeypatch, module, name, error, key, value
):
    manifest = config_loader.read(str(_ROOT))
    parent = manifest
    parts = key.split(".")
    for part in parts[:-1]:
        parent = parent[part]
    if value is config_loader.NONE:
        del parent[parts[-1]]
    else:
        parent[parts[-1]] = value
    path = tmp_path / "config" / "project.json"
    path.parent.mkdir()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(error, match=key.replace(".", r"\.")) as caught:
        _call(module, name, tmp_path, monkeypatch)
    assert isinstance(caught.value.__cause__, config_loader.ConfigError)


def test_import_policy_announces_its_empty_process_ending_map(tmp_path, monkeypatch):
    manifest = config_loader.read(str(_ROOT))
    del manifest["import_layers"]["may_end_the_process"]
    path = tmp_path / "config" / "project.json"
    path.parent.mkdir()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(config_loader, "_ANNOUNCED", set())
    stream = io.StringIO()
    monkeypatch.setattr("sys.stderr", stream)
    assert source_tree.import_layers(tmp_path)["may_end_the_process"] == {}
    assert "[using default] import_layers.may_end_the_process = {}" in stream.getvalue()
