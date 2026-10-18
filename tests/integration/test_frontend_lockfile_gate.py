"""
title: Integration — every frontend app tracks a lockfile that matches its manifest
kind: tests
layer: n/a
summary: A frontend app CI installs with no committed lockfile resolves a different tree from the one its author tested (keel's react-vite app did, and CI was red for days). So every package.json git tracks that the Makefile's `FE_APPS` glob names (the apps `make fe-install` installs, read off the Makefile, so a project whose config declares no `layers.frontend` block is judged too) has a package-lock.json beside it that git tracks too, read through `git ls-files`, never the filesystem; its `lockfileVersion` is 2 or more, so it carries a `packages` map; and the root entry `packages[""]` records the same dependencies, devDependencies, optionalDependencies and peerDependencies as the manifest, a missing section counting as empty. The app config/project.json `layers.frontend.stack` names under `layers.frontend.root`, when the block exists and names one, must be among the tracked apps. With no app tracked and no stack it skips, saying so, and in a tree that is in no git repository it skips, because nothing is tracked to judge; any other git failure fails. The same check function, run on a scratch repository, names a fault for an untracked lockfile, an absent one, and a devDependency the manifest gained that the lockfile root lacks, and none for a matching app.
"""

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

import hermetic_git

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
import git_tree  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration

_MANIFEST = "package.json"
_LOCKFILE = "package-lock.json"
# The manifest sections npm records on the lockfile's root package entry.
_SECTIONS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
# lockfileVersion 1 has no `packages` map, so it has no root entry to compare.
_MIN_LOCKFILE_VERSION = 2
# The Makefile line that names the apps fe-install installs: a make wildcard of
# each app's manifest, whose `*` matches inside one path segment, as git's
# `:(glob)` pathspec magic does.
_FE_APPS = re.compile(
    r"^FE_APPS\s*:?=\s*\$\(dir \$\(wildcard ([^)\s]+)\)\)\s*$", re.MULTILINE
)


class NoRepository(Exception):
    """The tree is in no git repository, so nothing in it is tracked."""


