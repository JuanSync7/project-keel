#!/usr/bin/env python3
"""
check_python_version.py - fail early when the selected project interpreter is too old.

The minimum Python is declared once, in pyproject.toml (`requires-python`); this
reads it (3.6-safe, no tomllib) and fails with a clear message when the selected
`python3` is older -- instead of letting pytest or application imports die later
with cryptic SyntaxErrors. Kept Python 3.6-compatible on purpose (no f-strings, no
annotations) so an old interpreter still reaches this message rather than crashing
on the syntax of the very guard meant to help it.
"""

import os
import re
import sys

_FALLBACK = (3, 10)


def required_min(root):
    """Return the (major, minor) floor from pyproject.toml requires-python.

    Falls back to _FALLBACK when pyproject.toml is absent or declares no bound, so
    the guard is best-effort and never itself the thing that breaks a build.
    """
    try:
        with open(os.path.join(root, "pyproject.toml")) as fh:
            text = fh.read()
    except OSError:
        return _FALLBACK
    m = re.search(r'requires-python\s*=\s*["\'][^0-9]*([0-9]+)\.([0-9]+)', text)
    if not m:
        return _FALLBACK
    return (int(m.group(1)), int(m.group(2)))


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    minimum = required_min(root)
    current = sys.version_info[:2]
    if current < minimum:
        sys.stderr.write(
            "ERROR: this project requires Python >=%d.%d; %s is %d.%d.\n"
            "Point PY at a newer interpreter, e.g. `make PY=python3.11 test` "
            "(or activate the project venv).\n"
            % (minimum[0], minimum[1], sys.executable, current[0], current[1]))
        return 1
    sys.stdout.write(
        "check_python_version: %s (%d.%d) satisfies >=%d.%d\n"
        % (sys.executable, current[0], current[1], minimum[0], minimum[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
