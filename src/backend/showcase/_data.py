"""
title: Showcase curated content
layer: backend
public_api: no
summary: The product narrative — features, deterministic-check catalogue, and setup steps.
"""
from __future__ import annotations

from ._models import Check, Feature, Link, Step

TAGLINE = "A polyglot-aware, agent-friendly project skeleton that stays honest."
SUMMARY = (
    "project_keel is a generic project skeleton with a strict, documented "
    "structure that both humans and coding agents can navigate. Every directory "
    "is labelled, every package has a public-API boundary, and a suite of "
    "deterministic checks keeps any project built from it structurally honest."
)

# The three load-bearing conventions (kept in step with README.md).
CONVENTIONS: tuple[str, ...] = (
    "__init__.py is the API — nothing leaves a package except through __all__.",
    "Every directory is labelled with README.md + CLAUDE.md frontmatter.",
    "Tests mirror src/ where it helps; integration/e2e/smoke go by scenario.",
)

FEATURES: tuple[Feature, ...] = (
    Feature(
        slug="deterministic-checks",
        title="Deterministic checks",
        summary="A linter for the template itself — same input, same verdict.",
        detail=(
            "Structure, frontmatter, package boundaries, the doc/code corpus and "
            "the published contracts are all enforced by stdlib, model-free checks "
            "that run identically in CI and on a laptop."
        ),
        icon="check",
        links=(Link("Checks catalogue", "docs-guides-deterministic-checks"),),
    ),
    Feature(
        slug="labelled-tree",
        title="Self-describing tree",
        summary="Every directory carries README + CLAUDE frontmatter.",
        detail=(
            "Files sort and route mechanically by their labels (kind, layer, "
            "status, owner, visibility), so humans and agents find their way "
            "without reading every file."
        ),
        icon="tree",
        links=(Link("Conventions", "conventions"),),
    ),
    Feature(
        slug="package-boundary",
        title="Enforced boundaries",
        summary="__init__.py is the public API; privates stay private.",
        detail=(
            "No code may import another package's _private module; callers go "
            "through the package's __all__. The boundary is checked, not just "
            "documented."
        ),
        icon="boundary",
        links=(),
    ),
    Feature(
        slug="vendor-neutral",
        title="Vendor-neutral by design",
        summary="Neutral concept first; a vendor is a thin, swappable adapter.",
        detail=(
            "Model providers live behind models/, schedulers and hooks behind thin "
            "triggers, wire formats behind adapters — so no single vendor is baked "
            "into the doer."
        ),
        icon="plug",
        links=(),
    ),
    Feature(
        slug="one-brain-corpus",
        title="One-brain corpus",
        summary="The repo compiles into a browsable knowledge graph.",
        detail=(
            "A deterministic job walks docs and code into wiki/corpus.json — nodes "
            "(doc/section/module/symbol) with tree and keyword-link edges — the "
            "data this very site renders."
        ),
        icon="brain",
        links=(Link("Wiki", "wiki-readme"),),
    ),
    Feature(
        slug="polyglot",
        title="Polyglot, layered",
        summary="Python backend, a TS frontend, REST/gRPC/MCP at the edges.",
        detail=(
            "Facts about each layer live in config/project.json and are checked "
            "against the tree, so 'what is this project made of' never drifts."
        ),
        icon="layers",
        links=(),
    ),
    Feature(
        slug="agent-surface",
        title="Agent surface",
        summary="A service can describe itself as a discoverable agent.",
        detail=(
            "A neutral AgentSurface contract (card/ask/health) with a thin wire "
            "adapter (AAD) whose JSON Schema is generated from the model and "
            "gate-checked for drift."
        ),
        icon="robot",
        links=(Link("Agent-surface guide", "docs-guides-agent-surface"),),
    ),
    Feature(
        slug="agent-runtimes",
        title="Durable agent control flow",
        summary="Agents declare a Plan; a swappable Runtime executes it — durably.",
        detail=(
            "An agent's control flow is a neutral Plan (typed steps + edges) run "
            "by a Runtime. The default engine is pure stdlib; LangGraph is one "
            "optional adapter. Durability, human-in-the-loop, fan-out and "
            "streaming are built in — a crash mid-fill resumes instead of "
            "re-running model calls."
        ),
        icon="flow",
        links=(Link("Agent-runtimes guide", "docs-guides-agent-runtimes"),
               Link("ADR-0003", "docs-adr-0003-agent-control-flow-runtime")),
    ),
    Feature(
        slug="dev-loops",
        title="Disciplined by default",
        summary="Any LLM working here defaults to TDD, bounded loops, and e2e tests.",
        detail=(
            "The agent rules bake in the development loops, so a coding agent "
            "applies them automatically: test-first (red-green-refactor), "
            "bounded convergence over multi-step work, end-to-end coverage for "
            "user-facing flows, and 'done' meaning a green make verify — never a "
            "self-report."
        ),
        icon="loop",
        links=(Link("Dev-loops playbook", "docs-guides-dev-loops"),),
    ),
)

