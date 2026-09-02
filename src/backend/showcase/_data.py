"""
title: Showcase curated content
layer: backend
public_api: no
summary: The product narrative — features, deterministic-check catalogue, and setup steps.
"""

from __future__ import annotations

from ._models import Check, Feature, Link, Principle, Step

TAGLINE = "A polyglot-aware, agent-friendly project skeleton that stays honest."
# `{title}`, not a literal: this is the copy a GENERATED project shows on its own
# overview page, so a hardcoded name there presents that project as the template it
# came from. `_repo.py` fills it from the manifest name.
SUMMARY_TEMPLATE = (
    "{title} is a generic project skeleton with a strict, documented "
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
        slug="edge-adapters",
        title="Tools & providers at the edge",
        summary="MCP tools, model providers, and scheduled jobs — each a thin adapter.",
        detail=(
            "The same capabilities reach the world through interchangeable "
            "adapters: MCP servers expose agents as tools (read-only Q&A, actions "
            "dry-run by default), any OpenAI-compatible endpoint or a local/fake "
            "model plugs in behind models/, and a scheduled job runs the same doer "
            "from cron, systemd, or CI. Pick one by name; nothing downstream changes."
        ),
        icon="plug",
        links=(
            Link("MCP servers", "mcp-readme"),
            Link("Model adapters", "models-readme"),
            Link("Scheduled jobs", "ops-scheduled-readme"),
        ),
    ),
    Feature(
        slug="coding-practices",
        title="Coding practices, enforced or advised",
        summary="Good-Python (and LLM/CUDA/LangGraph) habits sorted onto the gate/advise line.",
        detail=(
            "Precise container types, no implicit Optional, exception chaining, "
            "ABC hygiene, structured logging and an owned-exception boundary are "
            "gates that block make verify; injection, singledispatch and hot-path "
            "__slots__ are non-blocking advisories. Each practice is a row in "
            "config/practices.json; AI/CUDA/LangGraph rules ship off by default "
            "behind a profile, so the core stays domain-neutral."
        ),
        icon="check",
        links=(
            Link("Practices guide", "docs-guides-coding-practices"),
            Link("Checks catalogue", "docs-guides-deterministic-checks"),
        ),
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
        links=(
            Link("Agent-runtimes guide", "docs-guides-agent-runtimes"),
            Link("ADR-0003", "docs-adr-0003-agent-control-flow-runtime"),
        ),
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
    Feature(
        slug="generic-solution",
        title="Generic by default",
        summary="Any LLM here solves the class of inputs, not the example.",
        detail=(
            "The agent rules push every change toward the general rule: the "
            "eval is a sample not the spec, derive outputs from inputs, fix the "
            "generator not the golden — so a coding agent stops fitting the "
            "solution to one test. An advisory check (make advise) flags "
            "answer-key literals hardcoded in src/; it draws attention, never "
            "fails the build."
        ),
        icon="generic",
        links=(Link("Generic-solution playbook", "docs-guides-generic-solution"),),
    ),
)

