#!/usr/bin/env python3
"""
title: check_toolchain — the configured Node major, and the versions CI installs
kind: script
layer: n/a
summary: One home for the toolchain versions config/project.json `toolchain` declares. Mode `node` runs `node --version` and compares its major with `toolchain.node_major`; another major, a node that is not on PATH, one that exits non-zero, or output that is not `v<major>.<minor>.<patch>` is FAILURE with a three-part message, so `make fe-install` refuses before npm resolves a tree under the wrong runtime. Mode `versions` prints `node=<toolchain.node_major>` and `python=<toolchain.python>`, one per line, for a CI step that appends them to `$GITHUB_OUTPUT` (the step id is `toolchain`), so setup-node and setup-python read the config and never a literal. A value the loader refuses is CONFIG naming the key; an unknown mode is USAGE. It writes nothing. Stdlib-only and 3.6-safe, because `make fe-install` may run it under an interpreter older than requires-python.
"""

import argparse
import os
import re
import subprocess
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
_KEYS = (("toolchain", "node_major"), ("toolchain", "python"))
_NODE = ["node", "--version"]
# `node --version` prints `v<major>.<minor>.<patch>`, a pre-release or build
# suffix after it (Node's documented release format). 3.6 has no stdlib version
# class, and only the major is compared, so the grammar is anchored whole.
_NODE_VERSION = re.compile(r"\Av(\d+)\.(\d+)\.(\d+)([-+][0-9A-Za-z.+-]*)?\Z")


def _run(argv):
    """(exit status, stdout) of *argv*; FileNotFoundError when it is absent."""
    done = subprocess.run(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=build_child_env()
    )
    return done.returncode, done.stdout.decode("utf-8", "replace")


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="scripts/check_toolchain.py",
        description="Check the Node on PATH against config/project.json "
        "toolchain.node_major, or print the configured versions for CI.",
    )
    parser.add_argument(
        "mode",
        choices=("node", "versions"),
        help="node: refuse a Node whose major is not toolchain.node_major; "
        "versions: print node=<major> and python=<version> for $GITHUB_OUTPUT.",
    )
    return parser.parse_args(argv)


def _node(major, runner):
    where = "`node --version` on PATH"
    fix = (
        "install Node %d, or change config/project.json toolchain.node_major "
        "and the lockfiles with it" % major
    )
    try:
        status, text = runner(list(_NODE))
    except OSError as exc:
        return report(ExitCode.FAILURE, "node cannot be run (%s)" % exc, where, fix)
    if status != 0:
        return report(ExitCode.FAILURE, "node --version exited %d" % status, where, fix)
    found = _NODE_VERSION.match(text.strip())
    if found is None:
        return report(
            ExitCode.FAILURE,
            "node --version printed %r, which is not v<major>.<minor>.<patch>"
            % text.strip(),
            where,
            fix,
        )
    have = int(found.group(1))
    if have != major:
        return report(
            ExitCode.FAILURE,
            "node major is %d, and config/project.json toolchain.node_major is %d"
            % (have, major),
            where,
            fix,
        )
    sys.stdout.write("check_toolchain: node %s is major %d\n" % (text.strip(), major))
    return ExitCode.SUCCESS


def main(argv=None, runner=None, loaded=None):
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
            "call it as `check_toolchain.py node` or `check_toolchain.py versions`",
        )
    try:
        if loaded is None:
            loaded = config_loader.read(ROOT)
        values = config_loader.resolve(
            loaded, config_loader.rows(*_KEYS), config_loader.CONFIG_FILE
        )
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the toolchain settings are refused",
            "; ".join(exc.lines),
            "fix the toolchain block of config/project.json, then rerun",
        )
    major, python = values[_KEYS[0]], values[_KEYS[1]]
    if args.mode == "versions":
        sys.stdout.write("node=%d\npython=%s\n" % (major, python))
        return ExitCode.SUCCESS
    return _node(major, _run if runner is None else runner)


if __name__ == "__main__":
    finish(main())
