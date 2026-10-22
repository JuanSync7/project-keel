"""
title: Eval doers — the closed registry of code paths a case drives
layer: n/a
public_api: no
summary: DOERS maps each doer name a case may name to a function (text, backend) -> response that runs real project code on the backend it is handed: 'prompt' sends the text as the whole prompt, 'triage' runs agents/triage's shipped prompt, and each other agent's doer, named after the agent, reads the text as one JSON object holding exactly that agent's model-step inputs and runs the step the agent's own plan runs (a malformed text is a ValueError naming the doer). prompt_sha256 runs a doer against a backend that only captures what it is sent, so a recording's prompt hash comes from the code, never from hand; a doer that sends no prompt, or more than one, is a ValueError.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from agents.doc_reviewer import propose as propose_doc_edit
from agents.index_enforcer import summarize_gap
from agents.practice_refactor import propose as propose_refactor
from agents.triage import triage
from agents.wiki_navigator import synthesize
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


def _inputs(doer: str, text: str, spec: Mapping[str, type]) -> dict[str, Any]:
    """The JSON object *text* holds, keyed by exactly *spec*'s names, each value
    of its type (a list's members are objects). Raises ValueError naming
    *doer*, so a malformed case is that case's error before any model call."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(
            "doer %r: the case text is not JSON (%s)" % (doer, exc)
        ) from exc
    if not isinstance(data, dict) or set(data) != set(spec):
        raise ValueError(
            "doer %r: the case text must be a JSON object with exactly the keys %s"
            % (doer, sorted(spec))
        )
    for name, kind in sorted(spec.items()):
        value = data[name]
        if not isinstance(value, kind) or (
            isinstance(value, list) and not all(isinstance(v, dict) for v in value)
        ):
            raise ValueError(
                "doer %r: %r must be a JSON %s" % (doer, name, _JSON_NAMES[kind])
            )
    return data


_JSON_NAMES: Mapping[type, str] = MappingProxyType(
    {str: "string", dict: "object", list: "array of objects"}
)


def _index_enforcer(text: str, backend: ModelBackend) -> str:
    args = _inputs("index_enforcer", text, {"node": dict})
    return summarize_gap(args["node"], backend=backend)


def _spec_text(spec: dict[str, Any] | None) -> str:
    """A proposed edit spec as canonical JSON, or `null` for a decline."""
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))


def _doc_reviewer(text: str, backend: ModelBackend) -> str:
    args = _inputs("doc_reviewer", text, {"rules": list, "chunk": dict})
    return _spec_text(propose_doc_edit(args["rules"], args["chunk"], backend=backend))


def _practice_refactor(text: str, backend: ModelBackend) -> str:
    args = _inputs(
        "practice_refactor",
        text,
        {"practice": str, "practice_def": dict, "node": dict},
    )
    return _spec_text(
        propose_refactor(
            args["practice"], args["practice_def"], args["node"], backend=backend
        )
    )


def _wiki_navigator(text: str, backend: ModelBackend) -> str:
    args = _inputs("wiki_navigator", text, {"question": str, "nodes": list})
    return synthesize(args["question"], args["nodes"], backend=backend)


DOERS: Mapping[str, Doer] = MappingProxyType(
    {
        "doc_reviewer": _doc_reviewer,
        "index_enforcer": _index_enforcer,
        "practice_refactor": _practice_refactor,
        "prompt": _prompt,
        "triage": _triage,
        "wiki_navigator": _wiki_navigator,
    }
)


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
