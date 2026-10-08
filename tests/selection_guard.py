"""
title: Selection guard — a test run that ran zero tests fails
summary: The verdict tests/conftest.py applies when a pytest session ends. pytest exits 5 only when nothing is collected; a selection whose every test skipped exits 0, so a tier can be green with no assertion executed. Here zero tests ran is exit 5, with a message naming the selection as the run made it, unless the selection is one bare `-m` marker config/project.json make_targets.empty_test_selections declares, run over the configured suite with no `-k` and no explicit path, which exits 0 and prints its reason; a declared marker whose tests did run exits 1, because the declaration has gone stale.

Why "ran" and not "collected": a skip executes no assertion, so a selection
of only skips proves as little as an empty one. A test counts as ran when its
call phase passed or failed, or it is an xfail, which executed and failed as
predicted.

Only a single bare marker can be declared empty, and only for the run of
the configured suite. A compound expression (`smoke and not slow`), the whole
suite, and a run narrowed by `-k` or an explicit path never can: an exemption
has to name one thing that a reader can check has no tests. The message names
the selection as the run made it (`describe`), so a narrowed run is never
reported as the whole suite.

The declarations are read through scripts/check_structure.py
make_targets_policy, the same reader check_W applies, and a block it rejects
raises instead of reading as "nothing declared" -- a typo must not turn the
guard back into a pass over zero tests.
"""

import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KEY = "empty_test_selections"
_BARE_MARKER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EXPRESSION_WORDS = ("and", "or", "not")


def _policy_reader():
    scripts = os.path.join(_ROOT, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import check_structure

    return check_structure.make_targets_policy


def declared_empty(manifest=None):
    """make_targets.empty_test_selections ({marker: reason}) from `manifest`,
    or from this project's config/project.json when None. Raises RuntimeError
    when the policy rejects the make_targets block."""
    if manifest is None:
        path = os.path.join(_ROOT, "config", "project.json")
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    policy, errs = _policy_reader()(manifest)
    if policy is None:
        raise RuntimeError(
            "config/project.json make_targets (read for %s): %s"
            % (_KEY, "; ".join(errs))
        )
    return dict(policy[_KEY])


def selected_markers(markexpr):
    """[marker] when `markexpr` selects exactly one bare marker, else []."""
    expr = (markexpr or "").strip()
    if _BARE_MARKER.match(expr) and expr not in _EXPRESSION_WORDS:
        return [expr]
    return []


def describe(markexpr, keyword="", paths=()):
    """The selection a run made, as the message names it: its `-m` and `-k`
    expressions and the paths it was given, or "the whole suite"."""
    parts = []
    if (markexpr or "").strip():
        parts.append("-m %s" % markexpr.strip())
    if (keyword or "").strip():
        parts.append("-k %s" % keyword.strip())
    parts.extend(paths)
    return " ".join(parts) if parts else "the whole suite"


def verdict(ran, markexpr, declared, keyword="", paths=()):
    """(exit code, message) for a session that ran `ran` tests under `-m
    markexpr`, `-k keyword` and the explicit `paths`, with `declared` empty
    selections; (None, "") leaves it alone. A declaration exempts only the
    bare `-m <marker>` run of the configured suite: narrowed by `-k` or a path,
    the selection is no longer the one a reader checked has no tests."""
    markers = selected_markers(markexpr)
    marker = markers[0] if markers else None
    narrowed = bool((keyword or "").strip()) or bool(paths)
    declarable = marker is not None and not narrowed
    if ran == 0:
        if declarable and marker in declared:
            return 0, "empty selection declared: %s" % declared[marker]
        selection = describe(markexpr, keyword, paths)
        if declarable:
            advice = (
                "declare the marker in config/project.json make_targets.%s "
                "or add a test" % _KEY
            )
        else:
            advice = (
                "only a bare -m <marker> run can be declared empty "
                "(config/project.json make_targets.%s); add a test this "
                "selection runs or change the selection" % _KEY
            )
        return 5, "zero tests ran for %s; %s" % (selection, advice)
    if marker is not None and marker in declared:
        return (
            1,
            "stale: make_targets.%s.%s but %d tests ran" % (_KEY, marker, ran),
        )
    return None, ""
