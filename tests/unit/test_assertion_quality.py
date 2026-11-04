"""
title: Unit — tests/assertion_quality.py judges whether a test can fail
kind: tests
layer: n/a
summary: tests/assertion_quality.py over test files written to a temporary tree, one table row per planted fault: no assertion, a truthy-constant assertion, a tautology over a name or an attribute chain, a handler that passes or continues, and a test whose only assertion sits in a helper that asserts a constant, each red; an `assert`, a comparison of two calls, `pytest.raises` and `pytest.warns`, a mock's `assert_*`, a bare `isinstance` and a helper that asserts for real (same module, an imported module by either import form, a method through `self`), each green. The helper walk stops at the configured depth and terminates on a cycle; a file outside the roots is never a helper. `verdict` fails a run over zero tests, an unexcused finding and a stale excuse; `policy` reads the three keys, takes their defaults and refuses a value the loader refuses, naming the key.
"""

import json
import textwrap

import config_loader
import pytest

import assertion_quality as aq

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
    ("constant-true", {_TEST: "def test_a():\n    assert True\n"}, [aq.CONSTANT]),
    ("constant-text", {_TEST: "def test_a():\n    assert 'text'\n"}, [aq.CONSTANT]),
    ("constant-one", {_TEST: "def test_a():\n    assert 1\n"}, [aq.CONSTANT]),
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
        [aq.CONSTANT],
    ),
    (
        "imported-helper-asserts-a-constant",
        {
            "tests/helpers.py": _HELPER_CONSTANT,
            _TEST: "import helpers\n\ndef test_a():\n    helpers.check(2)\n",
        },
        [aq.CONSTANT],
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


def test_policy_reads_the_three_keys(tmp_path):
    block = {
        "roots": ["tests/unit"],
        "helper_depth": 2,
        "exempt": {"tests/unit/test_a.py::test_b": "r"},
    }
    assert aq.policy(_config(tmp_path, block)) == aq.Policy(
        ("tests/unit",), 2, {"tests/unit/test_a.py::test_b": "r"}
    )


def test_policy_takes_the_defaults_and_says_so(tmp_path, capsys):
    assert aq.policy(_config(tmp_path, {})) == aq.Policy(("tests",), 3, {})
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
    ],
)
def test_policy_refuses_a_bad_value_naming_the_key(tmp_path, key, value):
    with pytest.raises(
        config_loader.ConfigError, match="test_quality.assertions." + key
    ):
        aq.policy(_config(tmp_path, {key: value}))
