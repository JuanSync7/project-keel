"""
title: Unit — pytest_markers (which collected tests a marker call applies to)
kind: tests
layer: n/a
summary: marked_tests maps a `pytest.mark.<name>(...)` call to the collected tests it applies to — a decorator on a collected function or class, or an item of a module- or class-level `pytestmark` — and maps a call on a helper, on an uncollected class, or in a scope holding no collected test to an empty list; a call inside a function body has no entry. A definition pytest never collects marks nothing: a function or class a later statement of the same scope rebinds, a class that defines `__init__` or `__new__`, and anything under a `__test__` that is not a true constant. is_marker reads `<x>.mark.<name>` and `mark.<name>`. dir_recursed prunes a directory by pytest's `norecursedirs`, a virtual environment and `__pycache__`. marker_ids returns string-literal arguments and refuses a name, an f-string, a keyword or no argument with a reason. file_collected matches a file name against the `python_files` patterns. collection_rule_from_ini returns, outside a session, the same four ini values the running session holds, reads a project's renamed rule, imports nothing under the tests root, leaves the process environment and import path unchanged, and raises MarkerError when the ini it would read lies outside the project.
"""

import ast
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import pytest_markers as pm  # noqa: E402

pytestmark = pytest.mark.unit

_RULE = (("test",), ("Test",), ("test_*.py", "*_test.py"))

_SOURCE = """
import pytest

pytestmark = [pytest.mark.req("M"), pytest.mark.unit]

@pytest.mark.req("F")
def test_plain():
    pass

@pytest.mark.req("H")
def helper():
    pass

@pytest.mark.req("C")
class TestBox:
    pytestmark = pytest.mark.req("P")

    @pytest.mark.req("X")
    async def test_inner(self):
        pass

    def not_a_test(self):
        pass

    class TestNested:
        def test_deep(self):
            pass

@pytest.mark.req("U")
class Holder:
    def test_never_collected(self):
        pass

@pytest.mark.req("E")
class TestEmpty:
    pytestmark = [pytest.mark.req("EP")]

    def helper(self):
        pass

def test_body():
    pytest.mark.req("B")
"""


def _by_first_arg(source, rule=_RULE, marker="req"):
    tree = ast.parse(source)
    found = pm.marked_tests(tree, marker, rule)
    calls = {
        id(n): n.args[0].value
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and pm.is_marker(n.func, marker)
    }
    assert set(found) <= set(calls)
    return {calls[key]: tests for key, tests in found.items()}


def test_a_marker_counts_only_on_a_test_the_rule_collects():
    found = _by_first_arg(_SOURCE)
    box = ["TestBox::TestNested::test_deep", "TestBox::test_inner"]
    assert found == {
        "M": sorted(box + ["test_body", "test_plain"]),
        "F": ["test_plain"],
        "H": [],
        "C": box,
        "P": box,
        "X": ["TestBox::test_inner"],
        "U": [],
        "E": [],
        "EP": [],
    }
    # `B` sits in a function body, where pytest reads no marker.
    assert "B" not in found


def test_a_scope_with_no_collected_test_attaches_nothing():
    only_helpers = (
        'import pytest\npytestmark = pytest.mark.req("M")\ndef helper(): pass\n'
    )
    assert _by_first_arg(only_helpers) == {"M": []}
    with_test = only_helpers + "def test_one(): pass\n"
    assert _by_first_arg(with_test) == {"M": ["test_one"]}


def test_the_projects_own_rule_decides_what_is_collected():
    source = (
        "import pytest\n"
        '@pytest.mark.req("A")\ndef check_one(): pass\n'
        '@pytest.mark.req("B")\ndef test_two(): pass\n'
        '@pytest.mark.req("C")\nclass Suite:\n    def check_three(self): pass\n'
    )
    renamed = (("check_*",), ("Suite",), ("*.py",))
    assert _by_first_arg(source, renamed) == {
        "A": ["check_one"],
        "B": [],
        "C": ["Suite::check_three"],
    }
    assert _by_first_arg(source, marker="endpoint") == {}


