"""
title: Claude Code headless backend
layer: backend
public_api: no
summary: Runs a prompt via the Claude Code CLI in headless mode.
"""
from __future__ import annotations
import subprocess

from .contracts import ModelBackend

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
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"claude headless failed: {proc.stderr.strip()}")
        return proc.stdout.strip()
