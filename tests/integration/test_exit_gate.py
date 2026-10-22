"""
title: Integration — a process ends only through the exit helper, and the exit-code table is the enum
kind: tests
layer: n/a
summary: Three tree-wide gates over every Python file tests/source_tree.py `python_files` lists (the walk `check_structure.walk` uses), read from the syntax tree. The first fails an exit written anywhere but scripts/exit_codes.py (`sys.exit`, `os._exit`, any `.exit(...)` attribute such as argparse's, `raise SystemExit`, a SystemExit subclass, the builtins `exit` and `quit`, each of those as an attribute of `builtins` or `__builtins__`, and an import that renames any of them), an entry block that hands `finish` nothing while its module imports the helper, or that calls a function of its module and drops the value it returns, a return scripts/exit_code_table.py `read_script` cannot follow to an ExitCode member (a returned name bound by anything but a plain assignment included), a `report` or `fail` call missing one of its three message parts or holding a blank literal one, or handed a code that is not a failure member, a `passthrough` handed the script's own status (the entry function's result, directly or through a name, an int literal, a member, or a function of the module whose every return is one of those, also under a sign, in an arithmetic or `and`/`or` of them, or through a builtin such as `int`), an entry line `finish(passthrough(...))`, and an import of the helper under a second name. The second fails an ExitCode member the generated table in the limits guide does not name and a table row no member backs (scripts/exit_code_table.py `table_findings`). The third fails a `fail` or `finish` call outside the entry block of a module another project module imports (an import from tests/ does not count, and scripts/exit_codes.py is the helper), because a shared module raises or returns and only an entry point ends the process; `passthrough` is no ending, it marks a status and returns it. config/project.json `import_layers.may_end_the_process` names a module that may, with a non-blank reason, and an entry naming no such module is a finding. A walk that finds no Python file, or no entry block, is a failure, never a pass. It does not judge whether a message part is useful, and it cannot see an exit reached through `getattr`, `os.abort`, `os.kill`, an uncaught exception, argparse's own `--help` and usage exits, a `python -c` line in a makefile, or a status dropped by another callable (`asyncio.run(main())`); and it does not check a `passthrough` over a helper that returns another process's status (scripts/run_app.py `_app_status`), which passes by design, nor one over a function some of whose returns are the script's own literals and others a tool's status. The first and third hand their findings to scripts/expiring_tier.py as the checks `exit-helper` and `exit-shared-module`: in the template repository, which holds copier.yml, every finding is red; in a generated project a finding its `expiring_tier.baseline` records warns until `expiring_tier.expires`, and any other is red. Catching SystemExit is not an exit and is not a finding: the exception itself, or a tuple holding it, as the type of an `except` clause or an argument of pytest's `raises`; anywhere deeper in those expressions, and in a `raises` that is not pytest's, it is one. Not a check_* letter: the letters A to Z are taken.
"""

import ast
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import check_structure as cs  # noqa: E402
import exit_code_table as et  # noqa: E402
import expiring_tier  # noqa: E402

import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration

# The attribute names that end a process when called: `sys.exit`, `os._exit`,
# and an argparse parser's own `exit`.
_EXIT_ATTRIBUTES = ("exit", "_exit")
# The builtins the `site` module adds for the interactive prompt.
_EXIT_BUILTINS = ("exit", "quit")
_EXIT_EXCEPTION = "SystemExit"
# {module: names} whose import under any name is an exit the walk would not
# otherwise recognise at its call.
_EXIT_IMPORTS = {
    "sys": ("exit",),
    "os": ("_exit",),
    "builtins": (*_EXIT_BUILTINS, _EXIT_EXCEPTION),
}
# The module whose attributes are the builtins, and the name every module
# already holds it under without importing it.
_BUILTINS_MODULE = "builtins"
_BUILTINS_GLOBAL = "__builtins__"
# (module, function): the one call that, handed SystemExit, asserts on an exit
# instead of causing one.
_EXPECTING_CALL = ("pytest", "raises")
# `report(code, what, on, next_step)` and `fail(...)`: the parts after the code.
_MESSAGE_PARTS = ("what", "on", "next_step")
_MESSAGE_CALLS = ("report", "fail")
_FINISH = "finish"
# The helper is one module under one import name; this is the other spelling.
_SECOND_NAME = "scripts." + et.HELPER_MODULE


def _builtins_names(tree):
    """The names under which *tree* can reach the builtins module."""
    names = {_BUILTINS_GLOBAL}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == _BUILTINS_MODULE
            )
    return names


def _is_exit_exception(node, builtins_names):
    """True when *node* is `SystemExit`, bare or as an attribute of builtins."""
    if isinstance(node, ast.Name):
        return node.id == _EXIT_EXCEPTION
    return (
        isinstance(node, ast.Attribute)
        and node.attr == _EXIT_EXCEPTION
        and isinstance(node.value, ast.Name)
        and node.value.id in builtins_names
    )


