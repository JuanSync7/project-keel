"""
title: Unit — exit_code_table (the generated exit-code table and the reader of what a script exits with)
kind: tests
layer: n/a
summary: read_members reads the enum from the helper's syntax tree in value order and refuses a missing class, a member that is not three literals, a shared value and a text that cannot be a table cell. read_script follows an entry function to the members it returns, retains codes from results the entry block discards even beside `finish` (assignment of the result of a status-returning function to a name `finish` is never handed, including annotated, unpacked and chained targets), leaves used values and no-value setup calls clean, counts a `fail` call anywhere in the module, marks a passed-through status read from a tool, refuses a `passthrough` of the entry function's result, a literal, a member or a module function returning only those, also signed, combined by arithmetic or `or`, or through a builtin such as `int`, while a child's status through the same forms reads, refuses `finish(passthrough(...))` on the entry line, and reports a bare integer, an unknown member and a function that can reach its end without returning as findings, never as codes. split_region refuses a marker that is missing, repeated or out of order. render and exit_cell are pure and sorted. load_policy names the config key it cannot read. main writes the region, leaves every byte outside it alone, keeps a CRLF guide CRLF, reaches a fixed point on the second run, exits 1 from --check on a stale table, CONFIG when config/project.json `doc_drift` cannot be used, with the loader's line for each key before the one refusal, and 2 when it refuses anything else, and refuses a guide reached through a symlink without writing through it.
"""

import ast
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import exit_code_table as et  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import process_state  # noqa: E402

pytestmark = pytest.mark.unit

_GUIDE = "docs/guides/limits.md"
_HELPER_SOURCE = (
    "import enum\n"
    "\n"
    "class ExitCode(enum.IntEnum):\n"
    "    LATE = (7, 'it was late', 'start earlier')\n"
    "    SUCCESS = (0, 'fine', 'nothing')\n"
    "    USAGE = (2, 'refused', 'fix the call')\n"
)
_TOOL = (
    "from exit_codes import ExitCode, finish, report\n"
    "\n"
    "def main():\n"
    "    if __doc__:\n"
    "        return report(ExitCode.USAGE, 'tool: no', 'x', 'drop it')\n"
    "    return ExitCode.SUCCESS\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    finish(main())\n"
)


def _project(tmp_path, helper=_HELPER_SOURCE, tool=_TOOL, newline="\n"):
    root = tmp_path / "proj"
    for folder in ("scripts", "config", "docs/guides"):
        (root / folder).mkdir(parents=True)
    (root / et.HELPER).write_text(helper, encoding="utf-8")
    (root / "scripts" / "tool.py").write_text(tool, encoding="utf-8")
    (root / "Makefile").write_text(
        "verify:\n\tpython scripts/tool.py\n", encoding="utf-8"
    )
    (root / et.MANIFEST).write_text(
        json.dumps({et.BLOCK: {et.GUIDE_KEY: _GUIDE, et.TARGET_KEY: "verify"}}),
        encoding="utf-8",
    )
    lines = ["# Limits", "", et.BEGIN, "stale", et.END, "", "prose"]
    with open(str(root / _GUIDE), "w", encoding="utf-8", newline="") as fh:
        fh.write("".join(line + newline for line in lines))
    return root


def _bytes(root):
    return (root / _GUIDE).read_bytes()


def test_a_conflict_hunk_exits_2(tmp_path, capsys):
    root = _project(tmp_path)
    (root / et.MANIFEST).write_text(
        "{\n"
        + "<" * 7
        + ' before\n"a": 1\n'
        + "=" * 7
        + '\n"a": 2\n'
        + ">" * 7
        + " after\n}\n",
        encoding="utf-8",
    )
    assert et.main([], root=str(root)) == ExitCode.USAGE
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1 and "config/project.json" in lines[0]
    assert "Traceback" not in lines[0]


# --- the enum ------------------------------------------------------------------


def test_read_members_reads_the_shipped_enum_and_agrees_with_the_import():
    members = et.read_members(str(_ROOT))
    assert [(m.name, m.value, m.meaning, m.action) for m in members] == [
        (m.name, m.value, m.meaning, m.action)
        for m in sorted(ExitCode, key=lambda m: m.value)
    ]
    assert members, "zero members"


def test_read_members_sorts_by_value(tmp_path):
    root = _project(tmp_path)
    assert [m.name for m in et.read_members(str(root))] == ["SUCCESS", "USAGE", "LATE"]


@pytest.mark.parametrize(
    ("helper", "said"),
    [
        ("X = 1\n", "defines no exit-code enum"),
        ("class ExitCode:\n    pass\n", "has no member"),
        ("class ExitCode:\n    A = 1\n", "is not `NAME = "),
        ("class ExitCode:\n    A = (True, 'm', 'a')\n", "is not `NAME = "),
        ("class ExitCode:\n    A = (1, 'm')\n", "is not `NAME = "),
        ("class ExitCode:\n    A: tuple = (1, 'm', 'a')\n", "is not `NAME = "),
        (
            "class ExitCode:\n    A = (1, 'm', 'a')\n    B: tuple = (2, 'm', 'a')\n",
            "is not `NAME = ",
        ),
        ("class ExitCode:\n    A = B = (1, 'm', 'a')\n", "is not `NAME = "),
        ("class ExitCode:\n    A = (1, 'm', WORDS)\n", "is not `NAME = "),
        ("class ExitCode:\n    A = (1, 'a | b', 'a')\n", "cannot be a table cell"),
        ("class ExitCode:\n    A = (1, 'm', ' ')\n", "cannot be a table cell"),
        (
            "class ExitCode:\n    A = (1, 'm', 'a')\n    B = (1, 'm', 'a')\n",
            "share a value",
        ),
        ("class ExitCode(:\n", "cannot read a Python file"),
    ],
)
def test_read_members_refuses_an_enum_it_cannot_tabulate(tmp_path, helper, said):
    root = _project(tmp_path, helper=helper)
    with pytest.raises(et.TableError) as caught:
        et.read_members(str(root))
    assert said in caught.value.what
    assert caught.value.on and caught.value.next_step