# The governing conventions, deeper than the three headline ones above. Each
# summarises one CONVENTIONS section and links to it (read the rule in full in
# the wiki). Curated, not generated — kept in step with CONVENTIONS.md.
PRINCIPLES: tuple[Principle, ...] = (
    Principle(
        slug="agent-rules",
        title="One rule source, for humans and agents",
        essence="`AGENT.md` is the canonical, vendor-neutral rules file; "
        "`CLAUDE.md` is a symlink to it.",
        detail=(
            "Every directory's rules live in `AGENT.md`, and `CLAUDE.md` is just "
            "a symlink to its sibling — so Claude Code and any other agent tool "
            "read exactly the rules a human does. You edit `AGENT.md`, never the "
            "symlink; rules cascade from the root and a more specific directory "
            "overrides where it is stricter. The symlink is gate-checked, so the "
            "two cannot drift."
        ),
        links=(
            Link(
                "AGENT.md is canonical",
                "conventions#agent-rules-file-agent-md-is-canonical-claude-md-is-a-symlink",
            ),
        ),
    ),
    Principle(
        slug="labels",
        title="Every doc is labelled twice over",
        essence="Frontmatter routes files for humans and feeds the company-wide "
        "'one brain'.",
        detail=(
            "The human half (`kind`, `layer`, `status`, `owner`, `tags`, "
            "`summary`) lets files sort and route without being read. The corpus "
            "half (`id`, `created`/`updated`, `visibility`, `canonical`) lets one "
            "retrieval layer ingest every doc without garbage — `id` survives "
            "renames, `canonical` dedups mirrors, `visibility` keeps a "
            "confidential doc from the wrong audience. Code files carry no YAML, "
            "so the module docstring is the label and `__all__` is the public API."
        ),
        links=(
            Link(
                "Frontmatter scheme",
                "conventions#1-frontmatter-labeling-for-sort-route",
            ),
            Link(
                "Corpus-core fields",
                "conventions#corpus-core-fields-the-one-brain-reads-these",
            ),
        ),
    ),
    Principle(
        slug="taxonomy",
        title="Every directory has a fixed job",
        essence="A closed table gives each directory a kind and a "
        "'what goes in, what does not'.",
        detail=(
            "`src/` is the only home for production code, split frontend / "
            "backend / shared / app; transports live in `api/` and `mcp/`, "
            "automation in `scripts/`, agent brains in `agents/` — each with an "
            "explicit boundary on what it must not hold. A new directory is not "
            "finished until it carries a `README.md` and an `AGENT.md` with valid "
            "frontmatter, which is how the tree stays self-describing."
        ),
        links=(Link("Directory taxonomy", "conventions#2-directory-taxonomy"),),
    ),
    Principle(
        slug="boundary",
        title="`__init__.py` is the API; depend on contracts",
        essence="Nothing leaves a package except through `__all__`; cross-package "
        "wiring is a contract, not a class.",
        detail=(
            "Implementation lives in `_underscore` modules and is never imported "
            "across a package boundary — callers go through the package's "
            "`__init__.py`. Cross-package interfaces are ABCs or "
            "`typing.Protocol` in `contracts.py`, so you depend on the contract, "
            "not the concrete class. The same shape has polyglot analogs: a TS "
            "`index.ts` barrel, Go's capitalised exports, Rust's `pub` in "
            "`mod.rs`."
        ),
        links=(
            Link(
                "The boundary rule",
                "conventions#3-the-init-py-boundary-rule-the-important-one",
            ),
        ),
    ),
    Principle(
        slug="layering",
        title="Dependencies point one way",
        essence="`app → {frontend, backend} → shared`, and `shared/` depends on "
        "nothing.",
        detail=(
            "Frontend and backend never import each other; they meet through "
            "`shared/` — the framework-free FE↔BE contract — and are wired "
            "together in `app/`, which holds no business logic. `shared/` is for "
            "domain-meaningful types shared across a section; `util/` is for "
            "generic, domain-agnostic helpers — if a helper knows about your "
            "domain, it belongs in `shared/`."
        ),
        links=(
            Link("shared vs util", "conventions#4-shared-vs-util"),
            Link("Architecture", "docs-architecture-readme"),
        ),
    ),
    Principle(
        slug="triggers-doers",
        title="A trigger says when; a doer says what",
        essence="Automation splits in two: the doer holds the logic, the trigger "
        "is a thin adapter.",
        detail=(
            "Deterministic doers live in `scripts/` and LLM doers in `agents/` "
            "(model from `models/`); both are vendor-agnostic. The trigger — a "
            "pre-commit hook, a CI workflow, a cron entry — only records when to "
            "run and points at the doer, holding no logic. Swapping cron for "
            "systemd, or one agent ecosystem for another, never touches the doer."
        ),
        links=(
            Link(
                "Triggers vs doers",
                "conventions#7-triggers-vs-doers-hooks-scheduled-jobs",
            ),
        ),
    ),
    Principle(
        slug="adapters",
        title="Name the neutral concept; a vendor is one adapter",
        essence="Providers and engines hide behind a neutral contract, selected "
        "by name.",
        detail=(
            "A model provider lives behind `models/` (an agent gets its model "
            "from a registry, never a provider name); an agent's control flow is "
            "a neutral `Plan` run by a swappable `Runtime`, whose default engine "
            "is pure stdlib and whose vendor engine (e.g. LangGraph) is one "
            "lazily-loaded, optional adapter. Adapters change execution, never "
            "semantics — an equivalence test holds every engine to the reference."
        ),
        links=(
            Link(
                "runtimes/",
                "conventions#16-agent-control-flow-runtimes-a-neutral-plan-engines-are-adapters",
            ),
            Link("models/", "models-readme"),
        ),
    ),
    Principle(
        slug="agents",
        title="An agent is an in-process brain or a published surface",
        essence="Compiled in-process → a function; across a process boundary → an "
        "agent surface.",
        detail=(
            "An in-process agent lives in `agents/<name>/` — its `prompt.md`, a "
            "private `_brain.py`, and a `tools.md` manifest — and defaults model "
            "calls and writes to dry-run (`execute=False`). A service that "
            "crosses a process boundary publishes a neutral `AgentSurface` "
            "(`card` / `ask` / `health`) instead, with the wire dialect (the "
            "shipped reference is AAD) a thin adapter whose schema is generated "
            "and gate-checked for drift."
        ),
        links=(
            Link(
                "Agent surface",
                "conventions#14-exposing-a-service-as-an-agent-the-agent-surface",
            ),
            Link("Agent-surface guide", "docs-guides-agent-surface"),
        ),
    ),
    Principle(
        slug="manifest",
        title="Project facts live in one checked file",
        essence="`config/project.json` records the per-layer facts, and the "
        "checker won't let them drift.",
        detail=(
            "Because the repo is polyglot, 'what is this made of' is a set of "
            "per-layer facts — each layer's language and chosen stack, and which "
            "transports are enabled — not one global language. "
            "`check_structure.py` errors when a declared path, stack, or "
            "transport directory is missing, when `enabled` is not a subset of "
            "`available`, or when `backend.python` disagrees with "
            "`pyproject.toml`. It is a committed decision read by the gate, not "
            "the app."
        ),
        links=(
            Link(
                "Project manifest",
                "conventions#15-project-facts-manifest-config-project-json",
            ),
        ),
    ),
)