def _expecting_call(tree):
    """A predicate: is this call the test library's `raises`? It is when the
    callee is `<name>.raises` and `<name>` is that library imported, or a bare
    name that `from <library> import raises` binds. A function a module
    defines under the same name is not."""
    library, function = _EXPECTING_CALL
    modules, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == library
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == library
        ):
            names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == function
            )

    def expecting(func):
        if isinstance(func, ast.Name):
            return func.id in names
        return (
            isinstance(func, ast.Attribute)
            and func.attr == function
            and isinstance(func.value, ast.Name)
            and func.value.id in modules
        )

    return expecting


def _caught_or_expected(tree, builtins_names):
    """The ids of the SystemExit references that catch or expect an exit: the
    type of an `except` clause, or an argument of the test library's `raises`,
    in either place the exception itself or a tuple that holds it. A
    SystemExit any deeper in such an expression is being called or raised
    there, and is not allowed."""
    allowed = set()
    expecting = _expecting_call(tree)
    for node in ast.walk(tree):
        holders = []
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            holders.append(node.type)
        elif isinstance(node, ast.Call) and expecting(node.func):
            holders.extend(node.args)
            holders.extend(kw.value for kw in node.keywords)
        for holder in holders:
            items = holder.elts if isinstance(holder, ast.Tuple) else [holder]
            for item in items:
                if _is_exit_exception(item, builtins_names):
                    allowed.add(id(item))
                    # The `builtins` in `builtins.SystemExit` is no exit.
                    allowed.update(id(n) for n in ast.walk(item))
    return allowed


def exit_form_findings(tree, relpath):
    """Each place *tree* ends the process, or names the means to, without the
    helper: `relpath:line: what`."""
    out = []
    builtins_names = _builtins_names(tree)
    allowed = _caught_or_expected(tree, builtins_names)

    def finding(node, what):
        out.append(
            "%s:%d: %s -- end the process through `finish(main())` (%s)"
            % (relpath, node.lineno, what, et.HELPER)
        )

    for node in ast.walk(tree):
        if id(node) in allowed:
            continue
        if isinstance(node, ast.Attribute) and node.attr in _EXIT_ATTRIBUTES:
            finding(node, "`.%s` ends the process here" % node.attr)
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in _EXIT_IMPORTS[_BUILTINS_MODULE]
            and isinstance(node.value, ast.Name)
            and node.value.id in builtins_names
        ):
            finding(node, "`%s.%s` ends the process here" % (node.value.id, node.attr))
        elif isinstance(node, ast.Name) and node.id in _EXIT_BUILTINS:
            finding(node, "the builtin `%s` ends the process here" % node.id)
        elif isinstance(node, ast.Name) and node.id == _EXIT_EXCEPTION:
            finding(node, "`%s` is raised or named here" % _EXIT_EXCEPTION)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                if alias.name in _EXIT_IMPORTS.get(node.module or "", ()):
                    finding(node, "imports `%s.%s`" % (node.module, alias.name))
                if "%s.%s" % (node.module, alias.name) == _SECOND_NAME:
                    finding(node, "imports the helper as `%s`" % _SECOND_NAME)
            if node.module == _SECOND_NAME:
                finding(node, "imports the helper as `%s`" % _SECOND_NAME)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _SECOND_NAME:
                    finding(node, "imports the helper as `%s`" % _SECOND_NAME)
    return sorted(out)


def _blank_literal(node):
    """True when *node* is a string literal with nothing in it but space."""
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and not node.value.strip()
    )


def message_findings(tree, relpath):
    """Each `report` or `fail` call of the helper in *tree* that does not carry
    its three message parts, or carries a blank literal one. A starred or
    `**` argument is a finding: the parts could not be counted."""
    out = []
    bindings = et.helper_bindings(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        symbol = et.helper_symbol(node.func, bindings)
        if symbol not in _MESSAGE_CALLS:
            continue
        where = "%s:%d: `%s`" % (relpath, node.lineno, symbol)
        if any(isinstance(a, ast.Starred) for a in node.args) or any(
            kw.arg is None for kw in node.keywords
        ):
            out.append(
                "%s is called with a starred argument, so its message parts "
                "cannot be counted -- name each part" % where
            )
            continue
        given = dict(zip(_MESSAGE_PARTS, node.args[1:], strict=False))
        given.update({kw.arg: kw.value for kw in node.keywords})
        for part in _MESSAGE_PARTS:
            if part not in given:
                out.append(
                    "%s has no `%s` part -- say what failed, on which input "
                    "and what to do next" % (where, part)
                )
            elif _blank_literal(given[part]) or _is_none(given[part]):
                out.append("%s has a blank `%s` part" % (where, part))
    return sorted(out)


def _is_none(node):
    return isinstance(node, ast.Constant) and node.value is None


def entry_findings(tree, relpath, quiet_names, exercises_helper=False):
    """Each way *tree*'s entry block fails to end through the helper: a
    `finish` call outside the block, every return `read_tree` cannot follow to
    a member, and an entry block that hands `finish` nothing while the module
    binds the helper or the block drops what a function of the module returns.
    *exercises_helper* is the helper's own unit test, which calls `finish` to
    assert on it."""
    out = []
    bindings = et.helper_bindings(tree)
    blocks = et.entry_blocks(tree)
    handed = et.finish_calls(tree, bindings)
    in_block = {id(call) for call in handed}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and et.helper_symbol(node.func, bindings) == _FINISH
            and id(node) not in in_block
            and not exercises_helper
        ):
            out.append(  # noqa: PERF401 -- one finding per line reads plainer
                '%s:%d: `finish` is called outside the `if __name__ == "__main__":` '
                "block -- return the member to `main`'s caller, or call `fail`"
                % (relpath, node.lineno)
            )
    if handed:
        out.extend(et.read_tree(tree, relpath, quiet_names).findings)
    elif blocks and (bindings[0] or bindings[1]):
        out.append(
            "%s:%d: the entry block hands nothing to `finish`, so the status "
            "`main` returns is dropped -- write `finish(main())` (%s)"
            % (relpath, blocks[0].lineno, et.HELPER)
        )
    else:
        out.extend(
            "%s:%d: the entry block drops what `%s` returns, so the process "
            "exits 0 whatever it found -- write `finish(%s())` with `%s` "
            "returning members (%s), or return nothing from it"
            % (relpath, node.lineno, name, name, name, et.HELPER)
            for node, name in et.dropped_results(tree)
        )
    return sorted(out)


