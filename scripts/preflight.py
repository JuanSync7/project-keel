#!/usr/bin/env python3
"""
title: Preflight local gate installs
kind: script
layer: n/a
summary: Checks the selected Python environment, recorded scanner, applicable shell tools and each frontend journey's browser without running gates or installing anything; shared guards own their diagnostics, and any refused install exits 2. Successful checks are silent.
effect: read-only
"""

import contextlib
import io
import json
import os
import subprocess
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import check_python_version  # noqa: E402
import config_loader  # noqa: E402
import git_tree  # noqa: E402
import scan_secrets  # noqa: E402
import shell_gate  # noqa: E402
from child_env import ChildEnvError, build_child_env  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
_BROWSER = ("layers", "frontend", "journey", "browser_executable")
# Chromium's default headless journey uses the headless-shell executable, not
# chromium.executablePath()'s full browser. Ask the installed, pinned runner's
# registry so revision, platform and PLAYWRIGHT_BROWSERS_PATH stay its decision.
_BROWSER_PATH = """
const bundle = require.resolve('playwright-core/lib/coreBundle', {paths: [process.cwd()]});
const {registry} = require(bundle).registry;
process.stdout.write(registry.findExecutable('chromium-headless-shell').executablePath());
"""


def _probe_refused(folder, app, stderr):
    """Refuse a failed browser probe with its installed runner version and remedy."""
    metadata = os.path.join(
        folder, "node_modules", "@playwright", "test", "package.json"
    )
    try:
        with open(metadata, encoding="utf-8") as stream:
            version = json.load(stream)["version"]
    except (OSError, ValueError, KeyError, TypeError):
        version = None
    if isinstance(version, str) and version.strip():
        installed = "installed Playwright version %s" % config_loader.shown(
            version, bare=True
        )
    else:
        installed = (
            "installed Playwright version is unreadable at %s"
            % config_loader.shown(metadata, bare=True)
        )
    detail = next((line.strip() for line in stderr.splitlines() if line.strip()), "")
    if detail:
        installed += "; " + config_loader.shown(detail, bare=True)
    return report(
        ExitCode.USAGE,
        "scripts/preflight.py _BROWSER_PATH probe failed (%s)" % installed,
        app,
        "update the probe in scripts/preflight.py or set "
        "layers.frontend.journey.browser_executable to an installed executable, then rerun",
    )


def _browsers(root, apps, loaded):
    """Require each frontend journey's cached browser or configured executable."""
    if not apps:
        return ExitCode.SUCCESS
    override = config_loader.resolve(
        loaded, config_loader.rows(_BROWSER), config_loader.CONFIG_FILE
    )[_BROWSER]
    for app in apps:
        folder = os.path.join(root, app)
        executable = override
        if executable is None:
            try:
                proc = subprocess.run(
                    ["node", "-e", _BROWSER_PATH],
                    cwd=folder,
                    env=build_child_env(root=root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    # A local registry lookup should be quick; a hung Node must not stall verify.
                    timeout=10,
                )
            except subprocess.TimeoutExpired as exc:
                return report(
                    ExitCode.USAGE,
                    "node did not answer within the limit (%s)"
                    % config_loader.shown(str(exc), bare=True),
                    app,
                    "check the node on PATH, then rerun make preflight",
                )
            except OSError as exc:
                if not (isinstance(exc, FileNotFoundError) and exc.filename == "node"):
                    return report(
                        ExitCode.USAGE,
                        "node could not be started (%s)"
                        % config_loader.shown(str(exc), bare=True),
                        app,
                        "check the node on PATH, then rerun make preflight",
                    )
                return report(
                    ExitCode.USAGE,
                    "node cannot locate the journey browser (%s)"
                    % config_loader.shown(str(exc), bare=True),
                    app,
                    "install Node.js and run `make fe-install` and `make fe-browsers`, then rerun",
                )
            if proc.returncode or not proc.stdout.strip():
                return _probe_refused(folder, app, proc.stderr)
            executable = proc.stdout.strip()
        path = os.path.join(folder, executable)
        if not executable or not os.path.isfile(path) or not os.access(path, os.X_OK):
            return report(
                ExitCode.USAGE,
                "the journey browser is not installed at %s"
                % config_loader.shown(path, bare=True),
                app,
                "run `make fe-browsers`; if layers.frontend.journey.browser_executable "
                "is set, install that executable or set it to null to use the cache",
            )
    return ExitCode.SUCCESS


def _refused(root):
    """Report that preflight refused a required local install."""
    return report(
        ExitCode.USAGE,
        "a required local install is unavailable",
        root,
        "follow the advice above, then rerun make preflight",
    )


def main(argv=None, root=None):
    """Check local verify requirements, returning success silently or refusing with advice."""
    args = sys.argv[1:] if argv is None else argv
    if args == ["--help"]:
        sys.stdout.write(
            "Check local verify installs without running gates; arguments are frontend app directories.\n"
        )
        return ExitCode.SUCCESS
    root = ROOT if root is None else root
    try:
        loaded = config_loader.read(root)
        # Imports needing the project floor happen only after the 3.6-safe guard.
        with contextlib.redirect_stdout(io.StringIO()):
            if check_python_version.main() != ExitCode.SUCCESS:
                return _refused(root)
            import check_venv

            if check_venv.main(root=root, loaded=loaded) != ExitCode.SUCCESS:
                return _refused(root)
        status = scan_secrets.check_install(root, scan_secrets.settings(root))
        if status != ExitCode.SUCCESS:
            return _refused(root)
        status = shell_gate.check_install(
            root, shell_gate.settings(root, loaded=loaded)
        )
        if status != ExitCode.SUCCESS:
            return _refused(root)
        if _browsers(root, args, loaded) != ExitCode.SUCCESS:
            return _refused(root)
        return ExitCode.SUCCESS
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.USAGE if config_loader.is_conflict(exc) else ExitCode.CONFIG,
            "preflight: the project settings are refused",
            "; ".join(exc.lines),
            "fix config/project.json, then rerun make preflight",
        )
    except (
        ChildEnvError,
        git_tree.PathEscape,
        git_tree.NoGitError,
        git_tree.GitFailedError,
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        return report(
            ExitCode.USAGE,
            "a local install could not be checked (%s)"
            % config_loader.shown(str(exc), bare=True),
            root,
            "fix the named input, then rerun make preflight",
        )


if __name__ == "__main__":
    finish(main())
