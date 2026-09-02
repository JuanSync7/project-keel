"""
title: Claude Code headless backend
layer: backend
public_api: no
summary: Runs a prompt via the Claude Code CLI in headless mode. A missing binary is ModelUnavailable (absent); a non-zero exit is RuntimeError (broken).
"""

from __future__ import annotations

import subprocess

from .contracts import ModelBackend, ModelUnavailable

__all__ = ["ClaudeCodeHeadless"]


class ClaudeCodeHeadless(ModelBackend):
    """Adapter that shells out to `claude -p` (headless, non-interactive).

    Replace flags/parsing to match your installed Claude Code version.
    API keys come from the environment, never from config files.
    """

    name = "claude-code-headless"

    def __init__(self, model: str = "claude-opus-4-8", binary: str = "claude"):
        self.model = model
        self.binary = binary

    def run(self, prompt: str, **opts) -> str:
        cmd = [self.binary, "-p", prompt, "--model", self.model]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as exc:
            # Absent, not broken: nothing to run here. A doer that catches this
            # says so and exits 0; a traceback would read as a failed run.
            raise ModelUnavailable(
                f"claude binary {self.binary!r} is not on PATH -- install Claude "
                "Code, or select another backend (`models/`, e.g. `fake`)"
            ) from exc
        except OSError as exc:
            raise ModelUnavailable(f"cannot start {self.binary!r}: {exc}") from exc
        if proc.returncode != 0:
            # Present but failing: the run itself is the defect. Not swallowed.
            raise RuntimeError(f"claude headless failed: {proc.stderr.strip()}")
        return proc.stdout.strip()