def _mirror_test(relpath):
    """The unit test that mirrors the script at *relpath* (tests/AGENT.md)."""
    directory, name = os.path.split(relpath)
    return "tests/unit/%s/test_%s" % (directory, name)


def helper_findings(root):
    """Every finding of the first gate over the tree at *root*, with the count
    of files walked and of entry blocks judged. Raises st.SourceTreeError when there
    is nothing to walk."""
    files = st.python_files(root)
    if not files:
        raise st.SourceTreeError("%s: no Python file to judge -- zero items" % root)
    members = et.read_members(str(root))
    quiet = frozenset(m.name for m in members if m.value == 0)
    known = {m.name for m in members}
    findings, entries = [], 0
    for relpath in files:
        tree = st.parse(root, relpath)
        if relpath != et.HELPER:
            findings.extend(exit_form_findings(tree, relpath))
        # The helper's mirror unit test calls it with bad arguments on purpose.
        exercises = relpath == _mirror_test(et.HELPER)
        if not exercises:
            findings.extend(message_findings(tree, relpath))
            findings.extend(et.code_findings(tree, relpath, quiet))
        findings.extend(entry_findings(tree, relpath, quiet, exercises))
        entries += len(et.entry_blocks(tree))
        bindings = et.helper_bindings(tree)
        findings.extend(
            "%s:%d: names %s.%s, which %s does not define"
            % (relpath, node.lineno, et.ENUM, node.attr, et.HELPER)
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and et.helper_symbol(node.value, bindings) == et.ENUM
            and node.attr not in known
            # `ExitCode.__members__` reads the class, it names no member.
            and not node.attr.startswith("__")
        )
    # `read_tree` and `code_findings` both judge the code of a call an entry
    # function reaches; one line per defect.
    findings = sorted(set(findings))
    return {"files": len(files), "entries": entries, "findings": findings}


# The helper calls that end the process. `passthrough` only marks a wrapped
# tool's status for `finish` and returns it, so a module may call it anywhere.
_ENDING_CALLS = ("fail", "finish")
_TESTS = "tests/"


