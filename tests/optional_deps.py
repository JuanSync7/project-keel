"""
title: Optional-dependency policy — skip vs fail
summary: Turns pytest.importorskip into a hard import for any surface declared in KEEL_REQUIRED_EXTRAS (CI installs those on purpose) or named, in config/project.json `transports.extras`, by a transport `transports.enabled` lists (the project serves it, so its packages are owed on every machine, read through scripts/config_loader.py), so a broken install fails the run instead of degrading into a green suite with the assertions never executed; any other surface still skips, and a surface name outside SURFACES in either place is an error. require_or_skip applies the same rule to a surface that is not an import, such as the secret scanner `make secrets-install` builds.

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
* An enabled transport declares its own: config/project.json
  `transports.extras` names the extra its packages live in, and a project
  that serves REST owes FastAPI on a laptop as much as in CI. Before this a
  local `make verify` without FastAPI reported the REST suites as skipped.
* A module guarding an import names the surface that import belongs to.
* Declared  -> a real import, whose ImportError is a hard collection error.
* Undeclared -> `importorskip`, so a bare local clone still skips gracefully.

Keep `DELIBERATELY_OPTIONAL` honest: an entry there is a promise that the surface
is opt-in, not a place to silence an install problem.
"""

import importlib
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402

_ENABLED = ("transports", "enabled")
_TRANSPORT_EXTRAS = ("transports", "extras")

#: Environment variable CI sets to declare which optional surfaces it installed.
ENV_VAR = "KEEL_REQUIRED_EXTRAS"

#: The surface vocabulary: name -> the CI step that installs it. A name is valid
#: only if it appears here, so a typo in ci.yml (`tempalte`) is a loud error
#: instead of silently disabling the very guard it was meant to switch on — which
#: is the failure mode this whole module exists to remove.
SURFACES = {
    "template": 'pip install -e ".[dev,template]"',  # copier + its yaml
    "dev": 'pip install -e ".[dev,template]"',  # pytest, jsonschema, httpx
    "transport": 'pip install -e ".[dev,template]"',  # dev names transport
    "secrets": "make secrets-install",  # the pinned secret scanner, recorded
}

#: Surfaces that must stay a skip even in CI, with the reason. The langgraph
#: engine is selected by name at runtime (`get_runtime("langgraph")`); the default
#: `inprocess` runtime is pure stdlib, and keeping the default install
#: dependency-free is a deliberate property of the template.
DELIBERATELY_OPTIONAL = {
    "langgraph": "opt-in runtime engine; the default inprocess runtime is stdlib-only",
}


def served_extras(loaded=None):
    """The surfaces the enabled transports owe: config/project.json
    `transports.extras[t]` for each t in `transports.enabled`, read from
    *loaded* or, when None, from this checkout through the loader."""
    values = config_loader.resolve(
        config_loader.read(_ROOT) if loaded is None else loaded,
        config_loader.rows(_ENABLED, _TRANSPORT_EXTRAS),
        config_loader.CONFIG_FILE,
    )
    by_transport = values[_TRANSPORT_EXTRAS]
    return {by_transport[t] for t in values[_ENABLED] if t in by_transport}


def required_extras(loaded=None):
    """The surfaces CI declared and the enabled transports owe, validated
    against `SURFACES`; *loaded* is the config to read, this checkout's when
    None."""
    declared = {p.strip() for p in os.environ.get(ENV_VAR, "").split(",") if p.strip()}
    served = served_extras(loaded)
    for source, names in (
        (ENV_VAR, declared),
        ("config/project.json transports.extras", served),
    ):
        unknown = sorted(names - set(SURFACES))
        if unknown:
            raise RuntimeError(
                "%s names unknown surface(s) %s; known: %s. A typo here silently "
                "disables the hard-failure guard, so it is an error rather than a "
                "no-op." % (source, unknown, sorted(SURFACES))
            )
    return declared | served


def importorskip(module, extra, loaded=None):
    """Import `module`, or skip — unless `extra` is required, by CI or by an
    enabled transport (see `required_extras`; *loaded* is passed to it).

    `extra` must be a key of `SURFACES`: naming a surface that nothing installs
    would make this call permanently a skip.
    """
    if extra not in SURFACES:
        raise ValueError(
            "unknown surface %r for module %r; add it to SURFACES with the CI step "
            "that installs it, or use pytest.importorskip if it is genuinely "
            "optional" % (extra, module)
        )
    if extra in required_extras(loaded):
        # A real import: ImportError propagates and collection fails loudly.
        return importlib.import_module(module)
    return pytest.importorskip(module)


def require_or_skip(available, extra, reason, loaded=None):
    """Return when *available*; otherwise skip, or fail when *extra* is
    required by CI or by an enabled transport (*loaded* as `required_extras`). For a surface that is not a Python import, such as a
    program an installer builds: *reason* says what is missing."""
    if extra not in SURFACES:
        raise ValueError(
            "unknown surface %r; add it to SURFACES with the CI step that "
            "installs it" % (extra,)
        )
    if available:
        return
    if extra in required_extras(loaded):
        pytest.fail(
            "%s, and %s or an enabled transport declares %r required; run `%s`"
            % (reason, ENV_VAR, extra, SURFACES[extra])
        )
    pytest.skip("%s; `%s` installs it" % (reason, SURFACES[extra]))
