"""
title: Integration — slow tests stay in the gate and durations come from config
kind: tests
layer: n/a
summary: Guards make syntax and expansion before deriving verify's recursive hops without executing recipes, then judges every reached pytest against a named argument grammar and proves the test hop keeps slow tests and durations. Unsupported forms fail with their input, cause and fix. The duration count comes from a positive integer loader key; the slow marker is registered in both pytest twins.
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


# These functions only compute text or report diagnostics. Calls may name only
# declared uppercase macros whose bodies pass the same guard (GNU builtins are
# lowercase). Computed names, builtin calls and unknown expansions are refused
# before make runs, so no indirect path can reach shell/file/eval/guile.
_PURE_MAKE_FUNCTIONS = frozenset(
    [
        "if",
        "or",
        "and",
        "wildcard",
        "dir",
        "findstring",
        "firstword",
        "error",
        "info",
        "warning",
        "subst",
        "patsubst",
        "strip",
        "sort",
        "filter",
        "filter-out",
        "words",
        "word",
        "wordlist",
        "lastword",
        "notdir",
        "suffix",
        "basename",
        "addsuffix",
        "addprefix",
        "join",
        "origin",
        "flavor",
        "abspath",
        "realpath",
    ]
)
_PYTEST_ARGUMENTS = {
    "--keel-full-gate": None,
    "-p": r"no:cacheprovider",
    "-n": r"auto|[0-9]+",
    "--durations": r"[1-9][0-9]*|\$durations|\$\{durations\}",
    "--junitxml": r"[A-Za-z0-9_./-]+",
}
_MAKE_CONTROL_VARIABLES = frozenset(
    {"MAKE", "MAKEFILES", "MAKEFLAGS", "GNUMAKEFLAGS", "SHELL"}
)


def _require(condition, cause, source, fix):
    assert condition, f"{cause} on {source!r}. Fix: {fix}."


def _guard_expansions(text, source, macros):
    for match in re.finditer(r"\$(\$|[({]|.)", text):
        if match[1] not in ("(", "{"):
            continue
        tail = text[match.end() :]
        head = re.match(r"([A-Za-z0-9_][A-Za-z0-9_-]*)([)}]|[ \t,])", tail)
        call = re.match(r"call[ \t]+([A-Z_][A-Z0-9_]*)[ \t]*[,)}]", tail)
        safe = head and (
            head[2] in ")}"
            or head[1] in _PURE_MAKE_FUNCTIONS
            or (head[1] == "call" and call and call[1] in macros)
        )
        _require(
            safe,
            "Unjudged make expansion",
            source,
            "use static variable references and _PURE_MAKE_FUNCTIONS only",
        )


def _guard_makefile(text, source):
    # Only static assignments and explicit single-colon rules are modelled.
    # Includes are refused even when absent: make may remake them under -q/-n.
    # Match each logical line separately; whitespace must never eat a newline.
    logical = re.sub(r"\\\n[ \t]*", " ", text)
    macros = set(
        re.findall(r"^define ([A-Z_][A-Z0-9_]*)[ \t]*$", logical, re.MULTILINE)
    )
    in_define = False
    for number, line in enumerate(logical.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        where = f"{source}:{number}: {line}"
        _guard_expansions(line, where, macros)
        _require(
            not re.search(r"\bPYTEST_ADDOPTS\b", line),
            "Unjudged PYTEST_ADDOPTS",
            where,
            "remove PYTEST_ADDOPTS and pass only _PYTEST_ARGUMENTS explicitly",
        )
        definition = re.fullmatch(r"define ([A-Z_][A-Z0-9_]*)[ \t]*", line)
        if definition:
            _require(not in_define, "Nested make definition", where, "use flat macros")
            _require(
                definition[1] not in _MAKE_CONTROL_VARIABLES,
                "Unjudged make control macro",
                where,
                "use ordinary data macros without changing make execution",
            )
            in_define = True
            continue
        if line == "endef":
            _require(in_define, "Unmatched endef", where, "pair define and endef")
            in_define = False
            continue
        if in_define:
            continue
        if line.startswith("\t"):
            _require(
                not re.match(r"[ \t@-]*\+", line),
                "Unjudged forced recipe",
                where,
                "remove the + recipe prefix",
            )
            continue
        stripped = line.split("#", 1)[0].strip()
        _require(
            not re.match(r"(?:-?include|sinclude)\b", stripped),
            "Unjudged include remake",
            where,
            "inline the included makefile",
        )
        _require(
            not re.match(r"(?:ifdef|ifndef|ifeq|ifneq|else|endif)\b", stripped),
            "Unjudged conditional",
            where,
            "use unconditional explicit rules",
        )
        _require(
            "!=" not in line,
            "Unjudged shell assignment",
            where,
            "replace != with an inert literal assignment",
        )
        assignment = re.match(
            r"(?:(?:export|override|private) +)*([\w.-]+)[ \t]*[:?+]?=", stripped
        )
        if assignment:
            _require(
                assignment[1] not in _MAKE_CONTROL_VARIABLES
                and (
                    not assignment[1].startswith(".")
                    or assignment[1] == ".DEFAULT_GOAL"
                ),
                "Unjudged make control variable",
                where,
                "use ordinary data variables without changing make execution",
            )
            continue
        _require(
            not re.match(r"[^:]+::", stripped),
            "Unjudged double-colon rule",
            where,
            "merge the recipes into one single-colon rule",
        )
        _require(
            not re.match(
                r"[^:]+:[ \t]*(?:(?:export|override|private) +)*[\w.-]+[ \t]*[:?+]?=",
                stripped,
            ),
            "Unjudged target-specific variable",
            where,
            "pass ordinary assignments explicitly through the recursive make hop",
        )
        _require(
            re.fullmatch(r"[A-Za-z0-9_. -]+:[^;]*", stripped)
            and not stripped.startswith(("define ", "load ")),
            "Unjudged make syntax",
            where,
            "use explicit single-colon targets and separate tab recipes",
        )
        targets, prerequisites = stripped.split(":", 1)
        if any(target.startswith(".") for target in targets.split()):
            _require(
                targets == ".PHONY"
                and re.fullmatch(r"[A-Za-z0-9_. \t-]*", prerequisites),
                "Unjudged make special rule",
                where,
                "use only .PHONY with literal target names",
            )
    _require(
        not in_define, "Unclosed make definition", source, "close the macro with endef"
    )


def _rules(root):
    path = root / "Makefile"
    _require(path.is_file(), "Missing Makefile", path, "supply a readable Makefile")
    text = path.read_text(encoding="utf-8")
    _guard_makefile(text, path)
    rules = {}
    for rule in cs.make_target_rules(text):
        _require(
            rule.target not in rules,
            "Duplicate target",
            f"{path}: {rule.target}",
            "merge the target into one rule",
        )
        recipe_only = cs.make_target_rules(
            "probe:\n" + "".join("\t" + command + "\n" for command in rule.recipe)
        )[0]
        _require(
            rule.unresolved == recipe_only.unresolved,
            "Unjudged variable prerequisites",
            f"{path}: {rule.target}",
            "name prerequisite targets literally",
        )
        _require(
            rule.target not in {"Makefile", "__keel_slowtest_probe", "-"},
            "Unjudged makefile or probe remake",
            f"{path}: {rule.target}",
            "remove rules that remake makefiles or reserved probe targets",
        )
        rules[rule.target] = rule
    return rules


def _rule(rules, name, root):
    _require(
        name in rules,
        "Unjudged file prerequisite or missing target",
        f"{root}/Makefile: {name}",
        "declare an explicit target instead of a file or implicit prerequisite",
    )
    return rules[name]


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
    _require(
        proc.returncode in (0, 1) and not proc.stderr,
        "Make recipe expansion failed",
        f"{root}/Makefile: {rule.target}: {proc.stdout + proc.stderr}",
        "repair the make syntax and keep expansion free of side effects",
    )
    lines = proc.stdout.splitlines()
    commands = []
    for i in range(len(rule.recipe)):
        prefix = f"{probe}_{i}:"
        matches = [line for line in lines if line.startswith(prefix)]
        _require(
            len(matches) == 1,
            "Ambiguous make expansion output",
            f"{root}/Makefile: {rule.target}: {prefix}",
            "remove multiline or diagnostic-producing recipe expansions",
        )
        (line,) = matches
        commands.append(line.removeprefix(prefix))
    return commands


def _shell_words(command):
    try:
        lexer = shlex.shlex(
            command.replace("\\\n", ""), posix=True, punctuation_chars=";&|()\n"
        )
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError as error:
        raise AssertionError(
            f"Unjudged shell quoting on {command!r}. Fix: use balanced simple quoting."
        ) from error


def _make_hop(command):
    words = _shell_words(command)
    calls = [
        i
        for i, word in enumerate(words)
        if word == "__keel_make__"
        or (word == "make" and (i == 0 or words[i - 1] in ("--", ";", "&&")))
    ]
    if not calls:
        return [], []
    _require(
        len(calls) == 1, "Ambiguous make hop", command, "use one make call per line"
    )
    (start,) = calls
    _require(
        start == 0 or words[start - 1] == "--",
        "Unjudged make wrapper",
        command,
        "invoke make directly or after the gate wrapper's --",
    )
    goals, assignments = [], []
    for word in words[start + 1 :]:
        if re.match(r"^[A-Za-z_]\w*=", word):
            _require(
                word.split("=", 1)[0]
                not in _MAKE_CONTROL_VARIABLES | {"PYTEST_ADDOPTS"}
                and "$" not in word,
                "Unjudged make assignment",
                command,
                "pass literal data assignments without make controls or PYTEST_ADDOPTS",
            )
            assignments.append(word)
        else:
            _require(
                re.fullmatch(r"[A-Za-z0-9_-]+", word),
                "Unjudged make goal",
                command,
                "name each target literally without shell operators or flags",
            )
            goals.append(word)
    _require(goals, "Missing make goal", command, "name an explicit target")
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
        rule = _rule(rules, name, root)
        _require(
            not rule.unresolved,
            "Unjudged recipe references",
            rule,
            "use literal prerequisite targets and explicit make hops",
        )
        # GNU make executes a line with a literal MAKE reference under -n
        # even when that reference is in a branch that expands to nothing.
        _require(
            not any(re.search(r"\$[({]MAKE[)}]", command) for command in rule.recipe),
            "Unsafe recursive dry run",
            rule,
            "follow the make hop as data instead of dry-running it",
        )
        stack.extend(rule.prereqs)
        for command in _expanded_recipes(root, rule, assignments):
            _require(
                not re.match(r"[ \t@-]*\+", command),
                "Unsafe expanded forced recipe",
                command,
                "remove the expanded + prefix before dry-running the leaf",
            )
            goals, _ = _make_hop(command)
            _require(
                not goals,
                "Unsafe recursive dry run",
                f"{name}: {command}",
                "follow the make hop as data instead of dry-running it",
            )
    proc = subprocess.run(
        [
            "make",
            "-rR",
            "-f",
            "Makefile",
            "-n",
            target,
            "PY=" + sys.executable,
            *assignments,
        ],
        cwd=root,
        env=build_child_env(),
        capture_output=True,
        text=True,
        timeout=_timeout(),
    )
    _require(
        proc.returncode == 0,
        "Make leaf dry run failed",
        f"{root}/Makefile: {target}: {proc.stdout + proc.stderr}",
        "repair the leaf rule and its explicit prerequisites",
    )
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
    stack, seen, count, test_count = [("verify", (), False)], set(), 0, 0
    while stack:
        target, assignments, through_test = stack.pop()
        through_test = through_test or target == "test"
        key = (target, assignments, through_test)
        if key in seen:
            continue
        seen.add(key)
        rule = _rule(rules, target, root)
        stack.extend((name, assignments, through_test) for name in rule.prereqs)
        commands = _expanded_recipes(root, rule, assignments)
        recursive = False
        for command in commands:
            goals, overrides = _make_hop(command)
            recursive = recursive or bool(goals)
            inherited = dict(item.split("=", 1) for item in assignments)
            inherited.update(item.split("=", 1) for item in overrides)
            child = tuple(f"{key}={value}" for key, value in sorted(inherited.items()))
            stack.extend((name, child, through_test) for name in goals)
        if any(
            word == "pytest" or word.endswith("/pytest")
            for command in commands
            for word in _shell_words(command)
        ):
            # A recipe may run pytest and then recurse. Never dry-run such a
            # target; its expanded commands are already available as data.
            output = (
                "\n".join(commands)
                if recursive
                else _dry_run(target, root=root, assignments=assignments)
            )
            reached = _assert_full_pytests(output)
            count += reached
            if through_test:
                test_count += reached
    _require(
        count,
        "verify reaches zero pytest commands",
        root,
        "restore a full pytest invocation with --durations",
    )
    _require(
        test_count,
        "verify's test hop reaches zero full pytest commands",
        root,
        "restore the test hop and its full pytest invocation",
    )


def _assert_full_pytests(command):
    words = _shell_words(command)
    count = 0
    for i, word in enumerate(words):
        if word != "pytest" and not word.endswith("/pytest"):
            continue
        # Only an executable invocation counts; an echo mentioning pytest
        # cannot prove that the test hop runs any tests.
        start = i
        if i >= 2 and words[i - 1] == "-m":
            start = i - 2
            _require(
                words[start] == sys.executable,
                "Unjudged pytest interpreter",
                command,
                "invoke pytest through $(PY) -m pytest",
            )
        boundary = start
        while boundary and not all(char in ";&|()\n" for char in words[boundary - 1]):
            boundary -= 1
        _require(
            all(
                re.fullmatch(r"[A-Za-z_]\w*=[^$`]*", value)
                for value in words[boundary:start]
            ),
            "Unjudged pytest invocation prefix",
            command,
            "use a direct pytest invocation with literal environment assignments",
        )
        count += 1
        args = []
        for arg in words[i + 1 :]:
            if arg and all(char in ";&|()\n" for char in arg):
                break
            args.append(arg)
        options, position = set(), 0
        while position < len(args):
            option, equals, value = args[position].partition("=")
            _require(
                option in _PYTEST_ARGUMENTS,
                "Unjudged pytest argument",
                args[position],
                "use only _PYTEST_ARGUMENTS without test selections",
            )
            grammar = _PYTEST_ARGUMENTS[option]
            if grammar is None:
                valid = not equals
            else:
                if not equals:
                    position += 1
                    value = args[position] if position < len(args) else ""
                valid = re.fullmatch(grammar, value)
                if option == "--durations" and "$" in value:
                    binding = f"durations=$({sys.executable} scripts/config_get.py tests.durations)"
                    valid = (
                        valid
                        and boundary >= 2
                        and words[boundary - 2 : boundary] == [binding, "&&"]
                    )
            _require(
                valid,
                "Unjudged pytest option value",
                f"{option}={value}",
                "use the literal value grammar in _PYTEST_ARGUMENTS",
            )
            _require(
                option not in options,
                "Repeated pytest option",
                option,
                "pass each allowlisted option once",
            )
            options.add(option)
            position += 1
        _require(
            "--durations" in options,
            "pytest loses --durations",
            args,
            "pass --durations with a positive count from config",
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


_FULL_CHAIN = "verify:\n\t$(MAKE) test\ntest:\n\t$(PY) -m pytest --durations 10\n"


@pytest.mark.parametrize(
    ("prefix", "reason"),
    [
        ("-include missing.mk\nmissing.mk:\n\t@touch missing.mk\n", "include"),
        ("include missing.mk\nmissing.mk:\n\t@touch missing.mk\n", "include"),
        ("X := $(call shell,printf harmless)\n", "expansion"),
        ("X := $(shell printf harmless)\n", "expansion"),
        ("FN = shell\nX := $($(FN) printf harmless)\n", "expansion"),
        ("ifeq (1,1)\nX = yes\nendif\n", "conditional"),
        ("X != printf harmless\n", "shell assignment"),
        ("export PYTEST_ADDOPTS = -m slow\n", "PYTEST_ADDOPTS"),
        ("test: export PYTEST_ADDOPTS = -m slow\n", "PYTEST_ADDOPTS"),
        ("test: PYTEST_ADDOPTS = -m slow\n", "PYTEST_ADDOPTS"),
        ("other::\n\t@echo harmless\n", "double-colon"),
        ("other: FLAG = value\n", "target-specific"),
        ("other:\n\t+echo harmless\n", "forced recipe"),
    ],
    ids=[
        "absent-optional-include",
        "absent-required-include",
        "call-shell",
        "direct-shell",
        "computed-shell",
        "ifeq",
        "non-tab-shell-assignment",
        "export-addopts",
        "export-target-addopts",
        "target-addopts",
        "double-colon",
        "target-variable",
        "forced-recipe",
    ],
)
def test_guard_refuses_unsupported_make_forms_with_a_fix(tmp_path, prefix, reason):
    (tmp_path / "Makefile").write_text(prefix + _FULL_CHAIN, encoding="utf-8")
    with pytest.raises(AssertionError, match=reason) as failure:
        _rules(tmp_path)
    assert "Fix:" in str(failure.value)
    assert "Makefile" in str(failure.value)


@pytest.mark.parametrize(
    "args",
    [
        "tests/integration",
        "--collect-only",
        "$$FLAGS",
        '-xm "not slow"',
        "--desel=tests/test_sample.py::test_slow",
        "--unknown",
        "--durations nope",
        "--durations 0",
        "--durations $$OTHER",
        "--durations $(printf 10)",
    ],
    ids=[
        "positional",
        "collect-only",
        "shell-flags",
        "combined-short",
        "abbreviation",
        "unknown-option",
        "bad-duration",
        "zero-duration",
        "unknown-duration-variable",
        "duration-substitution",
    ],
)
def test_pytest_grammar_refuses_unknown_arguments_with_a_fix(tmp_path, args):
    (tmp_path / "Makefile").write_text(
        _FULL_CHAIN + f"\t$(PY) -m pytest --durations 10 {args}\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="pytest|expansion") as failure:
        _assert_verify_keeps_slow(tmp_path)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    "line",
    ["\tPYTEST_ADDOPTS='-m slow'\n", "\texport PYTEST_ADDOPTS='-m slow'\n"],
    ids=["later-addopts", "later-export-addopts"],
)
def test_later_recipe_addopts_is_refused(tmp_path, line):
    (tmp_path / "Makefile").write_text(_FULL_CHAIN + line, encoding="utf-8")
    with pytest.raises(AssertionError, match="PYTEST_ADDOPTS") as failure:
        _assert_verify_keeps_slow(tmp_path)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize("test_hop", ["", " test"], ids=["missing-test", "empty-test"])
def test_unfiltered_pytest_cannot_hide_a_dropped_test_hop(tmp_path, test_hop):
    (tmp_path / "Makefile").write_text(
        f"verify:\n\t$(MAKE) other{test_hop}\n"
        "other:\n\t$(PY) -m pytest --durations 10\n"
        "test:\n\t@echo no tests\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="test hop") as failure:
        _assert_verify_keeps_slow(tmp_path)
    assert "Fix:" in str(failure.value)


def test_file_prerequisite_is_refused_with_a_fix(tmp_path):
    (tmp_path / "Makefile").write_text(
        _FULL_CHAIN.replace("test:\n", "test: input.txt\n"), encoding="utf-8"
    )
    (tmp_path / "input.txt").write_text("present\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="input.txt") as failure:
        _assert_verify_keeps_slow(tmp_path)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    "recipe",
    [
        "\tCOUNT=10; $(PY) -m pytest --durations 10\n",
        "\t@echo make\n\t$(PY) -m pytest --durations 10\n",
    ],
    ids=["first-recipe-assignment", "echo-make"],
)
def test_unambiguous_recipe_lines_are_accepted(tmp_path, recipe):
    (tmp_path / "Makefile").write_text(
        "verify:\n\t$(MAKE) test\ntest:\n" + recipe, encoding="utf-8"
    )
    _assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    "prefix",
    [
        "sinclude missing.mk\n",
        "-include present.mk\n",
        "X := $(file >sentinel,unsafe)\n",
        "X := $(eval unsafe)\n",
        "X := $(guile unsafe)\n",
        "load unsafe.so\n",
        "define BAD\n$(call shell,printf harmless)\nendef\n",
        "define BAD\n$(shell printf harmless)\nendef\n",
        "define BAD\n$(call $(FN),printf harmless)\nendef\n",
        "Makefile:\n\t@touch Makefile\n",
        ".RECIPEPREFIX = >\n",
        "MAKEFLAGS = unsafe\n",
    ],
    ids=[
        "sinclude",
        "present-include",
        "file-function",
        "eval-function",
        "guile-function",
        "load-directive",
        "macro-builtin-call",
        "macro-shell",
        "macro-computed-call",
        "main-makefile-remake",
        "recipe-prefix",
        "makeflags",
    ],
)
def test_guard_refuses_the_parse_side_effect_class(tmp_path, prefix):
    (tmp_path / "Makefile").write_text(prefix + _FULL_CHAIN, encoding="utf-8")
    (tmp_path / "present.mk").write_text("# inert\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Fix:"):
        _rules(tmp_path)


@pytest.mark.parametrize(
    "recipe",
    [
        "\t$(PY) -m pytest --durations $$durations\n",
        "\t$$FLAGS $(PY) -m pytest --durations 10\n",
        "\t@echo pytest --durations 10\n",
    ],
    ids=["unbound-duration", "prefix-expansion", "echo-pytest"],
)
def test_only_a_known_pytest_invocation_counts(tmp_path, recipe):
    (tmp_path / "Makefile").write_text(
        "verify:\n\t$(MAKE) test\ntest:\n" + recipe, encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="pytest.*Fix:"):
        _assert_verify_keeps_slow(tmp_path)


def test_checked_macro_and_shared_test_prerequisite_are_accepted(tmp_path):
    (tmp_path / "Makefile").write_text(
        "define FULL_PYTEST\n$(PY) -m pytest --durations $(1)\nendef\n"
        "verify:\n\t$(MAKE) other test\n"
        "other: suite\ntest: suite\nsuite:\n\t$(call FULL_PYTEST,7)\n",
        encoding="utf-8",
    )
    _assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    "prefix",
    [
        ".SECONDEXPANSION:\n.PHONY: $$(shell printf harmless)\n",
        "define MAKEFILES\nmissing.mk\nendef\n",
    ],
    ids=["secondary-expansion", "control-macro"],
)
def test_guard_refuses_special_expansion_contexts(tmp_path, prefix):
    (tmp_path / "Makefile").write_text(prefix + _FULL_CHAIN, encoding="utf-8")
    with pytest.raises(AssertionError, match="Fix:"):
        _rules(tmp_path)
