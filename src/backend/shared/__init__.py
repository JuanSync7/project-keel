"""
title: Backend shared
layer: backend
public_api: yes
summary: Domain-meaningful types/models shared across backend features — incl. the project's own identity (name/title) read from the manifest.
"""
from __future__ import annotations

import json
import os

__all__ = ["display_title", "project_identity"]

_MANIFEST = ("config", "project.json")


def display_title(name: str) -> str:
    """Turn a project slug into a human display title.

    ``"acme_widgets" -> "Acme Widgets"``. This is deliberately the SAME derivation
    copier's computed ``project_title`` answer uses, so a project generated as
    "Acme Widgets" and one renamed to ``acme_widgets`` later present identically.
    Kept pure (no disk) so it is unit-testable and so callers decide where the
    name comes from.
    """
    return name.replace("_", " ").replace("-", " ").title()


def project_identity(root: str) -> tuple[str, str]:
    """Return ``(name, title)`` for the project rooted at *root*.

    Read from ``config/project.json`` — the manifest the project is already
    required to keep true (CONVENTIONS §15, enforced by ``check_H``) — rather than
    baked in at generation from a copier answer. An answer is frozen the moment
    the project is created and silently wrong the first time it is renamed; the
    manifest is the one place a rename is obliged to touch.

    Falls back to the root directory's own name, which is real information about
    an unnamed project, rather than to any hardcoded literal.
    """
    root = os.path.abspath(root)
    name = ""
    try:
        with open(os.path.join(root, *_MANIFEST), encoding="utf-8") as fh:
            name = (json.load(fh) or {}).get("name") or ""
    except (OSError, ValueError):
        name = ""
    if not name:
        name = os.path.basename(root)
    return name, display_title(name)
