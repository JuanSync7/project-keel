"""
title: Unit — scripts.check_practices detectors
kind: tests
layer: n/a
summary: The coding-practices advisor detects DI-inline / isinstance-chain / hot-path / acquire smells generally (over the input class, not one example), and its detectors are pure over an AST.
"""
import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_practices as cp  # noqa: E402

pytestmark = pytest.mark.unit


# --- dependency-injection smell ------------------------------------------------

def test_flags_provider_constructed_inline():
    tree = ast.parse("def build():\n    return ChatOpenAI(model='x')\n")
    found = cp.find_di_inline(tree, ["ChatOpenAI", "OpenAI"])
    assert [f["kind"] for f in found] == ["dependency-injection"]


def test_di_solves_the_class_not_one_token():
    """Any REGISTERED provider is caught; an unregistered call is not — the rule
    is 'a token from the registry', not a hardcoded vendor name (CONVENTIONS §18)."""
    tree = ast.parse("x = Anthropic()\n")
    assert cp.find_di_inline(tree, ["Anthropic"])
    assert cp.find_di_inline(tree, ["SomethingElse"]) == []


# --- singledispatch-candidate smell -------------------------------------------

def _chain(n):
    branches = "".join(
        "    %sif isinstance(x, T%d):\n        return %d\n" % ("" if i == 0 else "el", i, i)
        for i in range(n))
    return ast.parse("def f(x):\n%s    return None\n" % branches)


def test_flags_three_isinstance_branches_on_one_subject():
    found = cp.find_isinstance_chains(_chain(3))
    assert len(found) == 1 and found[0]["kind"] == "singledispatch-over-isinstance"


def test_two_isinstance_branches_is_fine():
    assert cp.find_isinstance_chains(_chain(2)) == []


def test_different_subjects_are_not_a_chain():
    src = ("def f(x, y):\n"
           "    if isinstance(x, int):\n        return 1\n"
           "    elif isinstance(y, str):\n        return 2\n"
           "    elif isinstance(x, float):\n        return 3\n"
           "    return 0\n")
    assert cp.find_isinstance_chains(ast.parse(src)) == []


# --- hot-path / __slots__ smell -----------------------------------------------

def _hotpath(body):
    src = "# hot-path\n" + body
    return ast.parse(src), cp._comment_lines(src, "hot-path")


def test_flags_hot_path_class_without_slots():
    tree, markers = _hotpath("class Chunk:\n    def __init__(self):\n        self.x = 1\n")
    found = cp.find_hotpath_no_slots(tree, markers)
    assert len(found) == 1 and found[0]["kind"] == "slots-hot-path"


def test_hot_path_with_slots_is_clean():
    tree, markers = _hotpath("class Chunk:\n    __slots__ = ('x',)\n    def m(self):\n        return 1\n")
    assert cp.find_hotpath_no_slots(tree, markers) == []


def test_hot_path_dataclass_slots_true_is_clean():
    tree, markers = _hotpath("@dataclass(slots=True)\nclass Chunk:\n    x: int = 0\n")
    assert cp.find_hotpath_no_slots(tree, markers) == []


def test_unmarked_class_is_never_flagged():
    tree = ast.parse("class Plain:\n    def __init__(self):\n        self.x = 1\n")
    assert cp.find_hotpath_no_slots(tree, set()) == []


# --- resource / context-manager smell (domain) --------------------------------

def test_acquire_outside_with_is_flagged():
    """Matches the last dotted segment, so 'torch.cuda.stream' catches stream()."""
    tree = ast.parse("def f():\n    s = stream()\n    return s\n")
    found = cp.find_acquire_no_cm(tree, ["torch.cuda.stream"])
    assert found and found[0]["kind"] == "resource-context-manager"


def test_acquire_inside_with_is_clean():
    tree = ast.parse("def f():\n    with stream() as s:\n        return s\n")
    assert cp.find_acquire_no_cm(tree, ["torch.cuda.stream"]) == []
