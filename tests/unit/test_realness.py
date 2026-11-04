"""
title: Unit — tests/realness.py tiers what a test replaces of its dependency
kind: tests
layer: n/a
summary: tests/realness.py over test files written to a temporary tree, one table row per planted signal: a `mocker` fixture, a `@patch` decorator, a `mock.patch` call through `from unittest import mock`, an autouse `monkeypatch` fixture in a `conftest.py` two directories above the test, a fixture that requests `mocker` through another fixture, and a `usefixtures` mark, each `mock` and named; `tmp_path`, `caplog` and `freezer`, `unittest.TestCase`, a local fixture that hides the plugin's `mocker` and a fixture cycle, each `unknown`; moto, `TestClient` and testcontainers each their own tier, and a test with a fake and a mock `mock`. `verdict` fails a run over zero tests, an unexcused `mock` test and a stale excuse; `policy` reads both keys, takes their defaults and refuses a value the loader refuses, naming the key.
"""

import json
import textwrap

import config_loader
import pytest

import realness

pytestmark = pytest.mark.unit

_TEST = "tests/e2e/flow/test_case.py"
_ROOTS = ("tests/e2e",)
_SEARCH = ["tests/", ""]


def _scan(tmp_path, files):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
    root = str(tmp_path)
    return realness.scan(root, realness.test_files(root, _ROOTS), _SEARCH)


# (row id, files, the one test's tier, the signals at that tier)
_ROWS = [
    (
        "mocker-fixture",
        {_TEST: "def test_a(mocker):\n    mocker.patch('os.getcwd')\n"},
        "mock",
        ("fixture:mocker",),
    ),
    (
        "patch-decorator",
        {
            _TEST: """
            from unittest.mock import patch

            @patch("os.getcwd")
            def test_a(getcwd):
                assert getcwd
            """
        },
        "mock",
        ("use:patch",),
    ),
    (
        "mock-module-call",
        {
            _TEST: """
            from unittest import mock

            def test_a():
                with mock.patch("os.getcwd"):
                    pass
            """
        },
        "mock",
        ("use:mock",),
    ),
    (
        "autouse-monkeypatch-in-a-conftest-above",
        {
            "tests/conftest.py": """
            import pytest

            @pytest.fixture(autouse=True)
            def stub(monkeypatch):
                monkeypatch.setenv("X", "1")
            """,
            _TEST: "def test_a():\n    assert 1\n",
        },
        "mock",
        ("autouse:fixture:stub->fixture:monkeypatch",),
    ),
    (
        "mocker-through-another-fixture",
        {
            "tests/e2e/conftest.py": """
            import pytest

            @pytest.fixture
            def client(mocker):
                return mocker.Mock()
            """,
            _TEST: "def test_a(client):\n    assert client\n",
        },
        "mock",
        ("fixture:client->fixture:mocker",),
    ),
    (
        "usefixtures-mark",
        {
            _TEST: """
            import pytest

            @pytest.mark.usefixtures("monkeypatch")
            def test_a():
                assert 1
            """
        },
        "mock",
        ("fixture:monkeypatch",),
    ),
    (
        "control-signals",
        {_TEST: "def test_a(tmp_path, caplog, freezer):\n    assert tmp_path\n"},
        "unknown",
        (),
    ),
    (
        "unittest-without-mock",
        {
            _TEST: """
            import unittest.mock

            def test_a():
                assert unittest.TestCase
            """
        },
        "unknown",
        (),
    ),
    (
        "a-local-fixture-hides-the-plugin",
        {
            _TEST: """
            import pytest

            @pytest.fixture
            def mocker(tmp_path):
                return tmp_path

            def test_a(mocker):
                assert mocker
            """
        },
        "unknown",
        (),
    ),
    (
        "fixture-cycle",
        {
            _TEST: """
            import pytest

            @pytest.fixture(name="a")
            def make_a(b):
                return b

            @pytest.fixture(name="b")
            def make_b(a):
                return a

            def test_a(a):
                assert a
            """
        },
        "unknown",
        (),
    ),
    (
        "fake",
        {
            _TEST: """
            import moto

            def test_a():
                with moto.mock_aws():
                    pass
            """
        },
        "fake",
        ("use:moto",),
    ),
    (
        "in-process",
        {
            _TEST: """
            from fastapi.testclient import TestClient

            def test_a(app):
                assert TestClient(app).get("/").status_code == 200
            """
        },
        "in_process",
        ("use:TestClient",),
    ),
    (
        "real",
        {
            _TEST: """
            from testcontainers.postgres import PostgresContainer

            def test_a():
                with PostgresContainer() as db:
                    assert db
            """
        },
        "real",
        ("use:PostgresContainer",),
    ),
    (
        "the-lowest-tier-wins",
        {
            _TEST: """
            import moto

            def test_a(mocker):
                with moto.mock_aws():
                    mocker.patch("os.getcwd")
            """
        },
        "mock",
        ("fixture:mocker",),
    ),
]


