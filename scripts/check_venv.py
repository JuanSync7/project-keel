#!/usr/bin/env python3
"""
title: check_venv — the venv holds what pyproject.toml declares, before a gate runs
kind: script
layer: n/a
summary: Judges the interpreter's installed distributions against pyproject.toml: every requirement of the core dependencies, of config/project.json `venv.extras` and of the extra each enabled transport names in `transports.extras`, following an extra that names the project itself and judging the requirements an extra asks of another distribution, is installed at a version its specifier allows; a requirement whose marker excludes this interpreter is not judged. An absent distribution, a version outside the specifier or an unparsable version is FAILURE naming each package, the interpreter and the exact `pip install -e ".[<extras>]"` command; an extra pyproject.toml does not declare, or a config value the loader refuses, is CONFIG; a pyproject.toml it cannot read is USAGE; nothing to judge is NOTHING_JUDGED. It reads installed metadata with importlib.metadata and never the network, and writes nothing.
effect: read-only
"""

import os
import sys
from importlib import metadata
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
_PYPROJECT = "pyproject.toml"
_GATE_EXTRAS = ("venv", "extras")
_ENABLED = ("transports", "enabled")
_TRANSPORT_EXTRAS = ("transports", "extras")

VersionOf = Callable[[str], Optional[str]]
RequiresOf = Callable[[str], List[str]]


class ProjectUnreadable(Exception):
    """pyproject.toml cannot be read as a project with a name."""


