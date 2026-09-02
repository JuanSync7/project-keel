"""
title: Export OpenAPI schema
kind: script
layer: backend
summary: Emit api/rest_fastapi/openapi.json from the live FastAPI app (one source of truth).
"""

# No `from __future__ import annotations`: the --check hook may run under an old
# python3 that lacks FastAPI; this file must still parse so the graceful skip
# below can fire (the same shape as scripts/agent_surface/generate_aad_schema.py,
# including its environment-vs-defect split — this file mirrored the PRE-fix
# version of that one until 2026-09-02).
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_OUT = os.path.join(_HERE, "openapi.json")

# The ONLY reasons this check may no-op: the host interpreter cannot parse the app
# (SyntaxError — the documented old pre-commit `python3`), or FastAPI / the app is
# not installed (ImportError, which ModuleNotFoundError extends). Both mean nothing
# is KNOWN about the contract, so a hook on an arbitrary host stays out of the way.
# Anything else means the check RAN and the app is broken — a duplicate operation
# id, a bad response_model, a NameError anywhere in the import graph — and the
# committed contract is unverifiable. Laundering that into a green `--check` is the
# silent-green class: this sits inside `make verify` and ships verbatim into every
# generated project, so the defect was inherited too.
_ENVIRONMENT_CANNOT_RUN = (ImportError, SyntaxError)


def _spec() -> dict:
    """Return the live OpenAPI document from the FastAPI app."""
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    from app import app  # imported here so --help / old python need no FastAPI

    return app.openapi()


def main(argv=None) -> int:
    """Write (or --check) the committed openapi.json contract snapshot.

    The committed file is the published REST contract; keep it generated from
    the live app so it cannot silently drift from the routes (api/ rules).
    Requires FastAPI (the project interpreter); --check is a no-op when absent.
    """
    ap = argparse.ArgumentParser(
        description="Export the FastAPI OpenAPI schema to openapi.json"
    )
    ap.add_argument(
        "--out", default=_OUT, help="output path (default: openapi.json next to app.py)"
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the committed openapi.json is stale (CI / pre-commit)",
    )
    opts = ap.parse_args(argv)

    try:
        text = json.dumps(_spec(), indent=2, sort_keys=True) + "\n"
    except _ENVIRONMENT_CANNOT_RUN as exc:
        # This host cannot run the check at all (old interpreter / FastAPI
        # absent). For --check that is a no-op; a real `make check-openapi` runs
        # under the project interpreter, where it is not.
        detail = "%s: %s" % (type(exc).__name__, exc)
        if opts.check:
            sys.stderr.write("OpenAPI check skipped (%s)\n" % detail)
            return 0
        sys.stderr.write("OpenAPI cannot be generated (%s)\n" % detail)
        return 1
    except Exception as exc:  # noqa: BLE001 — the app itself is broken
        # The environment DID run it and building the spec failed, so the
        # committed contract is unverifiable. Reporting 0 here would make the
        # drift guard report success while checking nothing.
        sys.stderr.write(
            "OpenAPI cannot be generated from the live app (%s: %s) — the "
            "contract is unverifiable; fix the app, do not edit openapi.json\n"
            % (type(exc).__name__, exc)
        )
        return 1

    if opts.check:
        try:
            with open(opts.out, encoding="utf-8") as fh:
                current = fh.read()
        except FileNotFoundError:
            # No contract committed yet — a real state, not a drift. `openapi.json`
            # is a GENERATED VIEW of the live app, so keel does not ship its own
            # into a new project: keel's names keel and lists the showcase routes,
            # which is stale in any project with a different name or without the
            # showcase, and `make check-all` would be red on arrival through no act
            # of the user's. Distinguishing "none yet" from "drifted" is what lets
            # the check be honest in both projects. Say so loudly; do not create it
            # here, because a check that writes is not a check.
            sys.stderr.write(
                "no committed openapi.json yet — publish this project's REST "
                "contract with `python %s`\n" % os.path.relpath(__file__)
            )
            return 0
        if current != text:
            sys.stderr.write(
                "openapi.json is stale; regenerate with "
                "`python api/rest_fastapi/export_openapi.py`\n"
            )
            return 1
        print("openapi.json up to date")
        return 0

    with open(opts.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote", opts.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