def library_findings(root):
    """Every call that ends the process in a module another project module
    imports, outside that module's entry block, with the count of such
    modules judged. Tests importing a module do not make it shared: a test
    imports scripts to drive their `main`. config/project.json
    `import_layers.may_end_the_process` names a module that may, with its
    reason; an entry that names no shared module calling the helper is
    stale and a finding."""
    files = st.python_files(root)
    if not files:
        raise st.SourceTreeError("%s: no Python file to judge -- zero items" % root)
    policy = st.import_layers(root)
    exempt = policy["may_end_the_process"]
    importers = {}
    for importer, _lineno, imported in st.import_edges(
        root, files, policy["search_roots"]
    ):
        if not importer.startswith(_TESTS) and imported != et.HELPER:
            importers.setdefault(imported, importer)
    findings, enders = [], set()
    for relpath in sorted(importers):
        tree = st.parse(root, relpath)
        bindings = et.helper_bindings(tree)
        entry = {id(n) for block in et.entry_blocks(tree) for n in ast.walk(block)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or id(node) in entry:
                continue
            name = et.helper_symbol(node.func, bindings)
            if name not in _ENDING_CALLS:
                continue
            enders.add(relpath)
            if relpath in exempt:
                continue
            findings.append(
                "%s:%d: %s is imported by %s, so it must raise or return, never end "
                "the process; return to the entry point and let it call finish"
                % (relpath, node.lineno, name, importers[relpath])
            )
    findings.extend(
        "config/project.json: import_layers.may_end_the_process names `%s`, which "
        "is no shared module that ends the process; delete the entry" % relpath
        for relpath in sorted(exempt)
        if relpath not in enders
    )
    return {"modules": len(importers), "findings": sorted(findings)}


# --- the tree itself -------------------------------------------------------------


def test_no_process_in_the_tree_ends_outside_the_helper():
    result = helper_findings(_ROOT)
    assert result["entries"] > 0, "no entry block was judged -- zero items"
    red = expiring_tier.apply("exit-helper", result["findings"], str(_ROOT))
    assert not red, "\n".join(red)


def test_the_exit_code_table_is_what_the_enum_and_the_gate_scripts_say():
    assert et.read_members(str(_ROOT)), "the enum has no member -- zero items"
    assert not et.table_findings(str(_ROOT)), "\n".join(et.table_findings(str(_ROOT)))


def test_every_member_is_named_by_a_row_and_every_row_by_a_member():
    """The two directions, read from the guide by the repo's table reader and
    not by comparing against what the generator would write."""
    guide, _target = et.load_policy(str(_ROOT))
    text = (_ROOT / guide).read_text(encoding="utf-8")
    region = et.split_region(text, guide)[1]
    table = cs._pipe_table(region, et.MEMBER_COLUMNS)
    assert table is not None, "%s: no member table in the region" % guide
    named = {(row[0], row[1].strip("`")) for row in table[1]}
    backed = {(str(m.value), m.name) for m in et.read_members(str(_ROOT))}
    assert backed, "zero members"
    assert named == backed


def test_a_shared_module_never_ends_the_process():
    result = library_findings(_ROOT)
    assert result["modules"] > 0, "no shared module was judged -- zero items"
    red = expiring_tier.apply("exit-shared-module", result["findings"], str(_ROOT))
    assert not red, "\n".join(red)


# --- fixtures: each check can fail -------------------------------------------------

_GOOD = (
    "import sys\n"
    "from exit_codes import ExitCode, finish, report\n"
    "\n"
    "def main():\n"
    "    if len(sys.argv) > 1:\n"
    "        return report(ExitCode.USAGE, 'tool: no', sys.argv[1], 'drop it')\n"
    "    return ExitCode.SUCCESS\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    finish(main())\n"
)
_GUIDE = "docs/guides/limits.md"
_MAKEFILE = "verify:\n\tpython scripts/tool.py\n"


def _tree(tmp_path, tool=_GOOD, extra=None):
    """A project with the real helper, one gate script, and a current table."""
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "docs" / "guides").mkdir(parents=True)
    shutil.copy(str(_ROOT / et.HELPER), str(root / et.HELPER))
    (root / "scripts" / "tool.py").write_text(tool, encoding="utf-8")
    for relpath, text in (extra or {}).items():
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        (root / relpath).write_text(text, encoding="utf-8")
    (root / "Makefile").write_text(_MAKEFILE, encoding="utf-8")
    (root / "config" / "project.json").write_text(
        json.dumps(
            {et.BLOCK: {et.GUIDE_KEY: _GUIDE, et.TARGET_KEY: "verify"}}, sort_keys=True
        ),
        encoding="utf-8",
    )
    (root / _GUIDE).write_text(
        "# Limits\n\n%s\n%s\n\nprose\n" % (et.BEGIN, et.END), encoding="utf-8"
    )
    return root


def _generate(root):
    assert et.main([], root=str(root)) == 0


def test_a_tree_that_ends_through_the_helper_has_no_finding(tmp_path):
    root = _tree(tmp_path)
    _generate(root)
    result = helper_findings(root)
    assert result == {"files": 2, "entries": 1, "findings": []}
    assert et.table_findings(str(root)) == []


_EXIT_FORMS = {
    "sys.exit": "import sys\nsys.exit(1)\n",
    "sys.exit(main())": (
        "import sys\n\ndef main():\n    return 1\n\n"
        "if __name__ == '__main__':\n    sys.exit(main())\n"
    ),
    "aliased sys": "import sys as s\ns.exit(1)\n",
    "from sys import exit": "from sys import exit as leave\nleave(1)\n",
    "raise SystemExit": "raise SystemExit(2)\n",
    "raise SystemExit bare": "def f():\n    raise SystemExit\n",
    "SystemExit subclass": "class Stop(SystemExit):\n    pass\n",
    "SystemExit renamed": "Stop = SystemExit\n",
    "os._exit": "import os\nos._exit(3)\n",
    "from os import _exit": "from os import _exit\n",
    "exit builtin": "exit(1)\n",
    "quit builtin": "quit()\n",
    "argparse exit": "import argparse\nargparse.ArgumentParser().exit(2, 'no')\n",
    "builtins.SystemExit": "import builtins\nraise builtins.SystemExit(7)\n",
    "builtins aliased": "import builtins as b\nraise b.SystemExit(7)\n",
    "builtins.quit": "import builtins\nbuiltins.quit(7)\n",
    "__builtins__.SystemExit": "raise __builtins__.SystemExit(7)\n",
    "from builtins import SystemExit": (
        "from builtins import SystemExit as Stop\nraise Stop(7)\n"
    ),
    "from builtins import quit": "from builtins import quit as leave\nleave(7)\n",
    "a local raises": "def raises(exc):\n    raise exc\n\nraises(SystemExit)\n",
    "raised inside pytest.raises": (
        "import pytest\n\ndef f():\n    pytest.raises(ValueError, SystemExit(7))\n"
    ),
    "raised in an except type": (
        "def f(exc):\n    raise exc\n\n"
        "try:\n    pass\nexcept f(SystemExit(7)):\n    pass\n"
    ),
    "second import name": "from scripts.exit_codes import finish\n",
    "second import name 2": "import scripts.exit_codes\n",
    "second import name 3": "from scripts import exit_codes\n",
}


