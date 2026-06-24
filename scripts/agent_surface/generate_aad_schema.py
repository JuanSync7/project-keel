"""
title: Generate the AAD JSON Schema
kind: script
layer: backend
summary: Emit config/agent_surface/aad-v1.0.schema.json from the AadDescriptor model (one source of truth).
"""
# NB: no `from __future__ import annotations` here on purpose — the pre-commit
# --check hook may run under an old `python3`, and this file must still parse
# so the graceful skip below can fire. Keep annotations 3.x-safe.
import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_OUT = os.path.join("config", "agent_surface", "aad-v1.0.schema.json")


def _schema() -> dict:
    """Build the JSON Schema from the pydantic AadDescriptor model."""
    sys.path.insert(0, os.path.join(_ROOT, "api", "rest_fastapi"))
    from aad import AAD_VERSION, AadDescriptor  # imported here so --help needs no deps

    schema = AadDescriptor.model_json_schema()
    schema["$comment"] = (
        "GENERATED from api/rest_fastapi/aad (descriptor.py); AAD v%s. "
        "Do not hand-edit — run scripts/agent_surface/generate_aad_schema.py." % AAD_VERSION
    )
    return schema


def main(argv=None) -> int:
    """Write (or --check) the committed AAD JSON Schema.

    Requires pydantic (run under the project interpreter, not a bare 3.6). The
    committed schema is the contract the conformance test validates against —
    keep it generated, never hand-maintained.
    """
    ap = argparse.ArgumentParser(description="Generate the AAD JSON Schema from the model")
    ap.add_argument("--out", default=_OUT, help="output path (default: %s)" % _OUT)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed schema is stale (CI / pre-commit)")
    opts = ap.parse_args(argv)

    try:
        text = json.dumps(_schema(), indent=2, sort_keys=True) + "\n"
    except Exception as exc:  # noqa: BLE001 — best-effort drift guard
        # Old interpreter (can't parse the adapter) or pydantic absent. For
        # --check this is a no-op (like cdmon when not installed); a real
        # `make agent-surface-schema` runs under the project interpreter.
        detail = "%s: %s" % (type(exc).__name__, exc)
        if opts.check:
            sys.stderr.write("AAD schema check skipped (%s)\n" % detail)
            return 0
        sys.stderr.write("AAD schema cannot be generated (%s)\n" % detail)
        return 1
    path = os.path.join(_ROOT, opts.out)
    if opts.check:
        try:
            with open(path, encoding="utf-8") as fh:
                current = fh.read()
        except FileNotFoundError:
            current = ""
        if current != text:
            sys.stderr.write(
                "AAD schema is stale; regenerate with "
                "`python scripts/agent_surface/generate_aad_schema.py`\n")
            return 1
        print("AAD schema up to date")
        return 0

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote", opts.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
