"""
title: Backend shared
layer: backend
public_api: yes
summary: Domain-meaningful types/models shared across backend features, including the project's identity read from the manifest; excessive JSON nesting or an unusable identity shape raises IdentityUnreadable naming the repair.
"""

from __future__ import annotations

import json
import os

__all__ = ["display_title", "project_identity", "IdentityUnreadable"]


class IdentityUnreadable(ValueError):
    """The manifest cannot supply an identity; the message names its repair."""


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
    Excessive nesting, a non-object manifest or a non-string name raises
    IdentityUnreadable naming the file and repair.
    """
    root = os.path.abspath(root)
    name = ""
    try:
        with open(os.path.join(root, *_MANIFEST), encoding="utf-8") as fh:
            data = json.load(fh)
    except RecursionError as exc:
        raise IdentityUnreadable(
            "config/project.json is nested too deeply; repair the manifest"
        ) from exc
    except (OSError, ValueError):  # noqa: DROP001 -- an unnamed manifest falls back to the directory name, as documented
        data = {}
    if not isinstance(data, dict):
        raise IdentityUnreadable(
            "config/project.json must be an object; repair the manifest"
        )
    name = data.get("name") or ""
    if not isinstance(name, str):
        raise IdentityUnreadable(
            "config/project.json name must be a string; repair the manifest"
        )
    if not name:
        name = os.path.basename(root)
    return name, display_title(name)