@pytest.mark.parametrize("form", sorted(_EXIT_FORMS))
def test_each_exit_form_outside_the_helper_is_a_finding(tmp_path, form):
    root = _tree(tmp_path, extra={"src/pkg/mod.py": _EXIT_FORMS[form]})
    findings = helper_findings(root)["findings"]
    assert findings, form
    assert all(f.startswith("src/pkg/mod.py:") for f in findings), findings
    # Green again once the exit is gone: the finding was the exit's, not the file's.
    (root / "src" / "pkg" / "mod.py").write_text("X = 1\n", encoding="utf-8")
    assert helper_findings(root)["findings"] == []


@pytest.mark.parametrize(
    "source",
    [
        "try:\n    pass\nexcept SystemExit:\n    pass\n",
        "try:\n    pass\nexcept (ValueError, SystemExit) as e:\n    print(e.code)\n",
        "import pytest\n\ndef test_x():\n    with pytest.raises(SystemExit):\n        pass\n",
        "import pytest as pt\n\ndef test_x():\n    with pt.raises(SystemExit):\n        pass\n",
        "from pytest import raises\n\ndef test_x():\n"
        "    with raises((ValueError, SystemExit)):\n        pass\n",
        "import pytest\n\ndef test_x():\n"
        "    with pytest.raises(expected_exception=SystemExit):\n        pass\n",
        "import builtins\n\ntry:\n    pass\nexcept builtins.SystemExit:\n    pass\n",
        "x = 'sys.exit(1)'\nexit_code = 3\n",
    ],
)
def test_catching_or_expecting_an_exit_is_not_a_finding(tmp_path, source):
    root = _tree(tmp_path, extra={"tests/test_mod.py": source})
    assert helper_findings(root)["findings"] == []


_BAD_ENTRIES = {
    "int return": _GOOD.replace("return ExitCode.SUCCESS", "return 0"),
    "bare failure member": _GOOD.replace(
        "return ExitCode.SUCCESS", "return ExitCode.FAILURE"
    ),
    "falls off the end": _GOOD.replace("    return ExitCode.SUCCESS\n", ""),
    "status dropped": _GOOD.replace("finish(main())", "main()"),
    "unknown member": _GOOD.replace("ExitCode.USAGE", "ExitCode.NOPE"),
    "another module's call": _GOOD.replace(
        "return ExitCode.SUCCESS", "return sys.getrecursionlimit()"
    ),
    "finish outside the block": _GOOD.replace(
        "def main():\n", "def stop():\n    finish(ExitCode.SUCCESS)\n\ndef main():\n"
    ),
    "finish of a literal": _GOOD.replace("finish(main())", "finish(1)"),
    "report of the success member": _GOOD.replace(
        "return ExitCode.SUCCESS", "return report(ExitCode.SUCCESS, 'a', 'b', 'c')"
    ),
    "status dropped, helper not imported": (
        "import sys\n\ndef main():\n    sys.stderr.write('check failed\\n')\n"
        "    return 1\n\nif __name__ == '__main__':\n    main()\n"
    ),
    "status dropped in a nested statement": (
        "def main():\n    return 1\n\n"
        "if __name__ == '__main__':\n    try:\n        main()\n"
        "    finally:\n        print('done')\n"
    ),
}
# Each line rebinds `rc` after `rc = ExitCode.SUCCESS` in a way the reader of
# returns does not follow, so the name can hold a status that is no member.
_REBINDINGS = {
    "tuple unpacking": "    rc, out = divmod(7, 8)\n",
    "starred unpacking": "    [rc, *rest] = [7, 8]\n",
    "for loop": "    for rc in (7,):\n        pass\n",
    "augmented assign": "    rc += 5\n",
    "walrus": "    if (rc := 9):\n        pass\n",
    "with as": "    with open(sys.argv[0]) as rc:\n        pass\n",
    "except as": "    try:\n        pass\n    except ValueError as rc:\n        pass\n",
    "import as": "    import os as rc\n",
    "global": "    global rc\n",
    "delete": "    del rc\n",
    "nested def": "    def rc():\n        return 7\n",
}
_REBOUND = _GOOD.replace(
    "    return ExitCode.SUCCESS\n", "    rc = ExitCode.SUCCESS\n%s    return rc\n"
)
_BAD_ENTRIES.update({"rebound by " + k: _REBOUND % v for k, v in _REBINDINGS.items()})
_BAD_ENTRIES["rebound by a parameter default"] = (
    "from exit_codes import ExitCode, finish\n\nrc = ExitCode.SUCCESS\n\n"
    "def main(rc=7):\n    return rc\n\nif __name__ == '__main__':\n    finish(main())\n"
)
_BAD_ENTRIES["rebound by another function's global"] = (
    "from exit_codes import ExitCode, finish\n\nrc = ExitCode.SUCCESS\n\n"
    "def spoil():\n    global rc\n    rc = 7\n\n"
    "def main():\n    spoil()\n    return rc\n\n"
    "if __name__ == '__main__':\n    finish(main())\n"
)
_BAD_ENTRIES["rebound in a module-level branch"] = (
    "import sys\nfrom exit_codes import ExitCode, finish\n\nrc = ExitCode.SUCCESS\n"
    "if sys.argv:\n    rc, _ = 7, 8\n\n"
    "def main():\n    return rc\n\nif __name__ == '__main__':\n    finish(main())\n"
)

