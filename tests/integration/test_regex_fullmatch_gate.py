"""
title: Integration — whole-value regex checks consume the entire input
kind: tests
layer: n/a
summary: Scans scripts/, src/, agents/ and models/ for match calls on literal dollar-terminated regexes, directly or through a named compiled pattern, regardless of MULTILINE flags. Synthetic modules prove the gate reports the unsafe forms and accepts fullmatch, prefix matches, escaped dollars and search/finditer scans. Dynamic patterns and cross-module bindings are outside this syntactic gate.
"""

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))

import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration

_ROOTS = ("scripts/", "src/", "agents/", "models/")


def _regex_names(tree):
    """Resolve re imports, including aliases, without importing judged code."""
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "re":
                    names[alias.asname or alias.name] = "re"
        elif isinstance(node, ast.ImportFrom) and node.module == "re":
            for alias in node.names:
                names[alias.asname or alias.name] = "re." + alias.name
    return names


def _name(node, names):
    if isinstance(node, ast.Name):
        return names.get(node.id, "")
    if isinstance(node, ast.Attribute):
        return _name(node.value, names) + "." + node.attr
    return ""


def _unsafe_pattern(call):
    """Whether a literal regex ends in an unescaped $, regardless of flags."""
    pattern = call.args[0] if call.args else None
    for keyword in call.keywords:
        if keyword.arg == "pattern":
            pattern = keyword.value
    if not isinstance(pattern, ast.Constant) or not isinstance(pattern.value, str):
        return False
    text = pattern.value
    if not text.endswith("$"):
        return False
    # An escaped dollar consumes a literal character, so it is no end anchor.
    slashes = len(text[:-1]) - len(text[:-1].rstrip("\\"))
    return not slashes % 2


def _match_lines(tree):
    """Unsafe match-call line numbers in one module's syntax tree."""
    names = _regex_names(tree)
    compiled = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if isinstance(value, ast.Call) and _name(value.func, names) == "re.compile":
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for target in targets:
                    if isinstance(target, ast.Name):
                        compiled[target.id] = _unsafe_pattern(value)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _name(node.func, names) == "re.match":
            if _unsafe_pattern(node):
                lines.append(node.lineno)
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "match":
            receiver = node.func.value
            if (isinstance(receiver, ast.Name) and compiled.get(receiver.id)) or (
                isinstance(receiver, ast.Call)
                and _name(receiver.func, names) == "re.compile"
                and _unsafe_pattern(receiver)
            ):
                lines.append(node.lineno)
    return sorted(lines)


def match_findings(root):
    """File:line findings for unsafe match calls in the owned source roots."""
    files = [path for path in st.python_files(root) if path.startswith(_ROOTS)]
    if not files:
        raise st.SourceTreeError("no Python source to judge -- zero items")
    return [
        "%s:%d: use fullmatch for a whole-value check ending in $" % (path, line)
        for path in files
        for line in _match_lines(st.parse(root, path))
    ]


def test_whole_value_checks_use_fullmatch():
    findings = match_findings(_ROOT)
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize(
    "source",
    [
        "import re\nTOKEN = re.compile(r'^word$')\nTOKEN.match(value)\n",
        "import re\nre.match(r'^word$', value)\n",
        "import re as rx\nrx.compile(r'^word$').match(value)\n",
        "from re import compile as regex\nTOKEN = regex(r'^word$')\nTOKEN.match(value)\n",
        "from re import match as start\nstart(pattern=r'^word$', string=value)\n",
        "import re\nTOKEN: object = re.compile(r'^word$', re.I)\nTOKEN.match(value)\n",
        "import re\nre.match(r'word\\\\$', value)\n",
        "import re\nTOKEN = re.compile(r'^word$', re.MULTILINE)\nTOKEN.match(value)\n",
        "import re\nre.match(r'^word$', value, flags=re.I | re.M)\n",
        "import re\nre.match(r'(?m)^word$', value)\n",
        "from re import match, M\nmatch(r'^word$', value, M)\n",
        "import re\nre.match(r'^word$', value, 8)\n",
    ],
)
def test_a_synthetic_module_with_an_unsafe_match_fails_the_gate(tmp_path, source):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "bad.py").write_text(source, encoding="utf-8")
    findings = match_findings(tmp_path)
    assert findings == [
        "scripts/bad.py:%d: use fullmatch for a whole-value check ending in $"
        % len(source.splitlines())
    ]


@pytest.mark.parametrize(
    "source",
    [
        "import re\nre.fullmatch(r'^word$', value)\n",
        "import re\nTOKEN = re.compile(r'^word$')\nTOKEN.fullmatch(value)\n",
        "import re\nre.match(r'^word', value)\n",
        "import re\nre.match(r'word\\$', value)\n",
        "import re\nre.search(r'^word$', value, re.M)\n",
        "import re\nre.compile(r'^word$', re.M).finditer(value)\n",
        "other.match(value)\n",
    ],
)
def test_full_matches_prefixes_and_multiline_scans_are_allowed(source):
    assert _match_lines(ast.parse(source)) == []


def test_an_empty_source_tree_cannot_pass(tmp_path):
    with pytest.raises(st.SourceTreeError, match="zero items"):
        match_findings(tmp_path)