def _tracked(root, app_glob, env):
    """The tracked paths, relative to *root*, of every manifest *app_glob* names
    and of the lockfile beside each."""
    if not git_tree.inside_a_repository(str(root), env=env):
        raise NoRepository(str(root))
    lock_glob = str(PurePosixPath(app_glob).with_name(_LOCKFILE))
    specs = [":(glob)" + app_glob, ":(glob)" + lock_glob]
    out = subprocess.run(
        ["git", "ls-files", "-z", "--"] + specs,
        cwd=str(root),
        env=env,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return {PurePosixPath(p) for p in out.split("\0") if p}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _app_faults(root, app, tracked):
    """The faults of one app directory (*app* relative to *root*)."""
    lock = app / _LOCKFILE
    if lock not in tracked:
        if (Path(root) / lock).exists():
            return ["%s exists but git does not track it; commit it" % lock]
        return [
            "%s has no %s; run `npm install` there and commit it" % (app, lock.name)
        ]
    try:
        manifest = _read_json(Path(root) / app / _MANIFEST)
        locked = _read_json(Path(root) / lock)
    except (OSError, ValueError) as exc:
        return ["%s: cannot read the manifest or the lockfile (%s)" % (app, exc)]
    level = locked.get("lockfileVersion")
    if not isinstance(level, int) or level < _MIN_LOCKFILE_VERSION:
        return [
            "%s has lockfileVersion %r, which records no root package; regenerate "
            "it with npm 7 or later" % (lock, level)
        ]
    entry = (locked.get("packages") or {}).get("")
    if not isinstance(entry, dict):
        return ['%s has no root entry packages[""]' % lock]
    faults = []
    for section in _SECTIONS:
        want, have = manifest.get(section) or {}, entry.get(section) or {}
        if want != have:
            faults.append(
                "%s %s differs from its %s root entry (only in the manifest: %s; "
                "only or different in the lockfile: %s); run `npm install` there "
                "and commit the lockfile"
                % (
                    app / _MANIFEST,
                    section,
                    lock.name,
                    sorted(k for k in want if want[k] != have.get(k)),
                    sorted(k for k in have if have[k] != want.get(k)),
                )
            )
    return faults


def lockfile_faults(root, app_glob, declared, env=None):
    """(apps judged, one line per fault) for the frontend apps git tracks that
    *app_glob* names; *declared* is the app directory the config declares, or
    None.

    Raises NoRepository when *root* is in no git repository, and
    CalledProcessError when git fails for any other reason."""
    env = build_child_env() if env is None else env
    tracked = _tracked(root, app_glob, env)
    apps = sorted(p.parent for p in tracked if p.name == _MANIFEST)
    faults = []
    if declared is not None and PurePosixPath(declared) not in apps:
        faults.append(
            "layers.frontend.stack declares %s but git tracks no %s there"
            % (declared, _MANIFEST)
        )
    for app in apps:
        faults.extend(_app_faults(root, app, tracked))
    return apps, faults


def _app_glob(root=_ROOT):
    """The manifest glob of the Makefile's FE_APPS line."""
    found = _FE_APPS.search((Path(root) / "Makefile").read_text(encoding="utf-8"))
    assert found, "the Makefile no longer names FE_APPS by a package.json glob"
    return found.group(1)


def _declared_app(root=_ROOT):
    """The app directory config/project.json `layers.frontend` declares, or None:
    a project generated with no frontend carries no `layers.frontend` block."""
    frontend = config_loader.read(str(root))["layers"].get("frontend") or {}
    if frontend.get("stack") is None:
        return None
    return PurePosixPath(frontend["root"]) / frontend["stack"]


def test_every_frontend_app_tracks_a_lockfile_that_matches_its_manifest():
    app_glob, declared = _app_glob(), _declared_app()
    try:
        apps, faults = lockfile_faults(_ROOT, app_glob, declared)
    except NoRepository:
        pytest.skip(
            "%s is in no git repository, so no lockfile is tracked to judge; the "
            "gate judges a committed tree" % _ROOT
        )
    assert faults == [], "\n".join(faults)
    if not apps:
        assert declared is None
        pytest.skip(
            "git tracks no %s the Makefile's FE_APPS glob names, and config "
            "declares no layers.frontend.stack: this project has no frontend app"
            % app_glob
        )


# The fixture's FE_APPS glob, in the Makefile's shape.
_GLOB = "web/*/" + _MANIFEST


def _scratch_repo(tmp_path, name, lock_root, track_lock=True, write_lock=True):
    repo = tmp_path / name
    app = repo / "web" / "app"
    app.mkdir(parents=True)
    (app / _MANIFEST).write_text(
        json.dumps({"name": "app", "dependencies": {"left-pad": "^1.3.0"}})
    )
    if write_lock:
        (app / _LOCKFILE).write_text(
            json.dumps({"lockfileVersion": 3, "packages": {"": lock_root}})
        )
    home = tmp_path / (name + "-git")
    home.mkdir()
    env = hermetic_git.git_env(home)
    git = ["git", "-C", str(repo)]
    subprocess.run(git + ["init", "-q"], env=env, check=True)
    subprocess.run(git + ["add", "web/app/" + _MANIFEST], env=env, check=True)
    if write_lock and track_lock:
        subprocess.run(git + ["add", "web/app/" + _LOCKFILE], env=env, check=True)
    subprocess.run(git + ["commit", "-qm", "app"], env=env, check=True)
    return repo, env


def test_the_lockfile_check_fails_an_untracked_missing_or_drifted_lockfile(tmp_path):
    matching = {"name": "app", "dependencies": {"left-pad": "^1.3.0"}}
    repo, env = _scratch_repo(tmp_path, "ok", matching)
    assert lockfile_faults(repo, _GLOB, None, env) == ([PurePosixPath("web/app")], [])
    assert lockfile_faults(repo, _GLOB, "web/app", env)[1] == []
    # The declared stack is held too: one git does not track is a fault.
    assert lockfile_faults(repo, _GLOB, "web/other", env)[1]

    repo, env = _scratch_repo(tmp_path, "untracked", matching, track_lock=False)
    (fault,) = lockfile_faults(repo, _GLOB, None, env)[1]
    assert "does not track" in fault

    repo, env = _scratch_repo(tmp_path, "absent", matching, write_lock=False)
    (fault,) = lockfile_faults(repo, _GLOB, None, env)[1]
    assert "has no" in fault

    repo, env = _scratch_repo(tmp_path, "drifted", matching)
    manifest = repo / "web" / "app" / _MANIFEST
    grown = dict(_read_json(manifest), devDependencies={"vitest": "^3.0.0"})
    manifest.write_text(json.dumps(grown))
    (fault,) = lockfile_faults(repo, _GLOB, None, env)[1]
    assert "devDependencies" in fault and "vitest" in fault

    outside = tmp_path / "no-repo"
    outside.mkdir()
    with pytest.raises(NoRepository):
        lockfile_faults(outside, _GLOB, None, env)
