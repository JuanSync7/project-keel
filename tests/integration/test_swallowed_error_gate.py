"""
title: Integration — no error is swallowed without a stated reason
kind: tests
layer: n/a
summary: A tree-wide gate over every Python file tests/source_tree.py `python_files` lists, read from the syntax tree. It fails a bare `except:`, and an `except` whose type is `Exception` or `BaseException` (alone, in a tuple, or as an attribute such as `builtins.Exception`) when the handler has no `raise` and its body only passes, continues, breaks, returns nothing or a fixed value (a constant, a signed constant such as `-1`, or a list, tuple, set or dict of them such as `[]`), assigns a fixed value, or holds a bare constant: such a handler throws the failure away, so the caller reads it as a success. Either is allowed when a `# noqa: BLE001` or `# noqa: E722` suppression on a line of the `except` clause gives a reason after its codes, read by `noqa_reasons`, which takes codes separated by commas or spaces as ruff does, so a second code is never the reason. A second check fails every BLE001 or E722 suppression in the tree whose reason holds no letter or digit, because ruff honours a bare suppression and the reason is the one record of why the error may be dropped. A walk with no Python file, or with no `except` handler to judge, is a failure, never a pass. Two more checks run through scripts/expiring_tier.py, so keel is red at once and a generated project warns until config/project.json `expiring_tier.expires`: `dropped-error-narrow` fails an `except` of a narrower type whose body only passes, continues, breaks or holds a bare constant (DROP001), and `dropped-error-call` fails a `contextlib.suppress(...)` call, by that name or an alias bound from contextlib (DROP002), and any call given `ignore_errors=True` (DROP003). Each is allowed with a `# noqa: DROPnnn -- <reason>` on a line the construct spans, and the blank-reason check covers those codes too; pyproject.toml lists the DROP codes under ruff's `external`, so ruff keeps their suppressions, and a test holds that list to the codes the gate owns. It cannot see a handler that does work but never looks at the error, or a narrow handler that returns or assigns a fixed value in place of the error; ruff's BLE001 and E722 run beside it. Not a check_* letter: the letters A to Z are taken.
"""

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "scripts"))

import expiring_tier  # noqa: E402

import source_tree as st  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:  # before 3.11; pytest itself depends on tomli there
    import tomli as tomllib

pytestmark = pytest.mark.integration

# The exception types that catch every error, so a handler of one that drops
# the error drops any failure at all.
_BROAD = ("Exception", "BaseException")
# ruff's codes for a blind `except Exception` and a bare `except:`.
_CODES = ("BLE001", "E722")
# The codes this gate owns, for the drops ruff is not asked to judge: the
# maintainer ruled on 2026-11-03 that one gate holds a dropped error, so a
# generated project meets these through the expiring tier rather than red at
# once from ruff's S110 and S112. pyproject.toml declares them ruff `external`,
# so ruff keeps their suppressions.
_NARROW_CODE = "DROP001"
_SUPPRESS_CODE = "DROP002"
_IGNORE_CODE = "DROP003"
# Every code whose suppression must say why the error may be dropped.
_OWNED = _CODES + (_NARROW_CODE, _SUPPRESS_CODE, _IGNORE_CODE)
_FIX = (
    "raise, return the failure, or give the reason after the code: "
    "`# noqa: %s -- <why the error may be dropped>`"
)


def _type_names(node):
    """The names an `except` clause's type expression catches."""
    items = node.elts if isinstance(node, ast.Tuple) else [node]
    out = []
    for item in items:
        if isinstance(item, ast.Name):
            out.append(item.id)
        elif isinstance(item, ast.Attribute):
            out.append(item.attr)
    return out