# Mirrors docs/guides/deterministic-checks.md. `present` is set at load time.
CHECKS: tuple[Check, ...] = (
    Check(
        slug="structure",
        name="Structure & frontmatter",
        script="scripts/check_structure.py",
        gate="error",
        interpreter="3.6-safe",
        command="make check",
        when="Every commit and in CI",
        purpose="Labels, taxonomy, package boundaries, tool/agent governance, "
        "project facts, agent-rules symlinks, ruleset parity, template twin "
        "parity, the machine-readable module contract, Makefile help parity, cross-reference resolution, check-catalogue parity and rosters (checks A–S).",
    ),
    Check(
        slug="python-floor",
        name="Interpreter floor",
        script="scripts/check_python_version.py",
        gate="error",
        interpreter="any",
        command="make check-python",
        when="Before every check that needs the project interpreter",
        purpose="$(PY) satisfies pyproject.toml's requires-python, said plainly "
        "before a newer-syntax check fails with a traceback.",
    ),
    Check(
        slug="corpus",
        name="Corpus integrity & determinism",
        script="scripts/jobs/check_corpus.py",
        gate="error",
        interpreter=">=3.7",
        command="python scripts/jobs/check_corpus.py",
        when="CI and after corpus changes",
        purpose="wiki/corpus.json is a valid, acyclic graph and the build is reproducible.",
    ),
    Check(
        slug="openapi",
        name="OpenAPI drift",
        script="api/rest_fastapi/export_openapi.py",
        gate="error",
        interpreter="FastAPI",
        command="make check-openapi",
        when="When routes change; in CI",
        purpose="The committed openapi.json matches the live FastAPI routes.",
    ),
    Check(
        slug="aad-schema",
        name="AAD schema drift",
        script="scripts/agent_surface/generate_aad_schema.py",
        gate="error",
        interpreter="pydantic",
        command="make check-aad",
        when="When the AAD model changes; in CI",
        purpose="The committed AAD JSON Schema matches the AadDescriptor model.",
    ),
    Check(
        slug="cdmon",
        name="Code-doc drift",
        script="scripts/cdmon_sync.py",
        gate="error",
        interpreter="any",
        command="python3 scripts/cdmon_sync.py --check",
        when="Every commit and under check-all (a stated skip until installed)",
        purpose="cdmon code↔doc drift monitor (a thin adapter over an external "
        "tool; optional).",
    ),
    Check(
        slug="doc-freshness",
        name="Doc freshness",
        script="scripts/review_docs.py",
        gate="report",
        interpreter="any (git)",
        command="make advise",
        when="Anytime; gated by tests/integration/test_doc_freshness.py",
        purpose="Every governed document's `updated:` is no earlier than its last "
        "commit, and a document modified in the working tree carries today's date.",
    ),
    Check(
        slug="accountability",
        name="Accountability report",
        script="scripts/accountability_report.py",
        gate="report",
        interpreter=">=3.7",
        command="make advise",
        when="Anytime; informational",
        purpose="Lists corpus nodes that resolve to no owner.",
    ),
    Check(
        slug="generic",
        name="Generic-solution advisor",
        script="scripts/check_generic.py",
        gate="report",
        interpreter="3.6-safe",
        command="make advise",
        when="Anytime; advisory (never fails the build)",
        purpose="Flags distinctive literals asserted as a test's expected value "
        "AND hardcoded in src/ logic — a 'fit the solution to the eval' "
        "smell. Advisory: draws attention, never gates. Suppress with "
        "# generic-ok: <reason>.",
    ),
    Check(
        slug="practices",
        name="Coding-practices advisor",
        script="scripts/check_practices.py",
        gate="report",
        interpreter="3.6-safe",
        command="make advise",
        when="Anytime; advisory (never fails the build)",
        purpose="Coding-practice smells read from config/practices.json. "
        "Advisory: draws attention, never gates.",
    ),
)