def test_read_members_refuses_a_missing_helper(tmp_path):
    root = _project(tmp_path)
    os.remove(str(root / et.HELPER))
    with pytest.raises(et.TableError, match="cannot read a Python file"):
        et.read_members(str(root))


# --- what a script exits with ----------------------------------------------------

_PRELUDE = "from exit_codes import ExitCode, fail, finish, passthrough, report\n\n"
_ENTRY = "\nif __name__ == '__main__':\n    finish(main())\n"


def _reading(tmp_path, body):
    root = _project(tmp_path, tool=_PRELUDE + body + _ENTRY)
    members = et.read_members(str(root))
    return et.read_script(str(root / "scripts" / "tool.py"), "scripts/tool.py", members)


@pytest.mark.parametrize(
    "entry",
    [
        "    main(); finish(ExitCode.SUCCESS)\n",
        "    status = main()\n    finish(ExitCode.SUCCESS)\n",
        "    status: ExitCode = main()\n    finish(ExitCode.SUCCESS)\n",
        "    status = main()\n    print(status)\n    finish(ExitCode.SUCCESS)\n",
        "    status: ExitCode = main()\n    print(status)\n    finish(ExitCode.SUCCESS)\n",
        "    a = b = main()\n    finish(ExitCode.SUCCESS)\n",
        "    a, b = main()\n    finish(ExitCode.SUCCESS)\n",
        "    [a, *b] = main()\n    finish(ExitCode.SUCCESS)\n",
        "    a = (b, c) = main()\n    finish(ExitCode.SUCCESS)\n",
    ],
    ids=[
        "expression",
        "unused-name",
        "unused-annotated-name",
        "bound-printed",
        "annotated-bound-printed",
        "chained",
        "tuple",
        "list-starred",
        "mixed-chained",
    ],
)
def test_read_tree_keeps_codes_from_a_dropped_result_beside_finish(entry):
    tree = ast.parse(
        _PRELUDE + "def main():\n"
        "    return report(ExitCode.USAGE, 'bad', 'input', 'fix it')\n"
        "if __name__ == '__main__':\n" + entry
    )
    reading = et.read_tree(tree, "tool.py", frozenset({"SUCCESS"}))
    assert reading.names == {"SUCCESS", "USAGE"}, reading
    assert not reading.passes, reading
    assert reading.findings == [], reading
    assert [(node.lineno, name) for node, name in et.dropped_results(tree)] == [
        (6, "main")
    ]


@pytest.mark.parametrize(
    "entry",
    [
        "    finish(main())\n",
        "    setup()\n    finish(main())\n",
        "    status = main()\n    finish(status)\n",
        "    status: ExitCode = main()\n    finish(status)\n",
        "    a = b = main()\n    finish(a)\n",
        "    a = b = main()\n    finish(b)\n",
        "    print(main())\n    finish(ExitCode.SUCCESS)\n",
        "    if main():\n        print('used')\n    finish(ExitCode.SUCCESS)\n",
    ],
    ids=[
        "forwarded",
        "setup",
        "bound",
        "annotated-bound",
        "chained-first",
        "chained-last",
        "printed",
        "condition",
    ],
)
def test_dropped_results_leaves_used_values_and_no_value_calls_alone(entry):
    tree = ast.parse(
        _PRELUDE + "def setup():\n    return None\n"
        "def main():\n    return ExitCode.SUCCESS\n"
        "if __name__ == '__main__':\n" + entry
    )
    assert et.dropped_results(tree) == []
    reading = et.read_tree(tree, "tool.py", frozenset({"SUCCESS"}))
    assert reading == et.Reading(frozenset({"SUCCESS"}), passes=False, findings=[])


@pytest.mark.parametrize(
    ("setup", "entry", "drops"),
    [
        (
            "import argparse\ndef build_parser():\n    return argparse.ArgumentParser()\n",
            "    parser = build_parser()\n    args = parser.parse_args()\n"
            "    finish(main(args))\n",
            [],
        ),
        (
            "import os\ndef find_root():\n    return '/project'\n",
            "    root = find_root()\n    os.chdir(root)\n    finish(main())\n",
            [],
        ),
        (
            "def warm_cache():\n    return {}\n",
            "    warm_cache()\n    finish(main())\n",
            ["warm_cache"],
        ),
    ],
    ids=["parser", "root", "bare-ordinary-result"],
)
def test_read_script_leaves_ordinary_results_out_of_exit_codes(
    tmp_path, setup, entry, drops
):
    source = (
        _PRELUDE + setup + "def main(*args):\n    return ExitCode.SUCCESS\n"
        "if __name__ == '__main__':\n" + entry
    )
    root = _project(tmp_path, tool=source)
    reading = et.read_script(
        str(root / "scripts/tool.py"), "scripts/tool.py", et.read_members(str(root))
    )
    assert reading == et.Reading(frozenset({"SUCCESS"}), passes=False, findings=[])
    assert [name for _node, name in et.dropped_results(ast.parse(source))] == drops


