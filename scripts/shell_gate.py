#!/usr/bin/env python3
"""
title: shell_gate — the shell scripts' lint, format and test gates
kind: script
layer: n/a
summary: The one adapter between keel's shell targets and the tools that judge shell, so a make target names a role and never a vendor. `lint` runs config/project.json `shell.linter`, `format-check` and `format` run `shell.formatter` (reporting a difference, and rewriting the files in place), and `test` runs `shell.test_runner`; each name must be one this module has an adapter for (shellcheck, shfmt and bats), or every mode is CONFIG before anything runs, because the flags are the tool's own. The files judged are what a commit could carry (scripts/git_tree.py candidate_files) that are regular files and not symlinks, a deleted tracked path left out: a shell script ends in a `shell.script_suffixes` suffix or opens with a shebang whose interpreter, after `env` and its options, is one of `shell.shebang_shells`, and a `shell.test_suffixes` file is a test, which only the test mode runs. The tool is looked up in the running interpreter's directory first, where a virtual environment installs one, then on PATH; one on neither is BACKEND_ABSENT naming it and its role, never a skip. It runs under the allowlisted environment (scripts/child_env.py) and its status is passed through, so a finding is the tool's own status. The test mode first asks the runner to count the tests: zero is NOTHING_JUDGED, and a count that is not a whole number, or a counting run that fails, is BACKEND_ABSENT, because the runner gave no verdict. Shell scripts with no test file are NOTHING_JUDGED, because a pass over zero tests proves nothing. With no shell script and no test file, or with `shell.enabled` false (the copier answer `shell`), every mode says why on stdout and exits 0 having run no tool. No repository is NOTHING_JUDGED, a git or file read that fails is USAGE, and a malformed shell block or child_env block is CONFIG.
effect: writes
rerun: fixed-point
rerun_proof: make:fmt-check-sh
"""

import argparse
import os
import shutil
import subprocess
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402
import git_tree  # noqa: E402
from child_env import ChildEnvError, build_child_env  # noqa: E402
from exit_codes import ExitCode, finish, passthrough, report  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
_BLOCK = ("shell",)
_FIELDS = (
    "enabled",
    "formatter",
    "linter",
    "script_suffixes",
    "shebang_shells",
    "test_runner",
    "test_suffixes",
)
_LINT, _FORMAT_CHECK, _FORMAT, _TEST = "lint", "format-check", "format", "test"
_ROLE = {
    _LINT: "linter",
    _FORMAT_CHECK: "formatter",
    _FORMAT: "formatter",
    _TEST: "test_runner",
}
# Per role, per adapter name, the flags each mode hands the tool before the
# files. These are the tools' own flags, which is why a name outside this table
# is refused rather than run with a guess.
_ADAPTERS = {
    "linter": {"shellcheck": {_LINT: ()}},
    # -d prints a diff and exits 1 when a file would change; -w rewrites in place.
    "formatter": {"shfmt": {_FORMAT_CHECK: ("-d",), _FORMAT: ("-w",)}},
    "test_runner": {"bats": {_TEST: ()}},
}
# The test runner's flag that prints the number of tests and runs none.
_COUNT_FLAG = {"bats": "--count"}
# How to install each adapter's tool, for the BACKEND_ABSENT next step.
_INSTALL = {
    "shellcheck": "install ShellCheck (a distribution package, or the "
    "shellcheck-py wheel into this virtual environment)",
    "shfmt": "install shfmt (a distribution package, or the shfmt-py wheel into "
    "this virtual environment)",
    "bats": "install bats-core (a distribution package, or its npm package) so "
    "`bats` is on PATH",
}
_WHERE = "config/project.json shell"
# `env` options that take the next word as their argument, so that word is not
# the interpreter (GNU coreutils env: --unset, --chdir; BSD env: -P).
_ENV_ARG_OPTIONS = frozenset(("-u", "--unset", "-C", "--chdir", "-P"))
# A shebang line longer than this is no interpreter line the kernel would run.
_SHEBANG_MAX = 256
_NAMED_MAX = 5


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="scripts/shell_gate.py",
        description="Lint, format-check, format or test the project's shell "
        "scripts with the tools config/project.json shell names.",
    )
    parser.add_argument(
        "mode",
        choices=(_LINT, _FORMAT_CHECK, _FORMAT, _TEST),
        help="lint, check the formatting of, format in place, or run the tests "
        "of the shell scripts",
    )
    return parser.parse_args(argv)


