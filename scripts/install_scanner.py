#!/usr/bin/env python3
"""
title: install_scanner — fetch the pinned secret scanner release, check its sha256, install it per user and record it
kind: script
layer: n/a
summary: `make secrets-install`'s doer, which needs no Go toolchain and no build: it picks this platform's archive from config/project.json `secrets.scanner.release_assets` (the key is the lowercased `<system>-<machine>`, such as `linux-x86_64`), fetches the file name joined to `secrets.scanner.release_url` (https, or file:// for a directory the host already holds), and installs the archive's one regular member named `secrets.scanner.name` as `<install_root>/<name>/<rev>/<name>` under `secrets.scanner.install_root`, outside the checkout, only when the archive's sha256 is the pinned one. It keeps the archive beside the program and records the program through scripts/scan_secrets.py `write_record`, the record every scan runs. A second run trusts nothing written beside the program: it finds the program unchanged only when the kept archive's sha256 is the config pin and the program's sha256 is that of the archive's one member, and then fetches nothing and rewrites nothing; otherwise, a lost archive or execute bit included, it fetches and installs again. A `secrets.scanner.name` other than the scanner scripts/scan_secrets.py adapts (`ADAPTER`), an unlisted platform, an install root or program path that resolves inside the checkout, a record file git would track and a refused setting (a `rev` or `name` that is not one path part included) are CONFIG before anything is fetched; a URL that cannot be read is BACKEND_ABSENT naming `secrets.scanner.release_url`; a sha256 that differs, a reply over `secrets.scanner.download_max_bytes`, an archive that cannot be read as a .tar.gz (a cut gzip stream included) or one without exactly one regular member of that name is FAILURE, and each leaves nothing installed and no record. A file on this host that cannot be read or written (the install root, the kept archive, the program, the record, the scratch directory) is USAGE naming that path, never a network fault. Stdlib-only.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/unit/scripts/test_install_scanner.py
"""

import argparse
import contextlib
import gzip
import hashlib
import http.client
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zlib

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
_ARCHIVE_ERRORS = (tarfile.TarError, EOFError, zlib.error, gzip.BadGzipFile)


class _Refused(Exception):
    """The fetched archive is not the pinned one; nothing is installed."""

    def __init__(self, what, on, next_step):
        super().__init__(what)
        self.what, self.on, self.next_step = what, on, next_step


class _Unfetched(Exception):
    """The release URL could not be read: the network or the mirror."""

    def __init__(self, error):
        super().__init__(str(error))
        self.error = error


class _Local(Exception):
    """A file on this host could not be read or written."""

    def __init__(self, path, error):
        super().__init__("%s: %s" % (path, error))
        self.path, self.error = path, error


@contextlib.contextmanager
def _local(path):
    """Report an OSError inside the block as _Local naming *path*."""
    try:
        yield
    except OSError as exc:
        raise _Local(path, exc) from exc


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


def _copy_member(archive, name, sink, on):
    """Hand each chunk of the archive's one regular member named *name* to
    *sink*; raises _Refused when the archive is not a readable .tar.gz holding
    exactly that member, and _Local when the archive file cannot be read."""
    with _local(archive), open(archive, "rb") as raw:
        try:
            with tarfile.open(fileobj=raw, mode="r:gz") as tar:
                hits = [m for m in tar.getmembers() if m.name in (name, "./" + name)]
                if len(hits) != 1 or not hits[0].isfile():
                    raise _Refused(
                        "the archive holds %d members named %s, and needs one "
                        "regular file" % (len(hits), name),
                        on,
                        "pin the release archive that ships the program at its "
                        "top level",
                    )
                source = tar.extractfile(hits[0])
                if source is None:
                    raise _Refused(
                        "the archive member %s cannot be read" % name,
                        on,
                        "pin an archive whose member is a regular file",
                    )
                with source:
                    for chunk in iter(lambda: source.read(_CHUNK), b""):
                        sink(chunk)
        # A cut or corrupt gzip stream surfaces as any of these, EOFError and
        # zlib.error included, never only as TarError.
        except _ARCHIVE_ERRORS as exc:
            raise _Refused(
                "the archive cannot be read as a .tar.gz (%s: %s)"
                % (type(exc).__name__, exc),
                on,
                "pin the release's .tar.gz archive, with the sha256 the vendor's "
                "checksums file gives it",
            ) from exc


def _member_sha256(archive, name):
    digest = hashlib.sha256()
    _copy_member(archive, name, digest.update, archive)
    return digest.hexdigest()


def _installed(program, kept, asset, name):
    """True when the kept archive is the pinned one and *program* is its
    member, byte for byte; raises _Local when either cannot be read."""
    if not (os.path.isfile(kept) and os.path.isfile(program)):
        return False
    if not os.access(program, os.X_OK):
        return False
    with _local(kept):
        if scan_secrets.sha256(kept) != asset["sha256"]:
            return False
    try:
        member = _member_sha256(kept, name)
    except _Refused:
        # The archive's bytes are the pinned ones, so the fetch that follows
        # gets the same bytes and reports this refusal; nothing is swallowed.
        return False
    with _local(program):
        return scan_secrets.sha256(program) == member