@pytest.mark.parametrize(
    "binding",
    [
        "value = helper()",
        "value: str = helper()",
        "a = value = helper()",
        "value, other = helper()",
        "[value, *other] = helper()",
    ],
)
def test_binding_an_ordinary_result_counts_as_using_it(binding):
    tree = ast.parse(
        _PRELUDE + "def helper():\n    return ('text', 'other')\n"
        "def main():\n    return ExitCode.SUCCESS\n"
        "if __name__ == '__main__':\n    "
        + binding
        + "\n    print(value)\n    finish(main())\n"
    )
    assert et.dropped_results(tree) == []
    assert et.read_tree(tree, "tool.py", frozenset({"SUCCESS"})).findings == []


@pytest.mark.parametrize(
    ("body", "drops"),
    [
        ("    return ExitCode.SUCCESS\n", ["helper"]),
        ("    return ExitCode.USAGE\n", ["helper"]),
        ("    return report(ExitCode.USAGE, 'bad', 'input', 'fix')\n", ["helper"]),
        ("    return passthrough(child())\n", ["helper"]),
        ("    status = leaf()\n    return status\n", ["helper"]),
        ("    return leaf() if ready else ExitCode.SUCCESS\n", ["helper"]),
        ("    def inner():\n        return leaf()\n    return inner()\n", ["helper"]),
        ("    if ready:\n        return leaf()\n    return {}\n", []),
        ("    return leaf() if ready else {}\n", []),
        ("    return 3\n", []),
        ("    status = leaf()\n    status += 1\n    return status\n", []),
        ("    return helper()\n", []),
        ("    status = status\n    return status\n", []),
    ],
    ids=[
        "member",
        "failure-member",
        "report",
        "passthrough",
        "assigned-call",
        "conditional",
        "nested-call",
        "mixed-returns",
        "mixed-conditional",
        "integer",
        "opaque-name",
        "recursive-call",
        "cyclic-name",
    ],
)
def test_only_status_returning_helpers_can_drop_a_bound_result(body, drops):
    tree = ast.parse(
        _PRELUDE + "def leaf():\n    return ExitCode.SUCCESS\n"
        "def helper():\n" + body + "def main():\n    return ExitCode.SUCCESS\n"
        "if __name__ == '__main__':\n"
        "    status = helper()\n    print(status)\n    finish(main())\n"
    )
    assert [name for _node, name in et.dropped_results(tree)] == drops


def test_an_entry_function_is_a_status_even_when_its_return_is_invalid():
    tree = ast.parse(
        _PRELUDE + "def run():\n    return 3\n"
        "if __name__ == '__main__':\n"
        "    status = run()\n    print(status)\n    finish(run())\n"
    )
    assert [name for _node, name in et.dropped_results(tree)] == ["run"]
    assert (
        "not an exit code"
        in et.read_tree(tree, "tool.py", frozenset({"SUCCESS"})).findings[0]
    )


@pytest.mark.parametrize(
    ("body", "names", "passes"),
    [
        ("def main():\n    return ExitCode.SUCCESS\n", {"SUCCESS"}, False),
        (
            "def main():\n    return report(ExitCode.LATE, 'a', 'b', 'c')\n",
            {"LATE"},
            False,
        ),
        (
            "def main():\n"
            "    return report(ExitCode.LATE if x else ExitCode.USAGE, 'a', 'b', 'c')\n",
            {"LATE", "USAGE"},
            False,
        ),
        (
            "def main():\n"
            "    return ExitCode.SUCCESS if x else report(ExitCode.USAGE, 'a', 'b', 'c')\n",
            {"SUCCESS", "USAGE"},
            False,
        ),
        ("def main():\n    return passthrough(run())\n", set(), True),
        (
            "def main():\n"
            "    rc = report(ExitCode.USAGE, 'a', 'b', 'c')\n"
            "    return rc\n",
            {"USAGE"},
            False,
        ),
        (
            "def _refuse():\n"
            "    return report(ExitCode.USAGE, 'a', 'b', 'c')\n\n"
            "def main():\n"
            "    if x:\n"
            "        return _refuse()\n"
            "    return ExitCode.SUCCESS\n",
            {"SUCCESS", "USAGE"},
            False,
        ),
        (
            "def _load():\n"
            "    fail(ExitCode.LATE, 'a', 'b', 'c')\n\n"
            "def main():\n"
            "    _load()\n"
            "    return ExitCode.SUCCESS\n",
            {"SUCCESS", "LATE"},
            False,
        ),
        (
            "def main():\n"
            "    def inner():\n"
            "        return 5\n"
            "    return ExitCode.SUCCESS\n",
            {"SUCCESS"},
            False,
        ),
    ],
)
def test_read_script_follows_the_grammar_to_members(tmp_path, body, names, passes):
    reading = _reading(tmp_path, body)
    assert reading.findings == []
    assert (reading.names, reading.passes) == (names, passes)