@pytest.mark.parametrize(
    "files, tier, signals", [r[1:] for r in _ROWS], ids=[r[0] for r in _ROWS]
)
def test_each_planted_signal_puts_the_test_in_its_tier(tmp_path, files, tier, signals):
    (tiered,) = _scan(tmp_path, files)
    assert (tiered.tier, tiered.signals) == (tier, signals)


def test_a_mock_test_is_named_with_file_line_function_and_signal(tmp_path):
    (tiered,) = _scan(
        tmp_path,
        {_TEST: "\n\nclass TestA:\n    def test_b(self, mocker):\n        pass\n"},
    )
    assert tiered.node_id == _TEST + "::TestA::test_b"
    assert str(tiered) == _TEST + ":4: TestA::test_b: mock: fixture:mocker"


def _tiered(tier="mock", test="test_a"):
    return realness.Tiered(_TEST, 1, test, tier, ("fixture:mocker",))


def test_verdict_fails_a_run_over_zero_tests():
    (line,) = realness.verdict([], {}, _ROOTS)
    assert "no test function was read under tests/e2e" in line


def test_verdict_fails_only_an_unexcused_mock_test():
    passing = [
        _tiered(t, "test_" + t) for t in ("fake", "in_process", "real", "unknown")
    ]
    assert realness.verdict(passing, {}, _ROOTS) == []
    assert realness.verdict([_tiered()], {}, _ROOTS) == [str(_tiered())]
    assert realness.verdict([_tiered()], {_tiered().node_id: "r"}, _ROOTS) == []


def test_verdict_fails_a_stale_excuse():
    (line,) = realness.verdict([_tiered("unknown")], {_tiered().node_id: "r"}, _ROOTS)
    assert line.startswith(_TEST + "::test_a: stale: ")


def _config(tmp_path, block):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"test_quality": {"realness": block}}), encoding="utf-8"
    )
    return str(tmp_path)


def test_policy_reads_both_keys(tmp_path):
    block = {"roots": ["tests/flows"], "exempt": {"tests/flows/test_a.py::test_b": "r"}}
    assert realness.policy(_config(tmp_path, block)) == realness.Policy(
        ("tests/flows",), {"tests/flows/test_a.py::test_b": "r"}
    )


def test_policy_takes_the_defaults_and_says_so(tmp_path, capsys):
    assert realness.policy(_config(tmp_path, {})) == realness.Policy(("tests/e2e",), {})
    assert "[using default] test_quality.realness.roots" in capsys.readouterr().err


@pytest.mark.parametrize(
    "key, value",
    [
        ("roots", []),
        ("roots", ["/tests"]),
        ("exempt", {"tests/e2e/test_a.py::test_b": ""}),
        ("exempt", {"tests/e2e/test_a.py": "r"}),
    ],
)
def test_policy_refuses_a_bad_value_naming_the_key(tmp_path, key, value):
    with pytest.raises(config_loader.ConfigError, match="test_quality.realness." + key):
        realness.policy(_config(tmp_path, {key: value}))