def test_marked_tests_and_attached_markers_agree_on_placement():
    """The end-to-end gate reads attached_markers; a call it counts is a call
    marked_tests has an entry for."""
    tree = ast.parse(_SOURCE)
    attached = pm.attached_markers(tree, "req", _RULE[:2])
    assert attached <= set(pm.marked_tests(tree, "req", _RULE))


def _call(text):
    return ast.parse(text, mode="eval").body


def test_a_tuple_pytestmark_is_read_like_a_list():
    source = (
        "import pytest\n"
        'pytestmark = (pytest.mark.req("M"), pytest.mark.unit)\n'
        "def test_a(): pass\n"
        "class TestBox:\n"
        '    pytestmark = (pytest.mark.req("P"),)\n'
        "    def test_b(self): pass\n"
    )
    assert _by_first_arg(source) == {
        "M": ["TestBox::test_b", "test_a"],
        "P": ["TestBox::test_b"],
    }
    tree = ast.parse(source)
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and pm.is_marker(n.func, "req")
    ]
    assert len(calls) == 2
    assert pm.attached_markers(tree, "req", _RULE[:2]) == {id(n) for n in calls}


# Each source holds one marker call, `X`, on a definition pytest never
# collects: what the name holds when its scope ends is something else, or
# pytest refuses the class.
_NEVER_COLLECTED = {
    "a later def of the same name": (
        '@pytest.mark.req("X")\ndef test_a(): assert False\n\ndef test_a(): pass\n'
    ),
    "a later assignment of the same name": (
        '@pytest.mark.req("X")\ndef test_a(): pass\n\ntest_a = None\n'
    ),
    "a later import of the same name": (
        '@pytest.mark.req("X")\ndef test_a(): pass\n\nfrom os import path as test_a\n'
    ),
    "a later conditional rebinding": (
        '@pytest.mark.req("X")\ndef test_a(): pass\n\nif pytest:\n    test_a = 1\n'
    ),
    "a deleted name": '@pytest.mark.req("X")\ndef test_a(): pass\n\ndel test_a\n',
    "a later class of the same name": (
        '@pytest.mark.req("X")\nclass TestA:\n    def test_a(self): pass\n'
        "\nclass TestA:\n    def test_b(self): pass\n"
    ),
    "a shadowed method": (
        "class TestA:\n"
        '    @pytest.mark.req("X")\n    def test_a(self): pass\n'
        "    def test_a(self): pass\n"
    ),
    "a class with __init__": (
        "class TestA:\n    def __init__(self): pass\n"
        '    @pytest.mark.req("X")\n    def test_a(self): pass\n'
    ),
    "a class with __new__": (
        '@pytest.mark.req("X")\nclass TestA:\n'
        "    def __new__(cls): return object.__new__(cls)\n"
        "    def test_a(self): pass\n"
    ),
    "a class switched off": (
        "class TestA:\n    __test__ = False\n"
        '    @pytest.mark.req("X")\n    def test_a(self): pass\n'
    ),
    "a decorated class switched off": (
        '@pytest.mark.req("X")\nclass TestA:\n    __test__ = False\n'
        "    def test_a(self): pass\n"
    ),
    "a class switched off by a name": (
        "OFF = False\nclass TestA:\n    __test__ = OFF\n"
        '    pytestmark = pytest.mark.req("X")\n    def test_a(self): pass\n'
    ),
    "a class switched off from outside": (
        '@pytest.mark.req("X")\nclass TestA:\n    def test_a(self): pass\n'
        "\nTestA.__test__ = False\n"
    ),
    "a function switched off": (
        '@pytest.mark.req("X")\ndef test_a(): pass\n\ntest_a.__test__ = False\n'
    ),
    "a module switched off": (
        '__test__ = False\n@pytest.mark.req("X")\ndef test_a(): pass\n'
    ),
    "a module switched off with an annotation": (
        '__test__: bool = False\n@pytest.mark.req("X")\ndef test_a(): pass\n'
    ),
    "a module switched off where source cannot say": (
        'if pytest:\n    __test__ = False\n@pytest.mark.req("X")\ndef test_a(): pass\n'
    ),
    "a module switched off by unpacking": (
        '__test__, other = False, 1\n@pytest.mark.req("X")\ndef test_a(): pass\n'
    ),
    "a superseded pytestmark": (
        'pytestmark = pytest.mark.req("X")\npytestmark = []\ndef test_a(): pass\n'
    ),
}