# `passthrough` marks a wrapped tool's status. Handed main's own result, or a
# status this script wrote itself, it would label the script's choice as a
# tool's and let a main returning integers past the gate.
_INT_MAIN = _GOOD.replace("return ExitCode.SUCCESS", "return 0").replace(
    "return report(ExitCode.USAGE, 'tool: no', sys.argv[1], 'drop it')", "return 2"
)
_BAD_ENTRIES["finish of passthrough of main"] = _INT_MAIN.replace(
    "finish(main())", "finish(passthrough(main()))"
).replace("finish, report", "finish, passthrough, report")
_BAD_ENTRIES["finish of passthrough of a name bound to main"] = _INT_MAIN.replace(
    "    finish(main())\n", "    rc = main()\n    finish(passthrough(rc))\n"
).replace("finish, report", "finish, passthrough, report")
_BAD_ENTRIES["passthrough of a module function returning integers"] = (
    "import sys\n"
    "from exit_codes import ExitCode, finish, passthrough\n"
    "\n"
    "def main2():\n"
    "    return 1 if len(sys.argv) > 1 else 0\n"
    "\n"
    "def main():\n"
    "    return passthrough(main2())\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    finish(main())\n"
)
# The same status dressed as a computed one: a builtin, an `or`, a sign.
for _label, _dressed in (
    ("through a builtin", "int(main2())"),
    ("or a literal", "main2() or 0"),
):
    _BAD_ENTRIES["passthrough of a module function returning integers " + _label] = (
        _BAD_ENTRIES["passthrough of a module function returning integers"].replace(
            "passthrough(main2())", "passthrough(%s)" % _dressed
        )
    )
_BAD_ENTRIES["passthrough of a negative literal"] = _BAD_ENTRIES[
    "passthrough of a module function returning integers"
].replace("passthrough(main2())", "passthrough(-1)")


def test_a_name_bound_only_by_plain_assignments_is_followed(tmp_path):
    """The control for the rebinding fixtures: the same script without the
    rebinding line has no finding, annotated or not."""
    for line in ("", "    rc: ExitCode = ExitCode.SUCCESS\n", "    other, x = 1, 2\n"):
        root = _tree(tmp_path / str(len(line)), tool=_REBOUND % line)
        assert helper_findings(root)["findings"] == [], line


def test_a_passthrough_of_a_wrapped_status_is_no_finding(tmp_path):
    """The control for the passthrough fixtures: a status read from the child
    the script ran, where it ran it, passes through."""
    tool = (
        "import subprocess\n"
        "from exit_codes import finish, passthrough\n"
        "\n"
        "def main():\n"
        "    return passthrough(subprocess.run(['true']).returncode)\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    finish(main())\n"
    )
    root = _tree(tmp_path, tool=tool)
    assert helper_findings(root)["findings"] == []


@pytest.mark.parametrize(
    "block",
    [
        "    main()\n",
        "    print(helper())\n",
        "    text = helper()\n    print(text)\n",
        "    import asyncio\n    asyncio.run(serve())\n",
    ],
)
def test_an_entry_block_that_drops_no_value_needs_no_finish(tmp_path, block):
    """An entry block with no status to hand over (a server, a demo): it calls
    a function that returns nothing, or it uses the value a function returns."""
    source = (
        "def main():\n    print('served')\n\n"
        "def helper():\n    return 'text'\n\n"
        "async def serve():\n    return None\n\n"
        "if __name__ == '__main__':\n" + block
    )
    root = _tree(tmp_path, extra={"src/pkg/__main__.py": source})
    assert helper_findings(root)["findings"] == []


@pytest.mark.parametrize("case", sorted(_BAD_ENTRIES))
def test_an_entry_that_does_not_return_members_through_finish_is_a_finding(
    tmp_path, case
):
    assert _BAD_ENTRIES[case] != _GOOD, case
    root = _tree(tmp_path, tool=_BAD_ENTRIES[case])
    findings = helper_findings(root)["findings"]
    assert findings, case
    assert all(f.startswith("scripts/tool.py") for f in findings), findings


_BLANK_PARTS = {
    "blank what": "report(ExitCode.USAGE, '', sys.argv[1], 'drop it')",
    "blank on": "report(ExitCode.USAGE, 'tool: no', '  ', 'drop it')",
    "blank next": "report(ExitCode.USAGE, 'tool: no', sys.argv[1], '')",
    "none part": "report(ExitCode.USAGE, 'tool: no', None, 'drop it')",
    "missing part": "report(ExitCode.USAGE, 'tool: no', sys.argv[1])",
    "blank keyword": "report(ExitCode.USAGE, 'tool: no', sys.argv[1], next_step='')",
    "starred": "report(ExitCode.USAGE, *sys.argv[1:4])",
}


