"""
title: Fake model backend
layer: backend
public_api: no
summary: A deterministic, offline ModelBackend for tests and disconnected dev.
"""
from __future__ import annotations

from .contracts import ModelBackend

__all__ = ["FakeModel"]


class FakeModel(ModelBackend):
    """A ModelBackend that never touches a network or process.

    It returns a fixed ``reply`` if one is given, otherwise a deterministic
    function of the prompt (so the same prompt always yields the same text, and
    different prompts are distinguishable). This is the model equivalent of the
    runtimes' in-memory checkpointer: a real, registered backend whose only job
    is to let agents and transports be exercised hermetically. Select it by name
    like any other: ``get_model("fake")`` or ``get_model("fake", reply=...)``.
    """

    name = "fake"

    def __init__(self, reply: str | None = None, prefix: str = "fake-answer"):
        self.reply = reply
        self.prefix = prefix

    def run(self, prompt: str, **opts) -> str:
        if self.reply is not None:
            return self.reply
        # Deterministic, prompt-dependent, and bounded — echoes the first line so
        # a caller can see WHAT was asked without replaying an unbounded prompt.
        first_line = prompt.strip().splitlines()[0] if prompt.strip() else ""
        return "[%s] %s" % (self.prefix, first_line)
