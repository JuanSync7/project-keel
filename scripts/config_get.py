#!/usr/bin/env python3
"""
title: config_get — print one configured value for a shell script
kind: script
layer: n/a
effect: read-only
summary: The shell side of scripts/config_loader.py. `config_get.py KEY` prints the value `resolve` gives the KEYS row whose dotted path is KEY, read from the row's file (config/project.json or config/practices.json; none for a variable-only row) and its variable, with the loader's precedence, default and type check; a string is printed as written and any other value as canonical JSON (sorted keys, `null` for None), on one line of stdout, while the loader's own lines go to stderr. A shell script reads `"$(python3 "$(dirname "$0")/config_get.py" KEY)"` instead of parsing the file itself, so a value has one reader and one rule (tests/integration/test_config_reads_gate.py fails a shell script that names a config file). Not one key, or a key no row declares, is USAGE; a secret row is USAGE and its value is never read, since a printed secret lands in a log; an absent or unreadable file and a wrong or missing value are CONFIG. Nothing reaches stdout on a refusal. Stdlib-only and 3.6-safe, since a shell script runs it with the host `python3`.
"""

# NB: stdlib only, no f-strings, no annotations: a shell script runs it with
# the host's bare `python3`, which may be 3.6 (as config_loader's own note says).

import json
import os
import sys

import config_loader
from exit_codes import ExitCode, finish, report

__all__ = ["main"]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENVIRONMENT = "the environment"


def _row(key):
    """The KEYS rows whose dotted path is *key*."""
    return [k for k in config_loader.KEYS if ".".join(k.path) == key]


def main(argv=None, root=None):
    """Print the value of the one key *argv* names, read under *root* (the
    project this module ships in when None)."""
    args = sys.argv[1:] if argv is None else list(argv)
    base = _ROOT if root is None else root
    if len(args) != 1:
        return report(
            ExitCode.USAGE,
            "config_get: name one key, not %d" % len(args),
            "the command line",
            "run `config_get.py KEY` with KEY a dotted path from "
            "scripts/config_loader.py KEYS, e.g. shell.formatter",
        )
    key = args[0]
    found = _row(key)
    if len(found) != 1:
        return report(
            ExitCode.USAGE,
            "config_get: %s is not a key scripts/config_loader.py KEYS declares"
            % config_loader.shown(key, bare=True),
            "the command line",
            "name a declared key, or add a KEYS row for it before reading it",
        )
    row = found[0]
    if row.secret:
        return report(
            ExitCode.USAGE,
            "config_get: %s is a secret, and a printed secret lands in a log" % key,
            "the command line",
            "let the program that needs it read it from the environment",
        )
    where = _ENVIRONMENT if row.file is None else row.file
    try:
        loaded = {} if row.file is None else config_loader.read(base, row.file)
        value = config_loader.resolve(loaded, (row,), where)[row.path]
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.USAGE if config_loader.is_conflict(exc) else ExitCode.CONFIG,
            "config_get: %s cannot be read" % key,
            "; ".join(exc.lines),
            "correct %s as the line says, then run it again" % where,
        )
    if isinstance(value, str):
        sys.stdout.write(value + "\n")
    else:
        sys.stdout.write(json.dumps(value, sort_keys=True) + "\n")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
