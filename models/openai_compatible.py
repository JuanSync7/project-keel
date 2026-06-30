"""
title: OpenAI-compatible model backend
layer: backend
public_api: no
summary: Adapter for any HTTP endpoint speaking the OpenAI chat-completions API.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, Optional

from .contracts import ModelBackend

__all__ = ["OpenAICompatible"]

# A transport is (url, payload, headers, timeout) -> parsed-json dict. The real
# one is urllib (stdlib, in-process — no curl/subprocess); tests inject a fake.
Transport = Callable[[str, dict, dict, float], dict]


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    """POST ``payload`` as JSON and return the decoded JSON response (stdlib)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 (own URL)
        return json.loads(resp.read().decode("utf-8"))


class OpenAICompatible(ModelBackend):
    """Talks to ANY server speaking the OpenAI chat-completions wire format.

    The provider is a *configuration* choice, not a baked-in vendor: point
    ``base_url`` at OpenAI, a local Ollama/vLLM/LM Studio server, Together,
    Groq, or an internal gateway — the adapter is identical. The API key is read
    from the environment (``api_key_env``), never from config or constructor
    args; a keyless local server simply gets no Authorization header.
    """

    name = "openai-compatible"

    def __init__(self, base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4o-mini", api_key_env: str = "OPENAI_API_KEY",
                 timeout: float = 60.0, transport: Optional[Transport] = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = timeout
        self._transport = transport or _post_json

    def run(self, prompt: str, **opts) -> str:
        url = self.base_url + "/chat/completions"
        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": prompt}]}
        payload.update(opts)   # temperature, max_tokens, … pass straight through
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
        if key:
            headers["Authorization"] = "Bearer " + key
        data = self._transport(url, payload, headers, self.timeout)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "unexpected response from %s: %r" % (url, data)) from exc
