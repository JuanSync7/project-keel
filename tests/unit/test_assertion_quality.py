"""
title: Unit — tests/assertion_quality.py judges whether a test can fail
kind: tests
layer: n/a
summary: Plants assertion, lexical binding, collection, root and policy faults in temporary projects and checks the scanner findings and verdicts. Regressions cover bounded literal folding and false comparisons, entered or callable expectations, comprehension and walrus bindings, every reachable helper tautology, ellipsis handlers, pytest aliases and shadowing, dotted imports, inherited and nested tests, TestCase assertions, named policy errors, malformed AAD schemas and bounded module-cache eviction.
"""

import ast
import json
import runpy
import textwrap
from pathlib import Path

import config_loader
import pytest

import assertion_quality as aq
import source_tree as st

pytestmark = pytest.mark.unit

_TEST = "tests/test_case.py"
_ROOTS = ("tests",)
# lib/ is searched so a helper there resolves, and only the roots keep it out.
_SEARCH = ["tests/", "lib/"]

_HELPER_CONSTANT = """
def check(value):
    assert True
"""
_HELPER_REAL = """
def check(value):
    assert value == 2
"""


def _tree(tmp_path, files):
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config/project.json").write_text(
        json.dumps(
            {
                "tests": {
                    "cache_max_entries": config_loader.rows(
                        ("tests", "cache_max_entries")
                    )[0].default
                }
            }
        ),
        encoding="utf-8",
    )
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(tmp_path)


def _scan(tmp_path, files, depth=3, roots=_ROOTS):
    root = _tree(tmp_path, files)
    return aq.scan(root, aq.test_files(root, roots), roots, depth, _SEARCH)


# (row id, files, the kinds the judge reports for the one test in _TEST)
_ROWS = [
    ("no-assertion", {_TEST: "def test_a():\n    value = 1\n"}, [aq.NO_ASSERTION]),
    ("constant-true", {_TEST: "def test_a():\n    assert True\n"}, [aq.TAUTOLOGY]),
    ("constant-text", {_TEST: "def test_a():\n    assert 'text'\n"}, [aq.TAUTOLOGY]),
    ("constant-one", {_TEST: "def test_a():\n    assert 1\n"}, [aq.TAUTOLOGY]),
    (
        "tautology-name",
        {_TEST: "def test_a():\n    value = 1\n    assert value == value\n"},
        [aq.TAUTOLOGY],
    ),
    (
        "tautology-chain",
        {_TEST: "def test_a(obj):\n    assert obj.a.b is obj.a.b\n"},
        [aq.TAUTOLOGY],
    ),
    (
        "swallowed-pass",
        {
            _TEST: """
            def test_a():
                value = 2
                try:
                    value = int("x")
                except ValueError:
                    pass
                assert value == 2
            """
        },
        [aq.SWALLOWED],
    ),
    (
        "swallowed-continue",
        {
            _TEST: """
            def test_a():
                seen = []
                for text in ("1", "x"):
                    try:
                        seen.append(int(text))
                    except ValueError:
                        continue
                assert seen == [1]
            """
        },
        [aq.SWALLOWED],
    ),
    (
        "helper-asserts-a-constant",
        {_TEST: "def _check():\n    assert True\n\ndef test_a():\n    _check()\n"},
        [aq.TAUTOLOGY],
    ),
    (
        "imported-helper-asserts-a-constant",
        {
            "tests/helpers.py": _HELPER_CONSTANT,
            _TEST: "import helpers\n\ndef test_a():\n    helpers.check(2)\n",
        },
        [aq.TAUTOLOGY],
    ),
    (
        "helper-cycle-asserts-nothing",
        {
            _TEST: """
            def _a(n):
                _b(n)

            def _b(n):
                _a(n)

            def test_a():
                _a(1)
            """
        },
        [aq.NO_ASSERTION],
    ),
    (
        "helper-outside-the-roots",
        {
            "lib/helpers.py": _HELPER_REAL,
            _TEST: "import helpers\n\ndef test_a():\n    helpers.check(2)\n",
        },
        [aq.NO_ASSERTION],
    ),
    ("assert", {_TEST: "def test_a():\n    assert sum([1, 1]) == 2\n"}, []),
    (
        "falsy-constant-fails-a-branch",
        {_TEST: "def test_a(x):\n    if x:\n        assert False\n"},
        [],
    ),
    ("two-calls", {_TEST: "def test_a(f):\n    assert f(1) == f(1)\n"}, []),
    ("bare-isinstance", {_TEST: "def test_a():\n    assert isinstance(1, int)\n"}, []),
    (
        "raises-block",
        {
            _TEST: "import pytest\n\ndef test_a():\n    with pytest.raises(ValueError):\n        int('x')\n"
        },
        [],
    ),
    (
        "raises-call",
        {
            _TEST: "from pytest import raises\n\ndef test_a():\n    raises(ValueError, int, 'x')\n"
        },
        [],
    ),
    (
        "warns-block",
        {
            _TEST: "import pytest\n\ndef test_a(f):\n    with pytest.warns(UserWarning):\n        f()\n"
        },
        [],
    ),
    (
        "mock-assert",
        {_TEST: "def test_a(m):\n    m(1)\n    m.assert_called_once_with(1)\n"},
        [],
    ),
    (
        "helper-in-the-module",
        {_TEST: "def _check(v):\n    assert v == 2\n\ndef test_a():\n    _check(2)\n"},
        [],
    ),
    (
        "imported-module-helper",
        {
            "tests/helpers.py": _HELPER_REAL,
            _TEST: "import helpers\n\ndef test_a():\n    helpers.check(2)\n",
        },
        [],
    ),
    (
        "imported-name-helper",
        {
            "tests/helpers.py": _HELPER_REAL,
            _TEST: "from helpers import check as c\n\ndef test_a():\n    c(2)\n",
        },
        [],
    ),
    (
        "method-through-self",
        {
            _TEST: """
            class TestA:
                def _check(self, v):
                    assert v == 2

                def test_a(self):
                    self._check(2)
            """
        },
        [],
    ),
]


@pytest.mark.parametrize(
    "files, kinds", [r[1:] for r in _ROWS], ids=[r[0] for r in _ROWS]
)
def test_each_planted_fault_is_red_and_each_real_assertion_green(
    tmp_path, files, kinds
):
    count, findings = _scan(tmp_path, files)
    assert count == 1
    assert [f.kind for f in findings] == kinds


def test_a_finding_names_file_line_and_function(tmp_path):
    _count, (finding,) = _scan(
        tmp_path, {_TEST: "\n\nclass TestA:\n    def test_b(self):\n        pass\n"}
    )
    assert finding.node_id == "tests/test_case.py::TestA::test_b"
    assert str(finding).startswith(
        "tests/test_case.py:4: TestA::test_b: no assertion: "
    )


def _chain(links):
    """A test that reaches a real assertion *links* helper calls below it."""
    lines = ["def _h%d(v):\n    _h%d(v)\n" % (i, i + 1) for i in range(1, links)]
    lines.append("def _h%d(v):\n    assert v == 2\n" % links)
    lines.append("def test_a():\n    _h1(2)\n")
    return {_TEST: "\n".join(lines)}


def test_the_helper_walk_stops_at_the_configured_depth(tmp_path):
    assert _scan(tmp_path / "at", _chain(3), depth=3)[1] == []
    (finding,) = _scan(tmp_path / "past", _chain(4), depth=3)[1]
    assert finding.kind == aq.NO_ASSERTION and "3 deep" in finding.detail


