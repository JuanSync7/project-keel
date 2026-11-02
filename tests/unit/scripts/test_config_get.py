"""
title: Unit — config_get (a shell script reads a configured value through the loader)
kind: tests
layer: n/a
summary: scripts/config_get.py KEY prints the value scripts/config_loader.py `resolve` gives the KEYS row whose dotted path is KEY — a string as written, any other value as canonical JSON, one line on stdout — with the loader's own lines (a default announced, a wrong value refused) on stderr. Its file comes from the row, so a variable-only row reads the environment alone and a variable set beside the file wins, as the loader's precedence says. A secret row and a key no row declares are USAGE, and nothing reaches stdout; an absent or unreadable file and a wrong value are CONFIG, never a guess.
"""

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_get  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_process(monkeypatch):
    # Each run of config_get is its own process, and the loader announces a
    # default once per process, so no case may see what another announced.
    monkeypatch.setattr(config_get.config_loader, "_ANNOUNCED", set())


def _project(tmp_path, manifest):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    if manifest is not None:
        text = manifest if isinstance(manifest, str) else json.dumps(manifest)
        (root / "config" / "project.json").write_text(text, encoding="utf-8")
    return root


def _run(root, *argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = config_get.main(list(argv), root=str(root))
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize(
    "manifest, key, printed",
    [
        ({"shell": {"formatter": "shfmt -i 2"}}, "shell.formatter", "shfmt -i 2\n"),
        (
            {"shell": {"script_suffixes": [".sh", ".ksh"]}},
            "shell.script_suffixes",
            '[".sh", ".ksh"]\n',
        ),
        ({"shell": {"enabled": False}}, "shell.enabled", "false\n"),
        (
            {"shell": {"excluded_paths": {"b": "y", "a": "x"}}},
            "shell.excluded_paths",
            '{"a": "x", "b": "y"}\n',
        ),
    ],
    ids=["string raw", "list as JSON", "bool as JSON", "object sorted"],
)
def test_a_set_value_is_printed_one_line(tmp_path, manifest, key, printed):
    code, out, err = _run(_project(tmp_path, manifest), key)
    assert (code, out) == (ExitCode.SUCCESS, printed), err


def test_an_unset_key_prints_its_default_and_the_loader_announces_it(tmp_path):
    code, out, err = _run(_project(tmp_path, {}), "shell.linter")
    assert (code, out) == (ExitCode.SUCCESS, "shellcheck\n"), err
    assert "[using default] shell.linter" in err, err


def test_a_null_default_is_printed_as_json_null(tmp_path):
    code, out, err = _run(_project(tmp_path, {}), "shell.no_scripts")
    assert (code, out) == (ExitCode.SUCCESS, "null\n"), err


def test_a_variable_only_row_reads_the_environment_without_the_file(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KEEL_MCP_MODEL", "some-model")
    code, out, err = _run(_project(tmp_path, None), "KEEL_MCP_MODEL")
    assert (code, out) == (ExitCode.SUCCESS, "some-model\n"), err


@pytest.mark.parametrize(
    "argv, said",
    [
        ((), "name one key"),
        (("shell.formatter", "shell.linter"), "name one key"),
        (("shell.nope",), "is not a key scripts/config_loader.py KEYS declares"),
        (("shell",), "is not a key scripts/config_loader.py KEYS declares"),
        (("ANTHROPIC_API_KEY",), "is a secret"),
    ],
    ids=["no key", "two keys", "unknown key", "a block, not a key", "secret"],
)
def test_a_call_it_cannot_answer_is_usage_and_prints_nothing(
    tmp_path, monkeypatch, argv, said
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-never-shown")
    code, out, err = _run(_project(tmp_path, {}), *argv)
    assert (code, out) == (ExitCode.USAGE, ""), err
    assert said in err, err
    assert "sk-never-shown" not in err, err


@pytest.mark.parametrize(
    "manifest, said",
    [
        (None, "config/project.json"),
        ("{not json", "config/project.json"),
        ({"shell": {"formatter": 3}}, "shell.formatter is"),
    ],
    ids=["absent", "unreadable", "wrong type"],
)
def test_a_config_fault_is_config_and_prints_nothing(tmp_path, manifest, said):
    code, out, err = _run(_project(tmp_path, manifest), "shell.formatter")
    assert (code, out) == (ExitCode.CONFIG, ""), err
    assert said in err, err


def test_keel_s_own_config_answers_every_non_secret_row(monkeypatch):
    """Every row a shell script may name resolves against keel's own tree, so
    the key the error message invites is one the tool can print."""
    keys = [
        ".".join(k.path)
        for k in config_get.config_loader.KEYS
        if not k.secret and k.file is not None
    ]
    assert keys, "KEYS declares no file row -- a pass over zero items"
    for key in keys:
        code, out, err = _run(_ROOT, key)
        assert code == ExitCode.SUCCESS, (key, err)
        assert out.endswith("\n") and out.count("\n") == 1, (key, out)
