#!/usr/bin/env python3
"""
title: run_app — run the composition root config/project.json declares
summary: `make run` runs this. It reads config/project.json `layers.app` and runs that module as `__main__` with the arguments it was given, so the entrypoint lives in the manifest scripts/check_structure.py check_H validates, not in the Makefile. An absent or null `layers.app` exits 2 with a message saying which, and the module's own exit code comes back unchanged. A first argument `-h`/`--help` describes this runner and runs nothing (scripts/AGENT.md); the app's own arguments go after `--` when the first of them would otherwise be read here. It writes nothing and starts no process.

What `layers.app` must hold is decided once, by check_structure.composition_root,
which check_H also applies, so the gate and this runner cannot disagree about
what is runnable. The import root it derives (the path minus the module's
dotted components) goes first on sys.path, in place of this script's own
directory, which would otherwise shadow a module of the same name.
"""

import json
import os
import runpy
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

sys.path.insert(0, _HERE)
from check_structure import composition_root  # noqa: E402

del sys.path[0]

_ABSENT = (
    'config/project.json layers.app is not declared; declare {"path","module"} or null'
)
_NULL = "no composition root declared (layers.app is null)"
_USAGE = """usage: run_app.py [-h] [--] [ARG ...]

Run the composition root config/project.json layers.app declares (its
"module", imported from the root its "path" implies) as __main__, passing
ARG ... to it, and exit with its exit code. Exit 2 when layers.app is absent,
null or malformed. Put the app's own arguments after `--` when the first one
is -h, --help or --; any other first argument is passed through as it is.

  -h, --help  show this message and exit; the app does not run
"""


def _refuse(message):
    sys.stderr.write("run_app: %s\n" % message)
    return 2


def main(argv=None, root=None):
    """Run the declared composition root with `argv`; return 2 when none is."""
    root = _ROOT if root is None else root
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ("-h", "--help"):
        sys.stdout.write(_USAGE)
        return 0
    if argv and argv[0] == "--":
        argv = argv[1:]
    with open(os.path.join(root, "config", "project.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    layers = manifest.get("layers") if isinstance(manifest, dict) else None
    if not isinstance(layers, dict) or "app" not in layers:
        return _refuse(_ABSENT)
    app = layers["app"]
    if app is None:
        return _refuse(_NULL)
    problems, import_root = composition_root(app, root)
    if problems:
        return _refuse("config/project.json: " + "; ".join(problems))
    # Python put this script's directory first; the composition root's import
    # root replaces it.
    if sys.path and os.path.abspath(sys.path[0] or os.curdir) == _HERE:
        del sys.path[0]
    sys.path.insert(0, import_root)
    module = app["module"]
    sys.argv = [module] + argv
    # A SystemExit the module raises propagates: its code is the process's.
    runpy.run_module(module, run_name="__main__", alter_sys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