def test_only_pytest_named_files_classes_and_functions_are_read(tmp_path):
    files = {
        _TEST: "class Helper:\n    def test_x(self):\n        pass\n\ndef check():\n    pass\n",
        "tests/helpers.py": "def test_y():\n    pass\n",
        "tests/sub/thing_test.py": "def test_z():\n    pass\n",
        "other/test_out.py": "def test_w():\n    pass\n",
    }
    count, findings = _scan(tmp_path, files)
    assert count == 1
    assert [f.node_id for f in findings] == ["tests/sub/thing_test.py::test_z"]


def _finding(test="test_a"):
    return aq.Finding(_TEST, 1, test, aq.NO_ASSERTION, "nothing asserts")


_GEN = "(self.assertEqual(value, 2) for value in values)"


@pytest.mark.parametrize(
    "body",
    [
        _GEN,
        "gen = " + _GEN,
        "bool(" + _GEN + ")",
        "iter(" + _GEN + ")",
        "next(it, " + _GEN + ")",
        "next(" + _GEN + ", *rest)",
        "dict(saved=" + _GEN + ")",
        "max(a, " + _GEN + ")",
        "try:\n    sum(" + _GEN + ', "")\nexcept TypeError:\n    recovered = True',
        "sum(" + _GEN + ", 0)",
        "max(" + _GEN + ", key=len)",
        "(item for item in " + _GEN + ")",
        "(_check(value) for value in values)",
        "[self.assertEqual(value, 2) for self in (dummy,)]",
        "self = other\nself.assertEqual(value, 2)",
        "with manager as self:\n    self.assertEqual(value, 2)",
        "try:\n    f()\nexcept ValueError as self:\n    self.assertEqual(value, 2)",
    ],
    ids=[
        "bare-generator",
        "bound-unused",
        "bool",
        "iter",
        "next-default",
        "next-starred-rest",
        "dict-keyword",
        "max-second",
        "sum-string-start",
        "sum-zero-start",
        "max-keyword",
        "unused-outer",
        "deferred-helper",
        "comprehension-self",
        "reassigned-self",
        "with-self",
        "except-self",
    ],
)
def test_cmp13_deferred_calls_and_rebound_receivers_count_as_nothing(tmp_path, body):
    source = (
        "import unittest\ndef _check(value):\n    assert value == 2\n"
        "class Checks(unittest.TestCase):\n    def test_a(self):\n"
        + textwrap.indent(body, "        ")
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


@pytest.mark.parametrize(
    "method, kinds",
    [
        (
            "@staticmethod\ndef test_a(self=None):\n    self.assertTrue(value)",
            [aq.NO_ASSERTION],
        ),
        ("def test_a(self):\n    case = self\n    case.assertEqual(value, 2)", []),
        ("def test_a(self):\n    (case := self)\n    case.assertTrue(value)", []),
        ("def test_a(self):\n    [c.assertEqual(value, 2) for c in (self,)]", []),
        ("def test_a(self):\n    for c in (self,):\n        c.assertTrue(value)", []),
        ("def test_a(case):\n    case.assertTrue(value)", []),
    ],
    ids=[
        "static-self-default",
        "assigned-case",
        "walrus-case",
        "comprehension-case",
        "for-case",
        "named-case",
    ],
)
def test_cmp13_receiver_regressions(tmp_path, method, kinds):
    source = "import unittest\nclass Checks(unittest.TestCase):\n" + textwrap.indent(
        method, "    "
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == kinds


@pytest.mark.parametrize(
    "body",
    [
        "all(" + _GEN + ")",
        "for item in " + _GEN + ":\n    seen = item",
        "[*" + _GEN + "]",
        "gen = " + _GEN + "\nlist(gen)",
        "next(" + _GEN + ", None)",
        "sum(" + _GEN + ")",
        "list(item for item in " + _GEN + ")",
        "(item for item in self.assertEqual(value, 2))",
    ],
    ids=[
        "all",
        "for",
        "star",
        "bound-list",
        "next-first",
        "sum-only",
        "consumed-outer",
        "first-iterable",
    ],
)
def test_cmp13_consumption_controls(tmp_path, body):
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n    def test_a(self):\n"
        + textwrap.indent(body, "        ")
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert findings == []


@pytest.mark.parametrize(
    "method",
    [
        "def test_a(self):\n    case = other\n    case.assertTrue(value)",
        "def test_a(self):\n    for c in ():\n        c.assertEqual(1, 2)",
        "def test_a(self):\n    [case.assertTrue(value) for case in (self, other)]",
        "def test_a(self):\n    case = self\n    case = other\n    case.assertTrue(value)",
        "def test_a(self):\n    case = self\n    case = self\n    case.assertTrue(value)",
        "@staticmethod\ndef test_a(case=None):\n    case.assertTrue(value)",
        "@classmethod\ndef test_a(cls):\n    cls.assertTrue(value)",
    ],
    ids=[
        "other",
        "empty-receiver-display",
        "mixed-display",
        "two-values",
        "two-same",
        "static-case-default",
        "class-method",
    ],
)
def test_cmp13_receiver_controls(tmp_path, method):
    source = "import unittest\nclass Checks(unittest.TestCase):\n" + textwrap.indent(
        method, "    "
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


@pytest.mark.parametrize(
    "body, kinds",
    [
        ("(pytest.fail('bad') for value in values)", [aq.NO_ASSERTION]),
        ("(m.assert_called_once() for value in values)", [aq.NO_ASSERTION]),
        ("(value for value in values if self.assertTrue(value))", [aq.NO_ASSERTION]),
        (
            "(value for value in values for item in self.assertTrue(value))",
            [aq.NO_ASSERTION],
        ),
        ("[value for value in " + _GEN + "]", []),
        ("{value for value in " + _GEN + "}", []),
        ("{value: value for value in " + _GEN + "}", []),
        ("gen = " + _GEN + "\ngen = other\nlist(gen)", [aq.NO_ASSERTION]),
        ("gen = " + _GEN + "\ngen = " + _GEN + "\nlist(gen)", [aq.NO_ASSERTION]),
        ("list(*(" + _GEN + ",))", [aq.NO_ASSERTION]),
        ("list(" + _GEN + ", **options)", [aq.NO_ASSERTION]),
        ("''.join(" + _GEN + ")", [aq.NO_ASSERTION]),
    ],
)
def test_generator_execution_boundaries(tmp_path, body, kinds):
    source = (
        "import unittest\nimport pytest\nclass Checks(unittest.TestCase):\n    def test_a(self):\n"
        + textwrap.indent(body, "        ")
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == kinds


def test_yield_from_in_a_consumed_helper(tmp_path):
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n"
        "    def delegated(self):\n        yield from " + _GEN + "\n"
        "    def test_a(self):\n        list(self.delegated())\n"
    )
    assert _scan(tmp_path, {_TEST: source}) == (1, [])


@pytest.mark.xfail(
    strict=True,
    reason="queued: a test that is itself a generator function is not run",
)
def test_known_limit_top_level_generator_test(tmp_path):
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n    def test_a(self):\n"
        "        yield from " + _GEN + "\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


@pytest.mark.parametrize(
    "body, signature, kinds",
    [
        ("drain(" + _GEN + ")", "self", []),
        ("drain(" + _GEN + ", None)", "self", []),
        ("drain(" + _GEN + ")", "self, drain", [aq.NO_ASSERTION]),
        ("drain = other\ndrain(" + _GEN + ")", "self", [aq.NO_ASSERTION]),
        ("from external import drain\ndrain(" + _GEN + ")", "self", [aq.NO_ASSERTION]),
        ("[drain(" + _GEN + ") for drain in funcs]", "self", [aq.NO_ASSERTION]),
        (
            "[drain(" + _GEN + ") for drain in funcs for drain in funcs]",
            "self",
            [aq.NO_ASSERTION],
        ),
        ("drain(" + _GEN + ", key=f)", "self", [aq.NO_ASSERTION]),
    ],
)
def test_consumers_come_from_policy_and_respect_bindings(
    tmp_path, body, signature, kinds
):
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n    def test_a("
        + signature
        + "):\n"
        + textwrap.indent(body, "        ")
    )
    count, findings = _scan(
        tmp_path,
        {
            _TEST: source,
            "config/project.json": json.dumps(
                {
                    "tests": {
                        "cache_max_entries": config_loader.rows(
                            ("tests", "cache_max_entries")
                        )[0].default
                    },
                    "test_quality": {"assertions": {"consumers": {"drain": "first"}}},
                }
            ),
        },
    )
    assert count == 1
    assert [f.kind for f in findings] == kinds


@pytest.mark.parametrize(
    "method, kinds",
    [
        ("def test_a(self=None):\n    self.assertTrue(value)", [aq.NO_ASSERTION]),
        (
            "@staticmethod\ndef test_a(self):\n    self.assertTrue(value)",
            [aq.NO_ASSERTION],
        ),
        (
            "@classmethod\ndef test_a(self):\n    self.assertTrue(value)",
            [aq.NO_ASSERTION],
        ),
        ("def test_a(self, /):\n    self.assertTrue(value)", []),
        ("def test_a(self, arg=None):\n    self.assertTrue(value)", []),
        (
            "def test_a(self):\n    case = self\n    with manager as case:\n        case.assertTrue(value)",
            [aq.NO_ASSERTION],
        ),
        (
            "def test_a(self):\n    case = self\n    try:\n        f()\n    except ValueError as case:\n        case.assertTrue(value)",
            [aq.NO_ASSERTION],
        ),
        (
            "def test_a(self):\n    case = self\n    import external as case\n    case.assertTrue(value)",
            [aq.NO_ASSERTION],
        ),
        (
            "def test_a(self, case):\n    case = self\n    case.assertTrue(value)",
            [aq.NO_ASSERTION],
        ),
        (
            "def test_a(self):\n    for case in values:\n        case.assertTrue(value)",
            [aq.NO_ASSERTION],
        ),
        (
            "def test_a(self):\n    for case in [self]:\n        case.assertTrue(value)",
            [],
        ),
        ("def test_a(self):\n    [case.assertTrue(value) for case in [self]]", []),
        (
            "def test_a(self):\n    [None for c in (self,) if (case := c)]\n    case.assertTrue(value)",
            [],
        ),
        (
            "def test_a(self):\n    def inner(self):\n        self.assertTrue(value)\n    inner(other)",
            [aq.NO_ASSERTION],
        ),
    ],
)
def test_receiver_binding_boundaries(tmp_path, method, kinds):
    source = "import unittest\nclass Checks(unittest.TestCase):\n" + textwrap.indent(
        method, "    "
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == kinds


@pytest.mark.parametrize(
    "body, kinds",
    [
        pytest.param(
            "case = self\ndef replace():\n    nonlocal case\n    case = stub\n"
            "replace()\ncase.assertTrue(False)",
            [aq.NO_ASSERTION],
            id="nonlocal-receiver",
        ),
        pytest.param(
            "gen = (self.assertTrue(v) for v in [False])\n"
            "def replace():\n    nonlocal gen\n    gen = iter(())\nreplace()\nlist(gen)",
            [aq.NO_ASSERTION],
            id="nonlocal-generator",
        ),
        pytest.param(
            "global case\ncase = self\ndef replace():\n    global case\n"
            "    case = stub\nreplace()\ncase.assertTrue(False)",
            [aq.NO_ASSERTION],
            id="global-receiver",
        ),
        pytest.param(
            "global gen\ngen = (self.assertTrue(v) for v in [False])\n"
            "def replace():\n    global gen\n    gen = iter(())\nreplace()\nlist(gen)",
            [aq.NO_ASSERTION],
            id="global-generator",
        ),
        pytest.param(
            "case = self\ndel case\ncase.assertTrue(value)",
            [aq.NO_ASSERTION],
            id="delete-receiver",
        ),
        pytest.param(
            "gen = (self.assertTrue(v) for v in [False])\ndel gen\nlist(gen)",
            [aq.NO_ASSERTION],
            id="delete-generator",
        ),
        pytest.param(
            "case = self\ndef nested(arg=(case := stub)):\n    return arg\n"
            "case.assertTrue(value)",
            [aq.NO_ASSERTION],
            id="function-default-binding",
        ),
        pytest.param(
            "case = self\nnested = lambda arg=(case := stub): arg\ncase.assertTrue(value)",
            [aq.NO_ASSERTION],
            id="lambda-default-binding",
        ),
        pytest.param(
            "case = self\ndef read():\n    return case\nread()\ncase.assertTrue(value)",
            [],
            id="nested-read",
        ),
        pytest.param(
            "case = self\nother = None\ndef replace():\n    nonlocal other\n"
            "    other = stub\nreplace()\ncase.assertTrue(value)",
            [],
            id="different-nonlocal",
        ),
        pytest.param(
            "gen = (self.assertTrue(v) for v in [False])\n"
            "def read():\n    return gen\nread()\nlist(gen)",
            [],
            id="generator-nested-read",
        ),
        pytest.param(
            "gen = (self.assertTrue(v) for v in [False])\nother = None\n"
            "def replace():\n    nonlocal other\n    other = stub\nreplace()\nlist(gen)",
            [],
            id="generator-different-nonlocal",
        ),
    ],
)
def test_fix1_binding_forms(tmp_path, body, kinds):
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n    def test_a(self):\n"
        + textwrap.indent(body, "        ")
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == kinds


@pytest.mark.parametrize(
    "module, body, consumers, kinds",
    [
        pytest.param(
            "def drain(it):\n    return tuple(it)\n",
            "drain(" + _GEN + ")",
            {"drain": "only"},
            [],
            id="module-def",
        ),
        pytest.param(
            "from lib import drain\n",
            "drain(" + _GEN + ")",
            {"drain": "only"},
            [],
            id="module-import",
        ),
        pytest.param(
            "drain = make()\n",
            "drain(" + _GEN + ")",
            {"drain": "only"},
            [aq.NO_ASSERTION],
            id="module-assignment",
        ),
        pytest.param(
            "def drain(it):\n    return tuple(it)\ndrain = other\n",
            "drain(" + _GEN + ")",
            {"drain": "only"},
            [aq.NO_ASSERTION],
            id="module-second-binding",
        ),
        pytest.param(
            "def all(gen):\n    return True\n",
            "all(" + _GEN + ")",
            {"all": "only"},
            [aq.NO_ASSERTION],
            id="builtin-def-shadow",
        ),
        pytest.param(
            "from lib import list\n",
            "list(" + _GEN + ")",
            {"list": "only"},
            [aq.NO_ASSERTION],
            id="builtin-import-shadow",
        ),
        pytest.param(
            "def drain(it):\n    return tuple(it)\n",
            "drain(" + _GEN + ")",
            {},
            [aq.NO_ASSERTION],
            id="unlisted-function",
        ),
        pytest.param("", "all(" + _GEN + ")", {"all": "only"}, [], id="builtin-all"),
        pytest.param("", "list(" + _GEN + ")", {"list": "only"}, [], id="builtin-list"),
        pytest.param(
            "def drain(it):\n    return tuple(it)\n",
            "def replace():\n    global drain\n    drain = other\n"
            "replace()\ndrain(" + _GEN + ")",
            {"drain": "only"},
            [aq.NO_ASSERTION],
            id="global-module-second-binding",
        ),
        pytest.param(
            "",
            "def replace():\n    global all\n    all = other\n"
            "replace()\nall(" + _GEN + ")",
            {"all": "only"},
            [aq.NO_ASSERTION],
            id="global-builtin-binding",
        ),
        pytest.param(
            "def drain(it):\n    return tuple(it)\n",
            "drain = other\ndrain(" + _GEN + ")",
            {"drain": "only"},
            [aq.NO_ASSERTION],
            id="local-binding",
        ),
    ],
)
def test_fix1_module_consumers(tmp_path, module, body, consumers, kinds):
    source = module + (
        "import unittest\nclass Checks(unittest.TestCase):\n    def test_a(self):\n"
        + textwrap.indent(body, "        ")
    )
    count, findings = _scan(
        tmp_path,
        {
            _TEST: source,
            "config/project.json": json.dumps(
                {
                    "tests": {"cache_max_entries": 256},
                    "test_quality": {"assertions": {"consumers": consumers}},
                }
            ),
        },
    )
    assert count == 1
    assert [f.kind for f in findings] == kinds


def test_fix1_scan_uses_passed_policy(tmp_path):
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n    def test_a(self):\n"
        "        drain(self.assertTrue(v) for v in [False])\n"
    )
    root = _tree(tmp_path, {_TEST: source})
    settings = aq.Policy(_ROOTS, 3, {}, {"drain": "only"})
    # A scan that rereads consumers instead of using Policy must refuse this.
    Path(root, "config/project.json").write_text(
        json.dumps(
            {
                "tests": {"cache_max_entries": 256},
                "test_quality": {"assertions": {"consumers": []}},
            }
        ),
        encoding="utf-8",
    )
    assert aq.scan(
        root, [_TEST], settings.roots, settings.helper_depth, _SEARCH, settings=settings
    ) == (1, [])


@pytest.mark.parametrize(
    "generator",
    [
        pytest.param("self.assertTrue(v) async for v in xs", id="async-for"),
        pytest.param("self.assertTrue(await value(v)) for v in xs", id="await"),
    ],
)
def test_fix1_sync_consumer_rejects_async_generator(tmp_path, generator):
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n    async def test_a(self):\n"
        "        list(" + generator + ")\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


def test_fix1_async_iteration_consumes_async_generator(tmp_path):
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n    async def test_a(self):\n"
        "        gen = (self.assertTrue(v) async for v in xs)\n"
        "        async for item in gen:\n            seen = item\n"
    )
    assert _scan(tmp_path, {_TEST: source}) == (1, [])


@pytest.mark.parametrize("case", ["pytest", "TestCase"])
@pytest.mark.parametrize(
    "consumer",
    [
        pytest.param("async for v in gen:\n    seen = v", id="async-for"),
        pytest.param("[v async for v in gen]", id="async-comprehension"),
    ],
)
def test_async_consumer_rejects_sync_generator(tmp_path, case, consumer):
    assertion = "pytest.fail('x')" if case == "pytest" else "self.fail('x')"
    body = (
        "gen = ("
        + assertion
        + " for x in [1])\ntry:\n"
        + textwrap.indent(consumer, "    ")
        + "\nexcept TypeError:\n    note = 1\n"
    )
    source = "import pytest\n" + (
        "async def test_a():\n" + textwrap.indent(body, "    ")
        if case == "pytest"
        else "import unittest\nclass Checks(unittest.TestCase):\n"
        "    async def test_a(self):\n" + textwrap.indent(body, "        ")
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


@pytest.mark.parametrize(
    "generator, kinds",
    [
        pytest.param("_check(x) for x in await data()", [], id="await-first-iterable"),
        pytest.param(
            "_check(x) for x in [1] if (lambda: (await value(y) for y in [1]))",
            [],
            id="await-nested-lambda",
        ),
        pytest.param(
            "_check(x) for x in [1] if (await value(y) for y in [1])",
            [],
            id="await-nested-generator-body",
        ),
        pytest.param(
            "_check(x) for x in [1] if (lambda y=await value(x): y)",
            [aq.NO_ASSERTION],
            id="await-lambda-default",
        ),
        pytest.param(
            "_check(x) for x in [1] if [y async for y in data()]",
            [aq.NO_ASSERTION],
            id="nested-async-comprehension",
        ),
        pytest.param(
            "_check(x) for x in [1] for y in await data()",
            [aq.NO_ASSERTION],
            id="await-later-iterable",
        ),
        pytest.param(
            "_check(x) for x in [1] if await value(x)",
            [aq.NO_ASSERTION],
            id="await-condition",
        ),
    ],
)
def test_generator_asyncness_uses_its_execution_scope(tmp_path, generator, kinds):
    source = (
        "def _check(x):\n    assert x == 1\n"
        "async def test_a():\n    list(" + generator + ")\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == kinds


def test_verdict_fails_a_run_over_zero_tests():
    (line,) = aq.verdict(0, [], {}, _ROOTS)
    assert "no test function was read under tests" in line


def test_verdict_names_an_unexcused_finding_and_lets_an_excused_one_through():
    assert aq.verdict(1, [_finding()], {}, _ROOTS) == [str(_finding())]
    assert (
        aq.verdict(1, [_finding()], {_finding().node_id: "returns None"}, _ROOTS) == []
    )


def test_verdict_fails_a_stale_excuse():
    (line,) = aq.verdict(1, [], {"tests/test_case.py::test_gone": "r"}, _ROOTS)
    assert line.startswith("tests/test_case.py::test_gone: stale: ")


def _config(tmp_path, block):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"test_quality": {"assertions": block}}), encoding="utf-8"
    )
    return str(tmp_path)


def test_policy_reads_the_four_keys(tmp_path):
    block = {
        "roots": ["tests/unit"],
        "helper_depth": 2,
        "exempt": {"tests/unit/test_a.py::test_b": "r"},
        "consumers": {"drain": "first"},
    }
    assert aq.policy(_config(tmp_path, block)) == aq.Policy(
        ("tests/unit",), 2, {"tests/unit/test_a.py::test_b": "r"}, {"drain": "first"}
    )


def test_policy_takes_the_defaults_and_says_so(tmp_path, capsys):
    assert aq.policy(_config(tmp_path, {})) == aq.Policy(
        ("tests",), 3, {}, config_loader.rows(aq.CONSUMERS)[0].default
    )
    assert (
        "[using default] test_quality.assertions.helper_depth"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize(
    "key, value",
    [
        ("helper_depth", 0),
        ("roots", []),
        ("roots", ["../tests"]),
        ("exempt", {"tests/test_a.py::test_b": " "}),
        ("exempt", {"tests/test_a.py": "r"}),
        ("exempt", {"tests/test_a.py::test_b[1]": "r"}),
        ("consumers", []),
        ("consumers", {"module.drain": "only"}),
        ("consumers", {"class": "only"}),
        ("consumers", {"drain": "second"}),
        ("consumers", {"drain": []}),
    ],
)
def test_policy_refuses_a_bad_value_naming_the_key(tmp_path, key, value):
    with pytest.raises(
        config_loader.ConfigError, match="test_quality.assertions." + key
    ):
        aq.policy(_config(tmp_path, {key: value}))


@pytest.mark.parametrize(
    "expression",
    [
        "x is x is x",
        "True",
        "1",
        "'message'",
        "x == y == y",
        "x <= x < y",
        "a[0] == a[0]",
        "a[1:] >= a[1:]",
        "(True, 'msg')",
        "(x, 'msg')",
        "[x]",
        "{x}",
        "{'key': x}",
        "True or y",
        "y or True",
        "(False and x) or True",
    ],
)
def test_statically_true_expressions_are_tautologies(tmp_path, expression):
    count, findings = _scan(
        tmp_path, {_TEST: f"def test_a(x, y, a):\n    assert {expression}\n"}
    )
    assert count == 1
    assert [finding.kind for finding in findings] == [aq.TAUTOLOGY]


@pytest.mark.parametrize("expression", ["x or False", "True and x", "[]", "f() == f()"])
def test_unknown_or_false_truth_does_not_make_a_tautology(tmp_path, expression):
    assert (
        _scan(tmp_path, {_TEST: f"def test_a(x, f):\n    assert {expression}\n"})[1]
        == []
    )


def test_a_real_assertion_does_not_hide_a_constant_tautology(tmp_path):
    count, findings = _scan(
        tmp_path, {_TEST: "def test_a(value):\n    assert True\n    assert value\n"}
    )
    assert count == 1
    assert [finding.kind for finding in findings] == [aq.TAUTOLOGY]


@pytest.mark.parametrize(
    "source, helpers, kinds",
    [
        (
            "class Thing:\n    def raises(self, error):\n        pass\ndef test_a():\n    Thing().raises(Exception)\n",
            {},
            [aq.NO_ASSERTION],
        ),
        (
            "def raises(error):\n    pass\ndef test_a():\n    raises(Exception)\n",
            {},
            [aq.NO_ASSERTION],
        ),
        (
            "from pytest import raises as expect\ndef test_a():\n    with expect(ValueError):\n        int('x')\n",
            {},
            [],
        ),
        ("import pytest as pt\ndef test_a():\n    pt.fail('must fail')\n", {}, []),
        (
            "def test_a():\n    from pytest import warns as expect\n    expect(UserWarning, f)\n",
            {},
            [],
        ),
        (
            "from pytest import raises\ndef test_a(raises):\n    raises(Exception)\n",
            {},
            [aq.NO_ASSERTION],
        ),
        (
            "import pytest\ndef test_a():\n    pytest = thing\n    pytest.raises(Exception)\n",
            {},
            [aq.NO_ASSERTION],
        ),
        (
            "from empty import h\ndef unrelated():\n    from real import h\ndef test_a():\n    h()\n",
            {
                "tests/empty.py": "def h():\n    pass\n",
                "tests/real.py": "def h():\n    assert value\n",
            },
            [aq.NO_ASSERTION],
        ),
        (
            "from empty import h\ndef test_a():\n    from real import h\n    h()\n",
            {
                "tests/empty.py": "def h():\n    pass\n",
                "tests/real.py": "def h():\n    assert value\n",
            },
            [],
        ),
        (
            "import pkg.m\ndef test_a():\n    pkg.m.h()\n",
            {
                "tests/pkg/__init__.py": "",
                "tests/pkg/m.py": "def h():\n    assert value\n",
            },
            [],
        ),
        (
            "import pkg.m as m\ndef test_a():\n    m.h()\n",
            {
                "tests/pkg/__init__.py": "",
                "tests/pkg/m.py": "def h():\n    assert value\n",
            },
            [],
        ),
        (
            "import pkg.m\ndef test_a(pkg):\n    pkg.m.h()\n",
            {
                "tests/pkg/__init__.py": "",
                "tests/pkg/m.py": "def h():\n    assert value\n",
            },
            [aq.NO_ASSERTION],
        ),
        (
            "from real import h\nfrom external import h\ndef test_a():\n    h()\n",
            {"tests/real.py": "def h():\n    assert value\n"},
            [aq.NO_ASSERTION],
        ),
        (
            "def test_a(pytest):\n    import pytest\n    pytest.raises(ValueError, f)\n",
            {},
            [],
        ),
    ],
)
def test_calls_follow_the_callers_bindings(tmp_path, source, helpers, kinds):
    count, findings = _scan(tmp_path, {_TEST: source, **helpers})
    assert count == 1
    assert [finding.kind for finding in findings] == kinds


def test_module_import_bindings_exclude_other_function_scopes(tmp_path):
    root = _tree(
        tmp_path,
        {
            _TEST: "from empty import h\ndef unrelated():\n    from real import h\n",
            "tests/empty.py": "",
            "tests/real.py": "",
        },
    )
    assert st.bindings(root, _TEST, st.parse(root, _TEST), _SEARCH)["h"] == (
        "tests/empty.py",
        "h",
    )


@pytest.mark.parametrize(
    "source, node_id, kinds",
    [
        ("if enabled:\n    def test_a():\n        pass\n", "test_a", [aq.NO_ASSERTION]),
        (
            "try:\n    def test_a():\n        pass\nexcept Error:\n    pass\n",
            "test_a",
            [aq.NO_ASSERTION],
        ),
        (
            "class Base:\n    def test_a(self):\n        pass\nclass TestChild(Base):\n    pass\n",
            "TestChild::test_a",
            [aq.NO_ASSERTION],
        ),
        (
            "from unittest import TestCase as Case\nclass Checks(Case):\n    def test_a(self):\n        pass\n",
            "Checks::test_a",
            [aq.NO_ASSERTION],
        ),
        (
            "import unittest as ut\nclass Base(ut.TestCase):\n    pass\nclass Checks(Base):\n    def test_a(self):\n        pass\n",
            "Checks::test_a",
            [aq.NO_ASSERTION],
        ),
        (
            "class TestOuter:\n    class TestInner:\n        def h(self):\n            assert value\n        def test_a(self):\n            self.h()\n",
            "TestOuter::TestInner::test_a",
            [],
        ),
        (
            "class Base:\n    def h(self):\n        assert value\n    def test_a(self):\n        self.h()\nclass TestChild(Base):\n    pass\n",
            "TestChild::test_a",
            [],
        ),
        (
            "class Base:\n    def h(self):\n        assert value\n    def test_a(self):\n        self.h()\nclass Left(Base):\n    pass\nclass Right(Base):\n    def h(self):\n        pass\nclass TestChild(Left, Right):\n    pass\n",
            "TestChild::test_a",
            [aq.NO_ASSERTION],
        ),
    ],
)
def test_collection_and_helpers_follow_pytest_shapes(tmp_path, source, node_id, kinds):
    count, findings = _scan(
        tmp_path, {_TEST: source + "\ndef test_companion():\n    assert value\n"}
    )
    assert count == 2
    assert [(f.test, f.kind) for f in findings] == [(node_id, kind) for kind in kinds]


@pytest.mark.parametrize(
    "classes",
    [
        "import unittest\nclass Checks(unittest.TestCase):",
        "import unittest as ut\nclass Checks(ut.TestCase):",
        "from unittest import TestCase as Case\nclass Checks(Case):",
        "import unittest\nCase = unittest.TestCase\nAlias = Case\nclass Checks(Alias):",
        "import unittest\nclass Base(unittest.TestCase):\n    pass\nclass Checks(Base):",
    ],
)
@pytest.mark.parametrize(
    "body",
    [
        "self.assertEqual(1, f())",
        "self.assertTrue(f())",
        "self.assertFalse(f())",
        "self.assertIsInstance(f(), int)",
        "self.fail('unexpected branch')",
        "self.assertRaises(ValueError, f)",
        "with self.assertRaises(ValueError):\n    f()",
        "with self.assertRaisesRegex(ValueError, 'bad'):\n    f()",
        "with self.assertWarns(UserWarning):\n    f()",
        "with self.assertWarnsRegex(UserWarning, 'bad'):\n    f()",
        "with self.assertLogs('app'):\n    f()",
    ],
)
def test_unittest_assertions_count_through_aliases_and_bases(tmp_path, classes, body):
    source = classes + "\n    def test_a(self):\n" + textwrap.indent(body, "        ")
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert findings == []


@pytest.mark.parametrize(
    "classes, body",
    [
        ("import unittest\nclass Checks(unittest.TestCase):", "f()"),
        ("class TestChecks:", "self.assertEqual(1, f())"),
        ("class TestChecks:", "self.fail('bad')"),
        ("import unittest\nclass Checks(unittest.TestCase):", "self.assertion(f())"),
        (
            "import unittest\nclass Checks(unittest.TestCase):",
            "other.assertEqual(1, f())",
        ),
        (
            "class TestCase:\n    pass\nclass TestChecks(TestCase):",
            "self.assertTrue(f())",
        ),
    ],
)
def test_unittest_assertion_names_need_a_testcase_receiver(tmp_path, classes, body):
    source = classes + "\n    def test_a(self):\n        " + body
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


@pytest.mark.parametrize(
    "call, kinds",
    [
        ("assertTrue(True)", [aq.TAUTOLOGY]),
        ("assertTrue(x or True)", [aq.TAUTOLOGY]),
        ("assertFalse(False)", [aq.TAUTOLOGY]),
        ("assertEqual(x, x)", [aq.TAUTOLOGY]),
        ("assertEqual(a[0], a[0])", [aq.TAUTOLOGY]),
        ("assertEqual(x, x, msg='same')", [aq.TAUTOLOGY]),
        ("assertTrue(False)", []),
        ("assertFalse(True)", []),
        ("assertEqual(f(), f())", []),
        ("assertEqual(1, f())", []),
    ],
)
def test_unittest_simple_assertions_use_the_expression_judge(tmp_path, call, kinds):
    count, findings = _scan(
        tmp_path,
        {
            _TEST: "import unittest\nclass Checks(unittest.TestCase):\n    def test_a(self):\n        self."
            + call
        },
    )
    assert count == 1
    assert [f.kind for f in findings] == kinds
    assert all(f.line == 4 for f in findings)


@pytest.mark.parametrize(
    "call, kinds", [("assertEqual(1, f())", []), ("assertTrue(True)", [aq.TAUTOLOGY])]
)
def test_unittest_helper_assertions_keep_the_class_context(tmp_path, call, kinds):
    count, findings = _scan(
        tmp_path,
        {
            _TEST: "import unittest\nclass Base(unittest.TestCase):\n    def check(self):\n        self."
            + call
            + "\nclass Checks(Base):\n    def test_a(self):\n        self.check()\n"
        },
    )
    assert count == 1
    assert [f.kind for f in findings] == kinds


@pytest.mark.parametrize("root_name, create", [("missing", False), ("empty", True)])
def test_each_configured_root_must_supply_test_files(tmp_path, root_name, create):
    root = _tree(tmp_path, {_TEST: "def test_a():\n    assert value\n"})
    if create:
        (tmp_path / root_name).mkdir()
    with pytest.raises(st.SourceTreeError, match=root_name):
        aq.test_files(root, ("tests", root_name))


@pytest.mark.parametrize(
    "block",
    [{"helper_depth": value} for value in (0, -1, "3", True)]
    + [{"exempt": {"tests/test_a.py::test_b": " "}}],
)
def test_config_fault_raises_the_gates_error_with_the_key(tmp_path, monkeypatch, block):
    gate = runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "integration/test_assertion_quality_gate.py"
        )
    )
    check = gate["test_every_test_function_shows_it_can_fail"]
    monkeypatch.setitem(check.__globals__, "_ROOT", Path(_config(tmp_path, block)))
    with pytest.raises(st.SourceTreeError) as caught:
        check()
    key = "test_quality.assertions." + next(iter(block))
    assert key in str(caught.value)
    assert isinstance(caught.value.__cause__, config_loader.ConfigError)
    assert str(caught.value) == "; ".join(caught.value.__cause__.lines)


