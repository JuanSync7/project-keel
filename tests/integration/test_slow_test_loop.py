"""
title: Integration — slow tests stay in the gate and durations come from config
kind: tests
layer: n/a
summary: Derives verify's recursive make hops with make's own variable expansion without executing recipes, then dry-runs only recursion-free leaves and checks every reached pytest keeps slow tests and durations. Fixture chains reject hidden selections and zero pytest calls. The duration count comes from a positive integer loader key with a default; the slow marker is registered in both pytest twins.
"""

import io
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 uses the declared dev dependency.
    import tomli as tomllib

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration


def _timeout():
    return config_loader.resolve(
        config_loader.read(_ROOT, "config/project.json"),
        [
            row
            for row in config_loader.KEYS
            if row.path == ("tests", "child_timeout_seconds")
        ],
        "config/project.json",
    )[("tests", "child_timeout_seconds")]


def _rules(root):
    problems = []
    files = cs.walk_makefiles(str(root), problems.append, problems.append)
    assert files and not problems, problems
    rules = {}
    for name, text in files:
        # Parsing makefiles can itself run commands. Refuse those forms before
        # asking make anything, and forbid makefile-remaking rules below.
        assert not re.search(
            r"\$[({]\s*(?:shell|file|eval)\b|^[^\t\n#]*!=", text, re.MULTILINE
        ), name
        assert not re.search(r"^\t[ @-]*\+", text, re.MULTILINE), name
        # These forms need target/conditional context that a text rule reader
        # does not retain. Fail closed instead of inspecting the wrong branch.
        assert not re.search(r"^(?:ifdef|ifndef|ifeq|ifneq)\b", text, re.MULTILINE), (
            name
        )
        assert not re.search(r"^[\w-]+\s*:\s*\w+\s*[:?+]?=", text, re.MULTILINE), name
        for rule in cs.make_target_rules(text):
            assert rule.target not in {path for path, _ in files}, rule.target
            assert rule.target not in rules, rule.target
            recipe_only = cs.make_target_rules(
                "probe:\n" + "".join("\t" + command + "\n" for command in rule.recipe)
            )[0]
            assert rule.unresolved == recipe_only.unresolved, (
                "cannot follow variable prerequisites",
                rule,
            )
            rules[rule.target] = rule
    return rules


def _expanded_recipes(root, rule, assignments):
    # The selected goal has no prerequisites and an empty recipe. -q never
    # reaches an original recipe, even one containing $(MAKE). info expands
    # recipe text as data after loading the real variables; it runs no shell.
    probe = "__keel_slowtest_probe"
    source = [f"{probe}: ;"]
    for i, command in enumerate(rule.recipe):
        source.extend(
            [
                f"define {probe}_{i}",
                command.replace("$@", rule.target),
                "endef",
                f"$(info {probe}_{i}:$({probe}_{i}))",
            ]
        )
    proc = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-rR",
            "-q",
            "-o",
            "Makefile",
            "-o",
            "-",
            "-f",
            "Makefile",
            "-f",
            "-",
            probe,
            "PY=" + sys.executable,
            "MAKE=__keel_make__",
            *assignments,
        ],
        input="\n".join(source) + "\n",
        cwd=root,
        env=build_child_env(),
        capture_output=True,
        text=True,
        timeout=_timeout(),
    )
    assert proc.returncode in (0, 1) and not proc.stderr, proc.stdout + proc.stderr
    lines = proc.stdout.splitlines()
    commands = []
    for i in range(len(rule.recipe)):
        prefix = f"{probe}_{i}:"
        (line,) = [line for line in lines if line.startswith(prefix)]
        commands.append(line.removeprefix(prefix))
    return commands


def _make_hop(command):
    words = shlex.split(command)
    calls = [i for i, word in enumerate(words) if word in ("__keel_make__", "make")]
    if not calls:
        return [], []
    assert len(calls) == 1, command
    (start,) = calls
    assert start == 0 or words[start - 1] == "--", command
    goals, assignments = [], []
    for word in words[start + 1 :]:
        if re.match(r"^[A-Za-z_]\w*=", word):
            assert word.split("=", 1)[0] not in ("MAKE", "MAKEFLAGS", "SHELL"), command
            assignments.append(word)
        else:
            assert re.fullmatch(r"[A-Za-z0-9_-]+", word), command
            goals.append(word)
    assert goals, command
    return goals, assignments