def _installed_version(name: str) -> Optional[str]:
    """The installed version of distribution *name*, or None when absent."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _installed_requires(name: str) -> List[str]:
    """The requirement strings distribution *name* declares in its metadata."""
    try:
        return list(metadata.requires(name) or [])
    except metadata.PackageNotFoundError:
        return []


def _toml() -> Any:
    # tomllib is stdlib from 3.11; requires-python admits 3.10, where pytest's
    # own dependency on tomli is what the `dev` extra brings.
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    return tomllib


def read_project(root: str) -> Dict[str, Any]:
    """pyproject.toml's `[project]` table under *root*, with `dependencies` and
    `optional-dependencies` always present; ProjectUnreadable otherwise."""
    path = os.path.join(root, _PYPROJECT)
    tomllib = _toml()
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProjectUnreadable("%s cannot be read (%s)" % (_PYPROJECT, exc)) from exc
    project = data.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("name"), str):
        raise ProjectUnreadable("%s has no [project] table with a name" % _PYPROJECT)
    out = dict(project)
    out["dependencies"] = list(project.get("dependencies") or [])
    out["optional-dependencies"] = dict(project.get("optional-dependencies") or {})
    return out


def wanted_extras(loaded: Mapping[str, Any]) -> List[str]:
    """The extras the gate needs: config `venv.extras`, then the extra each
    enabled transport names, in that order and each once. Raises the loader's
    ConfigError for a value it refuses."""
    values = config_loader.resolve(
        loaded,
        config_loader.rows(_GATE_EXTRAS, _ENABLED, _TRANSPORT_EXTRAS),
        config_loader.CONFIG_FILE,
    )
    out: List[str] = []
    by_transport = values[_TRANSPORT_EXTRAS]
    named = list(values[_GATE_EXTRAS]) + [
        by_transport[t] for t in values[_ENABLED] if t in by_transport
    ]
    for extra in named:
        if extra not in out:
            out.append(extra)
    return out


def _canonical(name: str) -> str:
    from packaging.utils import canonicalize_name

    return str(canonicalize_name(name))


def _applies(req: Any, extra: str) -> bool:
    # A requirement listed under an extra carries no `extra ==` marker of its
    # own; evaluating with extra="" keeps a marker such as python_version honest.
    return req.marker is None or bool(req.marker.evaluate({"extra": extra}))


def _expand(
    project: Mapping[str, Any], extras: Sequence[str]
) -> Tuple[List[Tuple[Any, str]], Set[str]]:
    """([(requirement, where it was declared)], every extra reached) for the
    core dependencies and *extras*, following an extra that names the project."""
    from packaging.requirements import Requirement

    me = _canonical(project["name"])
    declared = project["optional-dependencies"]
    reached: Set[str] = set()
    todo = list(extras)
    found: List[Tuple[Any, str]] = [
        (Requirement(s), "dependencies") for s in project["dependencies"]
    ]
    while todo:
        extra = todo.pop(0)
        if extra in reached:
            continue
        reached.add(extra)
        for spec in declared[extra]:
            req = Requirement(spec)
            if _canonical(req.name) == me:
                todo.extend(sorted(req.extras))
            else:
                found.append((req, "extra %s" % extra))
    return found, reached


def reachable(project: Mapping[str, Any], extras: Sequence[str]) -> Set[str]:
    """Every extra *extras* reach, through extras that name the project itself."""
    return _expand(project, extras)[1]


def install_extras(project: Mapping[str, Any], extras: Sequence[str]) -> List[str]:
    """The fewest of *extras*, in order, whose install reaches all of them: an
    extra another one already reaches is left out of the pip command."""
    out = []
    for extra in extras:
        others = [e for e in extras if e != extra]
        if extra not in reachable(project, others):
            out.append(extra)
    return out


def _judge(req: Any, have: Optional[str], label: str) -> Optional[str]:
    """Why *req* is unmet by installed version *have*, or None when it is met."""
    from packaging.version import InvalidVersion, Version

    if have is None:
        return "%s is not installed (%s wants %s)" % (req.name, label, req)
    if not str(req.specifier):
        return None
    try:
        ok = req.specifier.contains(Version(have), prereleases=True)
    except InvalidVersion:
        return "%s %s is installed, which is not a version %s can compare (%s)" % (
            req.name,
            have,
            req.specifier,
            label,
        )
    if ok:
        return None
    return "%s %s is installed and %s wants %s" % (req.name, have, label, req.specifier)


def unmet(
    project: Mapping[str, Any],
    extras: Sequence[str],
    version_of: VersionOf,
    requires_of: RequiresOf,
) -> Tuple[int, List[str]]:
    """(requirements judged, a sentence for each unmet one) for the core
    dependencies and *extras*. An extra a requirement asks of another
    distribution, `uvicorn[standard]`, judges the requirements that extra adds."""
    from packaging.requirements import Requirement

    found, _reached = _expand(project, extras)
    judged, problems = 0, []
    for req, label in found:
        if not _applies(req, ""):
            continue
        judged += 1
        problem = _judge(req, version_of(req.name), label)
        if problem:
            problems.append(problem)
            continue
        for extra in sorted(req.extras):
            for spec in requires_of(req.name):
                sub = Requirement(spec)
                # Only what the extra adds: an unconditional dependency of a
                # dependency is pip's to resolve, not pyproject.toml's claim.
                if not _applies(sub, extra) or _applies(sub, ""):
                    continue
                judged += 1
                where = "%s[%s] in %s" % (req.name, extra, label)
                problem = _judge(sub, version_of(sub.name), where)
                if problem:
                    problems.append(problem)
    return judged, problems


def main(
    root: Optional[str] = None,
    loaded: Optional[Mapping[str, Any]] = None,
    version_of: Optional[VersionOf] = None,
    requires_of: Optional[RequiresOf] = None,
    executable: Optional[str] = None,
) -> ExitCode:
    root = ROOT if root is None else root
    python = sys.executable if executable is None else executable
    try:
        import packaging.requirements  # noqa: F401
    except ImportError:
        return report(
            ExitCode.FAILURE,
            "check_venv: the `packaging` distribution is not installed, so no "
            "requirement can be judged",
            python,
            'run `%s -m pip install -e ".[dev]"`' % python,
        )
    try:
        if loaded is None:
            loaded = config_loader.read(root)
        extras = wanted_extras(loaded)
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "check_venv: the venv settings are refused",
            "; ".join(exc.lines),
            "fix venv.extras or transports in config/project.json, then rerun",
        )
    try:
        project = read_project(root)
    except ProjectUnreadable as exc:
        return report(
            ExitCode.USAGE,
            "check_venv: %s" % exc,
            os.path.join(root, _PYPROJECT),
            "restore a pyproject.toml whose [project] table has a name",
        )
    undeclared = [e for e in extras if e not in project["optional-dependencies"]]
    if undeclared:
        return report(
            ExitCode.CONFIG,
            "check_venv: config/project.json asks for extra %s, which %s does "
            "not declare" % (", ".join(undeclared), _PYPROJECT),
            "venv.extras and transports.extras",
            "declare the extra under [project.optional-dependencies] or remove "
            "it from config/project.json",
        )
    command = '%s -m pip install -e ".[%s]"' % (
        python,
        ",".join(install_extras(project, extras)),
    )
    judged, problems = unmet(
        project,
        extras,
        _installed_version if version_of is None else version_of,
        _installed_requires if requires_of is None else requires_of,
    )
    where = "%s against %s dependencies and extras %s" % (
        python,
        _PYPROJECT,
        ", ".join(sorted(reachable(project, extras))),
    )
    if judged == 0:
        return report(
            ExitCode.NOTHING_JUDGED,
            "check_venv: %s declares no requirement for this interpreter under "
            "extras %s" % (_PYPROJECT, ", ".join(extras)),
            where,
            "name the extras the gate imports in config/project.json venv.extras",
        )
    if problems:
        return report(
            ExitCode.FAILURE,
            "check_venv: the venv is older than %s: %s"
            % (_PYPROJECT, "; ".join(problems)),
            where,
            "run `%s`" % command,
        )
    sys.stdout.write(
        "check_venv: %s satisfies %d requirements of %s (extras %s)\n"
        % (python, judged, _PYPROJECT, ", ".join(sorted(reachable(project, extras))))
    )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
