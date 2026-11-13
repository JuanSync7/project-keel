"""
title: Unit — configured regex matching has a deadline
summary: Ordinary matches agree with re; hostile patterns and broken child replies refuse without exposing inputs, and empty batches start no child.
"""

import importlib
import re
import subprocess
import time
from typing import Any

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("mode", ["search", "fullmatch"])
@pytest.mark.parametrize("pattern", [r"[A-Z]+-\d+", r"(?i)^a.*z$"])
def test_ordinary_matches_agree_with_re(pattern: str, mode: str) -> None:
    bounded_match = importlib.import_module("scripts.bounded_match")
    values = ["", "KEEL-12", "prefix KEEL-12 suffix", "aZ", "a\nz", "KEEL-12\n"]
    expected = [getattr(re.compile(pattern), mode)(v) is not None for v in values]
    assert (
        bounded_match.match_values(pattern, "work_naming.backlog_id", values, mode)
        == expected
    )


def test_empty_values_start_no_child(monkeypatch: pytest.MonkeyPatch) -> None:
    bounded_match = importlib.import_module("scripts.bounded_match")

    def unexpected(*args: Any, **kwargs: Any) -> None:
        pytest.fail("an empty batch started a child")

    monkeypatch.setattr(subprocess, "run", unexpected)
    assert bounded_match.match_values("x", "work_naming.backlog_id", [], "search") == []


def test_backtracking_refuses_within_bound_without_inputs() -> None:
    bounded_match = importlib.import_module("scripts.bounded_match")
    pattern, value = "^(a+)+$", "a" * 100 + "!"
    started = time.monotonic()
    with pytest.raises(AssertionError) as caught:
        bounded_match.match_values(
            pattern, "work_naming.backlog_id", [value], "search", timeout=2
        )
    assert time.monotonic() - started < 10
    message = str(caught.value)
    assert "work_naming.backlog_id" in message
    assert "tests.child_timeout_seconds" in message
    assert "timeout" in message and "repair" in message
    assert pattern not in message and value not in message


@pytest.mark.parametrize(
    "returncode, output", [(1, "private"), (0, "not json"), (0, "[1]"), (0, "[]")]
)
def test_broken_child_refuses_without_inputs(
    monkeypatch: pytest.MonkeyPatch, returncode: int, output: str
) -> None:
    bounded_match = importlib.import_module("scripts.bounded_match")

    def reply(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], returncode, output, "private")

    monkeypatch.setattr(subprocess, "run", reply)
    with pytest.raises(AssertionError) as caught:
        bounded_match.match_values(
            "private", "work_naming.backlog_id", ["private"], "search"
        )
    message = str(caught.value)
    assert "work_naming.backlog_id" in message and "repair" in message
    assert "private" not in message


def test_batch_uses_one_isolated_child_and_stdin_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bounded_match = importlib.import_module("scripts.bounded_match")
    calls = []
    run = subprocess.run

    def record(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", record)
    assert bounded_match.match_values(
        "x", "work_naming.backlog_id", ["x", "y"], "search"
    ) == [True, False]
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0][1:3] == ["-I", "-c"]
    assert "env" in kwargs and "timeout" in kwargs
    assert '"x"' in kwargs["input"] and '"y"' in kwargs["input"]
    assert "work_naming.backlog_id" not in args[0]


@pytest.mark.parametrize(
    "pattern, values, expected",
    [
        (r"\d+", ["a1 b22 c333", "none", ""], [[(1, 2), (4, 6), (8, 11)], [], []]),
        (r"x*", ["ab"], [[(0, 0), (1, 1), (2, 2)]]),
        (r"é+", ["aéé é"], [[(1, 3), (4, 5)]]),
    ],
    ids=["several-none-empty-value", "empty-matches", "non-ascii-offsets"],
)
def test_spans_agree_with_finditer(
    pattern: str, values: list[str], expected: list[list[tuple[int, int]]]
) -> None:
    bounded_match = importlib.import_module("scripts.bounded_match")
    spans = bounded_match.match_spans(pattern, "doc_drift.forbidden_phrases", values)
    assert spans == expected
    assert spans == [[m.span() for m in re.finditer(pattern, v)] for v in values]


def test_spans_of_an_empty_batch_start_no_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bounded_match = importlib.import_module("scripts.bounded_match")

    def unexpected(*args: Any, **kwargs: Any) -> None:
        pytest.fail("an empty batch started a child")

    monkeypatch.setattr(subprocess, "run", unexpected)
    assert bounded_match.match_spans("x", "doc_drift.forbidden_phrases", []) == []


def test_spans_of_a_matching_then_backtracking_pattern_refuse_in_time() -> None:
    bounded_match = importlib.import_module("scripts.bounded_match")
    pattern, value = r"x|(a+)+$", "x " + "a" * 40 + "b"
    started = time.monotonic()
    with pytest.raises(AssertionError) as caught:
        bounded_match.match_spans(
            pattern, "doc_drift.forbidden_phrases", [value], timeout=0.5
        )
    assert time.monotonic() - started < 10
    message = str(caught.value)
    assert "doc_drift.forbidden_phrases" in message
    assert "timeout" in message and "repair" in message
    assert pattern not in message and value not in message


@pytest.mark.parametrize(
    "output",
    ["not json", "[]", "[[[0, 9]]]", "[[[1, 0]]]", "[[[0]]]", "[[[true, 1]]]", "[1]"],
)
def test_malformed_span_replies_refuse_without_inputs(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    bounded_match = importlib.import_module("scripts.bounded_match")

    def reply(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 0, output, "private")

    monkeypatch.setattr(subprocess, "run", reply)
    with pytest.raises(AssertionError) as caught:
        bounded_match.match_spans("private", "doc_drift.forbidden_phrases", ["abc"])
    message = str(caught.value)
    assert "doc_drift.forbidden_phrases" in message and "repair" in message
    assert "private" not in message