@pytest.mark.parametrize("case", sorted(_BLANK_PARTS))
def test_a_blank_or_missing_message_part_is_a_finding(tmp_path, case):
    good = "report(ExitCode.USAGE, 'tool: no', sys.argv[1], 'drop it')"
    assert good in _GOOD
    root = _tree(tmp_path, tool=_GOOD.replace(good, _BLANK_PARTS[case]))
    findings = helper_findings(root)["findings"]
    assert len(findings) == 1 and "scripts/tool.py:6: `report`" in findings[0], findings


def test_a_blank_part_of_fail_is_a_finding(tmp_path):
    source = (
        "import exit_codes\n\ndef stop(path):\n"
        "    exit_codes.fail(exit_codes.ExitCode.USAGE, 'no', path, ' ')\n"
    )
    root = _tree(tmp_path, extra={"scripts/lib.py": source})
    findings = helper_findings(root)["findings"]
    assert len(findings) == 1 and "`fail` has a blank `next_step`" in findings[0]


@pytest.mark.parametrize(
    "call",
    [
        "exit_codes.fail(7, 'a', path, 'c')",
        "exit_codes.report(7, 'a', path, 'c')",
        "exit_codes.fail(exit_codes.ExitCode.SUCCESS, 'a', path, 'c')",
        "exit_codes.report(code=path, what='a', on=path, next_step='c')",
        "exit_codes.fail(what='a', on=path, next_step='c')",
    ],
)
def test_a_code_the_helper_would_refuse_is_a_finding_in_any_module(tmp_path, call):
    """`report` raises on a code that is not a failure member, so the call
    would end on a traceback; a module with no entry block is read too."""
    source = "import exit_codes\n\ndef stop(path):\n    return %s\n" % call
    root = _tree(tmp_path, extra={"scripts/lib.py": source})
    findings = helper_findings(root)["findings"]
    assert len(findings) == 1 and findings[0].startswith("scripts/lib.py:4:"), findings


def _add_member(root, annotation=""):
    """Append to *root*'s enum a member its list does not hold yet, and return
    its name: one past the highest value, so the fixture holds whatever
    members a project has added. The line goes in at the class's last line,
    found in the syntax tree, so it does not depend on how the members before
    it are laid out. *annotation* is written between the name and the `=`."""
    path = root / et.HELPER
    text = path.read_text(encoding="utf-8")
    members = et.read_members(str(root))
    enum = next(
        node
        for node in ast.parse(text).body
        if isinstance(node, ast.ClassDef) and node.name == et.ENUM
    )
    name = "PLANTED_%d" % len(members)
    assert name not in {m.name for m in members}
    lines = text.splitlines(True)
    lines.insert(
        enum.end_lineno,
        "    %s%s = (%d, 'it was planted', 'nothing')\n"
        % (name, annotation, members[-1].value + 1),
    )
    path.write_text("".join(lines), encoding="utf-8")
    return name


def test_a_member_added_without_regenerating_is_a_finding(tmp_path):
    root = _tree(tmp_path)
    _generate(root)
    assert et.table_findings(str(root)) == []
    name = _add_member(root)
    findings = et.table_findings(str(root))
    assert findings == ["%s: the exit-code table names no member `%s`" % (_GUIDE, name)]
    assert et.main(["--check"], root=str(root)) == 1
    _generate(root)
    assert et.table_findings(str(root)) == []


def test_an_annotated_member_is_refused_not_skipped(tmp_path):
    """`NAME: tuple = (...)` is a member at run time; a reader that skipped it
    would call a table without its row current."""
    root = _tree(tmp_path)
    _generate(root)
    _add_member(root, annotation=": tuple")
    findings = et.table_findings(str(root))
    assert len(findings) == 1 and "%s:" % et.HELPER in findings[0], findings
    assert et.main(["--check"], root=str(root)) == 2


def test_a_table_row_no_member_backs_is_a_finding(tmp_path):
    root = _tree(tmp_path)
    _generate(root)
    guide = root / _GUIDE
    text = guide.read_text(encoding="utf-8")
    last = et.read_members(str(root))[-1]
    row = "| %d | `%s` |" % (last.value, last.name)
    assert text.count(row) == 1
    guide.write_text(
        text.replace(
            row, "| %d | `GHOST` | nothing | nothing |\n" % (last.value + 1) + row
        ),
        encoding="utf-8",
    )
    findings = et.table_findings(str(root))
    assert len(findings) == 1 and "`GHOST`, which nothing backs" in findings[0]
    assert et.main(["--check"], root=str(root)) == 1


def test_a_script_row_that_says_another_code_is_a_finding(tmp_path):
    root = _tree(tmp_path)
    _generate(root)
    guide = root / _GUIDE
    text = guide.read_text(encoding="utf-8")
    row = "| `scripts/tool.py` | 0, 2 |"
    assert text.count(row) == 1
    guide.write_text(text.replace(row, "| `scripts/tool.py` | 0 |"), encoding="utf-8")
    findings = et.table_findings(str(root))
    assert len(findings) == 1 and "script `scripts/tool.py`" in findings[0]


