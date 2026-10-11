#!/usr/bin/env python3
"""
title: Trace requirements — judge every requirement as covered, a documented gap or uncovered, and write the matrix
kind: script
layer: n/a
summary: The command line `make trace` runs; it calls scripts/traceability.py and holds no judging logic. It reads config/project.json `traceability`, refuses, before reading a spec or writing anything, a `matrix_path`, its temporary file, a `specs_root`, a `tests_root` or a `matrix_schema` reached through a symlink (the config's path check and git's ignore rule both judge the text of a path, not where it leads) and a `matrix_path` git does not ignore, writes a red `incomplete` matrix first so a run that stops never leaves an earlier green one standing, reads pytest's collection rule from the project's own ini without collecting a test, then judges every requirement and replaces `traceability.matrix_path` whole with the canonical matrix. Exit 0 when every unit is covered or a documented gap and there is no finding, 1 when there is a finding (each is one stderr line), and 2 when it could not judge or could not say so in a matrix: a refused `traceability` block, a symlinked or un-ignored path, a repository git cannot read, an unreadable schema, spec or test file, a collection rule pytest could not give, or a `matrix_path` the filesystem will not let it write (a directory already there, a file where its directory goes), which is one stderr line naming the configured path and leaves no temporary file. It imports no test and runs none. It is not the gate test (tests/integration/test_requirement_traceability.py judges the same tree in the suite) and not a coverage tool: it says a test names a requirement, never that the test proves it.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_requirement_traceability.py
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from collections.abc import Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

import check_structure  # noqa: E402 — the one reader of a module header
import git_tree  # noqa: E402 — the one definition of what git ignores
import pytest_markers  # noqa: E402
import traceability  # noqa: E402

_NAME = "trace"
EXIT_PASS, EXIT_FINDINGS, EXIT_REFUSED = 0, 1, 2
# How much of git's own complaint a refusal quotes.
_GIT_ERROR_MAX = 200


def _say(text: str) -> None:
    print("%s: %s" % (_NAME, text), file=sys.stderr)


def _write(root: str, rel: str, text: str) -> None:
    """Replace *rel* whole: written beside it, then renamed, so a reader never
    sees half a matrix. O_NOFOLLOW makes the kernel refuse a temporary file
    that became a symlink after the check in main."""
    path = os.path.join(root, *rel.split("/"))
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except OSError as exc:
        _discard(tmp)
        raise _Unwritable(rel, exc) from None


def _discard(path: str) -> None:
    """Remove the file at *path* if there is one. Whatever stops that (it is
    a directory, or its directory cannot be written) is the failure the caller
    is already reporting, so it is not a second one."""
    with contextlib.suppress(OSError):
        os.remove(path)


class _Unwritable(Exception):
    """The matrix could not be written or removed. Its text names the
    configured path and the kind of failure, never the absolute path."""

    def __init__(self, rel: str, exc: OSError) -> None:
        super().__init__(
            "%s `%s.matrix_path` %r cannot be written (%s: %s); no matrix "
            "was written for this run, so trust this exit code, not a file "
            "found there"
            % (
                traceability.MANIFEST,
                traceability.BLOCK,
                rel,
                type(exc).__name__,
                exc.strerror or "no reason given",
            )
        )


def _inside_a_repository(root: str) -> bool:
    """True when *root* or a directory above it holds a `.git` entry. Asked
    only after git has failed, to tell "no repository here" (nothing a matrix
    could dirty) from "a repository git could not read" (unknown)."""
    folder = os.path.realpath(root)
    while True:
        if os.path.lexists(os.path.join(folder, ".git")):
            return True
        parent = os.path.dirname(folder)
        if parent == folder:
            return False
        folder = parent


def _load_policy(root: str) -> traceability.Policy:
    path = os.path.join(root, *traceability.MANIFEST.split("/"))
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        raise traceability.TraceError(
            "%s cannot be read (%s)" % (traceability.MANIFEST, type(exc).__name__)
        ) from None
    return traceability.load_policy(manifest)


def _read_bounds(root: str, policy: traceability.Policy) -> traceability.Bounds:
    path = os.path.join(root, *policy.matrix_schema.split("/"))
    try:
        with open(path, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, ValueError) as exc:
        raise traceability.TraceError(
            "%s `%s.matrix_schema` %r cannot be read (%s)"
            % (
                traceability.MANIFEST,
                traceability.BLOCK,
                policy.matrix_schema,
                type(exc).__name__,
            )
        ) from None
    return traceability.read_bounds(schema)


def _shown(value: object, bounds: traceability.Bounds) -> str:
    # An id comes from a test file or a config value: printed escaped and cut,
    # so it cannot put a control character or a wall of text on the terminal.
    return "-" if value is None else ascii(str(value)[: bounds.id_max])


def _summary(
    rel: str, judgement: traceability.Judgement, policy: traceability.Policy
) -> None:
    if judgement.state == "no-requirements":
        why = (
            "no reason given"
            if policy.no_requirements is None
            else "%s is set" % traceability.EMPTY_KEY
        )
        print("%s: no requirement to trace (%s)" % (_NAME, why))
    else:
        print(
            "%s: %s"
            % (
                _NAME,
                ", ".join(
                    "%d %s" % (judgement.counts[v] or 0, v)
                    for v in traceability.VERDICTS
                ),
            )
        )
    print("%s: %s -> %s" % (_NAME, judgement.result, rel))


def main(argv: Sequence[str] | None = None) -> int:
    """Judge the project's requirements; the exit code is the verdict. A
    matrix path that cannot be written is exit 2 with one line saying so."""
    parser = argparse.ArgumentParser(
        description=check_structure._module_meta(__doc__)["title"],
        epilog="exit: 0 every unit covered or a documented gap; 1 a finding; "
        "2 could not judge (config, path, git, schema, spec, test file or "
        "collection rule) or could not write the matrix, or a usage error",
    )
    parser.add_argument(
        "--root", default=None, help="project root (default: this file's repo)"
    )
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root or _REPO)
    try:
        try:
            policy = _load_policy(root)
        except traceability.TraceError as exc:
            _say(str(exc))
            _say(
                "the `%s` block is what names the matrix, so nothing was written or "
                "removed and an earlier matrix may still stand; trust this exit "
                "code, not that file" % traceability.BLOCK
            )
            return EXIT_REFUSED

        rel = policy.matrix_path
        guarded = [rel, rel + ".tmp"]
        read = [policy.specs_root, policy.tests_root, policy.matrix_schema]
        linked = git_tree.through_symlink(root, guarded + read)
        if linked:
            _say(
                "%s `%s` reaches %s through a symlink; a read or a write there "
                "could land outside the project, so nothing was read or written"
                % (traceability.MANIFEST, traceability.BLOCK, ", ".join(linked))
            )
            return EXIT_REFUSED

        try:
            loose = [p for p in guarded if not git_tree.is_ignored(root, p)]
        except git_tree.NoGitError as exc:
            if _inside_a_repository(root):
                _say(
                    "git could not say whether %r is ignored (%s); a failure is "
                    "not an answer, so nothing was written"
                    % (rel, str(exc)[:_GIT_ERROR_MAX])
                )
                return EXIT_REFUSED
            # No repository, so no tracked tree a matrix could dirty. Staying
            # inside the project was through_symlink's question, already answered.
            loose = []
        if loose:
            _say(
                "%s `%s.matrix_path` %r is not git-ignored (%s); a matrix there "
                "would dirty the tree, so nothing was written"
                % (traceability.MANIFEST, traceability.BLOCK, rel, ", ".join(loose))
            )
            return EXIT_REFUSED

        try:
            bounds = _read_bounds(root, policy)
        except traceability.TraceError as exc:
            _say(str(exc))
            # Without the schema's version no matrix can be written, so an earlier
            # one goes rather than stand green beside this run. The path was
            # accepted above: inside the project and ignored.
            path = os.path.join(root, *rel.split("/"))
            if os.path.lexists(path):
                try:
                    os.remove(path)
                except OSError as gone:
                    raise _Unwritable(rel, gone) from None
                _say("removed the earlier %s" % rel)
            return EXIT_REFUSED

        _write(
            root,
            rel,
            traceability.render(
                traceability.stopped_matrix(policy, bounds, "incomplete")
            ),
        )
        try:
            rule = pytest_markers.collection_rule_from_ini(root, policy.tests_root)
            catalogue, judgement = traceability.trace_tree(root, policy, rule)
        except (traceability.TraceError, pytest_markers.MarkerError) as exc:
            _write(
                root,
                rel,
                traceability.render(
                    traceability.stopped_matrix(policy, bounds, "refused")
                ),
            )
            _say(str(exc))
            print("%s: refused -> %s" % (_NAME, rel))
            return EXIT_REFUSED

        matrix = traceability.build_matrix(policy, bounds, catalogue, judgement)
        _write(root, rel, traceability.render(matrix))
        for found in judgement.findings:
            _say(
                "%s: %s (%s)"
                % (found["kind"], _shown(found["id"], bounds), found["where"])
            )
        _summary(rel, judgement, policy)
        return EXIT_PASS if judgement.result == "pass" else EXIT_FINDINGS

    except _Unwritable as exc:
        _say(str(exc))
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