def _settings(root):
    keys = config_loader.rows(*[_BLOCK + (field,) for field in _FIELDS])
    values = config_loader.resolve(
        config_loader.read(root), keys, config_loader.CONFIG_FILE
    )
    return {field: values[_BLOCK + (field,)] for field in _FIELDS}


def _unknown_adapter(cfg):
    """The (role, name) of the first configured tool with no adapter, or None."""
    for role in sorted(_ADAPTERS):
        if cfg[role] not in _ADAPTERS[role]:
            return role, cfg[role]
    return None


def _shebang_interpreter(path):
    """The interpreter name a file's `#!` line runs, `env` and its options
    stepped over, or None for no shebang."""
    with open(path, "rb") as fh:
        first = fh.readline(_SHEBANG_MAX)
    if not first.startswith(b"#!"):
        return None
    words = first[2:].decode("latin-1").split()
    if not words:
        return None
    if os.path.basename(words[0]) != "env":
        return os.path.basename(words[0])
    rest = iter(words[1:])
    for word in rest:
        if word == "--":
            return next(rest, None)
        if word in _ENV_ARG_OPTIONS:
            next(rest, None)
        elif word.startswith("-") or "=" in word:
            continue
        else:
            return os.path.basename(word)
    return None


def _classify(root, cfg):
    """(shell scripts, shell tests), each a sorted list of repo-relative paths."""
    scripts, tests = [], []
    script_suffixes = tuple(cfg["script_suffixes"])
    test_suffixes = tuple(cfg["test_suffixes"])
    shells = frozenset(cfg["shebang_shells"])
    for rel in git_tree.candidate_files(root):
        path = os.path.join(root, rel)
        # A symlink is judged at its target, which is itself a candidate when
        # the project carries it; a deleted tracked path has nothing to judge.
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        if rel.endswith(test_suffixes):
            tests.append(rel)
        elif rel.endswith(script_suffixes) or _shebang_interpreter(path) in shells:
            scripts.append(rel)
    return sorted(scripts), sorted(tests)


def _interpreter_dir():
    """The running interpreter's directory, where a virtual environment puts
    the tools a wheel installed, or None."""
    return os.path.dirname(sys.executable) or None


def _find(name):
    """The tool's path: the interpreter's directory first, then PATH."""
    here = _interpreter_dir()
    return (here and shutil.which(name, path=here)) or shutil.which(name)


def _operands(paths):
    # A path that starts with `-` would read as an option, and not every
    # adapted tool takes `--` to end its options.
    return ["./" + p if p.startswith("-") else p for p in paths]


def _named(paths):
    shown = ", ".join(paths[:_NAMED_MAX])
    if len(paths) > _NAMED_MAX:
        shown += " and %d more" % (len(paths) - _NAMED_MAX)
    return shown


def _say(text):
    sys.stdout.write("shell_gate: %s\n" % text)
    sys.stdout.flush()