def _fixed(node):
    """True for an expression whose value is written out in full, so it holds
    nothing of an error: a constant, a sign over one (`-1`), or a list, tuple,
    set or dict of them (`[]`, `{}`). A sentinel is usually one of these."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp):
        return _fixed(node.operand)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_fixed(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        # A `None` key is a `**` unpacking, whose value is read, not written.
        return all(
            key is not None and _fixed(key) and _fixed(value)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    return False


def _quiet(statement):
    """True for a statement that does nothing with an error: `pass`,
    `continue`, `break`, a `return` of a fixed value or of nothing, an
    assignment of a fixed value (a sentinel the code after the `try` reads),
    or a bare constant (`...`, a string)."""
    if isinstance(statement, (ast.Pass, ast.Continue, ast.Break)):
        return True
    if isinstance(statement, ast.Return):
        return statement.value is None or _fixed(statement.value)
    if isinstance(statement, (ast.Assign, ast.AnnAssign)):
        return statement.value is not None and _fixed(statement.value)
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)


def _swallows(handler):
    """What *handler* catches when it throws the error away, else None."""
    if handler.type is None:
        return "a bare `except:`"
    caught = [name for name in _type_names(handler.type) if name in _BROAD]
    if not caught:
        return None
    if any(isinstance(n, ast.Raise) for s in handler.body for n in ast.walk(s)):
        return None
    if all(_quiet(statement) for statement in handler.body):
        return "`except %s` that only drops the error" % caught[0]
    return None


def _drops(statement):
    """True for a statement that does nothing at all with an error: `pass`,
    `continue`, `break`, or a bare constant (`...`, a string)."""
    if isinstance(statement, (ast.Pass, ast.Continue, ast.Break)):
        return True
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)


def _narrow_drop(handler):
    """What a narrow *handler* catches when its body only drops the error,
    else None; a bare or broad handler is `_swallows`'s to judge."""
    if handler.type is None or set(_type_names(handler.type)) & set(_BROAD):
        return None
    if all(_drops(statement) for statement in handler.body):
        return "`except %s` that only drops the error" % ast.unparse(handler.type)
    return None


def _clause_lines(handler):
    """The lines of the `except` clause itself, before its body."""
    last = max(handler.lineno, handler.body[0].lineno - 1)
    return range(handler.lineno, last + 1)


def _call_lines(call):
    """Every line the call spans, so a reason after its closing bracket counts."""
    return range(call.lineno, call.end_lineno + 1)


def _reasoned(reasons, lines, owned):
    """True when one of *lines* carries a suppression of a code in *owned*
    with a non-blank reason."""
    for lineno in lines:
        codes, reason = reasons.get(lineno, ((), ""))
        if set(codes) & set(owned) and not st.blank(reason):
            return True
    return False


def _suppress_names(tree):
    """(names, modules): the local names `from contextlib import suppress`
    binds, and the local names `import contextlib` binds, aliases included."""
    names, modules = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "contextlib":
            names.update(a.asname or a.name for a in node.names if a.name == "suppress")
        elif isinstance(node, ast.Import):
            modules.update(
                a.asname or a.name for a in node.names if a.name == "contextlib"
            )
    return names, modules


