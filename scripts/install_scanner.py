#!/usr/bin/env python3
"""
title: install_scanner — fetch the pinned secret scanner release, check its sha256, install it per user and record it
kind: script
layer: n/a
summary: `make secrets-install`'s doer, which needs no Go toolchain and no build: it picks this platform's archive from config/project.json `secrets.scanner.release_assets` (the key is the lowercased `<system>-<machine>`, such as `linux-x86_64`), fetches the file name joined to `secrets.scanner.release_url` (https, or file:// for a directory the host already holds), and installs the archive's one regular member named `secrets.scanner.name` as `<install_root>/<name>/<rev>/<name>` under `secrets.scanner.install_root`, outside the checkout, only when the archive's sha256 is the pinned one. It then records that program through scripts/scan_secrets.py `write_record`, the record every scan runs. A source note beside the program holds the archive's file name and sha256 and the program's own sha256, so a second run with the same pins finds the program unchanged, fetches nothing and rewrites nothing; an installed program that changed is fetched and installed again. An unlisted platform, an install root inside the checkout, a record file git would track and a refused setting are CONFIG before anything is fetched; a URL that cannot be read is BACKEND_ABSENT naming `secrets.scanner.release_url`; a sha256 that differs, a reply over `secrets.scanner.download_max_bytes` or an archive without exactly one regular member of that name is FAILURE, and each leaves nothing installed and no record. Stdlib-only.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/unit/scripts/test_install_scanner.py
"""

import argparse
import hashlib
import http.client
import json
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402
import scan_secrets  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
_BLOCK = ("secrets", "scanner")
_FIELDS = (
    "download_max_bytes",
    "download_timeout_seconds",
    "install_root",
    "release_assets",
    "release_url",
)
_WHERE = "config/project.json secrets.scanner"
_CHUNK = 1 << 16
_NOTE_SUFFIX = ".source.json"


class _Refused(Exception):
    """The fetched archive is not the pinned one; nothing is installed."""

    def __init__(self, what, on, next_step):
        super().__init__(what)
        self.what, self.on, self.next_step = what, on, next_step


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="scripts/install_scanner.py",
        description="Fetch the secret scanner release config/project.json "
        "secrets.scanner pins for this platform, check its sha256, install it "
        "under secrets.scanner.install_root and record it for every scan.",
    )
    return parser.parse_args(argv)


def _settings(root):
    keys = config_loader.rows(*[_BLOCK + (field,) for field in _FIELDS])
    values = config_loader.resolve(
        config_loader.read(root), keys, config_loader.CONFIG_FILE
    )
    return {field: values[_BLOCK + (field,)] for field in _FIELDS}


def _platform_key():
    """This host's key in secrets.scanner.release_assets: `linux-x86_64`."""
    return "%s-%s" % (platform.system().lower(), platform.machine().lower())


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([path, root]) == root


