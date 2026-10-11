"""
title: Eval doers — the closed registry of code paths a case drives
layer: n/a
public_api: no
summary: DOERS maps each doer name a case may name to a function (text, backend) -> response that runs real project code on the backend it is handed: 'prompt' sends the text as the whole prompt, and 'triage' runs agents/triage's shipped prompt. prompt_sha256 runs a doer against a backend that only captures what it is sent, so a recording's prompt hash comes from the code, never from hand; a doer that sends no prompt, or more than one, is a ValueError.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from types import MappingProxyType

from agents.triage import triage
from models import ModelBackend

__all__ = ["DOERS", "Doer", "prompt_sha256", "sha256_text"]

Doer = Callable[[str, ModelBackend], str]


def sha256_text(text: str) -> str:
    """'sha256:' and the hex digest of *text*'s UTF-8 bytes: the one spelling
    of a content hash in a case and a report."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prompt(text: str, backend: ModelBackend) -> str:
    return backend.run(text)


def _triage(text: str, backend: ModelBackend) -> str:
    return triage(text, execute=True, backend=backend)


DOERS: Mapping[str, Doer] = MappingProxyType({"prompt": _prompt, "triage": _triage})


class _Capture(ModelBackend):
    """Records each prompt it is sent and answers with nothing."""

    name = "capture"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run(self, prompt: str, **opts: object) -> str:
        self.prompts.append(prompt)
        return ""


def prompt_sha256(doer: str, text: str, doers: Mapping[str, Doer] = DOERS) -> str:
    """The hash of the prompt *doer* sends for *text*, by running it. Raises
    KeyError for an unknown doer and ValueError when it sends no prompt or more
    than one."""
    capture = _Capture()
    doers[doer](text, capture)
    if len(capture.prompts) != 1:
        raise ValueError(
            "doer %r sent %d prompts; a case judges exactly one"
            % (doer, len(capture.prompts))
        )
    return sha256_text(capture.prompts[0])