@pytest.mark.parametrize(
    ("body", "said"),
    [
        ("def main():\n    return 1\n", "scripts/tool.py:4"),
        ("def main():\n    return ExitCode.USAGE\n", "scripts/tool.py:4"),
        ("def main():\n    return int(ExitCode.SUCCESS)\n", "scripts/tool.py:4"),
        ("def main():\n    return other.main()\n", "scripts/tool.py:4"),
        (
            "def main():\n    if x:\n        return ExitCode.SUCCESS\n",
            "scripts/tool.py",
        ),
        ("def main():\n    pass\n", "scripts/tool.py"),
        (
            "def main():\n    return report(ExitCode.SUCCESS, 'a', 'b', 'c')\n",
            "has nothing to report",
        ),
        (
            "def main():\n    rc = ExitCode.SUCCESS\n    rc, out = pair()\n    return rc\n",
            "scripts/tool.py:6: returns `rc`",
        ),
        (
            "def main():\n    rc = ExitCode.SUCCESS\n    rc += 5\n    return rc\n",
            "scripts/tool.py:6: returns `rc`",
        ),
        ("def main(rc=7):\n    return rc\n", "scripts/tool.py:4: returns `rc`"),
        ("def main():\n    rc = rc\n    return rc\n", "scripts/tool.py"),
        (
            "def main():\n    return report(ExitCode.GHOST, 'a', 'b', 'c')\n",
            "names ExitCode.GHOST, which scripts/exit_codes.py does not define",
        ),
    ],
)
def test_read_script_reports_a_return_outside_the_grammar_and_reads_no_code_from_it(
    tmp_path, body, said
):
    reading = _reading(tmp_path, body)
    assert len(reading.findings) == 1, reading.findings
    assert said in reading.findings[0]
    # A failure member returned without `report` is still the code the
    # process exits with; no other unreadable return yields a name.
    assert reading.names <= {"SUCCESS", "USAGE"} and not reading.passes
    assert ("USAGE" in reading.names) == ("return ExitCode.USAGE" in body)


# A status the script chose itself, handed to `passthrough` as if a wrapped
# tool had produced it: each is a finding at the `passthrough` call's line.
_OWN_STATUS = "passthrough wraps a wrapped tool's status, never this script's own"


@pytest.mark.parametrize(
    ("body", "line"),
    [
        ("def main():\n    return passthrough(main())\n", 4),
        ("def main():\n    rc = main()\n    return passthrough(rc)\n", 5),
        (
            "def main2():\n    if x:\n        return 1\n    return 0\n\n"
            "def main():\n    return passthrough(main2())\n",
            9,
        ),
        ("def main():\n    return passthrough(0)\n", 4),
        ("def main():\n    rc = 1 if x else 0\n    return passthrough(rc)\n", 5),
        (
            "def _check():\n    return report(ExitCode.USAGE, 'a', 'b', 'c')\n\n"
            "def main():\n    return passthrough(_check())\n",
            7,
        ),
        ("def main():\n    rc = rc\n    return passthrough(rc)\n", 5),
        ("def main():\n    return passthrough(-1)\n", 4),
        ("def main():\n    return passthrough(int(main()))\n", 4),
        ("def main():\n    return passthrough(int(str(main())))\n", 4),
        ("def main():\n    return passthrough(max(main(), 1))\n", 4),
        ("def main():\n    return passthrough(main() or 0)\n", 4),
        ("def main():\n    return passthrough(main() + 0)\n", 4),
        (
            "def main2():\n    return 1 if x else 0\n\n"
            "def main():\n    return passthrough(int(main2()))\n",
            7,
        ),
    ],
    ids=[
        "the entry function",
        "a name bound to the entry function",
        "a module function returning its own integers",
        "a literal",
        "a name bound to literals",
        "a module function returning a member",
        "a name bound to itself",
        "a negative literal",
        "the entry function through a builtin",
        "the entry function through two builtins",
        "the entry function among literals through a builtin",
        "the entry function or a literal",
        "the entry function plus a literal",
        "a module function returning integers through a builtin",
    ],
)
def test_passthrough_of_the_entry_function_is_refused(tmp_path, body, line):
    reading = _reading(tmp_path, body)
    said = [f for f in reading.findings if _OWN_STATUS in f]
    assert said and all(f.startswith("scripts/tool.py:%d: " % line) for f in said), (
        reading.findings
    )
    assert not reading.passes, reading


@pytest.mark.parametrize(
    "entry",
    [
        "    finish(passthrough(main()))\n",
        "    rc = main()\n    finish(passthrough(rc))\n",
        "    finish(passthrough(subprocess.run(['tool']).returncode))\n",
    ],
    ids=["of main", "of a name bound to main", "of a wrapped status"],
)
def test_finish_of_passthrough_is_refused(tmp_path, entry):
    tool = (
        "import subprocess\n" + _PRELUDE + "def main():\n"
        "    return passthrough(subprocess.run(['tool']).returncode)\n\n"
        "if __name__ == '__main__':\n" + entry
    )
    root = _project(tmp_path, tool=tool)
    members = et.read_members(str(root))
    reading = et.read_script(
        str(root / "scripts" / "tool.py"), "scripts/tool.py", members
    )
    line = 7 + entry.count("\n")
    assert (
        "scripts/tool.py:%d: the entry line is finish(main()); call passthrough "
        "inside main where the wrapped tool's status is read" % line
    ) in reading.findings, reading.findings


@pytest.mark.parametrize(
    "body",
    [
        "import subprocess\n\n"
        "def main():\n    return passthrough(subprocess.run(['x']).returncode)\n",
        "def main():\n    return passthrough(target['returncode'])\n",
        "import subprocess\n\n"
        "def _run():\n    return subprocess.run(['x']).returncode\n\n"
        "def main():\n    return passthrough(_run())\n",
        # A function that turns another process's status into an int: one of
        # its returns reads that status, so it is not the script's own choice.
        "def _status(code):\n    if code is None:\n        return 0\n"
        "    return code & 255\n\n"
        "def main():\n    try:\n        run()\n    except SystemExit as stop:\n"
        "        return passthrough(_status(stop.code))\n"
        "    return ExitCode.SUCCESS\n",
        "import subprocess\n\n"
        "def main():\n    return passthrough(int(subprocess.call(['x'])))\n",
        "import subprocess\n\n"
        "def main():\n    return passthrough(subprocess.call(['x']) or 0)\n",
        # A builtin the module rebinds is the module's own function, followed
        # to its returns like any other.
        "import subprocess\n\n"
        "def int(value):\n    return subprocess.call([value])\n\n"
        "def main():\n    return passthrough(int(3))\n",
    ],
    ids=[
        "a child's returncode",
        "a recorded status",
        "a helper that runs the tool",
        "a helper that converts the tool's status",
        "a child's status through a builtin",
        "a child's status or a literal",
        "a module function that shadows a builtin",
    ],
)
def test_passthrough_of_a_wrapped_status_reads(tmp_path, body):
    reading = _reading(tmp_path, body)
    assert reading.findings == []
    assert reading.passes


