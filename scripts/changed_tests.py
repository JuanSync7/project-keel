#!/usr/bin/env python3
"""
title: Changed-tests loop — rerun recorded failures with a checkout-local cache
summary: test-changed uses pytest's --lf selection, running all selected tests on a cold cache. Refuses a disabled cacheprovider before collection and validates tests.cache_dir through the same function check_H uses. --help describes the loop; other arguments pass to pytest. Never gate evidence.
effect: writes
rerun: unsafe
"""

import os
import sys

import changed_cache
import config_loader
import git_tree
from exit_codes import ExitCode, finish, passthrough, report

__all__ = ["main"]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _loop_plugin(pytest):
    class FailureLoop:
        @pytest.hookimpl(tryfirst=True)
        def pytest_cmdline_main(self, config):
            # Check after pytest parses every source of options, before its
            # normal cmdline hook configures plugins or collects any tests.
            if not config.pluginmanager.hasplugin("cacheprovider"):
                return report(
                    ExitCode.USAGE,
                    "test-changed: cacheprovider plugin is disabled",
                    "pytest addopts or PYTEST_ADDOPTS",
                    "remove -p no:cacheprovider and rerun make test-changed; never the gate",
                )
            # --lf is registered only when the cache plugin is on. Set its
            # parsed option here so a disabled plugin gets our named refusal,
            # rather than pytest's unrecognised-argument error for --lf.
            config.option.lf = True
            return None

    return FailureLoop()


def main(argv=None, root=None):
    """Run the failure-only loop, passing pytest's result through the exit helper."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        sys.stdout.write(
            "test-changed [pytest arguments]: --lf reruns only recorded failures; "
            "a cold cache runs the selection. tests.cache_dir is checkout-relative "
            "and git-ignored. Remove -p no:cacheprovider from addopts and "
            "PYTEST_ADDOPTS. Never the gate; run make verify for the gate.\n"
        )
        return ExitCode.SUCCESS
    base = _ROOT if root is None else root
    try:
        path = changed_cache.cache_path(base)
    except (
        config_loader.ConfigError,
        ValueError,
        git_tree.NoGitError,
        git_tree.GitFailedError,
    ) as exc:
        return report(
            ExitCode.USAGE
            if isinstance(exc, config_loader.ConfigError)
            and config_loader.is_conflict(exc)
            else ExitCode.CONFIG,
            "test-changed: tests.cache_dir cannot be used",
            config_loader.shown(str(exc), bare=True),
            "set tests.cache_dir to an ignored directory inside the checkout",
        )
    import pytest

    return passthrough(
        int(
            pytest.main(
                args + ["-o", "cache_dir=" + path], plugins=[_loop_plugin(pytest)]
            )
        )
    )


if __name__ == "__main__":
    finish(main())
