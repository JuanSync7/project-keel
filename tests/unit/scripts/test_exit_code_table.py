"""
title: Unit — exit_code_table (the generated exit-code table and the reader of what a script exits with)
kind: tests
layer: n/a
summary: read_members reads the enum from the helper's syntax tree in value order and refuses a missing class, a member that is not three literals, a shared value and a text that cannot be a table cell. read_script follows an entry function to the members it returns, counts a `fail` call anywhere in the module, marks a passed-through status, and reports a bare integer, an unknown member and a function that can reach its end without returning as findings, never as codes. split_region refuses a marker that is missing, repeated or out of order. render and exit_cell are pure and sorted. load_policy names the config key it cannot read. main writes the region, leaves every byte outside it alone, keeps a CRLF guide CRLF, reaches a fixed point on the second run, exits 1 from --check on a stale table and 2 when it refuses, and refuses a guide reached through a symlink without writing through it.
"""

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import exit_code_table as et  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

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
    assert et.exit_cell({130, 2, 0}, False) == "0, 2, 130"
    assert et.exit_cell({0}, True) == "0, " + et.PASSES_THROUGH
    assert et.exit_cell(set(), True) == et.PASSES_THROUGH


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
        (lambda root: os.remove(str(root / et.MANIFEST)), "cannot read the manifest"),
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


def test_the_shipped_table_is_current():
    assert et.table_findings(str(_ROOT)) == []