def test_exit_codes_maps_names_to_values_by_the_given_root(tmp_path):
    root = _project(tmp_path)
    values, passes = et.exit_codes(str(root / "scripts" / "tool.py"), root=str(root))
    assert (values, passes) == ({0, 2}, False)


def test_gate_scripts_refuses_a_target_the_makefile_does_not_have(tmp_path):
    root = _project(tmp_path)
    assert et.gate_scripts(str(root), "verify") == ["scripts/tool.py"]
    with pytest.raises(et.TableError, match="no such target"):
        et.gate_scripts(str(root), "absent")


# --- the region ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "no markers\n",
        et.BEGIN + "\n",
        et.END + "\n",
        "%s\n%s\n" % (et.END, et.BEGIN),
        "%s\n%s\n%s\n" % (et.BEGIN, et.BEGIN, et.END),
        "%s\n%s\n%s\n" % (et.BEGIN, et.END, et.END),
        "  %s\n%s\n" % (et.BEGIN, et.END),
        "text %s\n%s\n" % (et.BEGIN, et.END),
    ],
)
def test_split_region_refuses_markers_that_do_not_bracket_one_region(text):
    with pytest.raises(et.TableError) as caught:
        et.split_region(text, "guide.md")
    assert caught.value.on == "guide.md"


def test_split_region_returns_the_three_parts_and_loses_no_byte():
    text = "a\r\n%s\r\nold\r\n%s\r\nz" % (et.BEGIN, et.END)
    before, region, after = et.split_region(text, "g")
    assert (before, region, after) == (
        "a\r\n%s\r\n" % et.BEGIN,
        "old\r\n",
        "%s\r\nz" % et.END,
    )
    assert before + region + after == text


def test_exit_cell_sorts_the_values_and_names_a_passed_through_status():
    assert et.exit_cell({130, 2, 0}, passes=False) == "0, 2, 130"
    assert et.exit_cell({0}, passes=True) == "0, " + et.PASSES_THROUGH
    assert et.exit_cell(set(), passes=True) == et.PASSES_THROUGH


def test_render_is_sorted_and_does_not_depend_on_the_order_it_is_given():
    members = [et.Member("SUCCESS", 0, "fine", "nothing"), et.Member("B", 2, "m", "a")]
    rows = [("scripts/b.py", {2, 0}, False), ("scripts/a.py", {0}, True)]
    text = et.render(members, rows)
    assert text == et.render(members, list(reversed(rows)))
    assert text.splitlines() == [
        "| Exit | Name | Meaning | What to do |",
        "|------|------|---------|------------|",
        "| 0 | `SUCCESS` | fine | nothing |",
        "| 2 | `B` | m | a |",
        "",
        "| Script | Exit |",
        "|--------|------|",
        "| `scripts/a.py` | 0, passes through |",
        "| `scripts/b.py` | 0, 2 |",
    ]
    assert et.render(members, rows, "\r\n") == text.replace("\n", "\r\n")


@pytest.mark.parametrize(
    ("manifest", "named"),
    [
        ("{", et.MANIFEST),
        ("[]", et.BLOCK),
        ("{}", et.BLOCK),
        (json.dumps({et.BLOCK: []}), et.BLOCK),
        (json.dumps({et.BLOCK: {et.TARGET_KEY: "verify"}}), et.GUIDE_KEY),
        (json.dumps({et.BLOCK: {et.GUIDE_KEY: " ", et.TARGET_KEY: "v"}}), et.GUIDE_KEY),
        (
            json.dumps({et.BLOCK: {et.GUIDE_KEY: "g.md", et.TARGET_KEY: 3}}),
            et.TARGET_KEY,
        ),
    ],
)
def test_load_policy_names_the_key_it_cannot_read(tmp_path, manifest, named):
    root = _project(tmp_path)
    (root / et.MANIFEST).write_text(manifest, encoding="utf-8")
    with pytest.raises(et.TableError) as caught:
        et.load_policy(str(root))
    assert named in caught.value.on


def test_load_policy_reads_this_checkout():
    guide, target = et.load_policy(str(_ROOT))
    assert (_ROOT / guide).is_file() and target


# --- the command -------------------------------------------------------------------


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_main_writes_the_region_only_and_a_second_run_changes_nothing(
    tmp_path, capsys, newline
):
    root = _project(tmp_path, newline=newline)
    before = _bytes(root)
    assert et.main(["--check"], root=str(root)) == ExitCode.FAILURE
    assert _bytes(root) == before, "--check wrote"
    err = capsys.readouterr().err
    assert "the exit-code table is stale" in err and "make exit-codes" in err

    assert et.main([], root=str(root)) is ExitCode.SUCCESS
    first = _bytes(root)
    head, _region, tail = et.split_region(before.decode("utf-8"), _GUIDE)
    text = first.decode("utf-8")
    assert text.startswith(head) and text.endswith(tail)
    assert b"stale" not in first
    assert b"| 7 | `LATE` | it was late | start earlier |" + newline.encode() in first
    assert b"| `scripts/tool.py` | 0, 2 |" + newline.encode() in first
    assert (newline == "\r\n") == (b"\r\n" in first)
    assert first.count(b"\n") == first.count(newline.encode())

    assert et.main([], root=str(root)) is ExitCode.SUCCESS
    assert _bytes(root) == first
    assert et.main(["--check"], root=str(root)) is ExitCode.SUCCESS
    assert not os.path.exists(str(root / _GUIDE) + ".tmp")
    assert "unchanged" in capsys.readouterr().out


