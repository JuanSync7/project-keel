"""
title: Claude Code headless backend
layer: backend
public_api: no
summary: Runs a prompt via the Claude Code CLI in headless mode, with the allowlisted environment plus the credential names config/project.json `models.credential_env` declares for this adapter (scripts/child_env.py). A missing binary is ModelUnavailable (absent); a non-zero exit is RuntimeError (broken); a broken allowlist is ChildEnvError, never ModelUnavailable.
"""

from __future__ import annotations

import subprocess

from scripts.child_env import build_child_env

from .contracts import ModelBackend, ModelUnavailable

__all__ = ["ClaudeCodeHeadless"]


class ClaudeCodeHeadless(ModelBackend):
    """Adapter that shells out to `claude -p` (headless, non-interactive).

    Replace flags/parsing to match your installed Claude Code version.
    API keys come from the environment, never from config files, and the CLI
    sees only the ones config/project.json `models.credential_env` names for
    this adapter: a cloud or forge credential in the parent stays there.
    """

    name = "claude-code-headless"

    def __init__(self, model: str = "claude-opus-4-8", binary: str = "claude"):
        self.model = model
        self.binary = binary

    def run(self, prompt: str, **opts) -> str:
        cmd = [self.binary, "-p", prompt, "--model", self.model]
        # Built outside the try: a broken allowlist is a config defect a caller
        # must see, never an absent model it may skip.
        env = build_child_env(credentials_for=self.name)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
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
