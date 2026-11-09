"""
title: Integration — external lint waivers still match a diagnostic
kind: tests
layer: n/a
summary: Derives external codes from pyproject.toml and Python roots from Makefile, then fails each named waiver without a same-code Ruff diagnostic on its line. Unknown codes need a named custom gate; zero Ruff codes or zero waivers fails. Not for reflection policy or waiver reasons, which test_banned_api_gate.py owns.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # before 3.11; pytest itself depends on tomli there
    import tomli as tomllib

from scripts import config_loader
from scripts.child_env import build_child_env

import source_tree as st
from script_copy import copy_with_imports

_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration

# Ruff cannot judge these custom rules; their owning gate must ship as well.
_CUSTOM_GATE = "tests/integration/test_swallowed_error_gate.py"
_CUSTOM_GATES = dict.fromkeys(
    ("DROP001", "DROP002", "DROP003"),
    _CUSTOM_GATE,
)


def _run(root, argv, *, input_text=None):
    key = ("tests", "child_timeout_seconds")
    timeout = config_loader.resolve(
        config_loader.read(str(root)),
        config_loader.rows(key),
        config_loader.CONFIG_FILE,
    )[key]
    return subprocess.run(
        argv,
        cwd=root,
        input=input_text,
        capture_output=True,
        text=True,
        env=build_child_env(root=str(root)),
        timeout=timeout,
    )


def _ruff(root, *args):
    return _run(root, [sys.executable, "-m", "ruff", *args])


def stale_external_waivers(root):
    """Return file, line and code findings; refuse an unjudgeable policy or scope."""
    root = Path(root).resolve()
    policy = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    external = policy["tool"]["ruff"]["lint"]["external"]
    assert isinstance(external, list) and external, "external: zero codes"
    assert all(isinstance(code, str) and code for code in external), external

    rules = _ruff(root, "rule", "--all", "--output-format", "json")
    assert rules.returncode == 0, rules.stdout + rules.stderr
    known = {rule["code"] for rule in json.loads(rules.stdout)}
    for code in sorted(set(external) - known):
        owner = _CUSTOM_GATES.get(code)
        assert owner and (root / owner).is_file(), (
            "%s: unknown to Ruff and no named custom gate owns it" % code
        )
    codes = sorted(set(external) & known)
    assert codes, "external: zero Ruff codes to judge"

    # Let make expand wildcards and includes in this project, including pruned roots.
    scope = _run(
        root,
        [
            "make",
            "--no-print-directory",
            "-s",
            "-f",
            "Makefile",
            "-f",
            "-",
            "__keel_waiver_roots",
        ],
        input_text=(
            ".PHONY: __keel_waiver_roots\n"
            "__keel_waiver_roots:\n\t@printf '%s\\n' $(PY_ROOTS)\n"
        ),
    )
    assert scope.returncode == 0, scope.stdout + scope.stderr
    roots = scope.stdout.splitlines()
    assert roots and all(roots), "Makefile PY_ROOTS: zero roots"
    files = _ruff(root, "check", "--show-files", *roots)
    assert files.returncode == 0, files.stdout + files.stderr
    waivers = []
    for name in files.stdout.splitlines():
        path = Path(name).relative_to(root).as_posix()
        for line, (named, _reason) in st.noqa_reasons(root, path).items():
            waivers.extend((path, line, code) for code in codes if code in named)
    assert waivers, "external: zero Ruff waivers to judge"

    diagnostics = set()
    for code in codes:
        result = _ruff(
            root,
            "check",
            "--no-cache",
            "--select",
            code,
            "--ignore-noqa",
            "--output-format",
            "json",
            *roots,
        )
        assert result.returncode in (0, 1), result.stdout + result.stderr
        for diagnostic in json.loads(result.stdout):
            if diagnostic["code"] == code:
                path = Path(diagnostic["filename"]).relative_to(root).as_posix()
                diagnostics.add((path, diagnostic["location"]["row"], code))
    return [
        "%s:%d: stale external waiver %s" % waiver
        for waiver in sorted(set(waivers) - diagnostics)
    ]


def test_tree_has_no_stale_external_waivers():
    findings = stale_external_waivers(_ROOT)
    assert not findings, "\n".join(findings)


def _project(tmp_path, codes, text):
    root = tmp_path / "project"
    (root / "chosen").mkdir(parents=True)
    copy_with_imports(root, _ROOT, ["config/project.json"])
    (root / "pyproject.toml").write_text(
        "[tool.ruff.lint]\nexternal = %s\n" % json.dumps(codes), encoding="utf-8"
    )
    (root / "Makefile").write_text(
        "CODE_ROOTS := chosen absent\nPY_ROOTS := $(wildcard $(CODE_ROOTS))\n",
        encoding="utf-8",
    )
    (root / "chosen" / "probe.py").write_text(text, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "value = 1  # noqa: F401\n",
            ["chosen/probe.py:1: stale external waiver F401"],
        ),
        (
            "import os\nvalue = 1  # noqa: F401\n",
            ["chosen/probe.py:2: stale external waiver F401"],
        ),
        (
            "import os  # noqa: F401, S603\n",
            ["chosen/probe.py:1: stale external waiver S603"],
        ),
        ("import os  # noqa: F401 -- compatibility import\n", []),
    ],
)
def test_waivers_match_both_code_and_line_in_the_project_scope(
    tmp_path, text, expected
):
    root = _project(tmp_path, ["F401", "S603"], text)
    # A stale waiver outside PY_ROOTS must not expand this project's lint scope.
    (root / "outside.py").write_text("value = 1  # noqa: F401\n", encoding="utf-8")
    assert stale_external_waivers(root) == expected


@pytest.mark.parametrize(
    ("codes", "text", "message"),
    [
        ([], "value = 1\n", "zero codes"),
        (["F401"], "value = '# noqa: F401'\n", "zero Ruff waivers"),
        (["UNKNOWN999"], "value = 1\n", "UNKNOWN999.*no named custom gate"),
        (["DROP001"], "value = 1\n", "DROP001.*no named custom gate"),
    ],
)
def test_empty_or_unowned_policies_fail_loudly(tmp_path, codes, text, message):
    root = _project(tmp_path, codes, text)
    with pytest.raises(AssertionError, match=message):
        stale_external_waivers(root)


def test_custom_codes_require_the_owner_and_do_not_count_as_ruff_codes(tmp_path):
    root = _project(tmp_path, ["DROP001"], "value = 1\n")
    copy_with_imports(root, _ROOT, [_CUSTOM_GATE])
    with pytest.raises(AssertionError, match="zero Ruff codes"):
        stale_external_waivers(root)
    (root / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nexternal = ["F401", "DROP001"]\n', encoding="utf-8"
    )
    (root / "chosen" / "probe.py").write_text(
        "import os  # noqa: F401\nvalue = 1  # noqa: DROP001\n", encoding="utf-8"
    )
    assert stale_external_waivers(root) == []


def test_empty_make_scope_fails_loudly(tmp_path):
    root = _project(tmp_path, ["F401"], "import os  # noqa: F401\n")
    (root / "Makefile").write_text("PY_ROOTS :=\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="PY_ROOTS: zero roots"):
        stale_external_waivers(root)
