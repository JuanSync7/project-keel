"""
title: Selection guard — refuse narrowed full gates and runs with zero tests
summary: A full gate accepts only configured harmless flag/value options in command-line tokens or shlex-parsed PYTEST_ADDOPTS; unknown tokens (including -k, -m, node ids and --deselect) and malformed environment quoting return ExitCode.USAGE, and an invalid allowlist returns ExitCode.CONFIG. The end-of-session verdict makes a run of zero tests exit 5, unless one bare marker make_targets.empty_test_selections declares is run over the configured suite with no -k or explicit path; a declared marker whose tests ran exits 1 as stale.

The Makefile runs this module before pytest so malformed PYTEST_ADDOPTS cannot
escape as pytest's own parse error. Its --keel-full-gate option makes conftest
check the actual invocation too. Tier targets and direct pytest omit that
option. This module writes no gate evidence.

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

import os
import re
import shlex
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

_KEY = "empty_test_selections"
_BARE_MARKER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EXPRESSION_WORDS = ("and", "or", "not")
_OPTIONS_KEY = ("tests", "full_gate_options")


def _full_gate_options():
    """Read and validate the configured flag/value allowlist."""
    options = config_loader.resolve(
        config_loader.read(_ROOT),
        config_loader.rows(_OPTIONS_KEY),
        config_loader.CONFIG_FILE,
        environ={},
    )[_OPTIONS_KEY]
    if not options:
        raise ValueError("full_gate_options must name at least one harmless option")
    for name, row in options.items():
        if (
            not re.fullmatch(r"-[A-Za-z]|--[a-z][a-z-]*", name)
            or not isinstance(row, dict)
            or row.get("kind") not in ("flag", "value")
            or not isinstance(row.get("_comment"), str)
            or not row["_comment"].strip()
            or (
                "values" in row
                and (
                    row["kind"] != "value"
                    or not isinstance(row["values"], list)
                    or not row["values"]
                    or not all(isinstance(value, str) for value in row["values"])
                )
            )
        ):
            raise ValueError("invalid full_gate_options entry %s" % name)
    return options


def _unrecognised(tokens, options):
    """Return the first token not proved harmless, with its offending option."""
    tokens = iter(tokens)
    for token in tokens:
        if token.startswith("--"):
            name, equals, value = token.partition("=")
            row = options.get(name)
            if row is None:
                return token, name
            if row["kind"] == "flag":
                if equals:
                    return token, name
                continue
            if not equals:
                value = next(tokens, None)
            if value is None or ("values" in row and value not in row["values"]):
                return token, "%s value %r" % (name, value)
        elif token.startswith("-") and token != "-":
            # argparse walks flag letters until a value letter owns the suffix.
            for offset, letter in enumerate(token[1:], 2):
                name = "-" + letter
                row = options.get(name)
                if row is None:
                    return token, name
                if row["kind"] == "value":
                    value = token[offset:]
                    if value.startswith("="):
                        value = value[1:]
                    elif not value:
                        value = next(tokens, None)
                    if value is None or (
                        "values" in row and value not in row["values"]
                    ):
                        return token, "%s value %r" % (name, value)
                    break
        else:
            return token, "node id" if "::" in token else "path"
    return None


def check_full_gate(args, addopts):
    """Require harmless argv and shlex-parsed PYTEST_ADDOPTS through a named exit."""
    try:
        env_tokens = shlex.split(addopts)
    except ValueError:
        return report(
            ExitCode.USAGE,
            "full gate cannot parse PYTEST_ADDOPTS",
            "PYTEST_ADDOPTS",
            "correct its shell quoting and run the full gate again",
        )
    try:
        options = _full_gate_options()
    except (config_loader.ConfigError, ValueError) as exc:
        return report(
            ExitCode.CONFIG,
            "full gate cannot read its option allowlist: %s" % exc,
            "tests.full_gate_options",
            "correct the configured flag/value entries and run the full gate again",
        )
    for source, tokens in (("command line", args), ("PYTEST_ADDOPTS", env_tokens)):
        refused = _unrecognised(tokens, options)
        if refused is not None:
            token, name = refused
            return report(
                ExitCode.USAGE,
                "full gate refuses unrecognised or narrowing token %s (%s)"
                % (token, name),
                source,
                "remove the selection or use a tier target or direct pytest",
            )
    return ExitCode.SUCCESS


def main():
    """Check the full gate before pytest parses PYTEST_ADDOPTS or writes reports."""
    return check_full_gate(sys.argv[1:], os.environ.get("PYTEST_ADDOPTS", ""))


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
    try:
        if manifest is None:
            manifest = config_loader.read(_ROOT)
        config_loader.resolve(
            manifest,
            config_loader.rows(("make_targets",)),
            config_loader.CONFIG_FILE,
            environ={},
        )
    except config_loader.ConfigError as exc:
        raise RuntimeError("; ".join(exc.lines)) from exc
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


if __name__ == "__main__":
    finish(main())
