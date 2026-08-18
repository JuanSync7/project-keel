"""
title: Optional-dependency policy — skip vs fail
summary: Turns pytest.importorskip into a hard import for any surface declared in KEEL_REQUIRED_EXTRAS (CI installs those on purpose), so a broken install fails the run instead of degrading into a green suite with the assertions never executed; an undeclared surface still skips.

Whether a missing optional dependency SKIPS the test or FAILS the run.

`pytest.importorskip` is the right default for a genuinely optional surface — the
langgraph engine is opt-in, and its conformance tests should not fail a machine
that never asked for it. It is exactly wrong for a surface CI installs *on
purpose*: there a missing or half-broken install degrades into a green run with
the assertions never executed, and nothing says so.

That is not hypothetical. `jsonschema` was in no extra at all, so the "served AAD
descriptor validates against the committed schema" assertion had **never run
anywhere** — not in CI, not locally — while the suite reported success on every
run. The one visible trace was a `1 skipped` that looked like the deliberate
langgraph skip.

So the decision lives here rather than in each module:

* CI declares the surfaces it installed, via `KEEL_REQUIRED_EXTRAS`.
* A module guarding an import names the surface that import belongs to.
* Declared  -> a real import, whose ImportError is a hard collection error.
* Undeclared -> `importorskip`, so a bare local clone still skips gracefully.

Keep `DELIBERATELY_OPTIONAL` honest: an entry there is a promise that the surface
is opt-in, not a place to silence an install problem.
"""

import importlib
import os

import pytest

#: Environment variable CI sets to declare which optional surfaces it installed.
ENV_VAR = "KEEL_REQUIRED_EXTRAS"

#: The surface vocabulary: name -> the CI step that installs it. A name is valid
#: only if it appears here, so a typo in ci.yml (`tempalte`) is a loud error
#: instead of silently disabling the very guard it was meant to switch on — which
#: is the failure mode this whole module exists to remove.
SURFACES = {
    "template": 'pip install -e ".[dev,template]"',  # copier + its yaml
    "dev": 'pip install -e ".[dev,template]"',  # pytest, jsonschema, httpx
    "transport": "pip install -r api/rest_fastapi/requirements.txt",
}

#: Surfaces that must stay a skip even in CI, with the reason. The langgraph
#: engine is selected by name at runtime (`get_runtime("langgraph")`); the default
#: `inprocess` runtime is pure stdlib, and keeping the default install
#: dependency-free is a deliberate property of the template.
DELIBERATELY_OPTIONAL = {
    "langgraph": "opt-in runtime engine; the default inprocess runtime is stdlib-only",
}


def required_extras():
    """The declared surfaces, validated against `SURFACES`."""
    declared = {p.strip() for p in os.environ.get(ENV_VAR, "").split(",") if p.strip()}
    unknown = sorted(declared - set(SURFACES))
    if unknown:
        raise RuntimeError(
            "%s names unknown surface(s) %s; known: %s. A typo here silently "
            "disables the hard-failure guard, so it is an error rather than a "
            "no-op." % (ENV_VAR, unknown, sorted(SURFACES))
        )
    return declared


def importorskip(module, extra):
    """Import `module`, or skip — unless CI declared `extra` required.

    `extra` must be a key of `SURFACES`: naming a surface that nothing installs
    would make this call permanently a skip.
    """
    if extra not in SURFACES:
        raise ValueError(
            "unknown surface %r for module %r; add it to SURFACES with the CI step "
            "that installs it, or use pytest.importorskip if it is genuinely "
            "optional" % (extra, module)
        )
    if extra in required_extras():
        # A real import: ImportError propagates and collection fails loudly.
        return importlib.import_module(module)
    return pytest.importorskip(module)
