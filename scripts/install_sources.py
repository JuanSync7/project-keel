#!/usr/bin/env python3
"""
title: install_sources — the configured mirror for one install source
kind: script
layer: n/a
summary: Prints the URL config/project.json `install_sources` sets for one source, so the command that installs from it can be pointed at a company mirror: `python_index` (pip's --index-url, for CI's install and the command `make check-venv` names), `npm_registry` (npm's --registry, for `make fe-install`) and `browser_download_host` (PLAYWRIGHT_DOWNLOAD_HOST, for `make fe-browsers`). A configured URL is printed alone on one line; null prints nothing, so the caller passes no flag and the tool's own configuration (pip.conf, .npmrc, the browser runner's default host) holds. The scanner's mirror is `secrets.scanner.release_url`, which scripts/install_scanner.py reads itself. A value the loader refuses (not https, no host, a user part, a query, a fragment or whitespace) is CONFIG naming the key, a user part never printed; a source outside `SOURCES` is USAGE. It reads config and writes nothing. Stdlib-only and 3.6-safe, because the Makefile may run it under an interpreter older than requires-python.
"""

import argparse
import os
import sys
from typing import Any, List, Mapping, Optional

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

__all__ = ["SOURCES", "main"]

ROOT = os.path.dirname(_SCRIPTS)
_BLOCK = "install_sources"
# The closed list, one entry per scripts/config_loader.py `install_sources` row
# (tests/unit/scripts/test_install_sources.py holds the two equal).
SOURCES = ("browser_download_host", "npm_registry", "python_index")


def _parse(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts/install_sources.py",
        description="Print the mirror config/project.json install_sources sets "
        "for one source, or nothing when it is null.",
    )
    parser.add_argument(
        "source",
        choices=SOURCES,
        help="the install source whose configured URL to print",
    )
    return parser.parse_args(argv)


def main(
    argv: Optional[List[str]] = None, loaded: Optional[Mapping[str, Any]] = None
) -> ExitCode:
    """Print the configured URL for one source; CONFIG when it is refused."""
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
            "call it as `install_sources.py <%s>`" % "|".join(SOURCES),
        )
    path = (_BLOCK, args.source)
    try:
        if loaded is None:
            loaded = config_loader.read(ROOT)
        values = config_loader.resolve(
            loaded, config_loader.rows(path), config_loader.CONFIG_FILE
        )
    except config_loader.ConfigError as exc:
        # The loader's lines never carry a user part, so they are safe to join.
        return report(
            ExitCode.CONFIG,
            "the install source %s.%s is refused" % path,
            "; ".join(exc.lines),
            "set it to an https mirror URL with no user part, query or "
            "fragment, or to null for the tool's own setting, then rerun",
        )
    url = values[path]
    if url is not None:
        sys.stdout.write(url + "\n")
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
