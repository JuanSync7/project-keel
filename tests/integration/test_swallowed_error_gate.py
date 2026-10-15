"""
title: Integration — no error is swallowed without a stated reason
kind: tests
layer: n/a
summary: A tree-wide gate over every Python file tests/source_tree.py `python_files` lists, read from the syntax tree. It fails a bare `except:`, and an `except` whose type is `Exception` or `BaseException` (alone, in a tuple, or as an attribute such as `builtins.Exception`) when the handler has no `raise` and its body only passes, continues, breaks, returns nothing or a fixed value (a constant, a signed constant such as `-1`, or a list, tuple, set or dict of them such as `[]`), assigns a fixed value, or holds a bare constant: such a handler throws the failure away, so the caller reads it as a success. Either is allowed when a `# noqa: BLE001` or `# noqa: E722` suppression on a line of the `except` clause gives a reason after its codes, read by `noqa_reasons`, which takes codes separated by commas or spaces as ruff does, so a second code is never the reason. A second check fails every BLE001 or E722 suppression in the tree whose reason holds no letter or digit, because ruff honours a bare suppression and the reason is the one record of why the error may be dropped. A walk with no Python file, or with no `except` handler to judge, is a failure, never a pass. It cannot see an error dropped through `contextlib.suppress`, a handler that does work but never looks at the error, or a narrow type caught and ignored; ruff's BLE001 and E722 run beside it. Not a check_* letter: the letters A to Z are taken.
"""

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))

import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration

# The exception types that catch every error, so a handler of one that drops
# the error drops any failure at all.
_BROAD = ("Exception", "BaseException")
# ruff's codes for a blind `except Exception` and a bare `except:`.
_CODES = ("BLE001", "E722")
_FIX = (
    "raise, return the failure, or give the reason after the codes: "
    "`# noqa: BLE001 -- <why the error may be dropped>`"
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


def _clause_lines(handler):
    """The lines of the `except` clause itself, before its body."""
    last = max(handler.lineno, handler.body[0].lineno - 1)
    return range(handler.lineno, last + 1)


def _reasoned(reasons, handler):
    """True when a line of *handler*'s clause carries a BLE001 or E722
    suppression with a non-blank reason."""
    for lineno in _clause_lines(handler):
        codes, reason = reasons.get(lineno, ((), ""))
        if set(codes) & set(_CODES) and not st.blank(reason):
            return True
    return False


def swallow_findings(root):
    """{files, handlers, findings, blank}: one finding per handler that
    swallows an error with no reasoned suppression, and one per BLE001 or
    E722 suppression whose reason is blank."""
    files = st.python_files(root)
    if not files:
        raise st.SourceTreeError("%s: no Python file to judge -- zero items" % root)
    handlers, findings, blank = 0, [], []
    for relpath in files:
        tree = st.parse(root, relpath)
        reasons = st.noqa_reasons(root, relpath)
        for lineno, (codes, reason) in sorted(reasons.items()):
            used = [code for code in codes if code in _CODES]
            if used and st.blank(reason):
                blank.append(
                    "%s:%d: `# noqa: %s` gives no reason; say after the codes why "
                    "the error may be dropped, or handle it"
                    % (relpath, lineno, ", ".join(used))
                )
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            handlers += 1
            what = _swallows(node)
            if what and not _reasoned(reasons, node):
                findings.append(
                    "%s:%d: %s swallows the error, so the caller reads a failure "
                    "as a success; %s" % (relpath, node.lineno, what, _FIX)
                )
    if not handlers:
        raise st.SourceTreeError("%s: no except handler to judge -- zero items" % root)
    return {
        "files": len(files),
        "handlers": handlers,
        "findings": sorted(findings),
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


def test_every_blind_except_suppression_gives_a_reason():
    blank = _tree_result()["blank"]
    assert not blank, "\n".join(blank)


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
        "    except ValueError:\n        pass\n",
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
        "narrow type",
        "reasoned BLE001",
        "reasoned E722",
        "reason on the clause's last line",
        "space-separated codes with a reason",
        "returns the error in a container",
    ],
)
def test_a_handler_that_handles_or_explains_is_no_finding(tmp_path, handler):
    result = swallow_findings(_project(tmp_path, _wrap(handler)))
    assert result["findings"] == [] and result["handlers"] == 1, result


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