@pytest.mark.parametrize("name", sorted(_NEVER_COLLECTED))
def test_a_marker_on_a_definition_pytest_never_collects_marks_nothing(name):
    source = "import pytest\n" + _NEVER_COLLECTED[name]
    assert _by_first_arg(source) == {"X": []}, name
    assert pm.attached_markers(ast.parse(source), "req", _RULE[:2]) == set(), name


def test_an_assignment_of_any_shape_is_read_without_error():
    source = (
        "import pytest\n"
        "a, b = 1, 2\n(c, [d, e]) = 1, [2, 3]\nbox = {}\nbox['k'] = 1\n"
        "box['k'].__test__ = False\nf: int\nb += 1\n*g, h = [1, 2]\n"
        '@pytest.mark.req("X")\ndef test_a(): pass\n'
    )
    assert _by_first_arg(source) == {"X": ["test_a"]}


def test_what_a_name_holds_last_is_what_is_collected():
    source = (
        "import pytest\n"
        "def test_a(): pass\n"
        '@pytest.mark.req("LAST")\ndef test_a(): pass\n'
        "class TestA:\n    __test__ = True\n"
        '    @pytest.mark.req("ON")\n    def test_b(self): pass\n'
    )
    assert _by_first_arg(source) == {"LAST": ["test_a"], "ON": ["TestA::test_b"]}


@pytest.mark.parametrize(
    "text, seen",
    [
        ("pytest.mark.req", True),
        ("p.mark.req", True),
        ("mark.req", True),
        ("a.b.mark.req", True),
        ("marks.req", False),
        ("pytest.req", False),
        ("req", False),
        ("mark.other", False),
        ("mark.req.x", False),
    ],
)
def test_a_marker_is_read_through_pytest_or_through_an_imported_mark(text, seen):
    assert pm.is_marker(_call(text), "req") is seen


def test_a_marker_through_an_imported_mark_is_attached_like_any_other():
    source = (
        "from pytest import mark\n"
        '@mark.req("A")\ndef test_a(): pass\n'
        '@mark.req("H")\ndef helper(): pass\n'
    )
    assert _by_first_arg(source) == {"A": ["test_a"], "H": []}


@pytest.mark.parametrize(
    "rel, patterns, recursed",
    [
        ("tests/unit", ("build", ".*"), True),
        ("tests/build", ("build", ".*"), False),
        ("tests/.hidden", ("build", ".*"), False),
        ("tests/unit/build", ("build",), False),
        ("tests/rebuild", ("build",), True),
        ("tests/rebuild", ("*build",), False),
        ("tests/unit/slow", ("unit/slow",), False),
        ("tests/unit/slow", ("e2e/slow",), True),
        ("tests/build", (), True),
        ("tests/__pycache__", (), False),
    ],
)
def test_a_directory_is_recursed_by_pytests_norecursedirs_rule(
    tmp_path, rel, patterns, recursed
):
    (tmp_path / rel).mkdir(parents=True)
    assert pm.dir_recursed(str(tmp_path / rel), rel, patterns) is recursed


