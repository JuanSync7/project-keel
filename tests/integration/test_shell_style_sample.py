"""
title: Integration — the shell-style guide's sample script passes every gate the guide names
kind: tests
layer: n/a
summary: docs/guides/shell-style.md §1 shows one script and says it passes every gate. This test lifts that fenced `sh` block and holds it to each gate as scripts/pad_report.sh in a fresh tree: the `title:` and `summary:` check_O reads, the `effect:` check_V demands of shell, the re-exec line check_X demands first (scripts/check_structure.py `reexec_findings`), the endings tests/integration/test_exit_gate.py `shell_findings` judges, no config file named in its code (tests/integration/test_config_reads_gate.py `shell_reads`), and the linter and the formatter's check config/project.json `shell` names, run through scripts/shell_gate.py `main` under the repository's .editorconfig, which the formatter reads. A guide with no `sh` block, or with two, is a failure. A tool on neither the interpreter's directory nor PATH skips that one case and says which tool, because keel declares neither tool as a dependency; every other case runs on any host.
"""

import io
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests" / "integration"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
import shell_gate  # noqa: E402
from exit_codes import ExitCode  # noqa: E402
from test_config_reads_gate import shell_reads  # noqa: E402
from test_exit_gate import _sh_tree, shell_findings  # noqa: E402

pytestmark = pytest.mark.integration

_GUIDE = _ROOT / "docs" / "guides" / "shell-style.md"
_AS = "scripts/pad_report.sh"
_BLOCK = re.compile(r"^```sh\n(.*?)^```$", re.MULTILINE | re.DOTALL)


def _sample():
    blocks = _BLOCK.findall(_GUIDE.read_text(encoding="utf-8"))
    assert len(blocks) == 1, (
        "%s holds %d `sh` blocks; this test judges exactly one, its §1 sample"
        % (_GUIDE.name, len(blocks))
    )
    return blocks[0]


@pytest.fixture
def tree(tmp_path, monkeypatch):
    root = _sh_tree(tmp_path, monkeypatch, {_AS: _sample()})
    shutil.copy(str(_ROOT / ".editorconfig"), str(root / ".editorconfig"))
    # The tools run under the allowlist, which the tree's manifest must declare.
    manifest = root / "config" / "project.json"
    loaded = json.loads(manifest.read_text(encoding="utf-8"))
    loaded["child_env"] = config_loader.read(str(_ROOT), "config/project.json")[
        "child_env"
    ]
    manifest.write_text(json.dumps(loaded, sort_keys=True), encoding="utf-8")
    return root


def test_the_sample_carries_the_header_check_o_and_check_v_read():
    block = cs._shell_header(_sample())
    assert block is not None, "the sample opens with no comment block"
    meta = cs._module_meta(block)
    assert meta.get("title") and meta.get("summary"), meta
    assert cs._shell_header_findings({_AS: _sample()}) == []
    assert cs._shell_effect_findings({_AS: _sample()}, None, None, None, None) == (
        [],
        [],
    )


def test_the_sample_opens_with_the_re_exec_line():
    assert cs.reexec_findings(_sample(), _AS) == []


def test_the_sample_ends_only_through_the_helper(tree):
    assert shell_findings(tree) == {"files": 1, "findings": [], "held_status": []}


def test_the_sample_names_no_config_file(tree):
    assert shell_reads(tree, _AS, config_loader.PROJECT_READS) == []


@pytest.mark.parametrize("mode", ["lint", "format-check"])
def test_the_sample_passes_the_configured_shell_tool(tree, mode, capsys):
    role = shell_gate._ROLE[mode]
    name = shell_gate.settings(str(tree), stream=io.StringIO())[role]
    if shell_gate._find(name) is None:
        pytest.skip("the %s %s is not installed here" % (role, name))
    code = shell_gate.main([mode], root=str(tree))
    assert code == ExitCode.SUCCESS, capsys.readouterr()