def _dry_run(target, *, root=None, assignments=()):
    root = _ROOT if root is None else root
    rules = _rules(root)
    stack, seen = [target], set()
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        rule = rules[name]
        assert not rule.unresolved, rule
        # GNU make executes a line with a literal MAKE reference under -n
        # even when that reference is in a branch that expands to nothing.
        assert not any(
            re.search(r"\$[({]MAKE[)}]", command) for command in rule.recipe
        ), rule
        stack.extend(rule.prereqs)
        for command in _expanded_recipes(root, rule, assignments):
            goals, _ = _make_hop(command)
            assert not goals, f"refusing recursive dry run: {name}: {command}"
    proc = subprocess.run(
        ["make", "-n", target, "PY=" + sys.executable, *assignments],
        cwd=root,
        env=build_child_env(),
        capture_output=True,
        text=True,
        timeout=_timeout(),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


@pytest.mark.parametrize(
    ("target", "selection"),
    [("unit", "unit and not slow"), ("test", None), ("test-ship", None)],
)
def test_only_unit_excludes_slow(target, selection):
    words = shlex.split(_dry_run(target))
    assert words.count("pytest") == 1, words
    args = words[words.index("pytest") + 1 :]
    actual = args[args.index("-m") + 1] if "-m" in args else None
    assert actual == selection, (target, args)
    if selection is None:
        assert not any(arg.startswith("-m") for arg in args), (target, args)
        assert "not slow" not in " ".join(args), (target, args)


def _assert_verify_keeps_slow(root):
    rules = _rules(root)
    stack, seen, count = [("verify", ())], set(), 0
    while stack:
        target, assignments = stack.pop()
        if (target, assignments) in seen:
            continue
        seen.add((target, assignments))
        rule = rules[target]
        stack.extend((name, assignments) for name in rule.prereqs)
        commands = _expanded_recipes(root, rule, assignments)
        recursive = False
        for command in commands:
            goals, overrides = _make_hop(command)
            recursive = recursive or bool(goals)
            inherited = dict(item.split("=", 1) for item in assignments)
            inherited.update(item.split("=", 1) for item in overrides)
            child = tuple(f"{key}={value}" for key, value in sorted(inherited.items()))
            stack.extend((name, child) for name in goals)
        if any(
            word == "pytest" or word.endswith("/pytest")
            for command in commands
            for word in shlex.split(command)
        ):
            # A recipe may run pytest and then recurse. Never dry-run such a
            # target; its expanded commands are already available as data.
            output = (
                "\n".join(commands)
                if recursive
                else _dry_run(target, root=root, assignments=assignments)
            )
            count += _assert_full_pytests(output)
    assert count, "verify reaches zero pytest commands"


def _assert_full_pytests(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    words = list(lexer)
    count = 0
    for i, word in enumerate(words):
        if word != "pytest" and not word.endswith("/pytest"):
            continue
        count += 1
        args = []
        for arg in words[i + 1 :]:
            if arg and all(char in ";&|()\n" for char in arg):
                break
            args.append(arg)
        assert not any(
            arg.startswith(
                ("-m", "-k", "--deselect", "--ignore", "--lf", "--last-failed")
            )
            for arg in args
        ), f"pytest selection drops tests: {args}"
        duration_index = (
            args.index("--durations") + 1 if "--durations" in args else len(args)
        )
        duration = next(
            (arg.split("=", 1)[1] for arg in args if arg.startswith("--durations=")),
            args[duration_index] if duration_index < len(args) else None,
        )
        assert duration and not duration.startswith("-"), (
            f"pytest loses --durations: {args}"
        )
    return count


def test_verify_reaches_the_full_test_recipe():
    _assert_verify_keeps_slow(_ROOT)


@pytest.mark.parametrize(
    "makefile",
    [
        'FLAGS = -m "not slow"\n'
        "HOP = test EXTRA='$(FLAGS)'\n"
        "verify:\n\t$(PY) gate.py -- $(MAKE) $(HOP) test\n"
        "test:\n\t$(PY) -m pytest --durations 10 $(EXTRA)\n",
        "verify:\n\t$(PY) gate.py -- $(MAKE) fast test\n"
        'fast:\n\t$(PY) -m pytest --durations 10 -m "not slow"\n'
        "test:\n\t$(PY) -m pytest --durations 10\n",
        "verify:\n\t$(PY) gate.py -- $(MAKE) test\ntest:\n\t@echo no tests\n",
    ],
    ids=["variable-hop", "different-target", "zero-pytest"],
)
def test_verify_rejects_incomplete_test_chains(tmp_path, makefile):
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    with pytest.raises(AssertionError, match="pytest"):
        _assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    "args",
    [
        '--durations 10 -m "not slow"',
        "--durations=10 -mnot\\ slow",
        "--durations 10 -k quick",
        "--durations 10 -kquick",
        "--durations 10 --deselect tests/test_sample.py::test_slow",
        "--durations 10 --deselect=tests/test_sample.py::test_slow",
        "--durations 10 --ignore=tests/test_slow.py",
        "--durations 10 --lf",
        "",
        "--durations",
    ],
)
def test_verify_checks_every_pytest_and_its_durations(tmp_path, args):
    (tmp_path / "Makefile").write_text(
        "NEXT = middle\n"
        "verify:\n\t$(MAKE) $(NEXT)\n"
        "middle:\n\t$(PY) gate.py -- $(MAKE) test\n"
        "test:\n\t$(PY) -m pytest --durations 10\n"
        f"\t$(PY) -m pytest {args}\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="pytest"):
        _assert_verify_keeps_slow(tmp_path)


def test_verify_follows_later_hops_and_distinct_variable_values(tmp_path):
    (tmp_path / "Makefile").write_text(
        "HOP = middle EXTRA='--durations=7'\n"
        "verify:\n\t$(MAKE) $(HOP)\n"
        "middle:\n\t$(PY) -m pytest --durations 10\n"
        "\t$(MAKE) test\n"
        "test:\n\t$(PY) -m pytest $(EXTRA)\n",
        encoding="utf-8",
    )
    _assert_verify_keeps_slow(tmp_path)
    with (tmp_path / "Makefile").open("a", encoding="utf-8") as stream:
        stream.write("\t$(MAKE) later\nlater:\n\t$(PY) -m pytest -k quick\n")
    with pytest.raises(AssertionError, match="pytest"):
        _assert_verify_keeps_slow(tmp_path)


def test_test_reads_its_duration_count_through_config_get():
    command = _dry_run("test")
    assert "scripts/config_get.py tests.durations" in command, command
    assert '--durations "$durations"' in command, command


def _durations_row():
    rows = [row for row in config_loader.KEYS if row.path == ("tests", "durations")]
    assert len(rows) == 1, "tests.durations needs one typed default row"
    return rows[0]


def test_durations_default_is_positive():
    row = _durations_row()
    assert row.type == "int"
    assert row.default == 10
    resolved = config_loader.resolve({}, [row], "defaults", stream=io.StringIO())
    assert resolved[row.path] == row.default


@pytest.mark.parametrize("value", [1, 7, 27])
def test_durations_accepts_positive_counts(value):
    row = _durations_row()
    resolved = config_loader.resolve({"tests": {"durations": value}}, [row], "fixture")
    assert resolved[row.path] == value


@pytest.mark.parametrize("value", [0, -1, True, "5", None])
def test_durations_refuses_zero_and_wrong_types(value):
    row = _durations_row()
    with pytest.raises(config_loader.WrongValue, match=r"tests\.durations"):
        config_loader.resolve(
            {"tests": {"durations": value}}, [row], "fixture", stream=io.StringIO()
        )


def test_slow_marker_is_registered_in_both_pytest_twins():
    text = (_ROOT / "pyproject.toml").read_text("utf-8")
    markers = tomllib.loads(text)["tool"]["pytest"]["ini_options"]["markers"]
    (slow,) = [marker for marker in markers if marker.startswith("slow:")]
    assert "unit" in slow and "gate" in slow, slow
    twin = _ROOT / "pyproject.toml.jinja"
    # Generated projects have no twins; their registered marker still applies.
    if twin.is_file():
        assert '"' + slow + '"' in twin.read_text("utf-8")