def _is_suppress(call, names, modules):
    """True for a call of `contextlib.suppress` under a name the module binds."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in names
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "suppress"
        and isinstance(func.value, ast.Name)
        and func.value.id in modules
    )


def _ignores_errors(call):
    """True for a call that passes `ignore_errors=True`, such as
    `shutil.rmtree(path, ignore_errors=True)`."""
    return any(
        kw.arg == "ignore_errors"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is True
        for kw in call.keywords
    )


def _finding(relpath, lineno, what, code):
    return (
        "%s:%d: %s swallows the error, so the caller reads a failure as a "
        "success; %s" % (relpath, lineno, what, _FIX % code)
    )


def swallow_findings(root):
    """{files, handlers, findings, narrow, calls, blank}: one finding per
    handler or call that drops an error with no reasoned suppression, sorted
    by rule (a broad handler, a narrow handler, a call), and one per
    suppression of a code the gate owns whose reason is blank."""
    files = st.python_files(root)
    if not files:
        raise st.SourceTreeError("%s: no Python file to judge -- zero items" % root)
    handlers, findings, narrow, calls, blank = 0, [], [], [], []
    for relpath in files:
        tree = st.parse(root, relpath)
        reasons = st.noqa_reasons(root, relpath)
        for lineno, (codes, reason) in sorted(reasons.items()):
            used = [code for code in codes if code in _OWNED]
            if used and st.blank(reason):
                blank.append(
                    "%s:%d: `# noqa: %s` gives no reason; say after the codes why "
                    "the error may be dropped, or handle it"
                    % (relpath, lineno, ", ".join(used))
                )
        names, modules = _suppress_names(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                handlers += 1
                lines = _clause_lines(node)
                what = _swallows(node)
                if what and not _reasoned(reasons, lines, _CODES):
                    code = "E722" if node.type is None else "BLE001"
                    findings.append(_finding(relpath, node.lineno, what, code))
                what = _narrow_drop(node)
                if what and not _reasoned(reasons, lines, (_NARROW_CODE,)):
                    narrow.append(_finding(relpath, node.lineno, what, _NARROW_CODE))
            elif isinstance(node, ast.Call):
                if _is_suppress(node, names, modules):
                    what, code = "`contextlib.suppress(...)`", _SUPPRESS_CODE
                elif _ignores_errors(node):
                    what, code = "`ignore_errors=True`", _IGNORE_CODE
                else:
                    continue
                if not _reasoned(reasons, _call_lines(node), (code,)):
                    calls.append(_finding(relpath, node.lineno, what, code))
    if not handlers:
        raise st.SourceTreeError("%s: no except handler to judge -- zero items" % root)
    return {
        "files": len(files),
        "handlers": handlers,
        "findings": sorted(findings),
        "narrow": sorted(narrow),
        "calls": sorted(calls),
        "blank": sorted(blank),
    }


# --- the tree itself -------------------------------------------------------------

_RESULT = {}


def _tree_result():
    if not _RESULT:
        _RESULT.update(swallow_findings(_ROOT))
    return _RESULT


def test_no_handler_in_the_tree_swallows_an_error():
    findings = _tree_result()["findings"]
    assert not findings, "\n".join(findings)


def test_no_narrow_handler_in_the_tree_only_drops_an_error():
    red = expiring_tier.apply(
        "dropped-error-narrow", _tree_result()["narrow"], str(_ROOT)
    )
    assert not red, "\n".join(red)


def test_no_call_in_the_tree_drops_an_error():
    red = expiring_tier.apply("dropped-error-call", _tree_result()["calls"], str(_ROOT))
    assert not red, "\n".join(red)


def test_every_blind_except_suppression_gives_a_reason():
    blank = _tree_result()["blank"]
    assert not blank, "\n".join(blank)


def test_ruff_keeps_the_suppressions_of_the_codes_the_gate_owns():
    """ruff's RUF100 would delete a `# noqa: DROP001` as an unknown code unless
    the code is declared `external`. pyproject.toml.jinja's ruff tables are held
    equal to these by tests/integration/test_copier_generation.py."""
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lint = tomllib.loads(text)["tool"]["ruff"]["lint"]
    assert "external" in lint, "pyproject.toml [tool.ruff.lint] has no `external`"
    owned = (_NARROW_CODE, _SUPPRESS_CODE, _IGNORE_CODE)
    assert set(owned) <= set(lint["external"]), lint["external"]


# --- fixtures: each rule can fail ---------------------------------------------------


def _project(tmp_path, text):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "mod.py").write_text(text, encoding="utf-8")
    return root


def _wrap(handler):
    return "def f():\n    try:\n        g()\n%s" % handler


@pytest.mark.parametrize(
    "handler, what",
    [
        ("    except:\n        pass\n", "a bare `except:`"),
        ("    except:\n        raise\n", "a bare `except:`"),
        ("    except Exception:\n        pass\n", "`except Exception`"),
        ("    except BaseException:\n        return None\n", "`except BaseException`"),
        (
            "    except (ValueError, Exception):\n        return 0\n",
            "`except Exception`",
        ),
        ("    except builtins.Exception:\n        ...\n", "`except Exception`"),
        ("    except Exception as exc:\n        return\n", "`except Exception`"),
        ("    except Exception:  # noqa: BLE001\n        pass\n", "`except Exception`"),
        (
            "    except Exception:  # noqa: BLE001 --  \n        pass\n",
            "`except Exception`",
        ),
        ("    except Exception:\n        return -1\n", "`except Exception`"),
        ("    except Exception:\n        return []\n", "`except Exception`"),
        ("    except Exception:\n        return {}\n", "`except Exception`"),
        ("    except Exception:\n        return ()\n", "`except Exception`"),
        (
            "    except Exception:\n        return {'ok': False, 'n': -1}\n",
            "`except Exception`",
        ),
        ("    except Exception:\n        x = None\n", "`except Exception`"),
        (
            "    except Exception:  # noqa: BLE001 E722\n        pass\n",
            "`except Exception`",
        ),
    ],
    ids=[
        "bare pass",
        "bare raise",
        "Exception pass",
        "BaseException return None",
        "tuple return constant",
        "attribute ellipsis",
        "bound name dropped",
        "suppression without reason",
        "suppression with blank reason",
        "return a negative constant",
        "return an empty list",
        "return an empty dict",
        "return an empty tuple",
        "return a container of constants",
        "assign a constant and fall through",
        "space-separated codes, no reason",
    ],
)
def test_a_swallowing_handler_is_a_finding(tmp_path, handler, what):
    result = swallow_findings(_project(tmp_path, _wrap(handler)))
    assert len(result["findings"]) == 1, result
    assert result["findings"][0].startswith("src/mod.py:4: %s" % what), result


@pytest.mark.parametrize(
    "handler",
    [
        "    except Exception:\n        raise\n",
        "    except Exception as exc:\n        raise RuntimeError('g') from exc\n",
        "    except Exception as exc:\n        log(exc)\n        return 1\n",
        "    except ValueError as exc:\n        log(exc)\n",
        "    except Exception:  # noqa: BLE001 -- g's failure is reported by g\n"
        "        pass\n",
        "    except:  # noqa: E722 — the probe may fail in any way\n        return None\n",
        "    except (\n        Exception\n    ):  # noqa: BLE001: any probe failure\n"
        "        pass\n",
        "    except Exception:  # noqa: BLE001 E722 -- g's failure is reported by g\n"
        "        pass\n",
        "    except Exception as exc:\n        return [exc]\n",
    ],
    ids=[
        "re-raise",
        "raise from",
        "uses the error",
        "narrow type that uses the error",
        "reasoned BLE001",
        "reasoned E722",
        "reason on the clause's last line",
        "space-separated codes with a reason",
        "returns the error in a container",
    ],
)
def test_a_handler_that_handles_or_explains_is_no_finding(tmp_path, handler):
    result = swallow_findings(_project(tmp_path, _wrap(handler)))
    assert result["findings"] == [] and result["narrow"] == [], result
    assert result["handlers"] == 1, result


def _loop(handler):
    return "def f():\n    for x in xs:\n        try:\n            g(x)\n%s" % handler


@pytest.mark.parametrize(
    "text, what",
    [
        (_wrap("    except ValueError:\n        pass\n"), "`except ValueError`"),
        (
            _wrap("    except (KeyError, OSError):\n        ...\n"),
            "`except (KeyError, OSError)`",
        ),
        (
            _wrap("    except os.error as exc:\n        'ignored'\n"),
            "`except os.error`",
        ),
        (
            _loop("        except ValueError:\n            continue\n"),
            "`except ValueError`",
        ),
        (
            _loop("        except ValueError:\n            break\n"),
            "`except ValueError`",
        ),
        (
            _wrap("    except ValueError:  # noqa: DROP001\n        pass\n"),
            "`except ValueError`",
        ),
        (
            _wrap(
                "    except ValueError:  # noqa: BLE001 -- wrong code\n        pass\n"
            ),
            "`except ValueError`",
        ),
    ],
    ids=[
        "pass",
        "tuple ellipsis",
        "attribute string",
        "continue",
        "break",
        "suppression without reason",
        "another rule's code",
    ],
)
def test_a_narrow_handler_that_only_drops_the_error_is_a_finding(tmp_path, text, what):
    result = swallow_findings(_project(tmp_path, text))
    assert result["findings"] == [], result
    assert len(result["narrow"]) == 1, result
    line = result["narrow"][0]
    assert line.split(": ", 1)[1].startswith(what), result
    assert "# noqa: DROP001 --" in line, line


@pytest.mark.parametrize(
    "handler",
    [
        "    except ValueError:  # noqa: DROP001 -- the probe may find no value\n"
        "        pass\n",
        "    except ValueError:\n        raise\n",
        "    except ValueError:\n        return None\n",
        "    except ValueError:\n        cleanup()\n",
        "    except Exception:  # noqa: BLE001 -- g reports its own failure\n"
        "        pass\n",
    ],
    ids=[
        "reasoned DROP001",
        "re-raise",
        "fixed value, the next slice's rule",
        "does work",
        "broad type is the broad rule's",
    ],
)
def test_a_narrow_handler_that_acts_or_explains_is_no_finding(tmp_path, handler):
    result = swallow_findings(_project(tmp_path, _wrap(handler)))
    assert result["narrow"] == [], result


def _calls(body):
    return (
        "def f():\n    try:\n        g()\n    except Exception:\n        raise\n" + body
    )


@pytest.mark.parametrize(
    "body, what, code",
    [
        (
            "import contextlib\nwith contextlib.suppress(OSError):\n    h()\n",
            "`contextlib.suppress(...)`",
            "DROP002",
        ),
        (
            "import contextlib as cl\nwith cl.suppress(OSError):\n    h()\n",
            "`contextlib.suppress(...)`",
            "DROP002",
        ),
        (
            "from contextlib import suppress\nwith suppress(OSError):\n    h()\n",
            "`contextlib.suppress(...)`",
            "DROP002",
        ),
        (
            "from contextlib import suppress as quiet\nwith quiet(OSError):\n    h()\n",
            "`contextlib.suppress(...)`",
            "DROP002",
        ),
        (
            "shutil.rmtree(d, ignore_errors=True)\n",
            "`ignore_errors=True`",
            "DROP003",
        ),
        (
            "shutil.rmtree(\n    d,\n    ignore_errors=True,\n)\n",
            "`ignore_errors=True`",
            "DROP003",
        ),
        (
            "shutil.rmtree(d, ignore_errors=True)  # noqa: DROP003\n",
            "`ignore_errors=True`",
            "DROP003",
        ),
        (
            "shutil.rmtree(d, ignore_errors=True)  # noqa: DROP002 -- wrong code\n",
            "`ignore_errors=True`",
            "DROP003",
        ),
    ],
    ids=[
        "module attribute",
        "module alias",
        "imported name",
        "imported alias",
        "ignore_errors",
        "ignore_errors over lines",
        "suppression without reason",
        "another rule's code",
    ],
)
def test_a_call_that_drops_an_error_is_a_finding(tmp_path, body, what, code):
    result = swallow_findings(_project(tmp_path, _calls(body)))
    assert len(result["calls"]) == 1, result
    line = result["calls"][0]
    assert line.split(": ", 1)[1].startswith(what), result
    assert "# noqa: %s --" % code in line, line


@pytest.mark.parametrize(
    "body",
    [
        "import contextlib\n"
        "with contextlib.suppress(OSError):  # noqa: DROP002 -- h is best effort\n"
        "    h()\n",
        "shutil.rmtree(\n    d,\n    ignore_errors=True,\n)  # noqa: DROP003 -- scratch\n",
        "shutil.rmtree(d, ignore_errors=False)\n",
        "shutil.rmtree(d, ignore_errors=flag)\n",
        "with suppress(OSError):\n    h()\n",
        "import contextlib\nwith contextlib.nullcontext():\n    h()\n",
        "with other.suppress(OSError):\n    h()\n",
    ],
    ids=[
        "reasoned DROP002",
        "reasoned DROP003 after the closing bracket",
        "ignore_errors False",
        "ignore_errors not a constant",
        "suppress not from contextlib",
        "another contextlib call",
        "suppress of another module",
    ],
)
def test_a_call_that_keeps_or_explains_the_error_is_no_finding(tmp_path, body):
    result = swallow_findings(_project(tmp_path, _calls(body)))
    assert result["calls"] == [], result


@pytest.mark.parametrize("code", ["DROP001", "DROP002", "DROP003"])
def test_a_blank_reason_on_a_gate_owned_code_is_a_finding(tmp_path, code):
    text = _calls("x = 1  # noqa: %s\n" % code)
    result = swallow_findings(_project(tmp_path, text))
    assert result["blank"] == [
        "src/mod.py:6: `# noqa: %s` gives no reason; say after the codes why "
        "the error may be dropped, or handle it" % code
    ], result


def test_a_blank_suppression_reason_is_a_finding_wherever_it_stands(tmp_path):
    text = (
        "def f():\n"
        "    try:\n"
        "        g()\n"
        "    except Exception as exc:  # noqa: BLE001\n"
        "        log(exc)\n"
        "x = 1  # noqa: E501\n"
    )
    result = swallow_findings(_project(tmp_path, text))
    assert result["findings"] == [], result
    assert result["blank"] == [
        "src/mod.py:4: `# noqa: BLE001` gives no reason; say after the codes why "
        "the error may be dropped, or handle it"
    ], result


def test_a_tree_with_no_handler_is_an_error_not_a_pass(tmp_path):
    with pytest.raises(st.SourceTreeError, match="zero items"):
        swallow_findings(_project(tmp_path, "x = 1\n"))


def test_a_tree_with_no_python_file_is_an_error_not_a_pass(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(st.SourceTreeError, match="zero items"):
        swallow_findings(root)


def test_space_separated_codes_are_all_codes_never_the_reason(tmp_path):
    """ruff reads codes separated by spaces as well as commas, so a second
    code is no reason for the first."""
    text = (
        "def f():\n"
        "    try:\n"
        "        g()\n"
        "    except Exception as exc:  # noqa: BLE001 E722\n"
        "        log(exc)\n"
    )
    result = swallow_findings(_project(tmp_path, text))
    assert result["blank"] == [
        "src/mod.py:4: `# noqa: BLE001, E722` gives no reason; say after the codes "
        "why the error may be dropped, or handle it"
    ], result
