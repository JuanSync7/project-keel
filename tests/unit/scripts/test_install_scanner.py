"""
title: Unit — install_scanner (the pinned scanner release, fetched from a local fixture and checked by sha256)
kind: tests
layer: n/a
summary: scripts/install_scanner.py driven against a release archive built in the test's own directory and named by a file:// `secrets.scanner.release_url`, so no test reaches the network. The archive whose sha256 config names installs its one member named `secrets.scanner.name` under `secrets.scanner.install_root`, executable, and records it through scripts/scan_secrets.py, so a scan then runs that program; a second run fetches nothing (the archive is gone by then) and leaves the program, its source note and the record byte-identical with the same modification times, which is the module's fixed point. An archive whose sha256 differs, one larger than `secrets.scanner.download_max_bytes`, one with no regular member of that name, and a URL that cannot be read each leave nothing installed and no record. A platform `secrets.scanner.release_assets` does not list, an install root inside the checkout and a record file git would track are each CONFIG before anything is fetched. An installed program that changed is fetched and installed again.
"""

import hashlib
import io
import json
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import config_loader  # noqa: E402
import install_scanner  # noqa: E402
import scan_secrets  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit

_BLOCK = ("secrets", "scanner")


def _scanner_config():
    """keel's own secrets.scanner values the assertions read, never typed here."""
    fields = ("name", "record_file", "rev")
    got = config_loader.resolve(
        config_loader.read(str(_ROOT)),
        config_loader.rows(*[_BLOCK + (f,) for f in fields]),
        config_loader.CONFIG_FILE,
    )
    return {path[-1]: value for path, value in got.items()}


_CFG = _scanner_config()
_NAME = _CFG["name"]
_RECORD = _CFG["record_file"]
# A platform no host reports, so the test never depends on the machine it runs
# on; _platform_key is pointed at it.
_PLATFORM = "testos-testarch"
_PROGRAM = b"#!/bin/sh\necho fixture scanner\n"


def _archive(members):
    """The bytes of a .tar.gz holding *members*, (name, bytes) pairs."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _git(repo, env, *argv):
    subprocess.run(
        ["git", *argv], cwd=str(repo), env=env, check=True, capture_output=True
    )


class _Project:
    def __init__(self, root, release_dir, tools):
        self.root = root
        self.release_dir = release_dir
        self.tools = tools

    def publish(self, members=None, file="scanner_testos.tar.gz", sha256=None):
        """Put an archive in the release directory and name it in config."""
        if members is None:
            members = [(_NAME, _PROGRAM), ("LICENSE", b"fixture licence\n")]
        data = _archive(members)
        (self.release_dir / file).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest() if sha256 is None else sha256
        self.scanner(release_assets={_PLATFORM: {"file": file, "sha256": digest}})
        return data

    def scanner(self, **values):
        path = self.root / "config" / "project.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["secrets"]["scanner"].update(values)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def run(self, *argv):
        return install_scanner.main(list(argv), root=str(self.root))

    def program(self):
        return self.tools / _NAME / _CFG["rev"] / _NAME

    def installed(self):
        """Every file under the install root, relative to it."""
        if not self.tools.exists():
            return []
        return sorted(
            str(p.relative_to(self.tools)) for p in self.tools.rglob("*") if p.is_file()
        )


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A committed project with keel's config, its record file ignored, a
    release directory served as a file:// URL and an install root in the
    test's own directory."""
    work = tmp_path / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(install_scanner, "_platform_key", lambda: _PLATFORM)
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    shutil.copyfile(
        str(_ROOT / "config" / "project.json"), str(root / "config" / "project.json")
    )
    (root / ".gitignore").write_text(_RECORD + "\n", encoding="utf-8")
    _git(root, env, "init", "-q")
    _git(root, env, "add", "-A")
    _git(root, env, "commit", "-q", "-m", "init")
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    tools = tmp_path / "tools"
    proj = _Project(root, release_dir, tools)
    proj.scanner(release_url=release_dir.as_uri(), install_root=str(tools))
    return proj


def test_the_pinned_archive_installs_its_program_and_records_it(project, capsys):
    project.publish()
    assert project.run() == ExitCode.SUCCESS
    program = project.program()
    assert program.read_bytes() == _PROGRAM
    assert program.stat().st_mode & stat.S_IXUSR
    record = json.loads((project.root / _RECORD).read_text(encoding="utf-8"))
    assert record == {
        "name": _NAME,
        "path": str(program),
        "rev": _CFG["rev"],
        "sha256": hashlib.sha256(_PROGRAM).hexdigest(),
    }
    assert "installed" in capsys.readouterr().out
    # The record is the one every scan runs: the adapter accepts it.
    cfg = scan_secrets.settings(str(project.root))
    assert scan_secrets._recorded(str(project.root), cfg) == (str(program), None)


def test_a_second_run_fetches_nothing_and_changes_nothing(project, capsys):
    project.publish()
    assert project.run() == ExitCode.SUCCESS
    files = [project.program(), project.root / _RECORD] + [
        project.tools / p for p in project.installed()
    ]
    before = {str(f): (f.read_bytes(), f.stat().st_mtime_ns) for f in files}
    # Gone, so a second fetch would fail: the no-op is proven, not assumed.
    for archive in project.release_dir.iterdir():
        archive.unlink()
    capsys.readouterr()
    assert project.run() == ExitCode.SUCCESS
    after = {str(f): (f.read_bytes(), f.stat().st_mtime_ns) for f in files}
    assert after == before
    assert "already installed" in capsys.readouterr().out