def test_a_virtual_environment_is_never_recursed(tmp_path):
    for name, marker in (("env", "pyvenv.cfg"), ("conda", "conda-meta/history")):
        folder = tmp_path / "tests" / name
        assert not (folder / marker).parent.mkdir(parents=True)
        assert pm.dir_recursed(str(folder), "tests/" + name, ()) is True
        (folder / marker).write_text("")
        assert pm.dir_recursed(str(folder), "tests/" + name, ()) is False


@pytest.mark.parametrize(
    "text, ids, reason",
    [
        ('m("A")', ["A"], None),
        ('m("A", "B")', ["A", "B"], None),
        ("m()", [], "names no id"),
        ("m(NAME)", [], "takes string literals only"),
        ('m("A", 3)', [], "takes string literals only"),
        ('m(f"A{n}")', [], "takes string literals only"),
        ('m(b"A")', [], "takes string literals only"),
        ('m("A" + "B")', [], "takes string literals only"),
        ('m(*["A"])', [], "takes string literals only"),
        ('m("A", id="B")', [], "takes no keyword argument"),
    ],
)
def test_marker_ids_reads_string_literals_or_says_why_not(text, ids, reason):
    assert pm.marker_ids(_call(text)) == (ids, reason)


@pytest.mark.parametrize(
    "rel, patterns, expected",
    [
        ("tests/unit/test_a.py", ("test_*.py",), True),
        ("tests/unit/a_test.py", ("test_*.py", "*_test.py"), True),
        ("tests/unit/helpers.py", ("test_*.py", "*_test.py"), False),
        ("tests/conftest.py", ("test_*.py",), False),
        ("tests/test_dir/helpers.py", ("test_*.py",), False),
        ("test_top.py", ("test_*.py",), True),
        ("tests/unit/check_a.py", ("tests/unit/check_*.py",), True),
        ("tests/e2e/check_a.py", ("tests/unit/check_*.py",), False),
        ("tests/unit/test_a.py", (), False),
    ],
)
def test_a_file_is_collected_by_name_or_by_path(rel, patterns, expected):
    assert pm.file_collected(rel, patterns) is expected


def test_the_rule_read_outside_a_session_equals_the_sessions_rule(pytestconfig):
    env, path = dict(os.environ), list(sys.path)
    modules = set(sys.modules)
    rule = pm.collection_rule_from_ini(str(_ROOT), "tests")
    assert rule == pm.full_rule(pytestconfig)
    assert isinstance(rule, pm.CollectionRule)
    assert rule[:2] == pm.collection_rule(pytestconfig)
    assert all(rule), rule
    assert dict(os.environ) == env and list(sys.path) == path
    # Nothing under tests/ is imported: collection is switched off.
    assert not {
        m for m in set(sys.modules) - modules if m.startswith(("test_", "conftest"))
    }


def test_the_rule_is_the_projects_own_and_never_a_parents(tmp_path):
    parent = tmp_path / "parent"
    project = parent / "project"
    (project / "tests").mkdir(parents=True)
    # A test file that would fail the run if anything imported it.
    (project / "tests" / "test_boom.py").write_text("raise SystemExit(99)\n")
    (project / "tests" / "conftest.py").write_text("raise SystemExit(98)\n")
    (project / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'python_functions = ["check_*"]\n'
        'python_classes = ["Suite"]\n'
        'python_files = ["check_*.py"]\n'
        'norecursedirs = ["skip_*", "vendored"]\n'
    )
    assert pm.collection_rule_from_ini(str(project), "tests") == (
        ("check_*",),
        ("Suite",),
        ("check_*.py",),
        ("skip_*", "vendored"),
    )

    (project / "pyproject.toml").unlink()
    (parent / "pytest.ini").write_text("[pytest]\npython_functions = other_*\n")
    with pytest.raises(pm.MarkerError, match="outside the project"):
        pm.collection_rule_from_ini(str(project), "tests")

    (project / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nminversion = '999'\n"
    )
    with pytest.raises(pm.MarkerError, match="collection rule"):
        pm.collection_rule_from_ini(str(project), "tests")