def test_a_tree_with_no_python_file_is_an_error_not_a_pass(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(st.SourceTreeError, match="zero items"):
        helper_findings(tmp_path / "empty")


def test_a_file_that_does_not_parse_is_an_error_not_a_skip(tmp_path):
    root = _tree(tmp_path, extra={"src/bad.py": "def (:\n"})
    with pytest.raises(st.SourceTreeError, match="src/bad.py"):
        helper_findings(root)


# --- fixtures: a shared module never ends the process -----------------------------

_LAYERS = {"search_roots": ["", "scripts/"], "order": [["scripts"]]}
_USER = "import lib\n\nlib.check()\n"


def _shared(tmp_path, lib, exempt=None, user=_USER):
    """A project whose scripts/user.py imports scripts/lib.py."""
    layers = dict(_LAYERS)
    if exempt is not None:
        layers["may_end_the_process"] = exempt
    root = _tree(tmp_path, extra={"scripts/lib.py": lib, "scripts/user.py": user})
    (root / "config" / "project.json").write_text(
        json.dumps({"import_layers": layers}), encoding="utf-8"
    )
    return root


_FAIL_IN_A_FUNCTION = (
    "from exit_codes import ExitCode, fail\n"
    "\n"
    "def check():\n"
    "    fail(ExitCode.USAGE, 'lib: bad', 'input', 'fix it')\n"
)


@pytest.mark.parametrize(
    "lib, line, name",
    [
        (_FAIL_IN_A_FUNCTION, 4, "fail"),
        (
            "import exit_codes\n"
            "exit_codes.fail(exit_codes.ExitCode.USAGE, 'lib: bad', 'in', 'fix')\n",
            2,
            "fail",
        ),
        (
            "from exit_codes import ExitCode, finish\n"
            "\n"
            "def check():\n"
            "    finish(ExitCode.SUCCESS)\n",
            4,
            "finish",
        ),
        (
            "import exit_codes\n"
            "_f = exit_codes.fail\n"
            "\n"
            "def check():\n"
            "    _f(exit_codes.ExitCode.USAGE, 'lib: bad', 'input', 'fix it')\n",
            5,
            "fail",
        ),
        (
            "from exit_codes import ExitCode, fail\n"
            "die = fail\n"
            "stop = die\n"
            "\n"
            "def check():\n"
            "    stop(ExitCode.USAGE, 'lib: bad', 'input', 'fix it')\n",
            6,
            "fail",
        ),
        (
            "import exit_codes\n"
            "helper = exit_codes\n"
            "\n"
            "def check():\n"
            "    helper.fail(helper.ExitCode.USAGE, 'lib: bad', 'input', 'fix it')\n",
            5,
            "fail",
        ),
    ],
    ids=[
        "fail in a function",
        "fail at module level",
        "finish in a function",
        "fail rebound to a name",
        "fail rebound twice",
        "the helper module rebound to a name",
    ],
)
def test_a_shared_module_that_ends_the_process_is_a_finding(tmp_path, lib, line, name):
    result = library_findings(_shared(tmp_path, lib))
    assert result["findings"] == [
        "scripts/lib.py:%d: %s is imported by scripts/user.py, so it must raise or "
        "return, never end the process; return to the entry point and let it call "
        "finish" % (line, name)
    ], result


def test_an_entry_block_or_passthrough_in_a_shared_module_is_no_finding(tmp_path):
    lib = (
        "from exit_codes import ExitCode, finish, passthrough\n"
        "\n"
        "def check():\n"
        "    return passthrough(3)\n"
        "\n"
        "def main():\n"
        "    return ExitCode.SUCCESS\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    finish(main())\n"
    )
    result = library_findings(_shared(tmp_path, lib))
    assert result == {"modules": 1, "findings": []}, result


def test_a_module_only_tests_import_is_not_shared(tmp_path):
    root = _shared(tmp_path, _FAIL_IN_A_FUNCTION, user="")
    (root / "tests").mkdir()
    (root / "tests" / "test_lib.py").write_text("import lib\n", encoding="utf-8")
    result = library_findings(root)
    assert result == {"modules": 0, "findings": []}, result


def test_an_exempt_module_is_no_finding(tmp_path):
    exempt = {"scripts/lib.py": "it runs before its importer can hold a main"}
    result = library_findings(_shared(tmp_path, _FAIL_IN_A_FUNCTION, exempt))
    assert result["findings"] == [], result


def test_a_stale_exemption_is_a_finding(tmp_path):
    exempt = {"scripts/lib.py": "it once ended the process"}
    result = library_findings(_shared(tmp_path, "def check():\n    return 1\n", exempt))
    assert result["findings"] == [
        "config/project.json: import_layers.may_end_the_process names "
        "`scripts/lib.py`, which is no shared module that ends the process; "
        "delete the entry"
    ], result


def test_an_exemption_with_a_blank_reason_is_an_error_not_a_pass(tmp_path):
    root = _shared(tmp_path, _FAIL_IN_A_FUNCTION, {"scripts/lib.py": " -- "})
    with pytest.raises(st.SourceTreeError, match="may_end_the_process"):
        library_findings(root)
