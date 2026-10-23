"""
title: MCP action server
layer: backend
public_api: no
summary: State-changing MCP tools that delegate to scripts/jobs doers; defaults to dry-run. A doer runs through scripts/resource_limits.py run_tool, held to config/project.json `agents.tool_timeout_seconds` and `agents.tool_max_output_bytes`; past either its process group is ended and the tool call is an error naming the key. `main` is the entry: it serves through mcp/protocol.py run_stdio_server and exits 0 once the loop ends, or CONFIG through scripts/exit_codes.py report, naming the key, when a setting it reads, those two included, is refused before it serves.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Thin transport: insert this dir so `protocol` imports as a sibling module, and
# the repo root so the doer's child gets the allowlisted environment.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(_ROOT))
# scripts/ itself, so the exit helper imports by its one bare name.
sys.path.insert(2, str(_ROOT / "scripts"))

from exit_codes import ExitCode, finish, report  # noqa: E402
from protocol import Tool, ToolServer, run_stdio_server  # noqa: E402
from scripts import config_loader  # noqa: E402
from scripts.resource_limits import run_tool, tool_limits  # noqa: E402

__all__ = ["build_action_server", "main"]

_REBUILD_DOER = "scripts/jobs/rebuild_index.py"

_REBUILD_SCHEMA = {
    "type": "object",
    "properties": {
        "out": {
            "type": "string",
            "description": "output path for the index (relative to repo root)",
        },
        "execute": {
            "type": "boolean",
            "description": "actually write the file (default false = dry-run)",
        },
    },
    "additionalProperties": False,
}


def _run_doer(root: str, args: list, limits_root: str | None = None) -> tuple:
    """Invoke a jobs doer via its CLI with the running interpreter and the
    allowlisted environment, held to *limits_root*'s agents.tool_timeout_seconds
    and agents.tool_max_output_bytes (this checkout when None); return
    (rc, out, err). ChildTimedOut or ChildOutputTooLarge names the key."""
    proc = run_tool(
        [sys.executable, _REBUILD_DOER, "--root", root] + args,
        cwd=str(_ROOT),
        root=limits_root,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _safe_out(tree: str, out: str) -> str:
    """Resolve ``out`` and refuse anything that escapes the indexed ``tree``.

    Defence in depth: MCP tool arguments can originate from an LLM acting on
    untrusted input, so an absolute path or a ``..`` escape (e.g. ``/etc/x``,
    ``../../x``) must be rejected before any write — the action tool may only
    write inside the tree it indexes.
    """
    base = os.path.realpath(tree)
    target = os.path.realpath(out if os.path.isabs(out) else os.path.join(base, out))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("out path %r escapes the indexed tree" % out)
    return target


def build_action_server(
    root: str | None = None, limits_root: str | None = None
) -> ToolServer:
    """Build the state-changing action server.

    Every tool defaults to **dry-run**: it reports what it WOULD do and writes
    nothing unless ``execute: true`` is passed. The work itself lives in the
    ``scripts/jobs`` doer — this server only validates, gates, and delegates.
    ``root`` overrides the tree to index (default: the repo root);
    ``limits_root`` is the checkout whose config bounds the doer (default:
    this one).
    """
    tree = root or str(_ROOT)

    def rebuild_index(args: dict) -> dict:
        out = args.get("out", "wiki/INDEX.md")
        execute = bool(args.get("execute", False))
        # Always compute the would-be index (read-only, no write) for a byte count.
        rc, content, err = _run_doer(tree, ["--out", "-"], limits_root)
        if rc != 0:
            raise RuntimeError("rebuild_index failed: %s" % err.strip())
        n_bytes = len(content.encode("utf-8"))
        if not execute:
            return {
                "executed": False,
                "target": out,
                "bytes": n_bytes,
                "preview": content[:200],
            }
        dest = _safe_out(tree, out)  # refuse escapes before writing
        # the doer does the write
        rc, _, err = _run_doer(tree, ["--out", dest], limits_root)
        if rc != 0:
            raise RuntimeError("rebuild_index write failed: %s" % err.strip())
        return {"executed": True, "target": out, "bytes": n_bytes}

    return ToolServer(
        "keel-actions",
        (
            Tool(
                name="rebuild_index",
                description="Rebuild the doc index (dry-run unless execute=true).",
                input_schema=_REBUILD_SCHEMA,
                handler=rebuild_index,
            ),
        ),
    )


def main(root: str | None = None) -> ExitCode:
    """Serve the action tools over stdio under *root*'s limits (this checkout
    when None), the doer's included, until stdin ends or a stop signal; CONFIG
    for a refused setting, before anything serves."""
    try:
        # Read once here so a refused tool limit stops the server before it
        # serves; each doer call reads it again, as a model call reads its own.
        tool_limits(root)
        run_stdio_server(build_action_server(limits_root=root), root=root)
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the MCP action server's settings are refused",
            "; ".join(exc.lines),
            "set each key the line names inside its bound",
        )
    return ExitCode.SUCCESS


if __name__ == "__main__":  # pragma: no cover — launched by an MCP client
    finish(main())