def _note(asset, program_sha):
    note = {"file": asset["file"], "sha256": asset["sha256"], "program": program_sha}
    return (json.dumps(note, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _installed(program, asset):
    """True when *program* is the member of the pinned archive, unchanged."""
    try:
        with open(program + _NOTE_SUFFIX, encoding="utf-8") as fh:
            note = json.load(fh)
    except (FileNotFoundError, ValueError):
        # No note, or one that does not parse, proves nothing about the
        # program, which the fetch then replaces with the pinned one.
        return False
    if not isinstance(note, dict) or not os.path.isfile(program):
        return False
    return (
        note.get("file") == asset["file"]
        and note.get("sha256") == asset["sha256"]
        and note.get("program") == scan_secrets.sha256(program)
    )


def _fetch(url, dest, inst):
    """Copy *url* to *dest*, returning its sha256; raises _Refused past the cap."""
    cap = inst["download_max_bytes"]
    digest = hashlib.sha256()
    total = 0
    with (
        urllib.request.urlopen(  # noqa: S310 — the scheme is held to https or file
            url, timeout=inst["download_timeout_seconds"]
        ) as reply,
        open(dest, "wb") as fh,
    ):
        for chunk in iter(lambda: reply.read(_CHUNK), b""):
            total += len(chunk)
            if total > cap:
                raise _Refused(
                    "the reply passed %d bytes" % cap,
                    "%s.download_max_bytes" % _WHERE,
                    "raise it only if the release itself is that large",
                )
            digest.update(chunk)
            fh.write(chunk)
    return digest.hexdigest()


def _extract(archive, name, dest):
    """Write the archive's one regular member named *name* to *dest*."""
    with tarfile.open(archive, "r:gz") as tar:
        hits = [m for m in tar.getmembers() if m.name in (name, "./" + name)]
        if len(hits) != 1 or not hits[0].isfile():
            raise _Refused(
                "the archive holds %d members named %s, and needs one regular file"
                % (len(hits), name),
                archive,
                "pin the release archive that ships the program at its top level",
            )
        source = tar.extractfile(hits[0])
        if source is None:
            raise _Refused(
                "the archive member %s cannot be read" % name,
                archive,
                "pin an archive whose member is a regular file",
            )
        with source, open(dest, "wb") as fh:
            shutil.copyfileobj(source, fh)


def _place(scratch_program, program):
    """Move the checked program into place: a whole file or none."""
    folder = os.path.dirname(program)
    os.makedirs(folder, exist_ok=True)
    handle, partial = tempfile.mkstemp(dir=folder, prefix=".partial-")
    try:
        with os.fdopen(handle, "wb") as fh, open(scratch_program, "rb") as src:
            shutil.copyfileobj(src, fh)
        os.chmod(partial, 0o755)
        os.replace(partial, program)
    except BaseException:
        os.unlink(partial)
        raise


def _install(url, asset, inst, name, program):
    """Fetch, check and place the program; raises _Refused or OSError."""
    scratch = tempfile.mkdtemp(prefix="install_scanner-")
    try:
        archive = os.path.join(scratch, asset["file"])
        got = _fetch(url, archive, inst)
        if got != asset["sha256"]:
            raise _Refused(
                "the archive's sha256 is %s, and config pins %s"
                % (got, asset["sha256"]),
                "%s.release_assets, fetched from %s" % (_WHERE, url),
                "check the sha256 against the vendor's checksums file for that "
                "release; never install an archive whose digest differs",
            )
        extracted = os.path.join(scratch, name)
        try:
            _extract(archive, name, extracted)
        except tarfile.TarError as exc:
            raise _Refused(
                "the archive cannot be read as a .tar.gz (%s)" % exc,
                url,
                "pin the release's .tar.gz archive",
            ) from exc
        _place(extracted, program)
        # The note is written last, so a run cut short leaves a program with
        # no matching note, which the next run installs again.
        scan_secrets.write_if_changed(
            program + _NOTE_SUFFIX, _note(asset, scan_secrets.sha256(program))
        )
    finally:
        shutil.rmtree(scratch)


def _run(root, cfg, inst):
    name, rev = cfg["name"], cfg["rev"]
    key = _platform_key()
    assets = inst["release_assets"]
    asset = assets.get(key)
    if asset is None:
        return report(
            ExitCode.CONFIG,
            "no %s release archive is pinned for this platform, %s" % (name, key),
            "%s.release_assets, which lists %s" % (_WHERE, ", ".join(sorted(assets))),
            "add a `%s` entry with the release's archive file name and its sha256 "
            "from the vendor's checksums file, or run on a listed platform" % key,
        )
    install_root = os.path.expanduser(inst["install_root"])
    if _inside(install_root, root):
        return report(
            ExitCode.CONFIG,
            "the install root %s is inside the checkout, where git would list "
            "the program" % install_root,
            "%s.install_root" % _WHERE,
            "point it at a per-user directory outside the checkout",
        )
    if not scan_secrets.record_is_ignored(root, cfg):
        return report(
            ExitCode.CONFIG,
            "git would commit the scanner record %s, which names one machine's "
            "path" % cfg["record_file"],
            "%s.record_file" % _WHERE,
            "ignore that path in .gitignore, then rerun",
        )
    program = os.path.join(install_root, name, rev, name)
    url = inst["release_url"].rstrip("/") + "/" + asset["file"]
    fetched = not _installed(program, asset)
    if fetched:
        try:
            _install(url, asset, inst, name, program)
        except _Refused as exc:
            return report(ExitCode.FAILURE, exc.what, exc.on, exc.next_step)
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            return report(
                ExitCode.BACKEND_ABSENT,
                "the release archive cannot be fetched (%s)" % exc,
                url,
                "check the network, or point %s.release_url at a reachable "
                "mirror that holds the same file" % _WHERE,
            )
    recorded = scan_secrets.write_record(root, cfg, program)
    sys.stdout.write(
        "install_scanner: %s %s %s at %s; record %s %s\n"
        % (
            name,
            rev,
            "installed" if fetched else "already installed",
            program,
            "written to" if recorded else "unchanged in",
            cfg["record_file"],
        )
    )
    return ExitCode.SUCCESS


def main(argv=None, root=None):
    try:
        _parse(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        # argparse ends the process itself: status 0 after --help, and a usage
        # error it has already written to stderr otherwise.
        if not exc.code:
            return ExitCode.SUCCESS
        return report(
            ExitCode.USAGE,
            "argparse refused the arguments above",
            "the command line",
            "call it with no arguments; config/project.json secrets.scanner "
            "says what to install",
        )
    root = os.path.abspath(ROOT if root is None else root)
    try:
        cfg = scan_secrets.settings(root)
        inst = _settings(root)
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the secret scanner settings are refused",
            "; ".join(exc.lines),
            "fix the secrets.scanner block of config/project.json, then rerun",
        )
    return _run(root, cfg, inst)


if __name__ == "__main__":
    finish(main())
