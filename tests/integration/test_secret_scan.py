"""
title: Integration — the secret scanner adapter against the real pinned scanner
kind: tests
layer: n/a
summary: scripts/scan_secrets.py run against the scanner `make secrets-install` built and recorded in this checkout's config/project.json `secrets.scanner.record_file`, in a scratch repository that copies this checkout's config. A credential-shaped value, built at run time so no committed file holds one, is red in the staged scan and, once committed, in the history scan, and stays red after a later commit deletes it, because history keeps it; each finding prints its file, line and rule and the value appears on neither stream. A clean repository scans clean and is left as git lists it, so `make secret-scan` stays [local], an exclusion naming the finding's exact file and rule makes the scan pass, and one no finding uses is a config fault. A recorded scanner that is gone is BACKEND_ABSENT. The commit hook's own arguments, read from .pre-commit-config.yaml, run outside a commit with nothing staged (`pre-commit run --all-files`) judge every commit: clean on a clean history and red on a committed credential, never a pass or a refusal over zero files. The one hook that runs scripts/scan_secrets.py is a local system hook and no pre-commit repository builds the scanner, so a commit needs no Go toolchain and runs only the recorded program. With no recorded scanner the scanner cases skip, and fail where KEEL_REQUIRED_EXTRAS declares `secrets`.
"""

import json
import os
import random
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import config_loader  # noqa: E402
import git_tree  # noqa: E402
import scan_secrets  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import hermetic_git  # noqa: E402
import optional_deps  # noqa: E402

pytestmark = pytest.mark.integration

_BLOCK = ("secrets", "scanner")


def _scanner_config():
    keys = ("name", "record_file", "rev")
    values = config_loader.resolve(
        config_loader.read(str(_ROOT)),
        config_loader.rows(*[_BLOCK + (k,) for k in keys]),
        config_loader.CONFIG_FILE,
    )
    return {k: values[_BLOCK + (k,)] for k in keys}


def _planted_value():
    # The access-key shape the default rules know, built here so the value is
    # in no committed file; base32's alphabet is the shape's own.
    rng = random.Random(7)
    return "AKIA" + "".join(
        rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(16)
    )


def _git(repo, env, *argv):
    subprocess.run(
        ["git", *argv], cwd=str(repo), env=env, check=True, capture_output=True
    )


@pytest.fixture
def recorded_scanner():
    """The program this checkout's record names, when it is there to run."""
    cfg = _scanner_config()
    path = None
    record = _ROOT / cfg["record_file"]
    if record.is_file():
        path = json.loads(record.read_text(encoding="utf-8")).get("path")
    optional_deps.require_or_skip(
        bool(path) and os.access(str(path), os.X_OK),
        "secrets",
        "no recorded %s at %s" % (cfg["name"], cfg["record_file"]),
    )
    return Path(path)


@pytest.fixture
def project(tmp_path, monkeypatch, recorded_scanner):
    """A committed scratch project with this checkout's config and the
    recorded scanner recorded again in its own record file."""
    work = tmp_path / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    shutil.copyfile(
        str(_ROOT / "config" / "project.json"), str(root / "config" / "project.json")
    )
    (root / ".gitignore").write_text(".secret-scan\n", encoding="utf-8")
    (root / "readme.txt").write_text("nothing to see\n", encoding="utf-8")
    _git(root, env, "init", "-q")
    _git(root, env, "add", "-A")
    _git(root, env, "commit", "-q", "-m", "init")
    cfg = scan_secrets.settings(str(root))
    assert scan_secrets.record_is_ignored(str(root), cfg)
    scan_secrets.write_record(str(root), cfg, str(recorded_scanner))
    return root, env


def _plant(root):
    (root / "creds.py").write_text(
        'aws_key = "%s"\n' % _planted_value(), encoding="utf-8"
    )


def _set_exclusions(root, exclusions):
    path = root / "config" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["secrets"]["scanner"]["exclusions"] = exclusions
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _quiet(capsys):
    out, err = capsys.readouterr()
    assert _planted_value() not in out + err, "the scan printed the value"
    return out.splitlines()


def test_a_clean_repository_scans_clean(project, capsys):
    root, env = project
    (root / "notes.txt").write_text("nothing shaped like a key\n", encoding="utf-8")
    _git(root, env, "add", "notes.txt")
    capsys.readouterr()
    before = git_tree.tree_snapshot(str(root))
    for mode in ("--staged", "--history"):
        assert scan_secrets.main([mode], root=str(root)) == ExitCode.SUCCESS, mode
    assert git_tree.tree_snapshot(str(root)) == before, "a scan changed the tree"


def test_a_staged_credential_is_red_and_never_printed(project, capsys):
    root, env = project
    _plant(root)
    _git(root, env, "add", "creds.py")
    capsys.readouterr()
    assert scan_secrets.main(["--staged"], root=str(root)) == ExitCode.FAILURE
    assert _quiet(capsys) == ["creds.py:1 aws-access-token"]