def test_main_refuses_a_guide_reached_through_a_symlink_and_writes_nothing(
    tmp_path, capsys
):
    root = _project(tmp_path)
    outside = tmp_path / "outside.md"
    os.replace(str(root / _GUIDE), str(outside))
    os.symlink(str(outside), str(root / _GUIDE))
    before = outside.read_bytes()
    assert et.main([], root=str(root)) == ExitCode.USAGE
    assert outside.read_bytes() == before
    assert "symlink" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("damage", "said"),
    [
        (lambda root: os.remove(str(root / _GUIDE)), "cannot read the guide"),
        (
            lambda root: (root / _GUIDE).write_text("no markers\n", encoding="utf-8"),
            "does not hold exactly one",
        ),
        (lambda root: os.remove(str(root / "scripts" / "tool.py")), "does not exist"),
        (
            lambda root: (root / "scripts" / "tool.py").write_text(
                "def main():\n    return 1\n\nif __name__ == '__main__':\n    main()\n",
                encoding="utf-8",
            ),
            "scripts/tool.py",
        ),
        (
            lambda root: (root / "Makefile").write_text("verify:\n\ttrue\n", "utf-8"),
            "zero items",
        ),
    ],
)
def test_main_refuses_what_it_cannot_tabulate_in_both_modes(
    tmp_path, capsys, damage, said
):
    root = _project(tmp_path)
    damage(root)
    for argv in ([], ["--check"]):
        assert et.main(argv, root=str(root)) == ExitCode.USAGE
        err = capsys.readouterr().err
        assert said in err and err.count("\n") == 1
    assert et.table_findings(str(root)) != []


@pytest.mark.parametrize(
    ("manifest", "said"),
    [
        (None, "config/project.json does not exist"),
        ("{", "config/project.json cannot be read as JSON"),
        ("{}", "[not set] doc_drift.gate_target"),
        (
            json.dumps({et.BLOCK: {et.GUIDE_KEY: "/abs.md", et.TARGET_KEY: "v"}}),
            "doc_drift.limits_guide is string",
        ),
    ],
    ids=["absent", "not-json", "empty", "absolute-guide"],
)
def test_main_refuses_a_config_fault_with_the_config_exit_in_both_modes(
    tmp_path, capsys, manifest, said
):
    """The doc_drift block is read through scripts/config_loader.py: a fault in
    it exits CONFIG, and the loader's lines come before the one refusal."""
    root = _project(tmp_path)
    if manifest is None:
        os.remove(str(root / et.MANIFEST))
    else:
        (root / et.MANIFEST).write_text(manifest, encoding="utf-8")
    before = _bytes(root)
    for argv in ([], ["--check"]):
        assert et.main(argv, root=str(root)) == ExitCode.CONFIG
        err = capsys.readouterr().err
        assert said in err, err
        assert err.splitlines()[-1].startswith("exit_code_table: "), err
    assert _bytes(root) == before


def test_an_empty_block_lists_both_keys_sorted_before_the_refusal(tmp_path, capsys):
    root = _project(tmp_path)
    (root / et.MANIFEST).write_text("{}", encoding="utf-8")
    assert et.main([], root=str(root)) == ExitCode.CONFIG
    lines = capsys.readouterr().err.splitlines()
    assert [ln.split("  ")[0] for ln in lines[:2]] == [
        "[not set] doc_drift.gate_target",
        "[not set] doc_drift.limits_guide",
    ], lines
    assert len(lines) == 3 and lines[2].startswith("exit_code_table: "), lines


def test_the_shipped_table_is_current():
    assert et.table_findings(str(_ROOT)) == []


# --- the shell helper --------------------------------------------------------------