# Mirrors docs/guides/deterministic-checks.md. `present` is set at load time.
CHECKS: tuple[Check, ...] = (
    Check(
        slug="structure", name="Structure & frontmatter",
        script="scripts/check_structure.py", gate="error", interpreter="3.6-safe",
        command="make check", when="Every commit and in CI",
        purpose="Labels, taxonomy, package boundaries, tool/agent governance, "
                "project facts and agent-rules symlinks (checks A–I).",
    ),
    Check(
        slug="scaffold-sync", name="Scaffold-embed sync",
        script="scripts/check_scaffold_sync.py", gate="error", interpreter="3.6-safe",
        command="python3 scripts/check_scaffold_sync.py", when="Every commit",
        purpose="scaffold.py's embedded scripts stay byte-identical to the live files.",
    ),
    Check(
        slug="corpus", name="Corpus integrity & determinism",
        script="scripts/jobs/check_corpus.py", gate="error", interpreter=">=3.7",
        command="python scripts/jobs/check_corpus.py", when="CI and after corpus changes",
        purpose="wiki/corpus.json is a valid, acyclic graph and the build is reproducible.",
    ),
    Check(
        slug="openapi", name="OpenAPI drift",
        script="api/rest_fastapi/export_openapi.py", gate="error", interpreter="FastAPI",
        command="make check-openapi", when="When routes change; in CI",
        purpose="The committed openapi.json matches the live FastAPI routes.",
    ),
    Check(
        slug="aad-schema", name="AAD schema drift",
        script="scripts/agent_surface/generate_aad_schema.py", gate="error",
        interpreter="pydantic", command="make check-aad",
        when="When the AAD model changes; in CI",
        purpose="The committed AAD JSON Schema matches the AadDescriptor model.",
    ),
    Check(
        slug="cdmon", name="Code-doc drift",
        script="scripts/cdmon_sync.py", gate="error", interpreter="any",
        command="python3 scripts/cdmon_sync.py --check", when="Every commit (no-op until installed)",
        purpose="cdmon code↔doc drift monitor (a thin adapter; optional).",
    ),
)

SETUP_STEPS: tuple[Step, ...] = (
    Step(title="Get the template",
         body="Copy or fork the repository to seed your own project.",
         command="git clone <this-repo> project_keel && cd project_keel"),
    Step(title="Make it yours",
         body="Rename src/backend/example_feature/ to your first real package and "
              "delete the optional dirs you do not need (wiki/, models/, evals/, "
              "containers/).",
         command="make scaffold"),
    Step(title="Pick one frontend stack",
         body="Set layers.frontend.stack in config/project.json and delete the "
              "stack dirs you are not using; the checks enforce the choice.",
         command=""),
    Step(title="Run the checks",
         body="The fast structural gate runs anywhere; the full suite runs under "
              "your project interpreter.",
         command="make check   # or: make check-all"),
    Step(title="Wire the hooks",
         body="Install pre-commit so the deterministic checks run on every commit; "
              "CI already runs `make check-all`.",
         command="pip install pre-commit && pre-commit install"),
)

__all__ = ["TAGLINE", "SUMMARY", "CONVENTIONS", "FEATURES", "CHECKS", "SETUP_STEPS"]