def test_a_lost_record_is_written_again_without_a_fetch(project):
    project.publish()
    assert project.run() == ExitCode.SUCCESS
    first = (project.root / _RECORD).read_bytes()
    (project.root / _RECORD).unlink()
    for archive in project.release_dir.iterdir():
        archive.unlink()
    assert project.run() == ExitCode.SUCCESS
    assert (project.root / _RECORD).read_bytes() == first


def test_a_wrong_sha256_refuses_and_leaves_nothing_installed(project, capsys):
    project.publish(sha256="0" * 64)
    assert project.run() == ExitCode.FAILURE
    assert project.installed() == []
    assert not (project.root / _RECORD).exists()
    err = capsys.readouterr().err
    assert "sha256" in err and "secrets.scanner.release_assets" in err, err


def test_a_changed_installed_program_is_installed_again(project):
    project.publish()
    assert project.run() == ExitCode.SUCCESS
    project.program().write_bytes(b"#!/bin/sh\necho tampered\n")
    assert project.run() == ExitCode.SUCCESS
    assert project.program().read_bytes() == _PROGRAM
    cfg = scan_secrets.settings(str(project.root))
    assert scan_secrets._recorded(str(project.root), cfg)[0] == str(project.program())


def test_an_unknown_platform_refuses_with_a_next_step(project, monkeypatch, capsys):
    project.publish()
    monkeypatch.setattr(install_scanner, "_platform_key", lambda: "plan9-mips")
    assert project.run() == ExitCode.CONFIG
    assert project.installed() == []
    assert not (project.root / _RECORD).exists()
    err = capsys.readouterr().err
    assert "plan9-mips" in err and _PLATFORM in err, err
    assert "checksums" in err, "the next step says where the sha256 comes from"


def test_an_unreadable_url_is_backend_absent_and_installs_nothing(project, capsys):
    project.publish()
    project.scanner(release_url=(project.release_dir / "missing").as_uri())
    assert project.run() == ExitCode.BACKEND_ABSENT
    assert project.installed() == []
    assert "secrets.scanner.release_url" in capsys.readouterr().err


def test_an_archive_larger_than_the_cap_installs_nothing(project, capsys):
    data = project.publish()
    project.scanner(download_max_bytes=len(data) - 1)
    assert project.run() == ExitCode.FAILURE
    assert project.installed() == []
    assert "secrets.scanner.download_max_bytes" in capsys.readouterr().err


@pytest.mark.parametrize(
    "members",
    [
        [("LICENSE", b"no program\n")],
        [("bin/" + _NAME, _PROGRAM)],
        [(_NAME, _PROGRAM), ("./" + _NAME, _PROGRAM)],
    ],
    ids=["absent", "nested", "twice"],
)
def test_an_archive_without_one_program_installs_nothing(project, capsys, members):
    project.publish(members=members)
    assert project.run() == ExitCode.FAILURE
    assert project.installed() == []
    assert not (project.root / _RECORD).exists()
    assert _NAME in capsys.readouterr().err


def test_a_link_named_like_the_program_installs_nothing(project):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(_NAME)
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)
    data = buf.getvalue()
    (project.release_dir / "link.tar.gz").write_bytes(data)
    project.scanner(
        release_assets={
            _PLATFORM: {
                "file": "link.tar.gz",
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        }
    )
    assert project.run() == ExitCode.FAILURE
    assert project.installed() == []


def test_an_install_root_inside_the_checkout_is_config(project, capsys):
    project.publish()
    project.scanner(install_root=str(project.root / "tools"))
    assert project.run() == ExitCode.CONFIG
    assert not (project.root / "tools").exists()
    assert "secrets.scanner.install_root" in capsys.readouterr().err


def test_a_record_file_git_would_track_is_config_before_any_fetch(project, capsys):
    project.publish()
    (project.root / ".gitignore").write_text("", encoding="utf-8")
    assert project.run() == ExitCode.CONFIG
    assert project.installed() == []
    assert "secrets.scanner.record_file" in capsys.readouterr().err


@pytest.mark.parametrize(
    "values",
    [
        {"release_url": "ftp://mirror.invalid/gitleaks"},
        {"release_url": "https://user:pw@mirror.invalid/gitleaks"},
        {"install_root": "relative/tools"},
        {"release_assets": {}},
        {"release_assets": {_PLATFORM: {"file": "a.tar.gz", "sha256": "abc"}}},
        {"release_assets": {_PLATFORM: {"file": "../a.tar.gz", "sha256": "0" * 64}}},
        {"release_assets": {_PLATFORM: {"file": "a.zip", "sha256": "0" * 64}}},
        {"download_max_bytes": 0},
        {"download_timeout_seconds": 0},
    ],
    ids=[
        "scheme",
        "userinfo",
        "relative-root",
        "no-asset",
        "short-sha",
        "path-in-file",
        "not-a-tarball",
        "zero-cap",
        "zero-timeout",
    ],
)
def test_a_refused_install_setting_is_config_before_any_fetch(project, capsys, values):
    project.publish()
    project.scanner(**values)
    assert project.run() == ExitCode.CONFIG
    assert project.installed() == []
    assert "secrets.scanner." + next(iter(values)) in capsys.readouterr().err


def test_an_argument_is_usage(project):
    assert project.run("--nonsense") == ExitCode.USAGE


def test_the_platform_key_is_the_lowercased_system_and_machine(monkeypatch):
    monkeypatch.setattr(install_scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install_scanner.platform, "machine", lambda: "X86_64")
    assert install_scanner._platform_key() == "linux-x86_64"