def _shell_project(tmp_path, *, enabled=True):
    root = _project(tmp_path)
    manifest = json.loads((root / et.MANIFEST).read_text(encoding="utf-8"))
    manifest["shell"] = {"enabled": enabled}
    (root / et.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _helper_sh(root):
    return root / et.HELPER_SH


def test_render_shell_names_every_member_in_value_order_with_its_meaning(tmp_path):
    text = et.render_shell(et.read_members(str(_project(tmp_path))))
    assert text.startswith("#!/bin/sh\n# title: ")
    assignments = [ln for ln in text.splitlines() if ln.startswith("EXIT_")]
    assert assignments == ["EXIT_SUCCESS=0", "EXIT_USAGE=2", "EXIT_LATE=7"]
    assert "# it was late -- start earlier\nEXIT_LATE=7\n" in text
    assert "exit_fail() {" in text and "exit_passthrough() {" in text
    assert "\r" not in text and text.endswith("}\n")


@pytest.mark.parametrize("missing", ["SUCCESS", "USAGE"])
def test_render_shell_refuses_an_enum_without_a_member_the_helper_uses(
    tmp_path, missing
):
    members = [m for m in et.read_members(str(_project(tmp_path))) if m.name != missing]
    with pytest.raises(et.TableError) as caught:
        et.render_shell(members)
    assert missing in caught.value.on and caught.value.next_step


def test_main_shell_writes_the_helper_and_a_second_run_changes_nothing(
    tmp_path, capsys
):
    root = _shell_project(tmp_path)
    guide = _bytes(root)
    assert et.main(["--shell", "--check"], root=str(root)) == ExitCode.FAILURE
    assert not _helper_sh(root).exists(), "--check wrote"
    err = capsys.readouterr().err
    assert et.HELPER_SH in err and "make exit-codes-sh" in err

    assert et.main(["--shell"], root=str(root)) is ExitCode.SUCCESS
    first = _helper_sh(root).read_bytes()
    assert first == et.render_shell(et.read_members(str(root))).encode("utf-8")
    assert "wrote" in capsys.readouterr().out

    assert et.main(["--shell"], root=str(root)) is ExitCode.SUCCESS
    assert _helper_sh(root).read_bytes() == first
    assert "unchanged" in capsys.readouterr().out
    assert et.main(["--shell", "--check"], root=str(root)) is ExitCode.SUCCESS
    assert "up to date" in capsys.readouterr().out
    assert not os.path.exists(str(_helper_sh(root)) + ".tmp")
    assert _bytes(root) == guide, "--shell touched the guide"


def test_main_shell_check_fails_a_helper_the_enum_has_moved_past(tmp_path, capsys):
    root = _shell_project(tmp_path)
    assert et.main(["--shell"], root=str(root)) is ExitCode.SUCCESS
    (root / et.HELPER).write_text(
        _HELPER_SOURCE.replace("(7,", "(8,"), encoding="utf-8"
    )
    before = _helper_sh(root).read_bytes()
    capsys.readouterr()
    assert et.main(["--shell", "--check"], root=str(root)) == ExitCode.FAILURE
    assert "is stale" in capsys.readouterr().err
    assert _helper_sh(root).read_bytes() == before


def test_main_shell_writes_and_judges_the_helper_with_shell_off(tmp_path, capsys):
    """`shell.enabled` switches the shell tools only: the helper ships and is
    judged whatever it says, so turning shell on later is that one key."""
    root = _shell_project(tmp_path, enabled=False)
    assert et.main(["--shell", "--check"], root=str(root)) == ExitCode.FAILURE
    assert "absent" in capsys.readouterr().err
    assert et.main(["--shell"], root=str(root)) is ExitCode.SUCCESS
    assert _helper_sh(root).is_file()
    assert et.main(["--shell", "--check"], root=str(root)) is ExitCode.SUCCESS
    assert "up to date" in capsys.readouterr().out


def test_main_shell_refuses_a_helper_reached_through_a_symlink(tmp_path, capsys):
    root = _shell_project(tmp_path)
    outside = tmp_path / "outside.sh"
    outside.write_text("old\n", encoding="utf-8")
    os.symlink(str(outside), str(_helper_sh(root)))
    assert et.main(["--shell"], root=str(root)) == ExitCode.USAGE
    assert outside.read_text(encoding="utf-8") == "old\n"
    assert "symlink" in capsys.readouterr().err


def test_the_shipped_shell_helper_is_current(capsys):
    assert et.main(["--shell", "--check"], root=str(_ROOT)) is ExitCode.SUCCESS
    assert "up to date" in capsys.readouterr().out


def test_check_exit_codes_judges_the_shell_helper_and_exit_codes_sh_writes_it():
    import check_structure as cs

    text = (_ROOT / "Makefile").read_text(encoding="utf-8")
    recipes = {r.target: r.recipe for r in cs.make_target_rules(text)}
    assert (
        "$(PY) scripts/exit_code_table.py --shell --check"
        in recipes["check-exit-codes"]
    )
    assert recipes["exit-codes-sh"] == ["$(PY) scripts/exit_code_table.py --shell"]


def test_the_helper_meets_the_shell_header_and_effect_rules(tmp_path):
    import check_structure as cs

    text = et.render_shell(et.read_members(str(_ROOT)))
    assert cs._shell_header_findings({et.HELPER_SH: text}) == []
    assert cs._shell_effect_findings(
        {et.HELPER_SH: text}, set(), set(), set(), lambda p: None
    ) == ([], [])


# The shell constructs dash and busybox sh do not read, each with a line that
# uses it. No POSIX shell or shellcheck runs here, so the helper is checked
# against this list, never proven under dash. `$((` is POSIX arithmetic, so
# only a `((` with no `$` before it is bash's.
_SH_BASH_ONLY = (
    ("[[", r"\[\[", '[[ "$#" -ne 4 ]] && exit 2'),
    ("local", r"\blocal\b", "local part"),
    ("function", r"\bfunction\b", "function f { :; }"),
    ("an array", r"\b\w+=\(|\$\{#?\w+\[|\b\w+\[[^]\s]*\]=", 'set -- "${parts[0]}"'),
    ("== in a test", r"==", '[ "$1" == x ]'),
    ("$'", r"\$'", "printf $'%s\\n' x"),
    ("process substitution", r"[<>]\(", "cat <(true)"),
    ("source", r"\bsource\b", "source ./x.sh"),
    ("declare", r"\bdeclare\b", "declare part=1"),
    ("let", r"\blet\b", "let part=1"),
    ("((", r"(?<!\$)\(\(", "(( part++ ))"),
    ("<<<", r"<<<", "cat <<< x"),
    ("&>", r"&>", "true &>/dev/null"),
    ("a replacement", r"\$\{#?\w+/", 'echo "${part//a/b}"'),
    ("a substring", r"\$\{\w+:(?![-=?+])", 'echo "${part:0:1}"'),
)


def _bash_only(text):
    """The names of the `_SH_BASH_ONLY` constructs *text* uses outside its
    comment lines, each once, in list order."""
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    return [name for name, pattern, _ in _SH_BASH_ONLY if re.search(pattern, code)]


def test_the_helper_uses_no_construct_a_posix_shell_does_not_read():
    text = et.render_shell(et.read_members(str(_ROOT)))
    assert _bash_only(text) == []


@pytest.mark.parametrize(
    "name, line",
    [(n, u) for n, _, u in _SH_BASH_ONLY],
    ids=[n for n, _, _ in _SH_BASH_ONLY],
)
def test_each_bash_only_construct_in_the_helper_is_found(name, line):
    text = et.render_shell(et.read_members(str(_ROOT)))
    assert _bash_only(text + line + "\n") == [name]
    assert _bash_only(text + "# " + line + "\n") == []


# POSIX lines that look like a bash-only construct of the list and are not.
_SH_POSIX_LOOKALIKES = (
    'echo "${part:-/tmp}" "${part:=1}" "${part:?no}" "${part:+y}"',
    'echo "${part#a}" "${part%/*}" "${#part}"',
    "echo x >&2 2>&1 <&0",
    "cat <<EOF",
)


@pytest.mark.parametrize("line", _SH_POSIX_LOOKALIKES)
def test_a_posix_line_like_a_bash_only_construct_is_not_found(line):
    assert _bash_only(line + "\n") == []


# The shells the helper is run under: /bin/sh as a script's `#!` line names
# it, and bash in both of its modes. Here /bin/sh is bash, so these runs
# prove the helper under bash only, and a bash-only construct passes all
# three: `_SH_BASH_ONLY` above is what keeps one out.
_SHELLS = (("/bin/sh",), ("bash",), ("bash", "--posix"))
# A run takes about 0.1 s here, rendering included; the bound only fires on a
# hung shell.
_SH_TIMEOUT_SECONDS = 30


# How long a killed process may take to be gone; SIGKILL lands in
# milliseconds here, and the bound only fires when it was never sent.
_GONE_SECONDS = 5


def test_a_hung_shell_is_stopped_at_the_bound_with_every_child(tmp_path, monkeypatch):
    """_run_sh never waits on a shell longer than _SH_TIMEOUT_SECONDS, and
    stops the shell's whole process group, so a child it started is gone
    too rather than left running under PID 1. The child holds the shell's
    pipes, so a runner that killed the shell alone and read them to their
    end would wait out the child; its read after the kill is bounded, and
    the child is still alive when it gives up."""
    monkeypatch.setattr(sys.modules[__name__], "_SH_TIMEOUT_SECONDS", 1)
    pidfile = tmp_path / "child.pid"
    body = "sleep 30 &\necho $! > '%s'\nwait" % pidfile
    with pytest.raises(subprocess.TimeoutExpired):
        _run_sh(tmp_path, body, _SHELLS[0])
    pid = int(pidfile.read_text(encoding="utf-8"))
    try:
        deadline = time.monotonic() + _GONE_SECONDS
        while process_state.alive(pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not process_state.alive(pid), "the shell's child %d outlived it" % pid
    finally:
        with contextlib.suppress(ProcessLookupError):  # noqa: DROP002 -- teardown: a process already gone is the end state it wants
            os.kill(pid, signal.SIGKILL)


def _run_sh(tmp_path, body, shell):
    """(status, stderr) of *shell* (argv words) sourcing the helper the
    shipped enum renders, then *body*. Rendered, not the shipped file, so a project with shell off,
    which has none, still proves the helper it would get."""
    from child_env import build_child_env

    helper = tmp_path / "exit_codes.sh"
    helper.write_text(et.render_shell(et.read_members(str(_ROOT))), encoding="utf-8")
    script = tmp_path / "use.sh"
    script.write_text(". '%s'\n%s\nexit 99\n" % (helper, body), encoding="utf-8")
    # A session of its own makes the shell a process group leader, so the
    # bound stops the group and no child the shell started outlives it.
    with subprocess.Popen(
        [*shell, str(script)],
        env=build_child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as proc:
        try:
            _out, err = proc.communicate(timeout=_SH_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            # Bounded too: a child the kill missed holds the pipes open, and
            # an unbounded read would wait for that child to exit.
            proc.communicate(timeout=_GONE_SECONDS)
            raise
    return proc.returncode, err


@pytest.mark.parametrize(
    ("body", "status", "said"),
    [
        (
            'exit_fail "$EXIT_CONFIG" "x: bad" "a.json" "fix it"',
            14,
            "x: bad: a.json; fix it\n",
        ),
        ('exit_fail "$EXIT_FAILURE" one two three', 1, "one: two; three\n"),
        ('exit_fail "$EXIT_SUCCESS" a b c', 2, "not a failure"),
        ("exit_fail 7 a b c", 2, "not a failure"),
        ('exit_fail "$EXIT_USAGE" a b', 2, "four"),
        ('exit_fail "$EXIT_USAGE" a "  " c', 2, "blank"),
        ("exit_passthrough 0", 0, ""),
        ("exit_passthrough 5", 5, ""),
        ("exit_passthrough 255", 255, ""),
        ("exit_passthrough 256", 2, "0 to 255"),
        # Past the shell's integer range `[` errors and its test is false.
        ("exit_passthrough 99999999999999999999", 2, "0 to 255"),
        ("exit_passthrough x", 2, "0 to 255"),
        ('exit_passthrough ""', 2, "0 to 255"),
        ("exit_passthrough", 2, "one"),
        ('exit "$EXIT_NOTHING_JUDGED"', 13, ""),
    ],
)
@pytest.mark.parametrize("shell", _SHELLS, ids=[" ".join(s) for s in _SHELLS])
def test_the_helper_ends_a_shell_script_as_the_python_helper_does(
    tmp_path, body, status, said, shell
):
    got, err = _run_sh(tmp_path, body, shell)
    assert got == status, err
    assert said in err
    if not said:
        assert err == "", err