@pytest.mark.parametrize(
    "schema, instance", [({"minLength": -1}, "ok"), ({"required": "name"}, {"name": 1})]
)
def test_aad_conformance_checks_the_schema_itself(
    tmp_path, monkeypatch, schema, instance
):
    gate = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "integration/test_aad_conformance.py")
    )
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    check = gate["test_descriptor_validates_against_committed_schema"]
    monkeypatch.setitem(check.__globals__, "_SCHEMA_PATH", path)
    jsonschema = gate["optional_deps"].importorskip("jsonschema", extra="dev")
    with pytest.raises(jsonschema.SchemaError):
        check(instance)


def test_module_cache_evicts_at_the_configured_limit(tmp_path, monkeypatch):
    root = _tree(
        tmp_path,
        {
            "tests/test_first.py": "from helpers import check\ndef test_first():\n    check(2)\n",
            "tests/test_second.py": "from helpers import check\ndef test_second():\n    check(2)\n",
            "tests/helpers.py": _HELPER_REAL,
        },
    )
    (tmp_path / "config/project.json").write_text(
        json.dumps({"tests": {"cache_max_entries": 1}}), encoding="utf-8"
    )
    parsed = []
    parse = st.parse

    def record(root, path):
        parsed.append(path)
        return parse(root, path)

    monkeypatch.setattr(st, "parse", record)
    assert aq.scan(root, aq.test_files(root, _ROOTS), _ROOTS, 3, _SEARCH) == (2, [])
    assert parsed.count("tests/helpers.py") == 2