def _count_tests(exe, name, tests, root):
    """The number of tests the runner finds in *tests*, or None with why not."""
    proc = subprocess.run(
        [exe, _COUNT_FLAG[name]] + _operands(tests),
        cwd=root,
        env=build_child_env(root=root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    text = proc.stdout.strip()
    if proc.returncode != 0:
        return None, "exited %d while counting (%s)" % (
            proc.returncode,
            proc.stderr.strip()[:200] or "no stderr",
        )
    if not text or text.strip("0123456789"):
        return None, "printed %r where a test count belongs" % text[:80]
    return int(text), None


def _gate(mode, root, cfg):
    role = _ROLE[mode]
    name = cfg[role]
    scripts, tests = _classify(root, cfg)
    judged = tests if mode == _TEST else scripts
    if not judged:
        if mode == _TEST and scripts:
            return report(
                ExitCode.NOTHING_JUDGED,
                "%d shell script(s) (%s) and no shell test to run"
                % (len(scripts), _named(scripts)),
                root,
                "add a test file ending in %s for them, or set shell.enabled to "
                "false" % " or ".join(cfg["test_suffixes"]),
            )
        _say(
            "no shell %s in what a commit could carry, so %s ran no tool"
            % ("test" if mode == _TEST else "script", mode)
        )
        return ExitCode.SUCCESS
    exe = _find(name)
    if exe is None:
        return report(
            ExitCode.BACKEND_ABSENT,
            "the %s %s (shell.%s) is not installed"
            % (role.replace("_", " "), name, role),
            "the interpreter's directory and PATH",
            _INSTALL[name] + ", then rerun",
        )
    if mode == _TEST:
        count, why = _count_tests(exe, name, judged, root)
        if count is None:
            return report(
                ExitCode.BACKEND_ABSENT,
                "the test runner %s gave no verdict: it %s" % (name, why),
                _named(judged),
                "run `%s %s` on those files by hand and fix the runner"
                % (name, _COUNT_FLAG[name]),
            )
        if count == 0:
            return report(
                ExitCode.NOTHING_JUDGED,
                "the shell test files hold 0 tests",
                _named(judged),
                "add a test to them, or remove the empty files",
            )
    flags = list(_ADAPTERS[role][name][mode])
    _say("%s (shell.%s) %s over %d file(s)" % (name, role, mode, len(judged)))
    proc = subprocess.run(
        [exe] + flags + _operands(judged), cwd=root, env=build_child_env(root=root)
    )
    return passthrough(proc.returncode)


def main(argv=None, root=None):
    try:
        args = _parse(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        # argparse ends the process itself: status 0 after --help, and a usage
        # error it has already written to stderr otherwise.
        if not exc.code:
            return ExitCode.SUCCESS
        return report(
            ExitCode.USAGE,
            "argparse refused the arguments above",
            "the command line",
            "call it with one of lint, format-check, format or test",
        )
    root = os.path.abspath(ROOT if root is None else root)
    try:
        cfg = _settings(root)
        unknown = _unknown_adapter(cfg)
        if unknown is not None:
            role, name = unknown
            return report(
                ExitCode.CONFIG,
                "shell.%s is %r, and scripts/shell_gate.py has adapters for %s only"
                % (role, name, ", ".join(sorted(_ADAPTERS[role]))),
                "%s.%s" % (_WHERE, role),
                "name one of those, or add an adapter for that tool first",
            )
        if not cfg["enabled"]:
            _say(
                "shell.enabled is false in config/project.json, so %s ran no tool"
                % args.mode
            )
            return ExitCode.SUCCESS
        return _gate(args.mode, root, cfg)
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the shell settings are refused",
            "; ".join(exc.lines),
            "fix the shell block of config/project.json, then rerun",
        )
    except ChildEnvError as exc:
        return report(
            ExitCode.CONFIG,
            "the shell tool's environment cannot be built (%s)" % exc,
            "config/project.json child_env",
            "fix the child_env block, then rerun",
        )
    except git_tree.NoGitError as exc:
        return report(
            ExitCode.NOTHING_JUDGED,
            "there is no git repository to list the shell scripts from (%s)" % exc,
            root,
            "run `git init` and add the project's files, then rerun",
        )
    except git_tree.GitFailedError as exc:
        return report(
            ExitCode.USAGE,
            "git failed (%s)" % exc,
            root,
            "fix the repository git cannot read, then rerun",
        )
    except OSError as exc:
        return report(
            ExitCode.USAGE,
            "a file could not be read (%s)" % exc,
            root,
            "make the file readable, or remove it, then rerun",
        )


if __name__ == "__main__":
    finish(main())