def test_a_committed_credential_stays_red_after_it_is_deleted(project, capsys):
    root, env = project
    _plant(root)
    _git(root, env, "add", "creds.py")
    _git(root, env, "commit", "-q", "-m", "leak")
    _git(root, env, "rm", "-q", "creds.py")
    _git(root, env, "commit", "-q", "-m", "delete")
    capsys.readouterr()
    assert scan_secrets.main(["--history"], root=str(root)) == ExitCode.FAILURE
    (line,) = _quiet(capsys)
    assert line.startswith("creds.py:1 aws-access-token "), line


def test_an_exact_exclusion_passes_and_a_neighbouring_rule_does_not(project, capsys):
    root, env = project
    _plant(root)
    _git(root, env, "add", "creds.py")
    _git(root, env, "commit", "-q", "-m", "fixture")
    _set_exclusions(root, {"creds.py": {"aws-access-token": "a planted fixture"}})
    assert scan_secrets.main(["--history"], root=str(root)) == ExitCode.SUCCESS
    _set_exclusions(root, {"creds.py": {"generic-api-key": "names no finding"}})
    capsys.readouterr()
    assert scan_secrets.main(["--history"], root=str(root)) == ExitCode.FAILURE
    _quiet(capsys)


def test_an_exclusion_no_finding_uses_is_a_config_fault(project, capsys):
    root, _env = project
    _set_exclusions(root, {"readme.txt": {"aws-access-token": "stale"}})
    capsys.readouterr()
    assert scan_secrets.main(["--history"], root=str(root)) == ExitCode.CONFIG
    assert "readme.txt aws-access-token" in capsys.readouterr().err


def test_a_recorded_scanner_that_is_gone_is_backend_absent(
    project, tmp_path, recorded_scanner, capsys
):
    root, _env = project
    copy_dir = tmp_path / "copy"
    copy_dir.mkdir()
    copy = copy_dir / recorded_scanner.name
    shutil.copyfile(str(recorded_scanner), str(copy))
    copy.chmod(copy.stat().st_mode | stat.S_IXUSR)
    scan_secrets.write_record(str(root), scan_secrets.settings(str(root)), str(copy))
    copy.unlink()
    capsys.readouterr()
    assert scan_secrets.main(["--history"], root=str(root)) == ExitCode.BACKEND_ABSENT
    assert "make secrets-install" in capsys.readouterr().err


def _scanner_hooks():
    """(repository, hook) for every .pre-commit-config.yaml hook whose entry
    runs scripts/scan_secrets.py."""
    yaml = optional_deps.importorskip("yaml", extra="template")
    loaded = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text())
    return [
        (repo["repo"], hook)
        for repo in loaded["repos"]
        for hook in repo["hooks"]
        if "scripts/scan_secrets.py" in hook.get("entry", "")
    ]


def _commit_hook_args():
    """The arguments the commit-time hook in .pre-commit-config.yaml hands
    scripts/scan_secrets.py, read from the file rather than retyped."""
    ((_repo, hook),) = _scanner_hooks()
    argv = shlex.split(hook["entry"])
    assert argv[:2] == ["python3", "scripts/scan_secrets.py"], argv
    return argv[2:]


def test_the_commit_hook_run_outside_a_commit_judges_the_history(project, capsys):
    """`pre-commit run --all-files` runs the commit hook with nothing staged:
    it passes on a clean history and is red on a committed credential, never
    a pass, or a refusal, over zero files."""
    root, env = project
    args = _commit_hook_args()
    capsys.readouterr()
    assert scan_secrets.main(args, root=str(root)) == ExitCode.SUCCESS
    _plant(root)
    _git(root, env, "add", "creds.py")
    _git(root, env, "commit", "-q", "-m", "leak")
    capsys.readouterr()
    assert scan_secrets.main(args, root=str(root)) == ExitCode.FAILURE
    said, line = _quiet(capsys)
    assert "nothing is staged" in said, said
    assert line.startswith("creds.py:1 aws-access-token "), line


def test_the_commit_hook_runs_the_recorded_scanner_and_builds_nothing():
    """The one hook that names the scanner is a local, system-language hook
    over scripts/scan_secrets.py, so committing needs no Go toolchain and no
    fetch: it runs only what `make secrets-install` recorded."""
    ((repo, hook),) = _scanner_hooks()
    assert repo == "local", repo
    assert hook["language"] == "system", hook
    assert hook["pass_filenames"] is False, hook
    assert hook.get("stages") in (None, ["pre-commit"]), hook


def test_no_pre_commit_repository_builds_the_scanner():
    yaml = optional_deps.importorskip("yaml", extra="template")
    name = _scanner_config()["name"]
    loaded = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text())
    builds = [
        r["repo"]
        for r in loaded["repos"]
        if (r["repo"] != "local" and name in r["repo"])
        or any(h["id"] == name for h in r["hooks"])
    ]
    assert builds == [], builds