@pytest.mark.parametrize(
    "body",
    [
        "pytest.raises(ValueError)",
        "pytest.warns(UserWarning)",
        "expect(ValueError, match='bad')",
        "saved = pytest.raises(ValueError)",
        "consume(pytest.warns(UserWarning))",
        "with consume(pytest.raises(ValueError)):\n    f()",
        "self.assertRaises(ValueError)",
        "self.assertRaisesRegex(ValueError, 'bad')",
        "self.assertWarns(UserWarning)",
        "self.assertWarnsRegex(UserWarning, 'bad')",
        "self.assertLogs('app', level='INFO')",
        "self.assertNoLogs('app')",
    ],
)
def test_expectation_construction_checks_nothing(tmp_path, body):
    source = (
        "import pytest\nfrom pytest import raises as expect\nimport unittest\n"
        "class Checks(unittest.TestCase):\n    def test_a(self):\n"
        + textwrap.indent(body, "        ")
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


@pytest.mark.parametrize(
    "body",
    [
        "pytest.raises(ValueError, int, 'x')",
        "pytest.warns(UserWarning, f)",
        "expect(ValueError, f, match='bad')",
        "with expect(ValueError), pytest.warns(UserWarning):\n    f()",
        "self.assertRaises(ValueError, f)",
        "self.assertRaisesRegex(ValueError, 'bad', f)",
        "self.assertWarns(UserWarning, f)",
        "self.assertWarnsRegex(UserWarning, 'bad', f)",
        "with self.assertNoLogs('app'):\n    f()",
    ],
)
def test_entered_or_callable_expectations_check_something(tmp_path, body):
    source = (
        "import pytest\nfrom pytest import raises as expect\nimport unittest\n"
        "class Checks(unittest.TestCase):\n    def test_a(self):\n"
        + textwrap.indent(body, "        ")
    )
    assert _scan(tmp_path, {_TEST: source}) == (1, [])


@pytest.mark.parametrize(
    "expression", ["x in x", "a[0] in a[0]", "x.items in x.items", "x in x in x"]
)
def test_identical_membership_operands_are_not_reflexive(tmp_path, expression):
    source = f"def test_a(x, a):\n    assert {expression}\n"
    assert _scan(tmp_path, {_TEST: source}) == (1, [])


@pytest.mark.parametrize(
    "comprehension",
    [
        "[pytest for pytest in ()]",
        "{pytest for pytest in ()}",
        "{pytest: pytest for pytest in ()}",
        "(pytest for pytest in ())",
        "[item for (pytest, item) in ()]",
        "[item for item in () for pytest in ()]",
        "[[pytest for pytest in ()] for item in ()]",
    ],
)
def test_comprehension_targets_do_not_hide_outer_imports(tmp_path, comprehension):
    source = (
        "import pytest\ndef test_a():\n    "
        + comprehension
        + "\n    with pytest.raises(ValueError):\n        int('x')\n"
    )
    assert _scan(tmp_path, {_TEST: source}) == (1, [])


@pytest.mark.parametrize(
    "comprehension",
    [
        "[(pytest := item) for item in ()]",
        "{(pytest := item) for item in ()}",
        "{item: (pytest := item) for item in ()}",
        "((pytest := item) for item in ())",
        "[[(pytest := item) for item in ()] for other in ()]",
    ],
)
def test_comprehension_walrus_still_hides_outer_imports(tmp_path, comprehension):
    source = (
        "import pytest\ndef test_a():\n    "
        + comprehension
        + "\n    with pytest.raises(ValueError):\n        int('x')\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


@pytest.mark.parametrize(
    "comprehension",
    [
        "[check(x) for x in (1, 2)]",
        "{check(x) for x in (1, 2)}",
        "{x: check(x) for x in (1, 2)}",
        "{check(x): x for x in (1, 2)}",
        "list(check(x) for x in (1, 2))",
        "[x for x in (1, 2) if check(x)]",
        "[y for x in (1, 2) for y in check(x)]",
        "[[check(x) for x in (1, 2)] for _ in (1,)]",
    ],
)
def test_a_helper_called_inside_a_comprehension_still_asserts(tmp_path, comprehension):
    # A comprehension's own scope holds its targets, but its body runs as part
    # of the test, so a helper it calls asserts for the test.
    source = (
        "def check(x):\n    assert x > 0\ndef test_a():\n    " + comprehension + "\n"
    )
    assert _scan(tmp_path, {_TEST: source}) == (1, [])


@pytest.mark.parametrize(
    "comprehension",
    [
        "[check(1) for check in (print,)]",
        "[y for check in (print,) for y in check(1)]",
        "[x for check in (print,) for x in (1,) if check(x)]",
        "{check(1): None for check in (print,)}",
        "[[check(1) for _ in (1,)] for check in (print,)]",
        "[[x for x in check(1)] for check in (print,)]",
        "[check.attr(1) for check in (print,)]",
        "{check(1) for check in (print,)}",
        "list(check(1) for check in (print,))",
        "[check(1) for (_, *check) in ((0, print),)]",
        "[None for x in (0,) if check(x) for check in (print,)]",
        "[None for x in (0,) for y in check(x) for check in (print,)]",
    ],
)
def test_a_call_through_a_name_the_comprehension_binds_never_reaches_the_helper(
    tmp_path, comprehension
):
    source = _HELPER_REAL + "def test_a():\n    " + comprehension + "\n"
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


@pytest.mark.parametrize(
    "comprehension",
    [
        "[None for check in check(2)]",
        "[None for sink[check(2)] in (0,)]",
        "[None for sink.attr in (check(2),)]",
        "[None for check(2).attr in (0,)]",
        "[m(check(2)) for m in (print,)]",
    ],
)
def test_the_first_iterable_and_a_target_subexpression_still_reach_the_helper(
    tmp_path, comprehension
):
    source = (
        _HELPER_REAL
        + "    return ()\n"
        + "def test_a():\n    sink = {}\n    "
        + comprehension
        + "\n"
    )
    assert _scan(tmp_path, {_TEST: source}) == (1, [])


def test_a_method_called_through_a_rebound_self_never_reaches_the_helper(tmp_path):
    source = (
        "class Dummy:\n"
        "    def check(self, value):\n"
        "        return value\n"
        "class TestA:\n"
        "    def check(self, value):\n"
        "        assert value == 2\n"
        "    def test_a(self):\n"
        "        [self.check(1) for self in (Dummy(),)]\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


def test_an_assertion_called_through_a_name_the_comprehension_binds_still_counts(
    tmp_path,
):
    source = (
        "from unittest.mock import Mock\n"
        "def test_a():\n"
        "    [m.assert_called_once() for m in (Mock(),)]\n"
    )
    assert _scan(tmp_path, {_TEST: source}) == (1, [])


@pytest.mark.parametrize(
    "expression",
    [
        "[(outer := inner) for inner in source]",
        "{inner: (outer := inner) for inner in source}",
        "((outer := inner) for inner in source)",
        "[[(outer := inner) for inner in source] for other in source]",
    ],
)
def test_scope_walker_exposes_only_enclosing_comprehension_bindings(expression):
    tree = ast.parse("def f():\n    " + expression)
    stores = [
        node.id
        for node in st.scope_nodes(tree.body[0])
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    ]
    assert stores == ["outer"]


@pytest.mark.parametrize(
    "test_body, helper_body",
    [
        ("check()\nassert value", "assert True"),
        ("check()", "assert True\nassert value"),
        ("assert value\ncheck()", "assert x == x"),
        ("good()\ncheck()", "assert True"),
        ("check()\ngood()", "assert True"),
        ("check()", "assert value\nbad()"),
        ("check()", "good()\nbad()"),
        ("check()", "bad()\ngood()"),
    ],
)
def test_reachable_helper_tautologies_survive_real_assertions(
    tmp_path, test_body, helper_body
):
    source = (
        "def good():\n    assert value\ndef bad():\n    assert True\n"
        "def check():\n"
        + textwrap.indent(helper_body, "    ")
        + "\ndef test_a(value):\n"
        + textwrap.indent(test_body, "    ")
        + "\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [(f.node_id, f.kind) for f in findings] == [
        (_TEST + "::test_a", aq.TAUTOLOGY)
    ]


def test_imported_helper_tautology_names_its_source_and_the_calling_test(tmp_path):
    count, findings = _scan(
        tmp_path,
        {
            _TEST: "from helpers import check\ndef test_a(value):\n    assert value\n    check()\n",
            "tests/helpers.py": "def check():\n    assert True\n",
        },
    )
    assert count == 1
    assert [(f.node_id, f.kind) for f in findings] == [
        (_TEST + "::test_a", aq.TAUTOLOGY)
    ]
    assert "tests/helpers.py:2" in findings[0].detail


@pytest.mark.parametrize("depth", [1, 2, 3, 6])
def test_tautologies_stop_at_helper_depth_and_cycles_are_reported_once(tmp_path, depth):
    source = (
        "def check():\n    assert value\n    bad()\n"
        "def bad():\n    assert True\n    check()\n"
        "def test_a():\n    check()\n    check()\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source}, depth=depth)
    assert count == 1
    assert [f.kind for f in findings] == ([] if depth == 1 else [aq.TAUTOLOGY])


_CONSTANT_TRUE = {
    "2 + 2": "4",
    "-3": "-3",
    "+2": "2",
    "1 < 2": "True",
    "1 != 2": "True",
    "2 + 2 == 4": "True",
    "3 > 2 >= 1": "True",
    "-3 < +2": "True",
    "9 // 2 == 4": "True",
    "7 % 3 == 1": "True",
    "2 ** 3 == 8": "True",
    "3 / 2 == 1.5": "True",
    "(1 << 3) | 2 == 10": "True",
    "(~1 & 3) ^ 1 == 3": "True",
    "'a' + 'b' == 'ab'": "True",
    "3 * 'x' == 'xxx'": "True",
    "b'a' < b'b'": "True",
    "[1, 2] == [1, 2]": "True",
    "1 in (1, 2)": "True",
    "2 not in {1, 3}": "True",
    "{'x': 1} == {'x': 1}": "True",
    "None is None": "True",
    "not (2 < 1)": "True",
    "(1 < 2 and 3 != 4) or False": "True",
    "(2 - 2) or (3 > 1)": "True",
}


@pytest.mark.parametrize("expression", _CONSTANT_TRUE)
def test_literal_operations_that_are_true_are_tautologies(tmp_path, expression):
    count, findings = _scan(
        tmp_path, {_TEST: f"def test_a():\n    assert {expression}\n"}
    )
    assert count == 1
    assert [f.kind for f in findings] == [aq.TAUTOLOGY]


@pytest.mark.parametrize("expression, expected", _CONSTANT_TRUE.items())
@pytest.mark.parametrize("method", ["assertTrue", "assertFalse", "assertEqual"])
def test_unittest_literal_operations_share_the_judge(
    tmp_path, expression, expected, method
):
    argument = {
        "assertTrue": expression,
        "assertFalse": "not (" + expression + ")",
        "assertEqual": "(" + expression + "), " + expected,
    }[method]
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n    def test_a(self):\n"
        f"        self.{method}({argument})\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.TAUTOLOGY]


@pytest.mark.parametrize(
    "expression",
    [
        "1 > 2",
        "2 + 2 == 5",
        "not (1 < 2)",
        "1 < 2 < 0",
        "2 < 1 == 1",
        "[] == [] != []",
        "2 - 2",
        "1 / 0",
        "1 + 'x'",
        "1 < 'x'",
        "2 ** (10 ** 10)",
        "x + 1 == 3",
        "obj.value + 1 == 3",
        "items[0] + 1 == 3",
        "f() + 1 == 3",
        "[f()] == [f()]",
    ],
)
def test_false_unknown_or_unsafe_operations_stay_real(tmp_path, expression):
    source = f"def test_a(x, obj, items, f):\n    assert {expression}\n"
    assert _scan(tmp_path, {_TEST: source}) == (1, [])


@pytest.mark.parametrize("body", ["...", "...\n...", "pass\n..."])
def test_ellipsis_only_handlers_are_swallowed_even_with_a_real_assertion(
    tmp_path, body
):
    source = (
        "def test_a(value):\n    try:\n        f()\n    except ValueError:\n"
        + textwrap.indent(body, "        ")
        + "\n    assert value\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.SWALLOWED]


@pytest.mark.parametrize(
    "binding, consumer",
    [
        pytest.param("def list(g):\n    return None", "list", id="local-list-def"),
        pytest.param("all = bool", "all", id="local-all-alias"),
        pytest.param("sorted = lambda g: g", "sorted", id="local-sorted-lambda"),
    ],
)
def test_fix2_enclosing_consumer_binding(tmp_path, binding, consumer):
    body = binding + "\ndef run():\n    " + consumer + "(check(x) for x in [1])\nrun()"
    source = _HELPER_REAL + "\ndef test_a():\n" + textwrap.indent(body, "    ")
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == [aq.NO_ASSERTION]


@pytest.mark.parametrize(
    "body, kinds",
    [
        pytest.param(
            "def check(v):\n    self.assertEqual(v, 2)\ncheck(2)",
            [],
            id="receiver-closure",
        ),
        pytest.param(
            "gen = (self.assertEqual(v, 2) for v in [2])\n"
            "def drain():\n    list(gen)\ndrain()",
            [],
            id="generator-closure",
        ),
        pytest.param(
            "def check(v):\n    self = object()\n    self.assertEqual(v, 2)\ncheck(2)",
            [aq.NO_ASSERTION],
            id="rebound-receiver",
        ),
        pytest.param(
            "def check(v):\n    self.assertEqual(v, 2)",
            [aq.NO_ASSERTION],
            id="uncalled-closure",
        ),
        pytest.param(
            "case = self\ndef run():\n"
            "    def check(v):\n        case.assertEqual(v, 2)\n"
            "    check(2)\nrun()",
            [],
            id="two-enclosing-functions",
        ),
        pytest.param(
            "class Helper:\n    self = object()\n"
            "    @staticmethod\n    def check(v):\n        self.assertEqual(v, 2)\n"
            "Helper.check(2)",
            [],
            id="skip-class-receiver-binding",
        ),
        pytest.param(
            "case = self\ndef run():\n    case = object()\n"
            "    def check(v):\n        case.assertEqual(v, 2)\n"
            "    check(2)\nrun()",
            [aq.NO_ASSERTION],
            id="nearest-function-receiver-binding",
        ),
    ],
)
def test_fix2_closure_resolution(tmp_path, body, kinds):
    source = (
        "import unittest\nclass Checks(unittest.TestCase):\n    def test_a(self):\n"
        + textwrap.indent(body, "        ")
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == kinds


@pytest.mark.parametrize(
    "target, kinds",
    [
        pytest.param("a, b", [], id="tuple-target"),
        pytest.param("[a, b]", [], id="list-target"),
        pytest.param("a, *b", [], id="starred-target"),
        pytest.param("gen", [aq.NO_ASSERTION], id="single-name"),
    ],
)
def test_fix2_assignment_unpacking(tmp_path, target, kinds):
    source = (
        _HELPER_REAL
        + "\ndef test_a():\n    "
        + target
        + " = (check(x) for x in [2, 2])\n"
    )
    count, findings = _scan(tmp_path, {_TEST: source})
    assert count == 1
    assert [f.kind for f in findings] == kinds