SETUP_STEPS: tuple[Step, ...] = (
    Step(
        title="Generate your project",
        body="One command runs an interactive Q&A (name, frontend stack, transports, "
        "domain profiles) and writes a tailored skeleton: the chosen stack, a "
        "filled-in config/project.json, and a .copier-answers.yml so you can pull "
        "future template improvements later. The template URL is whatever this "
        "project recorded as `_src_path` in .copier-answers.yml. Needs copier "
        "(pipx install copier, or pip install '.[template]' in a checkout).",
        command="copier copy <template-url> my-project",
    ),
    Step(
        title="Make it yours",
        # `models/` is deliberately NOT in this list, and README.md explains why:
        # config/project.json declares three model adapters, so deleting the
        # directory leaves the manifest claiming what no longer exists and
        # `make check` correctly reports 3 errors. The product page used to say
        # `models/`, so the two shipped surfaces gave opposite advice and this one
        # broke the newcomer's first command.
        body="Rename src/backend/example_feature/ to your first real package and delete "
        "any optional dirs you don't need (wiki/, evals/, containers/). Removing "
        "models/ also means removing its adapters from config/project.json, or "
        "`make check` will report the manifest claiming what is gone.",
        command="",
    ),
    Step(
        title="Run the checks",
        body="The fast structural gate runs anywhere; the full suite runs under your "
        "project interpreter.",
        command="make check   # or: make verify",
    ),
    Step(
        title="Wire the hooks",
        body="Install pre-commit so the deterministic checks run on every commit; CI "
        "already runs `make check-all`.",
        command="pip install pre-commit && pre-commit install",
    ),
    Step(
        title="Pull template updates later",
        body="When the template this project came from improves, re-apply the changes — copier "
        "three-way merges them using your recorded answers. `--trust` is required: "
        "re-answering a question has to remove what you declined, and copier only "
        "deletes through migrations, which run commands.",
        command="copier update --trust",
    ),
)

__all__ = [
    "TAGLINE",
    "SUMMARY_TEMPLATE",
    "CONVENTIONS",
    "FEATURES",
    "PRINCIPLES",
    "CHECKS",
    "SETUP_STEPS",
]