def _fetch(url, dest, inst):
    """Copy *url* to *dest*, returning its sha256; raises _Unfetched when the
    URL cannot be read, _Local when *dest* cannot be written and _Refused past
    the cap."""
    cap = inst["download_max_bytes"]
    digest = hashlib.sha256()
    total = 0
    try:
        reply = urllib.request.urlopen(  # noqa: S310 — the scheme is held to https or file
            url, timeout=inst["download_timeout_seconds"]
        )
    except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
        raise _Unfetched(exc) from exc
    # A read fault is raised as _Unfetched, which is no OSError, so the
    # _local block names *dest* only for a fault in writing it.
    with reply, _local(dest), open(dest, "wb") as fh:
        while True:
            try:
                chunk = reply.read(_CHUNK)
            except (http.client.HTTPException, OSError) as exc:
                raise _Unfetched(exc) from exc
            if not chunk:
                break
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


def _extract(archive, name, dest, on):
    """Write the archive's one regular member named *name* to *dest*."""
    with _local(dest), open(dest, "wb") as fh:

        def write(chunk):
            # Inside _copy_member's own block for the archive, which would
            # otherwise name the archive for a fault in writing *dest*.
            with _local(dest):
                fh.write(chunk)

        _copy_member(archive, name, write, on)


def _place(source, dest, mode):
    """Copy *source* into place at *dest* with *mode*: a whole file or none."""
    folder = os.path.dirname(dest)
    with _local(dest):
        os.makedirs(folder, exist_ok=True)
        handle, partial = tempfile.mkstemp(dir=folder, prefix=".partial-")
        try:
            with os.fdopen(handle, "wb") as fh, open(source, "rb") as src:
                shutil.copyfileobj(src, fh)
            os.chmod(partial, mode)
            os.replace(partial, dest)
        except BaseException:
            os.unlink(partial)
            raise


def _install(url, asset, inst, name, program, kept):
    """Fetch, check and place the archive and its program; raises _Refused,
    _Unfetched or _Local."""
    with _local(tempfile.gettempdir()):
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
        _extract(archive, name, extracted, url)
        # The archive is kept beside the program, so a later run proves the
        # program from bytes whose sha256 is the config pin; a note of digests
        # written here could be forged by anyone who can write here.
        _place(archive, kept, 0o644)
        _place(extracted, program, 0o755)
    finally:
        shutil.rmtree(scratch)


def _run(root, cfg, inst):
    name, rev = cfg["name"], cfg["rev"]
    why = scan_secrets.other_adapter(cfg)
    if why is not None:
        return report(
            ExitCode.CONFIG, why, "%s.name" % _WHERE, scan_secrets.OTHER_ADAPTER_NEXT
        )
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
    program = os.path.join(install_root, name, rev, name)
    # The program path is judged too, resolved: a link under the root could
    # still lead into the checkout.
    for path in (install_root, program):
        if _inside(path, root):
            return report(
                ExitCode.CONFIG,
                "%s resolves inside the checkout, where git would list the "
                "program" % path,
                "%s.install_root" % _WHERE,
                "point it at a per-user directory outside the checkout, with no "
                "link under it into the checkout",
            )
    if not scan_secrets.record_is_ignored(root, cfg):
        return report(
            ExitCode.CONFIG,
            "git would commit the scanner record %s, which names one machine's "
            "path" % cfg["record_file"],
            "%s.record_file" % _WHERE,
            "ignore that path in .gitignore, then rerun",
        )
    kept = os.path.join(os.path.dirname(program), asset["file"])
    url = inst["release_url"].rstrip("/") + "/" + asset["file"]
    try:
        fetched = not _installed(program, kept, asset, name)
        if fetched:
            _install(url, asset, inst, name, program, kept)
        with _local(os.path.join(root, cfg["record_file"])):
            recorded = scan_secrets.write_record(root, cfg, program)
    except _Refused as exc:
        return report(ExitCode.FAILURE, exc.what, exc.on, exc.next_step)
    except _Unfetched as exc:
        return report(
            ExitCode.BACKEND_ABSENT,
            "the release archive cannot be fetched (%s)" % exc.error,
            url,
            "check the network, or point %s.release_url at a reachable "
            "mirror that holds the same file" % _WHERE,
        )
    except _Local as exc:
        return report(
            ExitCode.USAGE,
            "a file on this host cannot be read or written (%s)" % exc.error,
            exc.path,
            "give this user read and write access to that path, or point "
            "%s.install_root elsewhere, then rerun" % _WHERE,
        )
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
