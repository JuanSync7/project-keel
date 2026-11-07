"""
title: Integration — the nested generated suite follows its shipped test recipe
kind: tests
layer: n/a
summary: Captures the generated-suite command without importing copier or rendering a project, and holds it to the shipped Makefile's worker-enabled test target and interpreter, with no outer make's flags, level or junit path reaching it.
"""

import ast
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="not a copier template — this is a generated project",
    ),
]


def test_nested_suite_delegates_to_the_shipped_worker_recipe():
    """The nested suite runs the shipped test target with its caller's Python,
    and none of an outer make's control variables or its junit path."""
    makefile = _ROOT / "Makefile"
    twin = _ROOT / "Makefile.jinja"
    shipped = twin if twin.is_file() else makefile
    recipes = re.findall(
        r"^test:[^\n]*\n((?:\t[^\n]*\n)+)",
        shipped.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert len(recipes) == 1, "expected one shipped test recipe"
    assert re.search(r"\$\(PY\) -m pytest\s+-n\s+auto\b", recipes[0]), recipes[0]

    source = _ROOT / "tests/integration/test_copier_generation.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_test_gate"
    ]
    assert len(functions) == 1, "expected one generated-suite runner"
    outer_list = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_OUTER_MAKE" for t in node.targets)
    ]
    assert len(outer_list) == 1, "expected one list of outer make variables"
    run = Mock()
    # What an outer `make -i test JUNIT_XML=...` hands its recipe's children:
    # with -i in MAKEFLAGS a nested make ignores a red suite and exits 0.
    outer = {
        "MAKEFLAGS": "i -- PY=/outer/python JUNIT_XML=outer.xml",
        "MFLAGS": "-i",
        "MAKELEVEL": "1",
        "MAKEOVERRIDES": "${-*-command-variables-*-}",
        "MAKEFILES": "outer.mk",
        "JUNIT_XML": "outer.xml",
    }
    arrival = Mock(return_value=dict(outer, on_arrival="sentinel"))
    namespace = {
        "os": os,
        "sys": sys,
        "subprocess": SimpleNamespace(run=run),
        "_on_arrival": arrival,
    }
    # Loading only the runner keeps optional copier imports and renders out of this test.
    exec(
        compile(
            ast.Module(body=outer_list + functions, type_ignores=[]),
            str(source),
            "exec",
        ),
        namespace,
    )
    project = _ROOT / "project-not-rendered"
    result = namespace["_test_gate"](project)

    run.assert_called_once()
    argv = run.call_args.args[0]
    assert argv == ["make", "test", "PY=" + sys.executable], (
        "the nested suite must delegate to the shipped worker recipe; got %r" % argv
    )
    assert run.call_args.kwargs["cwd"] == str(project)
    arrival.assert_called_once_with(dict(os.environ, PYTHONPATH="src:."))
    assert run.call_args.kwargs["env"] == {"on_arrival": "sentinel"}, (
        "an outer make's variables reached the nested make"
    )
    assert result is run.return_value
