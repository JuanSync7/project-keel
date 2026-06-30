"""
title: MCP action server
layer: backend
public_api: no
summary: State-changing MCP tools that delegate to scripts/jobs doers; defaults to dry-run.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Thin transport: insert this dir so `protocol` imports as a sibling module.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from protocol import Tool, ToolServer, serve_stdio  # noqa: E402

__all__ = ["build_action_server"]

_REBUILD_DOER = "scripts/jobs/rebuild_index.py"

_REBUILD_SCHEMA = {
    "type": "object",
    "properties": {
        "out": {"type": "string",
                "description": "output path for the index (relative to repo root)"},
        "execute": {"type": "boolean",
                    "description": "actually write the file (default false = dry-run)"},
    },
    "additionalProperties": False,
}


def _run_doer(root: str, args: list) -> tuple:
    """Invoke a jobs doer via its CLI with the running interpreter; return (rc, out)."""
    proc = subprocess.run([sys.executable, _REBUILD_DOER, "--root", root] + args,
                          cwd=str(_ROOT), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def build_action_server(root: str | None = None) -> ToolServer:
    """Build the state-changing action server.

    Every tool defaults to **dry-run**: it reports what it WOULD do and writes
    nothing unless ``execute: true`` is passed. The work itself lives in the
    ``scripts/jobs`` doer — this server only validates, gates, and delegates.
    ``root`` overrides the tree to index (default: the repo root).
    """
    tree = root or str(_ROOT)

    def rebuild_index(args: dict) -> dict:
        out = args.get("out", "wiki/INDEX.md")
        execute = bool(args.get("execute", False))
        # Always compute the would-be index (read-only, no write) for a byte count.
        rc, content, err = _run_doer(tree, ["--out", "-"])
        if rc != 0:
            raise RuntimeError("rebuild_index failed: %s" % err.strip())
        n_bytes = len(content.encode("utf-8"))
        if not execute:
            return {"executed": False, "target": out, "bytes": n_bytes,
                    "preview": content[:200]}
        rc, _, err = _run_doer(tree, ["--out", out])   # the doer does the write
        if rc != 0:
            raise RuntimeError("rebuild_index write failed: %s" % err.strip())
        return {"executed": True, "target": out, "bytes": n_bytes}

    return ToolServer("keel-actions", (
        Tool(name="rebuild_index",
             description="Rebuild the doc index (dry-run unless execute=true).",
             input_schema=_REBUILD_SCHEMA, handler=rebuild_index),
    ))


if __name__ == "__main__":   # pragma: no cover — launched by an MCP client
    serve_stdio(build_action_server())
